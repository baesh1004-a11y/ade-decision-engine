# Changelog

## ADE v1.0.1

### Fixed

- Distinguished live KIS quotes from fallback chart prices and exposed price freshness.
- Added bounded market-data caches and an explicit refresh action for the trading dashboard.
- Kept current and prior-run pending orders visible, cancellable, and separately labeled.
- Added a configurable approval expiry window for stale Korean and US order requests.
- Recorded ambiguous broker transport failures as `VERIFY_REQUIRED` instead of a definite failure.
- Prevented duplicate execution events and duplicate risk-triggered sell requests.
- Revalidated Korean buying power and Korean/US sellable quantities before broker submission.
- Queried pending approvals independently from the limited general order history.
- Distinguished unavailable Command Center database metrics from real zero values.
- Restored UTF-8 Korean dashboard copy and added regression coverage for data-accuracy fixes.

### Safety

- Backup branch: `backup/dashboard-before-11-20-20260721`.
- Default order approval lifetime: 30 minutes via `ADE_ORDER_REQUEST_TTL_MINUTES`.
- Orders with an uncertain broker response require execution-status verification before any retry.

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
- Configuration & Policy Engine v1 specification.
- Data Snapshot & Lineage Engine v1 specification.
- Audit & Compliance Engine v1 specification.
- Scheduler & Trigger Engine v1 specification.
- Portfolio Accounting & Performance Engine v1 specification.
- Market Regime & Feature Engine v1 specification.
- Signal Generation & Ranking Engine v1 specification.
- Portfolio Risk & Exposure Engine v1 specification.

### Updated

- Separated design, implementation, test, and execution status in `ROADMAP.md`.
- Documented the current Candidate Decision Engine as the existing Signal role.
- Added the migration plan from `strategy/candidate.py` to Signal Engine v1.0.
- Clarified that existing implementation must be smoke-tested before structural refactoring.
- Marked Backtest Engine design as complete while keeping implementation status as not started.
- Marked Report Engine design as complete while keeping implementation status as not started.
- Added run ID, stage state, failure isolation, idempotency, and audit-log design for integrated execution.
- Defined SQLite schemas for `ade_runs`, `ade_run_stages`, and `ade_run_artifacts`.
- Added explicit run/stage state-transition guards and transactional artifact persistence.
- Added portfolio-level risk limits for symbol, sector, correlation cluster, cash, total exposure, liquidity, volatility, daily loss, and drawdown.
- Added projected-portfolio validation, regime-based risk multipliers, standard reason codes, immutable Risk Snapshots, and property-based test requirements.

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
- Portfolio Risk hard blocks cannot be overridden by the Decision Engine.
- Approved orders must remain within all projected portfolio limits after execution simulation.

### Next

- Design Decision & Position Sizing Engine v1.
- Implement `db/migrations/001_create_run_state.sql`.
- Implement `RunRequest`, `RunResult`, `StageResult`, and the repository interface.
- Implement SQLite run/stage state transitions and transactional artifact storage.
- Wrap the existing analysis pipeline with an Orchestrator adapter.
- Run a fixed-fixture DataHub → Feature → Signal → Risk → Decision smoke test.
- Generate minimal Report Engine JSON fixture output.
