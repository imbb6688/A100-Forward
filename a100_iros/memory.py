from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import EvidenceItem, ResearchObject


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalized_statements(items: List[EvidenceItem]) -> Set[Tuple[str, str]]:
    return {(item.kind.value, " ".join(item.statement.split()).strip().lower()) for item in items}


@dataclass(frozen=True)
class ResearchSnapshot:
    snapshot_id: str
    research_id: str
    ticker: str
    captured_at: str
    payload: Dict[str, Any]
    note: str = ""

    @classmethod
    def capture(
        cls,
        obj: ResearchObject,
        *,
        snapshot_id: str,
        note: str = "",
        captured_at: Optional[str] = None,
    ) -> "ResearchSnapshot":
        if not snapshot_id.strip():
            raise ValueError("snapshot_id must not be empty")
        return cls(
            snapshot_id=snapshot_id.strip(),
            research_id=obj.research_id,
            ticker=obj.security.ticker,
            captured_at=captured_at or _utc_now(),
            payload=obj.to_dict(),
            note=note,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "research_id": self.research_id,
            "ticker": self.ticker,
            "captured_at": self.captured_at,
            "note": self.note,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchSnapshot":
        return cls(
            snapshot_id=str(data["snapshot_id"]),
            research_id=str(data["research_id"]),
            ticker=str(data["ticker"]),
            captured_at=str(data["captured_at"]),
            note=str(data.get("note", "")),
            payload=dict(data["payload"]),
        )


@dataclass(frozen=True)
class ThesisDelta:
    research_id: str
    ticker: str
    from_snapshot_id: str
    to_snapshot_id: str
    stance_before: str
    stance_after: str
    confidence_before: Optional[float]
    confidence_after: Optional[float]
    confidence_change: Optional[float]
    state_before: str
    state_after: str
    added_evidence: List[str] = field(default_factory=list)
    removed_evidence: List[str] = field(default_factory=list)
    added_risks: List[str] = field(default_factory=list)
    removed_risks: List[str] = field(default_factory=list)
    added_invalidation_conditions: List[str] = field(default_factory=list)
    removed_invalidation_conditions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "research_id": self.research_id,
            "ticker": self.ticker,
            "from_snapshot_id": self.from_snapshot_id,
            "to_snapshot_id": self.to_snapshot_id,
            "stance_before": self.stance_before,
            "stance_after": self.stance_after,
            "confidence_before": self.confidence_before,
            "confidence_after": self.confidence_after,
            "confidence_change": self.confidence_change,
            "state_before": self.state_before,
            "state_after": self.state_after,
            "added_evidence": list(self.added_evidence),
            "removed_evidence": list(self.removed_evidence),
            "added_risks": list(self.added_risks),
            "removed_risks": list(self.removed_risks),
            "added_invalidation_conditions": list(self.added_invalidation_conditions),
            "removed_invalidation_conditions": list(self.removed_invalidation_conditions),
        }


def _list_delta(before: List[str], after: List[str]) -> tuple[List[str], List[str]]:
    before_map = {" ".join(x.split()).strip().lower(): x for x in before if x.strip()}
    after_map = {" ".join(x.split()).strip().lower(): x for x in after if x.strip()}
    added = [after_map[k] for k in sorted(after_map.keys() - before_map.keys())]
    removed = [before_map[k] for k in sorted(before_map.keys() - after_map.keys())]
    return added, removed


def compare_snapshots(before: ResearchSnapshot, after: ResearchSnapshot) -> ThesisDelta:
    if before.research_id != after.research_id:
        raise ValueError("cannot compare snapshots from different research objects")
    if before.ticker != after.ticker:
        raise ValueError("cannot compare snapshots with different tickers")

    b = before.payload
    a = after.payload
    b_sec = b["security"]
    a_sec = a["security"]
    b_thesis = b_sec.get("thesis", {})
    a_thesis = a_sec.get("thesis", {})

    b_evidence = {
        (str(item.get("kind", "")), " ".join(str(item.get("statement", "")).split()).strip().lower()): str(item.get("statement", ""))
        for item in b_sec.get("evidence", [])
        if str(item.get("statement", "")).strip()
    }
    a_evidence = {
        (str(item.get("kind", "")), " ".join(str(item.get("statement", "")).split()).strip().lower()): str(item.get("statement", ""))
        for item in a_sec.get("evidence", [])
        if str(item.get("statement", "")).strip()
    }

    b_conf = b_thesis.get("confidence")
    a_conf = a_thesis.get("confidence")
    conf_change = None
    if b_conf is not None and a_conf is not None:
        conf_change = round(float(a_conf) - float(b_conf), 6)

    added_risks, removed_risks = _list_delta(list(b_sec.get("risks", [])), list(a_sec.get("risks", [])))
    added_invalidations, removed_invalidations = _list_delta(
        list(b_thesis.get("invalidation_conditions", [])),
        list(a_thesis.get("invalidation_conditions", [])),
    )

    return ThesisDelta(
        research_id=before.research_id,
        ticker=before.ticker,
        from_snapshot_id=before.snapshot_id,
        to_snapshot_id=after.snapshot_id,
        stance_before=str(b_thesis.get("stance", "UNDETERMINED")),
        stance_after=str(a_thesis.get("stance", "UNDETERMINED")),
        confidence_before=b_conf,
        confidence_after=a_conf,
        confidence_change=conf_change,
        state_before=str(b.get("state", "DISCOVERED")),
        state_after=str(a.get("state", "DISCOVERED")),
        added_evidence=[a_evidence[k] for k in sorted(a_evidence.keys() - b_evidence.keys())],
        removed_evidence=[b_evidence[k] for k in sorted(b_evidence.keys() - a_evidence.keys())],
        added_risks=added_risks,
        removed_risks=removed_risks,
        added_invalidation_conditions=added_invalidations,
        removed_invalidation_conditions=removed_invalidations,
    )
