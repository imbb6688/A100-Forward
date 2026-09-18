from __future__ import annotations

import argparse
import base64
import concurrent.futures
import html
import json
import math
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests


ANNOUNCEMENT_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
INDUSTRY_URL = "https://webapi.cninfo.com.cn/api/stock/p_stock2110"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.cninfo.com.cn/"}
ST_NAME = re.compile(r"^(?:\*?ST|S\*?ST)", re.IGNORECASE)


def _symbol(value: str) -> str:
    value = str(value).strip().upper().split(".")[0].zfill(6)
    suffix = "SH" if value.startswith(("5", "6", "9")) else "BJ" if value.startswith(("4", "8", "92")) else "SZ"
    return f"{value}.{suffix}"


def _intervals(
    frame: pd.DataFrame, value: str, start: pd.Timestamp, end: pd.Timestamp | None = None
) -> pd.DataFrame:
    if end is None:  # Backward-compatible helper form: _intervals(frame, value, end).
        end = start
        start = pd.Timestamp(frame.date.min())
    parts: list[dict] = []
    for symbol, group in frame.sort_values(["symbol", "date"]).groupby("symbol", sort=False):
        group = group.drop_duplicates("date", keep="last").reset_index(drop=True)
        prior = group[group.date <= start]
        after = group[group.date > start]
        if not prior.empty:
            after = pd.concat([pd.DataFrame({"symbol": [symbol], "date": [start], value: [prior.iloc[-1][value]]}), after])
        for _, row in after.iterrows():
            if row.date <= end:
                parts.append({"symbol": symbol, "effective_from": max(start, row.date), value: row[value]})
    out = pd.DataFrame(parts)
    if out.empty:
        return pd.DataFrame(columns=["symbol", "effective_from", "effective_to", value])
    out = out.drop_duplicates(["symbol", "effective_from"], keep="last")
    out = out[out[value].ne(out.groupby("symbol")[value].shift())].copy()
    out["effective_to"] = out.groupby("symbol")["effective_from"].shift(-1).sub(pd.Timedelta(days=1)).fillna(end)
    return out[["symbol", "effective_from", "effective_to", value]].sort_values(["symbol", "effective_from"]).reset_index(drop=True)


def _post_json(session: requests.Session, url: str, *, data=None, params=None, headers=None, attempts: int = 5) -> dict:
    error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = session.post(url, data=data, params=params, headers=headers, timeout=60)
            response.raise_for_status()
            payload = response.json()
            if payload.get("resultcode") not in (None, 200):
                raise RuntimeError(f"source resultcode={payload.get('resultcode')}: {payload.get('resultmsg')}")
            return payload
        except Exception as exc:
            error = exc
            time.sleep(min(2 ** attempt, 12))
    raise RuntimeError(f"source request failed after {attempts} attempts: {error}")


def _announcement_payload(page: int, start: str, end: str) -> dict[str, str]:
    return {
        "pageNum": str(page), "pageSize": "30", "column": "szse", "tabName": "fulltext",
        "plate": "", "stock": "", "searchkey": "风险警示", "secid": "", "category": "",
        "trade": "", "seDate": f"{start}~{end}", "sortName": "", "sortType": "", "isHLtitle": "true",
    }


def _next_session(day: pd.Timestamp, sessions: pd.DatetimeIndex) -> pd.Timestamp:
    position = int(sessions.searchsorted(day, side="right"))
    return sessions[position] if position < len(sessions) else day + pd.Timedelta(days=1)


def _clean_title(value: str) -> str:
    return re.sub(r"<[^>]+>", "", html.unescape(str(value))).replace(" ", "")


def _title_transition(title: str) -> bool | None:
    title = _clean_title(title)
    if "风险警示" not in title or any(word in title for word in ("申请", "可能", "提示性", "进展")):
        return None
    continues = any(word in title for word in ("继续实施", "继续被实施", "实施其他风险警示", "被实施其他风险警示"))
    if "撤销" in title and not continues:
        return False
    if continues or any(word in title for word in ("被实施", "叠加实施", "实施退市风险警示")):
        return True
    return None


def fetch_st(symbols: list[str], start: str, end: str, sessions: pd.DatetimeIndex, workers: int = 8) -> pd.DataFrame:
    first = _post_json(requests.Session(), ANNOUNCEMENT_URL, data=_announcement_payload(1, "2010-01-01", end), headers=HEADERS)
    total = int(first.get("totalAnnouncement", 0))
    pages = max(1, math.ceil(total / 30))

    def page(number: int) -> list[dict]:
        return _post_json(requests.Session(), ANNOUNCEMENT_URL, data=_announcement_payload(number, "2010-01-01", end), headers=HEADERS).get("announcements") or []

    announcements = list(first.get("announcements") or [])
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        for number, rows in zip(range(2, pages + 1), executor.map(page, range(2, pages + 1))):
            announcements.extend(rows)
            if number % 50 == 0:
                print(f"CNInfo ST announcements: {number}/{pages}")

    wanted = set(symbols)
    events: list[tuple[str, pd.Timestamp, bool, int]] = []
    for item in announcements:
        symbol = _symbol(item.get("secCode", ""))
        if symbol not in wanted:
            continue
        day = pd.to_datetime(item.get("announcementTime"), unit="ms", utc=True).tz_convert("Asia/Shanghai").tz_localize(None).normalize()
        observed = bool(ST_NAME.match(str(item.get("secName", "")).replace(" ", "")))
        events.append((symbol, day, observed, 0))
        transition = _title_transition(item.get("announcementTitle", ""))
        if transition is not None:
            events.append((symbol, _next_session(day, sessions), transition, 1))

    event_frame = pd.DataFrame(events, columns=["symbol", "date", "is_st", "priority"])
    if not event_frame.empty:
        event_frame = event_frame.sort_values(["symbol", "date", "priority"]).drop_duplicates(["symbol", "date"], keep="last")
    baseline = pd.DataFrame({"symbol": symbols, "date": pd.Timestamp(start), "is_st": False})
    first_observed = event_frame.sort_values("date").groupby("symbol", as_index=False).first() if not event_frame.empty else event_frame
    already_st = set(first_observed.loc[first_observed.is_st, "symbol"]) if not first_observed.empty else set()
    baseline.loc[baseline.symbol.isin(already_st), "is_st"] = True
    combined = pd.concat([baseline, event_frame[["symbol", "date", "is_st"]]], ignore_index=True)
    result = _intervals(combined, "is_st", pd.Timestamp(start), pd.Timestamp(end))
    if set(result.symbol) != wanted:
        raise RuntimeError(f"ST coverage incomplete: {len(set(result.symbol))}/{len(wanted)} symbols")
    return result


def _enckey() -> str:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad

    raw = pad(str(int(time.time())).encode(), 16)
    cipher = AES.new(b"1234567887654321", AES.MODE_CBC, iv=b"1234567887654321")
    return base64.b64encode(cipher.encrypt(raw)).decode()


def _industry_one(symbol: str, end: str) -> list[tuple[str, pd.Timestamp, str]]:
    code = symbol.split(".")[0]
    headers = {
        **HEADERS, "Accept": "*/*", "Accept-Enckey": _enckey(),
        "Origin": "https://webapi.cninfo.com.cn", "X-Requested-With": "XMLHttpRequest",
    }
    payload = _post_json(
        requests.Session(), INDUSTRY_URL,
        params={"scode": code, "sdate": "1990-01-01", "edate": end}, headers=headers,
    )
    rows = []
    for item in payload.get("records") or []:
        if item.get("F001V") not in {"008003", "008018"}:
            continue
        industry = str(item.get("F003V", "")).strip().upper()
        day = pd.to_datetime(item.get("VARYDATE"), errors="coerce")
        if pd.isna(day) or not re.fullmatch(r"S\d{6}", industry):
            continue
        rows.append((symbol, day.normalize(), industry[:3]))
    return rows


def fetch_industry(symbols: list[str], start: str, end: str, workers: int = 16) -> pd.DataFrame:
    rows: list[tuple[str, pd.Timestamp, str]] = []
    failures: list[str] = []

    def one(symbol: str):
        try:
            return symbol, _industry_one(symbol, end), None
        except Exception as exc:
            return symbol, [], str(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        for number, (symbol, found, error) in enumerate(executor.map(one, symbols), 1):
            rows.extend(found)
            if error or not found:
                failures.append(f"{symbol}: {error or 'no SW history'}")
            if number % 250 == 0:
                print(f"CNInfo SW industry: {number}/{len(symbols)}")
    if failures:
        sample = "; ".join(failures[:20])
        raise RuntimeError(f"industry coverage incomplete ({len(failures)} failures): {sample}")
    return _intervals(pd.DataFrame(rows, columns=["symbol", "date", "industry_code"]), "industry_code", pd.Timestamp(start), pd.Timestamp(end))


def _candidate_symbols(root: Path, symbols_file: Path | None = None) -> list[str]:
    path = symbols_file or root / "validation/walk_forward_candidate_universe.csv"
    if not path.exists():
        raise RuntimeError(f"candidate manifest missing: {path}")
    frame = pd.read_csv(path, dtype={"symbol": str})
    return sorted({_symbol(value) for value in frame.symbol})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/mnt/data"))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end")
    parser.add_argument("--kind", choices=("all", "st", "industry"), default="all")
    parser.add_argument("--symbols-file", type=Path)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--st-workers", type=int, default=8)
    parser.add_argument("--industry-workers", type=int, default=16)
    args = parser.parse_args()
    if not (0 <= args.shard_index < args.shard_count):
        raise ValueError("shard-index must be in [0, shard-count)")
    symbols = _candidate_symbols(args.root, args.symbols_file)
    symbols = symbols[args.shard_index :: args.shard_count]
    context_path = args.root / "A100_v5_results/A100_V5_context.npz"
    sessions = None
    if args.kind in {"all", "st"}:
        context = np.load(context_path, allow_pickle=False)
        sessions = pd.DatetimeIndex(pd.to_datetime(context["unique_dates"], unit="us")).normalize()
    end = args.end or (sessions.max().date().isoformat() if sessions is not None else pd.Timestamp.utcnow().date().isoformat())
    out = args.root / "pit"
    out.mkdir(parents=True, exist_ok=True)
    datasets = {}
    if args.kind in {"all", "st"}:
        datasets["st"] = (fetch_st(symbols, args.start, end, sessions, args.st_workers), "st_risk_warning_history.parquet", "CNInfo risk-warning announcements and historical security names")
    if args.kind in {"all", "industry"}:
        suffix = f".part-{args.shard_index:02d}-of-{args.shard_count:02d}" if args.shard_count > 1 else ""
        datasets["industry"] = (fetch_industry(symbols, args.start, end, args.industry_workers), f"industry_membership_history{suffix}.parquet", "CNInfo historical Shenwan classification (old and 2021 standards)")
    for kind, (frame, name, source) in datasets.items():
        frame.to_parquet(out / name, index=False)
        manifest = {
            "schema_version": 1, "kind": kind, "source_name": source, "rows": len(frame),
            "symbols": frame.symbol.nunique(), "candidate_symbols": len(symbols),
            "min_effective_from": str(frame.effective_from.min().date()), "max_effective_to": str(frame.effective_to.max().date()),
        }
        (out / f"{kind}_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
