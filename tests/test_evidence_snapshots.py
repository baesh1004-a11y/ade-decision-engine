import json
import sqlite3

import pandas as pd
import pytest

from dashboard.desk_data import DeskData, decode
from recommendation.daily_service import DailyRecommendationService
from recommendation.evidence import (
    EvidenceIntegrityError,
    capture_run_evidence,
)


def freeze(db, run_id="frozen"):
    db.add(run_id)
    db.add_evidence()
    data = DeskData(db.paths["kr"], "kr")
    context = data.context(run_id)
    service = DailyRecommendationService(db.paths["kr"])
    try:
        with service.conn:
            manifest = capture_run_evidence(
                service.conn,
                run_id,
                "kr",
                [decode(row["payload_json"]) for row in context.recommendations],
                context.finished_at,
                {"min_weekly_similarity": 85},
            )
    finally:
        service.close()
    row = context.recommendations[0]
    match = decode(row["payload_json"])["replay_matches"][0]
    return data, row, match, manifest


def test_saved_evidence_survives_price_corrections_pattern_deletion_and_new_source(
    desk_database,
):
    data, row, match, manifest = freeze(desk_database)
    original = data.evidence(row, match, "2026-09-12")
    assert original.frozen and original.digest == manifest["tickers"]["005930"]
    assert len(original.current) == len(original.historical) == 120
    with sqlite3.connect(data.path) as conn:
        conn.execute("UPDATE price_bars SET close=999999")
        conn.execute("DELETE FROM surge_pattern_bars")
        conn.execute("DELETE FROM surge_patterns")
    later = data.evidence(row, match, "2030-01-01")
    pd.testing.assert_frame_equal(later.current, original.current)
    pd.testing.assert_frame_equal(later.historical, original.historical)
    assert later.digest == original.digest
    assert not later.warnings


@pytest.mark.parametrize("target", ["snapshot", "recommendation", "match"])
def test_tampered_or_mismatched_evidence_fails_without_live_fallback(
    desk_database, target
):
    data, row, match, _ = freeze(desk_database)
    if target == "snapshot":
        with sqlite3.connect(data.path) as conn:
            conn.execute("UPDATE recommendation_evidence SET payload_json='{}'")
    elif target == "recommendation":
        payload = decode(row["payload_json"])
        payload["weekly_similarity"] = 99
        row = {**row, "payload_json": json.dumps(payload)}
    else:
        match = {**match, "event_date": "2012-01-01"}
    with pytest.raises(EvidenceIntegrityError, match="무결성"):
        data.evidence(row, match, "2026-09-12")


def test_evidence_insert_is_append_only_and_joins_result_rollback(desk_database):
    data, row, _, _ = freeze(desk_database)
    service = DailyRecommendationService(data.path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            with service.conn:
                capture_run_evidence(
                    service.conn,
                    "frozen",
                    "kr",
                    [decode(row["payload_json"])],
                    "2026-09-12",
                    {},
                )
        with pytest.raises(RuntimeError):
            with service.conn:
                service.conn.execute(
                    "INSERT INTO recommendation_runs(run_id,run_type,trading_date,started_at,status,parameters_json,market) "
                    "VALUES('rolled-back','MANUAL','2026-09-12','2026-09-12','RUNNING','{}','kr')"
                )
                capture_run_evidence(
                    service.conn,
                    "rolled-back",
                    "kr",
                    [decode(row["payload_json"])],
                    "2026-09-12",
                    {},
                )
                raise RuntimeError("result transaction failed")
        assert (
            service.conn.execute(
                "SELECT COUNT(*) FROM recommendation_evidence WHERE run_id='rolled-back'"
            ).fetchone()[0]
            == 0
        )
    finally:
        service.close()


def test_exact_pattern_identity_resolves_ambiguous_source_event(desk_database):
    db = desk_database
    db.add("legacy")
    db.add_evidence()
    data = DeskData(db.paths["kr"], "kr")
    row = data.context("legacy").recommendations[0]
    match = {
        **decode(row["payload_json"])["replay_matches"][0],
        "pattern_id": "pattern-1",
    }
    with sqlite3.connect(data.path) as conn:
        conn.execute(
            "INSERT INTO surge_patterns VALUES('new-version','event-1','kr','006840','2011-12-19')"
        )
    evidence = data.evidence(row, match, "2026-09-12")
    assert not evidence.frozen
    assert len(evidence.historical) == 120
    assert not evidence.warnings
