from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


ENGINE_VERSION = "entry-timing-v1.0.0"


@dataclass(frozen=True)
class EntrySignal:
    """A transparent scoring contribution from one entry timing rule."""

    name: str
    points: int
    reason: str


@dataclass(frozen=True)
class EntryDecision:
    """Serializable entry timing decision for one ticker/date snapshot."""

    engine_version: str
    entry_score: int
    action: str
    order_type: str
    entry_price: float
    limit_price: float
    risk_level: str
    risk_flags: list[str]
    reasons: list[str]
    signal_hits: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EntryTimingEngine:
    """ADE Entry Timing Engine v1.0.

    v1.0 intentionally uses daily OHLCV/indicator data only. Intraday, orderbook,
    and execution microstructure signals should be added in v2.0 without breaking
    this public decision payload.
    """

    REQUIRED_COLUMNS = {"High", "Low", "Close"}

    def evaluate(
        self,
        df: pd.DataFrame,
        candidate: dict[str, Any] | None = None,
        position: dict[str, Any] | None = None,
        market_regime: str = "SIDEWAY",
    ) -> EntryDecision:
        if df.empty:
            raise ValueError("Cannot evaluate entry timing on an empty dataframe")
        if len(df) < 20:
            raise ValueError("Entry timing requires at least 20 rows")

        normalized = self._normalize_columns(df)
        self._validate_required_columns(normalized)

        row = normalized.iloc[-1]
        prev = normalized.iloc[-2]
        recent = normalized.tail(20)
        hits: list[EntrySignal] = []
        flags: list[str] = []

        close = self._safe_float(row, "Close")
        high = self._safe_float(row, "High")
        low = self._safe_float(row, "Low")
        ma20 = self._safe_float(row, "MA20")
        ma60 = self._safe_float(row, "MA60")
        ma120 = self._safe_float(row, "MA120")
        vol20_ratio = self._safe_float(row, "VOL20_RATIO")
        body_ratio = self._safe_float(row, "BODY_RATIO")
        is_bullish = self._safe_bool(row, "IS_BULLISH")
        sto_k = self._safe_float(row, "STO533_K", 50.0)
        sto_d = self._safe_float(row, "STO533_D", 50.0)
        prev_sto_k = self._safe_float(prev, "STO533_K", sto_k)
        prev_sto_d = self._safe_float(prev, "STO533_D", sto_d)
        rsi = self._safe_float(row, "RSI", 50.0)
        macd = self._safe_float(row, "MACD", 0.0)
        macd_signal = self._safe_float(row, "MACD_SIGNAL", 0.0)
        prev_macd = self._safe_float(prev, "MACD", macd)
        prev_macd_signal = self._safe_float(prev, "MACD_SIGNAL", macd_signal)

        candidate_score = int(candidate.get("score", 0)) if candidate else 0
        candidate_action = str(candidate.get("action", "BUY_CANDIDATE")) if candidate else "BUY_CANDIDATE"
        candidate_risk = str(candidate.get("risk_level", "LOW")) if candidate else "LOW"
        position_weight = float(position.get("recommended_weight", 1.0)) if position else 1.0
        position_shares = int(position.get("shares", 1)) if position else 1

        if candidate and candidate_action in {"REJECT", "NEUTRAL"}:
            flags.append("Candidate decision is not actionable")
        if candidate_risk == "HIGH":
            flags.append("Candidate risk is high")
        if position and (position_weight <= 0 or position_shares <= 0):
            flags.append("No executable position size")
        if str(market_regime).upper() == "BEAR":
            flags.append("Bear market entry discount required")

        trend_ok = (close > ma20 > ma60 > 0) or (close > ma20 > 0 and ma60 >= ma120 > 0)
        long_trend_ok = close >= ma120 > 0
        if trend_ok:
            hits.append(EntrySignal("trend_alignment", 20, "Price is aligned with short/mid trend"))
        if long_trend_ok:
            hits.append(EntrySignal("above_ma120", 10, "Price is above MA120"))
        if close > ma20 > 0 and is_bullish:
            hits.append(EntrySignal("ma20_support", 10, "Bullish close above MA20 support"))

        recent_high_before_today = float(recent.iloc[:-1]["High"].max()) if len(recent) > 1 else high
        breakout = high >= recent_high_before_today and close >= recent_high_before_today * 0.995
        if breakout and vol20_ratio >= 1.5:
            hits.append(EntrySignal("volume_breakout", 20, "Price is breaking the 20-day high with volume expansion"))
        elif breakout:
            hits.append(EntrySignal("price_breakout", 10, "Price is testing a 20-day breakout level"))

        near_ma20 = ma20 > 0 and abs(close - ma20) / ma20 <= 0.03
        pulled_back = ma20 > 0 and float(recent["Close"].iloc[:-1].max()) > ma20 * 1.03
        stochastic_turn = sto_k > sto_d and prev_sto_k <= prev_sto_d
        if near_ma20 and pulled_back and is_bullish:
            hits.append(EntrySignal("pullback_support", 20, "Pullback to MA20 support shows bullish reaction"))
        if stochastic_turn and sto_k <= 60:
            hits.append(EntrySignal("stochastic_turn", 10, "STO 5-3-3 turned upward before overheating"))

        if vol20_ratio >= 2.0 and is_bullish:
            hits.append(EntrySignal("volume_confirmation", 15, "Bullish candle has volume confirmation"))
        elif vol20_ratio < 0.7:
            flags.append("Volume is weak")

        macd_cross = macd > macd_signal and prev_macd <= prev_macd_signal
        if macd_cross:
            hits.append(EntrySignal("macd_cross", 10, "MACD crossed above signal"))
        if 30 <= rsi <= 65:
            hits.append(EntrySignal("rsi_entry_zone", 10, "RSI is in a constructive entry zone"))
        elif rsi >= 75:
            flags.append("RSI is overheated")

        if not is_bullish and body_ratio >= 0.5:
            flags.append("Strong bearish candle blocks immediate entry")
        if close < ma120 and ma120 > 0:
            flags.append("Price is below MA120")
        if high < low or close < low or close <= 0:
            flags.append("Invalid price state")

        score = min(100, sum(hit.points for hit in hits))
        if candidate_score >= 85:
            score = min(100, score + 5)
        if str(market_regime).upper() == "BULL":
            score = min(100, score + 5)
        elif str(market_regime).upper() == "BEAR":
            score = max(0, score - 15)

        risk_level = self._risk_level(flags)
        action = self._action(score, risk_level, candidate_action, position_weight)
        order_type = "LIMIT" if action in {"BUY_NOW", "WAIT"} else "NONE"
        limit_price = self._limit_price(close=close, ma20=ma20, action=action)

        return EntryDecision(
            engine_version=ENGINE_VERSION,
            entry_score=int(score),
            action=action,
            order_type=order_type,
            entry_price=round(close, 4),
            limit_price=round(limit_price, 4),
            risk_level=risk_level,
            risk_flags=flags,
            reasons=[hit.reason for hit in hits],
            signal_hits=[asdict(hit) for hit in hits],
        )

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
            raise ValueError(f"Entry timing requires columns: {', '.join(missing)}")

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

    def _risk_level(self, flags: list[str]) -> str:
        high_flags = {
            "Candidate risk is high",
            "Strong bearish candle blocks immediate entry",
            "No executable position size",
            "Invalid price state",
        }
        if any(flag in high_flags for flag in flags):
            return "HIGH"
        if flags:
            return "MEDIUM"
        return "LOW"

    def _action(
        self,
        score: int,
        risk_level: str,
        candidate_action: str,
        position_weight: float,
    ) -> str:
        if risk_level == "HIGH":
            return "CANCEL"
        if candidate_action in {"REJECT", "NEUTRAL"}:
            return "CANCEL"
        if position_weight <= 0:
            return "CANCEL"
        if score >= 80 and risk_level == "LOW":
            return "BUY_NOW"
        if score >= 65:
            return "WAIT"
        if score >= 45:
            return "WATCH"
        return "CANCEL"

    def _limit_price(self, close: float, ma20: float, action: str) -> float:
        if action == "BUY_NOW":
            return close
        if action == "WAIT" and ma20 > 0:
            return min(close * 0.995, ma20 * 1.01)
        return 0.0


def evaluate_entry(
    df: pd.DataFrame,
    candidate: dict[str, Any] | None = None,
    position: dict[str, Any] | None = None,
    market_regime: str = "SIDEWAY",
) -> dict[str, Any]:
    """Backward-compatible helper returning a dict decision payload."""

    return EntryTimingEngine().evaluate(
        df=df,
        candidate=candidate,
        position=position,
        market_regime=market_regime,
    ).to_dict()
