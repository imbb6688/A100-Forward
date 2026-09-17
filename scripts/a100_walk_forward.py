from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, Sequence

import pandas as pd


REQUIRED = {"fold", "train_end", "test_start", "test_end", "exit_date", "pnl", "equity", "peak_equity"}


def _profit_factor(pnl: pd.Series) -> float | None:
    gains = float(pnl[pnl > 0].sum())
    losses = -float(pnl[pnl < 0].sum())
    if losses > 0:
        return gains / losses
    return None if gains == 0 else 999.0


def build_report(path: Path) -> Dict[str, Any]:
    raw = path.read_bytes()
    frame = pd.read_csv(path)
    missing = sorted(REQUIRED - set(frame.columns))
    if missing:
        raise ValueError(f"missing Walk Forward columns: {missing}")
    if frame.empty:
        raise ValueError("Walk Forward ledger is empty")
    for col in ("train_end", "test_start", "test_end", "exit_date"):
        frame[col] = pd.to_datetime(frame[col], errors="raise")
    if (frame["train_end"] >= frame["test_start"]).any():
        raise ValueError("training and test windows overlap")
    if ((frame["exit_date"] < frame["test_start"]) | (frame["exit_date"] > frame["test_end"])).any():
        raise ValueError("trade outside its declared out-of-sample test window")
    folds = []
    for fold, part in frame.groupby("fold", sort=True):
        pnl = pd.to_numeric(part["pnl"], errors="raise")
        equity = pd.to_numeric(part["equity"], errors="raise")
        peak = pd.to_numeric(part["peak_equity"], errors="raise")
        drawdown = equity / peak.replace(0, math.nan) - 1.0
        initial = float(equity.iloc[0] - pnl.iloc[0])
        net_return = float(pnl.sum() / initial) if initial > 0 else 0.0
        folds.append({
            "fold": str(fold),
            "train_end": part["train_end"].min().date().isoformat(),
            "test_start": part["test_start"].min().date().isoformat(),
            "test_end": part["test_end"].max().date().isoformat(),
            "trades": int(len(part)),
            "net_return": net_return,
            "profit_factor": _profit_factor(pnl),
            "max_drawdown": float(drawdown.min()),
        })
    return {
        "schema_version": 1,
        "status": "COMPLETE",
        "method": "anchored_or_rolling_out_of_sample_ledger",
        "data_fingerprint": hashlib.sha256(raw).hexdigest(),
        "folds": folds,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize an auditable out-of-sample Walk Forward trade ledger.")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("/mnt/data/validation/walk_forward_report.json"))
    args = parser.parse_args(argv)
    report = build_report(args.ledger)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
