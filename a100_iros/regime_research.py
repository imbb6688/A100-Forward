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
    # Experimental Dual Trend confirmation (independent A100 proxy).
    tf,ts=_ema(c,10),_ema(c,30)
    dual_score=(50*(tf>ts)+25*(_slope(tf)>0)+25*(_slope(ts)>0)).astype(float)
    # Experimental Capital Confirmation: OHLCV participation proxy, not institutional intent.
    ret1=c.pct_change()
    signed=np.sign(ret1.fillna(0))*np.log1p(v/vol20)
    cap5=signed.rolling(5,min_periods=5).mean(); cap20=signed.rolling(20,min_periods=20).mean()
    capital_score=(50*(cap5>0)+25*(cap5>cap20)+25*(v/vol20>1)).astype(float)
    x["atr20"]=atr; x["rail_score"]=rail_score; x["rail_regime"]=rail; x["gs_trigger"]=gs
    x["dual_trend_score"]=dual_score; x["dual_trend_confirm"]=(dual_score>=75)&(c>ts)
    x["capital_score"]=capital_score; x["capital_confirm"]=capital_score>=75
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


def industry_features(panel: pd.DataFrame, industry_col="industry") -> pd.DataFrame:
    """PIT cross-sectional industry regime; requires membership on each observation."""
    if industry_col not in panel.columns:
        return pd.DataFrame(columns=["date",industry_col,"industry_score","industry_regime"])
    p=panel.sort_values(["symbol","date"]).copy(); g=p.groupby("symbol",group_keys=False)
    p["r20"]=g["close"].pct_change(20)
    p["ma20"]=g["close"].transform(lambda s:s.rolling(20,min_periods=20).mean())
    p["above20"]=(p["close"]>p["ma20"]).astype(float); p["positive20"]=(p["r20"]>0).astype(float)
    d=p.groupby(["date",industry_col]).agg(breadth=("above20","mean"),positive20=("positive20","mean"),
        mom20=("r20","median"),members=("symbol","nunique")).reset_index()
    d["industry_score"]=(40*d.breadth+30*d.positive20+30*((d.mom20.clip(-.10,.10)+.10)/.20)).clip(0,100)
    d.loc[d.members<5,"industry_score"]=np.nan
    d["industry_regime"]=pd.cut(d.industry_score,[-1,35,55,70,101],
        labels=["WEAK","NEUTRAL","STRONG","LEADING"]).astype("string")
    return d

def ablation_matrix(z: pd.DataFrame) -> pd.DataFrame:
    """Incremental filters; exposes marginal value and signal attrition."""
    gs=z.gs_trigger.isin(["EARLY_ENTRY","TREND_ENTRY","REENTRY"])
    market=z.market_regime.isin(["RECOVERY","RISK_ON","STRONG"])
    rail=z.rail_regime.isin(["RECOVERY","BULL"])
    steps=[("GS",gs),("+Market",gs&market)]
    current=gs&market
    if "industry_regime" in z.columns:
        current=current&z.industry_regime.isin(["NEUTRAL","STRONG","LEADING"])
        steps.append(("+Industry",current))
    current=current&rail; steps.append(("+Rail",current))
    current=current&z.dual_trend_confirm; steps.append(("+DualTrend",current))
    current=current&z.capital_confirm; steps.append(("+Capital",current))
    rows=[]
    for name,mask in steps:
        q=z[mask & z.fwd_20d.notna()]
        rows.append({"model":name,"n":len(q),"mean_5d":q.fwd_5d.mean(),"mean_10d":q.fwd_10d.mean(),
            "mean_20d":q.fwd_20d.mean(),"hit20":(q.fwd_20d>0).mean() if len(q) else np.nan})
    return pd.DataFrame(rows)
