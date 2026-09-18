from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Sequence

import numpy as np
import pandas as pd


def _profit_factor(values: np.ndarray) -> float:
    gains = float(values[values > 0].sum())
    losses = -float(values[values < 0].sum())
    return gains / losses if losses > 0 else (999.0 if gains > 0 else 0.0)


def build(root: Path) -> Dict[str, Any]:
    feature_path = root / "A100_v6_results" / "A100_V6_features.npz"
    rank_path = root / "A100_v7_results" / "A100_V7_rank_context.npz"
    context_path = root / "A100_v5_results" / "A100_V5_context.npz"
    f = np.load(feature_path, allow_pickle=False)
    r = np.load(rank_path, allow_pickle=False)
    c = np.load(context_path, allow_pickle=False)
    rank = r["rank_score"].astype(float)
    broad = r["broad"].astype(bool)
    net_r = f["netR"].astype(float)
    dates = pd.to_datetime(c["unique_dates"], unit="us")
    date_code = f["date_code_sig"].astype(int)
    years = f["year"].astype(int)
    eligible = broad & np.isfinite(rank) & np.isfinite(net_r) & (years >= 2023)
    selected = []
    for day in np.unique(date_code[eligible]):
        ix = np.flatnonzero(eligible & (date_code == day))
        ix = ix[np.argsort(rank[ix])[::-1]][:2]
        selected.extend(ix.tolist())
    selected = np.asarray(selected, dtype=int)
    folds = []
    for year in sorted(set(years[selected].tolist())):
        ix = selected[years[selected] == year]
        values = net_r[ix]
        # Equal 0.5% risk units. This is a ranking-level proxy and deliberately
        # not a portfolio replay with overlapping positions/cash constraints.
        daily_return = values * 0.005
        equity = np.cumprod(1.0 + daily_return)
        peak = np.maximum.accumulate(equity)
        drawdown = equity / peak - 1.0
        folds.append({
            "fold": str(year),
            "train_end": "2022-12-31",
            "test_start": f"{year}-01-01",
            "test_end": f"{year}-12-31",
            "trades": int(len(ix)),
            "positive_trade_ratio": float(np.mean(values > 0)) if len(values) else 0.0,
            "mean_r": float(np.mean(values)) if len(values) else 0.0,
            "net_return": float(equity[-1] - 1.0) if len(equity) else 0.0,
            "profit_factor": _profit_factor(values),
            "max_drawdown": float(drawdown.min()) if len(drawdown) else 0.0,
            "first_signal_date": dates[date_code[ix]].min().date().isoformat() if len(ix) else None,
            "last_signal_date": dates[date_code[ix]].max().date().isoformat() if len(ix) else None,
        })
    digest = hashlib.sha256(feature_path.read_bytes() + rank_path.read_bytes()).hexdigest()
    return {
        "schema_version": 1,
        "status": "COMPLETE",
        "evidence_class": "RANKING_PROXY",
        "graduation_eligible": False,
        "model": "A100_V7_FROZEN",
        "training_window": "2020-2022",
        "selection": "daily Top 2 among Frozen V7 broad candidates",
        "data_fingerprint": digest,
        "limitations": [
            "PIT ST history is not yet applied",
            "historical industry membership is still a price-cluster proxy",
            "signal-level outcomes do not enforce portfolio overlap or cash constraints",
            "must be replaced by PORTFOLIO_REPLAY before graduation"
        ],
        "folds": folds,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/mnt/data"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = build(args.root)
    output = args.output or args.root / "validation" / "walk_forward_proxy_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    feature = np.load(args.root / "A100_v6_results" / "A100_V6_features.npz", allow_pickle=False)
    rank_context = np.load(args.root / "A100_v7_results" / "A100_V7_rank_context.npz", allow_pickle=False)
    context = np.load(args.root / "A100_v5_results" / "A100_V5_context.npz", allow_pickle=False)
    eligible = (
        rank_context["broad"].astype(bool)
        & np.isfinite(rank_context["rank_score"].astype(float))
        & (feature["year"].astype(int) >= 2023)
    )
    idx = np.flatnonzero(eligible)
    sid = feature["sid"].astype(int)[idx]
    date_code = feature["date_code_sig"].astype(int)[idx]
    candidates = pd.DataFrame({
        "signal_date": pd.to_datetime(context["unique_dates"][date_code], unit="us").strftime("%Y-%m-%d"),
        "symbol": context["symbols"][sid].astype(str),
        "rank_score": rank_context["rank_score"].astype(float)[idx],
    }).sort_values(["signal_date", "rank_score", "symbol"], ascending=[True, False, True])
    candidates.to_csv(output.parent / "walk_forward_candidate_universe.csv", index=False)
    report["candidate_rows"] = int(len(candidates))
    report["candidate_symbols"] = int(candidates["symbol"].nunique())
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
