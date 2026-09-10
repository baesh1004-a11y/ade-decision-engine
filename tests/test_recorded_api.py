import sqlite3

from fastapi.testclient import TestClient

from api.main import app


def test_api_returns_stable_recorded_result_for_same_client_request(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ADE_DATA_DIR", str(tmp_path))
    request = {
        "market": "us",
        "ticker": "NVDA",
        "idempotency_key": "api-request-1",
        "rows": [
            {
                "Open": 100 + i,
                "High": 102 + i,
                "Low": 99 + i,
                "Close": 101 + i,
                "Volume": 1000000,
            }
            for i in range(160)
        ],
    }
    with TestClient(app) as client:
        first = client.post("/decision", json=request)
        second = client.post("/decision", json=request)
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert first.json()["run"]["status"] == "SUCCEEDED"
        assert "candidate" in first.json()["decisions"]
        changed = client.post("/decision", json={**request, "cash": 5})
        assert changed.status_code == 400
        assert "different request" in changed.json()["detail"]
        assert (
            client.post("/decision", json={**request, "market": "unknown"}).status_code
            == 422
        )
    with sqlite3.connect(tmp_path / "us_market.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM ade_runs").fetchone()[0] == 1
