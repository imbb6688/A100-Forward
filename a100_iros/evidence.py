from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from .models import EvidenceItem


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def evidence_fingerprint(item: EvidenceItem) -> str:
    material = "|".join(
        [
            item.kind.value,
            " ".join(item.statement.split()).strip().lower(),
            (item.source or "").strip().lower(),
            (item.observed_at or "").strip(),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


class EvidenceStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    INVALIDATED = "INVALIDATED"
    CONFLICTING = "CONFLICTING"


@dataclass
class EvidenceLedgerEntry:
    evidence_id: str
    item: EvidenceItem
    status: EvidenceStatus = EvidenceStatus.ACTIVE
    added_at: str = field(default_factory=_utc_now)
    status_changed_at: Optional[str] = None
    status_reason: str = ""
    conflicts_with: List[str] = field(default_factory=list)

    def set_status(self, status: EvidenceStatus, reason: str = "") -> None:
        self.status = status
        self.status_changed_at = _utc_now()
        self.status_reason = reason

    def to_dict(self) -> Dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "item": {
                "kind": self.item.kind.value,
                "statement": self.item.statement,
                "source": self.item.source,
                "observed_at": self.item.observed_at,
                "confidence": self.item.confidence,
            },
            "status": self.status.value,
            "added_at": self.added_at,
            "status_changed_at": self.status_changed_at,
            "status_reason": self.status_reason,
            "conflicts_with": list(self.conflicts_with),
        }


class EvidenceLedger:
    def __init__(self) -> None:
        self._entries: Dict[str, EvidenceLedgerEntry] = {}

    def add(self, item: EvidenceItem) -> EvidenceLedgerEntry:
        evidence_id = evidence_fingerprint(item)
        if evidence_id not in self._entries:
            self._entries[evidence_id] = EvidenceLedgerEntry(evidence_id=evidence_id, item=item)
        return self._entries[evidence_id]

    def get(self, evidence_id: str) -> EvidenceLedgerEntry:
        return self._entries[evidence_id]

    def invalidate(self, evidence_id: str, reason: str) -> None:
        self.get(evidence_id).set_status(EvidenceStatus.INVALIDATED, reason)

    def supersede(self, old_id: str, new_item: EvidenceItem, reason: str) -> EvidenceLedgerEntry:
        old = self.get(old_id)
        new = self.add(new_item)
        old.set_status(EvidenceStatus.SUPERSEDED, reason)
        return new

    def mark_conflict(self, left_id: str, right_id: str, reason: str = "") -> None:
        if left_id == right_id:
            raise ValueError("an evidence item cannot conflict with itself")
        left = self.get(left_id)
        right = self.get(right_id)
        if right_id not in left.conflicts_with:
            left.conflicts_with.append(right_id)
        if left_id not in right.conflicts_with:
            right.conflicts_with.append(left_id)
        left.set_status(EvidenceStatus.CONFLICTING, reason)
        right.set_status(EvidenceStatus.CONFLICTING, reason)

    def active(self) -> List[EvidenceLedgerEntry]:
        return [entry for entry in self._entries.values() if entry.status is EvidenceStatus.ACTIVE]

    def entries(self) -> List[EvidenceLedgerEntry]:
        return sorted(self._entries.values(), key=lambda item: (item.added_at, item.evidence_id))

    def to_dict(self) -> Dict[str, object]:
        return {"entries": [entry.to_dict() for entry in self.entries()]}
