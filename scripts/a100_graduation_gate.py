from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence


FROZEN_RANKER = Path(__file__).with_name("a100_v7_forward_ranker.py")


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _finite(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def git_blob_sha(path: Path) -> str:
    content = path.read_bytes()
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content).hexdigest()


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    observed: Any
    required: Any
    reason: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "observed": self.observed,
            "required": self.required,
            "reason": self.reason,
        }


def _check(name: str, passed: bool, observed: Any, required: Any, reason: str) -> Check:
    return Check(name, bool(passed), observed, required, "PASS" if passed else reason)


def validate_frozen(policy: Mapping[str, Any]) -> List[Check]:
    expected = str(policy["frozen_v7_blob_sha"])
    observed = git_blob_sha(FROZEN_RANKER)
    return [_check("frozen_v7_unchanged", observed == expected, observed, expected, "FROZEN_V7_HASH_MISMATCH")]


def validate_data(policy: Mapping[str, Any], manifest: Mapping[str, Any], inventory: Mapping[str, Any]) -> List[Check]:
    cfg = policy["data"]
    checks = [
        _check("data_valid", manifest.get("data_valid") is True, manifest.get("data_valid"), True, "DATA_INVALID"),
        _check("full_market", manifest.get("full_market") is True, manifest.get("full_market"), True, "NOT_FULL_MARKET"),
        _check("download_complete", manifest.get("complete") is True, manifest.get("complete"), True, "DOWNLOAD_INCOMPLETE"),
        _check(
            "latest_rows",
            int(manifest.get("latest_rows") or 0) >= int(cfg["min_latest_rows"]),
            int(manifest.get("latest_rows") or 0),
            cfg["min_latest_rows"],
            "LATEST_SESSION_TOO_SMALL",
        ),
        _check(
            "completeness_ratio",
            float(manifest.get("completeness_ratio") or 0) >= float(cfg["min_completeness_ratio"]),
            float(manifest.get("completeness_ratio") or 0),
            cfg["min_completeness_ratio"],
            "DATA_COMPLETENESS_TOO_LOW",
        ),
    ]
    datasets = inventory.get("datasets") if isinstance(inventory, Mapping) else {}
    datasets = datasets if isinstance(datasets, Mapping) else {}
    for name in cfg["required_pit_datasets"]:
        item = datasets.get(name) if isinstance(datasets.get(name), Mapping) else {}
        status = str(item.get("status") or "MISSING")
        as_of_safe = item.get("point_in_time_safe") is True
        checks.append(_check(f"pit_dataset:{name}", status == "COMPLETE" and as_of_safe, item, {"status": "COMPLETE", "point_in_time_safe": True}, "PIT_DATASET_INCOMPLETE"))
    return checks


def validate_walk_forward(policy: Mapping[str, Any], report: Mapping[str, Any]) -> List[Check]:
    cfg = policy["walk_forward"]
    folds = report.get("folds") if isinstance(report, Mapping) else []
    folds = folds if isinstance(folds, list) else []
    pfs = [_finite(f.get("profit_factor")) for f in folds if isinstance(f, Mapping)]
    pfs = [x for x in pfs if x is not None]
    drawdowns = [abs(_finite(f.get("max_drawdown")) or float("inf")) for f in folds if isinstance(f, Mapping)]
    trades = sum(int(f.get("trades") or 0) for f in folds if isinstance(f, Mapping))
    profitable = sum(1 for f in folds if isinstance(f, Mapping) and (_finite(f.get("net_return")) or 0) > 0)
    profitable_ratio = profitable / len(folds) if folds else 0.0
    median_pf = sorted(pfs)[len(pfs) // 2] if pfs else 0.0
    worst_pf = min(pfs) if pfs else 0.0
    worst_dd = max(drawdowns) if drawdowns else 999.0
    return [
        _check("walk_forward_evidence_signed", report.get("status") == "COMPLETE" and bool(report.get("data_fingerprint")), {"status": report.get("status"), "data_fingerprint": report.get("data_fingerprint")}, "COMPLETE_WITH_FINGERPRINT", "WF_EVIDENCE_INCOMPLETE"),
        _check("walk_forward_folds", len(folds) >= int(cfg["min_folds"]), len(folds), cfg["min_folds"], "WF_TOO_FEW_FOLDS"),
        _check("walk_forward_trades", trades >= int(cfg["min_total_trades"]), trades, cfg["min_total_trades"], "WF_TOO_FEW_TRADES"),
        _check("walk_forward_profitable_folds", profitable_ratio >= float(cfg["min_profitable_fold_ratio"]), profitable_ratio, cfg["min_profitable_fold_ratio"], "WF_PROFITABLE_FOLD_RATIO_LOW"),
        _check("walk_forward_median_pf", median_pf >= float(cfg["min_median_profit_factor"]), median_pf, cfg["min_median_profit_factor"], "WF_MEDIAN_PF_LOW"),
        _check("walk_forward_worst_pf", worst_pf >= float(cfg["min_worst_fold_profit_factor"]), worst_pf, cfg["min_worst_fold_profit_factor"], "WF_WORST_FOLD_PF_LOW"),
        _check("walk_forward_worst_drawdown", worst_dd <= float(cfg["max_worst_fold_drawdown"]), worst_dd, cfg["max_worst_fold_drawdown"], "WF_DRAWDOWN_TOO_HIGH"),
    ]


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def validate_paper(policy: Mapping[str, Any], state_dir: Path) -> List[Check]:
    cfg = policy["paper"]
    state = _load_json(state_dir / "account_state.json", {}) or {}
    equity = _read_csv(state_dir / "equity_curve.csv")
    trades = _read_csv(state_dir / "trade_log.csv")
    dates = [row.get("date") for row in equity if row.get("date")]
    unique_dates = sorted(set(dates))
    closed = int(state.get("closed_trades") or len(trades))
    pnls = [_finite(row.get("pnl")) for row in trades]
    pnls = [x for x in pnls if x is not None]
    gains = sum(x for x in pnls if x > 0)
    losses = -sum(x for x in pnls if x < 0)
    pf = gains / losses if losses > 0 else (999.0 if gains > 0 else 0.0)
    max_dd = abs(_finite(state.get("max_drawdown")) or 0.0)
    duplicate_sessions = len(dates) - len(unique_dates)
    mode_ok = all((row.get("mode") or "SHADOW") in {"SHADOW", "PAPER"} for row in _read_csv(state_dir / "autonomous_journal.csv"))
    return [
        _check("paper_sessions", len(unique_dates) >= int(cfg["min_sessions"]), len(unique_dates), cfg["min_sessions"], "PAPER_TOO_SHORT"),
        _check("paper_closed_trades", closed >= int(cfg["min_closed_trades"]), closed, cfg["min_closed_trades"], "PAPER_TOO_FEW_TRADES"),
        _check("paper_profit_factor", pf >= float(cfg["min_profit_factor"]), pf, cfg["min_profit_factor"], "PAPER_PF_LOW"),
        _check("paper_max_drawdown", max_dd <= float(cfg["max_drawdown"]), max_dd, cfg["max_drawdown"], "PAPER_DRAWDOWN_TOO_HIGH"),
        _check("paper_state_unique_sessions", duplicate_sessions <= int(cfg["max_state_gap_sessions"]), duplicate_sessions, cfg["max_state_gap_sessions"], "PAPER_STATE_DUPLICATE"),
        _check("paper_no_broker_execution", mode_ok, mode_ok, True, "NON_PAPER_EXECUTION_DETECTED"),
    ]


def validate_risk(policy: Mapping[str, Any], report: Mapping[str, Any]) -> List[Check]:
    scenarios = report.get("scenarios") if isinstance(report, Mapping) else {}
    scenarios = scenarios if isinstance(scenarios, Mapping) else {}
    checks = []
    for name in policy["risk"]["required_scenarios"]:
        item = scenarios.get(name) if isinstance(scenarios.get(name), Mapping) else {}
        checks.append(_check(f"risk_scenario:{name}", item.get("passed") is True, item, {"passed": True}, "RISK_SCENARIO_NOT_PROVEN"))
    return checks


def evaluate(policy: Mapping[str, Any], root: Path) -> Dict[str, Any]:
    evidence = root / "validation"
    groups = {
        "frozen": validate_frozen(policy),
        "data": validate_data(policy, _load_json(root / "hithink_manifest.json", {}) or {}, _load_json(evidence / "data_inventory.json", {}) or {}),
        "walk_forward": validate_walk_forward(policy, _load_json(evidence / "walk_forward_report.json", {}) or {}),
        "paper": validate_paper(policy, root / "state"),
        "risk": validate_risk(policy, _load_json(evidence / "risk_scenarios.json", {}) or {}),
    }
    serialized = {name: [c.as_dict() for c in checks] for name, checks in groups.items()}
    passed = all(c.passed for checks in groups.values() for c in checks)
    blockers = [c.reason for checks in groups.values() for c in checks if not c.passed]
    return {
        "schema_version": 1,
        "system": "A100 Autonomous Trading System",
        "policy_version": policy["version"],
        "status": "GRADUATED" if passed else "BLOCKED",
        "live_trading_enabled": False,
        "broker_orders_enabled": False,
        "decision": "HUMAN_APPROVAL_REQUIRED_AFTER_GRADUATION" if passed else "REMAIN_SHADOW_PAPER",
        "checks": serialized,
        "blockers": sorted(set(blockers)),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate A100 evidence without enabling broker execution.")
    parser.add_argument("--root", type=Path, default=Path("/mnt/data"))
    parser.add_argument("--policy", type=Path, default=Path(__file__).parents[1] / "config" / "graduation_policy.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    policy = _load_json(args.policy)
    result = evaluate(policy, args.root)
    output = args.output or args.root / "forward" / "graduation_gate.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
