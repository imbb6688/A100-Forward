"""A100-IROS end-to-end example.

This example uses synthetic research inputs. It does not fetch market data,
produce a live signal, or place an order.
"""

from a100_iros import (
    EvidenceItem,
    EvidenceKind,
    EventAssessment,
    EventDirection,
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
    ThesisStance,
    TradePlan,
    TrendMode,
    ValidationRecord,
    ValidationStage,
    ValidationStageResult,
    promote_to_trade_ready,
    weighted_research_score,
)


def build_demo() -> ResearchObject:
    obj = ResearchObject(
        research_id="SEC-DEMO-001",
        security=SecurityResearchCard(ticker="000001.SZ", company_name="Demo Company"),
    )
    pipeline = ResearchPipeline(obj)

    pipeline.apply_market_regime(
        MarketRegimeAssessment(
            risk_mode=MarketRiskMode.NEUTRAL,
            trend_mode=TrendMode.UP,
            confidence=0.60,
            rationale=["synthetic example only"],
        )
    )
    pipeline.apply_industry(
        IndustryAssessment(
            industry="Demo Industry",
            demand_score=65,
            relative_strength_score=70,
            catalysts=["synthetic catalyst"],
            risks=["synthetic industry risk"],
        )
    )
    pipeline.set_fundamentals({"revenue_growth_yoy": 0.15, "quality": "research input"})
    pipeline.set_valuation({"pe_ttm": 20.0, "historical_percentile": 0.55})
    pipeline.set_technical_structure({"trend": "UP", "relative_strength": 72})
    pipeline.set_positioning({"turnover_state": "NORMAL"})
    pipeline.set_risks(["demand slowdown", "valuation compression"])

    pipeline.add_event(
        EventAssessment(
            event_id="DEMO-EVENT-001",
            title="Synthetic filing event",
            direction=EventDirection.POSITIVE,
            impact=0.6,
            surprise=0.5,
            persistence=0.5,
            credibility=1.0,
            priced_in=0.4,
            source="synthetic-example",
        )
    )
    pipeline.add_evidence(
        [
            EvidenceItem(
                kind=EvidenceKind.FACT,
                statement="Synthetic fact used only to demonstrate the data contract",
                source="synthetic-example",
                confidence=1.0,
            )
        ]
    )
    pipeline.update_thesis(
        stance=ThesisStance.POSITIVE,
        bull_case="Demand accelerates and estimates rise",
        base_case="Moderate growth continues",
        bear_case="Demand slows and valuation compresses",
        must_be_true=["reported demand remains consistent with the thesis"],
        invalidation_conditions=["reported demand materially deteriorates"],
        confidence=0.60,
        priced_in_assessment="partially priced in",
        variant_perception="synthetic example",
    )
    pipeline.set_research_score(
        weighted_research_score(
            {
                "industry": 70,
                "fundamental": 68,
                "event": 60,
                "technical": 72,
                "positioning": 55,
            }
        )
    )
    pipeline.set_premortem(
        [
            PremortemFailure(
                category="fundamental",
                scenario="expected demand does not convert into reported revenue",
                early_warning="order or revenue guidance weakens",
                mitigation="invalidate thesis rather than average down automatically",
            )
        ]
    )

    pipeline.mark_candidate()
    pipeline.send_to_validation()

    # The following records demonstrate the governance contract. Real evidence refs
    # must point to actual artifacts produced by 04 Backtest & Validation.
    pipeline.attach_validation_record(
        ValidationRecord(
            validation_id="DEMO-VALIDATION-001",
            stages=[
                ValidationStageResult(ValidationStage.BACKTEST, StageOutcome.PASS, "demo://backtest"),
                ValidationStageResult(ValidationStage.WALK_FORWARD, StageOutcome.PASS, "demo://walk-forward"),
                ValidationStageResult(ValidationStage.SHADOW_PAPER, StageOutcome.PASS, "demo://shadow"),
            ],
            accepted_at="2026-09-17T00:00:00+00:00",
            acceptance_ref="demo://acceptance",
            notes="synthetic example only",
        )
    )
    pipeline.attach_trade_plan(
        TradePlan(
            plan_id="DEMO-PLAN-001",
            ticker="000001.SZ",
            entry_conditions=["validated trigger is present"],
            invalidation_conditions=["reported demand materially deteriorates"],
            exit_conditions=["thesis completes or invalidates"],
            initial_position_fraction=0.05,
            maximum_position_fraction=0.10,
            time_stop="review after the thesis horizon",
            event_stop="reassess after a material filing",
        )
    )
    result = promote_to_trade_ready(obj)
    if not result.passed:
        raise RuntimeError(result.reasons)
    return obj


if __name__ == "__main__":
    repo = ResearchRepository("state/iros-demo")
    research = build_demo()
    repo.save(research)
    repo.save_snapshot(ResearchSnapshot.capture(research, snapshot_id="demo-final"))
    print(research.to_dict())
