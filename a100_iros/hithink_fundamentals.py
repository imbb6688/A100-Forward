from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import requests

from .models import EvidenceItem, EvidenceKind, ResearchObject
from .pipeline import ResearchPipeline


BASE_URL = "https://fuyao.aicubes.cn"
STATEMENT_ENDPOINTS = {
    "income": "/api/a-share/financials/income-statements",
    "balance_sheet": "/api/a-share/financials/balance-sheets",
    "cash_flow": "/api/a-share/financials/cash-flow-statements",
}
INDICATORS_ENDPOINT = "/api/a-share/financials/indicators"
VALUATION_ENDPOINT = "/api/a-share/valuations/snapshot"


@dataclass(frozen=True)
class HiThinkFundamentalBundle:
    ticker: str
    period: str
    indicator_report: Optional[str]
    income: List[Dict[str, Any]]
    balance_sheet: List[Dict[str, Any]]
    cash_flow: List[Dict[str, Any]]
    indicators: Dict[str, Any]
    valuation: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "period": self.period,
            "indicator_report": self.indicator_report,
            "income": list(self.income),
            "balance_sheet": list(self.balance_sheet),
            "cash_flow": list(self.cash_flow),
            "indicators": dict(self.indicators),
            "valuation": dict(self.valuation),
        }


class HiThinkFundamentalsClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("api_key must not be empty")
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.session = session or requests.Session()

    def _get(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        response = self.session.get(
            self.base_url + endpoint,
            params=params,
            headers={"X-api-key": self.api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("HiThink response must be a JSON object")
        code = payload.get("code")
        if code not in (0, "0", None):
            raise RuntimeError(
                f"HiThink API error code={code}, message={payload.get('message')!r}, request_id={payload.get('request_id')!r}"
            )
        data = payload.get("data")
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ValueError("HiThink response data must be a JSON object")
        return data

    @staticmethod
    def _items(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw = data.get("item", [])
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise ValueError("HiThink data.item must be a list")
        return [dict(row) for row in raw if isinstance(row, dict)]

    @staticmethod
    def _indicator_report_from_statements(rows: Iterable[Dict[str, Any]]) -> Optional[str]:
        candidates: List[tuple[int, str]] = []
        quarter_map = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 4}
        for row in rows:
            year = row.get("fiscal_year")
            fiscal_period = str(row.get("fiscal_period") or "").upper()
            period_end_ms = row.get("period_end_ms")
            if isinstance(year, int) and fiscal_period in quarter_map:
                key = int(period_end_ms) if isinstance(period_end_ms, (int, float)) else year * 10 + quarter_map[fiscal_period]
                candidates.append((key, f"{year}-{quarter_map[fiscal_period]}"))
        return max(candidates, key=lambda pair: pair[0])[1] if candidates else None

    def financials(
        self,
        ticker: str,
        *,
        period: str = "annual",
        limit: int = 5,
    ) -> HiThinkFundamentalBundle:
        ticker = ticker.strip().upper()
        if not ticker:
            raise ValueError("ticker must not be empty")
        if period not in {"annual", "quarterly"}:
            raise ValueError("period must be annual or quarterly")
        if not 1 <= int(limit) <= 20:
            raise ValueError("limit must be between 1 and 20")

        base_params = {"thscode": ticker, "period": period, "limit": int(limit)}
        statements: Dict[str, List[Dict[str, Any]]] = {}
        for name, endpoint in STATEMENT_ENDPOINTS.items():
            statements[name] = self._items(self._get(endpoint, base_params))

        indicator_report = self._indicator_report_from_statements(statements["income"])
        indicators: Dict[str, Any] = {}
        if indicator_report:
            indicators = dict(
                self._get(
                    INDICATORS_ENDPOINT,
                    {"thscode": ticker, "report": indicator_report},
                )
            )

        valuation_data = self._get(VALUATION_ENDPOINT, {"thscodes": ticker})
        valuation_items = self._items(valuation_data)
        valuation = valuation_items[0] if valuation_items else {}

        return HiThinkFundamentalBundle(
            ticker=ticker,
            period=period,
            indicator_report=indicator_report,
            income=statements["income"],
            balance_sheet=statements["balance_sheet"],
            cash_flow=statements["cash_flow"],
            indicators=indicators,
            valuation=valuation,
        )


def _latest_report_date_ms(rows: Iterable[Dict[str, Any]]) -> Optional[int]:
    values = []
    for row in rows:
        value = row.get("report_date_ms")
        if isinstance(value, (int, float)):
            values.append(int(value))
    return max(values) if values else None


def enrich_research_object_with_hithink_fundamentals(
    obj: ResearchObject,
    bundle: HiThinkFundamentalBundle,
) -> ResearchObject:
    if obj.security.ticker != bundle.ticker:
        raise ValueError("bundle ticker does not match research object")

    pipeline = ResearchPipeline(obj)
    latest_report_date_ms = max(
        [
            value
            for value in (
                _latest_report_date_ms(bundle.income),
                _latest_report_date_ms(bundle.balance_sheet),
                _latest_report_date_ms(bundle.cash_flow),
            )
            if value is not None
        ],
        default=None,
    )
    pipeline.set_fundamentals(
        {
            "source": "HiThink Financial-API",
            "period": bundle.period,
            "indicator_report": bundle.indicator_report,
            "income": bundle.income,
            "balance_sheet": bundle.balance_sheet,
            "cash_flow": bundle.cash_flow,
            "indicators": bundle.indicators,
            "latest_report_date_ms": latest_report_date_ms,
        }
    )
    pipeline.set_valuation(
        {
            "source": "HiThink Financial-API",
            "snapshot": bundle.valuation,
        }
    )
    pipeline.add_evidence(
        [
            EvidenceItem(
                kind=EvidenceKind.FACT,
                statement=(
                    f"HiThink fundamentals loaded for {bundle.ticker}: "
                    f"income={len(bundle.income)}, balance={len(bundle.balance_sheet)}, "
                    f"cashflow={len(bundle.cash_flow)}, indicator_report={bundle.indicator_report or 'none'}."
                ),
                source="HiThink Financial-API",
                confidence=1.0,
            )
        ]
    )
    return obj
