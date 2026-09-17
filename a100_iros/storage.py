from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .models import (
    DecisionState,
    EvidenceItem,
    EvidenceKind,
    ResearchObject,
    SecurityResearchCard,
    Thesis,
    ThesisStance,
)

SCHEMA_VERSION = "0.1"


def _from_payload(payload: Dict[str, Any]) -> ResearchObject:
    schema_version = payload.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported IROS schema_version: {schema_version!r}")

    raw = payload["research_object"]
    sec = raw["security"]
    thesis_raw = sec.get("thesis", {})
    evidence_raw = sec.get("evidence", [])

    thesis = Thesis(
        stance=ThesisStance(thesis_raw.get("stance", ThesisStance.UNDETERMINED.value)),
        bull_case=thesis_raw.get("bull_case", ""),
        base_case=thesis_raw.get("base_case", ""),
        bear_case=thesis_raw.get("bear_case", ""),
        must_be_true=list(thesis_raw.get("must_be_true", [])),
        invalidation_conditions=list(thesis_raw.get("invalidation_conditions", [])),
        priced_in_assessment=thesis_raw.get("priced_in_assessment", ""),
        variant_perception=thesis_raw.get("variant_perception", ""),
        confidence=thesis_raw.get("confidence"),
        updated_at=thesis_raw.get("updated_at") or raw.get("updated_at"),
    )

    evidence = [
        EvidenceItem(
            kind=EvidenceKind(item["kind"]),
            statement=item["statement"],
            source=item.get("source"),
            observed_at=item.get("observed_at"),
            confidence=item.get("confidence"),
        )
        for item in evidence_raw
    ]

    card = SecurityResearchCard(
        ticker=sec["ticker"],
        company_name=sec.get("company_name", ""),
        market_context=dict(sec.get("market_context", {})),
        industry_context=dict(sec.get("industry_context", {})),
        fundamentals=dict(sec.get("fundamentals", {})),
        valuation=dict(sec.get("valuation", {})),
        catalysts=list(sec.get("catalysts", [])),
        event_risks=list(sec.get("event_risks", [])),
        technical_structure=dict(sec.get("technical_structure", {})),
        positioning=dict(sec.get("positioning", {})),
        risks=list(sec.get("risks", [])),
        evidence=evidence,
        thesis=thesis,
    )

    return ResearchObject(
        research_id=raw["research_id"],
        security=card,
        state=DecisionState(raw["state"]),
        created_at=raw["created_at"],
        updated_at=raw["updated_at"],
        state_history=list(raw.get("state_history", [])),
        metadata=dict(raw.get("metadata", {})),
    )


def save_research_object(obj: ResearchObject, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "research_object": obj.to_dict(),
    }
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(target)


def load_research_object(path: str | Path) -> ResearchObject:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("IROS payload must be a JSON object")
    return _from_payload(payload)
