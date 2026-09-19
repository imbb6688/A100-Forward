from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

HORIZONS = (1, 3, 5, 10, 20)


def stats_for(signal: str, merged: pd.DataFrame) -> dict:
    idx = merged.index[merged["v2_signal"] == signal].tolist()
    events = []
    for i in idx:
        row = {"date": str(pd.Timestamp(merged.at[i, "date"]).date())}
        for h in HORIZONS:
            if i + h < len(merged):
                row[f"fwd_{h}d"] = float(merged.at[i + h, "ew_index"] / merged.at[i, "ew_index"] - 1.0)
            else:
                row[f"fwd_{h}d"] = None
        events.append(row)
    out = {"count": len(events), "events": events}
    for h in HORIZONS:
        vals = [e[f"fwd_{h}d"] for e in events if e[f"fwd_{h}d"] is not None]
        a = np.asarray(vals, dtype=float)
        out[f"{h}d"] = {"n": int(len(a))}
        if len(a):
            out[f"{h}d"].update({
                "mean": float(a.mean()),
                "median": float(np.median(a)),
                "positive_rate": float((a > 0).mean()),
                "negative_rate": float((a < 0).mean()),
                "min": float(a.min()),
                "max": float(a.max()),
            })
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Validate Yin-Yang v2 events on full market history")
    p.add_argument("--v1-history", required=True)
    p.add_argument("--v2-history", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()

    v1 = pd.read_csv(args.v1_history, parse_dates=["date"])
    v2 = pd.read_csv(args.v2_history, parse_dates=["date"])
    merged = v2.merge(v1[["date", "ew_index"]], on="date", how="inner", validate="one_to_one").sort_values("date").reset_index(drop=True)
    report = {
        "schema_version": "A100-YINYANG-V2-EVENT-VALIDATION-v1",
        "history_start": str(merged["date"].min().date()),
        "history_end": str(merged["date"].max().date()),
        "sessions": int(len(merged)),
        "gold": stats_for("GOLD", merged),
        "silver": stats_for("SILVER", merged),
        "bounce": stats_for("BOUNCE", merged),
        "interpretation": {
            "GOLD": "candidate risk-on confirmation event",
            "SILVER": "candidate deterioration/risk-off event",
            "BOUNCE": "candidate oversold rebound event without full confirmation",
        },
        "status": "RESEARCH_ONLY_NOT_PRODUCTION_VALIDATED",
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
