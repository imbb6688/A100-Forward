import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestWorkflowGovernance(unittest.TestCase):
    def test_backfill_is_manual_only(self):
        text = (ROOT / ".github/workflows/yinyang-backfill.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("\n  push:", text)

    def test_v2_calibration_is_manual_only(self):
        text = (ROOT / ".github/workflows/yinyang-v2-calibration.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("\n  push:", text)

    def test_daily_does_not_use_broad_research_push_globs(self):
        text = (ROOT / ".github/workflows/a100-forward.yml").read_text(encoding="utf-8")
        self.assertNotIn("- 'scripts/**'", text)
        self.assertNotIn("- 'a100_iros/**'", text)
        self.assertNotIn("- 'tests/**'", text)

    def test_daily_keeps_yinyang_research_fail_soft(self):
        text = (ROOT / ".github/workflows/a100-forward.yml").read_text(encoding="utf-8")
        self.assertIn("Yin-Yang v2 failed; Frozen V7 remains unaffected.", text)
        self.assertIn("yinyang_v2_publish_ready", text)
        self.assertIn("validate_yinyang_v2_runtime.py", text)


    def test_forward_schedule_documentation_matches_workflow(self):
        workflow = (ROOT / ".github/workflows/a100-forward.yml").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("cron: '10 8 * * 1-5'", workflow)
        self.assertIn("16:10 Asia/Shanghai", workflow)
        self.assertIn("16:10 Asia/Shanghai", readme)
        self.assertNotIn("15:35 Asia/Shanghai", readme)

    def test_autonomous_ci_is_scoped_to_autonomous_surface(self):
        text = (ROOT / ".github/workflows/a100-autonomous-ci.yml").read_text(encoding="utf-8")
        self.assertNotIn("- 'tests/**'", text)
        self.assertNotIn("- 'validation/**'", text)
        self.assertNotIn("- '.github/workflows/a100-forward.yml'", text)
        self.assertIn("- 'tests/test_autonomous_policy.py'", text)
        self.assertIn("-p 'test_autonomous_policy.py'", text)

    def test_agentic_persistence_is_scoped(self):
        text = (ROOT / ".github/workflows/a100-forward.yml").read_text(encoding="utf-8")
        self.assertNotIn(
            "cp -a /mnt/data/state/iros-regime/. state/iros-regime/",
            text,
        )
        self.assertIn(
            "cp -f /mnt/data/state/iros-regime/latest.json state/iros-regime/latest.json",
            text,
        )


if __name__ == "__main__":
    unittest.main()
