import unittest
import numpy as np, pandas as pd
from a100_iros.regime_research import stock_features,market_features

class TestRegimeResearch(unittest.TestCase):
    def panel(self):
        d=pd.date_range("2025-01-01",periods=140)
        rows=[]
        for j,s in enumerate(["000001.SZ","000002.SZ","600000.SH"]):
            c=np.linspace(10+j,20+j,140)
            for i,dt in enumerate(d):
                rows.append((s,dt,c[i],c[i]*1.01,c[i]*.99,c[i],1000+i))
        return pd.DataFrame(rows,columns=["symbol","date","open","high","low","close","volume"])
    def test_states_and_bounds(self):
        p=self.panel(); one=stock_features(p[p.symbol=="000001.SZ"])
        self.assertIn(one.rail_regime.iloc[-1],{"BULL","EXTENDED"})
        m=market_features(p); ready=m.score.dropna(); self.assertGreater(len(ready),0); self.assertTrue(ready.between(0,100).all()); self.assertTrue(m.score.iloc[:20].isna().any())
    def test_causal_prefix_invariance(self):
        p=self.panel(); one=p[p.symbol=="000001.SZ"].copy()
        a=stock_features(one.iloc[:100]); b=stock_features(one)
        pd.testing.assert_series_equal(a.rail_fast.reset_index(drop=True),b.rail_fast.iloc[:100].reset_index(drop=True),check_names=False)
if __name__=="__main__": unittest.main()
