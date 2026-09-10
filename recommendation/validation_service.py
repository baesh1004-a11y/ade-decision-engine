"""Optional environment reviews preserve each recommendation's rank and identity."""

from __future__ import annotations

from core.run_models import RunRequest, content_hash
from core.run_state_store import RunStateStore
from feedback.engine import FeedbackEngine
from meta_score.dashboard import _recommendation_from_payload, _save_final_decisions
from meta_score.engine import MetaScoreEngine
from meta_score.validation_context import EnvironmentAdvisor


def run_selected_validation(db_path, source_run_id, selected, payload):
    source = dict(payload)
    source["ticker"] = selected["ticker"]
    source["name"] = selected.get("display_name") or selected.get("name")
    recommendation = _recommendation_from_payload(source)
    store = RunStateStore(db_path)
    try:
        request = RunRequest(
            kind="validation",
            market=recommendation.market,
            ticker=recommendation.ticker,
            parameters={"source_run_id": source_run_id},
            input_hash=content_hash(source),
        )
        run_id = store.create(request, ("ENVIRONMENT", "VALIDATION", "FEEDBACK"))
        store.start(run_id)
        try:
            store.start_stage(run_id, "ENVIRONMENT")
            environment = EnvironmentAdvisor().analyze(recommendation)
            results = MetaScoreEngine().score(
                [recommendation],
                validation_contexts={str(recommendation.ticker): environment},
            )
            store.complete_stage(
                run_id,
                "ENVIRONMENT",
                {"analysis": [item.to_dict() for item in results]},
            )
            store.start_stage(run_id, "VALIDATION")
            with store.atomic():
                _save_final_decisions(
                    db_path,
                    source_run_id,
                    results,
                    replace_run=False,
                    connection=store.conn,
                )
                store.complete_stage(
                    run_id,
                    "VALIDATION",
                    {
                        "output": {
                            "source_run_id": source_run_id,
                            "ticker": recommendation.ticker,
                            "validations": [item.to_dict() for item in results],
                        }
                    },
                )
            store.start_stage(run_id, "FEEDBACK")
            try:
                feedback = FeedbackEngine(db_path)
                try:
                    feedback.register_meta_results(results)
                finally:
                    feedback.close()
            except Exception as exc:
                # A feedback outage must not erase an already saved environment review.
                store.fail_stage(run_id, "FEEDBACK", str(exc))
                return store.finish(run_id, "PARTIAL_SUCCESS", str(exc))
            store.complete_stage(run_id, "FEEDBACK")
            return store.finish(run_id)
        except Exception as exc:
            store.finish(run_id, "FAILED", str(exc))
            raise
    finally:
        store.close()
