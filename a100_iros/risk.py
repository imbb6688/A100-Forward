from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_FLOOR
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Holding:
    ticker: str
    market_value: float
    industry: str = ""
    theme: str = ""
    beta: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.ticker.strip():
            raise ValueError("ticker must not be empty")
        if self.market_value < 0:
            raise ValueError("market_value must be non-negative")


@dataclass(frozen=True)
class PortfolioRiskSummary:
    total_market_value: float
    ticker_weights: Dict[str, float]
    industry_weights: Dict[str, float]
    theme_weights: Dict[str, float]
    weighted_beta: Optional[float]
    concentration_hhi: float
    largest_position_weight: float
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "total_market_value": self.total_market_value,
            "ticker_weights": dict(self.ticker_weights),
            "industry_weights": dict(self.industry_weights),
            "theme_weights": dict(self.theme_weights),
            "weighted_beta": self.weighted_beta,
            "concentration_hhi": self.concentration_hhi,
            "largest_position_weight": self.largest_position_weight,
            "warnings": list(self.warnings),
        }


def summarize_portfolio(holdings: List[Holding]) -> PortfolioRiskSummary:
    total = sum(float(item.market_value) for item in holdings)
    if total <= 0:
        return PortfolioRiskSummary(
            total_market_value=0.0,
            ticker_weights={},
            industry_weights={},
            theme_weights={},
            weighted_beta=None,
            concentration_hhi=0.0,
            largest_position_weight=0.0,
            warnings=["portfolio has no positive market value"],
        )

    ticker_weights: Dict[str, float] = {}
    industry_weights: Dict[str, float] = {}
    theme_weights: Dict[str, float] = {}
    beta_weighted_sum = 0.0
    beta_weight_sum = 0.0

    for item in holdings:
        weight = float(item.market_value) / total
        ticker = item.ticker.strip().upper()
        ticker_weights[ticker] = ticker_weights.get(ticker, 0.0) + weight
        if item.industry.strip():
            industry_weights[item.industry.strip()] = industry_weights.get(item.industry.strip(), 0.0) + weight
        if item.theme.strip():
            theme_weights[item.theme.strip()] = theme_weights.get(item.theme.strip(), 0.0) + weight
        if item.beta is not None:
            beta_weighted_sum += weight * float(item.beta)
            beta_weight_sum += weight

    hhi = sum(weight * weight for weight in ticker_weights.values())
    largest = max(ticker_weights.values(), default=0.0)
    weighted_beta = None if beta_weight_sum <= 0 else beta_weighted_sum / beta_weight_sum

    warnings: List[str] = []
    if largest > 0.25:
        warnings.append("single-name exposure exceeds 25% of invested market value")
    for name, weight in sorted(industry_weights.items(), key=lambda pair: pair[1], reverse=True):
        if weight > 0.40:
            warnings.append(f"industry exposure exceeds 40%: {name}={weight:.1%}")
    for name, weight in sorted(theme_weights.items(), key=lambda pair: pair[1], reverse=True):
        if weight > 0.50:
            warnings.append(f"theme exposure exceeds 50%: {name}={weight:.1%}")

    return PortfolioRiskSummary(
        total_market_value=round(total, 6),
        ticker_weights={k: round(v, 6) for k, v in ticker_weights.items()},
        industry_weights={k: round(v, 6) for k, v in industry_weights.items()},
        theme_weights={k: round(v, 6) for k, v in theme_weights.items()},
        weighted_beta=None if weighted_beta is None else round(weighted_beta, 6),
        concentration_hhi=round(hhi, 6),
        largest_position_weight=round(largest, 6),
        warnings=warnings,
    )


@dataclass(frozen=True)
class RiskBudgetPosition:
    account_equity: float
    risk_fraction: float
    entry_price: float
    invalidation_price: float
    per_share_risk: float
    max_risk_amount: float
    raw_shares: int
    lot_size: int
    lot_adjusted_shares: int
    notional: float
    notional_fraction: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "account_equity": self.account_equity,
            "risk_fraction": self.risk_fraction,
            "entry_price": self.entry_price,
            "invalidation_price": self.invalidation_price,
            "per_share_risk": self.per_share_risk,
            "max_risk_amount": self.max_risk_amount,
            "raw_shares": self.raw_shares,
            "lot_size": self.lot_size,
            "lot_adjusted_shares": self.lot_adjusted_shares,
            "notional": self.notional,
            "notional_fraction": self.notional_fraction,
        }


def _d(value: float | int) -> Decimal:
    return Decimal(str(value))


def _floor_int(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def size_position_by_risk_budget(
    *,
    account_equity: float,
    risk_fraction: float,
    entry_price: float,
    invalidation_price: float,
    lot_size: int = 100,
    max_notional_fraction: float = 1.0,
) -> RiskBudgetPosition:
    """Mechanical research helper, not an order generator.

    Position size is capped by both loss-at-invalidation budget and a notional cap.
    Decimal arithmetic is used for the sizing path so ordinary quoted prices do not
    lose a board lot because of binary floating-point representation error.
    """
    if account_equity <= 0:
        raise ValueError("account_equity must be positive")
    if not 0 < risk_fraction <= 1:
        raise ValueError("risk_fraction must be in (0, 1]")
    if entry_price <= 0 or invalidation_price <= 0:
        raise ValueError("prices must be positive")
    if entry_price == invalidation_price:
        raise ValueError("entry_price and invalidation_price must differ")
    if lot_size <= 0:
        raise ValueError("lot_size must be positive")
    if not 0 < max_notional_fraction <= 1:
        raise ValueError("max_notional_fraction must be in (0, 1]")

    equity_d = _d(account_equity)
    risk_fraction_d = _d(risk_fraction)
    entry_d = _d(entry_price)
    invalidation_d = _d(invalidation_price)
    max_notional_fraction_d = _d(max_notional_fraction)

    per_share_risk_d = abs(entry_d - invalidation_d)
    max_risk_amount_d = equity_d * risk_fraction_d
    risk_limited_shares = _floor_int(max_risk_amount_d / per_share_risk_d)
    notional_limited_shares = _floor_int((equity_d * max_notional_fraction_d) / entry_d)
    raw_shares = max(0, min(risk_limited_shares, notional_limited_shares))
    lot_adjusted = (raw_shares // lot_size) * lot_size
    notional_d = _d(lot_adjusted) * entry_d

    return RiskBudgetPosition(
        account_equity=float(equity_d),
        risk_fraction=float(risk_fraction_d),
        entry_price=float(entry_d),
        invalidation_price=float(invalidation_d),
        per_share_risk=float(per_share_risk_d),
        max_risk_amount=float(max_risk_amount_d),
        raw_shares=raw_shares,
        lot_size=lot_size,
        lot_adjusted_shares=lot_adjusted,
        notional=float(notional_d),
        notional_fraction=float(notional_d / equity_d),
    )
