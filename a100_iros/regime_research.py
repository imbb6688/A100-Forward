"""Experimental A100 Regime/Rail/GS research layer.

Research-only: no production gate, ranker, position sizing, or Frozen V7 mutation.
All features are causal (rolling/ewm use current and prior bars only).
"""
from __future__ import annotations
import numpy as np
import pandas as pd

MARKET_LABELS=("RISK_OFF","DEFENSIVE","RECOVERY","RISK_ON","STRONG","OVERHEATED")
RAIL_LABELS=("BEAR","BOTTOMING","RECOVERY","BULL","EXTENDED","DISTRIBUTION")
GS_LABELS=("NO_SETUP","REVERSAL_WATCH","EARLY_ENTRY","TREND_ENTRY","REENTRY","EXHAUSTION","EXIT")

def _ema(s,n): return s.ewm(span=n,adjust=False,min_periods=n).mean()
def _slope(s,n=5): return s.pct_change(n)/float(n)

def stock_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute causal Adaptive Rail and GS proxy states for one symbol."""
    x=df.sort_values("date").copy()
    c=x["close"].astype(float); h=x["high"].astype(float); l=x["low"].astype(float)
    v=x["volume"].astype(float)
    fast,mid,slow=_ema(c,8),_ema(c,21),_ema(c,55)
    tr=pd.concat([(h-l),(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    atr=tr.rolling(20,min_periods=20).mean()
    vol20=v.rolling(20,min_periods=20).mean()
    ret20=c.pct_change(20)
    rail_score=(25*(c>fast)+25*(fast>mid)+25*(mid>slow)+25*(_slope(slow)>0)).astype(float)
    rail=np.full(len(x),"BEAR",object)
    bottom=(_slope(fast)>0)&(_slope(slow)<=0)
    recovery=(c>fast)&(fast>mid)&~((mid>slow)&(_slope(slow)>0))
    bull=(c>fast)&(fast>mid)&(mid>slow)&(_slope(slow)>0)
    extended=bull&((c-mid)/atr>2.5)
    distribution=((c<fast)&(_slope(fast)<0)&(mid>slow))
    rail[bottom.fillna(False)]="BOTTOMING"; rail[recovery.fillna(False)]="RECOVERY"
    rail[bull.fillna(False)]="BULL"; rail[extended.fillna(False)]="EXTENDED"
    rail[distribution.fillna(False)]="DISTRIBUTION"
    # GS is deliberately an A100 proxy, not a claim to reproduce proprietary THS GS.
    cross_up=(fast>mid)&(fast.shift()<=mid.shift())
    cross_dn=(fast<mid)&(fast.shift()>=mid.shift())
    vol_ok=v>vol20
    gs=np.full(len(x),"NO_SETUP",object)
    gs[(bottom&(ret20<0)).fillna(False)]="REVERSAL_WATCH"
    gs[(cross_up&(c>mid)&vol_ok).fillna(False)]="EARLY_ENTRY"
    gs[(bull&(c.shift()<=fast.shift())&(c>fast)).fillna(False)]="TREND_ENTRY"
    gs[(bull&(c>fast)&(c<fast+0.8*atr)&vol_ok).fillna(False)]="REENTRY"
    gs[extended.fillna(False)]="EXHAUSTION"
    gs[(cross_dn|((c<mid)&(_slope(mid)<0))).fillna(False)]="EXIT"
    x["rail_fast"]=fast; x["rail_mid"]=mid; x["rail_slow"]=slow
    x["atr20"]=atr; x["rail_score"]=rail_score; x["rail_regime"]=rail; x["gs_trigger"]=gs
    return x

def market_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional A-share market regime score, 0..100, by date."""
    p=panel.sort_values(["symbol","date"]).copy()
    g=p.groupby("symbol",group_keys=False)
    p["ma20"]=g["close"].transform(lambda s:s.rolling(20,min_periods=20).mean())
    p["ma60"]=g["close"].transform(lambda s:s.rolling(60,min_periods=60).mean())
    p["r20"]=g["close"].pct_change(20)
    p["r1"]=g["close"].pct_change()
    p["up"]=(p["r1"]>0).astype(float)
    p["above20"]=(p["close"]>p["ma20"]).astype(float)
    p["above60"]=(p["close"]>p["ma60"]).astype(float)
    d=p.groupby("date").agg(breadth20=("above20","mean"),breadth60=("above60","mean"),
        adv=("up","mean"),mom20=("r20","median"),dispersion=("r1","std"))
    d["score"]=(30*d.breadth20+25*d.breadth60+20*d.adv+
        20*((d.mom20.clip(-.10,.10)+.10)/.20)+5*(1-(d.dispersion.clip(0,.05)/.05))).clip(0,100)
    d["market_regime"]=pd.cut(d.score,[-1,20,40,55,70,85,101],labels=MARKET_LABELS).astype(str)
    return d.reset_index()

def forward_returns(df,horizons=(5,10,20)):
    out=df.copy()
    for h in horizons: out[f"fwd_{h}d"]=out["close"].shift(-h)/out["close"]-1
    return out
