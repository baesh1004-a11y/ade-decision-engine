from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from sto.structure_similarity import STOStructureSimilarityEngine


@dataclass(frozen=True)
class PathWatchConfig:
    """Trajectory tracking for Replay Target Watch.

    Target Watch answers "how close are we to the target box?".
    Path Watch answers "are we still travelling through the same sequence as
    the historical reference?". A small timing lead/lag is allowed because two
    market paths rarely advance at exactly the same trading-day speed.
    """

    ticker: str = "229200"
    symbol: str = "KODEX 코스닥150"
    reference_ticker: str = "006840"
    reference_symbol: str = "AK홀딩스(당시 애경유화)"
    lag_tolerance_days: int = 3
    comparison_days: int = 5
    sync_threshold: float = 75.0
    warning_threshold: float = 65.0
    break_threshold: float = 60.0
    break_confirm_days: int = 2
    resync_confirm_days: int = 2
    price_direction_weight: float = 0.25
    price_return_weight: float = 0.20
    sto_structure_weight: float = 0.45
    arrangement_weight: float = 0.10


@dataclass(frozen=True)
class PathDailyMatch:
    current_date: str
    reference_date: str
    score: float
    price_direction_match: bool
    price_return_score: float
    sto_structure_score: float
    arrangement_match: bool
    current_return_1d: float
    reference_return_1d: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PathWatchSnapshot:
    ticker: str
    symbol: str
    reference_ticker: str
    reference_symbol: str
    as_of: str | None
    path_state: str
    path_score: float | None
    timing_offset_days: int | None
    timing_label: str
    matched_reference_date: str | None
    consecutive_mismatch_days: int
    divergence_started_at: str | None
    break_confirmed_at: str | None
    last_sync_date: str | None
    price_direction_match: bool | None
    sto_direction_matches: int | None
    arrangement_match: bool | None
    daily_matches: tuple[PathDailyMatch, ...]
    note: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["daily_matches"] = [item.to_dict() for item in self.daily_matches]
        return payload


def _normalize_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    result = frame.rename(
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
    if "Date" not in result.columns or "Close" not in result.columns:
        return pd.DataFrame()
    result["Date"] = pd.to_datetime(result["Date"], errors="coerce")
    result["Close"] = pd.to_numeric(result["Close"], errors="coerce")
    for column in ("Open", "High", "Low", "Volume"):
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    return (
        result.dropna(subset=["Date", "Close"])
        .sort_values("Date")
        .drop_duplicates(subset=["Date"], keep="last")
        .reset_index(drop=True)
    )


def _date_index(frame: pd.DataFrame, value: str | pd.Timestamp | None) -> int | None:
    if frame.empty or value is None:
        return None
    target = pd.Timestamp(value).normalize()
    dates = frame["Date"].dt.normalize()
    exact = frame.index[dates == target]
    if len(exact):
        return int(exact[-1])
    prior = frame.index[dates <= target]
    return int(prior[-1]) if len(prior) else None


def _direction(value: float, *, epsilon: float = 0.001) -> int:
    if value > epsilon:
        return 1
    if value < -epsilon:
        return -1
    return 0


def _return_score(current_return: float, reference_return: float) -> float:
    distance = abs(float(current_return) - float(reference_return))
    return max(0.0, 100.0 / (1.0 + distance * 20.0))


def _sto_direction_matches(current_structure: Any, reference_structure: Any) -> int:
    current_slopes = current_structure.vector[6:9]
    reference_slopes = reference_structure.vector[6:9]
    matches = 0
    for current_value, reference_value in zip(current_slopes, reference_slopes):
        if _direction(float(current_value), epsilon=0.002) == _direction(float(reference_value), epsilon=0.002):
            matches += 1
    return matches


def _daily_match(
    current: pd.DataFrame,
    reference: pd.DataFrame,
    current_index: int,
    reference_index: int,
    *,
    engine: STOStructureSimilarityEngine,
    config: PathWatchConfig,
) -> tuple[PathDailyMatch, int]:
    current_close = float(current.loc[current_index, "Close"])
    reference_close = float(reference.loc[reference_index, "Close"])
    current_prev = float(current.loc[max(0, current_index - 1), "Close"])
    reference_prev = float(reference.loc[max(0, reference_index - 1), "Close"])
    current_return = current_close / current_prev - 1.0 if current_index > 0 and current_prev else 0.0
    reference_return = reference_close / reference_prev - 1.0 if reference_index > 0 and reference_prev else 0.0
    direction_match = _direction(current_return) == _direction(reference_return)
    direction_score = 100.0 if direction_match else 0.0
    return_score = _return_score(current_return, reference_return)

    current_structure = engine.extract(current.iloc[: current_index + 1])
    reference_structure = engine.extract(reference.iloc[: reference_index + 1])
    sto_score = float(engine.similarity(current_structure, reference_structure))
    arrangement_match = current_structure.arrangement == reference_structure.arrangement
    arrangement_score = (
        100.0
        if arrangement_match
        else 55.0
        if engine._compatible(current_structure.arrangement, reference_structure.arrangement)
        else 25.0
    )
    score = round(
        direction_score * config.price_direction_weight
        + return_score * config.price_return_weight
        + sto_score * config.sto_structure_weight
        + arrangement_score * config.arrangement_weight,
        2,
    )
    return (
        PathDailyMatch(
            current_date=str(pd.Timestamp(current.loc[current_index, "Date"]).date()),
            reference_date=str(pd.Timestamp(reference.loc[reference_index, "Date"]).date()),
            score=score,
            price_direction_match=direction_match,
            price_return_score=round(return_score, 2),
            sto_structure_score=round(sto_score, 2),
            arrangement_match=arrangement_match,
            current_return_1d=round(current_return * 100.0, 3),
            reference_return_1d=round(reference_return * 100.0, 3),
        ),
        _sto_direction_matches(current_structure, reference_structure),
    )


def _timing_label(offset: int | None) -> str:
    if offset is None or offset == 0:
        return "동일 속도"
    if offset > 0:
        return f"현재가 과거 경로보다 {offset}거래일 선행"
    return f"현재가 과거 경로보다 {abs(offset)}거래일 지연"


def _consecutive_below(matches: list[PathDailyMatch], threshold: float) -> int:
    count = 0
    for item in reversed(matches):
        if item.score >= threshold:
            break
        count += 1
    return count


def _break_windows(matches: list[PathDailyMatch], config: PathWatchConfig) -> list[tuple[str, str]]:
    """Return (warning-start date, confirmed-break date) windows."""

    windows: list[tuple[str, str]] = []
    run = 0
    warning_start: str | None = None
    confirmed = False
    for item in matches:
        if item.score < config.warning_threshold and warning_start is None:
            warning_start = item.current_date
        if item.score < config.break_threshold:
            run += 1
            if run >= config.break_confirm_days and not confirmed:
                windows.append((warning_start or item.current_date, item.current_date))
                confirmed = True
        else:
            run = 0
            if item.score >= config.sync_threshold:
                warning_start = None
                confirmed = False
    return windows


def _path_state(
    matches: list[PathDailyMatch],
    timing_offset: int,
    *,
    config: PathWatchConfig,
) -> tuple[str, int, str | None, str | None, str | None]:
    if not matches:
        return "데이터 없음", 0, None, None, None

    current_score = matches[-1].score
    mismatch_days = _consecutive_below(matches, config.warning_threshold)
    active_divergence = matches[-mismatch_days].current_date if mismatch_days else None
    synced = [item.current_date for item in matches if item.score >= config.sync_threshold]
    last_sync_date = synced[-1] if synced else None
    windows = _break_windows(matches, config)
    latest_break_start = windows[-1][0] if windows else None
    latest_break_confirmed = windows[-1][1] if windows else None

    confirmed_break = _consecutive_below(matches, config.break_threshold) >= config.break_confirm_days
    recent = matches[-config.resync_confirm_days :]
    resynced = (
        bool(windows)
        and len(recent) >= config.resync_confirm_days
        and all(item.score >= config.sync_threshold for item in recent)
        and latest_break_confirmed not in {item.current_date for item in recent}
    )

    divergence_started_at = active_divergence or latest_break_start
    if resynced:
        return "재동조", mismatch_days, divergence_started_at, latest_break_confirmed, last_sync_date
    if confirmed_break:
        return "경로 이탈", mismatch_days, divergence_started_at, latest_break_confirmed, last_sync_date
    if current_score < config.warning_threshold:
        return "이탈 주의", mismatch_days, divergence_started_at, latest_break_confirmed, last_sync_date
    if abs(timing_offset) > 0:
        return ("선행" if timing_offset > 0 else "지연"), mismatch_days, divergence_started_at, latest_break_confirmed, last_sync_date
    return "동조 중", mismatch_days, divergence_started_at, latest_break_confirmed, last_sync_date


def _empty_snapshot(cfg: PathWatchConfig, current: pd.DataFrame, note: str) -> PathWatchSnapshot:
    return PathWatchSnapshot(
        ticker=cfg.ticker,
        symbol=cfg.symbol,
        reference_ticker=cfg.reference_ticker,
        reference_symbol=cfg.reference_symbol,
        as_of=None if current.empty else str(pd.Timestamp(current["Date"].iloc[-1]).date()),
        path_state="데이터 없음",
        path_score=None,
        timing_offset_days=None,
        timing_label="비교 불가",
        matched_reference_date=None,
        consecutive_mismatch_days=0,
        divergence_started_at=None,
        break_confirmed_at=None,
        last_sync_date=None,
        price_direction_match=None,
        sto_direction_matches=None,
        arrangement_match=None,
        daily_matches=(),
        note=note,
    )


def _collect_matches(
    current: pd.DataFrame,
    reference: pd.DataFrame,
    *,
    current_anchor: int,
    reference_anchor: int,
    elapsed: int,
    offset: int,
    start_step: int,
    engine: STOStructureSimilarityEngine,
    config: PathWatchConfig,
) -> tuple[list[PathDailyMatch], list[int]]:
    matches: list[PathDailyMatch] = []
    sto_direction_counts: list[int] = []
    for step in range(max(1, start_step), elapsed + 1):
        current_index = current_anchor + step
        reference_index = reference_anchor + step + offset
        if current_index <= 0 or current_index >= len(current):
            continue
        if reference_index <= 0 or reference_index >= len(reference):
            continue
        match, sto_count = _daily_match(
            current,
            reference,
            current_index,
            reference_index,
            engine=engine,
            config=config,
        )
        matches.append(match)
        sto_direction_counts.append(sto_count)
    return matches, sto_direction_counts


def build_path_snapshot(
    current_ohlcv: pd.DataFrame,
    reference_ohlcv: pd.DataFrame,
    *,
    current_anchor_date: str | pd.Timestamp,
    reference_anchor_date: str | pd.Timestamp,
    config: PathWatchConfig | None = None,
) -> PathWatchSnapshot:
    """Compare the post-anchor trajectory with an historical reference path.

    `current_anchor_date` is T0 on KODEX 코스닥150 and
    `reference_anchor_date` is the corresponding circled T0 on AK홀딩스.
    The best timing alignment is selected from ±lag_tolerance_days using only
    recent observations, then the entire T0→today path is evaluated on that
    alignment so the first divergence and any later resynchronization remain
    observable.
    """

    cfg = config or PathWatchConfig()
    current = _normalize_ohlcv(current_ohlcv)
    reference = _normalize_ohlcv(reference_ohlcv)
    current_anchor = _date_index(current, current_anchor_date)
    reference_anchor = _date_index(reference, reference_anchor_date)
    if current.empty or reference.empty or current_anchor is None or reference_anchor is None:
        return _empty_snapshot(cfg, current, "현재/과거 OHLCV 또는 T0 기준일을 확인할 수 없습니다.")

    elapsed = len(current) - 1 - current_anchor
    if elapsed < 1:
        return _empty_snapshot(cfg, current, "T0 이후 최소 1거래일의 데이터가 필요합니다.")

    engine = STOStructureSimilarityEngine()
    best_offset: int | None = None
    best_recent_score: float | None = None
    recent_start = max(1, elapsed - cfg.comparison_days + 1)

    for offset in range(-cfg.lag_tolerance_days, cfg.lag_tolerance_days + 1):
        recent_matches, _ = _collect_matches(
            current,
            reference,
            current_anchor=current_anchor,
            reference_anchor=reference_anchor,
            elapsed=elapsed,
            offset=offset,
            start_step=recent_start,
            engine=engine,
            config=cfg,
        )
        if not recent_matches:
            continue
        average = sum(item.score for item in recent_matches) / len(recent_matches)
        if best_recent_score is None or average > best_recent_score:
            best_recent_score = average
            best_offset = offset

    if best_offset is None or best_recent_score is None:
        return _empty_snapshot(cfg, current, "T0 이후 비교 가능한 과거 거래일이 부족합니다.")

    matches, sto_direction_counts = _collect_matches(
        current,
        reference,
        current_anchor=current_anchor,
        reference_anchor=reference_anchor,
        elapsed=elapsed,
        offset=best_offset,
        start_step=1,
        engine=engine,
        config=cfg,
    )
    if not matches:
        return _empty_snapshot(cfg, current, "선택된 시간 정렬에서 비교 가능한 거래일이 없습니다.")

    state, mismatch_days, divergence_started_at, break_confirmed_at, last_sync_date = _path_state(
        matches,
        best_offset,
        config=cfg,
    )
    latest = matches[-1]
    return PathWatchSnapshot(
        ticker=cfg.ticker,
        symbol=cfg.symbol,
        reference_ticker=cfg.reference_ticker,
        reference_symbol=cfg.reference_symbol,
        as_of=latest.current_date,
        path_state=state,
        path_score=round(best_recent_score, 2),
        timing_offset_days=best_offset,
        timing_label=_timing_label(best_offset),
        matched_reference_date=latest.reference_date,
        consecutive_mismatch_days=mismatch_days,
        divergence_started_at=divergence_started_at,
        break_confirmed_at=break_confirmed_at,
        last_sync_date=last_sync_date,
        price_direction_match=latest.price_direction_match,
        sto_direction_matches=sto_direction_counts[-1],
        arrangement_match=latest.arrangement_match,
        daily_matches=tuple(matches),
        note=(
            "Path State v1.1 · 최근 5거래일로 ±3거래일 시간차를 정렬한 뒤 T0부터 현재까지의 "
            "전체 경로를 가격 방향/변화폭과 3계층 STO 구조·배열로 추적합니다. 하루 불일치는 "
            "이탈 주의, 2거래일 연속 강한 불일치는 경로 이탈, 이후 2거래일 연속 재일치하면 "
            "재동조로 판정합니다."
        ),
    )
