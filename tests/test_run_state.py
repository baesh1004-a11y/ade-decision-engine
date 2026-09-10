from copy import deepcopy
from dataclasses import replace

import pandas as pd
import pytest

from core.context import DecisionContext
from core.orchestrator import RecordedPipeline
from core.pipeline import ADEPipeline
from core.run_models import RunRequest, canonical_json
from core.run_state_store import RunStateError, RunStateStore


@pytest.fixture
def store(tmp_path):
    ledger = RunStateStore(tmp_path / "runs.db")
    yield ledger
    ledger.close()


def test_dependency_order_terminal_immutability_and_artifact_integrity(store):
    run_id = store.create(RunRequest("decision", "kr"), ("INPUT", "OUTPUT"))
    store.start(run_id)
    with pytest.raises(RunStateError, match="Previous stages"):
        store.start_stage(run_id, "OUTPUT")
    store.start_stage(run_id, "INPUT")
    with pytest.raises(ValueError):
        store.complete_stage(run_id, "INPUT", {"bad": float("nan")})
    assert store.get(run_id).stages[0].status == "RUNNING"
    store.complete_stage(run_id, "INPUT", {"evidence": {"score": 92.1}})
    store.start_stage(run_id, "OUTPUT")
    store.complete_stage(run_id, "OUTPUT", {"output": {"ticker": "005930"}})
    assert store.finish(run_id).output == {"ticker": "005930"}
    with pytest.raises(RunStateError):
        store.start(run_id)
    with pytest.raises(RunStateError):
        store.complete_stage(run_id, "OUTPUT", {"output": {"ticker": "different"}})
    store.conn.execute(
        "UPDATE ade_run_artifacts SET payload_json='{}' WHERE run_id=?", (run_id,)
    )
    with pytest.raises(RunStateError, match="integrity"):
        store.get(run_id)


def test_idempotency_checks_request_and_stage_plan(store):
    request = RunRequest(
        "decision", "us", {"threshold": 85}, idempotency_key="request-1"
    )
    run_id = store.create(request, ("A",))
    assert store.create(replace(request, run_id="new"), ("A",)) == run_id
    for changed, stages in [
        (replace(request, parameters={"threshold": 90}), ("A",)),
        (request, ("A", "B")),
    ]:
        with pytest.raises(RunStateError, match="different request"):
            store.create(changed, stages)
    assert len(store.recent("us")) == 1


def test_nested_stage_writes_obey_outer_rollback(store):
    run_id = store.create(RunRequest("decision", "kr"), ("A",))
    store.start(run_id)
    store.start_stage(run_id, "A")
    with pytest.raises(RuntimeError):
        with store.atomic():
            store.complete_stage(run_id, "A", {"output": {"score": 88}})
            store.finish(run_id)
            raise RuntimeError("legacy result insert failed")
    assert store.get(run_id).status == "RUNNING"
    assert store.get(run_id).stages[0].artifacts == {}
    assert store.finish(run_id, "FAILED", "rollback").stages[0].status == "FAILED"


@pytest.mark.parametrize("status", ["FAILED", "CANCELLED"])
def test_failure_closes_running_stage_and_skips_future_work(store, status):
    run_id = store.create(RunRequest("recommendation", "kr"), ("A", "B", "C"))
    store.start(run_id)
    store.start_stage(run_id, "A")
    store.complete_stage(run_id, "A", {"count": 3})
    store.start_stage(run_id, "B")
    result = store.finish(run_id, status, "interrupted")
    assert [stage.status for stage in result.stages] == [
        "SUCCEEDED",
        "FAILED",
        "SKIPPED",
    ]
    assert result.stages[0].artifacts == {"count": 3}


def context():
    close = pd.Series([100 + i * 0.5 for i in range(160)])
    return DecisionContext(
        "us",
        "NVDA",
        pd.DataFrame(
            {
                "Open": close - 0.3,
                "High": close + 1,
                "Low": close - 1,
                "Close": close,
                "Volume": 1_000_000,
            }
        ),
        account_balance=100_000_000,
        cash=50_000_000,
        market_regime="BULL",
        vix=18,
    )


def test_recorded_pipeline_preserves_real_decisions_and_does_not_mutate_input(store):
    original = context()
    expected = ADEPipeline().run(deepcopy(original)).to_dict()
    result = RecordedPipeline(store).run(original)
    assert canonical_json(result.output) == canonical_json(expected)
    assert original.decisions == {}
    assert list(original.market_data.columns) == [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]
    assert result.status == "SUCCEEDED"


def test_pipeline_retry_reuses_output_but_rejects_different_input(store):
    class CountingPipeline:
        calls = 0

        def run(self, item):
            self.calls += 1
            item.decisions["candidate"] = {"score": 88.25}
            return item

    engine = CountingPipeline()
    pipeline = RecordedPipeline(store, engine)
    original = context()
    first = pipeline.run(original, idempotency_key="client-1")
    assert pipeline.run(original, idempotency_key="client-1") == first
    assert engine.calls == 1
    original.learning_samples = [{"rule": "different"}]
    with pytest.raises(RunStateError):
        pipeline.run(original, idempotency_key="client-1")


def test_invalid_input_is_recorded_as_failed_without_running_engine(store):
    original = context()
    original.cash = -1
    with pytest.raises(ValueError, match="cash"):
        RecordedPipeline(store).run(original)
    run = store.get(store.recent("us")[0]["run_id"])
    assert run.status == "FAILED"
    assert [stage.status for stage in run.stages] == ["FAILED", "SKIPPED", "SKIPPED"]
