from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-shards", type=int, required=True)
    parser.add_argument("--expected-symbols", type=int, required=True)
    args = parser.parse_args()
    paths = sorted(args.input.rglob("industry_membership_history.part-*.parquet"))
    if len(paths) != args.expected_shards:
        raise RuntimeError(f"expected {args.expected_shards} shards, found {len(paths)}")
    frame = pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)
    frame = frame.sort_values(["symbol", "effective_from"]).reset_index(drop=True)
    if frame.symbol.nunique() != args.expected_symbols:
        raise RuntimeError(f"expected {args.expected_symbols} symbols, found {frame.symbol.nunique()}")
    overlaps = frame.effective_from.le(frame.groupby("symbol").effective_to.shift())
    if overlaps.any():
        raise RuntimeError(f"overlapping industry intervals: {int(overlaps.sum())}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(args.output, index=False)
    manifest = {
        "schema_version": 1,
        "kind": "industry",
        "source_name": "CNInfo historical Shenwan classification (old and 2021 standards)",
        "rows": len(frame),
        "symbols": frame.symbol.nunique(),
        "shards": len(paths),
        "min_effective_from": str(pd.to_datetime(frame.effective_from).min().date()),
        "max_effective_to": str(pd.to_datetime(frame.effective_to).max().date()),
    }
    (args.output.parent / "industry_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
