import json
import tempfile
import unittest
from pathlib import Path

from a100_iros import (
    DecisionState,
    EvidenceItem,
    EvidenceKind,
    ResearchObject,
    SecurityResearchCard,
    Thesis,
    ThesisStance,
    load_research_object,
    save_research_object,
)


class IrosStorageTests(unittest.TestCase):
    def test_round_trip_preserves_research_state(self) -> None:
        obj = ResearchObject(
            research_id="SEC-600206-001",
            security=SecurityResearchCard(
                ticker="600206.SH",
                company_name="Example",
                evidence=[
                    EvidenceItem(
                        kind=EvidenceKind.HYPOTHESIS,
                        statement="Demand may accelerate",
                        confidence=0.6,
                    )
                ],
                thesis=Thesis(
                    stance=ThesisStance.POSITIVE,
                    bull_case="Upside case",
                    invalidation_conditions=["Demand weakens"],
                    confidence=0.65,
                ),
            ),
        )
        obj.transition(DecisionState.RESEARCHING)
        obj.transition(DecisionState.CANDIDATE)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "research.json"
            save_research_object(obj, path)
            loaded = load_research_object(path)

        self.assertEqual(loaded.research_id, obj.research_id)
        self.assertEqual(loaded.state, DecisionState.CANDIDATE)
        self.assertEqual(loaded.security.ticker, "600206.SH")
        self.assertEqual(loaded.security.thesis.stance, ThesisStance.POSITIVE)
        self.assertEqual(loaded.security.evidence[0].kind, EvidenceKind.HYPOTHESIS)
        self.assertEqual(loaded.state_history, obj.state_history)

    def test_unknown_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "research.json"
            path.write_text(json.dumps({"schema_version": "999"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsupported IROS schema_version"):
                load_research_object(path)


if __name__ == "__main__":
    unittest.main()
