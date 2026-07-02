from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


ENGINE_VERSION = "exit-decision-v1.0.0"


@dataclass(frozen=True)
class PositionState:
    """Current open-position state required by the exit engine."""

    ticker: str
    entry_price: float
    shares: int
    current_price: float | None = None
    highest_price: float | None = None
    holding_days: int = 0
    stop_loss_price: float | None = None


@dataclass(frozen=True)
class ExitSignal:
    """A transparent scoring contribution from one exit rule."""

    name: str
    points: int
    reason: str


@dataclass(frozen=True)
class ExitDecision:
    """Serializable exit decision for one position/date snapshot."""

    engine_version: str
    ticker: str
    sell_score: int
    action: str
    sell_ratio: float
    sell_shares: int
    remaining_shares: int
    current_price: float
    pnl_pct: float
    risk_level: str
    risk_flags: list[str]
    reasons: list[str]
    signal_hits: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExitDecisionEngine:
    """ADE Exit Decision Engine v1.0.

    v1.0 uses daily OHLCV/indicator data and open-position state. It supports
    partial profit taking, full stop loss, trailing stop, trend/momentum exits,
    time exit, and gap-down risk handling.
    """

    REQUIRED_COLUMNS = {"High", "Low", "Close"}

    def evaluate(
        self,
        df: pd.DataFrame,
        position: PositionState | dict[str, Any],
        candidate: dict[str, Any] | None = None,
    ) -> ExitDecision:
        if df.empty:
            raise ValueError("Cannot evaluate exit decision on an empty dataframe")
        if len(df) < 2:
            raise ValueError("Exit decision requires at least 2 rows")

        data = self._normalize_position(position)
        self._validate_position(data)
        normalized = self._normalize_columns(df)
        self._validate_required_columns(normalized)

        row = normalized.iloc[-1]
        prev = normalized.iloc[-2]
        close = data.current_price if data.current_price is not None else self._safe_float(row, "Close")
        high = self._safe_float(row, "High")
        low = self._safe_float(row, "Low")
        open_price = self._safe_float(row, "Open", close)
        prev_close = self._safe_float(prev, "Close", close)
        ma20 = self._safe_float(row, "MA20")
        ma60 = self._safe_float(row, "MA60")
        ma120 = self._safe_float(row, "MA120")
        atr = self._safe_float(row, "ATR", self._safe_float(row, "ATR14", 0.0))
        rsi = self._safe_float(row, "RSI", 50.0)
        macd = self._safe_float(row, "MACD", 0.0)
        macd_signal = self._safe_float(row, "MACD_SIGNAL", 0.0)
        prev_macd = self._safe_float(prev, "MACD", macd)
        prev_macd_signal = self._safe_float(prev, "MACD_SIGNAL", macd_signal)
        vol20_ratio = self._safe_float(row, "VOL20_RATIO", 1.0)
        body_ratio = self._safe_float(row, "BODY_RATIO")
        is_bullish = self._safe_bool(row, "IS_BULLISH", close >= open_price)

        hits: list[ExitSignal] = []
        flags: list[str] = []

        pnl_pct = (close - data.entry_price) / data.entry_price
        highest_price = data.highest_price if data.highest_price is not None else max(high, close)
        drawdown_from_high = (close - highest_price) / highest_price if highest_price > 0 else 0.0
        candidate_score = int(candidate.get("score", 100)) if candidate else 100
        candidate_risk = str(candidate.get("risk_level", "LOW")) if candidate else "LOW"

        if pnl_pct >= 0.20:
            hits.append(ExitSignal("profit_20", 45, "Profit target +20% reached"))
        elif pnl_pct >= 0.10:
            hits.append(ExitSignal("profit_10", 25, "Profit target +10% reached"))

        if pnl_pct <= -0.05:
            hits.append(ExitSignal("stop_loss_5", 60, "Loss exceeded -5% stop threshold"))
            flags.append("Hard stop loss triggered")

        if data.stop_loss_price is not None and close <= data.stop_loss_price:
            hits.append(ExitSignal("manual_stop", 70, "Price reached configured stop-loss price"))
            flags.append("Configured stop loss triggered")

        if atr > 0 and close <= data.entry_price - 2 * atr:
            hits.append(ExitSignal("atr_stop", 55, "Price breached 2 ATR stop from entry"))
            flags.append("ATR stop triggered")

        if atr > 0 and highest_price > data.entry_price:
            trailing_stop = highest_price - 2 * atr
            if close <= trailing_stop:
                hits.append(ExitSignal("trailing_stop", 55, "Price breached 2 ATR trailing stop"))
                flags.append("Trailing stop triggered")
        elif highest_price > data.entry_price and drawdown_from_high <= -0.08:
            hits.append(ExitSignal("percent_trailing_stop", 45, "Price fell more than 8% from highest price"))
            flags.append("Percent trailing stop triggered")

        if close < ma20 and ma20 > 0:
            hits.append(ExitSignal("below_ma20", 20, "Price closed below MA20"))
        if close < ma60 and ma60 > 0:
            hits.append(ExitSignal("below_ma60", 30, "Price closed below MA60"))
        if close < ma120 and ma120 > 0:
            hits.append(ExitSignal("below_ma120", 40, "Price closed below MA120"))
            flags.append("Long-term trend broken")

        macd_dead_cross = macd < macd_signal and prev_macd >= prev_macd_signal
        if macd_dead_cross:
            hits.append(ExitSignal("macd_dead_cross", 25, "MACD crossed below signal"))

        if rsi >= 80 and pnl_pct > 0:
            hits.append(ExitSignal("rsi_overheated", 20, "RSI is overheated while position is profitable"))
        elif rsi <= 30 and pnl_pct < 0:
            hits.append(ExitSignal("rsi_breakdown", 20, "RSI is weak while position is losing"))

        if data.holding_days >= 30 and pnl_pct < 0.03:
            hits.append(ExitSignal("time_exit_30", 25, "Position underperformed after 30 holding days"))

        gap_down = prev_close > 0 and open_price <= prev_close * 0.95
        if gap_down:
            hits.append(ExitSignal("gap_down", 45, "Gap-down larger than 5% detected"))
            flags.append("Gap-down risk detected")

        if not is_bullish and body_ratio >= 0.6 and vol20_ratio >= 1.5:
            hits.append(ExitSignal("distribution_candle", 25, "High-volume bearish distribution candle"))

        if candidate_score < 55:
            hits.append(ExitSignal("candidate_deterioration", 25, "Candidate score deteriorated below C grade"))
        if candidate_risk == "HIGH":
            hits.append(ExitSignal("candidate_high_risk", 35, "Candidate engine reports high risk"))
            flags.append("Candidate risk is high")

        if high < low or close <= 0:
            flags.append("Invalid price state")

        sell_score = min(100, sum(hit.points for hit in hits))
        risk_level = self._risk_level(flags, sell_score)
        action, sell_ratio = self._action(sell_score, risk_level, pnl_pct, hits)
        sell_shares = min(data.shares, int(round(data.shares * sell_ratio)))
        remaining_shares = max(0, data.shares - sell_shares)

        return ExitDecision(
            engine_version=ENGINE_VERSION,
            ticker=data.ticker,
            sell_score=int(sell_score),
            action=action,
            sell_ratio=round(sell_ratio, 4),
            sell_shares=sell_shares,
            remaining_shares=remaining_shares,
            current_price=round(close, 4),
            pnl_pct=round(pnl_pct, 4),
            risk_level=risk_level,
            risk_flags=flags,
            reasons=[hit.reason for hit in hits],
            signal_hits=[asdict(hit) for hit in hits],
        )

    def _normalize_position(self, position: PositionState | dict[str, Any]) -> PositionState:
        if isinstance(position, PositionState):
            return position
        return PositionState(
            ticker=str(position["ticker"]),
            entry_price=float(position["entry_price"]),
            shares=int(position["shares"]),
            current_price=position.get("current_price"),
            highest_price=position.get("highest_price"),
            holding_days=int(position.get("holding_days", 0)),
            stop_loss_price=position.get("stop_loss_price"),
        )

    def _validate_position(self, position: PositionState) -> None:
        if position.entry_price <= 0:
            raise ValueError("entry_price must be greater than zero")
        if position.shares <= 0:
            raise ValueError("shares must be greater than zero")
        if position.holding_days < 0:
            raise ValueError("holding_days cannot be negative")

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        normalized = df.copy()
        aliases = {
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
        for src, dst in aliases.items():
            if src in normalized.columns and dst not in normalized.columns:
                normalized[dst] = normalized[src]
        return normalized

    def _validate_required_columns(self, df: pd.DataFrame) -> None:
        missing = sorted(self.REQUIRED_COLUMNS - set(df.columns))
        if missing:
            raise ValueError(f"Exit decision requires columns: {', '.join(missing)}")

    def _safe_float(self, row: pd.Series, key: str, default: float = 0.0) -> float:
        value = row.get(key, default)
        if pd.isna(value):
            return default
        return float(value)

    def _safe_bool(self, row: pd.Series, key: str, default: bool = False) -> bool:
        value = row.get(key, default)
        if pd.isna(value):
            return default
        return bool(value)

    def _risk_level(self, flags: list[str], sell_score: int) -> str:
        high_flags = {
            "Hard stop loss triggered",
            "Configured stop loss triggered",
            "ATR stop triggered",
            "Trailing stop triggered",
            "Gap-down risk detected",
            "Invalid price state",
        }
        if any(flag in high_flags for flag in flags) or sell_score >= 80:
            return "HIGH"
        if flags or sell_score >= 50:
            return "MEDIUM"
        return "LOW"

    def _action(
        self,
        sell_score: int,
        risk_level: str,
        pnl_pct: float,
        hits: list[ExitSignal],
    ) -> tuple[str, float]:
        hit_names = {hit.name for hit in hits}
        force_full_exit = {
            "stop_loss_5",
            "manual_stop",
            "atr_stop",
            "trailing_stop",
            "percent_trailing_stop",
            "gap_down",
            "below_ma120",
            "candidate_high_risk",
        }
        if "profit_20" in hit_names:
            return "SELL_ALL", 1.0
        if risk_level == "HIGH" and hit_names.intersection(force_full_exit):
            return "SELL_ALL", 1.0
        if sell_score >= 85 and "time_exit_30" not in hit_names:
            return "SELL_ALL", 1.0
        if sell_score >= 65:
            return "SELL_50", 0.5
        if "profit_10" in hit_names or sell_score >= 40:
            return "SELL_25", 0.25
        if sell_score >= 20 or pnl_pct < 0:
            return "WATCH", 0.0
        return "HOLD", 0.0


def evaluate_exit(
    df: pd.DataFrame,
    position: PositionState | dict[str, Any],
    candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Backward-compatible helper returning a dict decision payload."""

    return ExitDecisionEngine().evaluate(df=df, position=position, candidate=candidate).to_dict()
