import unittest

import numpy as np

from scripts.a100_v8_challenger import _period_label, _proxy_acceptance, eligibility_masks, select_top_two


class V8ChallengerTests(unittest.TestCase):
    def test_v8_changes_only_fulltrend_gate(self):
        features = {
            "setup": np.array([1, 1, 0, 1]),
            "market": np.array([14.0, 14.0, 14.0, 13.0]),
            "industry": np.array([9.0, 9.0, 9.0, 9.0]),
            "gate": np.array([True, False, True, True]),
        }
        masks = eligibility_masks(features, np.array([75.0, 75.0, 75.0, 75.0]))
        self.assertEqual(masks["FROZEN_V7"].tolist(), [True, False, False, False])
        self.assertEqual(masks["V8_COMPOSITE_GATE"].tolist(), [True, True, False, False])

    def test_top_two_is_daily_and_out_of_sample(self):
        eligible = np.ones(6, dtype=bool)
        scores = np.array([0.1, 0.9, 0.5, 0.3, 0.8, 0.7])
        net_r = np.ones(6)
        years = np.array([2022, 2023, 2023, 2023, 2024, 2024])
        dates = np.array([0, 1, 1, 1, 2, 2])
        selected = select_top_two(eligible, scores, net_r, years, dates)
        self.assertEqual(selected.tolist(), [1, 2, 4, 5])

    def test_proxy_acceptance_requires_cross_fold_robustness(self):
        strong = [
            {"trades": 40, "net_return": 0.1, "profit_factor": 1.2, "max_drawdown": -0.05},
            {"trades": 40, "net_return": 0.1, "profit_factor": 1.3, "max_drawdown": -0.06},
            {"trades": 40, "net_return": 0.1, "profit_factor": 1.4, "max_drawdown": -0.07},
        ]
        self.assertTrue(_proxy_acceptance(strong)["passed_all_proxy_checks"])
        weak = [dict(row) for row in strong]
        weak[0]["profit_factor"] = 0.5
        self.assertFalse(_proxy_acceptance(weak)["passed_all_proxy_checks"])

    def test_2026_is_diagnostic_not_acceptance_evidence(self):
        self.assertEqual(_period_label(2023), "RETROSPECTIVE_SELECTION")
        self.assertEqual(_period_label(2025), "RETROSPECTIVE_LOCKED_TEST")
        self.assertEqual(_period_label(2026), "CONTAMINATED_DIAGNOSTIC_ONLY")


if __name__ == "__main__":
    unittest.main()
