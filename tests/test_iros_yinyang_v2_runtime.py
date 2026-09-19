import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from scripts import validate_yinyang_v2_runtime as runtime


class TestYinYangV2Runtime(unittest.TestCase):
    def _write_case(self, root: Path, *, trade_date="2026-09-18", status="RESEARCH_ONLY_V2_CANDIDATE"):
        manifest = root / "manifest.json"
        latest = root / "latest.json"
        history = root / "history.csv"
        manifest.write_text(json.dumps({"latest_trade_date": trade_date}), encoding="utf-8")
        latest.write_text(json.dumps({
            "trade_date": trade_date,
            "yang_pct": 56.12,
            "yin_pct": 43.88,
            "position_tenths": 6,
            "signal": "GOLD",
            "state": "RECOVERY",
            "status": status,
        }), encoding="utf-8")
        pd.DataFrame([{
            "date": trade_date,
            "v2_yang_pct": 56.12,
            "v2_yin_pct": 43.88,
            "v2_position_tenths": 6,
            "v2_signal": "GOLD",
            "v2_state": "RECOVERY",
        }]).to_csv(history, index=False)
        return manifest, latest, history

    def test_valid_runtime_contract(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, latest, history = self._write_case(Path(td))
            with patch("sys.argv", [
                "validate_yinyang_v2_runtime.py",
                "--manifest", str(manifest),
                "--latest", str(latest),
                "--history", str(history),
            ]):
                self.assertEqual(runtime.main(), 0)

    def test_rejects_date_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest, latest, history = self._write_case(root)
            manifest.write_text(json.dumps({"latest_trade_date": "2026-09-17"}), encoding="utf-8")
            with patch("sys.argv", [
                "validate_yinyang_v2_runtime.py",
                "--manifest", str(manifest),
                "--latest", str(latest),
                "--history", str(history),
            ]):
                with self.assertRaisesRegex(ValueError, "date mismatch"):
                    runtime.main()

    def test_rejects_non_research_status(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, latest, history = self._write_case(Path(td), status="PRODUCTION")
            with patch("sys.argv", [
                "validate_yinyang_v2_runtime.py",
                "--manifest", str(manifest),
                "--latest", str(latest),
                "--history", str(history),
            ]):
                with self.assertRaisesRegex(ValueError, "research-only"):
                    runtime.main()


if __name__ == "__main__":
    unittest.main()
