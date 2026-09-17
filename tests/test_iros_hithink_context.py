import unittest
from unittest.mock import Mock

from a100_iros.hithink_context import HiThinkContextClient


class HiThinkContextTests(unittest.TestCase):
    def test_context_contracts(self) -> None:
        session = Mock()
        responses = []
        payloads = [
            {"item": [{"thscode": "885001.TI", "name": "Industry A"}]},
            {"item": [{"thscode": "600519.SH", "name": "Example"}]},
            {"item": [{"thscode": "600519.SH", "reason": "test"}]},
            {"item": [{"thscode": "600519.SH", "reason": "dragon"}]},
            {"item": [{"thscode": "000001.SZ"}]},
        ]
        for data in payloads:
            r = Mock()
            r.raise_for_status.return_value = None
            r.json.return_value = {"code": 0, "data": data}
            responses.append(r)
        session.get.side_effect = responses

        client = HiThinkContextClient("x", session=session)
        catalog = client.index_catalog("industry")
        constituents = client.index_constituents("885001.TI")
        anomaly = client.anomaly_for_stocks(["600519.SH"])
        dragon = client.dragon_tiger(board_type="all", date="2026-09-17")
        pool = client.limit_pool("up")

        self.assertEqual(catalog[0]["name"], "Industry A")
        self.assertEqual(constituents[0]["thscode"], "600519.SH")
        self.assertEqual(anomaly["item"][0]["reason"], "test")
        self.assertEqual(dragon["item"][0]["reason"], "dragon")
        self.assertEqual(pool["item"][0]["thscode"], "000001.SZ")

        calls = session.get.call_args_list
        self.assertEqual(calls[0].kwargs["params"], {"tag": "industry"})
        self.assertEqual(calls[1].kwargs["params"], {"thscode": "885001.TI"})
        self.assertEqual(calls[2].kwargs["params"], {"thscodes": "600519.SH"})
        self.assertEqual(calls[3].kwargs["params"], {"board_type": "all", "date": "2026-09-17"})


if __name__ == "__main__":
    unittest.main()
