import unittest

from a100_iros.agentic_ai_regime import (
    CANONICAL_BUCKETS,
    AgenticAIRegimeState,
    RegimeSignal,
    build_agentic_ai_regime,
    relative_strength_signal,
    validate_weights,
)


class TestAgenticAIRegime(unittest.TestCase):
    def test_expanding_full_coverage(self):
        signals = [RegimeSignal(bucket=bucket, score=0.6, confidence=0.9) for bucket in CANONICAL_BUCKETS]
        result = build_agentic_ai_regime(signals)
        self.assertEqual(result.state, AgenticAIRegimeState.EXPANDING)
        self.assertEqual(result.coverage, 1.0)
        self.assertGreater(result.score_0_100, 70)

    def test_missing_data_is_not_neutralized(self):
        result = build_agentic_ai_regime([RegimeSignal(bucket="domestic_compute", score=1.0)])
        self.assertEqual(result.state, AgenticAIRegimeState.INSUFFICIENT_DATA)
        self.assertLess(result.coverage, 0.67)

    def test_zero_confidence_fails_effective_coverage(self):
        signals = [RegimeSignal(bucket=bucket, score=1.0, confidence=0.0) for bucket in CANONICAL_BUCKETS]
        result = build_agentic_ai_regime(signals)
        self.assertEqual(result.coverage, 1.0)
        self.assertEqual(result.effective_coverage, 0.0)
        self.assertEqual(result.state, AgenticAIRegimeState.INSUFFICIENT_DATA)

    def test_relative_strength_scale_and_provenance(self):
        signal = relative_strength_signal(
            star100_return=0.12, star50_return=0.04, csi300_return=0.02,
            horizon="20d", scale=0.10, observed_at="2026-09-18", source="test",
        )
        self.assertGreater(signal.score, 0)
        self.assertEqual(signal.observed_at, "2026-09-18")
        self.assertEqual(signal.proxy_type, "index_relative_strength")

    def test_rejects_unknown_signal_bucket(self):
        with self.assertRaisesRegex(ValueError, "unknown regime bucket"):
            RegimeSignal(bucket="invented", score=0.0)

    def test_weights_are_exact_and_sum_to_one(self):
        with self.assertRaisesRegex(ValueError, "canonical buckets"):
            validate_weights({"domestic_compute": 1.0})
        invalid = {bucket: 0.1 for bucket in CANONICAL_BUCKETS}
        with self.assertRaisesRegex(ValueError, "sum to 1.0"):
            validate_weights(invalid)


if __name__ == "__main__":
    unittest.main()
