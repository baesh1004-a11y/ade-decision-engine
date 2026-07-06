from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class PatternState:
    sto_stack_score: int
    ma_alignment_score: int
    weekly_position_score: int
    volume_surge_score: int
    long_base_score: int
    breakout_score: int
    state_score: int
    labels: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ReplayCase:
    start_date: str
    end_date: str
    similarity: float
    forward_return_20d: float | None
    forward_return_60d: float | None
    drawdown_20d: float | None
    state: PatternState

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ReplayProbabilityResult:
    current_state: PatternState
    cases: list[ReplayCase]
    environment_score: int
    replay_probability: int
    grade: str
    action: str
    avg_return_20d: float | None
    win_rate_20d: float | None
    avg_drawdown_20d: float | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ReplayProbabilityEngine:
    """ADE 6-step replay probability engine.

    This is based on the user's trading process:
    1) candidate filter: large capital inflow / long-base breakout
    2) current state analysis: STO stack, MA alignment, weekly position, volume flow
    3) historical state search across prior windows
    4) post-event replay: future return / drawdown
    5) environment synchronization score
    6) final A/B/C/D entry value decision
    """

    def __init__(self, window: int = 120, forward_20d: int = 20, forward_60d: int = 60) -> None:
        self.window = window
        self.forward_20d = forward_20d
        self.forward_60d = forward_60d

    def evaluate(self, data: pd.DataFrame, environment_score: int = 70, top_n: int = 5) -> ReplayProbabilityResult:
        df = self._prepare(data)
        if len(df) < self.window + self.forward_60d + 30:
            current = self.extract_state(df)
            return ReplayProbabilityResult(current, [], environment_score, 0, "D", "EXCLUDE", None, None, None)

        current_window = df.tail(self.window).reset_index(drop=True)
        current_state = self.extract_state(current_window)
        cases: list[ReplayCase] = []
        latest_start = len(df) - self.window

        for start in range(0, latest_start - self.forward_60d, 5):
            end = start + self.window
            hist_window = df.iloc[start:end].reset_index(drop=True)
            hist_state = self.extract_state(hist_window)
            similarity = self._state_similarity(current_state, hist_state)
            if similarity < 55:
                continue
            cases.append(
                ReplayCase(
                    start_date=str(pd.Timestamp(df.iloc[start]["Date"]).date()),
                    end_date=str(pd.Timestamp(df.iloc[end - 1]["Date"]).date()),
                    similarity=round(similarity, 1),
                    forward_return_20d=self._future_return(df, end - 1, self.forward_20d),
                    forward_return_60d=self._future_return(df, end - 1, self.forward_60d),
                    drawdown_20d=self._future_drawdown(df, end - 1, self.forward_20d),
                    state=hist_state,
                )
            )

        cases = sorted(cases, key=lambda item: item.similarity, reverse=True)[:top_n]
        avg_return = self._avg([item.forward_return_20d for item in cases])
        avg_drawdown = self._avg([item.drawdown_20d for item in cases])
        win_rate = self._win_rate([item.forward_return_20d for item in cases])
        replay_probability = self._probability(current_state, cases, environment_score, avg_return, win_rate)
        grade = self._grade(replay_probability)
        action = self._action(grade)

        return ReplayProbabilityResult(
            current_state=current_state,
            cases=cases,
            environment_score=environment_score,
            replay_probability=replay_probability,
            grade=grade,
            action=action,
            avg_return_20d=avg_return,
            win_rate_20d=win_rate,
            avg_drawdown_20d=avg_drawdown,
        )

    def extract_state(self, data: pd.DataFrame) -> PatternState:
        df = self._prepare(data)
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]

        ma5 = close.rolling(5).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1] if len(df) >= 60 else ma20
        ma120 = close.rolling(120).mean().iloc[-1] if len(df) >= 120 else ma60
        latest_close = close.iloc[-1]

        rsi_5 = self._rsi(close, 5)
        rsi_10 = self._rsi(close, 10)
        rsi_20 = self._rsi(close, 20)
        sto_stack_score = 100 if rsi_5 >= rsi_10 >= rsi_20 and rsi_5 >= 55 else 60 if rsi_5 >= rsi_10 else 30

        ma_alignment_score = 100 if latest_close > ma5 > ma20 > ma60 > ma120 else 75 if latest_close > ma20 > ma60 else 45 if latest_close > ma20 else 20
        rolling_high = high.rolling(120, min_periods=20).max().iloc[-1]
        rolling_low = low.rolling(120, min_periods=20).min().iloc[-1]
        position = 0.5 if rolling_high == rolling_low else (latest_close - rolling_low) / (rolling_high - rolling_low)
        weekly_position_score = 100 if 0.55 <= position <= 0.95 else 70 if position > 0.35 else 40

        vol20 = volume.rolling(20).mean().iloc[-1]
        vol120 = volume.rolling(120, min_periods=20).mean().iloc[-1]
        volume_ratio_20 = volume.iloc[-1] / vol20 if vol20 else 1.0
        volume_ratio_120 = volume.iloc[-1] / vol120 if vol120 else 1.0
        volume_surge_score = 100 if volume_ratio_120 >= 10 else 85 if volume_ratio_20 >= 3 else 70 if volume_ratio_20 >= 1.5 else 35

        low_range = (rolling_high - rolling_low) / rolling_low if rolling_low else 1.0
        long_base_score = 100 if len(df) >= 100 and low_range <= 0.8 and latest_close >= ma60 else 70 if latest_close >= ma60 else 35
        breakout_score = 100 if latest_close >= rolling_high * 0.95 and volume_ratio_20 >= 1.5 else 70 if latest_close > ma20 and volume_ratio_20 >= 1.1 else 35

        state_score = round(
            sto_stack_score * 0.18
            + ma_alignment_score * 0.20
            + weekly_position_score * 0.14
            + volume_surge_score * 0.22
            + long_base_score * 0.13
            + breakout_score * 0.13
        )
        labels = []
        if volume_ratio_120 >= 10:
            labels.append("거래대금 10배 이상 후보")
        if sto_stack_score >= 85:
            labels.append("STO 3층 구조 유사")
        if ma_alignment_score >= 85:
            labels.append("이평 정배열")
        if long_base_score >= 85:
            labels.append("장기 바닥권 이후 돌파")
        if breakout_score >= 85:
            labels.append("돌파 + 거래량 동반")

        return PatternState(
            sto_stack_score=sto_stack_score,
            ma_alignment_score=ma_alignment_score,
            weekly_position_score=weekly_position_score,
            volume_surge_score=volume_surge_score,
            long_base_score=long_base_score,
            breakout_score=breakout_score,
            state_score=state_score,
            labels=labels,
        )

    @staticmethod
    def _prepare(data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        if "Date" not in df.columns:
            df = df.reset_index().rename(columns={"index": "Date"})
        return df.dropna(subset=["High", "Low", "Close", "Volume"]).reset_index(drop=True)

    @staticmethod
    def _rsi(close: pd.Series, period: int) -> float:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, pd.NA)
        rsi = 100 - (100 / (1 + rs))
        value = rsi.iloc[-1]
        return 50.0 if pd.isna(value) else float(value)

    @staticmethod
    def _state_similarity(a: PatternState, b: PatternState) -> float:
        fields = [
            "sto_stack_score",
            "ma_alignment_score",
            "weekly_position_score",
            "volume_surge_score",
            "long_base_score",
            "breakout_score",
        ]
        diffs = [abs(getattr(a, f) - getattr(b, f)) for f in fields]
        return max(0.0, 100.0 - sum(diffs) / len(diffs))

    @staticmethod
    def _future_return(df: pd.DataFrame, index: int, days: int) -> float | None:
        if index + days >= len(df):
            return None
        entry = float(df.iloc[index]["Close"])
        exit_price = float(df.iloc[index + days]["Close"])
        return None if entry <= 0 else round((exit_price / entry - 1) * 100, 2)

    @staticmethod
    def _future_drawdown(df: pd.DataFrame, index: int, days: int) -> float | None:
        if index + days >= len(df):
            return None
        entry = float(df.iloc[index]["Close"])
        lows = df.iloc[index + 1 : index + days + 1]["Low"]
        return None if entry <= 0 or lows.empty else round((float(lows.min()) / entry - 1) * 100, 2)

    @staticmethod
    def _avg(values: list[float | None]) -> float | None:
        valid = [v for v in values if v is not None]
        return None if not valid else round(sum(valid) / len(valid), 2)

    @staticmethod
    def _win_rate(values: list[float | None]) -> float | None:
        valid = [v for v in values if v is not None]
        return None if not valid else round(sum(v > 0 for v in valid) / len(valid) * 100, 1)

    @staticmethod
    def _probability(state: PatternState, cases: list[ReplayCase], environment_score: int, avg_return: float | None, win_rate: float | None) -> int:
        case_score = sum(c.similarity for c in cases) / len(cases) if cases else 0
        ret_score = 50 if avg_return is None else min(100, max(0, 50 + avg_return * 5))
        win_score = 50 if win_rate is None else win_rate
        score = state.state_score * 0.35 + case_score * 0.25 + environment_score * 0.20 + ret_score * 0.10 + win_score * 0.10
        return round(max(0, min(100, score)))

    @staticmethod
    def _grade(probability: int) -> str:
        if probability >= 70:
            return "A"
        if probability >= 50:
            return "B"
        if probability >= 30:
            return "C"
        return "D"

    @staticmethod
    def _action(grade: str) -> str:
        return {"A": "ENTRY_FAVORABLE", "B": "WAIT_OR_SCALE", "C": "WATCH_ONLY", "D": "EXCLUDE"}[grade]
