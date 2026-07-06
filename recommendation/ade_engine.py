from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from candidate.scanner import CandidateScore, scan_candidates
from datahub.repository import PriceRepository
from pattern.cross_universe_replay import CrossUniverseReplayEngine, CrossUniverseReplayResult
from report.replay_chart_report import ReplayChartReportWriter


@dataclass(frozen=True)
class ADERecommendation:
    rank: int
    candidate: CandidateScore
    replay: CrossUniverseReplayResult
    final_score: int
    grade: str
    action: str
    report_path: str | None
    reasons: list[str]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["candidate"] = self.candidate.to_dict()
        data["replay"] = self.replay.to_dict()
        return data


class ADERecommendationEngine:
    """Candidate scan -> replay analysis -> visual report -> final recommendation."""

    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.db_path = Path(db_path)

    def recommend(
        self,
        *,
        candidate_min_score: int = 55,
        candidate_top_n: int = 30,
        final_top_n: int = 10,
        replay_top_n: int = 20,
        min_similarity: float = 55.0,
        generate_reports: bool = True,
    ) -> list[ADERecommendation]:
        candidates = scan_candidates(self.db_path, min_score=candidate_min_score, top_n=candidate_top_n)
        repository = PriceRepository(self.db_path)
        recommendations: list[ADERecommendation] = []
        try:
            replay_engine = CrossUniverseReplayEngine(repository)
            report_writer = ReplayChartReportWriter(repository)
            for candidate in candidates:
                replay = replay_engine.search(
                    candidate.market,
                    candidate.ticker,
                    top_n=replay_top_n,
                    min_similarity=min_similarity,
                )
                final_score = self._final_score(candidate, replay)
                grade = self._grade(final_score)
                action = self._action(grade)
                report_path = None
                if generate_reports:
                    report_path = str(report_writer.write(replay))
                recommendations.append(
                    ADERecommendation(
                        rank=0,
                        candidate=candidate,
                        replay=replay,
                        final_score=final_score,
                        grade=grade,
                        action=action,
                        report_path=report_path,
                        reasons=self._reasons(candidate, replay),
                    )
                )
        finally:
            repository.close()

        recommendations = sorted(recommendations, key=lambda item: item.final_score, reverse=True)[:final_top_n]
        return [
            ADERecommendation(
                rank=index,
                candidate=item.candidate,
                replay=item.replay,
                final_score=item.final_score,
                grade=item.grade,
                action=item.action,
                report_path=item.report_path,
                reasons=item.reasons,
            )
            for index, item in enumerate(recommendations, start=1)
        ]

    @staticmethod
    def _final_score(candidate: CandidateScore, replay: CrossUniverseReplayResult) -> int:
        replay_score = replay.replay_probability
        candidate_score = candidate.score
        sample_score = min(100, len(replay.cases) * 5)
        win_score = replay.win_rate_20d if replay.win_rate_20d is not None else 50
        ret_score = 50 if replay.avg_return_20d is None else min(100, max(0, 50 + replay.avg_return_20d * 4))
        score = candidate_score * 0.30 + replay_score * 0.35 + sample_score * 0.10 + win_score * 0.10 + ret_score * 0.15
        return round(max(0, min(100, score)))

    @staticmethod
    def _grade(score: int) -> str:
        if score >= 82:
            return "S"
        if score >= 70:
            return "A"
        if score >= 58:
            return "B"
        if score >= 45:
            return "C"
        return "D"

    @staticmethod
    def _action(grade: str) -> str:
        return {
            "S": "STRONG_RECOMMEND",
            "A": "RECOMMEND",
            "B": "WATCH_OR_SCALE",
            "C": "WATCH_ONLY",
            "D": "EXCLUDE",
        }[grade]

    @staticmethod
    def _reasons(candidate: CandidateScore, replay: CrossUniverseReplayResult) -> list[str]:
        reasons = list(candidate.reasons[:6])
        reasons.append(f"Replay probability {replay.replay_probability}% / grade {replay.grade}")
        if replay.avg_return_20d is not None:
            reasons.append(f"Similar cases average 20D return {replay.avg_return_20d:+.2f}%")
        if replay.win_rate_20d is not None:
            reasons.append(f"Similar cases 20D win rate {replay.win_rate_20d:.1f}%")
        return reasons
