import unittest
from unittest.mock import Mock

from a100_iros.hithink_fundamentals import (
    HiThinkFundamentalsClient,
    enrich_research_object_with_hithink_fundamentals,
)
from a100_iros.models import ResearchObject, SecurityResearchCard


class HiThinkFundamentalsTests(unittest.TestCase):
    def test_fetches_all_financial_modules_and_valuation(self) -> None:
        session = Mock()
        responses = []
        for i in range(5):
            response = Mock()
            response.raise_for_status.return_value = None
            if i < 4:
                response.json.return_value = {
                    "code": 0,
                    "data": {
                        "item": [
                            {
                                "thscode": "600519.SH",
                                "report_date_ms": 1700000000000 + i,
                                "period_end_ms": 1699999990000,
                            }
                        ]
                    },
                }
            else:
                response.json.return_value = {
                    "code": 0,
                    "data": {"item": [{"thscode": "600519.SH", "pe_ttm": 20.0}]},
                }
            responses.append(response)
        session.get.side_effect = responses

        client = HiThinkFundamentalsClient("x", session=session)
        bundle = client.financials("600519.sh", period="annual", limit=5)
        self.assertEqual(bundle.ticker, "600519.SH")
        self.assertEqual(len(bundle.income), 1)
        self.assertEqual(len(bundle.balance_sheet), 1)
        self.assertEqual(len(bundle.cash_flow), 1)
        self.assertEqual(len(bundle.indicators), 1)
        self.assertEqual(bundle.valuation["pe_ttm"], 20.0)
        self.assertEqual(session.get.call_count, 5)

        obj = ResearchObject(
            research_id="SEC-600519-TEST",
            security=SecurityResearchCard(ticker="600519.SH"),
        )
        enrich_research_object_with_hithink_fundamentals(obj, bundle)
        self.assertEqual(obj.security.fundamentals["source"], "HiThink Financial-API")
        self.assertEqual(obj.security.valuation["snapshot"]["pe_ttm"], 20.0)
        self.assertEqual(obj.security.fundamentals["latest_report_date_ms"], 1700000000003)
        self.assertTrue(obj.security.evidence)

    def test_rejects_mismatched_ticker(self) -> None:
        session = Mock()
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"code": 0, "data": {"item": []}}
        session.get.return_value = response
        client = HiThinkFundamentalsClient("x", session=session)
        bundle = client.financials("600519.SH")
        obj = ResearchObject(
            research_id="SEC-000001-TEST",
            security=SecurityResearchCard(ticker="000001.SZ"),
        )
        with self.assertRaises(ValueError):
            enrich_research_object_with_hithink_fundamentals(obj, bundle)


if __name__ == "__main__":
    unittest.main()
