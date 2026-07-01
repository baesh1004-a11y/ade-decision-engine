from learning_v2.engine import AdaptiveLearningEngineV2
from learning_v2.evaluator import RuleEvaluator
from learning_v2.models import RuleSample
from learning_v2.optimizer import RuleWeightOptimizer
from learning_v2.persistence import LearningV2Repository


def _samples():
    return [
        RuleSample("probability", True, 0.08),
        RuleSample("probability", True, 0.04),
        RuleSample("probability", True, -0.02),
        RuleSample("pattern", True, 0.05),
        RuleSample("pattern", True, 0.03),
        RuleSample("pattern", True, -0.01),
        RuleSample("volume", True, -0.04),
        RuleSample("volume", True, -0.02),
        RuleSample("volume", True, 0.01),
    ]


def test_rule_evaluator_generates_statistics():
    stats = RuleEvaluator().evaluate(_samples())

    assert len(stats) == 3
    assert stats[0].performance_score >= stats[-1].performance_score
    assert {s.rule_name for s in stats} == {"probability", "pattern", "volume"}


def test_rule_weight_optimizer_updates_weights():
    stats = RuleEvaluator().evaluate(_samples())
    weights = RuleWeightOptimizer().optimize(stats, current_weights={"probability": 1.0, "pattern": 1.0, "volume": 1.0})

    assert len(weights) == 3
    assert all(0.5 <= w.weight <= 1.5 for w in weights)
    assert any(w.weight != w.previous_weight for w in weights)


def test_adaptive_learning_engine_returns_update_and_weight_map():
    engine = AdaptiveLearningEngineV2()
    update = engine.update(_samples())
    weight_map = engine.weight_map(update)

    assert update.engine_version == "adaptive-learning-v2.0.0"
    assert update.sample_count == len(_samples())
    assert "probability" in weight_map


def test_learning_v2_repository_saves_and_fetches_weights():
    engine = AdaptiveLearningEngineV2()
    update = engine.update(_samples()).to_dict()
    repo = LearningV2Repository()

    update_id = repo.save_update(update)
    weights = repo.fetch_latest_weights()

    assert update_id > 0
    assert "probability" in weights
    assert len(weights) == 3
    repo.close()
