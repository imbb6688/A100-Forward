from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from typing import Any, Dict, Iterable, List, Mapping, Optional


CANONICAL_BUCKETS = (
    "token_demand",
    "domestic_compute",
    "optical_interconnect",
    "semiconductor_equipment_materials",
    "robotics",
    "star100_relative_strength",
)

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
    proxy_type: str = "market_proxy"

    def __post_init__(self) -> None:
        if self.bucket not in CANONICAL_BUCKETS:
            raise ValueError(f"unknown regime bucket: {self.bucket}")
        if not isfinite(self.score) or not -1.0 <= self.score <= 1.0:
            raise ValueError("score must be finite and between -1 and 1")
        if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be finite and between 0 and 1")


@dataclass(frozen=True)
class BucketScore:
    bucket: str
    score: float
    confidence: float
    signal_count: int
    weight: float
    sources: List[str] = field(default_factory=list)
    observed_at: List[str] = field(default_factory=list)
    proxy_types: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgenticAIRegimeSnapshot:
    as_of: str
    state: AgenticAIRegimeState
    score_0_100: float
    coverage: float
    effective_coverage: float
    confidence: float
    buckets: List[BucketScore]
    missing_buckets: List[str]
    input_fingerprint: str = ""
    data_quality: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    governance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_weights(weights: Mapping[str, float]) -> Dict[str, float]:
    supplied = set(weights)
    expected = set(CANONICAL_BUCKETS)
    if supplied != expected:
        raise ValueError(
            f"weights must contain exactly the canonical buckets; "
            f"missing={sorted(expected - supplied)}, unknown={sorted(supplied - expected)}"
        )
    cleaned = {key: float(weights[key]) for key in CANONICAL_BUCKETS}
    if any(not isfinite(value) or value < 0 for value in cleaned.values()):
        raise ValueError("weights must be finite and non-negative")
    total = sum(cleaned.values())
    if total <= 0:
        raise ValueError("weights must sum to > 0")
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"weights must sum to 1.0, got {total:.8f}")
    return cleaned


def relative_strength_signal(
    *,
    star100_return: float,
    star50_return: float,
    csi300_return: float,
    horizon: str,
    confidence: float = 1.0,
    observed_at: Optional[str] = None,
    source: str = "",
    scale: float = 0.10,
) -> RegimeSignal:
    if scale <= 0:
        raise ValueError("scale must be positive")
    spread = 0.6 * (star100_return - star50_return) + 0.4 * (
        star100_return - csi300_return
    )
    score = max(-1.0, min(1.0, spread / scale))
    return RegimeSignal(
        bucket="star100_relative_strength",
        score=score,
        confidence=confidence,
        source=source or f"market_returns:{horizon}",
        observed_at=observed_at,
        note=f"STAR100-STAR50/CSI300 blended relative strength={spread:.4f}",
        proxy_type="index_relative_strength",
    )


def _aggregate_bucket(
    bucket: str, signals: Iterable[RegimeSignal], weight: float
) -> Optional[BucketScore]:
    rows = [signal for signal in signals if signal.bucket == bucket]
    if not rows:
        return None
    confidence_sum = sum(signal.confidence for signal in rows)
    if confidence_sum <= 0:
        score = sum(signal.score for signal in rows) / len(rows)
        confidence = 0.0
    else:
        score = sum(signal.score * signal.confidence for signal in rows) / confidence_sum
        confidence = confidence_sum / len(rows)
    return BucketScore(
        bucket=bucket,
        score=round(score, 6),
        confidence=round(confidence, 6),
        signal_count=len(rows),
        weight=weight,
        sources=sorted({signal.source for signal in rows if signal.source}),
        observed_at=sorted({signal.observed_at for signal in rows if signal.observed_at}),
        proxy_types=sorted({signal.proxy_type for signal in rows if signal.proxy_type}),
    )


def build_agentic_ai_regime(
    signals: Iterable[RegimeSignal],
    *,
    weights: Optional[Mapping[str, float]] = None,
    as_of: Optional[str] = None,
    min_coverage: float = 0.67,
    min_effective_coverage: float = 0.50,
    input_fingerprint: str = "",
    data_quality: Optional[Mapping[str, Any]] = None,
    provenance: Optional[Mapping[str, Any]] = None,
) -> AgenticAIRegimeSnapshot:
    if not 0.0 <= min_coverage <= 1.0:
        raise ValueError("min_coverage must be between 0 and 1")
    if not 0.0 <= min_effective_coverage <= 1.0:
        raise ValueError("min_effective_coverage must be between 0 and 1")
    validated_weights = validate_weights(weights or DEFAULT_WEIGHTS)
    rows = list(signals)

    buckets: List[BucketScore] = []
    missing: List[str] = []
    for bucket in CANONICAL_BUCKETS:
        result = _aggregate_bucket(bucket, rows, validated_weights[bucket])
        if result is None:
            missing.append(bucket)
        else:
            buckets.append(result)

    coverage = sum(bucket.weight for bucket in buckets)
    effective_coverage = sum(bucket.weight * bucket.confidence for bucket in buckets)
    if coverage > 0:
        raw = sum(bucket.score * bucket.weight for bucket in buckets) / coverage
    else:
        raw = 0.0
    score = 50.0 + 50.0 * raw

    if coverage < min_coverage or effective_coverage < min_effective_coverage:
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
        effective_coverage=round(effective_coverage, 3),
        confidence=round(effective_coverage, 3),
        buckets=buckets,
        missing_buckets=missing,
        input_fingerprint=input_fingerprint,
        data_quality=dict(data_quality or {}),
        provenance=dict(provenance or {}),
        governance={
            "research_only": True,
            "modifies_frozen_v7": False,
            "generates_orders": False,
            "validated_trading_rule": False,
            "min_coverage": min_coverage,
            "min_effective_coverage": min_effective_coverage,
            "score_interpretation": "0-100 market-implied regime strength; not a buy/sell signal",
            "promotion_requires": "Backtest -> Walk Forward -> Shadow/Paper -> Acceptance",
        },
    )
