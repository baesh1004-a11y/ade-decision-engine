import json

import pytest

from recommendation import daily_service
from recommendation.daily_service import DailyRecommendationService
from recommendation.run_context import completed_runs, load_latest_context


@pytest.fixture
def fake_engine(monkeypatch, tmp_path, recommendation_factory):
    class Engine:
        items = [recommendation_factory()]
        failure = None
        closed = False
        received = None

        def __init__(self, path):
            pass

        def recommend_interactive(self, **kwargs):
            Engine.received = kwargs
            if Engine.failure:
                raise Engine.failure
            return Engine.items, {"weekly_pass_comparisons": 7}

        def close(self):
            Engine.closed = True

    monkeypatch.setattr(daily_service, "InteractiveSurgePatternRecommender", Engine)
    monkeypatch.setattr(
        daily_service, "runtime_path", lambda *parts: tmp_path.joinpath(*parts)
    )
    return Engine


@pytest.mark.parametrize("empty", [False, True])
def test_recommendation_and_journal_finish_together_without_score_changes(
    tmp_path, fake_engine, empty
):
    if empty:
        fake_engine.items = []
    service = DailyRecommendationService(tmp_path / "market.db")
    try:
        result = service.run("MANUAL", min_sto_similarity=86.25)
        recorded = service.run_store.get(result.run_id)
        assert result.status == "COMPLETED"
        assert recorded.status == "SUCCEEDED"
        assert [stage.status for stage in recorded.stages] == ["SUCCEEDED"] * 3
        assert recorded.output["recommendations"] == [
            item.to_dict() for item in fake_engine.items
        ]
        rows = service.conn.execute(
            "SELECT * FROM daily_recommendations WHERE run_id=?", (result.run_id,)
        ).fetchall()
        assert len(rows) == len(fake_engine.items)
        for row, original in zip(rows, fake_engine.items):
            assert row["weekly_similarity"] == original.weekly_similarity
            assert row["sto_similarity"] == original.sto_similarity
            assert row["final_similarity"] == original.final_similarity
            assert json.loads(row["payload_json"]) == original.to_dict()
        assert fake_engine.received["min_sto_similarity"] == 86.25
        assert fake_engine.closed
        context = load_latest_context(service.conn, "kr")
        assert context.run_id == result.run_id
        assert context.recommendation_count == len(fake_engine.items)
        assert completed_runs(service.conn, "us") == []
    finally:
        service.close()


@pytest.mark.parametrize("cancel", [False, True])
def test_cancel_and_engine_failure_are_visible_in_both_run_stores(
    tmp_path, fake_engine, cancel
):
    fake_engine.failure = (
        daily_service.RecommendationCancelled("stop")
        if cancel
        else RuntimeError("engine failed")
    )
    service = DailyRecommendationService(tmp_path / "market.db")
    try:
        if cancel:
            assert service.run("MANUAL").status == "CANCELLED"
        else:
            with pytest.raises(RuntimeError, match="engine failed"):
                service.run("MANUAL")
        legacy = service.conn.execute("SELECT * FROM recommendation_runs").fetchone()
        recorded = service.run_store.get(legacy["run_id"])
        assert (
            recorded.status == legacy["status"] == ("CANCELLED" if cancel else "FAILED")
        )
        assert [stage.status for stage in recorded.stages] == [
            "FAILED",
            "SKIPPED",
            "SKIPPED",
        ]
        assert fake_engine.closed
    finally:
        service.close()


@pytest.mark.parametrize("table", ["daily_recommendations", "recommendation_evidence"])
def test_persist_failure_leaves_no_partial_recommendations_or_report(
    tmp_path, fake_engine, table
):
    service = DailyRecommendationService(tmp_path / "market.db")
    try:
        service.conn.executescript(f"""
            CREATE TRIGGER reject_result BEFORE INSERT ON {table} BEGIN
                SELECT RAISE(ABORT, 'test disk constraint');
            END;
        """)
        with pytest.raises(RuntimeError, match="test disk constraint"):
            service.run("MANUAL")
        legacy = service.conn.execute("SELECT * FROM recommendation_runs").fetchone()
        recorded = service.run_store.get(legacy["run_id"])
        assert legacy["status"] == recorded.status == "FAILED"
        assert recorded.output == {}
        assert (
            service.conn.execute(
                "SELECT COUNT(*) FROM daily_recommendations"
            ).fetchone()[0]
            == 0
        )
        assert not list(tmp_path.glob("daily_recommendations/*.html"))
        assert [stage.status for stage in recorded.stages] == [
            "SUCCEEDED",
            "SUCCEEDED",
            "FAILED",
        ]
    finally:
        service.close()


@pytest.mark.parametrize("missing", ["row", "table"])
def test_new_run_reads_frozen_evidence_and_detects_missing_snapshot(
    desk_database, fake_engine, missing
):
    from dashboard.desk_data import DeskData, decode
    from recommendation.evidence import EvidenceIntegrityError

    db = desk_database
    db.add_evidence()
    service = DailyRecommendationService(db.paths["kr"])
    try:
        result = service.run("MANUAL")
        data = DeskData(db.paths["kr"], "kr")
        row = data.context(result.run_id).recommendations[0]
        match = decode(row["payload_json"])["replay_matches"][0]
        evidence = data.evidence(row, match, result.finished_at)
        assert evidence.frozen
        assert len(evidence.current) == len(evidence.historical) == 120
        with service.conn:
            service.conn.execute(
                "DELETE FROM recommendation_evidence"
                if missing == "row"
                else "DROP TABLE recommendation_evidence"
            )
        with pytest.raises(EvidenceIntegrityError, match="누락"):
            data.evidence(row, match, result.finished_at)
    finally:
        service.close()
