from __future__ import annotations

from typing import Any

import pandas as pd

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field
except Exception as exc:  # pragma: no cover
    raise RuntimeError("FastAPI API requires fastapi and pydantic to be installed") from exc

from core.context import DecisionContext
from core.pipeline import ADEPipeline
from report.engine import ReportEngine


class MarketRow(BaseModel):
    Open: float
    High: float
    Low: float
    Close: float
    Volume: float
    Date: str | None = None


class DecisionRequest(BaseModel):
    market: str = "us"
    ticker: str
    rows: list[MarketRow] = Field(min_length=80)
    account_balance: float = 100_000_000
    cash: float = 50_000_000
    market_regime: str = "SIDEWAY"
    vix: float | None = None


app = FastAPI(title="ADE Decision Engine API", version="1.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ade-decision-engine"}


@app.post("/decision")
def decision(request: DecisionRequest) -> dict[str, Any]:
    try:
        df = pd.DataFrame([row.model_dump(exclude_none=True) for row in request.rows])
        context = DecisionContext(
            market=request.market,
            ticker=request.ticker,
            market_data=df,
            account_balance=request.account_balance,
            cash=request.cash,
            market_regime=request.market_regime,
            vix=request.vix,
        )
        result = ADEPipeline().run(context).to_dict()
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/report")
def report(request: DecisionRequest) -> dict[str, Any]:
    result = decision(request)
    return ReportEngine().build_report(ticker=request.ticker, pipeline_result=result)
