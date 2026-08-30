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

    Current KODEX EOD history stays on the normal ADE collector. The historical
    AK reference is automatically replaced by an explicit-date KRX source when
    the ordinary collector does not actually contain the 2011 comparison
    windows. This avoids generating scores from a recent-only 3000-row slice.
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

        reference_data = _normalize_ohlcv(reference_result.data)
        reference_source = reference_result.source
        reference_quality = reference_result.quality_score
        reference_message = reference_result.message

        if not _reference_has_required_windows(reference_data, cfg):
            fallback, fallback_source, fallback_message = _load_reference_history(cfg)
            if not fallback.empty and _reference_has_required_windows(fallback, cfg):
                reference_data = fallback
                reference_source = fallback_source
                reference_quality = _quality_score(fallback)
                reference_message = (
                    f"기본 {reference_result.source} 데이터가 2011 기준구간을 포함하지 않아 "
                    f"{fallback_source} 명시기간 데이터로 교체했습니다."
                )
            else:
                detail = fallback_message or "과거 데이터 공급원에서 2011 구간을 확보하지 못했습니다."
                reference_message = (
                    f"{reference_result.message or '기본 과거 데이터 부족'} · "
                    f"2011 역사 데이터 fallback 실패: {detail}"
                )

        return self.evaluate_frames(
            current_result.data,
            reference_data,
            config=cfg,
            current_source=current_result.source,
            reference_source=reference_source,
            current_quality_score=current_result.quality_score,
            reference_quality_score=reference_quality,
            upstream_messages=(current_result.message, reference_message),
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
        if not _reference_has_required_windows(reference, cfg):
            warnings.append(
                "AK 2011 대응점/B Target 구간 또는 선행 STO 계산용 과거 이력이 부족합니다. "
                f"현재 범위 {reference_oldest or '?'}~{_latest_date(reference) or '?'}"
            )

        resolved_current_anchor = _resolve_date(current, cfg.current_anchor_date)
        if resolved_current_anchor is None:
            warnings.append("KODEX 기준일(T0)을 현재 데이터에서 찾지 못했습니다.")

        resolved_reference_anchor: str | None = None
        anchor_similarity: float | None = None
        if resolved_current_anchor is not None and _reference_has_required_windows(reference, cfg):
            if cfg.reference_anchor_date:
                resolved_reference_anchor = _resolve_exact_or_previous_in_window(
                    reference,
                    cfg.reference_anchor_date,
                    cfg.reference_window_start,
                    cfg.reference_window_end,
                )
                if resolved_reference_anchor is None:
                    warnings.append("지정한 AK홀딩스 기준일을 과거 대응구간에서 찾지 못했습니다.")
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
            resolved_target = _resolve_exact_or_previous_in_window(
                reference,
                cfg.reference_target_date,
                cfg.reference_target_window_start,
                cfg.reference_target_window_end,
            )
            target_selection = "직접 지정"
            if resolved_target is None:
                warnings.append("지정한 B Target 기준일을 과거 B 후보구간에서 찾지 못했습니다.")
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


def _load_reference_history(
    cfg: IntegratedWatchConfig,
) -> tuple[pd.DataFrame, str, str | None]:
    start, end = _reference_history_bounds(cfg)
    errors: list[str] = []

    try:
        from pykrx import stock

        raw = stock.get_market_ohlcv_by_date(
            start.strftime("%Y%m%d"),
            end.strftime("%Y%m%d"),
            cfg.reference_ticker,
            adjusted=True,
        )
        frame = _normalize_krx_ohlcv(raw)
        if not frame.empty:
            return frame, "pykrx · KRX 수정주가", None
        errors.append("pykrx: empty")
    except Exception as exc:
        errors.append(f"pykrx: {exc}")

    try:
        import yfinance as yf

        symbols = [f"{cfg.reference_ticker.zfill(6)}.KS", f"{cfg.reference_ticker.zfill(6)}.KQ"]
        for symbol in symbols:
            raw = yf.download(
                symbol,
                start=start.date().isoformat(),
                end=(end + pd.Timedelta(days=1)).date().isoformat(),
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            frame = _normalize_ohlcv(raw)
            if not frame.empty:
                return frame, f"yfinance · {symbol}", None
        errors.append("yfinance: empty")
    except Exception as exc:
        errors.append(f"yfinance: {exc}")

    return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"]), "역사 데이터 없음", " | ".join(errors)


def _reference_history_bounds(cfg: IntegratedWatchConfig) -> tuple[pd.Timestamp, pd.Timestamp]:
    candidates = [
        pd.Timestamp(cfg.reference_window_start),
        pd.Timestamp(cfg.reference_window_end),
        pd.Timestamp(cfg.reference_target_window_start),
        pd.Timestamp(cfg.reference_target_window_end),
    ]
    if cfg.reference_anchor_date:
        candidates.append(pd.Timestamp(cfg.reference_anchor_date))
    if cfg.reference_target_date:
        candidates.append(pd.Timestamp(cfg.reference_target_date))
    core_start = min(candidates)
    core_end = max(candidates)
    return core_start - pd.Timedelta(days=550), core_end + pd.Timedelta(days=120)


def _reference_has_required_windows(reference: pd.DataFrame, cfg: IntegratedWatchConfig) -> bool:
    if reference.empty:
        return False
    frame = _normalize_ohlcv(reference)
    if frame.empty:
        return False
    anchor_start = pd.Timestamp(cfg.reference_window_start)
    anchor_end = pd.Timestamp(cfg.reference_window_end)
    target_start = pd.Timestamp(cfg.reference_target_window_start)
    target_end = pd.Timestamp(cfg.reference_target_window_end)
    anchor_rows = frame[(frame["Date"] >= anchor_start) & (frame["Date"] <= anchor_end)]
    target_rows = frame[(frame["Date"] >= target_start) & (frame["Date"] <= target_end)]
    prehistory = frame[frame["Date"] < anchor_start]
    return bool(not anchor_rows.empty and not target_rows.empty and len(prehistory) >= 120)


def _normalize_krx_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    data = frame.reset_index().rename(
        columns={
            "날짜": "Date",
            "일자": "Date",
            "시가": "Open",
            "고가": "High",
            "저가": "Low",
            "종가": "Close",
            "거래량": "Volume",
        }
    )
    if "Date" not in data.columns and len(data.columns):
        data = data.rename(columns={data.columns[0]: "Date"})
    return _normalize_ohlcv(data)


def _quality_score(frame: pd.DataFrame) -> int:
    data = _normalize_ohlcv(frame)
    if data.empty:
        return 0
    score = 100
    if len(data) < 120:
        score -= 20
    missing = data[["Open", "High", "Low", "Close", "Volume"]].isna().mean().mean()
    score -= int(float(missing) * 50)
    if (data["Close"].astype(float) <= 0).any():
        score -= 30
    return max(0, min(100, score))


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
    result = frame.copy()
    if isinstance(result.columns, pd.MultiIndex):
        result.columns = [column[0] if isinstance(column, tuple) else column for column in result.columns]
    result = result.rename(
        columns={
            "trade_date": "Date",
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
            "Adj Close": "Close",
        }
    )
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


def _resolve_exact_or_previous_in_window(
    frame: pd.DataFrame,
    requested: str | None,
    window_start: str,
    window_end: str,
) -> str | None:
    if frame.empty or not requested:
        return None
    requested_ts = pd.Timestamp(requested).normalize()
    start = pd.Timestamp(window_start).normalize()
    end = pd.Timestamp(window_end).normalize()
    eligible = frame[
        (frame["Date"].dt.normalize() >= start)
        & (frame["Date"].dt.normalize() <= end)
        & (frame["Date"].dt.normalize() <= requested_ts)
    ]
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
