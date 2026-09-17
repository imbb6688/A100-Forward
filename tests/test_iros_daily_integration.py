import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IROSDailyIntegrationTests(unittest.TestCase):
    def test_no_targets_is_successful_no_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            watchlist = folder / "watchlist.json"
            watchlist.write_text('{"watchlist":[]}', encoding="utf-8")
            research_root = folder / "research"
            env = dict(os.environ)
            env["HITHINK_FINANCE_API_KEY"] = "test-only"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/iros_enrich.py"),
                    "--daily",
                    str(folder / "missing.parquet"),
                    "--signal",
                    str(folder / "missing-signal.json"),
                    "--watchlist",
                    str(watchlist),
                    "--root",
                    str(research_root),
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            summary = json.loads((research_root / "latest_enrichment_run.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "SKIPPED_NO_TARGETS")
            self.assertEqual(summary["complete"], 0)
            self.assertEqual(summary["failed"], 0)

    def test_daily_workflow_is_research_failure_isolated(self):
        workflow = (ROOT / ".github/workflows/a100-forward.yml").read_text(encoding="utf-8")
        enrich = workflow.index("- name: Enrich IROS Security Research Files")
        account = workflow.index("- name: Update Forward Account V1")
        self.assertLess(enrich, account)
        self.assertIn("if python scripts/iros_enrich.py", workflow)
        self.assertIn("previous valid research files will remain unchanged", workflow)
        self.assertIn("touch /mnt/data/iros_enrichment_publish_ready", workflow)
        self.assertIn("git add state/iros_research", workflow)


if __name__ == "__main__":
    unittest.main()
