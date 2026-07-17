from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta

import pandas as pd

from recommendation.event_recommender import EventRecommendation, ReplayMatch
from surge.multi_horizon import MULTI_PATTERN_VERSION, MultiHorizonSurgePatternRecommender

ProgressCallback = Callable[[dict[str, object]], None]
CancelCheck = Callable[[], bool]


class RecommendationCancelled(RuntimeError):
    """Raised when a running recommendation job is cancelled by the user."""


class InteractiveSurgePatternRecommender(MultiHorizonSurgePatternRecommender):
    """Official ADE pre-surge recommender.

    One clear rule:
    compare every active symbol's latest 120 sessions with historical
    120-session patterns immediately preceding a real +30% surge.
    """

    WEEKLY_WEIGHT = 0.60
    STO_WEIGHT = 0.40

    def recommend_interactive(
        self,
        candidate_years: int = 2,
        lookback_months: int = 6,
        top_n: int = 20,
        weekly_pool_n: int = 100,
        min_weekly_similarity: float = 85.0,
        min_sto_similarity: float = 85.0,
        replay_top_n: int = 5,
        use_recent_replay: bool = True,
        use_weekly_filter: bool = True,
        use_sto_filter: bool = True,
        progress_callback: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> tuple[list[EventRecommendation], dict[str, object]]:
        # Legacy arguments remain only so older schedulers keep working.
        del lookback_months, use_recent_replay, use_weekly_filter, use_sto_filter

        candidate_years = max(1, int(candidate_years))
        pattern_limit = max(10, int(weekly_pool_n))
        replay_top_n = max(1, int(replay_top_n))
        top_n = max(1, int(top_n))

        def cancelled() -> bool:
            return bool(cancel_check and cancel_check())

        def publish(stage: str, current: int, total: int, message: str, **extra: object) -> None:
            if progress_callback is None:
                return
            progress_callback(
                {
                    "stage": stage,
                    "current": current,
                    "total": total,
                    "progress": 0.0 if total <= 0 else min(1.0, max(0.0, current / total)),
                    "message": message,
                    **extra,
                }
            )

        market, source = self._market_and_source()
        cutoff = (datetime.now().date() - timedelta(days=candidate_years * 365)).isoformat()
        patterns = self.conn.execute(
            """
            SELECT *
            FROM surge_patterns
            WHERE market=? AND pattern_version=? AND surge_start_date>=?
            ORDER BY surge_start_date DESC, surge_return_pct DESC
            LIMIT ?
            """,
            (market, MULTI_PATTERN_VERSION, cutoff, pattern_limit),
        ).fetchall()
        if not patterns:
            raise RuntimeError(
                f"최근 {candidate_years}년 급등직전 패턴이 없습니다. 패턴 DB를 다시 구축하세요."
            )

        publish("PREPARE", 0, len(patterns), "과거 급등직전 120일 패턴을 준비하고 있습니다.")
        prepared: list[tuple[sqlite3.Row, object, object]] = []
        for index, row in enumerate(patterns, start=1):
            if cancelled():
                raise RecommendationCancelled("사용자가 추천 생성을 중단했습니다.")
            item = self._prepare_pattern(row)
            if item is not None:
                prepared.append(item)
            if index == len(patterns) or index % 50 == 0:
                publish("PREPARE", index, len(patterns), "과거 급등직전 120일 패턴을 준비하고 있습니다.")

        symbols = self._active_symbols(market)
        diagnostics: dict[str, object] = {
            "algorithm": "pre-surge-120d-simple-v1",
            "market": market,
            "candidate_years": candidate_years,
            "replay_cutoff": cutoff,
            "pattern_pool": pattern_limit,
            "min_weekly_similarity": float(min_weekly_similarity),
            "min_sto_similarity": float(min_sto_similarity),
            "weekly_weight": self.WEEKLY_WEIGHT,
            "sto_weight": self.STO_WEIGHT,
            "patterns_loaded": len(patterns),
            "patterns_prepared": len(prepared),
            "symbols_total": len(symbols),
            "symbols_with_120d": 0,
            "weekly_pass_comparisons": 0,
            "sto_pass_comparisons": 0,
            "symbols_with_matches": 0,
            "final_recommendations": 0,
        }
        ranked_results: list[tuple[float, float, EventRecommendation]] = []

        for symbol_index, symbol in enumerate(symbols, start=1):
            if cancelled():
                diagnostics["cancelled_at_symbol"] = symbol_index
                raise RecommendationCancelled("사용자가 추천 생성을 중단했습니다.")

            ticker = str(symbol["ticker"])
            data = self.price_repo.fetch_dataframe(market, ticker, source=source)
            current = data.tail(120).reset_index(drop=True)
            if len(current) < 120:
                publish("MATCH", symbol_index, len(symbols), f"{ticker}: 120일 데이터 부족", diagnostics=diagnostics.copy())
                continue

            diagnostics["symbols_with_120d"] = int(diagnostics["symbols_with_120d"]) + 1
            current_weekly = self.weekly_engine.extract(current)
            current_sto = self.sto_engine.extract(current)
            candidate_matches: list[tuple[float, sqlite3.Row, ReplayMatch]] = []

            for pattern_index, (row, weekly, sto) in enumerate(prepared, start=1):
                if pattern_index % 50 == 0 and cancelled():
                    diagnostics["cancelled_at_symbol"] = symbol_index
                    raise RecommendationCancelled("사용자가 추천 생성을 중단했습니다.")

                weekly_score = self.weekly_engine.similarity(current_weekly, weekly)
                if weekly_score < min_weekly_similarity:
                    continue
                diagnostics["weekly_pass_comparisons"] = int(diagnostics["weekly_pass_comparisons"]) + 1

                sto_score = self.sto_engine.similarity(current_sto, sto)
                if sto_score < min_sto_similarity:
                    continue
                diagnostics["sto_pass_comparisons"] = int(diagnostics["sto_pass_comparisons"]) + 1

                final_score = (
                    weekly_score * self.WEEKLY_WEIGHT
                    + sto_score * self.STO_WEIGHT
                )
                match = ReplayMatch(
                    event_id=str(row["pattern_id"]),
                    event_date=str(row["surge_start_date"]),
                    market=str(row["market"]),
                    ticker=str(row["ticker"]),
                    name=row["name"],
                    weekly_similarity=weekly_score,
                    sto_similarity=sto_score,
                    final_similarity=final_score,
                    max_return=float(row["surge_return_pct"]),
                    max_drawdown=None,
                    equivalent_week_index=25,
                    future_start_week_index=26,
                    weeks_compared=26,
                    future_weeks_available=max(1, int(row["surge_horizon_days"]) // 5),
                )
                candidate_matches.append((final_score, row, match))

            candidate_matches.sort(
                key=lambda item: (
                    item[0],
                    item[2].weekly_similarity,
                    item[2].sto_similarity,
                    item[2].max_return or 0.0,
                ),
                reverse=True,
            )
            selected = candidate_matches[:replay_top_n]
            if selected:
                diagnostics["symbols_with_matches"] = int(diagnostics["symbols_with_matches"]) + 1
                matches = [item[2] for item in selected]
                best_score, best_row, best = selected[0]
                average_score = sum(item.final_similarity for item in matches) / len(matches)
                average_surge = sum(float(item.max_return or 0.0) for item in matches) / len(matches)
                average_days = sum(
                    float(row["target_hit_day"] or row["surge_horizon_days"])
                    for _, row, _ in selected
                ) / len(selected)

                reasons = [
                    "현재 최근 120거래일을 과거 실제 급등 직전 120거래일과 비교",
                    f"최종 유사도 = 주봉 60% + STO 40%: {best_score:.2f}%",
                    f"주봉 {best.weekly_similarity:.2f}% · STO {best.sto_similarity:.2f}%",
                    f"가장 유사한 과거 사례: {best.ticker} · {best.event_date}",
                    f"상위 {len(matches)}개 사례 평균 유사도 {average_score:.2f}%",
                    f"평균 30% 도달기간 {average_days:.1f}거래일 · 평균 최대상승 {average_surge:+.2f}%",
                ]
                recommendation = EventRecommendation(
                    market=market,
                    ticker=ticker,
                    name=symbol["name"],
                    recent_event_date=str(pd.Timestamp(current.iloc[-1]["Date"]).date()),
                    recent_money_ratio=0.0,
                    matched_event_id=best.event_id,
                    matched_event_date=best.event_date,
                    weekly_similarity=best.weekly_similarity,
                    sto_similarity=best.sto_similarity,
                    final_similarity=best.final_similarity,
                    matched_max_return=best.max_return,
                    matched_max_drawdown=None,
                    decision="RECOMMEND",
                    reasons=reasons,
                    replay_matches=matches,
                    prediction=None,
                )
                ranked_results.append((best_score, average_score, recommendation))

            publish("MATCH", symbol_index, len(symbols), f"{ticker} 분석 완료", ticker=ticker, diagnostics=diagnostics.copy())

        publish("RANK", 0, 1, "유사도가 높은 종목 순으로 정렬하고 있습니다.", diagnostics=diagnostics.copy())
        ranked_results.sort(
            key=lambda item: (
                item[0],
                item[1],
                item[2].weekly_similarity,
                item[2].sto_similarity,
            ),
            reverse=True,
        )
        recommendations = [item[2] for item in ranked_results[:top_n]]
        diagnostics["final_recommendations"] = len(recommendations)
        publish("COMPLETE", 1, 1, "추천 분석이 완료되었습니다.", diagnostics=diagnostics.copy())
        return recommendations, diagnostics
