from __future__ import annotations

from dataclasses import dataclass

from calibration.persistence import CalibrationRepository
from calibration.updater import ProbabilityUpdater
from explain.engine import ExplainableAIEngine
from learning_v2.persistence import LearningV2Repository
from pattern.context import PatternContextEngine
from pattern.memory import PatternMemoryBuilder, PatternMemoryRepository
from pattern.memory_matching import PatternMemoryMatchingEngine
from strategy.entry import EntryTimingEngine
from strategy.exit import ExitDecisionEngine
from strategy.learning import LearningEngine
from strategy.portfolio import PortfolioManagerEngine
from strategy.position_sizing import PositionSizingEngine
from strategy.probability import ProbabilityEngine
from strategy.risk import RiskEngine


@dataclass
class EngineRegistry:
    """Central dependency registry for ADEPipeline.

    This keeps the pipeline constructor flexible and makes integration tests
    easier because repositories and engines can be injected from one place.
    """

    memory_repository: PatternMemoryRepository
    memory_builder: PatternMemoryBuilder
    memory_matching_engine: PatternMemoryMatchingEngine
    pattern_context_engine: PatternContextEngine
    probability_engine: ProbabilityEngine
    probability_updater: ProbabilityUpdater
    explain_engine: ExplainableAIEngine
    risk_engine: RiskEngine
    position_engine: PositionSizingEngine
    entry_engine: EntryTimingEngine
    exit_engine: ExitDecisionEngine
    portfolio_engine: PortfolioManagerEngine
    learning_engine: LearningEngine
    calibration_repository: CalibrationRepository | None = None
    learning_v2_repository: LearningV2Repository | None = None


def build_default_registry(
    memory_repository: PatternMemoryRepository | None = None,
    calibration_repository: CalibrationRepository | None = None,
    learning_v2_repository: LearningV2Repository | None = None,
    memory_window: int = 20,
    memory_top_k: int = 10,
    horizons: tuple[int, ...] = (5, 10, 20, 40),
) -> EngineRegistry:
    memory_repository = memory_repository or PatternMemoryRepository()
    memory_builder = PatternMemoryBuilder(window=memory_window, horizons=horizons)
    memory_matching_engine = PatternMemoryMatchingEngine(
        memory_repository,
        window=memory_window,
        top_k=memory_top_k,
        horizons=horizons,
    )
    return EngineRegistry(
        memory_repository=memory_repository,
        memory_builder=memory_builder,
        memory_matching_engine=memory_matching_engine,
        pattern_context_engine=PatternContextEngine(window=memory_window, top_k=memory_top_k, horizons=horizons),
        probability_engine=ProbabilityEngine(horizon_days=20),
        probability_updater=ProbabilityUpdater(),
        explain_engine=ExplainableAIEngine(),
        risk_engine=RiskEngine(),
        position_engine=PositionSizingEngine(),
        entry_engine=EntryTimingEngine(),
        exit_engine=ExitDecisionEngine(),
        portfolio_engine=PortfolioManagerEngine(),
        learning_engine=LearningEngine(),
        calibration_repository=calibration_repository,
        learning_v2_repository=learning_v2_repository,
    )
