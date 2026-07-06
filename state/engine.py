from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class ADEState:
    sto_structure: str
    ma_structure: str
    weekly_position: str
    money_flow: str
    state_key: str
    labels: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ADEStateEngine:
    """Convert chart data into ADE state coordinates.

    This follows the user's flow: STO structure, MA array, weekly position,
    and capital/money-flow. Centerline is not part of matching state.
    """

    def extract(self, data: pd.DataFrame) -> ADEState:
        df = self._prepare(data)
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]

        rsi5 = self._rsi(close, 5)
        rsi10 = self._rsi(close, 10)
        rsi20 = self._rsi(close, 20)
        if rsi5 >= rsi10 >= rsi20 and rsi5 >= 55:
            sto = "STO_STACK_UP"
        elif rsi5 >= rsi10:
            sto = "STO_TURNING_UP"
        elif rsi5 < rsi10 < rsi20:
            sto = "STO_STACK_DOWN"
        else:
            sto = "STO_MIXED"

        ma5 = close.rolling(5).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60, min_periods=20).mean().iloc[-1]
        latest = close.iloc[-1]
        if latest > ma5 > ma20 > ma60:
            ma = "MA_BULL_ALIGN"
        elif latest > ma20 > ma60:
            ma = "MA_MID_BULL"
        elif latest < ma20 < ma60:
            ma = "MA_BEAR_ALIGN"
        else:
            ma = "MA_MIXED"

        rolling_high = high.rolling(120, min_periods=20).max().iloc[-1]
        rolling_low = low.rolling(120, min_periods=20).min().iloc[-1]
        position = 0.5 if rolling_high == rolling_low else (latest - rolling_low) / (rolling_high - rolling_low)
        if position >= 0.85:
            pos = "POSITION_HIGH_BREAKOUT"
        elif position >= 0.55:
            pos = "POSITION_UPPER_MID"
        elif position >= 0.30:
            pos = "POSITION_MID_BASE"
        else:
            pos = "POSITION_LOW_BASE"

        amount = close * volume
        amt20 = amount.rolling(20, min_periods=5).mean().iloc[-1]
        amt120 = amount.rolling(120, min_periods=20).mean().iloc[-1]
        ratio20 = amount.iloc[-1] / amt20 if amt20 else 1.0
        ratio120 = amount.iloc[-1] / amt120 if amt120 else 1.0
        if ratio120 >= 10:
            flow = "MONEY_EXPLOSION_10X"
        elif ratio20 >= 3:
            flow = "MONEY_SURGE_3X"
        elif ratio20 >= 1.5:
            flow = "MONEY_INCREASING"
        else:
            flow = "MONEY_NORMAL"

        labels = [sto, ma, pos, flow]
        return ADEState(
            sto_structure=sto,
            ma_structure=ma,
            weekly_position=pos,
            money_flow=flow,
            state_key="|".join(labels),
            labels=labels,
        )

    @staticmethod
    def similarity(a: ADEState, b: ADEState) -> int:
        fields = ["sto_structure", "ma_structure", "weekly_position", "money_flow"]
        matched = sum(1 for field in fields if getattr(a, field) == getattr(b, field))
        return round(matched / len(fields) * 100)

    @staticmethod
    def _prepare(data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        if "Date" in df.columns:
            df = df.sort_values("Date")
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["High", "Low", "Close", "Volume"]).reset_index(drop=True)

    @staticmethod
    def _rsi(close: pd.Series, period: int) -> float:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period, min_periods=3).mean()
        loss = (-delta.clip(upper=0)).rolling(period, min_periods=3).mean().replace(0, pd.NA)
        rsi = 100 - (100 / (1 + gain / loss))
        value = rsi.iloc[-1]
        return 50.0 if pd.isna(value) else float(value)
