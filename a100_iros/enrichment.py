from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from .hithink_context import HiThinkContextClient
from .hithink_fundamentals import (
    HiThinkFundamentalsClient,
    enrich_research_object_with_hithink_fundamentals,
)
from .hithink_live import (
    _compute_recent_features,
    _load_recent_daily,
    derive_market_regime,
    security_technical_snapshot,
)
from .memory import ResearchSnapshot
from .models import EvidenceItem, EvidenceKind, ResearchObject, SecurityResearchCard, Thesis, ThesisStance
from .pipeline import ResearchPipeline
from .repository import ResearchRepository


SCHEMA_VERSION = "A100-IROS-SECURITY-RESEARCH-FILE-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compact_timestamp(value: str) -> str:
    return "".join(ch for ch in value.replace("+00:00", "Z") if ch.isalnum())[:16]


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _ticker_from_row(row: Dict[str, Any]) -> str:
    for key in ("thscode", "ts_code", "symbol", "ticker", "stock_code", "code"):
        value = row.get(key)
        if value:
            return str(value).strip().upper()
    return ""


def _items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = payload.get("item", [])
    if not isinstance(raw, list):
        return []
    return [dict(row) for row in raw if isinstance(row, dict)]


@dataclass(frozen=True)
class EnrichmentTarget:
    ticker: str
    company_name: str = ""
    source: str = "WATCHLIST"
    source_payload: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized = self.ticker.strip().upper()
        if not normalized or "." not in normalized:
            raise ValueError("ticker must include exchange suffix")
        object.__setattr__(self, "ticker", normalized)
        object.__setattr__(self, "source", self.source.strip().upper() or "WATCHLIST")


@dataclass(frozen=True)
class EnrichmentResult:
    ticker: str
    research_id: str
    status: str
    security_file: Optional[str] = None
    snapshot_id: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SecurityResearchFile:
    generated_at: str
    as_of: str
    research_id: str
    ticker: str
    source: str
    source_fingerprint: str
    adapter_status: Dict[str, str]
    research_object: Dict[str, Any]
    snapshot_id: str
    governance: Dict[str, Any]
    raw_context: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            **asdict(self),
        }


class IROSEnrichmentOrchestrator:
    """Research-only coordinator for persistent HiThink-enriched security files.

    All network reads complete before repository state is written for a ticker.
    A failed ticker leaves its previous valid object and security file untouched.
    """

    def __init__(
        self,
        *,
        repository: ResearchRepository,
        normalized_daily_path: str | Path,
        fundamentals_client: HiThinkFundamentalsClient,
        context_client: HiThinkContextClient,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.repository = repository
        self.normalized_daily_path = Path(normalized_daily_path)
        self.fundamentals_client = fundamentals_client
        self.context_client = context_client
        self.clock = clock
        self.security_files_dir = self.repository.root / "security_files"
        self.history_dir = self.security_files_dir / "history"

    @staticmethod
    def research_id_for(ticker: str) -> str:
        return "SEC-" + ticker.strip().upper().replace(".", "-")

    def _base_object(self, target: EnrichmentTarget) -> ResearchObject:
        research_id = self.research_id_for(target.ticker)
        if self.repository.exists(research_id):
            obj = self.repository.load(research_id)
            if obj.security.ticker != target.ticker:
                raise ValueError("stored research object ticker mismatch")
            obj = copy.deepcopy(obj)
            if target.company_name:
                obj.security.company_name = target.company_name
            return obj
        return ResearchObject(
            research_id=research_id,
            security=SecurityResearchCard(
                ticker=target.ticker,
                company_name=target.company_name,
                thesis=Thesis(
                    stance=ThesisStance.UNDETERMINED,
                    base_case="Real data enriched; analyst thesis not yet completed.",
                    confidence=None,
                ),
            ),
        )

    def _prepare_industry_context(self, tickers: set[str]) -> Dict[str, Dict[str, Any]]:
        remaining = set(tickers)
        resolved: Dict[str, Dict[str, Any]] = {}
        catalog = self.context_client.index_catalog("industry")
        for index in catalog:
            if not remaining:
                break
            index_code = _ticker_from_row(index)
            if not index_code:
                continue
            constituents = self.context_client.index_constituents(index_code)
            for row in constituents:
                ticker = _ticker_from_row(row)
                if ticker in remaining:
                    resolved[ticker] = {
                        "source": "HiThink Financial-API",
                        "industry_index": dict(index),
                        "constituent": dict(row),
                    }
                    remaining.remove(ticker)
        for ticker in remaining:
            resolved[ticker] = {
                "source": "HiThink Financial-API",
                "industry_index": None,
                "constituent": None,
                "status": "NOT_RESOLVED",
            }
        return resolved

    def _prepare_event_context(self, tickers: Sequence[str], as_of: str) -> Dict[str, Dict[str, Any]]:
        by_ticker = {
            ticker: {
                "source": "HiThink Financial-API",
                "as_of": as_of,
                "anomaly": [],
                "dragon_tiger": [],
                "limit_up": [],
                "limit_down": [],
                "limit_break": [],
            }
            for ticker in tickers
        }
        for offset in range(0, len(tickers), 50):
            payload = self.context_client.anomaly_for_stocks(tickers[offset : offset + 50])
            for row in _items(payload):
                ticker = _ticker_from_row(row)
                if ticker in by_ticker:
                    by_ticker[ticker]["anomaly"].append(row)

        shared = {
            "dragon_tiger": self.context_client.dragon_tiger(board_type="all", date=as_of),
            "limit_up": self.context_client.limit_pool("up"),
            "limit_down": self.context_client.limit_pool("down"),
            "limit_break": self.context_client.limit_pool("break"),
        }
        for kind, payload in shared.items():
            for row in _items(payload):
                ticker = _ticker_from_row(row)
                if ticker in by_ticker:
                    by_ticker[ticker][kind].append(row)
        return by_ticker

    def _persist(
        self,
        *,
        obj: ResearchObject,
        target: EnrichmentTarget,
        generated_at: str,
        as_of: str,
        adapter_status: Dict[str, str],
        raw_context: Dict[str, Any],
    ) -> tuple[Path, str]:
        source_fingerprint = _fingerprint(
            {
                "target": asdict(target),
                "as_of": as_of,
                "technical": obj.security.technical_structure,
                "fundamentals": obj.security.fundamentals,
                "valuation": obj.security.valuation,
                "industry": obj.security.industry_context,
                "events": raw_context.get("events", {}),
            }
        )
        snapshot_id = f"{_compact_timestamp(generated_at)}-{source_fingerprint[:12]}"
        obj.metadata["enrichment"] = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "as_of": as_of,
            "source": target.source,
            "source_fingerprint": source_fingerprint,
            "adapter_status": dict(adapter_status),
            "research_only": True,
            "modifies_frozen_v7": False,
            "auto_promotes_state": False,
        }
        snapshot = ResearchSnapshot.capture(
            obj,
            snapshot_id=snapshot_id,
            captured_at=generated_at,
            note=f"HiThink enrichment from {target.source}",
        )
        security_file = SecurityResearchFile(
            generated_at=generated_at,
            as_of=as_of,
            research_id=obj.research_id,
            ticker=obj.security.ticker,
            source=target.source,
            source_fingerprint=source_fingerprint,
            adapter_status=dict(adapter_status),
            research_object=obj.to_dict(),
            snapshot_id=snapshot_id,
            governance={
                "research_only": True,
                "modifies_frozen_v7": False,
                "generates_orders": False,
                "auto_promotes_state": False,
                "validation_required": "Backtest -> Walk Forward -> Shadow/Paper -> Acceptance",
            },
            raw_context=raw_context,
        )
        payload = security_file.to_dict()
        archive_path = self.history_dir / target.ticker.replace(".", "-") / f"{snapshot_id}.json"
        repository_snapshot_path = self.repository.snapshot_path(obj.research_id, snapshot_id)
        if archive_path.exists() or repository_snapshot_path.exists():
            raise FileExistsError(f"security research snapshot already exists: {snapshot_id}")
        _atomic_json(archive_path, payload)
        self.repository.save_snapshot(snapshot)
        current_path = self.security_files_dir / f"{target.ticker.replace('.', '-')}.json"
        _atomic_json(current_path, payload)
        self.repository.save(obj)
        return current_path, snapshot_id

    def run(self, targets: Iterable[EnrichmentTarget], *, as_of: Optional[str] = None) -> Dict[str, Any]:
        unique: Dict[str, EnrichmentTarget] = {}
        for target in targets:
            unique[target.ticker] = target
        ordered = [unique[key] for key in sorted(unique)]
        if not ordered:
            raise ValueError("at least one enrichment target is required")

        generated_at = self.clock()
        recent = _compute_recent_features(_load_recent_daily(self.normalized_daily_path))
        metrics, market_regime = derive_market_regime(recent)
        effective_as_of = as_of or metrics.trade_date
        if effective_as_of != metrics.trade_date:
            raise ValueError("requested as_of does not match the market adapter trade date")

        tickers = [target.ticker for target in ordered]
        industry_context = self._prepare_industry_context(set(tickers))
        event_context = self._prepare_event_context(tickers, effective_as_of)

        results: List[EnrichmentResult] = []
        for target in ordered:
            research_id = self.research_id_for(target.ticker)
            try:
                obj = self._base_object(target)
                technical = security_technical_snapshot(recent, target.ticker)
                fundamental_bundle = self.fundamentals_client.financials(target.ticker)

                pipeline = ResearchPipeline(obj)
                pipeline.apply_market_regime(market_regime)
                pipeline.set_technical_structure(technical)
                pipeline.set_positioning(
                    {
                        "source": technical["source"],
                        "trade_date": technical["trade_date"],
                        "amount": technical["amount"],
                        "amount_ratio20": technical["amount_ratio20"],
                    }
                )
                enrich_research_object_with_hithink_fundamentals(obj, fundamental_bundle)
                obj.security.industry_context = dict(industry_context[target.ticker])
                events = event_context[target.ticker]
                obj.metadata["event_context"] = copy.deepcopy(events)
                # The fundamentals adapter appends its own audit entries through a
                # separate pipeline instance; reload before recording later stages.
                pipeline = ResearchPipeline(obj)
                pipeline.add_evidence(
                    [
                        EvidenceItem(
                            kind=EvidenceKind.FACT,
                            statement=f"HiThink market data for {target.ticker} is aligned to {effective_as_of}.",
                            source="HiThink Market Adapter",
                            observed_at=effective_as_of,
                            confidence=1.0,
                        ),
                        EvidenceItem(
                            kind=EvidenceKind.FACT,
                            statement=f"HiThink industry context resolved for {target.ticker}: {industry_context[target.ticker].get('status', 'RESOLVED')}.",
                            source="HiThink Industry Adapter",
                            observed_at=effective_as_of,
                            confidence=1.0,
                        ),
                        EvidenceItem(
                            kind=EvidenceKind.FACT,
                            statement=(
                                f"HiThink event context loaded for {target.ticker}: "
                                f"anomaly={len(events['anomaly'])}, dragon_tiger={len(events['dragon_tiger'])}, "
                                f"limit_up={len(events['limit_up'])}, limit_down={len(events['limit_down'])}, "
                                f"limit_break={len(events['limit_break'])}."
                            ),
                            source="HiThink Event Adapter",
                            observed_at=effective_as_of,
                            confidence=1.0,
                        ),
                    ]
                )
                adapter_status = {
                    "market": "COMPLETE",
                    "industry": "COMPLETE" if industry_context[target.ticker].get("industry_index") else "COMPLETE_NOT_RESOLVED",
                    "fundamentals": "COMPLETE",
                    "valuation": "COMPLETE",
                    "events": "COMPLETE",
                    "capital_flow": "UNAVAILABLE_UPSTREAM",
                }
                current_path, snapshot_id = self._persist(
                    obj=obj,
                    target=target,
                    generated_at=generated_at,
                    as_of=effective_as_of,
                    adapter_status=adapter_status,
                    raw_context={
                        "target": asdict(target),
                        "market_metrics": metrics.to_dict(),
                        "industry": industry_context[target.ticker],
                        "events": events,
                    },
                )
                results.append(
                    EnrichmentResult(
                        ticker=target.ticker,
                        research_id=research_id,
                        status="COMPLETE",
                        security_file=str(current_path),
                        snapshot_id=snapshot_id,
                    )
                )
            except Exception as exc:
                results.append(
                    EnrichmentResult(
                        ticker=target.ticker,
                        research_id=research_id,
                        status="FAILED_NO_WRITE",
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
                )

        summary = {
            "schema_version": "A100-IROS-ENRICHMENT-RUN-v1",
            "generated_at": generated_at,
            "as_of": effective_as_of,
            "market_metrics": metrics.to_dict(),
            "results": [result.to_dict() for result in results],
            "complete": sum(result.status == "COMPLETE" for result in results),
            "failed": sum(result.status != "COMPLETE" for result in results),
            "governance": {
                "research_only": True,
                "modifies_frozen_v7": False,
                "generates_orders": False,
                "auto_promotes_state": False,
            },
        }
        _atomic_json(self.repository.root / "enrichment_runs" / f"{_compact_timestamp(generated_at)}.json", summary)
        _atomic_json(self.repository.root / "latest_enrichment_run.json", summary)
        return summary


def targets_from_frozen_signal(signal: Dict[str, Any]) -> List[EnrichmentTarget]:
    trade_date = str(signal.get("latest_trade_date") or "")
    targets: List[EnrichmentTarget] = []
    for row in signal.get("top2", []):
        if not isinstance(row, dict) or not row.get("symbol"):
            continue
        targets.append(
            EnrichmentTarget(
                ticker=str(row["symbol"]),
                company_name=str(row.get("name") or ""),
                source="FROZEN_V7",
                source_payload={"trade_date": trade_date, "candidate": dict(row)},
            )
        )
    return targets


def targets_from_watchlist(rows: Iterable[Dict[str, Any]]) -> List[EnrichmentTarget]:
    targets: List[EnrichmentTarget] = []
    for row in rows:
        ticker = row.get("ticker") or row.get("symbol") or row.get("thscode")
        if not ticker:
            continue
        targets.append(
            EnrichmentTarget(
                ticker=str(ticker),
                company_name=str(row.get("company_name") or row.get("name") or ""),
                source="WATCHLIST",
                source_payload=dict(row),
            )
        )
    return targets
