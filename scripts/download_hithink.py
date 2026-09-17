from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests

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

RAW_DAILY = OUT / "hithink_daily_raw.parquet"
NORMALIZED_DAILY = OUT / "A100_2020_2026_raw.parquet"
ADJ = OUT / "A100_adjustment_factors.parquet"
MANIFEST = OUT / "hithink_manifest.json"


def presigned(kind: str) -> str:
    response = requests.get(
        BASE + ENDPOINTS[kind],
        headers={"X-api-key": KEY},
        timeout=45,
    )
    if response.status_code != 200:
        raise RuntimeError(f"{kind}: HTTP {response.status_code}: {response.text[:500]}")
    payload = response.json()
    code = payload.get("code")
    if code not in (0, "0", None):
        raise RuntimeError(
            f"{kind}: HiThink code={code}, message={payload.get('message')!r}, request_id={payload.get('request_id')!r}"
        )
    data = payload.get("data") or {}
    url = data.get("presigned_url") or data.get("download_url")
    if not url:
        raise RuntimeError(
            f"{kind}: no download URL; data_keys={list(data)[:20]}, message={payload.get('message')!r}"
        )
    return str(url)


def valid_parquet(path: Path, min_bytes: int = 1024) -> bool:
    """Decode every record batch before promoting a downloaded object."""
    if not path.exists() or path.stat().st_size < min_bytes:
        return False
    try:
        pf = pq.ParquetFile(path)
        if pf.metadata is None or pf.metadata.num_rows <= 0:
            return False
        decoded_rows = 0
        for batch in pf.iter_batches(batch_size=65536):
            batch.validate(full=True)
            decoded_rows += batch.num_rows
        return decoded_rows == pf.metadata.num_rows
    except Exception:
        return False


def fetch(kind: str, dest: Path) -> int:
    tmp = dest.with_suffix(dest.suffix + ".part")
    last_error = None

    for attempt in range(1, 9):
        # A renewed signed URL may identify a newer dump. Never splice it onto
        # bytes fetched with a previous URL.
        tmp.unlink(missing_ok=True)
        try:
            url = presigned(kind)
            cmd = [
                "curl",
                "-L",
                "--fail",
                "--show-error",
                "--retry",
                "6",
                "--retry-delay",
                "5",
                "--retry-all-errors",
                "--connect-timeout",
                "30",
                "--max-time",
                "1800",
                "-C",
                "-",
                "-o",
                str(tmp),
                url,
            ]
            print(f"{kind}: curl attempt {attempt}; existing={tmp.stat().st_size if tmp.exists() else 0}", flush=True)
            completed = subprocess.run(
                cmd,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            if completed.returncode != 0:
                # A completed partial file can cause a range-related curl error on retry.
                # Accept it only if it is already a readable parquet file.
                if not valid_parquet(tmp):
                    raise RuntimeError(f"curl exited {completed.returncode}")
            if not valid_parquet(tmp):
                raise RuntimeError(f"{kind}: downloaded file is not a readable parquet")
            tmp.replace(dest)
            print(f"{kind}: completed {dest.stat().st_size} bytes", flush=True)
            return int(dest.stat().st_size)
        except Exception as exc:
            last_error = exc
            tmp.unlink(missing_ok=True)
            print(f"{kind}: attempt {attempt} failed ({type(exc).__name__})", flush=True)
            if attempt < 8:
                time.sleep(min(10 * attempt, 60))

    raise RuntimeError(
        f"{kind}: failed after retries ({type(last_error).__name__ if last_error else 'unknown'})"
    ) from None


def require_columns(pf: pq.ParquetFile, required: set[str], label: str) -> None:
    missing = required - set(pf.schema.names)
    if missing:
        raise RuntimeError(f"{label} missing columns: {sorted(missing)}")


def normalize_daily(raw: Path, dest: Path) -> tuple[pd.DataFrame, pq.ParquetFile]:
    pf = pq.ParquetFile(raw)
    require_columns(
        pf,
        {"thscode", "date_ms", "open_price", "high_price", "low_price", "close_price", "volume", "turnover"},
        "daily dump",
    )
    if pf.metadata.num_rows < 7_000_000:
        raise RuntimeError(f"daily dump too small: {pf.metadata.num_rows}")

    table = pq.read_table(raw)
    df = table.to_pandas()
    df = df.rename(
        columns={
            "thscode": "ts_code",
            "open_price": "open",
            "high_price": "high",
            "low_price": "low",
            "close_price": "close",
            "turnover": "amount",
        }
    )

    local_dates = (
        pd.to_datetime(df["date_ms"], unit="ms", utc=True)
        .dt.tz_convert("Asia/Shanghai")
        .dt.tz_localize(None)
        .dt.normalize()
    )
    df["trade_date"] = (local_dates.astype("int64") // 1000).astype("int64")
    cutoff = np.int64(pd.Timestamp("2020-01-01").value // 1000)
    df = df[df["trade_date"] >= cutoff].copy()

    df = (
        df.sort_values(["ts_code", "trade_date"], kind="mergesort")
        .drop_duplicates(["ts_code", "trade_date"], keep="last")
        .reset_index(drop=True)
    )
    df["pre_close"] = df.groupby("ts_code", sort=False)["close"].shift(1)

    bad_ohlc = (
        df["high"] < df[["open", "close", "low"]].max(axis=1)
    ) | (
        df["low"] > df[["open", "close", "high"]].min(axis=1)
    )
    if bool(bad_ohlc.fillna(False).any()):
        raise RuntimeError(f"bad OHLC rows={int(bad_ohlc.sum())}")

    ordered = [
        "ts_code",
        "currency",
        "interval",
        "adjusted",
        "date_ms",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "trade_date",
        "pre_close",
    ]
    df = df[[c for c in ordered if c in df.columns]]
    pq.write_table(
        pa.Table.from_pandas(df, preserve_index=False),
        dest,
        compression="snappy",
        row_group_size=1_000_000,
    )
    if not valid_parquet(dest):
        raise RuntimeError("normalized daily parquet validation failed")
    return df, pf


def build_manifest(df: pd.DataFrame, raw_bytes: int, adj_bytes: int) -> dict:
    if df.empty:
        raise RuntimeError("normalized market data is empty")
    latest_us = int(df["trade_date"].max())
    latest = pd.to_datetime(latest_us, unit="us").strftime("%Y-%m-%d")
    counts = df.groupby("trade_date", sort=True).size()
    latest_rows = int(counts.loc[latest_us])
    prior = counts[counts.index < latest_us].tail(20)
    recent_median = float(prior.median()) if len(prior) else float(latest_rows)
    completeness_ratio = float(latest_rows / recent_median) if recent_median > 0 else 0.0
    absolute_floor_ok = latest_rows >= 4500
    relative_ok = completeness_ratio >= 0.97
    full_market = bool(absolute_floor_ok and relative_ok)

    return {
        "schema_version": "A100-HITHINK-NORMALIZED-v3",
        "source": "HiThink Financial-API full-market daily-k + adjustment events",
        "latest_trade_date": latest,
        "latest_trade_date_us": latest_us,
        "latest_rows": latest_rows,
        "recent_20_session_median_rows": recent_median,
        "completeness_ratio": completeness_ratio,
        "absolute_floor_rows": 4500,
        "minimum_completeness_ratio": 0.97,
        "absolute_floor_ok": absolute_floor_ok,
        "relative_completeness_ok": relative_ok,
        "full_market": full_market,
        "complete": full_market,
        "data_valid": full_market,
        "rows": int(len(df)),
        "symbols": int(df["ts_code"].nunique()),
        "raw_daily_bytes": int(raw_bytes),
        "normalized_daily_bytes": int(NORMALIZED_DAILY.stat().st_size),
        "adjustment_bytes": int(adj_bytes),
        "price_basis": "unadjusted (matches frozen V7 research contract)",
    }


def main() -> None:
    print("Downloading HiThink daily dump...", flush=True)
    raw_bytes = fetch("daily", RAW_DAILY)
    print("Downloading HiThink adjustment dump...", flush=True)
    adj_bytes = fetch("adj", ADJ)

    # Confirm both provider dumps are readable before normalization.
    pq.ParquetFile(ADJ)
    df, _ = normalize_daily(RAW_DAILY, NORMALIZED_DAILY)
    manifest = build_manifest(df, raw_bytes, adj_bytes)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    for required in (RAW_DAILY, NORMALIZED_DAILY, ADJ, MANIFEST):
        if not required.exists() or required.stat().st_size == 0:
            raise RuntimeError(f"missing required output: {required}")

    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)
    if not manifest["full_market"]:
        raise SystemExit(
            "FAIL CLOSED: incomplete full-market session: "
            f"latest_rows={manifest['latest_rows']}, "
            f"recent_median={manifest['recent_20_session_median_rows']:.1f}, "
            f"completeness_ratio={manifest['completeness_ratio']:.4f}"
        )


if __name__ == "__main__":
    main()
