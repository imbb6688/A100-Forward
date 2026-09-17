from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class ValidationStatus(str, Enum):
    UNVALIDATED_RESEARCH_HEURISTIC = "UNVALIDATED_RESEARCH_HEURISTIC"
    BACKTESTED = "BACKTESTED"
    WALK_FORWARD_VALIDATED = "WALK_FORWARD_VALIDATED"
    SHADOW_VALIDATED = "SHADOW_VALIDATED"
    VALIDATED = "VALIDATED"


class MarketRiskMode(str, Enum):
    RISK_ON = "RISK_ON"
    NEUTRAL = "NEUTRAL"
    RISK_OFF = "RISK_OFF"


class TrendMode(str, Enum):
    UP = "UP"
    RANGE = "RANGE"
    DOWN = "DOWN"


class EventDirection(str, Enum):
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"
    MIXED = "MIXED"


@dataclass(frozen=True)
class MarketRegimeAssessment:
    risk_mode: MarketRiskMode
    trend_mode: TrendMode
    confidence: float
    rationale: List[str] = field(default_factory=list)
    suitable_strategy_tags: List[str] = field(default_factory=list)
    restricted_strategy_tags: List[str] = field(default_factory=list)
    validation_status: ValidationStatus = ValidationStatus.UNVALIDATED_RESEARCH_HEURISTIC

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    def to_dict(self) -> Dict[str, object]:
        return {
            "risk_mode": self.risk_mode.value,
            "trend_mode": self.trend_mode.value,
            "confidence": self.confidence,
            "rationale": list(self.rationale),
            "suitable_strategy_tags": list(self.suitable_strategy_tags),
            "restricted_strategy_tags": list(self.restricted_strategy_tags),
            "validation_status": self.validation_status.value,
        }


@dataclass(frozen=True)
class IndustryAssessment:
    industry: str
    cycle_score: Optional[float] = None
    demand_score: Optional[float] = None
    supply_score: Optional[float] = None
    pricing_score: Optional[float] = None
    policy_score: Optional[float] = None
    relative_strength_score: Optional[float] = None
    breadth_score: Optional[float] = None
    catalysts: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    validation_status: ValidationStatus = ValidationStatus.UNVALIDATED_RESEARCH_HEURISTIC

    def __post_init__(self) -> None:
        if not self.industry.strip():
            raise ValueError("industry must not be empty")
        for name in (
            "cycle_score",
            "demand_score",
            "supply_score",
            "pricing_score",
            "policy_score",
            "relative_strength_score",
            "breadth_score",
        ):
            value = getattr(self, name)
            if value is not None and not 0.0 <= value <= 100.0:
                raise ValueError(f"{name} must be between 0 and 100")

    def to_dict(self) -> Dict[str, object]:
        return {
            "industry": self.industry,
            "cycle_score": self.cycle_score,
            "demand_score": self.demand_score,
            "supply_score": self.supply_score,
            "pricing_score": self.pricing_score,
            "policy_score": self.policy_score,
            "relative_strength_score": self.relative_strength_score,
            "breadth_score": self.breadth_score,
            "catalysts": list(self.catalysts),
            "risks": list(self.risks),
            "validation_status": self.validation_status.value,
        }


@dataclass(frozen=True)
class EventAssessment:
    event_id: str
    title: str
    direction: EventDirection
    impact: float
    surprise: float
    persistence: float
    credibility: float
    priced_in: float
    source: str = ""
    observed_at: str = ""
    notes: str = ""
    validation_status: ValidationStatus = ValidationStatus.UNVALIDATED_RESEARCH_HEURISTIC

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id must not be empty")
        if not self.title.strip():
            raise ValueError("title must not be empty")
        for name in ("impact", "surprise", "persistence", "credibility", "priced_in"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")

    @property
    def incremental_information_score(self) -> float:
        # Research heuristic only. A high priced-in estimate reduces incremental information.
        return round(self.impact * self.surprise * self.persistence * self.credibility * (1.0 - self.priced_in), 6)

    def to_dict(self) -> Dict[str, object]:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "direction": self.direction.value,
            "impact": self.impact,
            "surprise": self.surprise,
            "persistence": self.persistence,
            "credibility": self.credibility,
            "priced_in": self.priced_in,
            "incremental_information_score": self.incremental_information_score,
            "source": self.source,
            "observed_at": self.observed_at,
            "notes": self.notes,
            "validation_status": self.validation_status.value,
        }


@dataclass(frozen=True)
class ResearchScore:
    components: Dict[str, float]
    weights: Dict[str, float]
    score: float
    validation_status: ValidationStatus = ValidationStatus.UNVALIDATED_RESEARCH_HEURISTIC

    def to_dict(self) -> Dict[str, object]:
        return {
            "components": dict(self.components),
            "weights": dict(self.weights),
            "score": self.score,
            "validation_status": self.validation_status.value,
        }


def weighted_research_score(
    components: Dict[str, float],
    weights: Optional[Dict[str, float]] = None,
    *,
    validation_status: ValidationStatus = ValidationStatus.UNVALIDATED_RESEARCH_HEURISTIC,
) -> ResearchScore:
    if not components:
        raise ValueError("components must not be empty")
    for name, value in components.items():
        if not 0.0 <= float(value) <= 100.0:
            raise ValueError(f"component {name!r} must be between 0 and 100")

    if weights is None:
        equal = 1.0 / len(components)
        weights = {name: equal for name in components}
    else:
        missing = set(components) - set(weights)
        extra = set(weights) - set(components)
        if missing or extra:
            raise ValueError(f"weights keys must match components; missing={sorted(missing)}, extra={sorted(extra)}")
        if any(float(value) < 0.0 for value in weights.values()):
            raise ValueError("weights must be non-negative")
        total = sum(float(value) for value in weights.values())
        if total <= 0.0:
            raise ValueError("weights must sum to a positive value")
        weights = {name: float(value) / total for name, value in weights.items()}

    score = sum(float(components[name]) * float(weights[name]) for name in components)
    return ResearchScore(
        components={name: float(value) for name, value in components.items()},
        weights={name: float(value) for name, value in weights.items()},
        score=round(score, 6),
        validation_status=validation_status,
    )
