# Changelog

## ADE Design v0.1

### Added

- Master roadmap for ADE project tracking.
- System Architecture specification.
- DataHub Engine specification.
- Data Quality Engine specification.
- KIS Integration Layer specification.
- Portfolio State Engine specification.
- Signal Engine specification.
- Risk Engine specification.
- Decision Engine Core specification.
- Order Engine v1 specification.
- Execution Monitor v1 specification.
- Backtest Engine v1 specification.
- Report Engine v1 specification.
- Integration Orchestrator v1 specification.
- Run State Store v1 specification.

### Updated

- Separated design, implementation, test, and execution status in `ROADMAP.md`.
- Documented the current Candidate Decision Engine as the existing Signal role.
- Added the migration plan from `strategy/candidate.py` to Signal Engine v1.0.
- Clarified that existing implementation must be smoke-tested before structural refactoring.
- Marked Backtest Engine design as complete while keeping implementation status as not started.
- Marked Report Engine design as complete while keeping implementation status as not started.
- Added run ID, stage state, failure isolation, idempotency, and audit-log design for integrated execution.
- Changed the next milestone from additional engine design to Orchestrator wrapping and fixture-based smoke testing.
- Defined SQLite schemas for `ade_runs`, `ade_run_stages`, and `ade_run_artifacts`.
- Added explicit run/stage state-transition guards, transactional artifact persistence, and stale-run recovery tests.
- Updated the implementation priority to build the Run State Store before wrapping the existing pipeline.

### Notes

- This version records architecture and reference design.
- KIS OpenAPI integration is documented as a design layer.
- Backtest results are validation evidence, not proof of future performance.
- Report Engine is an explanation and audit layer. It must not create new trading decisions or modify orders, executions, or portfolio state.
- Integration Orchestrator controls execution order and state but must not create or alter investment decisions.
- The existing `main.py` and `ADEPipeline` are preserved initially and connected through an adapter before gradual stage separation.
- Run State Store persists execution evidence but does not determine investment decisions, execution order, or retry policy.
- Completed runs are immutable terminal records; reruns create a new run ID.
- Credentials, access tokens, and account authentication data must not be stored in run artifacts.

### Next

- Implement `db/migrations/001_create_run_state.sql`.
- Implement `RunRequest`, `RunResult`, `StageResult`, and the repository interface.
- Implement SQLite run/stage state transitions and transactional artifact storage.
- Wrap the existing analysis pipeline with an Orchestrator adapter.
- Run a fixed-fixture DataHub → Signal → Risk → Decision smoke test.
- Generate minimal Report Engine JSON fixture output.
