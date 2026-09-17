import unittest

from a100_iros import (
    DecisionState,
    EvidenceItem,
    EvidenceKind,
    ResearchObject,
    SecurityResearchCard,
    Thesis,
    ThesisStance,
)


def make_object() -> ResearchObject:
    card = SecurityResearchCard(
        ticker=" 300007.sz ",
        company_name="Example",
        evidence=[
            EvidenceItem(
                kind=EvidenceKind.FACT,
                statement="Example fact",
                source="unit-test",
                confidence=1.0,
            )
        ],
        thesis=Thesis(
            stance=ThesisStance.NEUTRAL,
            base_case="Research pending",
            confidence=0.5,
        ),
    )
    return ResearchObject(research_id="SEC-300007-001", security=card)


class IrosModelTests(unittest.TestCase):
    def test_ticker_is_normalized(self) -> None:
        obj = make_object()
        self.assertEqual(obj.security.ticker, "300007.SZ")

    def test_valid_research_state_path(self) -> None:
        obj = make_object()
        path = [
            DecisionState.RESEARCHING,
            DecisionState.CANDIDATE,
            DecisionState.VALIDATION,
            DecisionState.TRADE_READY,
            DecisionState.ACTIVE_POSITION,
            DecisionState.EXIT,
            DecisionState.POST_REVIEW,
            DecisionState.ARCHIVED,
        ]
        for state in path:
            obj.transition(state)
        self.assertIs(obj.state, DecisionState.ARCHIVED)
        self.assertEqual(
            [row["state"] for row in obj.state_history],
            [DecisionState.DISCOVERED.value, *[state.value for state in path]],
        )

    def test_invalid_state_jump_is_rejected(self) -> None:
        obj = make_object()
        with self.assertRaisesRegex(ValueError, "invalid transition"):
            obj.transition(DecisionState.ACTIVE_POSITION)

    def test_confidence_is_bounded(self) -> None:
        with self.assertRaisesRegex(ValueError, "confidence"):
            EvidenceItem(kind=EvidenceKind.FACT, statement="x", confidence=1.01)
        with self.assertRaisesRegex(ValueError, "confidence"):
            Thesis(confidence=-0.01)

    def test_serialization_contains_plain_enum_values(self) -> None:
        obj = make_object()
        payload = obj.to_dict()
        self.assertEqual(payload["state"], "DISCOVERED")
        self.assertEqual(payload["security"]["thesis"]["stance"], "NEUTRAL")
        self.assertEqual(payload["security"]["evidence"][0]["kind"], "FACT")


if __name__ == "__main__":
    unittest.main()
