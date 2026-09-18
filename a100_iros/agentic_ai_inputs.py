from __future__ import annotations

import json
from datetime import date, datetime
from math import tanh
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .agentic_ai_regime import RegimeSignal, relative_strength_signal, validate_weights
from .hithink_live import _compute_recent_features, _load_recent_daily


HORIZONS = (5, 20, 60)
HORIZON_WEIGHTS = {5: 0.25, 20: 0.45, 60: 0.30}
HORIZON_SCALES = {5: 0.04, 20: 0.10, 60: 0.20}


def load_regime_config(path: str | Path) -> Dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_weights(payload.get("weights", {}))
    themes = payload.get("market_proxy_baskets")
    if not isinstance(themes, dict):
        raise ValueError("market_proxy_baskets must be an object")
    for bucket in (
        "domestic_compute",
        "optical_interconnect",
        "semiconductor_equipment_materials",
        "robotics",
    ):
        rows = themes.get(bucket)
        if not isinstance(rows, list) or len(rows) < 3:
            raise ValueError(f"{bucket} requires at least three market proxy members")
        for row in rows:
            if not isinstance(row, dict) or not row.get("ticker") or not row.get("name"):
                raise ValueError(f"{bucket} proxy entries require ticker and name")
    return payload


def _trade_date(value: int) -> str:
    return pd.to_datetime(int(value), unit="us").strftime("%Y-%m-%d")


def _metric_for_symbol(frame: pd.DataFrame, symbol: str, latest_us: int) -> Dict[str, Any] | None:
    rows = frame[frame["ts_code"].astype(str).str.upper() == symbol.upper()].copy()
    if rows.empty or int(rows.iloc[-1]["trade_date"]) != latest_us:
        return None
    row = rows.iloc[-1]
    returns = {
        horizon: (
            None
            if pd.isna(row.get(f"return_{horizon}d"))
            else float(row[f"return_{horizon}d"])
        )
        for horizon in HORIZONS
    }
    above_ma20 = None
    if pd.notna(row.get("ma20")) and float(row["ma20"]) != 0:
        above_ma20 = bool(float(row["close"]) > float(row["ma20"]))
    return {
        "ticker": symbol.upper(),
        "returns": returns,
        "above_ma20": above_ma20,
        "amount_ratio20": (
            None if pd.isna(row.get("amount_ratio20")) else float(row["amount_ratio20"])
        ),
    }


def _basket_metrics(
    frame: pd.DataFrame,
    symbols: Sequence[str],
    latest_us: int,
) -> Dict[str, Any]:
    rows = [metric for symbol in symbols if (metric := _metric_for_symbol(frame, symbol, latest_us))]
    returns: Dict[int, float | None] = {}
    horizon_coverage: Dict[int, float] = {}
    for horizon in HORIZONS:
        values = [row["returns"][horizon] for row in rows if row["returns"][horizon] is not None]
        returns[horizon] = float(np.mean(values)) if values else None
        horizon_coverage[horizon] = len(values) / len(symbols) if symbols else 0.0
    breadth_values = [row["above_ma20"] for row in rows if row["above_ma20"] is not None]
    breadth = float(np.mean(breadth_values)) if breadth_values else None
    return {
        "returns": returns,
        "horizon_coverage": horizon_coverage,
        "breadth_above_ma20": breadth,
        "available_members": [row["ticker"] for row in rows],
        "requested_members": list(symbols),
        "member_coverage": len(rows) / len(symbols) if symbols else 0.0,
    }


def _resolve_index_metrics(
    frame: pd.DataFrame,
    latest_us: int,
    definition: Mapping[str, Any],
    constituents: Mapping[str, Sequence[str]],
) -> Dict[str, Any]:
    for ticker in definition.get("direct_tickers", []):
        metric = _metric_for_symbol(frame, str(ticker), latest_us)
        if metric and all(metric["returns"][horizon] is not None for horizon in HORIZONS):
            return {
                "returns": metric["returns"],
                "confidence": 1.0,
                "method": "direct_index_or_etf_series",
                "ticker": str(ticker).upper(),
            }

    index_code = str(definition["constituent_index_code"]).upper()
    members = [str(value).upper() for value in constituents.get(index_code, [])]
    if len(members) < int(definition.get("minimum_constituents", 20)):
        raise ValueError(f"insufficient constituents for {index_code}: {len(members)}")
    basket = _basket_metrics(frame, members, latest_us)
    minimum_coverage = float(definition.get("minimum_market_coverage", 0.80))
    if basket["member_coverage"] < minimum_coverage:
        raise ValueError(
            f"market coverage for {index_code} is {basket['member_coverage']:.3f}, "
            f"below {minimum_coverage:.3f}"
        )
    if any(basket["returns"][horizon] is None for horizon in HORIZONS):
        raise ValueError(f"index proxy {index_code} lacks required return horizons")
    return {
        "returns": basket["returns"],
        "confidence": 0.70 * basket["member_coverage"],
        "method": "current_constituents_equal_weight",
        "ticker": index_code,
        "member_count": len(members),
        "market_member_coverage": basket["member_coverage"],
        "bias_warning": "Current-constituent equal-weight proxy; not point-in-time or cap-weighted.",
    }


def _theme_signal(
    *,
    bucket: str,
    basket: Mapping[str, Any],
    benchmark: Mapping[str, Any],
    as_of: str,
    minimum_coverage: float,
) -> RegimeSignal | None:
    if basket["member_coverage"] < minimum_coverage:
        return None
    components = []
    available_weight = 0.0
    for horizon in HORIZONS:
        theme_return = basket["returns"][horizon]
        benchmark_return = benchmark["returns"][horizon]
        if theme_return is None or benchmark_return is None:
            continue
        weight = HORIZON_WEIGHTS[horizon]
        excess = theme_return - benchmark_return
        components.append(weight * tanh(excess / HORIZON_SCALES[horizon]))
        available_weight += weight
    breadth = basket["breadth_above_ma20"]
    if breadth is not None:
        components.append(0.10 * (2.0 * breadth - 1.0))
        available_weight += 0.10
    if available_weight <= 0:
        return None
    score = max(-1.0, min(1.0, sum(components) / available_weight))
    confidence = min(
        1.0,
        basket["member_coverage"]
        * (sum(basket["horizon_coverage"].values()) / len(HORIZONS)),
    )
    return RegimeSignal(
        bucket=bucket,
        score=score,
        confidence=confidence,
        source="HiThink full-market daily-k; curated listed-equity proxy basket",
        observed_at=as_of,
        note=(
            f"market proxy; members={len(basket['available_members'])}/"
            f"{len(basket['requested_members'])}; breadth_ma20={breadth}"
        ),
        proxy_type="market_proxy_not_fundamental_demand",
    )


def build_market_proxy_payload(
    *,
    normalized_daily_path: str | Path,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    index_constituents: Mapping[str, Sequence[str]],
    today: date | None = None,
) -> Dict[str, Any]:
    validate_weights(config.get("weights", {}))
    if not all(bool(manifest.get(key)) for key in ("full_market", "complete", "data_valid")):
        raise ValueError("HiThink manifest is not complete/full-market/data-valid")

    recent = _compute_recent_features(_load_recent_daily(normalized_daily_path, sessions=90))
    recent["return_60d"] = recent.groupby("ts_code", sort=False)["close"].pct_change(60)
    latest_us = int(recent["trade_date"].max())
    as_of = _trade_date(latest_us)
    if as_of != str(manifest.get("latest_trade_date")):
        raise ValueError("regime market date does not match HiThink manifest date")

    local_today = today or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    age_days = (local_today - date.fromisoformat(as_of)).days
    max_age_days = int(config.get("quality_gates", {}).get("max_calendar_age_days", 4))
    if age_days < 0 or age_days > max_age_days:
        raise ValueError(f"market data is stale or future-dated: as_of={as_of}, age_days={age_days}")

    index_defs = config["relative_strength_indices"]
    resolved = {
        key: _resolve_index_metrics(recent, latest_us, index_defs[key], index_constituents)
        for key in ("star100", "star50", "csi300")
    }
    benchmark = resolved["csi300"]
    minimum_proxy_coverage = float(
        config.get("quality_gates", {}).get("minimum_proxy_member_coverage", 0.60)
    )

    signals: list[RegimeSignal] = []
    details: Dict[str, Any] = {}
    for bucket, members in config["market_proxy_baskets"].items():
        symbols = [str(row["ticker"]).upper() for row in members]
        basket = _basket_metrics(recent, symbols, latest_us)
        details[bucket] = basket
        signal = _theme_signal(
            bucket=bucket,
            basket=basket,
            benchmark=benchmark,
            as_of=as_of,
            minimum_coverage=minimum_proxy_coverage,
        )
        if signal:
            signals.append(signal)

    horizon_signals = []
    for horizon in HORIZONS:
        horizon_signals.append(
            relative_strength_signal(
                star100_return=float(resolved["star100"]["returns"][horizon]),
                star50_return=float(resolved["star50"]["returns"][horizon]),
                csi300_return=float(resolved["csi300"]["returns"][horizon]),
                horizon=f"{horizon}d",
                confidence=min(item["confidence"] for item in resolved.values()),
                observed_at=as_of,
                source="HiThink full-market daily-k; STAR100/STAR50/CSI300 relative strength",
                scale=HORIZON_SCALES[horizon],
            )
        )
    relative_score = sum(
        signal.score * HORIZON_WEIGHTS[horizon]
        for signal, horizon in zip(horizon_signals, HORIZONS)
    )
    relative_confidence = sum(
        signal.confidence * HORIZON_WEIGHTS[horizon]
        for signal, horizon in zip(horizon_signals, HORIZONS)
    )
    signals.append(
        RegimeSignal(
            bucket="star100_relative_strength",
            score=relative_score,
            confidence=relative_confidence,
            source="HiThink full-market daily-k; 5d/20d/60d blended relative strength",
            observed_at=as_of,
            note="; ".join(signal.note for signal in horizon_signals),
            proxy_type="index_relative_strength",
        )
    )

    missing = [bucket for bucket in config["weights"] if bucket not in {s.bucket for s in signals}]
    return {
        "schema_version": "A100-Agentic-AI-Regime-Input-v2",
        "as_of": as_of,
        "weights": config["weights"],
        "signals": [signal.__dict__ for signal in signals],
        "quality": {
            "manifest_schema": manifest.get("schema_version"),
            "manifest_latest_rows": manifest.get("latest_rows"),
            "market_date_age_days": age_days,
            "missing_buckets": missing,
            "theme_details": details,
            "index_details": resolved,
        },
        "provenance": {
            "source": manifest.get("source"),
            "manifest_latest_trade_date": manifest.get("latest_trade_date"),
            "formula_version": "market-proxy-relative-strength-v2",
            "disclosure": (
                "Industry buckets are market-implied listed-equity proxies, not direct measures "
                "of token usage, orders, revenue or fundamentals. token_demand is intentionally "
                "missing until a supported upstream source exists."
            ),
        },
    }


def index_codes_from_config(config: Mapping[str, Any]) -> Iterable[str]:
    for definition in config["relative_strength_indices"].values():
        yield str(definition["constituent_index_code"]).upper()
