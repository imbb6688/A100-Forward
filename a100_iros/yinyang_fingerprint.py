from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd


class MarketState(str, Enum):
    RISK_OFF = "RISK_OFF"
    DEFENSIVE = "DEFENSIVE"
    TRANSITION = "TRANSITION"
    RECOVERY = "RECOVERY"
    RISK_ON = "RISK_ON"


@dataclass(frozen=True)
class FingerprintSnapshot:
    trade_date: str
    score_0_100: float
    yin_pct: float
    yang_pct: float
    state: str
    silver_finger: bool
    gold_finger: bool
    breadth_score: float
    trend_score: float
    momentum_score: float
    liquidity_score: float
    volatility_score: float
    leadership_score: float
    capital_score: float
    advancers: int
    decliners: int
    unchanged: int
    new_high_20: int
    new_low_20: int
    limit_up_like: int
    limit_down_like: int
    coverage: float
    status: str = "LEGACY_V1_REGIME_ONLY_FINGER_SEMANTICS_DEPRECATED"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


WEIGHTS = {
    "breadth": 0.25,
    "trend": 0.20,
    "momentum": 0.15,
    "liquidity": 0.15,
    "volatility": 0.10,
    "leadership": 0.10,
    "capital": 0.05,
}


def _clip01(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))


def _state(score: float) -> MarketState:
    if score < 25:
        return MarketState.RISK_OFF
    if score < 40:
        return MarketState.DEFENSIVE
    if score < 55:
        return MarketState.TRANSITION
    if score < 70:
        return MarketState.RECOVERY
    return MarketState.RISK_ON


def _normalize_daily(df: pd.DataFrame) -> pd.DataFrame:
    required = {"ts_code", "trade_date", "open", "high", "low", "close", "volume", "amount", "pre_close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    out = df.copy()
    out["date"] = pd.to_datetime(out["trade_date"], unit="us").dt.normalize()
    out = out.sort_values(["ts_code", "date"], kind="mergesort")
    g = out.groupby("ts_code", sort=False)
    out["ret1"] = out["close"] / out["pre_close"] - 1.0
    out["ma20"] = g["close"].transform(lambda s: s.rolling(20, min_periods=20).mean())
    out["ma60"] = g["close"].transform(lambda s: s.rolling(60, min_periods=60).mean())
    out["high20_prev"] = g["high"].transform(lambda s: s.shift(1).rolling(20, min_periods=20).max())
    out["low20_prev"] = g["low"].transform(lambda s: s.shift(1).rolling(20, min_periods=20).min())
    out["amt20"] = g["amount"].transform(lambda s: s.rolling(20, min_periods=5).mean())
    out["rv20"] = g["ret1"].transform(lambda s: s.rolling(20, min_periods=10).std())
    return out


def build_history(df: pd.DataFrame) -> pd.DataFrame:
    x = _normalize_daily(df)
    rows: list[dict[str, Any]] = []
    for dt, d in x.groupby("date", sort=True):
        valid = d[np.isfinite(d["ret1"]) & np.isfinite(d["close"]) & (d["close"] > 0)]
        n = len(valid)
        if n == 0:
            continue
        adv = int((valid["ret1"] > 0.001).sum())
        dec = int((valid["ret1"] < -0.001).sum())
        flat = int(n - adv - dec)
        breadth_ratio = (adv - dec) / max(adv + dec, 1)
        above20 = float((valid["close"] > valid["ma20"]).mean())
        above60 = float((valid["close"] > valid["ma60"]).mean())
        median_ret = float(valid["ret1"].median())
        mean_ret = float(valid["ret1"].mean())
        high20 = int((valid["close"] >= valid["high20_prev"]).fillna(False).sum())
        low20 = int((valid["close"] <= valid["low20_prev"]).fillna(False).sum())
        amount_ratio = float((valid["amount"] / valid["amt20"]).replace([np.inf, -np.inf], np.nan).median())
        median_rv = float(valid["rv20"].median())
        up_like = int((valid["ret1"] >= 0.095).sum())
        dn_like = int((valid["ret1"] <= -0.095).sum())

        breadth = _clip01(0.5 + 0.5 * breadth_ratio)
        trend = _clip01(0.5 * above20 + 0.5 * above60)
        momentum = _clip01(0.5 + 4.0 * median_ret)
        liquidity = _clip01(0.5 + 0.5 * (amount_ratio - 1.0) if np.isfinite(amount_ratio) else 0.5)
        volatility = _clip01(1.0 - (median_rv / 0.05 if np.isfinite(median_rv) else 0.5))
        leadership = _clip01(0.5 + (high20 - low20) / max(n * 0.10, 1))
        capital = _clip01(0.5 + 3.0 * mean_ret)

        score = 100.0 * (
            WEIGHTS["breadth"] * breadth
            + WEIGHTS["trend"] * trend
            + WEIGHTS["momentum"] * momentum
            + WEIGHTS["liquidity"] * liquidity
            + WEIGHTS["volatility"] * volatility
            + WEIGHTS["leadership"] * leadership
            + WEIGHTS["capital"] * capital
        )
        rows.append({
            "date": dt,
            "score_0_100": score,
            "breadth_score": breadth * 100,
            "trend_score": trend * 100,
            "momentum_score": momentum * 100,
            "liquidity_score": liquidity * 100,
            "volatility_score": volatility * 100,
            "leadership_score": leadership * 100,
            "capital_score": capital * 100,
            "ew_return_1d": mean_ret,
            "advancers": adv,
            "decliners": dec,
            "unchanged": flat,
            "new_high_20": high20,
            "new_low_20": low20,
            "limit_up_like": up_like,
            "limit_down_like": dn_like,
            "coverage": n,
        })
    hist = pd.DataFrame(rows)
    if hist.empty:
        return hist
    hist["ew_index"] = (1.0 + hist["ew_return_1d"].clip(-0.15, 0.15).fillna(0.0)).cumprod() * 1000.0
    hist["score_ma3"] = hist["score_0_100"].rolling(3, min_periods=1).mean()
    hist["breadth_ma3"] = hist["breadth_score"].rolling(3, min_periods=1).mean()
    hist["score_delta3"] = hist["score_0_100"].diff(3)
    hist["state"] = hist["score_0_100"].map(lambda s: _state(float(s)).value)
    prev = hist["score_0_100"].shift(1)
    hist["silver_finger"] = (
        (prev < 40)
        & (hist["score_0_100"] >= 45)
        & (hist["score_delta3"] > 5)
        & (hist["breadth_ma3"] >= 50)
    )
    hist["gold_finger"] = (
        (hist["score_0_100"] >= 60)
        & (hist["score_ma3"] >= 55)
        & (hist["trend_score"] >= 55)
        & (hist["breadth_score"] >= 55)
        & (hist["leadership_score"] >= 50)
        & (hist["liquidity_score"] >= 45)
    )
    return hist


def snapshot_from_history(hist: pd.DataFrame) -> FingerprintSnapshot:
    if hist.empty:
        raise ValueError("no valid market observations")
    r = hist.iloc[-1]
    score = float(r["score_0_100"])
    yang = float(np.clip(score, 0, 100))
    return FingerprintSnapshot(
        trade_date=pd.Timestamp(r["date"]).date().isoformat(),
        score_0_100=round(score, 2),
        yin_pct=round(100.0 - yang, 2),
        yang_pct=round(yang, 2),
        state=str(r["state"]),
        silver_finger=bool(r["silver_finger"]),
        gold_finger=bool(r["gold_finger"]),
        breadth_score=round(float(r["breadth_score"]), 2),
        trend_score=round(float(r["trend_score"]), 2),
        momentum_score=round(float(r["momentum_score"]), 2),
        liquidity_score=round(float(r["liquidity_score"]), 2),
        volatility_score=round(float(r["volatility_score"]), 2),
        leadership_score=round(float(r["leadership_score"]), 2),
        capital_score=round(float(r["capital_score"]), 2),
        advancers=int(r["advancers"]),
        decliners=int(r["decliners"]),
        unchanged=int(r["unchanged"]),
        new_high_20=int(r["new_high_20"]),
        new_low_20=int(r["new_low_20"]),
        limit_up_like=int(r["limit_up_like"]),
        limit_down_like=int(r["limit_down_like"]),
        coverage=float(r["coverage"]),
    )


def latest_snapshot(df: pd.DataFrame) -> FingerprintSnapshot:
    return snapshot_from_history(build_history(df))
