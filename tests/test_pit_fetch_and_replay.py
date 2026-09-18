import unittest
import pandas as pd

from scripts.a100_fetch_pit_history import _intervals, _symbol, _title_transition
from scripts.a100_portfolio_replay import limit_pct, pit_at


class PitFetchReplayTests(unittest.TestCase):
    def test_symbol_normalization(self):
        self.assertEqual(_symbol("600519.SH"), "600519.SH")
        self.assertEqual(_symbol("000001"), "000001.SZ")

    def test_intervals_are_non_overlapping(self):
        raw = pd.DataFrame({"symbol": ["A", "A", "A"], "date": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"]), "is_st": [False, False, True]})
        out = _intervals(raw, "is_st", pd.Timestamp("2020-01-10"))
        self.assertEqual(out.effective_to.iloc[0], pd.Timestamp("2020-01-02"))
        self.assertTrue(out.is_st.iloc[1])

    def test_pit_lookup_and_st_limit(self):
        idx = {"A": [(pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-31"), True)]}
        self.assertTrue(pit_at(idx, "A", pd.Timestamp("2020-01-10")))
        self.assertEqual(limit_pct("600000.SH", pd.Timestamp("2020-01-10"), True), .05)

    def test_risk_warning_title_state_machine(self):
        self.assertTrue(_title_transition("关于公司股票被实施退市风险警示暨停牌的公告"))
        self.assertFalse(_title_transition("关于撤销其他风险警示暨停牌的公告"))
        self.assertTrue(_title_transition("关于撤销退市风险警示并继续实施其他风险警示暨停牌的公告"))
        self.assertIsNone(_title_transition("关于申请撤销其他风险警示的公告"))
        self.assertIsNone(_title_transition("关于可能被实施退市风险警示的提示性公告"))


if __name__ == "__main__":
    unittest.main()
