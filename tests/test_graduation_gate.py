import json
import tempfile
import unittest
from pathlib import Path

from scripts.a100_graduation_gate import evaluate
from scripts.a100_risk_scenarios import run_scenarios


POLICY = Path(__file__).parents[1] / "config" / "graduation_policy.json"


class GraduationGateTests(unittest.TestCase):
    def _root(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        (root / "state").mkdir()
        (root / "validation").mkdir()
        (root / "hithink_manifest.json").write_text(json.dumps({"data_valid": True, "full_market": True, "complete": True, "latest_rows": 5000, "completeness_ratio": 1.0}))
        (root / "validation" / "data_inventory.json").write_text(json.dumps({"datasets": {name: {"status": "COMPLETE", "point_in_time_safe": True} for name in ("price_adjustment", "st_risk_warning_history", "industry_membership_history")}}))
        folds = [{"profit_factor": 1.2, "max_drawdown": -0.10, "trades": 40, "net_return": 0.02} for _ in range(3)]
        (root / "validation" / "walk_forward_report.json").write_text(json.dumps({"status": "COMPLETE", "data_fingerprint": "abc", "folds": folds}))
        scenarios = run_scenarios()
        (root / "validation" / "risk_scenarios.json").write_text(json.dumps(scenarios))
        (root / "state" / "account_state.json").write_text(json.dumps({"closed_trades": 30, "max_drawdown": -0.05}))
        (root / "state" / "equity_curve.csv").write_text("date\n" + "\n".join(f"2026-01-{i:02d}" for i in range(1, 61)))
        trades = "pnl\n" + "\n".join(["2"] * 20 + ["-1"] * 10)
        (root / "state" / "trade_log.csv").write_text(trades)
        dates = [f"2026-01-{i:02d}" for i in range(1, 61)]
        (root / "state" / "autonomous_journal.csv").write_text("date,mode\n" + "\n".join(f"{d},PAPER" for d in dates))
        return tmp, root

    def test_current_evidence_fails_closed(self):
        policy = json.loads(POLICY.read_text())
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = evaluate(policy, root)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["live_trading_enabled"])

    def test_complete_synthetic_evidence_can_graduate_but_never_auto_enables_live(self):
        policy = json.loads(POLICY.read_text())
        tmp, root = self._root()
        try:
            result = evaluate(policy, root)
        finally:
            tmp.cleanup()
        self.assertEqual(result["status"], "GRADUATED")
        self.assertFalse(result["live_trading_enabled"])
        self.assertEqual(result["decision"], "HUMAN_APPROVAL_REQUIRED_AFTER_GRADUATION")

    def test_risk_scenarios_pass(self):
        report = run_scenarios()
        self.assertTrue(all(x["passed"] for x in report["scenarios"].values()))


if __name__ == "__main__":
    unittest.main()
