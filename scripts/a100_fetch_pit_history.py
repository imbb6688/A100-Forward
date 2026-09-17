from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import baostock as bs
import numpy as np
import pandas as pd
import requests


SW_URL = "https://www.swsresearch.com/swindex/pdf/SwClass2021/StockClassifyUse_stock.xls"


def _symbol(value: str) -> str:
    value = str(value).strip().upper().split(".")[0].zfill(6)
    suffix = "SH" if value.startswith(("5", "6", "9")) else "BJ" if value.startswith(("4", "8")) else "SZ"
    return f"{value}.{suffix}"


def _intervals(frame: pd.DataFrame, value: str, end: pd.Timestamp) -> pd.DataFrame:
    parts = []
    for symbol, group in frame.sort_values(["symbol", "date"]).groupby("symbol", sort=False):
        group = group.drop_duplicates("date", keep="last").reset_index(drop=True)
        changed = group[value].ne(group[value].shift()).cumsum()
        for _, run in group.groupby(changed):
            parts.append({"symbol": symbol, "effective_from": run.date.iloc[0], "effective_to": end, value: run[value].iloc[0]})
    out = pd.DataFrame(parts)
    out["effective_to"] = out.groupby("symbol")["effective_from"].shift(-1).sub(pd.Timedelta(days=1)).fillna(end)
    return out


def fetch_st(symbols: list[str], start: str, end: str) -> pd.DataFrame:
    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"BaoStock login failed: {login.error_code} {login.error_msg}")
    rows = []
    try:
        for n, symbol in enumerate(symbols, 1):
            code, market = symbol.split(".")
            if market == "BJ":
                continue
            rs = bs.query_history_k_data_plus(f"{market.lower()}.{code}", "date,isST", start_date=start, end_date=end, frequency="d", adjustflag="3")
            if rs.error_code != "0":
                raise RuntimeError(f"BaoStock {symbol}: {rs.error_code} {rs.error_msg}")
            while rs.next():
                date, flag = rs.get_row_data()
                rows.append((symbol, pd.Timestamp(date), flag == "1"))
            if n % 500 == 0:
                print(f"BaoStock ST: {n}/{len(symbols)}")
    finally:
        bs.logout()
    if not rows:
        raise RuntimeError("BaoStock returned no ST history")
    return _intervals(pd.DataFrame(rows, columns=["symbol", "date", "is_st"]), "is_st", pd.Timestamp(end))


def fetch_industry(symbols: set[str], end: str) -> pd.DataFrame:
    response = requests.get(SW_URL, timeout=120)
    response.raise_for_status()
    if response.content[:1] == b"<":
        raise RuntimeError("SWS industry download returned HTML")
    raw = pd.read_excel(io.BytesIO(response.content), dtype={"股票代码": str, "行业代码": str})
    raw = raw.rename(columns={"股票代码": "symbol", "计入日期": "date", "行业代码": "industry_code"})
    raw = raw[["symbol", "date", "industry_code"]].dropna()
    raw["symbol"] = raw.symbol.map(_symbol)
    raw["date"] = pd.to_datetime(raw.date).dt.normalize()
    raw["industry_code"] = raw.industry_code.astype(str).str.strip()
    raw = raw[raw.symbol.isin(symbols)]
    if raw.empty:
        raise RuntimeError("SWS returned no matching industry history")
    return _intervals(raw, "industry_code", pd.Timestamp(end))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/mnt/data"))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end")
    args = parser.parse_args()
    context = np.load(args.root / "A100_v5_results/A100_V5_context.npz", allow_pickle=False)
    symbols = sorted({_symbol(x) for x in context["symbols"].astype(str)})
    end = args.end or pd.to_datetime(context["unique_dates"].max(), unit="us").date().isoformat()
    out = args.root / "pit"
    out.mkdir(parents=True, exist_ok=True)
    datasets = {
        "st": (fetch_st(symbols, args.start, end), "st_risk_warning_history.parquet", "BaoStock daily isST"),
        "industry": (fetch_industry(set(symbols), end), "industry_membership_history.parquet", "SWS 2021 classification history"),
    }
    for kind, (frame, name, source) in datasets.items():
        frame.to_parquet(out / name, index=False)
        manifest = {"schema_version": 1, "kind": kind, "source_name": source, "rows": len(frame), "symbols": frame.symbol.nunique(), "min_effective_from": str(frame.effective_from.min().date()), "max_effective_to": str(frame.effective_to.max().date())}
        (out / f"{kind}_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
