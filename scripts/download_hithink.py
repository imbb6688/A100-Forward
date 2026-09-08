import os, json, requests
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

BASE = "https://fuyao.aicubes.cn"
ENDPOINTS = {
    "daily": "/api/dump/market-dumps/daily-k/download-url",
    "adj": "/api/dump/market-dumps/adjustment-factors/download-url",
}

OUT = Path("/mnt/data")
OUT.mkdir(parents=True, exist_ok=True)

KEY = os.environ.get("HITHINK_FINANCE_API_KEY")
if not KEY:
    raise SystemExit("HITHINK_FINANCE_API_KEY secret is missing")


def get_presigned_url(kind: str) -> str:
    """Call HiThink signing endpoint and return official data.presigned_url."""
    endpoint = BASE + ENDPOINTS[kind]
    r = requests.get(endpoint, headers={"X-api-key": KEY}, timeout=45)

    if r.status_code != 200:
        raise RuntimeError(
            f"{kind} signing failed: HTTP {r.status_code}; body={r.text[:500]}"
        )

    try:
        obj = r.json()
    except Exception:
        raise RuntimeError(
            f"{kind} signing returned non-JSON response: {r.text[:500]}"
        )

    code = obj.get("code")
    message = obj.get("message", "")
    request_id = obj.get("request_id", "")

    # HiThink official success code is 0.
    if code not in (0, "0", None):
        raise RuntimeError(
            f"{kind} HiThink API error: code={code}, message={message!r}, "
            f"request_id={request_id!r}"
        )

    data = obj.get("data") or {}
    url = data.get("presigned_url")

    # Backward/compatibility fallbacks, but official current field is presigned_url.
    if not url:
        url = (
            data.get("download_url")
            or obj.get("presigned_url")
            or obj.get("download_url")
            or obj.get("url")
        )

    if not url:
        safe_data_keys = list(data.keys())[:20] if isinstance(data, dict) else []
        raise RuntimeError(
            f"{kind} response has no presigned URL: code={code}, "
            f"message={message!r}, request_id={request_id!r}, "
            f"data_keys={safe_data_keys}"
        )

    return url


def signed_download(kind: str, dest: Path) -> int:
    url = get_presigned_url(kind)

    with requests.get(url, stream=True, timeout=(30, 300)) as d:
        if d.status_code == 403:
            raise RuntimeError(
                f"{kind} presigned URL returned HTTP 403; URL may have expired. "
                f"Re-run the workflow to request a fresh URL."
            )
        d.raise_for_status()

        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in d.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)
        tmp.replace(dest)

    return dest.stat().st_size


daily = OUT / "A100_2020_2026_raw.parquet"
adj = OUT / "A100_adjustment_factors.parquet"

print("Downloading HiThink full-market daily dump...")
print("daily bytes", signed_download("daily", daily))

print("Downloading HiThink adjustment-factor dump...")
print("adjustment bytes", signed_download("adj", adj))

# Normalize official dump schema to the legacy A100 schema.
T = pq.read_table(daily)
rename = {
    "thscode": "ts_code",
    "open_price": "open",
    "high_price": "high",
    "low_price": "low",
    "close_price": "close",
    "turnover": "amount",
}

cols, names = [], []
for name in T.column_names:
    names.append(rename.get(name, name))
    cols.append(T[name])
T = pa.table(cols, names=names)

if "trade_date" not in T.column_names:
    # HiThink documents date_ms as Asia/Shanghai midnight.
    # Convert explicitly to Asia/Shanghai to avoid previous-day UTC drift.
    ms = T["date_ms"].to_numpy(zero_copy_only=False)
    trade = (
        pd.to_datetime(ms, unit="ms", utc=True)
        .tz_convert("Asia/Shanghai")
        .strftime("%Y-%m-%d")
        .to_numpy(dtype="U10")
    )
    T = T.append_column("trade_date", pa.array(trade))

df = T.to_pandas()
df = df.sort_values(["ts_code", "trade_date"], kind="stable").reset_index(drop=True)

if "pre_close" not in df.columns:
    df["pre_close"] = df.groupby("ts_code", sort=False)["close"].shift(1)

# Preserve the historical A100 research window plus new forward dates.
df = df[df["trade_date"] >= "2020-01-01"].reset_index(drop=True)

pq.write_table(
    pa.Table.from_pandas(df, preserve_index=False),
    daily,
    compression="snappy",
)

latest = str(df["trade_date"].max())
nlatest = int((df["trade_date"] == latest).sum())

meta = {
    "latest_trade_date": latest,
    "latest_rows": nlatest,
    "rows": int(len(df)),
    "symbols": int(df["ts_code"].nunique()),
    "daily_bytes": int(daily.stat().st_size),
    "adjustment_bytes": int(adj.stat().st_size),
}

(OUT / "hithink_manifest.json").write_text(
    json.dumps(meta, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print(json.dumps(meta, ensure_ascii=False))

# Fail closed if the latest session is implausibly incomplete.
if nlatest < 4500:
    raise SystemExit(
        f"FAIL CLOSED: latest trading day has only {nlatest} rows (<4500)"
    )
