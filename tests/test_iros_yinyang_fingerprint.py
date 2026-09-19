import unittest

import numpy as np
import pandas as pd

from a100_iros.yinyang_fingerprint import MarketState, build_history, latest_snapshot


def synthetic_market(days=90, names=80, drift=0.002):
    dates = pd.bdate_range("2026-01-01", periods=days)
    rows = []
    for j in range(names):
        px = 10 + j * 0.01
        for i, dt in enumerate(dates):
            ret = drift + 0.002 * np.sin(i / 4 + j)
            pre = px
            px = max(1, px * (1 + ret))
            rows.append({
                "ts_code": f"{j:06d}.SZ",
                "trade_date": int(dt.value // 1000),
                "open": pre,
                "high": max(pre, px) * 1.002,
                "low": min(pre, px) * 0.998,
                "close": px,
                "volume": 1_000_000 + i * 100,
                "amount": (1_000_000 + i * 100) * px,
                "pre_close": pre,
            })
    return pd.DataFrame(rows)


class TestYinYangFingerprint(unittest.TestCase):
    def test_bullish_synthetic_market_scores_above_midpoint(self):
        df = synthetic_market(drift=0.003)
        snap = latest_snapshot(df)
        self.assertGreater(snap.score_0_100, 50)
        self.assertGreater(snap.yang_pct, snap.yin_pct)
        self.assertIn(snap.state, {MarketState.RECOVERY.value, MarketState.RISK_ON.value})

    def test_bearish_synthetic_market_scores_below_midpoint(self):
        df = synthetic_market(drift=-0.003)
        snap = latest_snapshot(df)
        self.assertLess(snap.score_0_100, 50)
        self.assertGreater(snap.yin_pct, snap.yang_pct)

    def test_history_contains_state_transition_fields(self):
        hist = build_history(synthetic_market())
        self.assertIn("silver_finger", hist.columns)
        self.assertIn("gold_finger", hist.columns)
        self.assertIn("state", hist.columns)
        self.assertGreater(len(hist), 20)

    def test_missing_required_column_fails_closed(self):
        df = synthetic_market().drop(columns=["amount"])
        with self.assertRaisesRegex(ValueError, "missing required columns"):
            latest_snapshot(df)


if __name__ == "__main__":
    unittest.main()
