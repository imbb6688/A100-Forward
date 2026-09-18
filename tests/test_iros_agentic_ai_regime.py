import unittest
from a100_iros.agentic_ai_regime import RegimeSignal, AgenticAIRegimeState, build_agentic_ai_regime, relative_strength_signal

class TestAgenticAIRegime(unittest.TestCase):
    def test_expanding_full_coverage(self):
        buckets=["token_demand","domestic_compute","optical_interconnect","semiconductor_equipment_materials","robotics","star100_relative_strength"]
        s=[RegimeSignal(bucket=b, score=.6, confidence=.9) for b in buckets]
        r=build_agentic_ai_regime(s)
        self.assertEqual(r.state, AgenticAIRegimeState.EXPANDING)
        self.assertEqual(r.coverage, 1.0)
        self.assertGreater(r.score_0_100, 70)

    def test_missing_data_is_not_neutralized(self):
        r=build_agentic_ai_regime([RegimeSignal(bucket="domestic_compute", score=1.0)])
        self.assertEqual(r.state, AgenticAIRegimeState.INSUFFICIENT_DATA)
        self.assertLess(r.coverage, .67)

    def test_relative_strength(self):
        s=relative_strength_signal(star100_return=.12, star50_return=.04, csi300_return=.02, horizon="20d")
        self.assertGreater(s.score, 0)

if __name__=="__main__": unittest.main()
