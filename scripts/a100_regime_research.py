"""Offline historical validation runner for A100 experimental regime layer."""
import argparse, json
from pathlib import Path
import pandas as pd
from a100_iros.regime_research import market_features,stock_features,forward_returns,industry_features,ablation_matrix,transition_matrix

def load(path):
    p=Path(path)
    x=pd.read_parquet(p) if p.suffix.lower() in {".parquet",".pq"} else pd.read_csv(p)
    aliases={"thscode":"symbol","ts_code":"symbol","trade_date":"date"}
    x=x.rename(columns={k:v for k,v in aliases.items() if k in x.columns})
    need={"symbol","date","open","high","low","close","volume"}
    miss=need-set(x.columns)
    if miss: raise ValueError(f"missing columns: {sorted(miss)}")
    # A100 canonical trade_date is integer microseconds; CSV/public inputs may be date strings.
    if pd.api.types.is_numeric_dtype(x["date"]):
        x["date"]=pd.to_datetime(x["date"],unit="us")
    else:
        x["date"]=pd.to_datetime(x["date"])
    return x.sort_values(["symbol","date"])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True); ap.add_argument("--out",default="research_results/regime_v1")
    ap.add_argument("--focus-start",default="2026-05-19"); ap.add_argument("--focus-end",default="2026-09-18")
    a=ap.parse_args(); out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    raw=load(a.input); m=market_features(raw)
    stocks=pd.concat([forward_returns(stock_features(g)) for _,g in raw.groupby("symbol",sort=False)],ignore_index=True)
    z=stocks.merge(m[["date","score","market_regime"]],on="date",how="left")
    ind=industry_features(raw)
    if not ind.empty:
        z=z.merge(ind[["date","industry","industry_score","industry_regime"]],on=["date","industry"],how="left")
        ind.to_csv(out/"industry_regime.csv",index=False)
    z.to_parquet(out/"regime_observations.parquet",index=False); m.to_csv(out/"market_regime.csv",index=False)
    ablation_matrix(z).to_csv(out/"ablation_matrix.csv",index=False)
    entry=z.gs_trigger.isin(["EARLY_ENTRY","TREND_ENTRY","REENTRY"]) & z.fwd_20d.notna()
    risk=z.loc[entry].groupby(["market_regime","rail_regime"],dropna=False).agg(
        n=("fwd_20d","size"),mean20=("fwd_20d","mean"),net20=("net_fwd_20d","mean"),
        mae20=("mae_20d","mean"),mfe20=("mfe_20d","mean"),
        stop_rate=("stop_hit_20d","mean")).reset_index()
    risk.to_csv(out/"risk_path_matrix.csv",index=False)
    transition_matrix(z).to_csv(out/"transition_matrix.csv",index=False)
    valid=z[z.fwd_20d.notna()]
    summary=valid.groupby(["market_regime","rail_regime","gs_trigger"],dropna=False).agg(
        n=("fwd_20d","size"),mean_5d=("fwd_5d","mean"),mean_20d=("fwd_20d","mean"),
        hit20=("fwd_20d",lambda s:(s>0).mean())).reset_index()
    summary.to_csv(out/"state_forward_returns.csv",index=False)
    focus=z[(z.date>=a.focus_start)&(z.date<=a.focus_end)]
    focus.groupby("date").agg(market_score=("score","first"),market_regime=("market_regime","first"),
        symbols=("symbol","nunique"),bull=("rail_regime",lambda s:(s=="BULL").mean()),
        early=("gs_trigger",lambda s:s.isin(["EARLY_ENTRY","TREND_ENTRY","REENTRY"]).mean())
        ).reset_index().to_csv(out/"focus_2026_0519_0918.csv",index=False)
    meta={"research_only":True,"frozen_v7_modified":False,"rows":len(z),"start":str(z.date.min()),"end":str(z.date.max())}
    (out/"manifest.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
if __name__=="__main__": main()
