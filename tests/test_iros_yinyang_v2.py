import unittest

import pandas as pd

from a100_iros.yinyang_v2 import build_v2


class TestYinYangV2(unittest.TestCase):
    def test_transition_semantics(self):
        rows = [
            {"date":"2026-09-01","score_0_100":60.48,"breadth_score":62.4,"trend_score":61.3,"momentum_score":52.3,"liquidity_score":48.3,"leadership_score":100.0,"ew_return_1d":0.0048},
            {"date":"2026-09-02","score_0_100":45.84,"breadth_score":27.85,"trend_score":56.89,"momentum_score":46.2,"liquidity_score":42.9,"leadership_score":67.9,"ew_return_1d":-0.0066},
            {"date":"2026-09-03","score_0_100":45.75,"breadth_score":33.64,"trend_score":53.15,"momentum_score":47.3,"liquidity_score":40.6,"leadership_score":61.4,"ew_return_1d":-0.0043},
            {"date":"2026-09-04","score_0_100":46.59,"breadth_score":45.43,"trend_score":53.06,"momentum_score":49.3,"liquidity_score":46.9,"leadership_score":27.8,"ew_return_1d":-0.0030},
            {"date":"2026-09-07","score_0_100":55.13,"breadth_score":59.31,"trend_score":55.71,"momentum_score":51.3,"liquidity_score":41.4,"leadership_score":76.1,"ew_return_1d":0.0093},
            {"date":"2026-09-08","score_0_100":59.41,"breadth_score":62.79,"trend_score":59.76,"momentum_score":52.1,"liquidity_score":42.1,"leadership_score":100.0,"ew_return_1d":0.0066},
            {"date":"2026-09-09","score_0_100":46.14,"breadth_score":32.38,"trend_score":56.63,"momentum_score":47.3,"liquidity_score":39.5,"leadership_score":62.4,"ew_return_1d":-0.0047},
            {"date":"2026-09-10","score_0_100":33.42,"breadth_score":17.04,"trend_score":48.68,"momentum_score":44.0,"liquidity_score":36.6,"leadership_score":0.0,"ew_return_1d":-0.0136},
            {"date":"2026-09-11","score_0_100":29.96,"breadth_score":11.49,"trend_score":35.22,"momentum_score":41.1,"liquidity_score":44.6,"leadership_score":0.0,"ew_return_1d":-0.0200},
            {"date":"2026-09-14","score_0_100":47.43,"breadth_score":58.59,"trend_score":37.54,"momentum_score":51.1,"liquidity_score":35.3,"leadership_score":46.9,"ew_return_1d":0.0052},
            {"date":"2026-09-15","score_0_100":29.95,"breadth_score":19.78,"trend_score":28.99,"momentum_score":44.0,"liquidity_score":35.3,"leadership_score":0.0,"ew_return_1d":-0.0137},
            {"date":"2026-09-16","score_0_100":52.62,"breadth_score":78.11,"trend_score":35.33,"momentum_score":53.9,"liquidity_score":37.6,"leadership_score":41.7,"ew_return_1d":0.0141},
            {"date":"2026-09-17","score_0_100":45.12,"breadth_score":47.66,"trend_score":35.83,"momentum_score":49.7,"liquidity_score":36.8,"leadership_score":50.4,"ew_return_1d":0.0012},
            {"date":"2026-09-18","score_0_100":60.14,"breadth_score":79.08,"trend_score":43.89,"momentum_score":54.3,"liquidity_score":42.4,"leadership_score":88.4,"ew_return_1d":0.0156},
        ]
        v2 = build_v2(pd.DataFrame(rows)).set_index(v2_date := "date")
        self.assertEqual(v2.loc[pd.Timestamp("2026-09-03"), "v2_signal"], "SILVER")
        self.assertEqual(v2.loc[pd.Timestamp("2026-09-08"), "v2_signal"], "GOLD")
        self.assertEqual(v2.loc[pd.Timestamp("2026-09-10"), "v2_signal"], "SILVER")
        self.assertEqual(v2.loc[pd.Timestamp("2026-09-11"), "v2_signal"], "NONE")
        self.assertEqual(v2.loc[pd.Timestamp("2026-09-16"), "v2_signal"], "BOUNCE")
        self.assertEqual(v2.loc[pd.Timestamp("2026-09-18"), "v2_signal"], "GOLD")


if __name__ == "__main__":
    unittest.main()
