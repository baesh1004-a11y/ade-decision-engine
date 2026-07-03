from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class DataQualityIssue:
    """One deterministic data-quality finding for a price dataset."""

    severity: str
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DataQualityReport:
    """ADE-ready quality report for OHLCV data."""

    market: str
    ticker: str
    row_count: int
    start_date: str | None
    end_date: str | None
    is_usable: bool
    issues: list[DataQualityIssue]

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "ERROR")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "WARNING")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["error_count"] = self.error_count
        payload["warning_count"] = self.warning_count
        return payload


class PriceDataQualityValidator:
    """Validate whether normalized price data can safely feed ADEPipeline.

    The validator is deliberately deterministic and cheap. It should run after
    every import/sync path before a dataset is used for candidate, decision, or
    exit engines.
    """

    REQUIRED_COLUMNS = {"Date", "Open", "High", "Low", "Close", "Volume"}

    def __init__(self, min_rows: int = 60, max_missing_ratio: float = 0.01) -> None:
        self.min_rows = min_rows
        self.max_missing_ratio = max_missing_ratio

    def validate(self, df: pd.DataFrame, market: str, ticker: str) -> DataQualityReport:
        issues: list[DataQualityIssue] = []
        row_count = len(df)
        start_date: str | None = None
        end_date: str | None = None

        missing_columns = sorted(self.REQUIRED_COLUMNS - set(df.columns))
        if missing_columns:
            issues.append(
                DataQualityIssue(
                    severity="ERROR",
                    code="MISSING_COLUMNS",
                    message="Price data is missing required OHLCV columns",
                    context={"columns": missing_columns},
                )
            )
            return DataQualityReport(market, ticker, row_count, start_date, end_date, False, issues)

        if row_count == 0:
            issues.append(
                DataQualityIssue(
                    severity="ERROR",
                    code="EMPTY_DATASET",
                    message="Price dataset is empty",
                )
            )
            return DataQualityReport(market, ticker, row_count, start_date, end_date, False, issues)

        work = df.copy()
        work["Date"] = pd.to_datetime(work["Date"], errors="coerce")
        invalid_dates = int(work["Date"].isna().sum())
        if invalid_dates:
            issues.append(
                DataQualityIssue(
                    severity="ERROR",
                    code="INVALID_DATE",
                    message="Price data contains invalid trade dates",
                    context={"invalid_dates": invalid_dates},
                )
            )
        work = work.dropna(subset=["Date"]).sort_values("Date")
        if not work.empty:
            start_date = work["Date"].iloc[0].strftime("%Y-%m-%d")
            end_date = work["Date"].iloc[-1].strftime("%Y-%m-%d")

        duplicate_dates = int(work["Date"].duplicated().sum())
        if duplicate_dates:
            issues.append(
                DataQualityIssue(
                    severity="ERROR",
                    code="DUPLICATE_DATE",
                    message="Price data contains duplicate trade dates after normalization",
                    context={"duplicate_dates": duplicate_dates},
                )
            )

        if row_count < self.min_rows:
            issues.append(
                DataQualityIssue(
                    severity="WARNING",
                    code="SHORT_HISTORY",
                    message="Price history may be too short for stable ADE indicators",
                    context={"row_count": row_count, "min_rows": self.min_rows},
                )
            )

        numeric_columns = ["Open", "High", "Low", "Close", "Volume"]
        for column in numeric_columns:
            work[column] = pd.to_numeric(work[column], errors="coerce")

        missing_cells = int(work[numeric_columns].isna().sum().sum())
        total_cells = max(1, len(work) * len(numeric_columns))
        missing_ratio = missing_cells / total_cells
        if missing_ratio > self.max_missing_ratio:
            issues.append(
                DataQualityIssue(
                    severity="ERROR",
                    code="MISSING_NUMERIC_VALUES",
                    message="Price data has too many missing numeric OHLCV values",
                    context={"missing_cells": missing_cells, "missing_ratio": round(missing_ratio, 4)},
                )
            )

        invalid_price_rows = work[
            (work["Open"] <= 0)
            | (work["High"] <= 0)
            | (work["Low"] <= 0)
            | (work["Close"] <= 0)
            | (work["High"] < work["Low"])
            | (work["High"] < work["Open"])
            | (work["High"] < work["Close"])
            | (work["Low"] > work["Open"])
            | (work["Low"] > work["Close"])
        ]
        if not invalid_price_rows.empty:
            issues.append(
                DataQualityIssue(
                    severity="ERROR",
                    code="INVALID_OHLC_RANGE",
                    message="Price data contains impossible OHLC ranges",
                    context={"rows": len(invalid_price_rows)},
                )
            )

        negative_volume_rows = work[work["Volume"] < 0]
        if not negative_volume_rows.empty:
            issues.append(
                DataQualityIssue(
                    severity="ERROR",
                    code="NEGATIVE_VOLUME",
                    message="Price data contains negative volume values",
                    context={"rows": len(negative_volume_rows)},
                )
            )

        if len(work) >= 2:
            max_gap_days = int(work["Date"].diff().dt.days.max())
            if max_gap_days >= 10:
                issues.append(
                    DataQualityIssue(
                        severity="WARNING",
                        code="LARGE_DATE_GAP",
                        message="Price data contains a large calendar gap",
                        context={"max_gap_days": max_gap_days},
                    )
                )

        is_usable = not any(issue.severity == "ERROR" for issue in issues)
        return DataQualityReport(market, ticker, row_count, start_date, end_date, is_usable, issues)
