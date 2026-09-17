from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .models import DecisionState, EvidenceKind, ResearchObject
from .trade_plan import trade_plan_from_dict
from .validation import validation_record_from_dict


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


def _has_valid_validation_record(obj: ResearchObject) -> bool:
    raw = obj.metadata.get("validation_record")
    if not isinstance(raw, dict):
        return False
    try:
        return validation_record_from_dict(raw).is_validated
    except (KeyError, TypeError, ValueError):
        return False


def _has_valid_trade_plan(obj: ResearchObject) -> bool:
    raw = obj.metadata.get("trade_plan")
    if not isinstance(raw, dict):
        return False
    try:
        plan = trade_plan_from_dict(raw)
    except (KeyError, TypeError, ValueError):
        return False
    return plan.ticker.strip().upper() == obj.security.ticker


def evaluate_trade_readiness(obj: ResearchObject) -> GateResult:
    """Governance gate only; this is not a buy/sell signal.

    TRADE_READY requires explicit thesis invalidation, sourced factual evidence,
    a complete Backtest -> Walk Forward -> Shadow/Paper validation record that has
    an acceptance reference, and a structured trade plan. No single metadata flag
    can bypass this gate.
    """

    evidence_kinds = {item.kind for item in obj.security.evidence}

    checks = {
        "state_is_validation": obj.state is DecisionState.VALIDATION,
        "has_fact_or_evidence": bool(evidence_kinds & {EvidenceKind.FACT, EvidenceKind.EVIDENCE}),
        "has_base_case": bool(obj.security.thesis.base_case.strip()),
        "has_invalidation_conditions": bool(obj.security.thesis.invalidation_conditions),
        "has_confidence": obj.security.thesis.confidence is not None,
        "has_valid_validation_record": _has_valid_validation_record(obj),
        "has_valid_trade_plan": _has_valid_trade_plan(obj),
    }

    labels = {
        "state_is_validation": "object must be in VALIDATION before TRADE_READY",
        "has_fact_or_evidence": "at least one FACT or EVIDENCE item is required",
        "has_base_case": "thesis base_case is required",
        "has_invalidation_conditions": "at least one invalidation condition is required",
        "has_confidence": "thesis confidence is required",
        "has_valid_validation_record": "Backtest, Walk Forward and Shadow/Paper must all PASS and have an acceptance reference",
        "has_valid_trade_plan": "a structured trade plan matching the ticker is required",
    }
    reasons = [labels[key] for key, value in checks.items() if not value]
    return GateResult(passed=all(checks.values()), checks=checks, reasons=reasons)


def promote_to_trade_ready(obj: ResearchObject) -> GateResult:
    result = evaluate_trade_readiness(obj)
    if result.passed:
        obj.transition(DecisionState.TRADE_READY)
    return result
