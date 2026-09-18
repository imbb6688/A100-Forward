import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from a100_iros.agentic_ai_inputs import build_market_proxy_payload, load_regime_config
from a100_iros.agentic_ai_regime import RegimeSignal, build_agentic_ai_regime


class TestAgenticAIInputs(unittest.TestCase):
    def setUp(self):
        self.config = load_regime_config("config/agentic_ai_regime.json")

    def _market_file(self, root: Path, latest: str = "2026-09-18") -> Path:
        dates = pd.bdate_range(end=latest, periods=80)
        themes = [row["ticker"] for rows in self.config["market_proxy_baskets"].values() for row in rows]
        tickers = themes + ["000698.SH", "000688.SH", "000300.SH"]
        drift = {"000698.SH": 0.0020, "000688.SH": 0.0010, "000300.SH": 0.0005}
        records = []
        for ticker_no, ticker in enumerate(tickers):
            daily = drift.get(ticker, 0.0012 + (ticker_no % 4) * 0.0001)
            for session_no, session in enumerate(dates):
                close = 100.0 * ((1.0 + daily) ** session_no)
                records.append({
                    "ts_code": ticker, "trade_date": session.value // 1000,
                    "open": close * 0.998, "high": close * 1.01, "low": close * 0.99,
                    "close": close, "volume": 1_000_000 + session_no,
                    "amount": 100_000_000 + session_no * 1000,
                })
        path = root / "daily.parquet"
        pd.DataFrame(records).to_parquet(path, index=False)
        return path

    @staticmethod
    def _manifest(latest: str = "2026-09-18"):
        return {
            "schema_version": "test-manifest-v1", "source": "synthetic-test",
            "full_market": True, "complete": True, "data_valid": True,
            "latest_trade_date": latest, "latest_rows": 23,
        }

    def test_builds_real_market_proxy_payload_without_faking_token_demand(self):
        with tempfile.TemporaryDirectory() as temporary:
            payload = build_market_proxy_payload(
                normalized_daily_path=self._market_file(Path(temporary)),
                manifest=self._manifest(), config=self.config, index_constituents={},
                today=date(2026, 9, 18),
            )
        buckets = {signal["bucket"] for signal in payload["signals"]}
        self.assertNotIn("token_demand", buckets)
        self.assertEqual(len(buckets), 5)
        self.assertEqual(payload["quality"]["missing_buckets"], ["token_demand"])
        snapshot = build_agentic_ai_regime(
            [RegimeSignal(**row) for row in payload["signals"]],
            weights=self.config["weights"], as_of=payload["as_of"],
        )
        self.assertEqual(snapshot.coverage, 0.85)
        self.assertNotEqual(snapshot.state.value, "INSUFFICIENT_DATA")

    def test_rejects_stale_market_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "stale or future-dated"):
                build_market_proxy_payload(
                    normalized_daily_path=self._market_file(Path(temporary)),
                    manifest=self._manifest(), config=self.config, index_constituents={},
                    today=date(2026, 9, 25),
                )

    def test_rejects_future_dated_market_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "stale or future-dated"):
                build_market_proxy_payload(
                    normalized_daily_path=self._market_file(Path(temporary)),
                    manifest=self._manifest(), config=self.config, index_constituents={},
                    today=date(2026, 9, 17),
                )

    def test_rejects_invalid_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self._manifest()
            manifest["complete"] = False
            with self.assertRaisesRegex(ValueError, "not complete"):
                build_market_proxy_payload(
                    normalized_daily_path=self._market_file(Path(temporary)),
                    manifest=manifest, config=self.config, index_constituents={},
                    today=date(2026, 9, 18),
                )

    def test_config_has_no_duplicate_proxy_members(self):
        members = [row["ticker"] for rows in self.config["market_proxy_baskets"].values() for row in rows]
        self.assertEqual(len(members), len(set(members)))
        self.assertEqual(json.loads(Path("config/agentic_ai_regime.json").read_text())["schema_version"],
                         "A100-Agentic-AI-Regime-v2")


if __name__ == "__main__":
    unittest.main()
