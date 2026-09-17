import tempfile
import unittest

from a100_iros import (
    DecisionState,
    EvidenceItem,
    EvidenceKind,
    EvidenceLedger,
    EvidenceStatus,
    EventAssessment,
    EventDirection,
    Holding,
    IndustryAssessment,
    MarketRegimeAssessment,
    MarketRiskMode,
    PremortemFailure,
    ResearchObject,
    ResearchPipeline,
    ResearchRepository,
    ResearchSnapshot,
    SecurityResearchCard,
    StageOutcome,
    Thesis,
    ThesisStance,
    TradePlan,
    TrendMode,
    ValidationRecord,
    ValidationStage,
    ValidationStageResult,
    ValidationStatus,
    compare_snapshots,
    evaluate_trade_readiness,
    promote_to_trade_ready,
    size_position_by_risk_budget,
    summarize_portfolio,
    weighted_research_score,
)


def make_object() -> ResearchObject:
    return ResearchObject(
        research_id="SEC-300007-001",
        security=SecurityResearchCard(
            ticker="300007.sz",
            company_name="Example",
            thesis=Thesis(stance=ThesisStance.NEUTRAL, base_case="Initial case", confidence=0.5),
        ),
    )


def validated_record() -> ValidationRecord:
    return ValidationRecord(
        validation_id="VAL-001",
        stages=[
            ValidationStageResult(ValidationStage.BACKTEST, StageOutcome.PASS, evidence_ref="artifact://backtest"),
            ValidationStageResult(ValidationStage.WALK_FORWARD, StageOutcome.PASS, evidence_ref="artifact://wf"),
            ValidationStageResult(ValidationStage.SHADOW_PAPER, StageOutcome.PASS, evidence_ref="artifact://shadow"),
        ],
        accepted_at="2026-09-17T00:00:00+00:00",
        acceptance_ref="04-backtest-validation/acceptance-001",
    )


class IROSV1Tests(unittest.TestCase):
    def test_snapshot_delta_tracks_thesis_evidence_and_risk_changes(self) -> None:
        obj = make_object()
        before = ResearchSnapshot.capture(obj, snapshot_id="s1", captured_at="2026-09-17T00:00:00+00:00")
        obj.security.evidence.append(EvidenceItem(kind=EvidenceKind.FACT, statement="Revenue accelerated", source="filing"))
        obj.security.risks.append("Valuation compression")
        obj.security.thesis = Thesis(
            stance=ThesisStance.POSITIVE,
            base_case="Improving",
            bear_case="Demand weakens",
            invalidation_conditions=["Demand rolls over"],
            confidence=0.7,
        )
        after = ResearchSnapshot.capture(obj, snapshot_id="s2", captured_at="2026-09-18T00:00:00+00:00")
        delta = compare_snapshots(before, after)
        self.assertEqual(delta.stance_before, "NEUTRAL")
        self.assertEqual(delta.stance_after, "POSITIVE")
        self.assertAlmostEqual(delta.confidence_change, 0.2)
        self.assertEqual(delta.added_evidence, ["Revenue accelerated"])
        self.assertEqual(delta.added_risks, ["Valuation compression"])
        self.assertEqual(delta.added_invalidation_conditions, ["Demand rolls over"])

    def test_repository_persists_objects_and_immutable_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = ResearchRepository(tmp)
            obj = make_object()
            repo.save(obj)
            self.assertTrue(repo.exists(obj.research_id))
            loaded = repo.load(obj.research_id)
            self.assertEqual(loaded.security.ticker, "300007.SZ")
            snap = ResearchSnapshot.capture(obj, snapshot_id="fixed", captured_at="2026-09-17T00:00:00+00:00")
            repo.save_snapshot(snap)
            with self.assertRaises(FileExistsError):
                repo.save_snapshot(snap)
            self.assertEqual(repo.list_research_ids(), [obj.research_id])
            self.assertEqual([x.snapshot_id for x in repo.list_snapshots(obj.research_id)], ["fixed"])

    def test_evidence_ledger_tracks_conflict_and_invalidation(self) -> None:
        ledger = EvidenceLedger()
        a = ledger.add(EvidenceItem(kind=EvidenceKind.FACT, statement="Demand rose", source="A"))
        b = ledger.add(EvidenceItem(kind=EvidenceKind.FACT, statement="Demand fell", source="B"))
        ledger.mark_conflict(a.evidence_id, b.evidence_id, "sources disagree")
        self.assertEqual(ledger.get(a.evidence_id).status, EvidenceStatus.CONFLICTING)
        self.assertIn(b.evidence_id, ledger.get(a.evidence_id).conflicts_with)
        ledger.invalidate(a.evidence_id, "later filing corrected data")
        self.assertEqual(ledger.get(a.evidence_id).status, EvidenceStatus.INVALIDATED)

    def test_weighted_score_is_normalized_and_unvalidated_by_default(self) -> None:
        score = weighted_research_score(
            {"industry": 80, "fundamental": 60, "technical": 70},
            {"industry": 2, "fundamental": 1, "technical": 1},
        )
        self.assertAlmostEqual(score.score, 72.5)
        self.assertEqual(score.validation_status, ValidationStatus.UNVALIDATED_RESEARCH_HEURISTIC)
        self.assertAlmostEqual(sum(score.weights.values()), 1.0)

    def test_pipeline_records_structured_research_without_auto_promoting(self) -> None:
        obj = make_object()
        pipeline = ResearchPipeline(obj)
        pipeline.apply_market_regime(
            MarketRegimeAssessment(
                risk_mode=MarketRiskMode.NEUTRAL,
                trend_mode=TrendMode.RANGE,
                confidence=0.6,
                rationale=["mixed breadth"],
            )
        )
        pipeline.apply_industry(IndustryAssessment(industry="Sensors", demand_score=70))
        pipeline.add_event(
            EventAssessment(
                event_id="evt-1",
                title="Contract update",
                direction=EventDirection.POSITIVE,
                impact=0.7,
                surprise=0.5,
                persistence=0.6,
                credibility=0.9,
                priced_in=0.4,
            )
        )
        pipeline.add_evidence([EvidenceItem(kind=EvidenceKind.FACT, statement="Filed contract update", source="exchange")])
        pipeline.update_thesis(
            stance=ThesisStance.POSITIVE,
            bull_case="Upside if demand accelerates",
            base_case="Moderate growth",
            bear_case="Demand slows",
            must_be_true=["orders convert to revenue"],
            invalidation_conditions=["orders are cancelled"],
            confidence=0.65,
        )
        pipeline.set_premortem([PremortemFailure(category="fundamental", scenario="orders fail to convert")])
        self.assertEqual(obj.state, DecisionState.RESEARCHING)
        self.assertEqual(obj.security.market_context["risk_mode"], "NEUTRAL")
        self.assertEqual(len(obj.security.catalysts), 1)
        self.assertGreaterEqual(len(obj.metadata["iros_audit_log"]), 5)

    def test_validation_record_is_not_valid_without_all_stages_and_acceptance(self) -> None:
        incomplete = ValidationRecord(
            validation_id="VAL-INCOMPLETE",
            stages=[ValidationStageResult(ValidationStage.BACKTEST, StageOutcome.PASS)],
        )
        self.assertFalse(incomplete.is_validated)
        complete_but_unaccepted = ValidationRecord(
            validation_id="VAL-UNACCEPTED",
            stages=[
                ValidationStageResult(ValidationStage.BACKTEST, StageOutcome.PASS),
                ValidationStageResult(ValidationStage.WALK_FORWARD, StageOutcome.PASS),
                ValidationStageResult(ValidationStage.SHADOW_PAPER, StageOutcome.PASS),
            ],
        )
        self.assertFalse(complete_but_unaccepted.is_validated)
        self.assertTrue(validated_record().is_validated)

    def test_trade_readiness_requires_validation_record_and_trade_plan(self) -> None:
        obj = make_object()
        pipeline = ResearchPipeline(obj)
        pipeline.ensure_researching()
        pipeline.add_evidence([EvidenceItem(kind=EvidenceKind.FACT, statement="Verified fact", source="filing")])
        pipeline.update_thesis(
            stance=ThesisStance.POSITIVE,
            bull_case="Upside",
            base_case="Validated research case",
            bear_case="Downside",
            must_be_true=["demand persists"],
            invalidation_conditions=["thesis condition fails"],
            confidence=0.7,
        )
        pipeline.mark_candidate()
        pipeline.send_to_validation()
        self.assertFalse(evaluate_trade_readiness(obj).passed)

        pipeline.attach_validation_record(validated_record())
        self.assertFalse(evaluate_trade_readiness(obj).passed)

        pipeline.attach_trade_plan(
            TradePlan(
                plan_id="PLAN-001",
                ticker="300007.SZ",
                entry_conditions=["validated entry trigger"],
                invalidation_conditions=["thesis condition fails"],
                exit_conditions=["exit condition"],
                initial_position_fraction=0.05,
                maximum_position_fraction=0.10,
            )
        )
        passed = promote_to_trade_ready(obj)
        self.assertTrue(passed.passed)
        self.assertEqual(obj.state, DecisionState.TRADE_READY)

    def test_portfolio_risk_summary_and_position_budget(self) -> None:
        summary = summarize_portfolio(
            [
                Holding("A", 300_000, industry="Optics", theme="AI", beta=1.2),
                Holding("B", 200_000, industry="Optics", theme="AI", beta=1.0),
                Holding("C", 500_000, industry="Grid", theme="Power", beta=0.8),
            ]
        )
        self.assertAlmostEqual(summary.total_market_value, 1_000_000)
        self.assertAlmostEqual(summary.industry_weights["Optics"], 0.5)
        self.assertTrue(any("Optics" in x for x in summary.warnings))
        sized = size_position_by_risk_budget(
            account_equity=1_000_000,
            risk_fraction=0.008,
            entry_price=20,
            invalidation_price=19.2,
            lot_size=100,
            max_notional_fraction=0.25,
        )
        self.assertEqual(sized.max_risk_amount, 8000)
        self.assertEqual(sized.lot_adjusted_shares, 10000)
        self.assertEqual(sized.notional, 200000)


if __name__ == "__main__":
    unittest.main()
