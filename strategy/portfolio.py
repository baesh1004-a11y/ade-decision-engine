from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


ENGINE_VERSION = "portfolio-manager-v1.0.0"


@dataclass(frozen=True)
class Holding:
    ticker: str
    market: str
    sector: str
    quantity: int
    price: float
    cost_basis: float | None = None

    @property
    def value(self) -> float:
        return self.quantity * self.price


@dataclass(frozen=True)
class PortfolioState:
    account_balance: float
    cash: float
    holdings: list[Holding]
    market_regime: str = "SIDEWAY"


@dataclass(frozen=True)
class PortfolioRecommendation:
    ticker: str
    action: str
    current_weight: float
    target_weight: float
    trade_value: float
    reason: str


@dataclass(frozen=True)
class PortfolioDecision:
    engine_version: str
    portfolio_score: int
    action: str
    total_value: float
    cash_weight: float
    target_cash_weight: float
    position_count: int
    max_position_weight: float
    max_sector_weight: float
    risk_flags: list[str]
    recommendations: list[dict[str, Any]]
    sector_weights: dict[str, float]
    market_weights: dict[str, float]
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PortfolioManagerEngine:
    """ADE Portfolio Manager Engine v1.0.

    This engine evaluates account-level allocation quality and recommends
    rebalancing actions. It does not place orders. It only produces auditable
    portfolio recommendations.
    """

    CASH_TARGETS = {
        "BULL": 0.10,
        "SIDEWAY": 0.20,
        "BEAR": 0.50,
    }

    def __init__(
        self,
        max_positions: int = 10,
        max_position_weight: float = 0.20,
        max_sector_weight: float = 0.30,
        max_market_weight: float = 0.70,
        min_trade_value: float = 100_000,
    ) -> None:
        self.max_positions = max_positions
        self.max_position_weight = max_position_weight
        self.max_sector_weight = max_sector_weight
        self.max_market_weight = max_market_weight
        self.min_trade_value = min_trade_value

    def evaluate(self, portfolio: PortfolioState | dict[str, Any]) -> PortfolioDecision:
        state = self._normalize(portfolio)
        self._validate(state)

        total_value = self._total_value(state)
        cash_weight = state.cash / total_value
        target_cash_weight = self.CASH_TARGETS.get(state.market_regime.upper(), 0.20)
        position_weights = self._position_weights(state.holdings, total_value)
        sector_weights = self._group_weights(state.holdings, total_value, "sector")
        market_weights = self._group_weights(state.holdings, total_value, "market")

        flags: list[str] = []
        reasons: list[str] = []
        recs: list[PortfolioRecommendation] = []

        if len(state.holdings) > self.max_positions:
            flags.append("Too many positions")
            reasons.append("Position count exceeds max_positions")

        if cash_weight < target_cash_weight * 0.8:
            flags.append("Cash below target")
            reasons.append("Cash is below target for current market regime")
        elif cash_weight > target_cash_weight * 1.5:
            flags.append("Cash above target")
            reasons.append("Cash is above target and may reduce return potential")

        for holding in state.holdings:
            weight = position_weights[holding.ticker]
            if weight > self.max_position_weight:
                excess_value = (weight - self.max_position_weight) * total_value
                recs.append(
                    PortfolioRecommendation(
                        ticker=holding.ticker,
                        action="TRIM",
                        current_weight=round(weight, 4),
                        target_weight=self.max_position_weight,
                        trade_value=round(excess_value, 2),
                        reason="Position exceeds max single-position weight",
                    )
                )
                flags.append(f"{holding.ticker} overweight")

        for sector, weight in sector_weights.items():
            if weight > self.max_sector_weight:
                flags.append(f"{sector} sector overweight")
                reasons.append(f"Sector {sector} exceeds max sector weight")

        for market, weight in market_weights.items():
            if weight > self.max_market_weight:
                flags.append(f"{market} market overweight")
                reasons.append(f"Market {market} exceeds max market weight")

        cash_gap = target_cash_weight - cash_weight
        if cash_gap > 0.03:
            recs.append(
                PortfolioRecommendation(
                    ticker="CASH",
                    action="RAISE_CASH",
                    current_weight=round(cash_weight, 4),
                    target_weight=round(target_cash_weight, 4),
                    trade_value=round(cash_gap * total_value, 2),
                    reason="Increase cash toward market-regime target",
                )
            )
        elif cash_gap < -0.05:
            recs.append(
                PortfolioRecommendation(
                    ticker="CASH",
                    action="DEPLOY_CASH",
                    current_weight=round(cash_weight, 4),
                    target_weight=round(target_cash_weight, 4),
                    trade_value=round(abs(cash_gap) * total_value, 2),
                    reason="Cash is materially above target",
                )
            )

        recs = [rec for rec in recs if rec.trade_value >= self.min_trade_value]
        portfolio_score = self._score(flags, cash_weight, target_cash_weight, len(recs))
        action = self._action(portfolio_score, recs)

        if not reasons and not flags:
            reasons.append("Portfolio is within configured allocation limits")

        return PortfolioDecision(
            engine_version=ENGINE_VERSION,
            portfolio_score=portfolio_score,
            action=action,
            total_value=round(total_value, 2),
            cash_weight=round(cash_weight, 4),
            target_cash_weight=round(target_cash_weight, 4),
            position_count=len(state.holdings),
            max_position_weight=self.max_position_weight,
            max_sector_weight=self.max_sector_weight,
            risk_flags=flags,
            recommendations=[asdict(rec) for rec in recs],
            sector_weights={key: round(value, 4) for key, value in sector_weights.items()},
            market_weights={key: round(value, 4) for key, value in market_weights.items()},
            reasons=reasons,
        )

    def _normalize(self, payload: PortfolioState | dict[str, Any]) -> PortfolioState:
        if isinstance(payload, PortfolioState):
            return payload
        holdings = [h if isinstance(h, Holding) else Holding(**h) for h in payload.get("holdings", [])]
        return PortfolioState(
            account_balance=float(payload["account_balance"]),
            cash=float(payload.get("cash", 0.0)),
            holdings=holdings,
            market_regime=str(payload.get("market_regime", "SIDEWAY")),
        )

    def _validate(self, state: PortfolioState) -> None:
        if state.account_balance <= 0:
            raise ValueError("account_balance must be greater than zero")
        if state.cash < 0:
            raise ValueError("cash cannot be negative")
        for holding in state.holdings:
            if holding.quantity < 0:
                raise ValueError("holding quantity cannot be negative")
            if holding.price < 0:
                raise ValueError("holding price cannot be negative")

    def _total_value(self, state: PortfolioState) -> float:
        holdings_value = sum(holding.value for holding in state.holdings)
        total = state.cash + holdings_value
        return total if total > 0 else state.account_balance

    def _position_weights(self, holdings: list[Holding], total_value: float) -> dict[str, float]:
        weights: dict[str, float] = {}
        for holding in holdings:
            weights[holding.ticker] = weights.get(holding.ticker, 0.0) + holding.value / total_value
        return weights

    def _group_weights(self, holdings: list[Holding], total_value: float, field: str) -> dict[str, float]:
        weights: dict[str, float] = {}
        for holding in holdings:
            key = getattr(holding, field) or "UNKNOWN"
            weights[key] = weights.get(key, 0.0) + holding.value / total_value
        return weights

    def _score(self, flags: list[str], cash_weight: float, target_cash_weight: float, rec_count: int) -> int:
        penalty = len(flags) * 12 + rec_count * 8
        penalty += int(abs(cash_weight - target_cash_weight) * 100)
        return max(0, min(100, 100 - penalty))

    def _action(self, score: int, recommendations: list[PortfolioRecommendation]) -> str:
        if not recommendations and score >= 85:
            return "HOLD"
        if score >= 70:
            return "MONITOR"
        return "REBALANCE"


def evaluate_portfolio(payload: PortfolioState | dict[str, Any]) -> dict[str, Any]:
    return PortfolioManagerEngine().evaluate(payload).to_dict()
