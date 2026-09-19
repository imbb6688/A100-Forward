from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

HORIZONS = (1, 3, 5, 10, 20)


def _event_stats(hist: pd.DataFrame, signal_col: str) -> dict:
    events = hist.index[hist[signal_col].fillna(False)].tolist()
    rows = []
    for i in events:
        row = {"date": str(pd.Timestamp(hist.at[i, "date"]).date()), "score": float(hist.at[i, "score_0_100"])}
        for h in HORIZONS:
            if i + h < len(hist):
                r = float(hist.at[i + h, "ew_index"] / hist.at[i, "ew_index"] - 1.0)
                row[f"fwd_{h}d"] = r
            else:
                row[f"fwd_{h}d"] = None
        rows.append(row)

    summary = {"count": len(rows), "events": rows}
    for h in HORIZONS:
        vals = [r[f"fwd_{h}d"] for r in rows if r[f"fwd_{h}d"] is not None]
        if vals:
            a = np.asarray(vals, dtype=float)
            summary[f"{h}d"] = {
                "mean": float(a.mean()),
                "median": float(np.median(a)),
                "positive_rate": float((a > 0).mean()),
                "min": float(a.min()),
                "max": float(a.max()),
                "n": int(len(a)),
            }
        else:
            summary[f"{h}d"] = {"n": 0}
    return summary


def _window_summary(hist: pd.DataFrame, start: str, end: str) -> dict:
    d = hist[(hist["date"] >= pd.Timestamp(start)) & (hist["date"] <= pd.Timestamp(end))].copy()
    if d.empty:
        return {"start": start, "end": end, "rows": 0}
    transitions = int((d["state"] != d["state"].shift(1)).sum() - 1)
    return {
        "start": start,
        "end": end,
        "rows": int(len(d)),
        "score_start": float(d.iloc[0]["score_0_100"]),
        "score_end": float(d.iloc[-1]["score_0_100"]),
        "score_min": float(d["score_0_100"].min()),
        "score_max": float(d["score_0_100"].max()),
        "state_counts": {str(k): int(v) for k, v in d["state"].value_counts().to_dict().items()},
        "state_transitions": max(transitions, 0),
        "silver_dates": [str(pd.Timestamp(x).date()) for x in d.loc[d["silver_finger"], "date"]],
        "gold_dates": [str(pd.Timestamp(x).date()) for x in d.loc[d["gold_finger"], "date"]],
        "latest_20": [
            {
                "date": str(pd.Timestamp(r.date).date()),
                "score": round(float(r.score_0_100), 2),
                "state": str(r.state),
                "silver": bool(r.silver_finger),
                "gold": bool(r.gold_finger),
                "yin": round(100.0 - float(r.score_0_100), 2),
                "yang": round(float(r.score_0_100), 2),
            }
            for r in d.tail(20).itertuples()
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Validate A100 Yin-Yang Gold/Silver Finger history")
    p.add_argument("--history", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--window-start", default="2026-05-19")
    p.add_argument("--window-end", default="2026-09-18")
    args = p.parse_args()

    hist = pd.read_csv(args.history, parse_dates=["date"])
    required = {"date", "score_0_100", "state", "silver_finger", "gold_finger", "ew_index"}
    missing = required - set(hist.columns)
    if missing:
        raise ValueError(f"history missing columns: {sorted(missing)}")

    report = {
        "schema_version": "A100-YINYANG-VALIDATION-v1",
        "history_start": str(hist["date"].min().date()),
        "history_end": str(hist["date"].max().date()),
        "sessions": int(len(hist)),
        "silver": _event_stats(hist, "silver_finger"),
        "gold": _event_stats(hist, "gold_finger"),
        "drought_window": _window_summary(hist, args.window_start, args.window_end),
        "status": "RESEARCH_ONLY_UNVALIDATED",
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
