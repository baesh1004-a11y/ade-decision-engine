"""Small offline fixtures for saved recommendation and UI integration tests."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pandas as pd
import pytest

from recommendation.daily_service import DailyRecommendationService
from recommendation.event_recommender import EventRecommendation, ReplayMatch


@pytest.fixture
def recommendation_factory():
    def make(ticker="005930", market="kr", score=93.25):
        match = ReplayMatch(
            "event-1",
            "2011-12-19",
            market,
            "006840",
            "과거 사례",
            score,
            89.125,
            score,
            35.2,
            None,
            25,
            26,
            26,
            4,
        )
        return EventRecommendation(
            market,
            ticker,
            "삼성전자" if ticker == "005930" else "두 번째 종목",
            "2026-06-19",
            0,
            match.event_id,
            match.event_date,
            score,
            89.125,
            score,
            35.2,
            None,
            "RECOMMEND",
            ["120거래일 비교", "주봉 유사도 순위"],
            [match],
        )

    return make


@pytest.fixture
def desk_database(tmp_path, monkeypatch, recommendation_factory):
    from dashboard import order_candidate_store as candidates
    from maintenance import recommendation_runner
    from markets import profiles

    paths = {
        market: tmp_path / ("market.db" if market == "kr" else "us_market.db")
        for market in ("kr", "us")
    }
    for market, path in paths.items():
        service = DailyRecommendationService(path, market=market)
        service.close()
        monkeypatch.setitem(
            profiles.PROFILES, market, replace(profiles.PROFILES[market], db_path=path)
        )
    state = tmp_path / "ui.sqlite3"
    monkeypatch.setenv("ADE_UI_STATE_DB", str(state))
    monkeypatch.setenv("ADE_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setattr(candidates, "_DB_PATH", state)
    monkeypatch.setattr(candidates, "_LEGACY_JSON_PATH", tmp_path / "absent.json")
    monkeypatch.setattr(candidates, "_SCHEMA_READY", False)
    monkeypatch.setattr(candidates, "_HEALTH_CACHE", None)
    monkeypatch.setattr(
        recommendation_runner,
        "get_status",
        lambda market: {"state": "IDLE", "running": False},
    )
    for name in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "KIS_ACCOUNT"):
        monkeypatch.setenv(name, "")

    def add(
        run_id,
        *,
        market="kr",
        tickers=("005930", "000660"),
        finished="2026-06-19T16:10:00",
    ):
        service = DailyRecommendationService(paths[market], market=market)
        try:
            service.conn.execute(
                "INSERT INTO recommendation_runs(run_id,run_type,trading_date,started_at,finished_at,status,"
                "recommendation_count,parameters_json,market) VALUES(?,'MANUAL',?,?,?,'COMPLETED',?,?,?)",
                (
                    run_id,
                    finished[:10],
                    finished,
                    finished,
                    len(tickers),
                    json.dumps({"min_weekly_similarity": 85, "min_sto_similarity": 85}),
                    market,
                ),
            )
            for rank, ticker in enumerate(tickers, 1):
                item = recommendation_factory(ticker, market, 94.5 - rank)
                service.conn.execute(
                    "INSERT INTO daily_recommendations(run_id,rank_no,market,ticker,name,decision,final_similarity,"
                    "weekly_similarity,sto_similarity,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        rank,
                        market,
                        ticker,
                        item.name,
                        item.decision,
                        item.final_similarity,
                        item.weekly_similarity,
                        item.sto_similarity,
                        json.dumps(item.to_dict(), ensure_ascii=False),
                    ),
                )
            service.conn.commit()
        finally:
            service.close()

    def add_evidence():
        service = DailyRecommendationService(paths["kr"])
        try:
            service.conn.executescript("""
                CREATE TABLE price_bars(market TEXT,ticker TEXT,source TEXT,trade_date TEXT,
                                        open REAL,high REAL,low REAL,close REAL,volume REAL);
                CREATE TABLE surge_patterns(pattern_id TEXT,source_event_id TEXT,market TEXT,ticker TEXT,
                                            surge_start_date TEXT);
                CREATE TABLE surge_pattern_bars(pattern_id TEXT,day_index INTEGER,trade_date TEXT,
                                               open REAL,high REAL,low REAL,close REAL,volume REAL);
                INSERT INTO surge_patterns VALUES('pattern-1','event-1','kr','006840','2011-12-19');
            """)
            dates = pd.bdate_range(end="2026-06-19", periods=120)
            historical = pd.bdate_range(end="2011-12-16", periods=120)
            for index, (now, past) in enumerate(zip(dates, historical)):
                close = 100 + index * 0.1
                for ticker in ("005930", "000660"):
                    for source, factor in (("fdr", 1), ("alternate", 100)):
                        service.conn.execute(
                            "INSERT INTO price_bars VALUES(?,?,?,?,?,?,?,?,?)",
                            (
                                "kr",
                                ticker,
                                source,
                                str(now.date()),
                                close * factor,
                                (close + 1) * factor,
                                (close - 1) * factor,
                                close * factor,
                                1000 + index,
                            ),
                        )
                service.conn.execute(
                    "INSERT INTO surge_pattern_bars VALUES(?,?,?,?,?,?,?,?)",
                    (
                        "pattern-1",
                        index,
                        str(past.date()),
                        close,
                        close + 1,
                        close - 1,
                        close,
                        1000,
                    ),
                )
            service.conn.execute(
                "INSERT INTO price_bars VALUES('kr','005930','fdr','2026-06-22',9999,10000,9998,9999,99999)"
            )
            service.conn.commit()
        finally:
            service.close()

    return SimpleNamespace(paths=paths, state=state, add=add, add_evidence=add_evidence)
