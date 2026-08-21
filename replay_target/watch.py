from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from sto.structure_similarity import STOStructure, STOStructureSimilarityEngine


@dataclass(frozen=True)
class TargetWatchConfig:
    ticker: str = "232080"
    symbol: str = "TIGER 코스닥150"
    watch_threshold: float = 65.0
    approaching_threshold: float = 75.0
    trigger_threshold: float = 85.0
    price_weight: float = 0.30
    sto_short_weight: float = 0.20
    sto_middle_weight: float = 0.20
    sto_long_weight: float = 0.20
    path_weight: float = 0.10


@dataclass(frozen=True)
class TargetWatchSnapshot:
    ticker: str
    symbol: str
    as_of: str | None
    current_close: float | None
    target_score: float | None
    state: str
    price_score: float | None
    sto_short_score: float | None
    sto_middle_score: float | None
    sto_long_score: float | None
    path_score: float | None
    short_sto: float | None
    middle_sto: float | None
    long_sto: float | None
    arrangement: str | None
    labels: tuple[str, ...]
    note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_state(score: float | None, config: TargetWatchConfig | None = None) -> str:
    cfg = config or TargetWatchConfig()
    if score is None:
        return "데이터 없음"
    if score >= cfg.trigger_threshold:
        return "Target 도달"
    if score >= cfg.approaching_threshold:
        return "접근중"
    if score >= cfg.watch_threshold:
        return "관찰"
    return "대기"


def _normalize_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    renamed = frame.rename(
        columns={
            "trade_date": "Date",
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    ).copy()
    if "Date" in renamed.columns:
        renamed["Date"] = pd.to_datetime(renamed["Date"], errors="coerce")
    required = ["Open", "High", "Low", "Close"]
    if not all(column in renamed.columns for column in required):
        return pd.DataFrame()
    return renamed.dropna(subset=["Close"]).reset_index(drop=True)


def _last_date(frame: pd.DataFrame) -> str | None:
    if frame.empty or "Date" not in frame.columns or pd.isna(frame["Date"].iloc[-1]):
        return None
    return str(pd.Timestamp(frame["Date"].iloc[-1]).date())


def _price_structure(frame: pd.DataFrame) -> tuple[float, float, float, float]:
    close = frame["Close"].astype(float)
    current = float(close.iloc[-1])
    recent = close.tail(min(20, len(close)))
    high = float(recent.max())
    low = float(recent.min())
    range_pos = 0.5 if high <= low else (current - low) / (high - low)
    ret_5 = current / float(close.iloc[-6]) - 1.0 if len(close) >= 6 else 0.0
    ret_20 = current / float(close.iloc[-21]) - 1.0 if len(close) >= 21 else ret_5
    drawdown = current / high - 1.0 if high > 0 else 0.0
    return current, range_pos, ret_5, ret_20 + drawdown


def _similarity_scalar(a: float, b: float, scale: float = 1.0) -> float:
    distance = abs(float(a) - float(b)) * scale
    return max(0.0, 100.0 / (1.0 + distance))


def _target_price_score(current: pd.DataFrame, target: pd.DataFrame) -> float:
    _, c_pos, c_ret5, c_combo = _price_structure(current)
    _, t_pos, t_ret5, t_combo = _price_structure(target)
    return round(
        _similarity_scalar(c_pos, t_pos, 4.0) * 0.40
        + _similarity_scalar(c_ret5, t_ret5, 14.0) * 0.30
        + _similarity_scalar(c_combo, t_combo, 10.0) * 0.30,
        2,
    )


def _layer_score(engine: STOStructureSimilarityEngine, a: list[float], b: list[float], av: float, bv: float) -> float:
    if a and b and len(a) == len(b):
        return round(engine._path_similarity(a, b), 2)
    return round(_similarity_scalar(av / 100.0, bv / 100.0, 5.0), 2)


def _path_score(current: STOStructure, target: STOStructure) -> float:
    arrangement = 100.0 if current.arrangement == target.arrangement else 55.0 if STOStructureSimilarityEngine._compatible(current.arrangement, target.arrangement) else 25.0
    slope_distance = sum((a - b) ** 2 for a, b in zip(current.vector[6:9], target.vector[6:9])) ** 0.5
    slope = max(0.0, 100.0 / (1.0 + slope_distance * 6.0))
    return round(arrangement * 0.45 + slope * 0.55, 2)


def build_snapshot(
    current_ohlcv: pd.DataFrame,
    target_ohlcv: pd.DataFrame,
    *,
    config: TargetWatchConfig | None = None,
) -> TargetWatchSnapshot:
    cfg = config or TargetWatchConfig()
    current = _normalize_ohlcv(current_ohlcv)
    target = _normalize_ohlcv(target_ohlcv)
    if current.empty or target.empty:
        return TargetWatchSnapshot(
            ticker=cfg.ticker,
            symbol=cfg.symbol,
            as_of=_last_date(current),
            current_close=None if current.empty else float(current["Close"].iloc[-1]),
            target_score=None,
            state="데이터 없음",
            price_score=None,
            sto_short_score=None,
            sto_middle_score=None,
            sto_long_score=None,
            path_score=None,
            short_sto=None,
            middle_sto=None,
            long_sto=None,
            arrangement=None,
            labels=(),
            note="현재 또는 Target OHLCV 데이터가 부족합니다.",
        )

    engine = STOStructureSimilarityEngine()
    current_structure = engine.extract(current)
    target_structure = engine.extract(target)
    price_score = _target_price_score(current, target)
    short_score = _layer_score(engine, current_structure.short_path, target_structure.short_path, current_structure.short, target_structure.short)
    middle_score = _layer_score(engine, current_structure.middle_path, target_structure.middle_path, current_structure.middle, target_structure.middle)
    long_score = _layer_score(engine, current_structure.long_path, target_structure.long_path, current_structure.long, target_structure.long)
    path_score = _path_score(current_structure, target_structure)
    score = round(
        price_score * cfg.price_weight
        + short_score * cfg.sto_short_weight
        + middle_score * cfg.sto_middle_weight
        + long_score * cfg.sto_long_weight
        + path_score * cfg.path_weight,
        2,
    )
    state = classify_state(score, cfg)
    return TargetWatchSnapshot(
        ticker=cfg.ticker,
        symbol=cfg.symbol,
        as_of=_last_date(current),
        current_close=float(current["Close"].iloc[-1]),
        target_score=score,
        state=state,
        price_score=price_score,
        sto_short_score=short_score,
        sto_middle_score=middle_score,
        sto_long_score=long_score,
        path_score=path_score,
        short_sto=round(current_structure.short, 2),
        middle_sto=round(current_structure.middle, 2),
        long_sto=round(current_structure.long, 2),
        arrangement=current_structure.arrangement,
        labels=tuple(current_structure.labels),
        note="Target State v1 · 가격구조 30% + STO 단/중/장 각 20% + 진행방향 10%",
    )
