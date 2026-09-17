from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from .assessments import ValidationStatus


class ValidationStage(str, Enum):
    BACKTEST = "BACKTEST"
    WALK_FORWARD = "WALK_FORWARD"
    SHADOW_PAPER = "SHADOW_PAPER"


class StageOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"


@dataclass(frozen=True)
class ValidationStageResult:
    stage: ValidationStage
    outcome: StageOutcome
    evidence_ref: str = ""
    dataset_version: str = ""
    code_version: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "stage": self.stage.value,
            "outcome": self.outcome.value,
            "evidence_ref": self.evidence_ref,
            "dataset_version": self.dataset_version,
            "code_version": self.code_version,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ValidationRecord:
    validation_id: str
    stages: List[ValidationStageResult]
    accepted_at: str = ""
    acceptance_ref: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.validation_id.strip():
            raise ValueError("validation_id must not be empty")

    @property
    def status(self) -> ValidationStatus:
        by_stage = {row.stage: row for row in self.stages}
        required = {
            ValidationStage.BACKTEST,
            ValidationStage.WALK_FORWARD,
            ValidationStage.SHADOW_PAPER,
        }
        if not required.issubset(by_stage):
            return ValidationStatus.UNVALIDATED_RESEARCH_HEURISTIC
        if any(by_stage[stage].outcome is not StageOutcome.PASS for stage in required):
            return ValidationStatus.UNVALIDATED_RESEARCH_HEURISTIC
        if not self.accepted_at.strip() or not self.acceptance_ref.strip():
            return ValidationStatus.SHADOW_VALIDATED
        return ValidationStatus.VALIDATED

    @property
    def is_validated(self) -> bool:
        return self.status is ValidationStatus.VALIDATED

    def to_dict(self) -> Dict[str, object]:
        return {
            "validation_id": self.validation_id,
            "status": self.status.value,
            "accepted_at": self.accepted_at,
            "acceptance_ref": self.acceptance_ref,
            "notes": self.notes,
            "stages": [row.to_dict() for row in self.stages],
        }


def validation_record_from_dict(data: Dict[str, object]) -> ValidationRecord:
    rows = []
    for raw in data.get("stages", []):
        if not isinstance(raw, dict):
            raise ValueError("validation stage must be an object")
        rows.append(
            ValidationStageResult(
                stage=ValidationStage(str(raw["stage"])),
                outcome=StageOutcome(str(raw["outcome"])),
                evidence_ref=str(raw.get("evidence_ref", "")),
                dataset_version=str(raw.get("dataset_version", "")),
                code_version=str(raw.get("code_version", "")),
                notes=str(raw.get("notes", "")),
            )
        )
    return ValidationRecord(
        validation_id=str(data["validation_id"]),
        stages=rows,
        accepted_at=str(data.get("accepted_at", "")),
        acceptance_ref=str(data.get("acceptance_ref", "")),
        notes=str(data.get("notes", "")),
    )
