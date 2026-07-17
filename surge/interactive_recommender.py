from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta

import pandas as pd

from recommendation.event_recommender import EventRecommendation, ReplayMatch
from surge.multi_horizon import MULTI_PATTERN_VERSION, SURGE_CLASSES, MultiHorizonSurgePatternRecommender

ProgressCallback = Callable[[dict[str, object]], None]
CancelCheck = Callable[[], bool]


class RecommendationCancelled(RuntimeError):
    """Raised when a running recommendation job is cancelled by the user."""


class InteractiveSurgePatternRecommender(MultiHorizonSurgePatternRecommender):
    """Multi-horizon recommender with optional filters, progress and cancellation hooks."""

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
        del lookback_months  # retained for API compatibility

        def cancelled() -> bool:
            return bool(cancel_check and cancel_check())

        def publish(stage: str, current: int, total: int, message: str, **extra: object) -> None:
            if progress_callback is None:
                return
            ratio = 0.0 if total <= 0 else min(1.0, max(0.0, current / total))
            progress_callback({
                "stage": stage,
                "current": current,
                "total": total,
                "progress": ratio,
                "message": message,
                **extra,
            })

        market, source = self._market_and_source()
        where = ["market=?", "pattern_version=?"]
        params: list[object] = [market, MULTI_PATTERN_VERSION]
        replay_cutoff: str | None = None
        if use_recent_replay:
            replay_cutoff = (datetime.now().date() - timedelta(days=max(1, candidate_years) * 365)).isoformat()
            where.append("money_event_date>=?")
            params.append(replay_cutoff)
        params.append(max(500, weekly_pool_n * 20))
        patterns = self.conn.execute(
            f"""
            SELECT * FROM surge_patterns
            WHERE {' AND '.join(where)}
            ORDER BY speed_weight DESC, surge_return_pct DESC, surge_start_date DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        if not patterns:
            scope = f"최근 {candidate_years}년" if use_recent_replay else "전체 기간"
            raise RuntimeError(f"{scope} 다중기간 급등직전 패턴이 없습니다. 패턴 DB를 다시 구축하세요.")

        publish("PREPARE", 0, len(patterns), "과거 급등 패턴을 준비하고 있습니다.")
        prepared = []
        for index, row in enumerate(patterns, start=1):
            if cancelled():
                raise RecommendationCancelled("사용자가 추천 생성을 중단했습니다.")
            item = self._prepare_pattern(row)
            if item is not None:
                prepared.append(item)
            if index == len(patterns) or index % 100 == 0:
                publish("PREPARE", index, len(patterns), "과거 급등 패턴을 준비하고 있습니다.")

        symbols = self._active_symbols(market)
        diagnostics: dict[str, object] = {
            "market": market,
            "use_recent_replay": use_recent_replay,
            "replay_years": candidate_years if use_recent_replay else None,
            "replay_cutoff": replay_cutoff,
            "use_weekly_filter": use_weekly_filter,
            "min_weekly_similarity": min_weekly_similarity if use_weekly_filter else None,
            "use_sto_filter": use_sto_filter,
            "min_sto_similarity": min_sto_similarity if use_sto_filter else None,
            "patterns_loaded": len(patterns),
            "patterns_prepared": len(prepared),
            "symbols_total": len(symbols),
            "symbols_with_120d": 0,
            "chart_pass_comparisons": 0,
            "sto_pass_comparisons": 0,
            "symbols_with_matches": 0,
            "final_recommendations": 0,
        }
        ranked_results: list[tuple[float, EventRecommendation]] = []

        for symbol_index, symbol in enumerate(symbols, start=1):
            if cancelled():
                diagnostics["cancelled_at_symbol"] = symbol_index
                raise RecommendationCancelled("사용자가 추천 생성을 중단했습니다.")

            data = self.price_repo.fetch_dataframe(market, str(symbol["ticker"]), source=source)
            current = data.tail(120).reset_index(drop=True)
            if len(current) < 120:
                publish("MATCH", symbol_index, len(symbols), f"{symbol['ticker']} 데이터 부족으로 건너뜀", diagnostics=diagnostics.copy())
                continue

            diagnostics["symbols_with_120d"] = int(diagnostics["symbols_with_120d"]) + 1
            current_weekly = self.weekly_engine.extract(current)
            current_sto = self.sto_engine.extract(current)
            candidate_matches: list[tuple[float, sqlite3.Row, ReplayMatch]] = []

            for pattern_index, (row, weekly, sto) in enumerate(prepared, start=1):
                if pattern_index % 100 == 0 and cancelled():
                    diagnostics["cancelled_at_symbol"] = symbol_index
                    raise RecommendationCancelled("사용자가 추천 생성을 중단했습니다.")

                chart_score = self.weekly_engine.similarity(current_weekly, weekly)
                chart_pass = (not use_weekly_filter) or chart_score >= min_weekly_similarity
                if not chart_pass:
                    continue
                diagnostics["chart_pass_comparisons"] = int(diagnostics["chart_pass_comparisons"]) + 1

                sto_score = self.sto_engine.similarity(current_sto, sto)
                sto_pass = (not use_sto_filter) or sto_score >= min_sto_similarity
                if not sto_pass:
                    continue
                diagnostics["sto_pass_comparisons"] = int(diagnostics["sto_pass_comparisons"]) + 1

                enabled_scores = []
                if use_weekly_filter:
                    enabled_scores.append(chart_score)
                if use_sto_filter:
                    enabled_scores.append(sto_score)
                raw_similarity = min(enabled_scores) if enabled_scores else (chart_score + sto_score) / 2.0
                weighted_score = raw_similarity * float(row["speed_weight"] or 1.0)
                match = ReplayMatch(
                    event_id=str(row["pattern_id"]),
                    event_date=str(row["surge_start_date"]),
                    market=str(row["market"]),
                    ticker=str(row["ticker"]),
                    name=row["name"],
                    weekly_similarity=chart_score,
                    sto_similarity=sto_score,
                    final_similarity=raw_similarity,
                    max_return=float(row["surge_return_pct"]),
                    max_drawdown=None,
                    equivalent_week_index=25,
                    future_start_week_index=26,
                    weeks_compared=26,
                    future_weeks_available=max(1, int(row["surge_horizon_days"]) // 5),
                )
                candidate_matches.append((weighted_score, row, match))

            candidate_matches.sort(key=lambda item: (item[0], item[2].final_similarity, item[2].max_return or 0.0), reverse=True)
            selected = candidate_matches[:replay_top_n]
            if selected:
                diagnostics["symbols_with_matches"] = int(diagnostics["symbols_with_matches"]) + 1
                matches = [item[2] for item in selected]
                best_weighted, best_row, best = selected[0]
                average_surge = sum(float(item.max_return or 0.0) for item in matches) / len(matches)
                class_counts: dict[str, int] = {name: 0 for name, _, _ in SURGE_CLASSES}
                weighted_days = 0.0
                total_weight = 0.0
                for _, row, _ in selected:
                    cls = str(row["surge_class"])
                    class_counts[cls] = class_counts.get(cls, 0) + 1
                    weight = float(row["speed_weight"] or 1.0)
                    weighted_days += float(row["target_hit_day"] or row["surge_horizon_days"]) * weight
                    total_weight += weight
                expected_days = weighted_days / total_weight if total_weight else 0.0
                distribution = " · ".join(f"{name} {class_counts.get(name, 0)}" for name, _, _ in SURGE_CLASSES)
                active_filters = []
                if use_recent_replay:
                    active_filters.append(f"최근 {candidate_years}년 Replay")
                if use_weekly_filter:
                    active_filters.append(f"주봉 {min_weekly_similarity:.0f}% 이상")
                if use_sto_filter:
                    active_filters.append(f"STO {min_sto_similarity:.0f}% 이상")
                reasons = [
                    "적용 옵션: " + (" · ".join(active_filters) if active_filters else "유사도 필터 없음"),
                    f"차트 유사도 {best.weekly_similarity:.2f}% · STO 3계층 유사도 {best.sto_similarity:.2f}%",
                    f"Top1 유형 {best_row['surge_class']} · 30% 최초 도달 {int(best_row['target_hit_day'])}거래일",
                    f"속도 가중점수 {best_weighted:.2f} · 예상 30% 도달 {expected_days:.1f}거래일",
                    f"매칭 {len(matches)}건 · 유형분포 {distribution}",
                    f"매칭 사례 평균 최대상승률 {average_surge:+.2f}%",
                ]
                recommendation = EventRecommendation(
                    market=market,
                    ticker=str(symbol["ticker"]),
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
                    decision="RECOMMEND" if len(matches) >= 2 else "WATCH",
                    reasons=reasons,
                    replay_matches=matches,
                    prediction=None,
                )
                confidence = min(1.0, len(matches) / max(2.0, float(replay_top_n)))
                ranking_score = best_weighted * (0.85 + 0.15 * confidence)
                ranked_results.append((ranking_score, recommendation))

            publish("MATCH", symbol_index, len(symbols), f"{symbol['ticker']} 분석 완료", ticker=str(symbol["ticker"]), diagnostics=diagnostics.copy())

        publish("RANK", 0, 1, "통과 종목의 최종 순위를 계산하고 있습니다.", diagnostics=diagnostics.copy())
        ranked_results.sort(key=lambda item: (item[0], item[1].final_similarity, len(item[1].replay_matches), item[1].matched_max_return or 0.0), reverse=True)
        recommendations = [item[1] for item in ranked_results[:top_n]]
        diagnostics["final_recommendations"] = len(recommendations)
        publish("COMPLETE", 1, 1, "추천 분석이 완료되었습니다.", diagnostics=diagnostics.copy())
        return recommendations, diagnostics
