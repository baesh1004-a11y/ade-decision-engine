from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta
from time import perf_counter

import pandas as pd

from prediction.replay_prediction import ReplayPredictionEngine
from recommendation.event_recommender import EventRecommendation, ReplayMatch
from sto.structure_similarity import STOStructure
from surge.multi_horizon import MULTI_PATTERN_VERSION, MultiHorizonSurgePatternRecommender
from weekly.shape_similarity import WeeklyShape

ProgressCallback = Callable[[dict[str, object]], None]
CancelCheck = Callable[[], bool]

FEATURE_CACHE_VERSION = "weekly26-sto3layer-v2-fingerprint"


class RecommendationCancelled(RuntimeError):
    """Raised when a running recommendation job is cancelled by the user."""


class InteractiveSurgePatternRecommender(MultiHorizonSurgePatternRecommender):
    """Official ADE pre-surge recommender."""

    def _ensure_feature_cache(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recommendation_feature_cache (
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                last_trade_date TEXT NOT NULL,
                feature_version TEXT NOT NULL,
                data_fingerprint TEXT NOT NULL DEFAULT '',
                weekly_json TEXT NOT NULL,
                sto_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (market, ticker, last_trade_date, feature_version)
            )
            """
        )
        columns = {str(row[1]) for row in self.conn.execute("PRAGMA table_info(recommendation_feature_cache)").fetchall()}
        if "data_fingerprint" not in columns:
            self.conn.execute("ALTER TABLE recommendation_feature_cache ADD COLUMN data_fingerprint TEXT NOT NULL DEFAULT ''")
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_recommendation_feature_cache_lookup
            ON recommendation_feature_cache(market, ticker, last_trade_date, feature_version)
            """
        )
        self.conn.commit()

    @staticmethod
    def _weekly_from_dict(payload: dict[str, object]) -> WeeklyShape:
        return WeeklyShape(
            normalized_close=list(payload.get("normalized_close") or []),
            normalized_high=list(payload.get("normalized_high") or []),
            normalized_low=list(payload.get("normalized_low") or []),
            volume_ratio=list(payload.get("volume_ratio") or []),
            box_width=float(payload.get("box_width") or 0.0),
            pullback_depth=float(payload.get("pullback_depth") or 0.0),
            breakout_angle=float(payload.get("breakout_angle") or 0.0),
            trend_slope=float(payload.get("trend_slope") or 0.0),
            labels=list(payload.get("labels") or []),
        )

    @staticmethod
    def _sto_from_dict(payload: dict[str, object]) -> STOStructure:
        return STOStructure(
            short=float(payload.get("short") or 0.0),
            middle=float(payload.get("middle") or 0.0),
            long=float(payload.get("long") or 0.0),
            spread_sm=float(payload.get("spread_sm") or 0.0),
            spread_ml=float(payload.get("spread_ml") or 0.0),
            convergence=float(payload.get("convergence") or 0.0),
            slope_short=float(payload.get("slope_short") or 0.0),
            slope_middle=float(payload.get("slope_middle") or 0.0),
            slope_long=float(payload.get("slope_long") or 0.0),
            arrangement=str(payload.get("arrangement") or "UNKNOWN"),
            vector=list(payload.get("vector") or []),
            labels=list(payload.get("labels") or []),
            short_path=list(payload.get("short_path") or []),
            middle_path=list(payload.get("middle_path") or []),
            long_path=list(payload.get("long_path") or []),
        )

    @staticmethod
    def _data_fingerprint(current: pd.DataFrame, source: str) -> str:
        columns = [name for name in ("Date", "Open", "High", "Low", "Close", "Volume") if name in current.columns]
        payload = current[columns].tail(120).copy()
        if "Date" in payload.columns:
            payload["Date"] = pd.to_datetime(payload["Date"], errors="coerce").astype(str)
        serialized = payload.to_json(orient="split", date_format="iso", double_precision=10)
        raw = f"{source}|{len(payload)}|{serialized}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _load_cached_features(self, market: str, ticker: str, last_trade_date: str, data_fingerprint: str) -> tuple[WeeklyShape, STOStructure] | None:
        row = self.conn.execute(
            """
            SELECT weekly_json, sto_json, data_fingerprint
            FROM recommendation_feature_cache
            WHERE market=? AND ticker=? AND last_trade_date=? AND feature_version=?
            """,
            (market, ticker, last_trade_date, FEATURE_CACHE_VERSION),
        ).fetchone()
        if row is None or str(row["data_fingerprint"] or "") != data_fingerprint:
            return None
        try:
            weekly_payload = json.loads(str(row["weekly_json"]))
            sto_payload = json.loads(str(row["sto_json"]))
            return self._weekly_from_dict(weekly_payload), self._sto_from_dict(sto_payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    def _save_cached_features(self, market: str, ticker: str, last_trade_date: str, data_fingerprint: str, weekly: WeeklyShape, sto: STOStructure) -> None:
        self.conn.execute(
            """
            INSERT INTO recommendation_feature_cache(
                market, ticker, last_trade_date, feature_version, data_fingerprint, weekly_json, sto_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market, ticker, last_trade_date, feature_version)
            DO UPDATE SET data_fingerprint=excluded.data_fingerprint,
                          weekly_json=excluded.weekly_json,
                          sto_json=excluded.sto_json,
                          updated_at=CURRENT_TIMESTAMP
            """,
            (
                market,
                ticker,
                last_trade_date,
                FEATURE_CACHE_VERSION,
                data_fingerprint,
                json.dumps(weekly.to_dict(), ensure_ascii=False, separators=(",", ":")),
                json.dumps(sto.to_dict(), ensure_ascii=False, separators=(",", ":")),
            ),
        )

    def recommend_interactive(self, candidate_years: int = 2, lookback_months: int = 6, top_n: int = 20, weekly_pool_n: int = 100, min_weekly_similarity: float = 85.0, min_sto_similarity: float = 85.0, replay_top_n: int = 5, use_recent_replay: bool = True, use_weekly_filter: bool = True, use_sto_filter: bool = True, progress_callback: ProgressCallback | None = None, cancel_check: CancelCheck | None = None) -> tuple[list[EventRecommendation], dict[str, object]]:
        del lookback_months, use_recent_replay, use_weekly_filter, use_sto_filter
        self._ensure_feature_cache()
        prediction_engine = ReplayPredictionEngine(self.db_path)
        started = perf_counter()
        candidate_years = max(1, int(candidate_years))
        pattern_limit = max(10, int(weekly_pool_n))
        replay_top_n = max(1, int(replay_top_n))
        top_n = max(1, int(top_n))

        def log(message: str) -> None:
            print(f"[ADE][RECOMMEND] {message}", flush=True)

        def cancelled() -> bool:
            return bool(cancel_check and cancel_check())

        def publish(stage: str, current: int, total: int, message: str, **extra: object) -> None:
            if progress_callback is not None:
                progress_callback({"stage": stage, "current": current, "total": total, "progress": 0.0 if total <= 0 else min(1.0, max(0.0, current / total)), "message": message, **extra})

        market, source = self._market_and_source()
        cutoff = (datetime.now().date() - timedelta(days=candidate_years * 365)).isoformat()
        log(f"start market={market} source={source} years={candidate_years} pattern_limit={pattern_limit} weekly_min={min_weekly_similarity:.1f} sto_min={min_sto_similarity:.1f} top_n={top_n}")

        pattern_query_started = perf_counter()
        patterns = self.conn.execute(
            """
            SELECT * FROM surge_patterns
            WHERE market=? AND pattern_version=? AND surge_start_date>=?
            ORDER BY surge_start_date DESC, surge_return_pct DESC
            LIMIT ?
            """,
            (market, MULTI_PATTERN_VERSION, cutoff, pattern_limit),
        ).fetchall()
        duration_pattern_query = perf_counter() - pattern_query_started
        if not patterns:
            prediction_engine.close()
            raise RuntimeError(f"최근 {candidate_years}년 급등직전 패턴이 없습니다. 패턴 DB를 다시 구축하세요.")

        diagnostics: dict[str, object] = {
            "algorithm": "pre-surge-120d-weekly-rank-sto-filter-v3",
            "market": market,
            "candidate_years": candidate_years,
            "replay_cutoff": cutoff,
            "pattern_pool": pattern_limit,
            "min_weekly_similarity": float(min_weekly_similarity),
            "min_sto_similarity": float(min_sto_similarity),
            "patterns_loaded": len(patterns),
            "patterns_prepared": 0,
            "patterns_rejected": 0,
            "symbols_total": 0,
            "symbols_db_hit": 0,
            "symbols_db_miss": 0,
            "symbols_external_fetch": 0,
            "symbols_price_error": 0,
            "symbols_with_120d": 0,
            "symbols_without_120d": 0,
            "feature_cache_hit": 0,
            "feature_cache_miss": 0,
            "weekly_pass_comparisons": 0,
            "sto_pass_comparisons": 0,
            "symbols_with_weekly_pass": 0,
            "symbols_with_sto_pass": 0,
            "symbols_with_matches": 0,
            "predictions_created": 0,
            "prediction_samples_missing": 0,
            "final_recommendations": 0,
            "duration_pattern_query_seconds": round(duration_pattern_query, 3),
            "duration_prepare_seconds": 0.0,
            "duration_symbol_list_seconds": 0.0,
            "duration_bulk_price_load_seconds": 0.0,
            "duration_price_load_seconds": 0.0,
            "duration_feature_cache_read_seconds": 0.0,
            "duration_feature_extract_seconds": 0.0,
            "duration_feature_cache_write_seconds": 0.0,
            "duration_weekly_compare_seconds": 0.0,
            "duration_sto_compare_seconds": 0.0,
            "duration_prediction_seconds": 0.0,
            "duration_sort_seconds": 0.0,
            "duration_match_seconds": 0.0,
            "duration_total_seconds": 0.0,
            "slowest_symbols": [],
        }

        prepare_started = perf_counter()
        publish("PREPARE", 0, len(patterns), "과거 급등직전 120일 패턴을 준비하고 있습니다.", diagnostics=diagnostics.copy())
        prepared: list[tuple[sqlite3.Row, object, object]] = []
        for index, row in enumerate(patterns, start=1):
            if cancelled():
                prediction_engine.close()
                raise RecommendationCancelled("사용자가 추천 생성을 중단했습니다.")
            item = self._prepare_pattern(row)
            if item is not None:
                prepared.append(item)
            else:
                diagnostics["patterns_rejected"] = int(diagnostics["patterns_rejected"]) + 1
            if index == len(patterns) or index % 50 == 0:
                diagnostics["patterns_prepared"] = len(prepared)
                publish("PREPARE", index, len(patterns), "과거 급등직전 120일 패턴을 준비하고 있습니다.", diagnostics=diagnostics.copy())
        diagnostics["patterns_prepared"] = len(prepared)
        diagnostics["duration_prepare_seconds"] = round(perf_counter() - prepare_started, 3)
        if not prepared:
            prediction_engine.close()
            raise RuntimeError("조회된 급등직전 패턴을 비교 가능한 형태로 준비하지 못했습니다.")

        symbol_list_started = perf_counter()
        symbols = self._active_symbols(market)
        diagnostics["duration_symbol_list_seconds"] = round(perf_counter() - symbol_list_started, 3)
        diagnostics["symbols_total"] = len(symbols)

        bulk_started = perf_counter()
        try:
            bulk_prices = self.price_repo.fetch_latest_by_ticker(market, limit_per_ticker=120, source=source)
        except Exception as exc:
            log(f"bulk_price_error type={type(exc).__name__} message={exc}")
            bulk_prices = {}
        diagnostics["duration_bulk_price_load_seconds"] = round(perf_counter() - bulk_started, 3)
        log(f"bulk_price_load symbols={len(bulk_prices)} duration={diagnostics['duration_bulk_price_load_seconds']}s")

        ranked_results: list[tuple[float, float, EventRecommendation]] = []
        match_started = perf_counter()
        slowest_symbols: list[dict[str, object]] = []
        pending_cache_writes = 0

        for symbol_index, symbol in enumerate(symbols, start=1):
            if cancelled():
                diagnostics["cancelled_at_symbol"] = symbol_index
                prediction_engine.close()
                raise RecommendationCancelled("사용자가 추천 생성을 중단했습니다.")
            ticker = str(symbol["ticker"])
            symbol_started = perf_counter()
            price_seconds = feature_seconds = weekly_seconds = sto_seconds = 0.0
            price_started = perf_counter()
            try:
                data = bulk_prices.get(ticker)
                if data is None or data.empty:
                    diagnostics["symbols_db_miss"] = int(diagnostics["symbols_db_miss"]) + 1
                    data = pd.DataFrame()
                else:
                    diagnostics["symbols_db_hit"] = int(diagnostics["symbols_db_hit"]) + 1
            except Exception as exc:
                diagnostics["symbols_price_error"] = int(diagnostics["symbols_price_error"]) + 1
                log(f"price_error ticker={ticker} type={type(exc).__name__} message={exc}")
                data = pd.DataFrame()
            price_seconds = perf_counter() - price_started
            diagnostics["duration_price_load_seconds"] = round(float(diagnostics["duration_price_load_seconds"]) + price_seconds, 3)
            current = data.tail(120).reset_index(drop=True)
            if len(current) < 120:
                diagnostics["symbols_without_120d"] = int(diagnostics["symbols_without_120d"]) + 1
                continue
            diagnostics["symbols_with_120d"] = int(diagnostics["symbols_with_120d"]) + 1
            last_trade_date = str(pd.Timestamp(current.iloc[-1]["Date"]).date())
            data_fingerprint = self._data_fingerprint(current, source)
            cache_read_started = perf_counter()
            cached = self._load_cached_features(market, ticker, last_trade_date, data_fingerprint)
            diagnostics["duration_feature_cache_read_seconds"] = round(float(diagnostics["duration_feature_cache_read_seconds"]) + (perf_counter() - cache_read_started), 3)
            if cached is not None:
                diagnostics["feature_cache_hit"] = int(diagnostics["feature_cache_hit"]) + 1
                current_weekly, current_sto = cached
            else:
                diagnostics["feature_cache_miss"] = int(diagnostics["feature_cache_miss"]) + 1
                feature_started = perf_counter()
                current_weekly = self.weekly_engine.extract(current)
                current_sto = self.sto_engine.extract(current)
                feature_seconds = perf_counter() - feature_started
                diagnostics["duration_feature_extract_seconds"] = round(float(diagnostics["duration_feature_extract_seconds"]) + feature_seconds, 3)
                cache_write_started = perf_counter()
                self._save_cached_features(market, ticker, last_trade_date, data_fingerprint, current_weekly, current_sto)
                diagnostics["duration_feature_cache_write_seconds"] = round(float(diagnostics["duration_feature_cache_write_seconds"]) + (perf_counter() - cache_write_started), 3)
                pending_cache_writes += 1

            candidate_matches: list[tuple[float, sqlite3.Row, ReplayMatch]] = []
            symbol_weekly_pass = symbol_sto_pass = False
            for row, pattern_weekly, pattern_sto in prepared:
                weekly_started = perf_counter()
                weekly_score = self.weekly_engine.similarity(current_weekly, pattern_weekly)
                weekly_seconds += perf_counter() - weekly_started
                diagnostics["duration_weekly_compare_seconds"] = round(float(diagnostics["duration_weekly_compare_seconds"]) + weekly_seconds, 3)
                if weekly_score < min_weekly_similarity:
                    continue
                diagnostics["weekly_pass_comparisons"] = int(diagnostics["weekly_pass_comparisons"]) + 1
                symbol_weekly_pass = True
                sto_started = perf_counter()
                sto_score = self.sto_engine.similarity(current_sto, pattern_sto)
                sto_seconds += perf_counter() - sto_started
                diagnostics["duration_sto_compare_seconds"] = round(float(diagnostics["duration_sto_compare_seconds"]) + sto_seconds, 3)
                if sto_score < min_sto_similarity:
                    continue
                diagnostics["sto_pass_comparisons"] = int(diagnostics["sto_pass_comparisons"]) + 1
                symbol_sto_pass = True
                match = ReplayMatch(
                    event_id=str(row["source_event_id"] or row["pattern_id"]) if "source_event_id" in row.keys() else str(row["pattern_id"]),
                    event_date=str(row["surge_start_date"]),
                    market=str(row["market"]),
                    ticker=str(row["ticker"]),
                    name=row["name"],
                    weekly_similarity=weekly_score,
                    sto_similarity=sto_score,
                    final_similarity=weekly_score,
                    max_return=float(row["surge_return_pct"]),
                    max_drawdown=None,
                    equivalent_week_index=25,
                    future_start_week_index=26,
                    weeks_compared=26,
                    future_weeks_available=max(1, int(row["surge_horizon_days"]) // 5),
                )
                candidate_matches.append((weekly_score, row, match))

            if symbol_weekly_pass:
                diagnostics["symbols_with_weekly_pass"] = int(diagnostics["symbols_with_weekly_pass"]) + 1
            if symbol_sto_pass:
                diagnostics["symbols_with_sto_pass"] = int(diagnostics["symbols_with_sto_pass"]) + 1
            candidate_matches.sort(key=lambda item: (item[0], item[2].sto_similarity, item[2].max_return or 0.0), reverse=True)
            selected = candidate_matches[:replay_top_n]
            if selected:
                diagnostics["symbols_with_matches"] = int(diagnostics["symbols_with_matches"]) + 1
                matches = [item[2] for item in selected]
                best_score, _best_row, best = selected[0]
                average_weekly = sum(item.weekly_similarity for item in matches) / len(matches)
                average_sto = sum(item.sto_similarity for item in matches) / len(matches)
                average_surge = sum(float(item.max_return or 0.0) for item in matches) / len(matches)
                average_days = sum(float(row["target_hit_day"] or row["surge_horizon_days"]) for _, row, _ in selected) / len(selected)
                prediction_started = perf_counter()
                prediction = prediction_engine.predict(matches)
                diagnostics["duration_prediction_seconds"] = round(float(diagnostics["duration_prediction_seconds"]) + (perf_counter() - prediction_started), 3)
                if prediction is not None:
                    diagnostics["predictions_created"] = int(diagnostics["predictions_created"]) + 1
                    diagnostics["prediction_samples_missing"] = int(diagnostics["prediction_samples_missing"]) + max(0, len(matches) - prediction.sample_count)
                else:
                    diagnostics["prediction_samples_missing"] = int(diagnostics["prediction_samples_missing"]) + len(matches)
                reasons = [
                    "현재 최근 120거래일을 과거 실제 급등 직전 120거래일과 비교",
                    f"추천 순위 점수는 주봉 유사도 단일 기준: {best_score:.2f}%",
                    f"STO는 최소 {min_sto_similarity:.1f}% 통과 필터이며 대표 사례 STO는 {best.sto_similarity:.2f}%",
                    f"가장 유사한 과거 사례: {best.ticker} · {best.event_date}",
                    f"상위 {len(matches)}개 사례 평균 주봉 {average_weekly:.2f}% · 평균 STO {average_sto:.2f}%",
                    f"평균 30% 도달기간 {average_days:.1f}거래일 · 평균 최대상승 {average_surge:+.2f}%",
                ]
                if prediction is not None:
                    reasons.extend([f"Replay Prediction 등급 {prediction.grade}", f"7거래일 상승확률 {prediction.seven_day_up_probability:.2f}% · 기대수익 {prediction.seven_day_expected_return:+.2f}%", f"목표수익 {prediction.target_return:+.2f}% · 참고 손절폭 {prediction.stop_return:.2f}% · 권장 보유 {prediction.holding_days}일"])
                recommendation = EventRecommendation(market=market, ticker=ticker, name=symbol["name"], recent_event_date=last_trade_date, recent_money_ratio=0.0, matched_event_id=best.event_id, matched_event_date=best.event_date, weekly_similarity=best.weekly_similarity, sto_similarity=best.sto_similarity, final_similarity=best.weekly_similarity, matched_max_return=best.max_return, matched_max_drawdown=None, decision="RECOMMEND", reasons=reasons, replay_matches=matches, prediction=prediction)
                ranked_results.append((best.weekly_similarity, average_weekly, recommendation))
            symbol_total = perf_counter() - symbol_started
            slowest_symbols.append({"ticker": ticker, "total_seconds": round(symbol_total, 4), "price_seconds": round(price_seconds, 4), "feature_seconds": round(feature_seconds, 4), "weekly_seconds": round(weekly_seconds, 4), "sto_seconds": round(sto_seconds, 4), "status": "MATCHED" if selected else "NO_MATCH"})
            slowest_symbols = sorted(slowest_symbols, key=lambda item: float(item["total_seconds"]), reverse=True)[:10]
            if symbol_index == len(symbols) or symbol_index % 25 == 0:
                diagnostics["duration_match_seconds"] = round(perf_counter() - match_started, 3)
                diagnostics["slowest_symbols"] = slowest_symbols
                publish("MATCH", symbol_index, len(symbols), f"{ticker} 분석 완료", ticker=ticker, diagnostics=diagnostics.copy())

        if pending_cache_writes:
            self.conn.commit()
        diagnostics["duration_match_seconds"] = round(perf_counter() - match_started, 3)
        sort_started = perf_counter()
        publish("RANK", 0, 1, "주봉 유사도가 높은 종목 순으로 정렬하고 있습니다.", diagnostics=diagnostics.copy())
        ranked_results.sort(key=lambda item: (item[0], item[1], item[2].sto_similarity), reverse=True)
        diagnostics["duration_sort_seconds"] = round(perf_counter() - sort_started, 3)
        recommendations = [item[2] for item in ranked_results[:top_n]]
        diagnostics["final_recommendations"] = len(recommendations)
        diagnostics["duration_total_seconds"] = round(perf_counter() - started, 3)
        prediction_engine.close()
        log(f"feature_cache hit={diagnostics['feature_cache_hit']} miss={diagnostics['feature_cache_miss']} version={FEATURE_CACHE_VERSION}")
        log(f"prediction created={diagnostics['predictions_created']} missing_samples={diagnostics['prediction_samples_missing']}")
        publish("COMPLETE", 1, 1, "추천 분석이 완료되었습니다.", diagnostics=diagnostics.copy())
        return recommendations, diagnostics
