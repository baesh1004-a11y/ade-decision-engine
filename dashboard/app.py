from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from datahub.repository import PriceRepository
from features.engine import FeatureEngine
from portfolio.engine import PortfolioEngine
from recommendation.engine import RecommendationEngine
from recommendation.models import RecommendationInput
from universe.manager import DynamicUniverseManager


DB_PATH = Path("datahub/market.db")
app = FastAPI(title="ADE Dashboard", version="1.0.0")


def load_report():
    repository = PriceRepository(DB_PATH)
    try:
        feature_engine = FeatureEngine()
        universe = []
        for symbol in DynamicUniverseManager().active():
            data = repository.fetch_dataframe(symbol.market, symbol.ticker, source="fdr")
            if len(data) < 30:
                continue
            universe.append(
                RecommendationInput(
                    market=symbol.market,
                    ticker=symbol.ticker,
                    name=symbol.name,
                    market_data=feature_engine.transform(data),
                    sector=symbol.sector,
                )
            )
        return RecommendationEngine().rank(universe, top_n=5)
    finally:
        repository.close()


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    report = load_report()
    portfolio = PortfolioEngine().allocate(report.recommendations)
    rows = "".join(
        f"<tr><td>{index}</td><td>{item.market.upper()}</td><td>{item.ticker}</td>"
        f"<td>{item.name or ''}</td><td>{item.final_score}</td><td>{item.grade}</td>"
        f"<td>{item.action}</td><td>{item.confidence:.2f}</td></tr>"
        for index, item in enumerate(report.recommendations, start=1)
    )
    portfolio_rows = "".join(
        f"<li>{item.market.upper()}:{item.ticker} - {item.weight:.1%}</li>" for item in portfolio
    ) or "<li>No eligible positions</li>"
    return f"""
    <html><head><title>ADE Dashboard</title>
    <style>
    body{{font-family:Arial;margin:40px;background:#f6f8fb;color:#172033}}
    .card{{background:white;padding:24px;border-radius:14px;box-shadow:0 4px 18px #0001;margin-bottom:24px}}
    table{{width:100%;border-collapse:collapse}} th,td{{padding:10px;border-bottom:1px solid #e8edf3;text-align:left}}
    </style></head><body>
    <h1>ADE Decision Engine</h1>
    <div class='card'><h2>Daily Picks</h2><table>
    <tr><th>#</th><th>Market</th><th>Ticker</th><th>Name</th><th>Score</th><th>Grade</th><th>Action</th><th>Confidence</th></tr>
    {rows}</table></div>
    <div class='card'><h2>Portfolio</h2><ul>{portfolio_rows}</ul></div>
    </body></html>
    """


@app.get("/api/recommendations")
def recommendations() -> dict:
    report = load_report()
    return {
        "total_universe": report.total_universe,
        "selected_count": report.selected_count,
        "recommendations": [item.to_dict() for item in report.recommendations],
    }
