"""A100 Investment Research Operating System (IROS).

Research-only layer. This package must not mutate the Frozen V7 trading logic.
"""

from .assessments import (
    EventAssessment,
    EventDirection,
    IndustryAssessment,
    MarketRegimeAssessment,
    MarketRiskMode,
    ResearchScore,
    TrendMode,
    ValidationStatus,
    weighted_research_score,
)
from .evidence import EvidenceLedger, EvidenceLedgerEntry, EvidenceStatus, evidence_fingerprint
from .gates import GateResult, evaluate_trade_readiness, promote_to_trade_ready
from .memory import ResearchSnapshot, ThesisDelta, compare_snapshots
from .models import (
    DecisionState,
    EvidenceItem,
    EvidenceKind,
    ResearchObject,
    SecurityResearchCard,
    Thesis,
    ThesisStance,
)
from .pipeline import PremortemFailure, ResearchPipeline
from .repository import ResearchRepository
from .risk import (
    Holding,
    PortfolioRiskSummary,
    RiskBudgetPosition,
    size_position_by_risk_budget,
    summarize_portfolio,
)
from .storage import SCHEMA_VERSION, load_research_object, save_research_object

__all__ = [
    "DecisionState",
    "EvidenceItem",
    "EvidenceKind",
    "ResearchObject",
    "SecurityResearchCard",
    "Thesis",
    "ThesisStance",
    "SCHEMA_VERSION",
    "load_research_object",
    "save_research_object",
    "ValidationStatus",
    "MarketRiskMode",
    "TrendMode",
    "EventDirection",
    "MarketRegimeAssessment",
    "IndustryAssessment",
    "EventAssessment",
    "ResearchScore",
    "weighted_research_score",
    "ResearchSnapshot",
    "ThesisDelta",
    "compare_snapshots",
    "ResearchRepository",
    "EvidenceLedger",
    "EvidenceLedgerEntry",
    "EvidenceStatus",
    "evidence_fingerprint",
    "ResearchPipeline",
    "PremortemFailure",
    "GateResult",
    "evaluate_trade_readiness",
    "promote_to_trade_ready",
    "Holding",
    "PortfolioRiskSummary",
    "RiskBudgetPosition",
    "summarize_portfolio",
    "size_position_by_risk_budget",
]
