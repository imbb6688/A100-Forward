import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from a100_iros.enrichment import (
    EnrichmentTarget,
    IROSEnrichmentOrchestrator,
    targets_from_frozen_signal,
    targets_from_watchlist,
)
from a100_iros.hithink_fundamentals import HiThinkFundamentalBundle
from a100_iros.repository import ResearchRepository


TARGET = "000001.SZ"


def make_daily(path: Path) -> None:
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    rows = []
    tickers = [TARGET] + [f"{i:06d}.SZ" for i in range(2, 1003)]
    for day in range(25):
        trade_us = int((start + timedelta(days=day)).timestamp() * 1_000_000)
        for i, ticker in enumerate(tickers):
            close = 10.0 + day * 0.03 + i * 0.0001
            rows.append(
                {
                    "ts_code": ticker,
                    "trade_date": trade_us,
                    "open": close - 0.02,
                    "high": close + 0.05,
                    "low": close - 0.05,
                    "close": close,
                    "volume": 100000 + i,
                    "amount": 1000000 + day * 1000 + i,
                }
            )
    pq.write_table(pa.Table.from_pandas(pd.DataFrame(rows), preserve_index=False), path)


class FakeFundamentals:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    def financials(self, ticker: str) -> HiThinkFundamentalBundle:
        self.calls.append(ticker)
        if self.fail:
            raise RuntimeError("fundamentals unavailable")
        return HiThinkFundamentalBundle(
            ticker=ticker,
            period="annual",
            indicator_report="2025-4",
            income=[{"thscode": ticker, "report_date_ms": 1, "revenue": 100}],
            balance_sheet=[{"thscode": ticker, "report_date_ms": 1, "assets": 200}],
            cash_flow=[{"thscode": ticker, "report_date_ms": 1, "operating_cash_flow": 30}],
            indicators={"thscode": ticker, "roe": 0.12},
            valuation={"thscode": ticker, "pe_ttm": 15.0},
        )


class FakeContext:
    def index_catalog(self, tag: str):
        return [{"thscode": "885001.TI", "name": "Banking"}]

    def index_constituents(self, thscode: str):
        return [{"thscode": TARGET, "name": "Ping An Bank"}]

    def anomaly_for_stocks(self, thscodes):
        return {"item": [{"thscode": thscodes[0], "reason": "test anomaly"}]}

    def dragon_tiger(self, *, board_type: str = "all", date=None):
        return {"item": [{"thscode": TARGET, "reason": "test board"}]}

    def limit_pool(self, kind: str):
        return {"item": [{"thscode": TARGET, "kind": kind}]} if kind == "up" else {"item": []}


class EnrichmentOrchestratorTests(unittest.TestCase):
    def make_orchestrator(self, root: Path, daily: Path, *, fail: bool = False, at: str = "2026-09-17T15:00:00+00:00"):
        return IROSEnrichmentOrchestrator(
            repository=ResearchRepository(root),
            normalized_daily_path=daily,
            fundamentals_client=FakeFundamentals(fail=fail),
            context_client=FakeContext(),
            clock=lambda: at,
        )

    def test_builds_persistent_security_research_file_and_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            daily = root / "daily.parquet"
            make_daily(daily)
            orchestrator = self.make_orchestrator(root / "iros", daily)
            summary = orchestrator.run(
                [
                    EnrichmentTarget(
                        ticker=TARGET,
                        company_name="Ping An Bank",
                        source="FROZEN_V7",
                        source_payload={"rank": 1},
                    )
                ]
            )

            self.assertEqual(summary["complete"], 1)
            self.assertEqual(summary["failed"], 0)
            result = summary["results"][0]
            self.assertEqual(result["status"], "COMPLETE")

            current = Path(result["security_file"])
            self.assertTrue(current.exists())
            payload = json.loads(current.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "A100-IROS-SECURITY-RESEARCH-FILE-v1")
            self.assertEqual(payload["research_object"]["state"], "RESEARCHING")
            self.assertEqual(payload["research_object"]["security"]["industry_context"]["industry_index"]["name"], "Banking")
            self.assertEqual(payload["research_object"]["security"]["valuation"]["snapshot"]["pe_ttm"], 15.0)
            self.assertEqual(len(payload["raw_context"]["events"]["anomaly"]), 1)
            self.assertTrue(payload["governance"]["research_only"])
            self.assertFalse(payload["governance"]["modifies_frozen_v7"])
            self.assertFalse(payload["governance"]["generates_orders"])
            self.assertTrue((root / "iros/objects/SEC-000001-SZ.json").exists())
            self.assertEqual(len(list((root / "iros/snapshots/SEC-000001-SZ").glob("*.json"))), 1)
            self.assertEqual(len(list((root / "iros/security_files/history/000001-SZ").glob("*.json"))), 1)

    def test_failed_refresh_does_not_replace_last_valid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            daily = root / "daily.parquet"
            make_daily(daily)
            iros_root = root / "iros"
            target = EnrichmentTarget(ticker=TARGET)
            first = self.make_orchestrator(iros_root, daily).run([target])
            current = Path(first["results"][0]["security_file"])
            before = current.read_text(encoding="utf-8")

            failed = self.make_orchestrator(
                iros_root,
                daily,
                fail=True,
                at="2026-09-17T16:00:00+00:00",
            ).run([target])
            self.assertEqual(failed["results"][0]["status"], "FAILED_NO_WRITE")
            self.assertEqual(current.read_text(encoding="utf-8"), before)
            self.assertEqual(len(list((iros_root / "snapshots/SEC-000001-SZ").glob("*.json"))), 1)

    def test_target_sources_are_normalized_and_deduplicated(self):
        signal_targets = targets_from_frozen_signal(
            {
                "latest_trade_date": "2026-09-17",
                "top2": [{"symbol": "000001.sz", "rank": 1}],
            }
        )
        watch_targets = targets_from_watchlist(
            [{"ticker": "000001.sz", "company_name": "Ping An Bank"}]
        )
        self.assertEqual(signal_targets[0].ticker, TARGET)
        self.assertEqual(signal_targets[0].source, "FROZEN_V7")
        self.assertEqual(watch_targets[0].ticker, TARGET)
        self.assertEqual(watch_targets[0].source, "WATCHLIST")


if __name__ == "__main__":
    unittest.main()
