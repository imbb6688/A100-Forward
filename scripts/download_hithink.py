import os, json
from pathlib import Path
import requests
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

BASE="https://fuyao.aicubes.cn"
ENDPOINTS={
    "daily":"/api/dump/market-dumps/daily-k/download-url",
    "adj":"/api/dump/market-dumps/adjustment-factors/download-url",
}
OUT=Path("/mnt/data"); OUT.mkdir(parents=True,exist_ok=True)
KEY=os.environ.get("HITHINK_FINANCE_API_KEY")
if not KEY: raise SystemExit("HITHINK_FINANCE_API_KEY secret is missing")

def presigned(kind):
    r=requests.get(BASE+ENDPOINTS[kind],headers={"X-api-key":KEY},timeout=45)
    if r.status_code!=200:
        raise RuntimeError(f"{kind}: HTTP {r.status_code}: {r.text[:500]}")
    obj=r.json(); code=obj.get("code"); msg=obj.get("message",""); req=obj.get("request_id","")
    if code not in (0,"0",None):
        raise RuntimeError(f"{kind}: HiThink code={code}, message={msg!r}, request_id={req!r}")
    data=obj.get("data") or {}
    url=data.get("presigned_url") or data.get("download_url")
    if not url:
        raise RuntimeError(f"{kind}: no data.presigned_url; code={code}, message={msg!r}, request_id={req!r}, data_keys={list(data)[:20]}")
    return url

def fetch(kind,dest):
    url=presigned(kind); tmp=dest.with_suffix(dest.suffix+".part")
    if tmp.exists(): tmp.unlink()
    with requests.get(url,stream=True,timeout=(30,600)) as r:
        if r.status_code==403: raise RuntimeError(f"{kind}: presigned URL HTTP 403; re-run workflow")
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_content(1024*1024):
                if chunk: f.write(chunk)
    if tmp.stat().st_size<1024: raise RuntimeError(f"{kind}: implausibly small file")
    tmp.replace(dest)
    return dest.stat().st_size

raw=OUT/"hithink_daily_raw.parquet"
daily=OUT/"A100_2020_2026_raw.parquet"
adj=OUT/"A100_adjustment_factors.parquet"

print("Downloading HiThink daily dump...",flush=True); rb=fetch("daily",raw)
print("Downloading HiThink adjustment dump...",flush=True); ab=fetch("adj",adj)

pf=pq.ParquetFile(raw)
req={"thscode","date_ms","open_price","high_price","low_price","close_price","volume","turnover"}
miss=req-set(pf.schema.names)
if miss: raise RuntimeError(f"daily dump missing columns: {sorted(miss)}")
if pf.metadata.num_rows<7_000_000: raise RuntimeError(f"daily dump too small: {pf.metadata.num_rows}")

df=pq.read_table(raw).to_pandas()
df=df.rename(columns={
    "thscode":"ts_code","open_price":"open","high_price":"high","low_price":"low",
    "close_price":"close","turnover":"amount"
})
local=(pd.to_datetime(df["date_ms"],unit="ms",utc=True)
       .dt.tz_convert("Asia/Shanghai").dt.tz_localize(None).dt.normalize())
df["trade_date"]=(local.astype("int64")//1000).astype("int64")

cut=np.int64(pd.Timestamp("2020-01-01").value//1000)
df=df[df["trade_date"]>=cut].copy()
df=(df.sort_values(["ts_code","trade_date"],kind="mergesort")
      .drop_duplicates(["ts_code","trade_date"],keep="last").reset_index(drop=True))
df["pre_close"]=df.groupby("ts_code",sort=False)["close"].shift(1)

bad=((df["high"]<df[["open","close","low"]].max(axis=1)) |
     (df["low"]>df[["open","close","high"]].min(axis=1)))
if bool(bad.fillna(False).any()): raise RuntimeError(f"bad OHLC rows={int(bad.sum())}")

keep=[c for c in ["ts_code","currency","interval","adjusted","date_ms","open","high","low","close","volume","amount","trade_date","pre_close"] if c in df.columns]
df=df[keep]
pq.write_table(pa.Table.from_pandas(df,preserve_index=False),daily,compression="snappy",row_group_size=1_000_000)

latest_us=int(df["trade_date"].max())
latest=pd.to_datetime(latest_us,unit="us").strftime("%Y-%m-%d")
nlatest=int((df["trade_date"]==latest_us).sum())
manifest={
    "schema_version":"A100-HITHINK-NORMALIZED-v1",
    "latest_trade_date":latest,
    "latest_trade_date_us":latest_us,
    "latest_rows":nlatest,
    "rows":int(len(df)),
    "symbols":int(df["ts_code"].nunique()),
    "raw_daily_bytes":int(rb),
    "normalized_daily_bytes":int(daily.stat().st_size),
    "adjustment_bytes":int(ab),
    "price_basis":"unadjusted (matches frozen V7 research contract)"
}
(OUT/"hithink_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(manifest,ensure_ascii=False,indent=2),flush=True)
if nlatest<4500: raise SystemExit(f"FAIL CLOSED: latest trading day has only {nlatest} rows (<4500)")
