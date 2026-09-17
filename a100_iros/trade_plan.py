from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class TradePlan:
    plan_id: str
    ticker: str
    entry_conditions: List[str]
    invalidation_conditions: List[str]
    exit_conditions: List[str]
    initial_position_fraction: Optional[float] = None
    maximum_position_fraction: Optional[float] = None
    add_conditions: List[str] = field(default_factory=list)
    reduce_conditions: List[str] = field(default_factory=list)
    time_stop: str = ""
    event_stop: str = ""
    portfolio_risk_note: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.plan_id.strip():
            raise ValueError("plan_id must not be empty")
        if not self.ticker.strip():
            raise ValueError("ticker must not be empty")
        if not self.entry_conditions:
            raise ValueError("entry_conditions must not be empty")
        if not self.invalidation_conditions:
            raise ValueError("invalidation_conditions must not be empty")
        if not self.exit_conditions:
            raise ValueError("exit_conditions must not be empty")
        for name in ("initial_position_fraction", "maximum_position_fraction"):
            value = getattr(self, name)
            if value is not None and not 0.0 < value <= 1.0:
                raise ValueError(f"{name} must be in (0, 1]")
        if (
            self.initial_position_fraction is not None
            and self.maximum_position_fraction is not None
            and self.initial_position_fraction > self.maximum_position_fraction
        ):
            raise ValueError("initial_position_fraction cannot exceed maximum_position_fraction")

    def to_dict(self) -> Dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "ticker": self.ticker.strip().upper(),
            "entry_conditions": list(self.entry_conditions),
            "invalidation_conditions": list(self.invalidation_conditions),
            "exit_conditions": list(self.exit_conditions),
            "initial_position_fraction": self.initial_position_fraction,
            "maximum_position_fraction": self.maximum_position_fraction,
            "add_conditions": list(self.add_conditions),
            "reduce_conditions": list(self.reduce_conditions),
            "time_stop": self.time_stop,
            "event_stop": self.event_stop,
            "portfolio_risk_note": self.portfolio_risk_note,
            "created_at": self.created_at,
        }


def trade_plan_from_dict(data: Dict[str, object]) -> TradePlan:
    return TradePlan(
        plan_id=str(data["plan_id"]),
        ticker=str(data["ticker"]),
        entry_conditions=[str(x) for x in data.get("entry_conditions", [])],
        invalidation_conditions=[str(x) for x in data.get("invalidation_conditions", [])],
        exit_conditions=[str(x) for x in data.get("exit_conditions", [])],
        initial_position_fraction=(
            None if data.get("initial_position_fraction") is None else float(data["initial_position_fraction"])
        ),
        maximum_position_fraction=(
            None if data.get("maximum_position_fraction") is None else float(data["maximum_position_fraction"])
        ),
        add_conditions=[str(x) for x in data.get("add_conditions", [])],
        reduce_conditions=[str(x) for x in data.get("reduce_conditions", [])],
        time_stop=str(data.get("time_stop", "")),
        event_stop=str(data.get("event_stop", "")),
        portfolio_risk_note=str(data.get("portfolio_risk_note", "")),
        created_at=str(data.get("created_at", "")),
    )
