from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class V2Snapshot:
    trade_date: str
    yang_pct: float
    yin_pct: float
    position_tenths: int
    signal: str
    state: str
    status: str = "RESEARCH_ONLY_V2_CANDIDATE"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clip100(x: pd.Series | np.ndarray) -> pd.Series:
    return pd.Series(np.clip(np.asarray(x, dtype=float), 0.0, 100.0))


def build_v2(history: pd.DataFrame) -> pd.DataFrame:
    h = history.copy()
    h["date"] = pd.to_datetime(h["date"])
    h = h.sort_values("date", kind="mergesort").reset_index(drop=True)

    required = {
        "score_0_100", "breadth_score", "trend_score", "momentum_score",
        "liquidity_score", "leadership_score", "ew_return_1d"
    }
    missing = required - set(h.columns)
    if missing:
        raise ValueError(f"history missing required v2 columns: {sorted(missing)}")

    # Head A: Yang Spectrum.
    # v1 composite score is deliberately NOT reused as Yang.
    # Candidate v2 formula is a parsimonious calibration proxy using structural
    # trend participation plus leadership diffusion. Coefficients are frozen
    # research candidates derived from the first vendor-labeled falsification set.
    raw_yang = -1.7908517 + 0.3997391 * h["trend_score"] + 0.4568233 * h["leadership_score"]
    h["v2_yang_pct"] = np.clip(raw_yang, 0.0, 100.0)
    h["v2_yin_pct"] = 100.0 - h["v2_yang_pct"]

    h["score_d1"] = h["score_0_100"].diff()
    h["score_d2"] = h["score_0_100"].diff(2)
    h["score_d3"] = h["score_0_100"].diff(3)
    h["breadth_d1"] = h["breadth_score"].diff()
    h["trend_d1"] = h["trend_score"].diff()
    h["recent_score_max3"] = h["score_0_100"].shift(1).rolling(3, min_periods=1).max()
    h["recent_score_min3"] = h["score_0_100"].shift(1).rolling(3, min_periods=1).min()
    h["prev_weak"] = h["score_0_100"].shift(1) < 50

    # Head C: transition-event state machine.
    # SILVER = deterioration after a recently strong regime; deliberately not recovery.
    silver_raw = (
        (h["score_0_100"] <= 46)
        & (h["breadth_score"] <= 35)
        & (h["score_0_100"].shift(1) < 50)
        & (h["recent_score_max3"] >= 58)
    )
    # A Finger is an event, not a persistent state. Suppress consecutive
    # duplicate SILVER prints after the first deterioration transition.
    silver = silver_raw & ~silver_raw.shift(1, fill_value=False)

    # BOUNCE = sharp rebound from an extreme weak state without sufficient
    # trend confirmation to qualify as GOLD.
    bounce = (
        (h["score_0_100"].shift(1) <= 32)
        & (h["score_d1"] >= 18)
        & (h["breadth_score"] >= 55)
        & (h["trend_score"] < 45)
    )

    # GOLD = renewed broad strength following a material recent repair,
    # not simple persistence at a high score. This prevents 2026-09-01-style
    # continuation false positives.
    repair = (h["score_d1"] >= 10) | (h["score_d3"] >= 10)
    gold = (
        (h["score_0_100"] >= 58)
        & (h["breadth_score"] >= 60)
        & (h["leadership_score"] >= 80)
        & repair
        & ~bounce
    )

    h["v2_signal"] = np.select(
        [gold, silver, bounce],
        ["GOLD", "SILVER", "BOUNCE"],
        default="NONE",
    )

    h["v2_state"] = np.select(
        [
            h["v2_yang_pct"] < 20,
            h["v2_yang_pct"] < 40,
            h["v2_yang_pct"] < 55,
            h["v2_yang_pct"] < 70,
        ],
        ["RISK_OFF", "DEFENSIVE", "TRANSITION", "RECOVERY"],
        default="RISK_ON",
    )

    # Head B: position is an ordinal research state with hysteresis.
    # Finger events have precedence; otherwise exposure follows Yang with
    # conservative inertia rather than a direct Yang-to-position mapping.
    pos = np.zeros(len(h), dtype=int)
    current = 3
    for i, row in h.iterrows():
        sig = row["v2_signal"]
        yang = float(row["v2_yang_pct"])
        if sig == "SILVER":
            current = 2
        elif sig == "BOUNCE":
            current = 3
        elif sig == "GOLD":
            current = int(np.clip(round(yang / 10), 5, 8))
        else:
            target = int(np.clip(round(yang / 10), 2, 8))
            if target > current:
                current += min(1, target - current)
            elif target < current:
                current -= min(1, current - target)
        pos[i] = current
    h["v2_position_tenths"] = pos
    return h


def latest_v2_snapshot(history: pd.DataFrame) -> V2Snapshot:
    v2 = build_v2(history)
    if v2.empty:
        raise ValueError("empty history")
    r = v2.iloc[-1]
    return V2Snapshot(
        trade_date=pd.Timestamp(r["date"]).date().isoformat(),
        yang_pct=round(float(r["v2_yang_pct"]), 2),
        yin_pct=round(float(r["v2_yin_pct"]), 2),
        position_tenths=int(r["v2_position_tenths"]),
        signal=str(r["v2_signal"]),
        state=str(r["v2_state"]),
    )
