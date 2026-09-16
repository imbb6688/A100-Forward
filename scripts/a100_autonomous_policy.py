from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class RiskPolicy:
    max_positions: int = 5
    max_single_position_pct: float = 0.25
    max_portfolio_exposure_pct: float = 0.65
    soft_drawdown: float = -0.08
    hard_drawdown: float = -0.12
    soft_loss_streak: int = 5
    hard_loss_streak: int = 8
    min_data_completeness: float = 0.98
    min_candidate_count: int = 2


def _finite_number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in (float("inf"), float("-inf")):
        return default
    return number


def classify_market_regime(signal: Dict[str, Any], account: Dict[str, Any], policy: RiskPolicy = RiskPolicy()) -> Dict[str, Any]:
    completeness = _finite_number(signal.get("completeness_ratio"), 0.0)
    candidate_count = int(signal.get("candidate_count") or 0)
    market_gate = bool(signal.get("market_gate"))
    equity = _finite_number(account.get("equity"), 0.0)
    peak = max(_finite_number(account.get("peak_equity"), equity), 1e-9)
    drawdown = equity / peak - 1.0 if equity > 0 else -1.0
    loss_streak = int(account.get("loss_streak") or 0)

    reasons: List[str] = []
    if not bool(signal.get("validated_full_market")) or not bool(signal.get("data_valid")):
        reasons.append("DATA_INVALID")
    if completeness < policy.min_data_completeness:
        reasons.append("DATA_INCOMPLETE")
    if candidate_count < policy.min_candidate_count:
        reasons.append("THIN_CANDIDATE_SET")
    if not market_gate:
        reasons.append("MARKET_GATE_OFF")
    if drawdown <= policy.hard_drawdown:
        reasons.append("HARD_DRAWDOWN")
    if loss_streak >= policy.hard_loss_streak:
        reasons.append("HARD_LOSS_STREAK")

    if any(x in reasons for x in ("DATA_INVALID", "DATA_INCOMPLETE", "HARD_DRAWDOWN", "HARD_LOSS_STREAK")):
        regime = "RISK_OFF"
        exposure = 0.0
    elif not market_gate or candidate_count < policy.min_candidate_count:
        regime = "DEFENSIVE"
        exposure = 0.0
    elif drawdown <= policy.soft_drawdown or loss_streak >= policy.soft_loss_streak:
        regime = "CAUTIOUS"
        exposure = 0.35
    else:
        regime = "RISK_ON"
        exposure = policy.max_portfolio_exposure_pct

    return {
        "regime": regime,
        "target_exposure_pct": exposure,
        "drawdown": drawdown,
        "loss_streak": loss_streak,
        "candidate_count": candidate_count,
        "completeness_ratio": completeness,
        "market_gate": market_gate,
        "reasons": reasons,
    }


def apply_global_controls(regime: Dict[str, Any], *, mode: str = "SHADOW", kill_switch: bool = False) -> Dict[str, Any]:
    """Apply system-level controls after market/risk classification.

    Autonomous 1.x intentionally supports SHADOW mode only. Any unexpected mode
    fails closed. The global kill switch always forces RISK_OFF and zero new
    exposure regardless of upstream model output.
    """
    normalized_mode = str(mode or "").strip().upper()
    if normalized_mode != "SHADOW":
        raise ValueError(f"unsupported autonomous mode: {normalized_mode or '<empty>'}")

    controlled = dict(regime)
    controlled["reasons"] = list(regime.get("reasons") or [])
    controlled["control_mode"] = normalized_mode
    controlled["kill_switch"] = bool(kill_switch)
    if kill_switch:
        controlled["regime"] = "RISK_OFF"
        controlled["target_exposure_pct"] = 0.0
        if "GLOBAL_KILL_SWITCH" not in controlled["reasons"]:
            controlled["reasons"].append("GLOBAL_KILL_SWITCH")
    return controlled


def validate_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    reasons: List[str] = []
    rank = _finite_number(candidate.get("v7_rank_score"), float("-inf"))
    v6 = _finite_number(candidate.get("v6_score"), float("-inf"))
    industry = _finite_number(candidate.get("industry_score"), float("-inf"))
    market = _finite_number(candidate.get("market_score"), float("-inf"))
    symbol = str(candidate.get("symbol") or "").strip()

    if not symbol:
        reasons.append("MISSING_SYMBOL")
    if rank == float("-inf") or v6 == float("-inf"):
        reasons.append("MISSING_MODEL_SCORE")
    if industry == float("-inf") or market == float("-inf"):
        reasons.append("MISSING_CONTEXT_SCORE")

    return {
        "symbol": symbol,
        "passed": not reasons,
        "reasons": reasons,
        "scores": {
            "v7_rank_score": None if rank == float("-inf") else rank,
            "v6_score": None if v6 == float("-inf") else v6,
            "industry_score": None if industry == float("-inf") else industry,
            "market_score": None if market == float("-inf") else market,
        },
    }


def _account_positions(account: Dict[str, Any]) -> List[Dict[str, Any]]:
    positions = account.get("open_positions")
    if positions is None:
        positions = account.get("positions", [])
    return positions if isinstance(positions, list) else []


def build_shadow_allocations(
    candidates: Iterable[Dict[str, Any]],
    regime: Dict[str, Any],
    account: Dict[str, Any],
    policy: RiskPolicy = RiskPolicy(),
) -> Dict[str, Any]:
    target_exposure = min(
        max(_finite_number(regime.get("target_exposure_pct"), 0.0), 0.0),
        policy.max_portfolio_exposure_pct,
    )
    if regime["regime"] == "RISK_OFF" or target_exposure <= 0.0:
        return {"allocations": [], "rejected": [], "target_exposure_pct": 0.0}

    held = {str(p.get("symbol")) for p in _account_positions(account)}
    pending = {str(p.get("symbol")) for p in account.get("pending_orders", []) if isinstance(p, dict)}
    validations = []
    eligible = []
    for raw in candidates:
        c = dict(raw)
        v = validate_candidate(c)
        validations.append((c, v))
        if v["passed"] and v["symbol"] not in held and v["symbol"] not in pending:
            eligible.append(c)

    eligible.sort(key=lambda x: _finite_number(x.get("v7_rank_score"), -1e99), reverse=True)
    slots = max(0, policy.max_positions - len(held))
    selected = eligible[:slots]
    per_name = min(policy.max_single_position_pct, target_exposure / max(len(selected), 1)) if selected else 0.0

    allocations = [
        {
            "symbol": str(c.get("symbol")),
            "target_weight_pct": per_name,
            "rank": int(c.get("rank") or i + 1),
            "v7_rank_score": _finite_number(c.get("v7_rank_score")),
            "v6_score": _finite_number(c.get("v6_score")),
            "industry_score": _finite_number(c.get("industry_score")),
            "market_score": _finite_number(c.get("market_score")),
            "decision": "SHADOW_BUY_CANDIDATE",
        }
        for i, c in enumerate(selected)
    ]

    selected_symbols = {a["symbol"] for a in allocations}
    rejected = []
    for c, v in validations:
        symbol = v["symbol"]
        if symbol in selected_symbols:
            continue
        reasons = list(v["reasons"])
        if symbol in held:
            reasons.append("ALREADY_HELD")
        if symbol in pending:
            reasons.append("ALREADY_PENDING")
        if v["passed"] and not reasons:
            reasons.append("PORTFOLIO_CAP")
        rejected.append({"symbol": symbol, "reasons": reasons})

    return {
        "allocations": allocations,
        "rejected": rejected,
        "target_exposure_pct": target_exposure,
    }
