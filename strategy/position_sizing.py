from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import floor
from typing import Any


ENGINE_VERSION = "position-sizing-v1.0.0"


@dataclass(frozen=True)
class AccountState:
    """Portfolio/account inputs required by the position sizing engine."""

    account_balance: float
    cash: float | None = None
    current_position_value: float = 0.0
    sector_exposure: float = 0.0
    portfolio_heat: float = 0.0


@dataclass(frozen=True)
class PositionSizingInput:
    """Normalized input payload for one sizing recommendation."""

    ticker: str
    price: float
    grade: str
    confidence: float
    risk_level: str = "LOW"
    atr: float | None = None
    stop_loss_price: float | None = None
    market_regime: str = "SIDEWAY"
    expected_return: float | None = None
    win_rate: float | None = None
    payoff_ratio: float | None = None
    account: AccountState = field(default_factory=lambda: AccountState(account_balance=0.0))


@dataclass(frozen=True)
class PositionRecommendation:
    """Serializable output record for position sizing."""

    engine_version: str
    ticker: str
    recommended_weight: float
    buy_amount: float
    shares: int
    max_loss: float
    risk_score: int
    kelly_weight: float
    atr_risk: float
    sector_adjustment: float
    heat_adjustment: float
    cash_limited: bool
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PositionSizingEngine:
    """ADE Position Sizing Engine v1.0.

    The engine converts a candidate decision into a risk-aware allocation.
    It combines grade-based base weight, confidence adjustment, market regime,
    ATR/stop-loss risk, Kelly cap, sector exposure, portfolio heat, and cash cap.
    """

    BASE_WEIGHTS = {
        "S": 0.15,
        "A": 0.10,
        "B": 0.06,
        "C": 0.03,
        "D": 0.01,
        "F": 0.0,
    }
    MARKET_MULTIPLIERS = {
        "BULL": 1.00,
        "SIDEWAY": 0.80,
        "BEAR": 0.50,
    }
    RISK_MULTIPLIERS = {
        "LOW": 1.00,
        "MEDIUM": 0.70,
        "HIGH": 0.35,
    }

    def __init__(
        self,
        max_position_weight: float = 0.15,
        max_trade_risk: float = 0.01,
        max_sector_exposure: float = 0.30,
        max_portfolio_heat: float = 0.06,
    ) -> None:
        self.max_position_weight = max_position_weight
        self.max_trade_risk = max_trade_risk
        self.max_sector_exposure = max_sector_exposure
        self.max_portfolio_heat = max_portfolio_heat

    def recommend(self, payload: PositionSizingInput | dict[str, Any]) -> PositionRecommendation:
        data = self._normalize(payload)
        self._validate(data)

        reasons: list[str] = []
        base_weight = self.BASE_WEIGHTS.get(data.grade.upper(), 0.0)
        reasons.append(f"Base weight from grade {data.grade.upper()}: {base_weight:.2%}")

        confidence_multiplier = self._confidence_multiplier(data.confidence)
        market_multiplier = self.MARKET_MULTIPLIERS.get(data.market_regime.upper(), 0.80)
        risk_multiplier = self.RISK_MULTIPLIERS.get(data.risk_level.upper(), 0.70)
        atr_multiplier, atr_risk = self._atr_adjustment(data)
        sector_adjustment = self._sector_adjustment(data.account.sector_exposure)
        heat_adjustment = self._heat_adjustment(data.account.portfolio_heat)
        kelly_weight = self._kelly_weight(data.win_rate, data.payoff_ratio)

        raw_weight = (
            base_weight
            * confidence_multiplier
            * market_multiplier
            * risk_multiplier
            * atr_multiplier
            * sector_adjustment
            * heat_adjustment
        )

        capped_weight = min(raw_weight, self.max_position_weight)
        if kelly_weight > 0:
            capped_weight = min(capped_weight, kelly_weight)
            reasons.append(f"Kelly cap applied: {kelly_weight:.2%}")

        risk_capped_weight = self._risk_cap_weight(data)
        if risk_capped_weight is not None:
            capped_weight = min(capped_weight, risk_capped_weight)
            reasons.append(f"Stop/ATR risk cap applied: {risk_capped_weight:.2%}")

        available_cash = data.account.cash if data.account.cash is not None else data.account.account_balance
        cash_weight = max(0.0, available_cash / data.account.account_balance)
        cash_limited = capped_weight > cash_weight
        final_weight = max(0.0, min(capped_weight, cash_weight))

        buy_amount = data.account.account_balance * final_weight
        shares = floor(buy_amount / data.price)
        executable_amount = shares * data.price
        executable_weight = executable_amount / data.account.account_balance
        max_loss = self._max_loss(data, shares)
        risk_score = self._risk_score(data, executable_weight, atr_risk)

        if cash_limited:
            reasons.append("Allocation reduced by available cash")
        if sector_adjustment < 1:
            reasons.append("Allocation reduced by sector exposure")
        if heat_adjustment < 1:
            reasons.append("Allocation reduced by portfolio heat")
        if atr_multiplier < 1:
            reasons.append("Allocation reduced by volatility/ATR risk")
        if shares == 0:
            reasons.append("No executable share count under current constraints")

        return PositionRecommendation(
            engine_version=ENGINE_VERSION,
            ticker=data.ticker,
            recommended_weight=round(executable_weight, 4),
            buy_amount=round(executable_amount, 2),
            shares=shares,
            max_loss=round(max_loss, 2),
            risk_score=risk_score,
            kelly_weight=round(kelly_weight, 4),
            atr_risk=round(atr_risk, 4),
            sector_adjustment=round(sector_adjustment, 4),
            heat_adjustment=round(heat_adjustment, 4),
            cash_limited=cash_limited,
            reasons=reasons,
        )

    def _normalize(self, payload: PositionSizingInput | dict[str, Any]) -> PositionSizingInput:
        if isinstance(payload, PositionSizingInput):
            return payload

        account_payload = payload.get("account", {})
        account = account_payload if isinstance(account_payload, AccountState) else AccountState(**account_payload)
        return PositionSizingInput(
            ticker=payload["ticker"],
            price=float(payload["price"]),
            grade=str(payload["grade"]),
            confidence=float(payload.get("confidence", 0.0)),
            risk_level=str(payload.get("risk_level", "LOW")),
            atr=payload.get("atr"),
            stop_loss_price=payload.get("stop_loss_price"),
            market_regime=str(payload.get("market_regime", "SIDEWAY")),
            expected_return=payload.get("expected_return"),
            win_rate=payload.get("win_rate"),
            payoff_ratio=payload.get("payoff_ratio"),
            account=account,
        )

    def _validate(self, data: PositionSizingInput) -> None:
        if data.price <= 0:
            raise ValueError("price must be greater than zero")
        if data.account.account_balance <= 0:
            raise ValueError("account_balance must be greater than zero")
        if data.account.cash is not None and data.account.cash < 0:
            raise ValueError("cash cannot be negative")
        if not 0 <= data.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if data.atr is not None and data.atr < 0:
            raise ValueError("atr cannot be negative")

    def _confidence_multiplier(self, confidence: float) -> float:
        if confidence >= 0.90:
            return 1.20
        if confidence >= 0.80:
            return 1.10
        if confidence >= 0.70:
            return 1.00
        if confidence >= 0.60:
            return 0.80
        return 0.50

    def _atr_adjustment(self, data: PositionSizingInput) -> tuple[float, float]:
        if not data.atr:
            return 1.0, 0.0
        atr_ratio = data.atr / data.price
        if atr_ratio >= 0.08:
            return 0.50, atr_ratio
        if atr_ratio >= 0.05:
            return 0.70, atr_ratio
        if atr_ratio >= 0.03:
            return 0.90, atr_ratio
        return 1.05, atr_ratio

    def _sector_adjustment(self, sector_exposure: float) -> float:
        if sector_exposure <= 0:
            return 1.0
        if sector_exposure >= self.max_sector_exposure:
            return 0.0
        remaining = self.max_sector_exposure - sector_exposure
        return max(0.0, min(1.0, remaining / self.max_sector_exposure))

    def _heat_adjustment(self, portfolio_heat: float) -> float:
        if portfolio_heat <= 0:
            return 1.0
        if portfolio_heat >= self.max_portfolio_heat:
            return 0.0
        remaining = self.max_portfolio_heat - portfolio_heat
        return max(0.0, min(1.0, remaining / self.max_portfolio_heat))

    def _kelly_weight(self, win_rate: float | None, payoff_ratio: float | None) -> float:
        if win_rate is None or payoff_ratio is None or payoff_ratio <= 0:
            return 0.0
        raw_kelly = win_rate - ((1 - win_rate) / payoff_ratio)
        half_kelly = max(0.0, raw_kelly * 0.5)
        return min(half_kelly, self.max_position_weight)

    def _risk_cap_weight(self, data: PositionSizingInput) -> float | None:
        risk_per_share = self._risk_per_share(data)
        if risk_per_share <= 0:
            return None
        max_risk_amount = data.account.account_balance * self.max_trade_risk
        max_shares_by_risk = floor(max_risk_amount / risk_per_share)
        return (max_shares_by_risk * data.price) / data.account.account_balance

    def _risk_per_share(self, data: PositionSizingInput) -> float:
        if data.stop_loss_price is not None and data.stop_loss_price < data.price:
            return data.price - data.stop_loss_price
        if data.atr is not None and data.atr > 0:
            return data.atr * 2
        return 0.0

    def _max_loss(self, data: PositionSizingInput, shares: int) -> float:
        return shares * self._risk_per_share(data)

    def _risk_score(self, data: PositionSizingInput, weight: float, atr_risk: float) -> int:
        score = weight * 100
        score += atr_risk * 100
        score += data.account.sector_exposure * 50
        score += data.account.portfolio_heat * 200
        if data.risk_level.upper() == "MEDIUM":
            score += 10
        elif data.risk_level.upper() == "HIGH":
            score += 25
        return int(max(0, min(100, round(score))))


def recommend_position(payload: PositionSizingInput | dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible helper returning a dict payload."""

    return PositionSizingEngine().recommend(payload).to_dict()
