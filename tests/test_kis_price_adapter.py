from __future__ import annotations

from datahub.kis import KISPriceDownloader


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.status_code = 200
        self.text = str(payload)

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self) -> None:
        self.posts: list[dict] = []
        self.gets: list[dict] = []

    def post(self, url: str, json: dict | None = None, headers: dict | None = None, timeout: int | None = None):
        self.posts.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return FakeResponse({"access_token": "dummy-token", "expires_in": 3600})

    def get(self, url: str, headers: dict | None = None, params: dict | None = None, timeout: int | None = None):
        self.gets.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        return FakeResponse(
            {
                "rt_cd": "0",
                "output2": [
                    {
                        "stck_bsop_date": "20260701",
                        "stck_oprc": "70000",
                        "stck_hgpr": "71000",
                        "stck_lwpr": "69000",
                        "stck_clpr": "70500",
                        "acml_vol": "1234567",
                    }
                ],
            }
        )


def test_kis_price_downloader_normalizes_daily_bars() -> None:
    session = FakeSession()
    downloader = KISPriceDownloader("dummy-app-key", "dummy-app-secret", session=session)

    records = downloader.download_daily_bars("005930", start="20260701", end="20260701")

    assert len(records) == 1
    assert records[0].market == "kr"
    assert records[0].ticker == "005930"
    assert records[0].trade_date == "2026-07-01"
    assert records[0].open == 70000.0
    assert records[0].high == 71000.0
    assert records[0].low == 69000.0
    assert records[0].close == 70500.0
    assert records[0].volume == 1234567.0
    assert records[0].source == "kis"
    assert session.posts[0]["url"].endswith("/oauth2/tokenP")
    assert "authorization" in session.gets[0]["headers"]
