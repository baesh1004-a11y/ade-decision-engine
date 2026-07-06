from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class CenterlineSnapshot:
    weekly: float | None
    monthly: float | None
    quarterly: float | None
    half_year: float | None
    yearly: float | None
    yearly_distance_pct: float | None
    alignment_score: int
    slope_score: int
    convergence_score: int
    breakout_score: int
    centerline_score: int
    labels: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class CenterlineEngine:
    """ADE centerline engine based on rolling high-low midpoint.

    Centerline = (rolling high + rolling low) / 2.
    Windows: weekly 5D, monthly 21D, quarterly 63D, half-year 126D, yearly 252D.
    """

    WINDOWS = {
        "weekly": 5,
        "monthly": 21,
        "quarterly": 63,
        "half_year": 126,
        "yearly": 252,
    }

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        df = self._prepare(data)
        for name, window in self.WINDOWS.items():
            high = df["High"].rolling(window, min_periods=max(3, window // 4)).max()
            low = df["Low"].rolling(window, min_periods=max(3, window // 4)).min()
            df[f"CL_{name.upper()}"] = (high + low) / 2
            df[f"CL_{name.upper()}_SLOPE"] = df[f"CL_{name.upper()}"].diff(5)
            df[f"CL_{name.upper()}_DIST"] = (df["Close"] - df[f"CL_{name.upper()}"]) / df[f"CL_{name.upper()}"].replace(0, pd.NA)
        return df

    def snapshot(self, data: pd.DataFrame) -> CenterlineSnapshot:
        df = self.transform(data)
        if df.empty:
            return CenterlineSnapshot(None, None, None, None, None, None, 0, 0, 0, 0, 0, [])

        last = df.iloc[-1]
        close = float(last["Close"])
        weekly = self._val(last.get("CL_WEEKLY"))
        monthly = self._val(last.get("CL_MONTHLY"))
        quarterly = self._val(last.get("CL_QUARTERLY"))
        half_year = self._val(last.get("CL_HALF_YEAR"))
        yearly = self._val(last.get("CL_YEARLY"))

        centers = [x for x in [weekly, monthly, quarterly, half_year, yearly] if x is not None]
        labels: list[str] = []

        alignment_score = 0
        if all(x is not None for x in [weekly, monthly, quarterly, half_year, yearly]):
            if close > weekly > monthly > quarterly > half_year > yearly:
                alignment_score = 100
                labels.append("중심값 완전 정배열")
            elif close > monthly > quarterly > yearly:
                alignment_score = 80
                labels.append("중심값 중장기 정배열")
            elif yearly is not None and close > yearly:
                alignment_score = 60
                labels.append("연봉 중심값 상단 회복")
            else:
                alignment_score = 30
        elif yearly is not None and close > yearly:
            alignment_score = 60
            labels.append("연봉 중심값 상단 회복")

        yearly_distance_pct = None
        if yearly is not None and yearly > 0:
            yearly_distance_pct = round((close / yearly - 1) * 100, 2)
            if 0 <= yearly_distance_pct <= 20:
                labels.append("연봉 중심값 근처 돌파 구간")
            elif yearly_distance_pct > 20:
                labels.append("연봉 중심값 대비 확장 구간")

        slopes = [self._val(last.get(f"CL_{name.upper()}_SLOPE")) for name in self.WINDOWS]
        valid_slopes = [s for s in slopes if s is not None]
        up_count = sum(s > 0 for s in valid_slopes)
        slope_score = round(up_count / len(valid_slopes) * 100) if valid_slopes else 0
        if slope_score >= 80:
            labels.append("중심값 기울기 상승 전환")

        convergence_score = 0
        if len(centers) >= 3 and close > 0:
            spread = (max(centers) - min(centers)) / close
            convergence_score = 100 if spread <= 0.08 else 80 if spread <= 0.15 else 55 if spread <= 0.30 else 30
            if convergence_score >= 80:
                labels.append("중심값 수렴 후 확산 가능")

        breakout_score = 0
        if yearly is not None and len(df) >= 2:
            prev_close = float(df.iloc[-2]["Close"])
            prev_yearly = self._val(df.iloc[-2].get("CL_YEARLY"))
            if prev_yearly is not None and prev_close <= prev_yearly and close > yearly:
                breakout_score = 100
                labels.append("연봉 중심값 상향 돌파")
            elif close > yearly and yearly_distance_pct is not None and yearly_distance_pct <= 15:
                breakout_score = 80
            elif close > yearly:
                breakout_score = 60
            else:
                breakout_score = 25

        centerline_score = round(
            alignment_score * 0.30
            + slope_score * 0.25
            + convergence_score * 0.20
            + breakout_score * 0.25
        )

        return CenterlineSnapshot(
            weekly=weekly,
            monthly=monthly,
            quarterly=quarterly,
            half_year=half_year,
            yearly=yearly,
            yearly_distance_pct=yearly_distance_pct,
            alignment_score=alignment_score,
            slope_score=slope_score,
            convergence_score=convergence_score,
            breakout_score=breakout_score,
            centerline_score=centerline_score,
            labels=labels,
        )

    @staticmethod
    def _prepare(data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        if "Date" in df.columns:
            df = df.sort_values("Date")
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["High", "Low", "Close"]).reset_index(drop=True)

    @staticmethod
    def _val(value) -> float | None:
        if value is None or pd.isna(value):
            return None
        return round(float(value), 4)
