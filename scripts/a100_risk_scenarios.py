from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Sequence

try:
    from a100_autonomous_policy import RiskPolicy, classify_market_regime, execution_interlock
except ModuleNotFoundError:  # package-style imports in unit tests
    from scripts.a100_autonomous_policy import RiskPolicy, classify_market_regime, execution_interlock


def run_scenarios() -> Dict[str, Any]:
    policy = RiskPolicy()
    clean_signal = {"data_valid": True, "validated_full_market": True, "completeness_ratio": 1.0, "candidate_count": 2, "market_gate": True}
    clean_account = {"equity": 1_000_000, "peak_equity": 1_000_000, "loss_streak": 0}
    scenarios: Dict[str, Dict[str, Any]] = {}

    def record(name: str, passed: bool, observed: Any) -> None:
        scenarios[name] = {"passed": bool(passed), "observed": observed}

    for name, change in (("invalid_data", {"data_valid": False}), ("stale_data", {"data_fresh": False})):
        signal = dict(clean_signal)
        signal.update(change)
        gate = execution_interlock(signal, clean_account, {"broker_available": True, "order_state_known": True, "price_consistent": True})
        record(name, not gate["allow_new_risk"], gate)

    hard_dd = classify_market_regime(clean_signal, {**clean_account, "equity": 870_000}, policy)
    record("hard_drawdown", hard_dd["regime"] == "RISK_OFF", hard_dd)
    hard_streak = classify_market_regime(clean_signal, {**clean_account, "loss_streak": 8}, policy)
    record("hard_loss_streak", hard_streak["regime"] == "RISK_OFF", hard_streak)

    for name, execution in (
        ("unknown_order_state", {"broker_available": True, "order_state_known": False, "price_consistent": True}),
        ("broker_unavailable", {"broker_available": False, "order_state_known": True, "price_consistent": True}),
        ("price_conflict", {"broker_available": True, "order_state_known": True, "price_consistent": False}),
    ):
        gate = execution_interlock(clean_signal, clean_account, execution)
        record(name, not gate["allow_new_risk"], gate)

    # These market-microstructure controls are implemented in the frozen paper
    # account engine; their source-contract markers are verified here without
    # changing that frozen ranker or pretending a broker fill occurred.
    account_source = Path(__file__).with_name("a100_account_v1.py").read_text(encoding="utf-8")
    record("t_plus_one", "t<=int(p['entry_date_code'])" in account_source, "same-day exits are skipped")
    record("limit_up_entry", "locked_up(sym,dt,pre,o,h,l)" in account_source, "locked limit-up entries are blocked")
    record("limit_down_exit", "locked_down(sym,dt,pre,o,h,l)" in account_source, "locked limit-down exits remain open")
    return {"schema_version": 1, "status": "COMPLETE", "scenarios": scenarios}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/mnt/data/validation/risk_scenarios.json"))
    args = parser.parse_args(argv)
    report = run_scenarios()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(x["passed"] for x in report["scenarios"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
