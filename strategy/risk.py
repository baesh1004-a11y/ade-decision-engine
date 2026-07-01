from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


ENGINE_VERSION = "risk-engine-v1.0.0"


@dataclass(frozen=True)
class RiskInput:
    account_balance: float
    equity_peak: float
    daily_pnl: float = 0.0
    open_risk: float = 0.0
    portfolio_heat: float = 0.0
    cash_weight: float = 0.0
    vix: float | None = None
    market_regime: str = "SIDEWAY"
    consecutive_losses: int = 0


@dataclass(frozen=True)
class RiskDecision:
    engine_version: str
    risk_score: int
    risk_level: str
    action: str
    trade_allowed: bool
    max_new_position_weight: float
    target_cash_weight: float
    daily_loss_pct: float
    drawdown_pct: float
    risk_flags: list[str]
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RiskEngine:
    """ADE Risk Engine v1.0.

    Account-level survival engine. It can allow trading, reduce size, pause new
    entries, or force deleveraging based on daily loss, drawdown, VIX, portfolio
    heat, and consecutive losses.
    """

    def __init__(
        self,
        daily_stop_loss: float = -0.03,
        max_drawdown_warn: float = -0.10,
        max_drawdown_stop: float = -0.15,
        max_portfolio_heat: float = 0.06,
    ) -> None:
        self.daily_stop_loss = daily_stop_loss
        self.max_drawdown_warn = max_drawdown_warn
        self.max_drawdown_stop = max_drawdown_stop
        self.max_portfolio_heat = max_portfolio_heat

    def evaluate(self, payload: RiskInput | dict[str, Any]) -> RiskDecision:
        data = self._normalize(payload)
        self._validate(data)

        daily_loss_pct = data.daily_pnl / data.account_balance
        drawdown_pct = (data.account_balance - data.equity_peak) / data.equity_peak
        flags: list[str] = []
        reasons: list[str] = []

        if daily_loss_pct <= self.daily_stop_loss:
            flags.append("Daily stop loss breached")
            reasons.append("Daily loss exceeded configured stop threshold")

        if drawdown_pct <= self.max_drawdown_stop:
            flags.append("Max drawdown stop breached")
            reasons.append("Account drawdown exceeded hard stop threshold")
        elif drawdown_pct <= self.max_drawdown_warn:
            flags.append("Max drawdown warning")
            reasons.append("Account drawdown exceeded warning threshold")

        if data.portfolio_heat >= self.max_portfolio_heat:
            flags.append("Portfolio heat limit breached")
            reasons.append("Open portfolio risk is above configured heat limit")

        if data.vix is not None:
            if data.vix >= 40:
                flags.append("VIX crisis regime")
                reasons.append("VIX is in crisis regime")
            elif data.vix >= 30:
                flags.append("VIX high regime")
                reasons.append("VIX is elevated")

        if data.market_regime.upper() == "BEAR":
            flags.append("Bear market regime")
            reasons.append("Market regime requires defensive allocation")

        if data.consecutive_losses >= 3:
            flags.append("Consecutive loss streak")
            reasons.append("Loss streak requires reduced trading intensity")

        score = self._risk_score(flags, daily_loss_pct, drawdown_pct, data)
        level = self._risk_level(score, flags)
        action = self._action(level, flags)
        trade_allowed = action not in {"PAUSE_TRADING", "FORCE_DELEVERAGE"}
        max_new_weight = self._max_new_position_weight(level, flags)
        target_cash = self._target_cash_weight(level, flags, data)

        if not reasons:
            reasons.append("Account risk is within configured limits")

        return RiskDecision(
            engine_version=ENGINE_VERSION,
            risk_score=score,
            risk_level=level,
            action=action,
            trade_allowed=trade_allowed,
            max_new_position_weight=round(max_new_weight, 4),
            target_cash_weight=round(target_cash, 4),
            daily_loss_pct=round(daily_loss_pct, 4),
            drawdown_pct=round(drawdown_pct, 4),
            risk_flags=flags,
            reasons=reasons,
        )

    def _normalize(self, payload: RiskInput | dict[str, Any]) -> RiskInput:
        if isinstance(payload, RiskInput):
            return payload
        return RiskInput(
            account_balance=float(payload["account_balance"]),
            equity_peak=float(payload["equity_peak"]),
            daily_pnl=float(payload.get("daily_pnl", 0.0)),
            open_risk=float(payload.get("open_risk", 0.0)),
            portfolio_heat=float(payload.get("portfolio_heat", 0.0)),
            cash_weight=float(payload.get("cash_weight", 0.0)),
            vix=payload.get("vix"),
            market_regime=str(payload.get("market_regime", "SIDEWAY")),
            consecutive_losses=int(payload.get("consecutive_losses", 0)),
        )

    def _validate(self, data: RiskInput) -> None:
        if data.account_balance <= 0:
            raise ValueError("account_balance must be greater than zero")
        if data.equity_peak <= 0:
            raise ValueError("equity_peak must be greater than zero")
        if data.consecutive_losses < 0:
            raise ValueError("consecutive_losses cannot be negative")
        if data.portfolio_heat < 0:
            raise ValueError("portfolio_heat cannot be negative")
        if data.cash_weight < 0:
            raise ValueError("cash_weight cannot be negative")

    def _risk_score(self, flags: list[str], daily_loss_pct: float, drawdown_pct: float, data: RiskInput) -> int:
        score = 0
        score += min(35, int(abs(min(0.0, daily_loss_pct)) * 1000))
        score += min(35, int(abs(min(0.0, drawdown_pct)) * 350))
        score += min(20, int(data.portfolio_heat * 250))
        if data.vix is not None:
            score += max(0, min(20, int((data.vix - 20) * 1.0)))
        score += len(flags) * 6
        return max(0, min(100, score))

    def _risk_level(self, score: int, flags: list[str]) -> str:
        hard_flags = {"Daily stop loss breached", "Max drawdown stop breached", "VIX crisis regime"}
        if any(flag in hard_flags for flag in flags) or score >= 80:
            return "CRITICAL"
        if score >= 55:
            return "HIGH"
        if score >= 30:
            return "MEDIUM"
        return "LOW"

    def _action(self, level: str, flags: list[str]) -> str:
        if level == "CRITICAL":
            if "Max drawdown stop breached" in flags or "VIX crisis regime" in flags:
                return "FORCE_DELEVERAGE"
            return "PAUSE_TRADING"
        if level == "HIGH":
            return "REDUCE_RISK"
        if level == "MEDIUM":
            return "LIMIT_NEW_TRADES"
        return "ALLOW_TRADING"

    def _max_new_position_weight(self, level: str, flags: list[str]) -> float:
        if level == "CRITICAL":
            return 0.0
        if level == "HIGH":
            return 0.03
        if level == "MEDIUM":
            return 0.06
        if "Bear market regime" in flags:
            return 0.05
        return 0.10

    def _target_cash_weight(self, level: str, flags: list[str], data: RiskInput) -> float:
        base = {"BULL": 0.10, "SIDEWAY": 0.20, "BEAR": 0.50}.get(data.market_regime.upper(), 0.20)
        if level == "CRITICAL":
            return max(base, 0.70)
        if level == "HIGH":
            return max(base, 0.50)
        if level == "MEDIUM":
            return max(base, 0.30)
        return base


def evaluate_risk(payload: RiskInput | dict[str, Any]) -> dict[str, Any]:
    return RiskEngine().evaluate(payload).to_dict()
