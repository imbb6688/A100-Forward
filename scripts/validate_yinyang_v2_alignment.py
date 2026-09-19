from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> int:
    p = argparse.ArgumentParser(description="Validate Yin-Yang v2 against vendor-labeled sample")
    p.add_argument("--series", required=True)
    p.add_argument("--labels", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()

    s = pd.read_csv(args.series)
    s["date"] = s["date"].astype(str).str[:10]
    labels = pd.DataFrame(json.loads(Path(args.labels).read_text(encoding="utf-8"))["labels"])
    m = labels.merge(s, on="date", how="left", validate="one_to_one")
    if m["v2_yang_pct"].isna().any():
        raise ValueError("v2 series missing labeled dates")

    vendor_signal = m["signal"].fillna("NONE").astype(str)
    pred_signal = m["v2_signal"].fillna("NONE").astype(str)
    signal_accuracy = float((vendor_signal == pred_signal).mean())

    y = m["yang_pct"].astype(float).to_numpy()
    yp = m["v2_yang_pct"].astype(float).to_numpy()
    mae = float(np.abs(y - yp).mean())
    rmse = float(np.sqrt(np.square(y - yp).mean()))
    corr = float(np.corrcoef(y, yp)[0, 1])

    pos = m["position_tenths"].astype(float).to_numpy()
    pp = m["v2_position_tenths"].astype(float).to_numpy()
    pos_mae = float(np.abs(pos - pp).mean())
    exact_pos = float((pos == pp).mean())

    rows = []
    for r in m.itertuples():
        vs = "NONE" if pd.isna(r.signal) else str(r.signal)
        ps = str(r.v2_signal)
        rows.append({
            "date": str(r.date),
            "vendor_yang": float(r.yang_pct),
            "v2_yang": round(float(r.v2_yang_pct), 2),
            "vendor_position": int(r.position_tenths),
            "v2_position": int(r.v2_position_tenths),
            "vendor_signal": vs,
            "v2_signal": ps,
            "signal_match": bool(vs == ps),
        })

    report = {
        "schema_version": "A100-YINYANG-V2-ALIGNMENT-v1",
        "sample_start": str(m["date"].min()),
        "sample_end": str(m["date"].max()),
        "n": int(len(m)),
        "yang": {
            "correlation": corr,
            "mae_percentage_points": mae,
            "rmse_percentage_points": rmse,
        },
        "position": {
            "mae_tenths": pos_mae,
            "exact_match_rate": exact_pos,
        },
        "signal": {
            "accuracy": signal_accuracy,
            "matches": int((vendor_signal == pred_signal).sum()),
            "mismatches": int((vendor_signal != pred_signal).sum()),
        },
        "rows": rows,
        "status": "RESEARCH_ONLY_CALIBRATION",
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
