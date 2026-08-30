from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from collector.base import CollectorRequest, MarketDataCollector
from collector.fdr import FDRCollector
from replay_target.path_watch import PathWatchSnapshot, build_path_snapshot
from replay_target.watch import TargetWatchSnapshot, build_snapshot
from sto.structure_similarity import STOStructureSimilarityEngine


@dataclass(frozen=True)
class IntegratedWatchConfig:
    """Configuration for the standalone Replay Target / Path Watch workbench."""

    ticker: str = "229200"
    symbol: str = "KODEX 코스닥150"
    reference_ticker: str = "006840"
    reference_symbol: str = "AK홀딩스(당시 애경유화)"
    current_anchor_date: str = "2026-08-25"

    reference_window_start: str = "2011-10-17"
    reference_window_end: str = "2011-11-11"
    reference_anchor_date: str | None = None

    reference_target_date: str | None = None
    reference_target_window_start: str = "2011-11-14"
    reference_target_window_end: str = "2011-12-02"

    current_period: str = "2y"
    reference_period: str = "20y"
    min_current_rows: int = 80
    min_reference_rows: int = 120


@dataclass(frozen=True)
class IntegratedWatchResult:
    config: IntegratedWatchConfig
    ready: bool
    current_source: str
    reference_source: str
    current_quality_score: int
    reference_quality_score: int
    current_rows: int
    reference_rows: int
    current_oldest_date: str | None
    current_latest_date: str | None
    reference_oldest_date: str | None
    reference_latest_date: str | None
    current_close: float | None
    resolved_current_anchor_date: str | None
    resolved_reference_anchor_date: str | None
    anchor_similarity: float | None
    resolved_reference_target_date: str | None
    target_selection: str
    target: TargetWatchSnapshot | None
    path: PathWatchSnapshot | None
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["target"] = None if self.target is None else self.target.to_dict()
        payload["path"] = None if self.path is None else self.path.to_dict()
        return payload


class ReplayTargetIntegratedService:
    """Load market data, calibrate the reference, then run both watches.

    The service is isolated from recommendation and order state. It reads
    market data and returns research/verification evidence only.
    """

    def __init__(self, collector: MarketDataCollector | None = None) -> None:
        self.collector = collector or FDRCollector()
        self.sto = STOStructureSimilarityEngine()

    def run_live(self, config: IntegratedWatchConfig | None = None) -> IntegratedWatchResult:
        cfg = config or IntegratedWatchConfig()
        current_result = self.collector.fetch(
            CollectorRequest(market="kr", ticker=cfg.ticker, period=cfg.current_period, interval="1d")
        )
        reference_result = self.collector.fetch(
            CollectorRequest(
                market="kr",
                ticker=cfg.reference_ticker,
                period=cfg.reference_period,
                interval="1d",
            )
        )
        return self.evaluate_frames(
            current_result.data,
            reference_result.data,
            config=cfg,
            current_source=current_result.source,
            reference_source=reference_result.source,
            current_quality_score=current_result.quality_score,
            reference_quality_score=reference_result.quality_score,
            upstream_messages=(current_result.message, reference_result.message),
        )

    def evaluate_frames(
        self,
        current_ohlcv: pd.DataFrame,
        reference_ohlcv: pd.DataFrame,
        *,
        config: IntegratedWatchConfig | None = None,
        current_source: str = "provided",
        reference_source: str = "provided",
        current_quality_score: int = 100,
        reference_quality_score: int = 100,
        upstream_messages: tuple[str, str] = ("", ""),
    ) -> IntegratedWatchResult:
        cfg = config or IntegratedWatchConfig()
        current = _normalize_ohlcv(current_ohlcv)
        reference = _normalize_ohlcv(reference_ohlcv)
        warnings: list[str] = []

        if upstream_messages[0] not in {"", "ok"}:
            warnings.append(f"현재 데이터 수집: {upstream_messages[0]}")
        if upstream_messages[1] not in {"", "ok"}:
            warnings.append(f"과거 데이터 수집: {upstream_messages[1]}")
        if len(current) < cfg.min_current_rows:
            warnings.append(f"현재 데이터가 {len(current)}행으로 기준 {cfg.min_current_rows}행보다 적습니다.")
        if len(reference) < cfg.min_reference_rows:
            warnings.append(f"과거 데이터가 {len(reference)}행으로 기준 {cfg.min_reference_rows}행보다 적습니다.")

        reference_oldest = _oldest_date(reference)
        if reference_oldest and pd.Timestamp(reference_oldest) > pd.Timestamp(cfg.reference_window_start):
            warnings.append(
                f"AK 과거 데이터가 {reference_oldest}부터 시작해 2011 기준구간을 포함하지 않습니다."
            )

        resolved_current_anchor = _resolve_date(current, cfg.current_anchor_date)
        if resolved_current_anchor is None:
            warnings.append("KODEX 기준일(T0)을 현재 데이터에서 찾지 못했습니다.")

        resolved_reference_anchor: str | None = None
        anchor_similarity: float | None = None
        if resolved_current_anchor is not None and not reference.empty:
            if cfg.reference_anchor_date:
                resolved_reference_anchor = _resolve_date(reference, cfg.reference_anchor_date)
                if resolved_reference_anchor is None:
                    warnings.append("지정한 AK홀딩스 기준일을 과거 데이터에서 찾지 못했습니다.")
                else:
                    anchor_similarity = self._anchor_similarity(
                        current,
                        reference,
                        resolved_current_anchor,
                        resolved_reference_anchor,
                    )
            else:
                resolved_reference_anchor, anchor_similarity = self._auto_reference_anchor(
                    current,
                    reference,
                    current_anchor_date=resolved_current_anchor,
                    window_start=cfg.reference_window_start,
                    window_end=cfg.reference_window_end,
                )
                if resolved_reference_anchor is None:
                    warnings.append("AK 동그라미/A 전환 구간에서 대응 T0를 찾지 못했습니다.")

        target_selection = "미설정"
        if cfg.reference_target_date:
            resolved_target = _resolve_date(reference, cfg.reference_target_date)
            target_selection = "직접 지정"
            if resolved_target is None:
                warnings.append("지정한 B Target 기준일을 과거 데이터에서 찾지 못했습니다.")
        else:
            resolved_target = _auto_reference_target(
                reference,
                window_start=cfg.reference_target_window_start,
                window_end=cfg.reference_target_window_end,
                after_date=resolved_reference_anchor,
            )
            target_selection = "B 박스 구간 자동 저점"
            if resolved_target is None:
                warnings.append("AK B 박스 후보구간에서 Target 기준일을 찾지 못했습니다.")

        if resolved_reference_anchor and resolved_target:
            if pd.Timestamp(resolved_target) <= pd.Timestamp(resolved_reference_anchor):
                warnings.append("B Target 기준일은 AK 대응 T0보다 뒤여야 합니다.")
                resolved_target = None

        target_snapshot: TargetWatchSnapshot | None = None
        if not current.empty and resolved_target:
            target_frame = reference[reference["Date"] <= pd.Timestamp(resolved_target)].copy()
            if not target_frame.empty:
                target_snapshot = build_snapshot(current, target_frame)

        path_snapshot: PathWatchSnapshot | None = None
        if resolved_current_anchor and resolved_reference_anchor and not current.empty and not reference.empty:
            path_snapshot = build_path_snapshot(
                current,
                reference,
                current_anchor_date=resolved_current_anchor,
                reference_anchor_date=resolved_reference_anchor,
            )

        ready = bool(
            target_snapshot is not None
            and target_snapshot.target_score is not None
            and path_snapshot is not None
            and path_snapshot.path_score is not None
        )
        if not ready:
            warnings.append("Target/Path 동시 판정에 필요한 데이터 또는 기준일이 아직 충분하지 않습니다.")

        return IntegratedWatchResult(
            config=cfg,
            ready=ready,
            current_source=current_source,
            reference_source=reference_source,
            current_quality_score=int(current_quality_score),
            reference_quality_score=int(reference_quality_score),
            current_rows=len(current),
            reference_rows=len(reference),
            current_oldest_date=_oldest_date(current),
            current_latest_date=_latest_date(current),
            reference_oldest_date=reference_oldest,
            reference_latest_date=_latest_date(reference),
            current_close=_latest_close(current),
            resolved_current_anchor_date=resolved_current_anchor,
            resolved_reference_anchor_date=resolved_reference_anchor,
            anchor_similarity=None if anchor_similarity is None else round(anchor_similarity, 2),
            resolved_reference_target_date=resolved_target,
            target_selection=target_selection,
            target=target_snapshot,
            path=path_snapshot,
            warnings=tuple(dict.fromkeys(warnings)),
        )

    def _anchor_similarity(
        self,
        current: pd.DataFrame,
        reference: pd.DataFrame,
        current_anchor_date: str,
        reference_anchor_date: str,
    ) -> float:
        current_frame = current[current["Date"] <= pd.Timestamp(current_anchor_date)]
        reference_frame = reference[reference["Date"] <= pd.Timestamp(reference_anchor_date)]
        if current_frame.empty or reference_frame.empty:
            return 0.0
        current_structure = self.sto.extract(current_frame)
        reference_structure = self.sto.extract(reference_frame)
        sto_score = float(self.sto.similarity(current_structure, reference_structure))
        price_score = _price_shape_similarity(current_frame, reference_frame)
        return sto_score * 0.75 + price_score * 0.25

    def _auto_reference_anchor(
        self,
        current: pd.DataFrame,
        reference: pd.DataFrame,
        *,
        current_anchor_date: str,
        window_start: str,
        window_end: str,
    ) -> tuple[str | None, float | None]:
        current_frame = current[current["Date"] <= pd.Timestamp(current_anchor_date)]
        if current_frame.empty:
            return None, None
        current_structure = self.sto.extract(current_frame)
        start = pd.Timestamp(window_start)
        end = pd.Timestamp(window_end)
        candidate_rows = reference[(reference["Date"] >= start) & (reference["Date"] <= end)]
        if candidate_rows.empty:
            return None, None

        best_date: str | None = None
        best_score: float | None = None
        for idx in candidate_rows.index:
            history = reference.loc[:idx]
            if len(history) < 50:
                continue
            sto_score = float(self.sto.similarity(current_structure, self.sto.extract(history)))
            price_score = _price_shape_similarity(current_frame, history)
            score = sto_score * 0.75 + price_score * 0.25
            if best_score is None or score > best_score:
                best_score = score
                best_date = str(pd.Timestamp(reference.loc[idx, "Date"]).date())
        return best_date, best_score


def _auto_reference_target(
    reference: pd.DataFrame,
    *,
    window_start: str,
    window_end: str,
    after_date: str | None,
) -> str | None:
    if reference.empty:
        return None
    start = pd.Timestamp(window_start)
    end = pd.Timestamp(window_end)
    candidates = reference[(reference["Date"] >= start) & (reference["Date"] <= end)].copy()
    if after_date:
        candidates = candidates[candidates["Date"] > pd.Timestamp(after_date)]
    if candidates.empty:
        return None
    idx = candidates["Close"].astype(float).idxmin()
    return str(pd.Timestamp(reference.loc[idx, "Date"]).date())


def _price_shape_similarity(a: pd.DataFrame, b: pd.DataFrame, length: int = 20) -> float:
    if a.empty or b.empty:
        return 0.0
    av = a["Close"].astype(float).tail(length).tolist()
    bv = b["Close"].astype(float).tail(length).tolist()
    n = min(len(av), len(bv))
    if n < 5:
        return 0.0
    av = av[-n:]
    bv = bv[-n:]
    abase = av[0] if av[0] else 1.0
    bbase = bv[0] if bv[0] else 1.0
    an = [value / abase - 1.0 for value in av]
    bn = [value / bbase - 1.0 for value in bv]
    rmse = (sum((x - y) ** 2 for x, y in zip(an, bn)) / n) ** 0.5
    return max(0.0, 100.0 / (1.0 + rmse * 10.0))


def _normalize_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
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
    if "Date" not in result.columns:
        result = result.reset_index()
        if "Date" not in result.columns and "index" in result.columns:
            result = result.rename(columns={"index": "Date"})
    required = ["Date", "Open", "High", "Low", "Close"]
    if not all(column in result.columns for column in required):
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    if "Volume" not in result.columns:
        result["Volume"] = 0.0
    result["Date"] = pd.to_datetime(result["Date"], errors="coerce")
    for column in ("Open", "High", "Low", "Close", "Volume"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return (
        result[["Date", "Open", "High", "Low", "Close", "Volume"]]
        .dropna(subset=["Date", "Close"])
        .sort_values("Date")
        .drop_duplicates(subset=["Date"], keep="last")
        .reset_index(drop=True)
    )


def _resolve_date(frame: pd.DataFrame, requested: str | None) -> str | None:
    if frame.empty or not requested:
        return None
    requested_ts = pd.Timestamp(requested).normalize()
    eligible = frame[frame["Date"].dt.normalize() <= requested_ts]
    if eligible.empty:
        return None
    return str(pd.Timestamp(eligible["Date"].iloc[-1]).date())


def _oldest_date(frame: pd.DataFrame) -> str | None:
    if frame.empty:
        return None
    return str(pd.Timestamp(frame["Date"].iloc[0]).date())


def _latest_date(frame: pd.DataFrame) -> str | None:
    if frame.empty:
        return None
    return str(pd.Timestamp(frame["Date"].iloc[-1]).date())


def _latest_close(frame: pd.DataFrame) -> float | None:
    if frame.empty:
        return None
    try:
        return float(frame["Close"].iloc[-1])
    except (TypeError, ValueError):
        return None
