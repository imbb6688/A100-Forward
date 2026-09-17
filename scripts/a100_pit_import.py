from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import pandas as pd


CONTRACTS = {
    "st": {
        "output": "st_risk_warning_history.parquet",
        "required": ["symbol", "effective_from", "effective_to", "is_st"],
    },
    "industry": {
        "output": "industry_membership_history.parquet",
        "required": ["symbol", "effective_from", "effective_to", "industry_code"],
    },
}


def _read(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if path.suffix.lower() in {".csv", ".txt"}:
        return pd.read_csv(path)
    raise ValueError("input must be CSV or Parquet")


def normalize(kind: str, source: Path) -> pd.DataFrame:
    contract = CONTRACTS[kind]
    frame = _read(source).copy()
    missing = sorted(set(contract["required"]) - set(frame.columns))
    if missing:
        raise ValueError(f"missing PIT columns: {missing}")
    frame = frame[contract["required"]]
    frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
    if frame["symbol"].eq("").any():
        raise ValueError("blank symbol")
    for col in ("effective_from", "effective_to"):
        frame[col] = pd.to_datetime(frame[col], errors="raise").dt.normalize()
    if (frame["effective_to"] < frame["effective_from"]).any():
        raise ValueError("effective_to precedes effective_from")
    if kind == "st":
        accepted = {True, False, 0, 1, "0", "1", "true", "false", "TRUE", "FALSE"}
        if not frame["is_st"].isin(accepted).all():
            raise ValueError("is_st must be boolean-like")
        frame["is_st"] = frame["is_st"].map(lambda x: str(x).lower() in {"1", "true"})
    else:
        frame["industry_code"] = frame["industry_code"].astype(str).str.strip()
        if frame["industry_code"].eq("").any():
            raise ValueError("blank industry_code")
    frame = frame.sort_values(["symbol", "effective_from", "effective_to"]).reset_index(drop=True)
    previous_end = frame.groupby("symbol")["effective_to"].shift()
    if (frame["effective_from"] <= previous_end).fillna(False).any():
        raise ValueError("overlapping PIT validity intervals")
    if frame.duplicated().any():
        raise ValueError("duplicate PIT rows")
    return frame


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import externally sourced PIT history into the A100 canonical contract.")
    parser.add_argument("kind", choices=sorted(CONTRACTS))
    parser.add_argument("source", type=Path)
    parser.add_argument("--root", type=Path, default=Path("/mnt/data"))
    parser.add_argument("--source-name", required=True)
    parser.add_argument("--source-version", required=True)
    args = parser.parse_args(argv)
    frame = normalize(args.kind, args.source)
    out_dir = args.root / "pit"
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / CONTRACTS[args.kind]["output"]
    frame.to_parquet(output, index=False)
    manifest = {
        "schema_version": 1,
        "kind": args.kind,
        "source_name": args.source_name,
        "source_version": args.source_version,
        "rows": int(len(frame)),
        "symbols": int(frame["symbol"].nunique()),
        "min_effective_from": frame["effective_from"].min().date().isoformat(),
        "max_effective_to": frame["effective_to"].max().date().isoformat(),
        "output": str(output),
    }
    (out_dir / f"{args.kind}_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
