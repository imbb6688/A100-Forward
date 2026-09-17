from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class DecisionState(str, Enum):
    DISCOVERED = "DISCOVERED"
    RESEARCHING = "RESEARCHING"
    WATCHLIST = "WATCHLIST"
    CANDIDATE = "CANDIDATE"
    VALIDATION = "VALIDATION"
    TRADE_READY = "TRADE_READY"
    ACTIVE_POSITION = "ACTIVE_POSITION"
    REDUCE = "REDUCE"
    EXIT = "EXIT"
    POST_REVIEW = "POST_REVIEW"
    ARCHIVED = "ARCHIVED"
    REJECTED = "REJECTED"
    INVALIDATED = "INVALIDATED"


_ALLOWED_TRANSITIONS = {
    DecisionState.DISCOVERED: {DecisionState.RESEARCHING, DecisionState.REJECTED},
    DecisionState.RESEARCHING: {DecisionState.WATCHLIST, DecisionState.CANDIDATE, DecisionState.REJECTED},
    DecisionState.WATCHLIST: {DecisionState.RESEARCHING, DecisionState.CANDIDATE, DecisionState.REJECTED},
    DecisionState.CANDIDATE: {DecisionState.VALIDATION, DecisionState.WATCHLIST, DecisionState.INVALIDATED},
    DecisionState.VALIDATION: {DecisionState.TRADE_READY, DecisionState.WATCHLIST, DecisionState.INVALIDATED},
    DecisionState.TRADE_READY: {DecisionState.ACTIVE_POSITION, DecisionState.WATCHLIST, DecisionState.INVALIDATED},
    DecisionState.ACTIVE_POSITION: {DecisionState.REDUCE, DecisionState.EXIT, DecisionState.INVALIDATED},
    DecisionState.REDUCE: {DecisionState.ACTIVE_POSITION, DecisionState.EXIT},
    DecisionState.EXIT: {DecisionState.POST_REVIEW},
    DecisionState.POST_REVIEW: {DecisionState.ARCHIVED, DecisionState.WATCHLIST},
    DecisionState.REJECTED: {DecisionState.RESEARCHING, DecisionState.ARCHIVED},
    DecisionState.INVALIDATED: {DecisionState.POST_REVIEW, DecisionState.ARCHIVED},
    DecisionState.ARCHIVED: set(),
}


class EvidenceKind(str, Enum):
    FACT = "FACT"
    EVIDENCE = "EVIDENCE"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"
    CANDIDATE_RULE = "CANDIDATE_RULE"
    VALIDATED_RULE = "VALIDATED_RULE"


class ThesisStance(str, Enum):
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"
    UNDETERMINED = "UNDETERMINED"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class EvidenceItem:
    kind: EvidenceKind
    statement: str
    source: Optional[str] = None
    observed_at: Optional[str] = None
    confidence: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("evidence statement must not be empty")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass
class Thesis:
    stance: ThesisStance = ThesisStance.UNDETERMINED
    bull_case: str = ""
    base_case: str = ""
    bear_case: str = ""
    must_be_true: List[str] = field(default_factory=list)
    invalidation_conditions: List[str] = field(default_factory=list)
    priced_in_assessment: str = ""
    variant_perception: str = ""
    confidence: Optional[float] = None
    updated_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("thesis confidence must be between 0 and 1")


@dataclass
class SecurityResearchCard:
    ticker: str
    company_name: str = ""
    market_context: Dict[str, Any] = field(default_factory=dict)
    industry_context: Dict[str, Any] = field(default_factory=dict)
    fundamentals: Dict[str, Any] = field(default_factory=dict)
    valuation: Dict[str, Any] = field(default_factory=dict)
    catalysts: List[Dict[str, Any]] = field(default_factory=list)
    event_risks: List[Dict[str, Any]] = field(default_factory=list)
    technical_structure: Dict[str, Any] = field(default_factory=dict)
    positioning: Dict[str, Any] = field(default_factory=dict)
    risks: List[str] = field(default_factory=list)
    evidence: List[EvidenceItem] = field(default_factory=list)
    thesis: Thesis = field(default_factory=Thesis)

    def __post_init__(self) -> None:
        self.ticker = self.ticker.strip().upper()
        if not self.ticker:
            raise ValueError("ticker must not be empty")


@dataclass
class ResearchObject:
    research_id: str
    security: SecurityResearchCard
    state: DecisionState = DecisionState.DISCOVERED
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    state_history: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.research_id.strip():
            raise ValueError("research_id must not be empty")
        if not self.state_history:
            self.state_history.append({"state": self.state.value, "at": self.created_at})

    def transition(self, new_state: DecisionState) -> None:
        if new_state == self.state:
            return
        allowed = _ALLOWED_TRANSITIONS[self.state]
        if new_state not in allowed:
            raise ValueError(f"invalid transition: {self.state.value} -> {new_state.value}")
        self.state = new_state
        self.updated_at = _utc_now()
        self.state_history.append({"state": new_state.value, "at": self.updated_at})

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        data["security"]["thesis"]["stance"] = self.security.thesis.stance.value
        for item in data["security"]["evidence"]:
            item["kind"] = item["kind"].value if isinstance(item["kind"], EvidenceKind) else item["kind"]
        return data
