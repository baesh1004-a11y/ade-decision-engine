import sqlite3
from pathlib import Path

import pytest
import requests
from streamlit.testing.v1 import AppTest

from dashboard.desk_charts import compare_prices, compare_sto
from dashboard.desk_data import DeskData, decode
from dashboard.desk_review import load_review
from dashboard.order_candidate_store import list_candidates
from recommendation.run_context import latest_run


APP = Path(__file__).resolve().parents[1] / "dashboard_app.py"


@pytest.fixture
def offline(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail(
            "Saved evidence and candidate handoff must not call an external API"
        )

    monkeypatch.setattr(requests.sessions.Session, "request", fail)


def button(app, label):
    # AppTest 1.54 models segmented_control as a multi-select ButtonGroup.
    # Supply its documented list value so it emits the actual frontend indices.
    for group in app.get("button_group"):
        if isinstance(group.value, str):
            group.set_value([group.value])
    return next(item for item in app.button if item.label == label)


def test_latest_empty_run_is_market_specific_and_does_not_reuse_old_candidates(
    desk_database,
):
    db = desk_database
    db.add("old")
    db.add("new-empty", tickers=(), finished="2026-06-20T16:10:00")
    data = DeskData(db.paths["kr"], "kr")
    assert data.runs()[0]["run_id"] == "new-empty"
    assert data.context("new-empty").recommendations == []
    assert DeskData(db.paths["kr"], "us").runs() == []
    with data.connect() as conn:
        assert latest_run(conn, "kr")["run_id"] == "new-empty"
        assert latest_run(conn, "us") is None


def test_absent_market_database_is_not_created_and_missing_table_is_readable(tmp_path):
    path = tmp_path / "absent.db"
    data = DeskData(path, "kr")
    assert data.runs() == []
    assert data.health()["prices"] is None
    assert not path.exists()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE recommendation_runs(run_id TEXT,started_at TEXT,status TEXT)"
    )
    conn.execute(
        "INSERT INTO recommendation_runs VALUES('legacy','2026-01-01','FAILED')"
    )
    assert latest_run(conn)["actual_recommendation_count"] == 0
    conn.close()


def test_evidence_excludes_future_bars_and_never_mixes_price_sources(desk_database):
    db = desk_database
    db.add("saved")
    db.add_evidence()
    data = DeskData(db.paths["kr"], "kr")
    selected = data.context("saved").recommendations[0]
    match = decode(selected["payload_json"])["replay_matches"][0]
    evidence = data.evidence(selected, match, "2026-09-08")
    assert evidence.source == "fdr"
    assert len(evidence.current) == len(evidence.historical) == 120
    assert evidence.current.iloc[-1]["Date"] == "2026-06-19"
    assert evidence.current["Close"].max() < 120
    assert evidence.pattern["pattern_id"] == "pattern-1"
    assert not evidence.warnings
    price = compare_prices(evidence.current, evidence.historical)
    assert list(price.data[0].x) == list(range(-119, 1))
    assert price.data[0].y[0] == price.data[2].y[0] == 100
    sto = compare_sto(evidence.current, evidence.historical)
    assert len(sto.data) == 6
    assert all(len(trace.x) == 6 for trace in sto.data)
    with sqlite3.connect(db.paths["kr"]) as conn:
        conn.execute(
            "INSERT INTO surge_patterns VALUES('other-version','event-1','kr','006840','2011-12-19')"
        )
    ambiguous = data.evidence(selected, match, "2026-09-08")
    assert ambiguous.historical.empty
    assert any("여러 개" in warning for warning in ambiguous.warnings)


def test_app_empty_state_and_market_navigation(desk_database, offline):
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not app.exception
    assert button(app, "추천 새로 계산").disabled
    assert any("첫 추천 결과" in item.value for item in app.markdown)
    app.selectbox(key="desk_market").select("us").run()
    assert not app.exception
    assert app.session_state["ade_market"] == "us"
    app.radio(key="desk_navigation").set_value("실행기록").run()
    assert not app.exception
    assert any("단계별 기록" in item.value for item in app.info)


def test_app_pins_selected_run_and_explicitly_opens_new_empty_result(
    desk_database, offline
):
    db = desk_database
    db.add("original")
    db.add_evidence()
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not app.exception
    assert app.session_state["desk_selected_run_kr"] == "original"
    assert app.get("plotly_chart")
    app.radio(key="desk_mode_kr_original_005930").set_value("STO 3계층").run()
    assert not app.exception
    db.add("empty", tickers=(), finished="2026-06-20T16:10:00")
    app.run()
    assert app.session_state["desk_selected_run_kr"] == "original"
    button(app, "최신 결과 보기").click().run()
    assert not app.exception
    assert app.session_state["desk_selected_run_kr"] == "empty"
    assert any("0개" in item.value for item in app.info)
    assert not app.get("plotly_chart")
    assert not app.text_area


def test_review_and_candidate_handoff_keep_source_and_return_without_order_submission(
    desk_database, offline, monkeypatch
):
    from dashboard import ade_ui_v1_app as legacy

    db = desk_database
    db.add("review-run")
    db.add_evidence()
    monkeypatch.setattr(
        legacy, "_cached_kis_snapshot", lambda: (None, [], "연결 미설정")
    )
    monkeypatch.setattr(legacy, "load_kis_quote", lambda ticker: (None, None))
    monkeypatch.setattr(legacy, "load_orderable", lambda *args: (None, None))
    monkeypatch.setattr(
        legacy,
        "submit_paper_order",
        lambda **kw: pytest.fail("Candidate handoff submitted an order"),
    )
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    prefix = "desk_review_kr_review-run_005930"
    app.text_area(key=prefix + "note").input("거래량 지속 여부를 확인한다")
    app.checkbox(key=prefix + "price").check()
    button(app, "검토 내용 저장").click().run()
    assert not app.exception
    owner = app.session_state["ade_owner_id"]
    assert (
        load_review(owner, "kr", "review-run", "005930")["note"]
        == "거래량 지속 여부를 확인한다"
    )
    assert load_review("different-owner", "kr", "review-run", "005930") == {}
    button(app, "주문 후보로 보내기").click().run()
    assert not app.exception
    assert app.session_state["ade_primary_page"] == "주문"
    candidate = list_candidates(owner, "kr")[0]
    assert candidate["source_run_id"] == "review-run"
    assert candidate["source_rank"] == 1
    assert any("거래량 지속 여부" in item.value for item in app.markdown)
    button(app, "추천 근거로 돌아가기").click().run()
    assert not app.exception
    assert app.session_state["desk_selected_run_kr"] == "review-run"
    assert app.text_area(key=prefix + "note").value == "거래량 지속 여부를 확인한다"


def test_us_candidate_uses_usd_request_flow_and_saved_recommendation(
    desk_database, offline
):
    db = desk_database
    db.add("us-origin", market="us", tickers=("AAPL",))
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.selectbox(key="desk_market").select("us").run()
    assert not app.exception
    button(app, "주문 후보로 보내기").click().run()
    assert not app.exception
    assert not app.error
    assert app.session_state["ade_market"] == "us"
    assert app.number_input(key="us_price_AAPL").label == "지정가(USD)"
    assert button(app, "주문 요청 생성")
    with sqlite3.connect(db.paths["us"]) as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM us_trade_order_requests").fetchone()[0]
            == 0
        )
    button(app, "추천 근거로 돌아가기").click().run()
    assert not app.exception
    assert app.session_state["desk_selected_run_us"] == "us-origin"


def test_review_draft_survives_ticker_market_and_focus_changes(desk_database, offline):
    db = desk_database
    db.add("draft-run")
    db.add_evidence()
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    prefix = "desk_review_kr_draft-run_005930"
    app.text_area(key=prefix + "note").input("저장 전에도 유지할 반대 근거").run()
    app.checkbox(key=prefix + "sto").check().run()
    button(app, "02   두 번째 종목").click().run()
    button(app, "01   삼성전자").click().run()
    assert app.text_area(key=prefix + "note").value == "저장 전에도 유지할 반대 근거"
    app.toggle(key="desk_focus_kr").set_value(True).run()
    assert app.get("plotly_chart")
    assert app.checkbox(key=prefix + "sto").value
    app.selectbox(key="desk_market").select("us").run()
    app.selectbox(key="desk_market").select("kr").run()
    assert not app.exception
    assert app.text_area(key=prefix + "note").value == "저장 전에도 유지할 반대 근거"
    owner = app.session_state["ade_owner_id"]
    assert load_review(owner, "kr", "draft-run", "005930") == {}


def test_save_and_next_advances_queue_without_changing_rank_or_leaking_owners(
    desk_database, offline
):
    from dashboard.desk_review import save_review

    db = desk_database
    db.add("queue-run")
    db.add_evidence()
    save_review("someone-else", "kr", "queue-run", "000660", {}, {"verdict": "관찰"})
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    prefix = "desk_review_kr_queue-run_005930"
    app.radio(key=prefix + "verdict").set_value("관찰").run()
    button(app, "저장하고 다음 미검토").click().run()
    assert not app.exception
    assert app.session_state["desk_ticker_kr_queue-run"] == "000660"
    app.selectbox(key="desk_queue_kr").select("미검토").run()
    assert button(app, "02   두 번째 종목")
    assert all(item.label != "01   삼성전자" for item in app.button)
    app.selectbox(key="desk_queue_kr").select("관찰").run()
    assert button(app, "01   삼성전자")
    assert all(item.label != "02   두 번째 종목" for item in app.button)
    button(app, "저장하고 다음 미검토").click().run()
    assert app.session_state["desk_ticker_kr_queue-run"] == "000660"
    button(app, "저장하고 다음 미검토").click().run()
    assert not app.exception
    assert any("모든 추천 종목" in item.value for item in app.success)
