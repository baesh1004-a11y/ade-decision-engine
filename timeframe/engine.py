from __future__ import annotations

from typing import Any

import pandas as pd


class MultiTimeframeEngine:
    """Analyze weekly/daily/intraday-like trend alignment.

    v1 supports native daily data and derives weekly frames when Date is present.
    Intraday frames can be passed explicitly through `frames`.
    """

    def evaluate(self, daily: pd.DataFrame, frames: dict[str, pd.DataFrame] | None = None) -> dict[str, Any]:
        frames = dict(frames or {})
        frames.setdefault("daily", daily)
        if "weekly" not in frames:
            frames["weekly"] = self._to_weekly(daily)
        results = {name: self._frame_score(frame) for name, frame in frames.items() if len(frame) >= 5}
        if not results:
            return {"engine_version": "multi-timeframe-v1.0.0", "alignment_score": 0.0, "frames": {}, "signal": "INSUFFICIENT"}
        alignment = sum(item["score"] for item in results.values()) / len(results)
        return {
            "engine_version": "multi-timeframe-v1.0.0",
            "alignment_score": round(alignment, 4),
            "frames": results,
            "signal": "ALIGNED" if alignment >= 70 else "MIXED" if alignment >= 45 else "WEAK",
        }

    def _to_weekly(self, df: pd.DataFrame) -> pd.DataFrame:
        if "Date" not in df.columns:
            return df.tail(max(5, len(df) // 5)).copy()
        work = df.copy()
        work["Date"] = pd.to_datetime(work["Date"], errors="coerce")
        work = work.dropna(subset=["Date"]).set_index("Date")
        if work.empty:
            return df.tail(max(5, len(df) // 5)).copy()
        weekly = work.resample("W").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
        return weekly.reset_index()

    def _frame_score(self, df: pd.DataFrame) -> dict[str, Any]:
        close = df["Close"].astype(float)
        last = float(close.iloc[-1])
        ma_fast = float(close.tail(min(10, len(close))).mean())
        ma_slow = float(close.tail(min(30, len(close))).mean())
        momentum = float(last / close.iloc[max(0, len(close) - min(10, len(close)))] - 1.0) if len(close) > 1 else 0.0
        score = 0.0
        score += 40 if last > ma_fast else 15
        score += 35 if ma_fast >= ma_slow else 10
        score += 25 if momentum > 0 else 5
        return {
            "score": round(score, 4),
            "last_close": round(last, 4),
            "fast_ma": round(ma_fast, 4),
            "slow_ma": round(ma_slow, 4),
            "momentum": round(momentum, 4),
        }
