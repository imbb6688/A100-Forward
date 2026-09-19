from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> int:
    p = argparse.ArgumentParser(description="Compare A100 Yin-Yang v1 with vendor-labeled calibration sample")
    p.add_argument("--history", required=True)
    p.add_argument("--labels", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()

    hist = pd.read_csv(args.history)
    hist["date"] = hist["date"].astype(str).str[:10]
    labels = json.loads(Path(args.labels).read_text(encoding="utf-8"))["labels"]
    lab = pd.DataFrame(labels)
    merged = lab.merge(hist, on="date", how="left", validate="one_to_one")
    if merged["score_0_100"].isna().any():
        missing = merged.loc[merged["score_0_100"].isna(), "date"].tolist()
        raise ValueError(f"missing A100 history for labeled dates: {missing}")

    y = merged["yang_pct"].astype(float).to_numpy()
    pscore = merged["score_0_100"].astype(float).to_numpy()
    corr = float(np.corrcoef(y, pscore)[0, 1])
    mae = float(np.abs(y - pscore).mean())
    rmse = float(np.sqrt(np.square(y - pscore).mean()))

    vendor_signal = merged["signal"].fillna("NONE").astype(str)
    a100_signal = np.where(merged["gold_finger"].astype(bool), "GOLD",
                   np.where(merged["silver_finger"].astype(bool), "SILVER", "NONE"))
    merged["a100_signal"] = a100_signal

    report = {
        "schema_version": "A100-YINYANG-VENDOR-ALIGNMENT-v1",
        "sample_start": str(merged["date"].min()),
        "sample_end": str(merged["date"].max()),
        "n": int(len(merged)),
        "yang_alignment": {"correlation": corr, "mae_percentage_points": mae, "rmse_percentage_points": rmse},
        "vendor_signal_dates": {
            name: merged.loc[vendor_signal == name, "date"].tolist()
            for name in sorted(set(vendor_signal) - {"NONE"})
        },
        "a100_signal_dates": {
            name: merged.loc[merged["a100_signal"] == name, "date"].tolist()
            for name in sorted(set(merged["a100_signal"]) - {"NONE"})
        },
        "mismatches": [
            {
                "date": str(r.date),
                "vendor_yang": float(r.yang_pct),
                "a100_score": float(r.score_0_100),
                "vendor_position_tenths": int(r.position_tenths),
                "vendor_signal": None if pd.isna(r.signal) else str(r.signal),
                "a100_signal": str(r.a100_signal),
            }
            for r in merged.itertuples()
            if (("NONE" if pd.isna(r.signal) else str(r.signal)) != str(r.a100_signal))
        ],
        "conclusion": "V1 is not vendor-aligned; do not use static score thresholds as Gold/Silver Finger semantics.",
        "status": "RESEARCH_ONLY"
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
