import os
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from a100_runtime_checks import expected_session, require_session

BASE = "https://fuyao.aicubes.cn"
ENDPOINTS = {
    "daily": "/api/dump/market-dumps/daily-k/download-url",
    "adj": "/api/dump/market-dumps/adjustment-factors/download-url",
}


def presigned(kind, key):
    with requests.get(BASE + ENDPOINTS[kind],
                      headers={"X-api-key": key}, timeout=45) as response:
        if response.status_code != 200:
            raise RuntimeError(f"{kind}: signing HTTP {response.status_code}")
        obj = response.json()
    if obj.get("code") not in (0, "0", None):
        raise RuntimeError(f"{kind}: signing request rejected")
    data = obj.get("data") or {}
    url = data.get("presigned_url") or data.get("download_url")
    if not isinstance(url, str) or urlsplit(url).scheme != "https":
        raise RuntimeError(f"{kind}: missing HTTPS download URL")
    return url


def validate_parquet(path):
    parquet = pq.ParquetFile(path)
    try:
        if parquet.metadata.num_rows <= 0:
            raise RuntimeError("empty parquet")
        # Decode every row group, not just the footer, before accepting a download.
        for batch in parquet.iter_batches(batch_size=65536):
            batch.validate(full=True)
    finally:
        parquet.close()


def fetch(kind, dest, key, attempts=5):
    tmp = dest.with_suffix(dest.suffix + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, attempts + 1):
        try:
            url = presigned(kind, key)
            # Fresh requests restart the object: renewed URLs may refer to a newer dump.
            with requests.get(url, stream=True, timeout=(30, 600),
                              headers={"Accept-Encoding": "identity"}) as response:
                if response.status_code != 200:
                    raise RuntimeError(f"{kind}: download HTTP {response.status_code}")
                with tmp.open("wb") as stream:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            stream.write(chunk)
                length = response.headers.get("Content-Length")
                if length is not None and tmp.stat().st_size != int(length):
                    raise RuntimeError(f"{kind}: incomplete download")
            validate_parquet(tmp)
            tmp.replace(dest)
            return dest.stat().st_size
        except Exception as error:
            tmp.unlink(missing_ok=True)
            # Exception messages from HTTP clients can contain signed URLs or keys.
            print(f"{kind}: attempt {attempt}/{attempts} failed ({type(error).__name__})",
                  flush=True)
            if attempt == attempts:
                raise RuntimeError(f"{kind}: download failed after {attempts} attempts") from None
            time.sleep(min(5 * 2 ** (attempt - 1), 60))


def main():
    key = os.environ.get("HITHINK_FINANCE_API_KEY")
    if not key:
        raise SystemExit("HITHINK_FINANCE_API_KEY secret is missing")
    out = Path(os.environ.get("A100_DATA_DIR", "/mnt/data"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "hithink_manifest.json").unlink(missing_ok=True)
    required_date = expected_session()
    raw=out/"hithink_daily_raw.parquet"
    daily=out/"A100_2020_2026_raw.parquet"
    adj=out/"A100_adjustment_factors.parquet"
    
    print("Downloading HiThink daily dump...",flush=True); rb=fetch("daily",raw,key)
    print("Downloading HiThink adjustment dump...",flush=True); ab=fetch("adj",adj,key)
    
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
    df["trade_date"]=(local.astype("datetime64[ns]").astype("int64")//1000).astype("int64")
    
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
    require_session(latest, required_date)
    counts=df.groupby("trade_date",sort=True).size()
    nlatest=int(counts.loc[latest_us])
    
    prior=counts[counts.index<latest_us].tail(20)
    recent_median=float(prior.median()) if len(prior) else float(nlatest)
    completeness_ratio=float(nlatest/recent_median) if recent_median>0 else 0.0
    
    absolute_floor_ok=bool(nlatest>=4500)
    relative_completeness_ok=bool(completeness_ratio>=0.97)
    full_market=bool(absolute_floor_ok and relative_completeness_ok)
    
    manifest={
        "expected_trade_date":required_date,
        "schema_version":"A100-HITHINK-NORMALIZED-v2",
        "source":"HiThink Financial-API full-market daily-k + adjustment events",
        "latest_trade_date":latest,
        "latest_trade_date_us":latest_us,
        "latest_rows":nlatest,
        "recent_20_session_median_rows":recent_median,
        "completeness_ratio":completeness_ratio,
        "absolute_floor_rows":4500,
        "minimum_completeness_ratio":0.97,
        "absolute_floor_ok":absolute_floor_ok,
        "relative_completeness_ok":relative_completeness_ok,
        "full_market":full_market,
        "complete":full_market,
        "data_valid":full_market,
        "rows":int(len(df)),
        "symbols":int(df["ts_code"].nunique()),
        "raw_daily_bytes":int(rb),
        "normalized_daily_bytes":int(daily.stat().st_size),
        "adjustment_bytes":int(ab),
        "price_basis":"unadjusted (matches frozen V7 research contract)"
    }
    (out/"hithink_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(manifest,ensure_ascii=False,indent=2),flush=True)
    
    if not full_market:
        raise SystemExit(
            "FAIL CLOSED: incomplete full-market session: "
            f"latest_rows={nlatest}, recent_median={recent_median:.1f}, "
            f"completeness_ratio={completeness_ratio:.4f}"
        )


if __name__ == "__main__":
    main()
