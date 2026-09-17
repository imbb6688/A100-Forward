from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .assessments import ValidationStatus
from .models import DecisionState, EvidenceKind, ResearchObject


@dataclass(frozen=True)
class GateResult:
    passed: bool
    checks: Dict[str, bool]
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "passed": self.passed,
            "checks": dict(self.checks),
            "reasons": list(self.reasons),
        }


def evaluate_trade_readiness(obj: ResearchObject) -> GateResult:
    """Governance gate only; this is not a buy/sell signal.

    TRADE_READY is allowed only when research has explicit invalidation criteria,
    at least one factual/evidentiary item, a defined base case, non-null confidence,
    and metadata proving the validation stage has reached VALIDATED.
    """

    evidence_kinds = {item.kind for item in obj.security.evidence}
    validation_raw = str(obj.metadata.get("validation_status", ""))

    checks = {
        "state_is_validation": obj.state is DecisionState.VALIDATION,
        "has_fact_or_evidence": bool(evidence_kinds & {EvidenceKind.FACT, EvidenceKind.EVIDENCE}),
        "has_base_case": bool(obj.security.thesis.base_case.strip()),
        "has_invalidation_conditions": bool(obj.security.thesis.invalidation_conditions),
        "has_confidence": obj.security.thesis.confidence is not None,
        "validation_status_is_validated": validation_raw == ValidationStatus.VALIDATED.value,
    }

    labels = {
        "state_is_validation": "object must be in VALIDATION before TRADE_READY",
        "has_fact_or_evidence": "at least one FACT or EVIDENCE item is required",
        "has_base_case": "thesis base_case is required",
        "has_invalidation_conditions": "at least one invalidation condition is required",
        "has_confidence": "thesis confidence is required",
        "validation_status_is_validated": "04 Backtest & Validation acceptance must set validation_status=VALIDATED",
    }
    reasons = [labels[key] for key, value in checks.items() if not value]
    return GateResult(passed=all(checks.values()), checks=checks, reasons=reasons)


def promote_to_trade_ready(obj: ResearchObject) -> GateResult:
    result = evaluate_trade_readiness(obj)
    if result.passed:
        obj.transition(DecisionState.TRADE_READY)
    return result
