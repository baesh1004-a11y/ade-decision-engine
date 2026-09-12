import sqlite3

import pytest

from core.run_state_store import RunStateStore
from dashboard.desk_data import DeskData, decode
from meta_score.validation_context import ValidationContext
from recommendation import validation_service


@pytest.fixture
def review_engines(monkeypatch):
    class Advisor:
        failure = None

        def analyze(self, item):
            if Advisor.failure:
                raise Advisor.failure
            return ValidationContext("BUY", "HOLD", 80)

    class Feedback:
        failure = None

        def __init__(self, path):
            pass

        def register_meta_results(self, results):
            if Feedback.failure:
                raise Feedback.failure

        def close(self):
            pass

    monkeypatch.setattr(validation_service, "EnvironmentAdvisor", Advisor)
    monkeypatch.setattr(validation_service, "FeedbackEngine", Feedback)
    return Advisor, Feedback


def test_reviewing_second_ticker_keeps_first_and_original_rank(
    desk_database, review_engines
):
    db = desk_database
    db.add("review")
    data = DeskData(db.paths["kr"], "kr")
    before = data.context("review").recommendations
    for selected in reversed(before):
        result = validation_service.run_selected_validation(
            db.paths["kr"], "review", selected, decode(selected["payload_json"])
        )
        assert result.status == "SUCCEEDED"
        assert result.output["source_run_id"] == "review"
    after = data.context("review")
    assert set(after.validations) == {"005930", "000660"}
    assert after.validations["005930"]["rank_no"] == 1
    assert after.validations["000660"]["rank_no"] == 2
    assert after.recommendations == before


def test_feedback_failure_preserves_saved_environment_and_reports_partial(
    desk_database, review_engines
):
    db = desk_database
    db.add("review")
    review_engines[1].failure = RuntimeError("feedback unavailable")
    data = DeskData(db.paths["kr"], "kr")
    selected = data.context("review").recommendations[0]
    result = validation_service.run_selected_validation(
        db.paths["kr"], "review", selected, decode(selected["payload_json"])
    )
    assert result.status == "PARTIAL_SUCCESS"
    assert [stage.status for stage in result.stages] == [
        "SUCCEEDED",
        "SUCCEEDED",
        "FAILED",
    ]
    assert "005930" in data.context("review").validations


def test_persist_failure_rolls_back_environment_result_and_journal_artifact(
    desk_database, review_engines
):
    db = desk_database
    db.add("review")
    data = DeskData(db.paths["kr"], "kr")
    selected = data.context("review").recommendations[0]
    validation_service.run_selected_validation(
        db.paths["kr"], "review", selected, decode(selected["payload_json"])
    )
    before = data.context("review").validations
    with sqlite3.connect(db.paths["kr"]) as conn:
        conn.executescript("""
            CREATE TRIGGER fail_validation BEFORE INSERT ON final_decisions BEGIN
                SELECT RAISE(ABORT, 'validation constraint');
            END;
        """)
    with pytest.raises(sqlite3.IntegrityError):
        validation_service.run_selected_validation(
            db.paths["kr"], "review", selected, decode(selected["payload_json"])
        )
    assert data.context("review").validations == before
    store = RunStateStore(db.paths["kr"])
    try:
        last = store.get(store.recent("kr")[0]["run_id"])
        assert last.status == "FAILED"
        assert last.output == {}
        assert [stage.status for stage in last.stages] == [
            "SUCCEEDED",
            "FAILED",
            "SKIPPED",
        ]
    finally:
        store.close()
