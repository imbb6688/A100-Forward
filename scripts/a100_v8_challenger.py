from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor


MODEL_SPEC = {
    "n_estimators": 220,
    "max_depth": 4,
    "min_samples_leaf": 40,
    "max_features": 0.8,
    "random_state": 17,
}


def eligibility_masks(features: Mapping[str, np.ndarray], v6_score: np.ndarray) -> Dict[str, np.ndarray]:
    """Return the frozen baseline and one isolated challenger.

    V8 changes only the redundant long-trend gate. All security-level quality,
    pullback, market-score, and industry-score requirements remain frozen.
    """
    common = (
        (features["setup"].astype(int) == 1)
        & (features["market"].astype(float) >= 14.0)
        & (features["industry"].astype(float) >= 9.0)
        & (v6_score.astype(float) >= 75.0)
    )
    return {
        "FROZEN_V7": common & features["gate"].astype(bool),
        "V8_COMPOSITE_GATE": common,
    }


def _rank_features(raw: np.ndarray, eligible: np.ndarray, date_code: np.ndarray) -> np.ndarray:
    ranked = np.full_like(raw, np.nan, dtype=np.float32)
    for day in np.unique(date_code[eligible]):
        idx = np.flatnonzero(eligible & (date_code == day))
        for column in range(raw.shape[1]):
            ranked[idx, column] = (
                pd.Series(raw[idx, column]).rank(pct=True, method="average").to_numpy(dtype=np.float32)
            )
    return ranked


def fit_rank_scores(
    features: Mapping[str, np.ndarray],
    v6_score: np.ndarray,
    eligible: np.ndarray,
) -> np.ndarray:
    net_r = features["netR"].astype(float)
    years = features["year"].astype(int)
    date_code = features["date_code_sig"].astype(int)
    raw = np.column_stack([
        v6_score,
        features["core"],
        features["industry"],
        features["oldleader"],
        features["market"],
        features["dist"],
        features["ret5"],
        features["ret20"],
        features["atrpct"],
        features["volratio"],
        features["limit20"],
    ]).astype(float)
    ranked = _rank_features(raw, eligible, date_code)
    design = np.column_stack([
        ranked,
        v6_score / 100.0,
        features["industry"].astype(float) / 12.0,
        features["market"].astype(float) / 20.0,
        np.clip(features["dist"].astype(float), -0.2, 0.3),
        np.clip(features["atrpct"].astype(float), 0.0, 0.15),
        np.log1p(np.clip(features["volratio"].astype(float), 0.0, 10.0)),
    ]).astype(np.float32)
    train = eligible & (years <= 2022) & np.isfinite(net_r)
    if int(train.sum()) < 500:
        raise ValueError(f"insufficient training observations: {int(train.sum())}")
    medians = np.nanmedian(design[train], axis=0)
    for column in range(design.shape[1]):
        missing = ~np.isfinite(design[:, column])
        design[missing, column] = medians[column] if np.isfinite(medians[column]) else 0.5
    count_by_day = np.bincount(date_code[train], minlength=int(date_code.max()) + 1)
    weights = np.ones(len(net_r), dtype=float)
    weights[train] = 1.0 / np.maximum(count_by_day[date_code[train]], 1)
    weights[train] *= train.sum() / weights[train].sum()
    model = ExtraTreesRegressor(n_jobs=-1, **MODEL_SPEC)
    model.fit(design[train], net_r[train], sample_weight=weights[train])
    scores = np.full(len(net_r), np.nan, dtype=np.float32)
    scores[eligible] = model.predict(design[eligible]).astype(np.float32)
    return scores


def _profit_factor(values: np.ndarray) -> float:
    gains = float(values[values > 0].sum())
    losses = -float(values[values < 0].sum())
    return gains / losses if losses > 0 else (999.0 if gains > 0 else 0.0)


def select_top_two(
    eligible: np.ndarray,
    scores: np.ndarray,
    net_r: np.ndarray,
    years: np.ndarray,
    date_code: np.ndarray,
) -> np.ndarray:
    test = eligible & np.isfinite(scores) & np.isfinite(net_r) & (years >= 2023)
    selected: list[int] = []
    for day in np.unique(date_code[test]):
        idx = np.flatnonzero(test & (date_code == day))
        selected.extend(idx[np.argsort(scores[idx])[::-1]][:2].tolist())
    return np.asarray(selected, dtype=int)


def _folds(
    selected: np.ndarray,
    net_r: np.ndarray,
    years: np.ndarray,
    date_code: np.ndarray,
    dates: pd.DatetimeIndex,
) -> list[Dict[str, Any]]:
    output = []
    for year in range(2023, int(years.max()) + 1):
        idx = selected[years[selected] == year]
        values = net_r[idx]
        daily_return = values * 0.005
        equity = np.cumprod(1.0 + daily_return)
        peak = np.maximum.accumulate(equity) if len(equity) else np.asarray([])
        drawdown = equity / peak - 1.0 if len(equity) else np.asarray([])
        output.append({
            "fold": str(year),
            "trades": int(len(idx)),
            "signal_days": int(len(np.unique(date_code[idx]))),
            "positive_trade_ratio": float(np.mean(values > 0)) if len(values) else 0.0,
            "mean_r": float(np.mean(values)) if len(values) else 0.0,
            "net_return": float(equity[-1] - 1.0) if len(equity) else 0.0,
            "profit_factor": _profit_factor(values),
            "max_drawdown": float(drawdown.min()) if len(drawdown) else 0.0,
            "first_signal_date": dates[date_code[idx]].min().date().isoformat() if len(idx) else None,
            "last_signal_date": dates[date_code[idx]].max().date().isoformat() if len(idx) else None,
        })
    return output


def _proxy_acceptance(folds: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    active = [fold for fold in folds if int(fold["trades"]) > 0]
    total_trades = sum(int(fold["trades"]) for fold in active)
    profitable_ratio = sum(float(fold["net_return"]) > 0 for fold in active) / len(active) if active else 0.0
    factors = [float(fold["profit_factor"]) for fold in active]
    worst_drawdown = min((float(fold["max_drawdown"]) for fold in active), default=-1.0)
    checks = {
        "at_least_3_folds": len(active) >= 3,
        "at_least_100_trades": total_trades >= 100,
        "profitable_fold_ratio_at_least_0_67": profitable_ratio >= 0.67,
        "median_profit_factor_at_least_1_10": bool(factors) and float(np.median(factors)) >= 1.10,
        "worst_profit_factor_at_least_0_90": bool(factors) and min(factors) >= 0.90,
        "worst_drawdown_no_worse_than_0_15": worst_drawdown >= -0.15,
    }
    return {
        "passed_all_proxy_checks": all(checks.values()),
        "checks": checks,
        "observed": {
            "folds": len(active),
            "trades": total_trades,
            "profitable_fold_ratio": profitable_ratio,
            "median_profit_factor": float(np.median(factors)) if factors else 0.0,
            "worst_profit_factor": min(factors) if factors else 0.0,
            "worst_drawdown": worst_drawdown,
        },
    }


def _period_label(year: int) -> str:
    if year <= 2024:
        return "RETROSPECTIVE_SELECTION"
    if year == 2025:
        return "RETROSPECTIVE_LOCKED_TEST"
    return "CONTAMINATED_DIAGNOSTIC_ONLY"


def _baseline_parity(
    root: Path,
    expected_mask: np.ndarray,
    reproduced_scores: np.ndarray,
) -> Dict[str, Any]:
    """Fail closed unless the comparator reproduces the frozen V7 artifact."""
    frozen_path = root / "A100_v7_results" / "A100_V7_rank_context.npz"
    frozen = np.load(frozen_path, allow_pickle=False)
    frozen_mask = frozen["broad"].astype(bool)
    frozen_scores = frozen["rank_score"].astype(float)
    mask_match = bool(np.array_equal(expected_mask, frozen_mask))
    finite_match = bool(np.array_equal(np.isfinite(reproduced_scores), np.isfinite(frozen_scores)))
    common = np.isfinite(reproduced_scores) & np.isfinite(frozen_scores)
    max_abs_error = float(np.max(np.abs(reproduced_scores[common] - frozen_scores[common]))) if common.any() else 0.0
    score_match = finite_match and bool(np.allclose(reproduced_scores[common], frozen_scores[common], rtol=0.0, atol=1e-7))
    passed = mask_match and score_match
    result = {
        "passed": passed,
        "mask_exact_match": mask_match,
        "score_finite_mask_exact_match": finite_match,
        "score_max_abs_error": max_abs_error,
        "tolerance": 1e-7,
    }
    if not passed:
        raise RuntimeError(f"Frozen V7 reproduction failed: {result}")
    return result


def build(root: Path, output_dir: Path) -> Dict[str, Any]:
    feature_path = root / "A100_v6_results" / "A100_V6_features.npz"
    score_path = root / "A100_v6_results" / "A100_V6_score_context.npz"
    context_path = root / "A100_v5_results" / "A100_V5_context.npz"
    features_npz = np.load(feature_path, allow_pickle=False)
    features = {key: features_npz[key] for key in features_npz.files}
    v6_score = np.load(score_path, allow_pickle=False)["score"].astype(float)
    context = np.load(context_path, allow_pickle=False)
    dates = pd.to_datetime(context["unique_dates"], unit="us")
    years = features["year"].astype(int)
    date_code = features["date_code_sig"].astype(int)
    net_r = features["netR"].astype(float)
    masks = eligibility_masks(features, v6_score)

    variants: Dict[str, Any] = {}
    selected_rows = []
    parity: Dict[str, Any] | None = None
    for name, eligible in masks.items():
        scores = fit_rank_scores(features, v6_score, eligible)
        if name == "FROZEN_V7":
            parity = _baseline_parity(root, eligible, scores)
        selected = select_top_two(eligible, scores, net_r, years, date_code)
        folds = _folds(selected, net_r, years, date_code, dates)
        for fold in folds:
            fold["evidence_period"] = _period_label(int(fold["fold"]))
        acceptance_folds = [fold for fold in folds if int(fold["fold"]) <= 2025]
        variants[name] = {
            "definition": (
                "Frozen V7: composite thresholds plus MA20>MA60>MA120 full-trend gate"
                if name == "FROZEN_V7"
                else "V8 Challenger: same thresholds/model; remove only the redundant MA120 full-trend gate"
            ),
            "eligible_rows_all_years": int(eligible.sum()),
            "training_rows_with_outcome": int((eligible & (years <= 2022) & np.isfinite(net_r)).sum()),
            "folds": folds,
            "proxy_acceptance_pre_2026": _proxy_acceptance(acceptance_folds),
            "diagnostic_including_2026": _proxy_acceptance(folds),
        }
        sid = features["sid"].astype(int)[selected]
        for idx, symbol_id in zip(selected, sid):
            selected_rows.append({
                "variant": name,
                "signal_date": dates[date_code[idx]].date().isoformat(),
                "symbol": str(context["symbols"][symbol_id]),
                "rank_score": float(scores[idx]),
                "net_r": float(net_r[idx]),
                "market_score": float(features["market"][idx]),
                "industry_score": float(features["industry"][idx]),
                "v6_score": float(v6_score[idx]),
            })

    frame = pd.DataFrame(selected_rows).sort_values(["variant", "signal_date", "rank_score"], ascending=[True, True, False])
    output_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_dir / "v8_challenger_selected.csv", index=False)
    digest = hashlib.sha256(feature_path.read_bytes() + score_path.read_bytes()).hexdigest()
    report = {
        "schema_version": "A100-V8-CHALLENGER-v1",
        "status": "COMPLETE",
        "evidence_class": "RANKING_PROXY_NOT_GRADUATION_EVIDENCE",
        "frozen_v7_modified": False,
        "data_fingerprint": digest,
        "training_window": "2020-2022",
        "evaluation_windows": {
            "2023-2024": "retrospective selection/robustness",
            "2025": "retrospective locked-test convention; not pristine after strategy review",
            "2026": "diagnostic only; explicitly contaminated by observing the May 19 failure",
        },
        "frozen_v7_reproduction": parity,
        "controlled_change": "Remove only Frozen V7 full-trend gate; retain composite market>=14 and all security thresholds.",
        "limitations": [
            "PIT ST history is not yet applied",
            "historical industry membership is still a price-cluster proxy",
            "signal-level outcomes do not enforce portfolio overlap or cash constraints",
            "candidate model is refit per variant on the unchanged 2020-2022 training window",
            "2026 is excluded from acceptance because the challenger was designed after observing its May 19 signal",
            "all historical periods are retrospective research, not a claim of pristine out-of-sample discovery",
            "must pass PIT portfolio replay and shadow/paper before any production promotion",
        ],
        "variants": variants,
    }
    (output_dir / "v8_challenger_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare Frozen V7 with a controlled V8 market-gate challenger")
    parser.add_argument("--root", type=Path, default=Path("/mnt/data"))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    output = args.output_dir or args.root / "validation" / "v8_challenger"
    build(args.root, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
