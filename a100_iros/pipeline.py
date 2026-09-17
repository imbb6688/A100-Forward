from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from .assessments import EventAssessment, IndustryAssessment, MarketRegimeAssessment, ResearchScore
from .models import DecisionState, EvidenceItem, ResearchObject, Thesis, ThesisStance
from .trade_plan import TradePlan
from .validation import ValidationRecord


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PremortemFailure:
    category: str
    scenario: str
    early_warning: str = ""
    mitigation: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "category": self.category,
            "scenario": self.scenario,
            "early_warning": self.early_warning,
            "mitigation": self.mitigation,
        }


@dataclass
class ResearchPipeline:
    """Deterministic coordinator for already-sourced research inputs.

    This class does not fetch market data and does not generate orders. It records
    assessments, evidence and governance metadata into a ResearchObject so the
    research path is reproducible and auditable.
    """

    obj: ResearchObject
    audit_log: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        existing = self.obj.metadata.get("iros_audit_log")
        if isinstance(existing, list):
            self.audit_log = [dict(row) for row in existing if isinstance(row, dict)]

    def _record(self, action: str, details: Optional[Dict[str, Any]] = None) -> None:
        row: Dict[str, Any] = {"at": _utc_now(), "action": action}
        if details:
            row["details"] = details
        self.audit_log.append(row)
        self.obj.metadata["iros_audit_log"] = list(self.audit_log)
        self.obj.updated_at = row["at"]

    def ensure_researching(self) -> None:
        if self.obj.state is DecisionState.DISCOVERED:
            self.obj.transition(DecisionState.RESEARCHING)
            self._record("transition_to_researching")

    def apply_market_regime(self, assessment: MarketRegimeAssessment) -> None:
        self.ensure_researching()
        self.obj.security.market_context = assessment.to_dict()
        self._record("apply_market_regime", {"validation_status": assessment.validation_status.value})

    def apply_industry(self, assessment: IndustryAssessment) -> None:
        self.ensure_researching()
        self.obj.security.industry_context = assessment.to_dict()
        self._record("apply_industry_assessment", {"industry": assessment.industry})

    def set_fundamentals(self, data: Dict[str, Any]) -> None:
        self.ensure_researching()
        self.obj.security.fundamentals = dict(data)
        self._record("set_fundamentals", {"fields": sorted(self.obj.security.fundamentals)})

    def set_valuation(self, data: Dict[str, Any]) -> None:
        self.ensure_researching()
        self.obj.security.valuation = dict(data)
        self._record("set_valuation", {"fields": sorted(self.obj.security.valuation)})

    def set_technical_structure(self, data: Dict[str, Any]) -> None:
        self.ensure_researching()
        self.obj.security.technical_structure = dict(data)
        self._record("set_technical_structure", {"fields": sorted(self.obj.security.technical_structure)})

    def set_positioning(self, data: Dict[str, Any]) -> None:
        self.ensure_researching()
        self.obj.security.positioning = dict(data)
        self._record("set_positioning", {"fields": sorted(self.obj.security.positioning)})

    def set_risks(self, risks: Iterable[str]) -> None:
        self.ensure_researching()
        normalized: List[str] = []
        seen = set()
        for risk in risks:
            value = " ".join(str(risk).split()).strip()
            key = value.lower()
            if value and key not in seen:
                normalized.append(value)
                seen.add(key)
        self.obj.security.risks = normalized
        self._record("set_risks", {"count": len(normalized)})

    def add_event(self, event: EventAssessment) -> None:
        self.ensure_researching()
        payload = event.to_dict()
        direction = payload["direction"]
        if direction == "NEGATIVE":
            self.obj.security.event_risks.append(payload)
        else:
            self.obj.security.catalysts.append(payload)
        self._record("add_event", {"event_id": event.event_id, "direction": direction})

    def add_evidence(self, evidence: Iterable[EvidenceItem]) -> None:
        self.ensure_researching()
        count = 0
        existing = {
            (item.kind.value, " ".join(item.statement.split()).strip().lower(), item.source or "")
            for item in self.obj.security.evidence
        }
        for item in evidence:
            key = (item.kind.value, " ".join(item.statement.split()).strip().lower(), item.source or "")
            if key not in existing:
                self.obj.security.evidence.append(item)
                existing.add(key)
                count += 1
        self._record("add_evidence", {"added": count})

    def update_thesis(
        self,
        *,
        stance: ThesisStance,
        bull_case: str,
        base_case: str,
        bear_case: str,
        must_be_true: Iterable[str],
        invalidation_conditions: Iterable[str],
        confidence: Optional[float],
        priced_in_assessment: str = "",
        variant_perception: str = "",
    ) -> None:
        self.ensure_researching()
        self.obj.security.thesis = Thesis(
            stance=stance,
            bull_case=bull_case,
            base_case=base_case,
            bear_case=bear_case,
            must_be_true=list(must_be_true),
            invalidation_conditions=list(invalidation_conditions),
            priced_in_assessment=priced_in_assessment,
            variant_perception=variant_perception,
            confidence=confidence,
        )
        self._record("update_thesis", {"stance": stance.value, "confidence": confidence})

    def set_research_score(self, score: ResearchScore) -> None:
        self.obj.metadata["research_score"] = score.to_dict()
        self._record("set_research_score", {"score": score.score, "validation_status": score.validation_status.value})

    def set_premortem(self, failures: Iterable[PremortemFailure]) -> None:
        rows = [item.to_dict() for item in failures]
        self.obj.metadata["premortem"] = rows
        self._record("set_premortem", {"count": len(rows)})

    def attach_validation_record(self, record: ValidationRecord) -> None:
        self.obj.metadata["validation_record"] = record.to_dict()
        self.obj.metadata["validation_status"] = record.status.value
        self._record(
            "attach_validation_record",
            {"validation_id": record.validation_id, "status": record.status.value},
        )

    def attach_trade_plan(self, plan: TradePlan) -> None:
        if plan.ticker.strip().upper() != self.obj.security.ticker:
            raise ValueError("trade plan ticker does not match research object")
        self.obj.metadata["trade_plan"] = plan.to_dict()
        self._record("attach_trade_plan", {"plan_id": plan.plan_id})

    def mark_candidate(self) -> None:
        self.ensure_researching()
        if self.obj.state is DecisionState.RESEARCHING:
            self.obj.transition(DecisionState.CANDIDATE)
            self._record("mark_candidate")
        elif self.obj.state is DecisionState.WATCHLIST:
            self.obj.transition(DecisionState.CANDIDATE)
            self._record("mark_candidate")
        elif self.obj.state is not DecisionState.CANDIDATE:
            raise ValueError(f"cannot mark candidate from state {self.obj.state.value}")

    def send_to_validation(self) -> None:
        if self.obj.state is not DecisionState.CANDIDATE:
            raise ValueError("research object must be CANDIDATE before VALIDATION")
        self.obj.transition(DecisionState.VALIDATION)
        self._record("send_to_validation")
