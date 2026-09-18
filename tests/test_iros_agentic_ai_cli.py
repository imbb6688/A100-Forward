import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from scripts.iros_agentic_ai_regime import _append_history_once, _validate_input
from a100_iros.agentic_ai_inputs import load_regime_config


class TestAgenticAIRegimeCLI(unittest.TestCase):
    def _payload(self, as_of: str):
        config = load_regime_config("config/agentic_ai_regime.json")
        return config, {
            "schema_version": "A100-Agentic-AI-Regime-Input-v2",
            "as_of": as_of,
            "weights": config["weights"],
            "signals": [{
                "bucket": "domestic_compute", "score": 0.1, "confidence": 1.0,
                "source": "test", "observed_at": as_of,
            }],
            "quality": {"test": True},
            "provenance": {"source": "synthetic-test"},
        }

    def test_prebuilt_input_rejects_stale_date(self):
        stale = (date.today() - timedelta(days=10)).isoformat()
        config, payload = self._payload(stale)
        with self.assertRaisesRegex(ValueError, "stale or future-dated"):
            _validate_input(payload, config)

    def test_prebuilt_input_requires_governed_schema_and_provenance(self):
        config, payload = self._payload(date.today().isoformat())
        payload["schema_version"] = "unknown"
        with self.assertRaisesRegex(ValueError, "schema_version"):
            _validate_input(payload, config)
        payload["schema_version"] = "A100-Agentic-AI-Regime-Input-v2"
        payload["provenance"] = {}
        with self.assertRaisesRegex(ValueError, "provenance.source"):
            _validate_input(payload, config)

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
