import pytest

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


def test_ticker_is_normalized() -> None:
    obj = make_object()
    assert obj.security.ticker == "300007.SZ"


def test_valid_research_state_path() -> None:
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
    assert obj.state is DecisionState.ARCHIVED
    assert [row["state"] for row in obj.state_history] == [
        DecisionState.DISCOVERED.value,
        *[state.value for state in path],
    ]


def test_invalid_state_jump_is_rejected() -> None:
    obj = make_object()
    with pytest.raises(ValueError, match="invalid transition"):
        obj.transition(DecisionState.ACTIVE_POSITION)


def test_confidence_is_bounded() -> None:
    with pytest.raises(ValueError, match="confidence"):
        EvidenceItem(kind=EvidenceKind.FACT, statement="x", confidence=1.01)
    with pytest.raises(ValueError, match="confidence"):
        Thesis(confidence=-0.01)


def test_serialization_contains_plain_enum_values() -> None:
    obj = make_object()
    payload = obj.to_dict()
    assert payload["state"] == "DISCOVERED"
    assert payload["security"]["thesis"]["stance"] == "NEUTRAL"
    assert payload["security"]["evidence"][0]["kind"] == "FACT"
