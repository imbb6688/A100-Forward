from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from a100_iros.yinyang_v2 import build_v2, latest_v2_snapshot


def main() -> int:
    p = argparse.ArgumentParser(description="Build A100 Yin-Yang v2 research state")
    p.add_argument("--history", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--series", required=True)
    args = p.parse_args()

    hist = pd.read_csv(args.history)
    v2 = build_v2(hist)
    snap = latest_v2_snapshot(hist)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(snap.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    keep = [
        "date", "v2_yang_pct", "v2_yin_pct", "v2_position_tenths",
        "v2_signal", "v2_state", "score_0_100", "breadth_score",
        "trend_score", "leadership_score"
    ]
    v2[keep].to_csv(args.series, index=False)
    print(json.dumps(snap.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
