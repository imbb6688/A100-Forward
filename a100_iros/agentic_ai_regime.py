from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional

DEFAULT_WEIGHTS = {
    "token_demand": 0.15,
    "domestic_compute": 0.20,
    "optical_interconnect": 0.15,
    "semiconductor_equipment_materials": 0.20,
    "robotics": 0.10,
    "star100_relative_strength": 0.20,
}

class AgenticAIRegimeState(str, Enum):
    EXPANDING = "EXPANDING"
    BUILDING = "BUILDING"
    NEUTRAL = "NEUTRAL"
    COOLING = "COOLING"
    DETERIORATING = "DETERIORATING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

@dataclass(frozen=True)
class RegimeSignal:
    bucket: str
    score: float
    confidence: float = 1.0
    source: str = ""
    observed_at: Optional[str] = None
    note: str = ""

    def __post_init__(self) -> None:
        if not -1.0 <= self.score <= 1.0:
            raise ValueError("score must be between -1 and 1")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

@dataclass(frozen=True)
class BucketScore:
    bucket: str
    score: float
    confidence: float
    signal_count: int
    weight: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class AgenticAIRegimeSnapshot:
    as_of: str
    state: AgenticAIRegimeState
    score_0_100: float
    coverage: float
    confidence: float
    buckets: List[BucketScore]
    missing_buckets: List[str]
    governance: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def relative_strength_signal(
    *,
    star100_return: float,
    star50_return: float,
    csi300_return: float,
    horizon: str,
    confidence: float = 1.0,
) -> RegimeSignal:
    spread = 0.6 * (star100_return - star50_return) + 0.4 * (star100_return - csi300_return)
    score = max(-1.0, min(1.0, spread / 0.10))
    return RegimeSignal(
        bucket="star100_relative_strength",
        score=score,
        confidence=confidence,
        source=f"market_returns:{horizon}",
        note=f"STAR100-STAR50/CSI300 blended relative strength={spread:.4f}",
    )

def _aggregate_bucket(bucket: str, signals: Iterable[RegimeSignal], weight: float) -> Optional[BucketScore]:
    rows = [s for s in signals if s.bucket == bucket]
    if not rows:
        return None
    conf_sum = sum(s.confidence for s in rows)
    if conf_sum <= 0:
        score = sum(s.score for s in rows) / len(rows)
        conf = 0.0
    else:
        score = sum(s.score * s.confidence for s in rows) / conf_sum
        conf = conf_sum / len(rows)
    return BucketScore(bucket, round(score, 6), round(conf, 6), len(rows), weight)

def build_agentic_ai_regime(
    signals: Iterable[RegimeSignal],
    *,
    weights: Optional[Mapping[str, float]] = None,
    as_of: Optional[str] = None,
    min_coverage: float = 0.67,
) -> AgenticAIRegimeSnapshot:
    weights = dict(weights or DEFAULT_WEIGHTS)
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("weights must sum to > 0")
    weights = {k: v / total_weight for k, v in weights.items()}
    rows = list(signals)
    buckets: List[BucketScore] = []
    missing: List[str] = []
    for bucket, weight in weights.items():
        b = _aggregate_bucket(bucket, rows, weight)
        if b is None:
            missing.append(bucket)
        else:
            buckets.append(b)

    observed_weight = sum(b.weight for b in buckets)
    coverage = observed_weight
    if observed_weight > 0:
        raw = sum(b.score * b.weight for b in buckets) / observed_weight
        conf = sum(b.confidence * b.weight for b in buckets) / observed_weight
    else:
        raw, conf = 0.0, 0.0
    score = 50.0 + 50.0 * raw

    if coverage < min_coverage:
        state = AgenticAIRegimeState.INSUFFICIENT_DATA
    elif score >= 70:
        state = AgenticAIRegimeState.EXPANDING
    elif score >= 58:
        state = AgenticAIRegimeState.BUILDING
    elif score >= 42:
        state = AgenticAIRegimeState.NEUTRAL
    elif score >= 30:
        state = AgenticAIRegimeState.COOLING
    else:
        state = AgenticAIRegimeState.DETERIORATING

    return AgenticAIRegimeSnapshot(
        as_of=as_of or _utc_now(),
        state=state,
        score_0_100=round(score, 3),
        coverage=round(coverage, 3),
        confidence=round(conf * coverage, 3),
        buckets=buckets,
        missing_buckets=missing,
        governance={
            "research_only": True,
            "modifies_frozen_v7": False,
            "validated_trading_rule": False,
            "min_coverage": min_coverage,
            "score_interpretation": "0-100 regime strength; not a buy/sell signal",
        },
    )
