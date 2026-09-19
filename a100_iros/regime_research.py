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
    # GS trigger is intentionally orthogonal to Rail: momentum/price-volume events only.
    # This lets ablation measure Rail's independent contribution.
    mom_fast=_ema(c,5); mom_slow=_ema(c,13)
    cross_up=(mom_fast>mom_slow)&(mom_fast.shift()<=mom_slow.shift())
    cross_dn=(mom_fast<mom_slow)&(mom_fast.shift()>=mom_slow.shift())
    vol_ok=v>vol20
    gs=np.full(len(x),"NO_SETUP",object)
    gs[((ret20<0)&cross_up).fillna(False)]="REVERSAL_WATCH"
    gs[(cross_up&vol_ok).fillna(False)]="EARLY_ENTRY"
    gs[((ret20>0)&(c>c.shift())&vol_ok).fillna(False)]="TREND_ENTRY"
    pullback=(ret20>0)&(c<c.rolling(5,min_periods=5).max())&(c>c.shift())&vol_ok
    gs[pullback.fillna(False)]="REENTRY"
    gs[((ret20>0.20)&(v>1.5*vol20)).fillna(False)]="EXHAUSTION"
    gs[cross_dn.fillna(False)]="EXIT"
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

def forward_returns(df,horizons=(1,3,5,10,20)):
    """Forward close returns plus path-aware MAE/MFE and simple cost/stop research fields."""
    out=df.copy()
    c=out["close"].astype(float); h=out["high"].astype(float); l=out["low"].astype(float)
    for n in horizons:
        out[f"fwd_{n}d"]=c.shift(-n)/c-1
        future_l=pd.concat([l.shift(-k) for k in range(1,n+1)],axis=1).min(axis=1)
        future_h=pd.concat([h.shift(-k) for k in range(1,n+1)],axis=1).max(axis=1)
        out[f"mae_{n}d"]=future_l/c-1; out[f"mfe_{n}d"]=future_h/c-1
    # Conservative round-trip research cost: 20 bps; not a production execution model.
    out["net_fwd_20d"]=out["fwd_20d"]-0.002
    risk=1.5*out["atr20"]/c
    out["atr_stop_pct"]=-risk
    out["stop_hit_20d"]=out["mae_20d"]<=out["atr_stop_pct"]
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


def rail_transitions(z: pd.DataFrame) -> pd.DataFrame:
    """Label causal Rail state changes for transition-event studies."""
    x=z.sort_values(["symbol","date"]).copy()
    prev=x.groupby("symbol",sort=False)["rail_regime"].shift()
    x["rail_prev"]=prev
    x["rail_transition"]=prev.astype("string")+"->"+x["rail_regime"].astype("string")
    x.loc[prev.isna() | (prev==x["rail_regime"]),"rail_transition"]=pd.NA
    return x

def transition_matrix(z: pd.DataFrame) -> pd.DataFrame:
    """Event-study evidence for Market x Rail transition x GS context."""
    x=rail_transitions(z)
    event=x.rail_transition.notna() & x.fwd_20d.notna()
    q=x[event].copy()
    q["gs_entry"]=q.gs_trigger.isin(["EARLY_ENTRY","TREND_ENTRY","REENTRY"])
    group=["market_regime","rail_transition","gs_entry"]
    return q.groupby(group,dropna=False).agg(
        n=("fwd_20d","size"),
        mean_1d=("fwd_1d","mean"),mean_3d=("fwd_3d","mean"),mean_5d=("fwd_5d","mean"),
        mean_10d=("fwd_10d","mean"),mean_20d=("fwd_20d","mean"),
        hit20=("fwd_20d",lambda s:(s>0).mean()),
        mae20=("mae_20d","mean"),mfe20=("mfe_20d","mean"),
        stop_rate=("stop_hit_20d","mean")).reset_index()
