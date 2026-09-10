"""Record the existing decision pipeline without changing its scoring rules."""

from __future__ import annotations

import math
from copy import deepcopy

import pandas as pd

from core.context import DecisionContext
from core.pipeline import ADEPipeline
from core.run_models import RunRequest, RunResult, content_hash
from core.run_state_store import RunStateError, RunStateStore


class RecordedPipeline:
    def __init__(
        self, store: RunStateStore, pipeline: ADEPipeline | None = None
    ) -> None:
        self.store = store
        self.pipeline = pipeline or ADEPipeline()

    def run(
        self, context: DecisionContext, *, idempotency_key: str | None = None
    ) -> RunResult:
        bars = context.market_data.astype(object).where(
            pd.notna(context.market_data), None
        )
        inputs = context.to_dict()
        inputs.pop("decisions")
        inputs.pop("errors")
        inputs["learning_samples"] = context.learning_samples
        request = RunRequest(
            kind="decision",
            market=context.market,
            ticker=context.ticker,
            parameters={
                "pipeline": "ADEPipeline",
                "market_regime": context.market_regime,
            },
            input_hash=content_hash(
                {
                    "context": inputs,
                    "bars": bars.to_dict("records"),
                    "index": list(bars.index),
                }
            ),
            idempotency_key=idempotency_key,
        )
        run_id = self.store.create(request, ("INPUT", "DECISION", "RESULT"))
        existing = self.store.get(run_id)
        if existing.status in {"SUCCEEDED", "PARTIAL_SUCCESS"}:
            return existing
        if existing.status != "CREATED":
            raise RunStateError(
                "This request is already running or failed; use a new idempotency key to retry"
            )
        self.store.start(run_id)
        try:
            self.store.start_stage(run_id, "INPUT")
            if (
                not math.isfinite(context.account_balance)
                or context.account_balance <= 0
            ):
                raise ValueError("account_balance must be finite and positive")
            if not math.isfinite(context.cash) or context.cash < 0:
                raise ValueError("cash must be finite and nonnegative")
            if bars.empty or not {"Open", "High", "Low", "Close", "Volume"}.issubset(
                bars.columns
            ):
                raise ValueError("Nonempty OHLCV data is required")
            self.store.complete_stage(
                run_id,
                "INPUT",
                {
                    "input": {
                        "rows": len(bars),
                        "ticker": context.ticker,
                        "input_hash": request.input_hash,
                    }
                },
            )
            self.store.start_stage(run_id, "DECISION")
            result = self.pipeline.run(deepcopy(context))
            self.store.complete_stage(
                run_id, "DECISION", {"decisions": result.decisions}
            )
            self.store.start_stage(run_id, "RESULT")
            self.store.complete_stage(run_id, "RESULT", {"output": result.to_dict()})
            status = "PARTIAL_SUCCESS" if result.errors else "SUCCEEDED"
            return self.store.finish(run_id, status, "; ".join(result.errors) or None)
        except Exception as exc:
            self.store.finish(run_id, "FAILED", f"{type(exc).__name__}: {exc}")
            raise
