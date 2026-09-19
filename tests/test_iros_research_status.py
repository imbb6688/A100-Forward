import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_research_status


class TestResearchStatus(unittest.TestCase):
    def test_stale_yinyang_snapshot_is_unavailable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = root / "manifest.json"
            yy = root / "yy.json"
            out = root / "status.json"

            manifest.write_text(json.dumps({
                "latest_trade_date": "2026-09-18",
                "full_market": True,
            }), encoding="utf-8")
            yy.write_text(json.dumps({
                "trade_date": "2026-09-17",
                "yang_pct": 45.0,
                "yin_pct": 55.0,
                "position_tenths": 3,
                "signal": "NONE",
                "state": "TRANSITION",
                "status": "RESEARCH_ONLY_V2_CANDIDATE",
            }), encoding="utf-8")

            with patch("sys.argv", [
                "build_research_status.py",
                "--manifest", str(manifest),
                "--yinyang-v2", str(yy),
                "--output", str(out),
            ]):
                self.assertEqual(build_research_status.main(), 0)

            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertFalse(payload["yinyang_v2"]["available"])
            self.assertFalse(payload["yinyang_v2"]["date_aligned"])
            self.assertTrue(payload["yinyang_v2"]["stale_snapshot_present"])

    def test_aligned_yinyang_snapshot_is_available(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = root / "manifest.json"
            yy = root / "yy.json"
            out = root / "status.json"

            manifest.write_text(json.dumps({
                "latest_trade_date": "2026-09-18",
                "full_market": True,
            }), encoding="utf-8")
            yy.write_text(json.dumps({
                "trade_date": "2026-09-18",
                "yang_pct": 56.12,
                "yin_pct": 43.88,
                "position_tenths": 6,
                "signal": "GOLD",
                "state": "RECOVERY",
                "status": "RESEARCH_ONLY_V2_CANDIDATE",
            }), encoding="utf-8")

            with patch("sys.argv", [
                "build_research_status.py",
                "--manifest", str(manifest),
                "--yinyang-v2", str(yy),
                "--output", str(out),
            ]):
                self.assertEqual(build_research_status.main(), 0)

            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(payload["yinyang_v2"]["available"])
            self.assertTrue(payload["yinyang_v2"]["date_aligned"])
            self.assertFalse(payload["yinyang_v2"]["stale_snapshot_present"])


if __name__ == "__main__":
    unittest.main()
