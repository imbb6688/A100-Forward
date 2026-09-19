from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from a100_iros.yinyang_fingerprint import build_history, latest_snapshot


def main() -> int:
    p = argparse.ArgumentParser(description="A100 Yin-Yang Spectrum + Gold/Silver Finger v1")
    p.add_argument("--daily", required=True)
    p.add_argument("--output", default="/mnt/data/state/iros-regime/yinyang/latest.json")
    p.add_argument("--history", default="/mnt/data/state/iros-regime/yinyang/history.csv")
    args = p.parse_args()

    df = pd.read_parquet(args.daily)
    hist = build_history(df)
    snap = latest_snapshot(df)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    hp = Path(args.history)
    hp.parent.mkdir(parents=True, exist_ok=True)
    hist.to_csv(hp, index=False)
    print(json.dumps(snap.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
