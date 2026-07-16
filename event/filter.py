from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class MoneyExplosionEvent:
    market: str
    ticker: str
    name: str | None
    event_date: str
    money_ratio_120d: float
    money_ratio_20d: float
    bullish_body: bool
    long_base: bool
    labels: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class MarketEventRule:
    min_ratio_120d: float
    label: str


DEFAULT_MARKET_RULES: dict[str, MarketEventRule] = {
    "kr": MarketEventRule(
        min_ratio_120d=6.0,
        label="한국장 120일 평균 거래대금 6배 이상",
    ),
    "us": MarketEventRule(
        min_ratio_120d=4.0,
        label="미국장 120일 평균 거래대금 4배 이상",
    ),
}


class MoneyExplosionEventFilter:
    """Find Replay start events with market-specific money thresholds.

    Defaults:
    - KR: current dollar volume >= 6x the 120-session average
    - US: current dollar volume >= 4x the 120-session average

    ``min_ratio_120d`` remains available as a global override for backward
    compatibility and one-off experiments.
    """

    def __init__(
        self,
        min_ratio_120d: float | None = None,
        market_rules: dict[str, MarketEventRule] | None = None,
    ) -> None:
        self.min_ratio_120d = min_ratio_120d
        self.market_rules = dict(DEFAULT_MARKET_RULES if market_rules is None else market_rules)

    def latest_event(self, market: str, ticker: str, name: str | None, data: pd.DataFrame) -> MoneyExplosionEvent | None:
        df = self._prepare(data)
        if len(df) < 60:
            return None
        return self._event_at(market, ticker, name, df, len(df) - 1)

    def historical_events(self, market: str, ticker: str, name: str | None, data: pd.DataFrame) -> list[MoneyExplosionEvent]:
        df = self._prepare(data)
        events: list[MoneyExplosionEvent] = []
        if len(df) < 140:
            return events
        for i in range(120, len(df) - 1):
            event = self._event_at(market, ticker, name, df, i)
            if event is not None:
                events.append(event)
        return events

    def threshold_for(self, market: str) -> float:
        if self.min_ratio_120d is not None:
            return float(self.min_ratio_120d)
        rule = self.market_rules.get(market.strip().lower())
        return float(rule.min_ratio_120d) if rule is not None else 10.0

    def _event_at(self, market: str, ticker: str, name: str | None, df: pd.DataFrame, index: int) -> MoneyExplosionEvent | None:
        close = df["Close"]
        open_ = df["Open"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]
        amount = close * volume
        amt20 = amount.rolling(20, min_periods=5).mean()
        amt120 = amount.rolling(120, min_periods=20).mean()
        ratio20 = float(amount.iloc[index] / amt20.iloc[index]) if amt20.iloc[index] else 1.0
        ratio120 = float(amount.iloc[index] / amt120.iloc[index]) if amt120.iloc[index] else 1.0

        threshold = self.threshold_for(market)
        if ratio120 < threshold:
            return None

        candle_range = max(float(high.iloc[index] - low.iloc[index]), 1e-9)
        body_ratio = float(close.iloc[index] - open_.iloc[index]) / candle_range
        bullish_body = body_ratio >= 0.45 and close.iloc[index] > open_.iloc[index]

        prior = df.iloc[max(0, index - 120) : index]
        if prior.empty:
            long_base = False
        else:
            base_high = float(prior["High"].max())
            base_low = float(prior["Low"].min())
            long_base = base_low > 0 and (base_high - base_low) / base_low <= 0.8

        market_key = market.strip().lower()
        rule = self.market_rules.get(market_key)
        threshold_label = (
            f"120일 평균 거래대금 {threshold:g}배 이상"
            if self.min_ratio_120d is not None or rule is None
            else rule.label
        )
        labels = [threshold_label]
        if bullish_body:
            labels.append("장대양봉")
        if long_base:
            labels.append("장기 박스권 이후 대금")

        return MoneyExplosionEvent(
            market=market,
            ticker=ticker,
            name=name,
            event_date=str(pd.Timestamp(df.iloc[index]["Date"]).date()),
            money_ratio_120d=round(ratio120, 2),
            money_ratio_20d=round(ratio20, 2),
            bullish_body=bullish_body,
            long_base=long_base,
            labels=labels,
        )

    @staticmethod
    def _prepare(data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        if "Date" in df.columns:
            df = df.sort_values("Date")
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).reset_index(drop=True)
