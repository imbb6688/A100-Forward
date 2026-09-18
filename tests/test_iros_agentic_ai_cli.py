import json
import tempfile
import unittest
from pathlib import Path

from scripts.iros_agentic_ai_regime import _append_history_once


class TestAgenticAIRegimeCLI(unittest.TestCase):
    def test_history_deduplicates_same_observation_and_fingerprint(self):
        with tempfile.TemporaryDirectory() as temporary:
            history = Path(temporary) / "history.jsonl"
            snapshot = {"as_of": "2026-09-18", "input_fingerprint": "abc", "state": "NEUTRAL"}
            _append_history_once(history, snapshot)
            _append_history_once(history, snapshot)
            self.assertEqual(len(history.read_text(encoding="utf-8").splitlines()), 1)

    def test_history_preserves_revised_input_for_same_date(self):
        with tempfile.TemporaryDirectory() as temporary:
            history = Path(temporary) / "history.jsonl"
            _append_history_once(history, {"as_of": "2026-09-18", "input_fingerprint": "abc"})
            _append_history_once(history, {"as_of": "2026-09-18", "input_fingerprint": "def"})
            rows = [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["input_fingerprint"] for row in rows], ["abc", "def"])


if __name__ == "__main__":
    unittest.main()
