from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .assessments import MarketRegimeAssessment, MarketRiskMode, TrendMode, ValidationStatus
from .models import EvidenceItem, EvidenceKind, ResearchObject, SecurityResearchCard, Thesis, ThesisStance
from .pipeline import ResearchPipeline
from .storage import save_research_object


REQUIRED_DAILY_COLUMNS = {
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
}


@dataclass(frozen=True)
class LiveMarketMetrics:
    trade_date: str
    symbol_count: int
    breadth_up_ratio: float
    above_ma20_ratio: float
    median_return_20d: float
    median_amount_ratio_20d: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _load_recent_daily(path: str | Path, sessions: int = 70) -> pd.DataFrame:
    pf = pq.ParquetFile(path)
    missing = REQUIRED_DAILY_COLUMNS - set(pf.schema.names)
    if missing:
        raise ValueError(f"HiThink normalized daily data missing columns: {sorted(missing)}")

    df = pq.read_table(path, columns=sorted(REQUIRED_DAILY_COLUMNS)).to_pandas()
    if df.empty:
        raise ValueError("HiThink normalized daily data is empty")
    df = df.sort_values(["trade_date", "ts_code"], kind="mergesort")
    dates = np.sort(df["trade_date"].dropna().astype("int64").unique())
    if len(dates) < 21:
        raise ValueError("at least 21 trading sessions are required for IROS live metrics")
    keep = dates[-min(int(sessions), len(dates)) :]
    recent = df[df["trade_date"].isin(keep)].copy()
    recent = recent.sort_values(["ts_code", "trade_date"], kind="mergesort").reset_index(drop=True)
    return recent


def _compute_recent_features(recent: pd.DataFrame) -> pd.DataFrame:
    g = recent.groupby("ts_code", sort=False)
    recent["prev_close_calc"] = g["close"].shift(1)
    recent["return_1d"] = recent["close"] / recent["prev_close_calc"] - 1.0
    recent["ma20"] = g["close"].transform(lambda s: s.rolling(20, min_periods=20).mean())
    recent["ma60"] = g["close"].transform(lambda s: s.rolling(60, min_periods=60).mean())
    recent["return_5d"] = g["close"].pct_change(5)
    recent["return_20d"] = g["close"].pct_change(20)
    recent["amount_ma20"] = g["amount"].transform(lambda s: s.rolling(20, min_periods=20).mean())
    recent["amount_ratio20"] = recent["amount"] / recent["amount_ma20"].replace(0, np.nan)

    prev_close = recent["prev_close_calc"]
    true_range = pd.concat(
        [
            recent["high"] - recent["low"],
            (recent["high"] - prev_close).abs(),
            (recent["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    recent["true_range"] = true_range
    recent["atr20"] = recent.groupby("ts_code", sort=False)["true_range"].transform(
        lambda s: s.rolling(20, min_periods=20).mean()
    )
    recent["atr20_pct"] = recent["atr20"] / recent["close"].replace(0, np.nan)
    recent["high20"] = recent.groupby("ts_code", sort=False)["high"].transform(
        lambda s: s.rolling(20, min_periods=20).max()
    )
    recent["distance_to_20d_high"] = recent["close"] / recent["high20"].replace(0, np.nan) - 1.0
    return recent


def derive_market_regime(recent_with_features: pd.DataFrame) -> tuple[LiveMarketMetrics, MarketRegimeAssessment]:
    latest_us = int(recent_with_features["trade_date"].max())
    latest = recent_with_features[recent_with_features["trade_date"] == latest_us].copy()
    eligible = latest[latest["ma20"].notna() & latest["prev_close_calc"].notna()].copy()
    if len(eligible) < 1000:
        raise ValueError(f"latest market sample too small for regime metrics: {len(eligible)}")

    breadth_up = float((eligible["return_1d"] > 0).mean())
    above_ma20 = float((eligible["close"] > eligible["ma20"]).mean())
    median_ret20 = float(eligible["return_20d"].median(skipna=True))
    median_amount_ratio20 = float(eligible["amount_ratio20"].median(skipna=True))
    trade_date = pd.to_datetime(latest_us, unit="us").strftime("%Y-%m-%d")

    if breadth_up >= 0.55 and above_ma20 >= 0.55:
        risk_mode = MarketRiskMode.RISK_ON
    elif breadth_up <= 0.45 and above_ma20 <= 0.45:
        risk_mode = MarketRiskMode.RISK_OFF
    else:
        risk_mode = MarketRiskMode.NEUTRAL

    if above_ma20 >= 0.60 and median_ret20 > 0:
        trend_mode = TrendMode.UP
    elif above_ma20 <= 0.40 and median_ret20 < 0:
        trend_mode = TrendMode.DOWN
    else:
        trend_mode = TrendMode.RANGE

    confidence = min(0.95, 0.50 + abs(breadth_up - 0.50) + abs(above_ma20 - 0.50))
    metrics = LiveMarketMetrics(
        trade_date=trade_date,
        symbol_count=int(eligible["ts_code"].nunique()),
        breadth_up_ratio=round(breadth_up, 6),
        above_ma20_ratio=round(above_ma20, 6),
        median_return_20d=round(median_ret20, 6),
        median_amount_ratio_20d=round(median_amount_ratio20, 6),
    )
    assessment = MarketRegimeAssessment(
        risk_mode=risk_mode,
        trend_mode=trend_mode,
        confidence=round(confidence, 6),
        rationale=[
            f"breadth_up_ratio={breadth_up:.3f}",
            f"above_ma20_ratio={above_ma20:.3f}",
            f"median_return_20d={median_ret20:.4f}",
            f"median_amount_ratio_20d={median_amount_ratio20:.3f}",
        ],
        validation_status=ValidationStatus.UNVALIDATED_RESEARCH_HEURISTIC,
    )
    return metrics, assessment


def security_technical_snapshot(recent_with_features: pd.DataFrame, ticker: str) -> Dict[str, Any]:
    ticker = ticker.strip().upper()
    rows = recent_with_features[recent_with_features["ts_code"].astype(str).str.upper() == ticker].copy()
    if rows.empty:
        raise KeyError(f"ticker not present in HiThink normalized daily data: {ticker}")
    row = rows.iloc[-1]

    def clean(value: Any) -> Any:
        if pd.isna(value):
            return None
        if isinstance(value, (np.floating, float)):
            return round(float(value), 8)
        if isinstance(value, (np.integer, int)):
            return int(value)
        return value

    latest_us = int(row["trade_date"])
    return {
        "source": "HiThink Financial-API normalized full-market daily-k",
        "trade_date": pd.to_datetime(latest_us, unit="us").strftime("%Y-%m-%d"),
        "close": clean(row["close"]),
        "return_1d": clean(row["return_1d"]),
        "return_5d": clean(row["return_5d"]),
        "return_20d": clean(row["return_20d"]),
        "ma20": clean(row["ma20"]),
        "ma60": clean(row["ma60"]),
        "distance_to_ma20": clean(row["close"] / row["ma20"] - 1.0) if pd.notna(row["ma20"]) and row["ma20"] else None,
        "atr20": clean(row["atr20"]),
        "atr20_pct": clean(row["atr20_pct"]),
        "distance_to_20d_high": clean(row["distance_to_20d_high"]),
        "amount": clean(row["amount"]),
        "amount_ratio20": clean(row["amount_ratio20"]),
    }


def build_live_bundle(
    *,
    normalized_daily_path: str | Path,
    signal_path: str | Path,
    manifest_path: str | Path,
    adjustment_path: str | Path,
    output_dir: str | Path,
) -> Dict[str, Any]:
    signal = json.loads(Path(signal_path).read_text(encoding="utf-8"))
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    adj_pf = pq.ParquetFile(adjustment_path)

    if not all(bool(manifest.get(k)) for k in ("full_market", "complete", "data_valid")):
        raise ValueError("HiThink manifest is not complete/full-market/data-valid")
    if signal.get("latest_trade_date") != manifest.get("latest_trade_date"):
        raise ValueError("Frozen V7 signal date does not match HiThink manifest date")

    recent = _compute_recent_features(_load_recent_daily(normalized_daily_path))
    metrics, market_assessment = derive_market_regime(recent)
    if metrics.trade_date != manifest.get("latest_trade_date"):
        raise ValueError("IROS derived market date does not match HiThink manifest date")

    output = Path(output_dir)
    objects_dir = output / "objects"
    objects_dir.mkdir(parents=True, exist_ok=True)

    research_rows: List[Dict[str, Any]] = []
    for candidate in signal.get("top2", []):
        ticker = str(candidate["symbol"]).strip().upper()
        technical = security_technical_snapshot(recent, ticker)
        research_id = f"HITHINK-{metrics.trade_date}-{ticker}"
        obj = ResearchObject(
            research_id=research_id,
            security=SecurityResearchCard(
                ticker=ticker,
                company_name="",
                thesis=Thesis(
                    stance=ThesisStance.UNDETERMINED,
                    base_case="Live data ingested; fundamental/event thesis not yet completed.",
                    confidence=None,
                ),
            ),
            metadata={
                "source_mode": "LIVE_HITHINK",
                "source_trade_date": metrics.trade_date,
                "frozen_v7_candidate": dict(candidate),
                "validation_status": ValidationStatus.UNVALIDATED_RESEARCH_HEURISTIC.value,
            },
        )
        pipeline = ResearchPipeline(obj)
        pipeline.apply_market_regime(market_assessment)
        pipeline.set_technical_structure(technical)
        pipeline.set_positioning(
            {
                "source": technical["source"],
                "trade_date": technical["trade_date"],
                "amount": technical["amount"],
                "amount_ratio20": technical["amount_ratio20"],
            }
        )
        pipeline.add_evidence(
            [
                EvidenceItem(
                    kind=EvidenceKind.FACT,
                    statement=f"HiThink full-market session {metrics.trade_date} passed A100 completeness checks.",
                    source="hithink_manifest.json",
                    observed_at=metrics.trade_date,
                    confidence=1.0,
                ),
                EvidenceItem(
                    kind=EvidenceKind.EVIDENCE,
                    statement=f"Frozen V7 selected {ticker} in its Top-2 research candidate output.",
                    source="A100 Frozen V7 latest_signal.json",
                    observed_at=metrics.trade_date,
                    confidence=1.0,
                ),
            ]
        )
        save_research_object(obj, objects_dir / f"{research_id}.json")
        research_rows.append(
            {
                "research_id": research_id,
                "ticker": ticker,
                "decision_state": obj.state.value,
                "v7_rank": candidate.get("rank"),
                "v7_rank_score": candidate.get("v7_rank_score"),
                "technical": technical,
            }
        )

    bundle = {
        "schema_version": "A100-IROS-HITHINK-LIVE-v1",
        "trade_date": metrics.trade_date,
        "data_source": manifest.get("source"),
        "manifest": {
            "latest_rows": manifest.get("latest_rows"),
            "symbols": manifest.get("symbols"),
            "completeness_ratio": manifest.get("completeness_ratio"),
            "full_market": manifest.get("full_market"),
            "data_valid": manifest.get("data_valid"),
        },
        "adjustment_event_rows": int(adj_pf.metadata.num_rows),
        "market_metrics": metrics.to_dict(),
        "market_regime": market_assessment.to_dict(),
        "frozen_v7": {
            "market_gate": signal.get("market_gate"),
            "candidate_count": signal.get("candidate_count"),
            "top2_count": len(signal.get("top2", [])),
        },
        "research_objects": research_rows,
        "governance": {
            "research_only": True,
            "modifies_frozen_v7": False,
            "research_heuristics_validated": False,
        },
    }
    (output / "live_bundle.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return bundle
