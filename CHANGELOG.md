# Changelog

## ADE v1.0.4

### Visual system

- Replaced the pervasive blue gradient with a neutral gray canvas, white cards, and a single navy accent.
- Standardized the dashboard on Pretendard with Korean and system-font fallbacks.
- Defined consistent heading, body, caption, badge, and key-number sizes.
- Limited desktop content to 1480px and tightened the recommendation-to-chart layout.
- Applied an 8px spacing rhythm with consistent section, card, and mobile-bottom spacing.
- Unified card borders, 12px radii, restrained shadows, and selected/risk accents.
- Added tabular numeric emphasis and Korean-market red/blue direction labels.
- Improved order and execution tables with 40px rows, pinned identity/status columns, and numeric formats.
- Simplified trading charts with Korean-market candle colors, quieter volume/grid lines, and 520px/360px responsive heights.

### Notes

- Button size and emphasis rules were intentionally unchanged because design proposal 47 was passed.
- Backup branch: `backup/dashboard-before-41-50-20260722`.

## ADE v1.0.3

### Dashboard design

- Consolidated trading mode, KIS readiness, recommendation count, and pending approvals in the top status area.
- Improved recommendation controls as readable, keyboard-visible selection cards.
- Grouped the selected symbol summary, price source, quote metrics, chart, and refresh controls.
- Presented order entry as input, review, and approval-waiting steps with an estimated order amount.
- Added a per-order status timeline while keeping raw order and execution tables in detailed view.
- Added a mobile bottom navigation bar for recommendations, charts, analysis, orders, and approvals.
- Standardized empty and chart-error states with clear next actions.
- Added text and icons to status colors, stronger contrast, and visible keyboard focus.
- Added persisted basic and detailed dashboard modes backed by the dashboard database.

### Safety

- Approval-waiting order cards were intentionally not changed because design proposal 35 was passed.
- Backup branch: `backup/dashboard-before-31-40-20260722`.

## ADE v1.0.2

### Improved

- Migrated active dashboards from deprecated `use_container_width` calls to the current width API.
- Submitted Korean and US order inputs through forms to avoid full reruns while editing.
- Replaced eager detail tabs with a selected-view control so hidden panels do not execute.
- Cached US chart downloads and exposed actionable errors while retaining server logs.
- Displayed order and execution timestamps in Korea Standard Time while storing new events in UTC.

### Safety

- Rejected identical unresolved order requests and atomically claimed approvals before broker submission.
- Enabled SQLite WAL mode and a 30-second busy timeout for concurrent dashboard sessions.
- Persisted filled quantity and retained reservations for partially filled orders.
- Checked KIS US-dollar buying power and other unresolved US buy reservations before approval.
- Backup branch: `backup/dashboard-before-21-30-20260722`.

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
- Decision & Position Sizing Engine v1 specification.
- Order Validation & Routing Engine v2 specification.

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
- Defined final BUY/HOLD/REDUCE/SELL/REJECT/NO_ACTION priority rules and Order Intent mapping.
- Added position sizing bounded by Signal strength, confidence, market regime, and Risk-approved amount and quantity.
- Added stop-loss, trailing-stop, take-profit protection, daily one-entry selection, snapshot contract validation, and deterministic decision hashing.
- Extended the Order boundary with approval TTL, snapshot consistency, latest buying-power and sellable-quantity revalidation, quote freshness, price collars, tick normalization, route policy, and broker circuit breakers.
- Added atomic submission reservations, order fingerprints, idempotency keys, unresolved cash/quantity reservations, and concurrent duplicate protection.
- Defined `VERIFY_REQUIRED` for ambiguous broker responses and prohibited automatic resubmission until broker-side reconciliation confirms the result.

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
- Decision buy amount and quantity can never exceed Risk approval.
- Expired or cross-run Signal/Risk snapshots cannot be combined into a decision.
- Sell and reduce actions are evaluated before new entries; only one new symbol may be opened per day under the virtual portfolio policy.
- Order validation may reduce or reject execution but must never increase Decision or Risk-approved quantity, amount, or aggressiveness.
- `LIVE_BLOCKED` must result in zero live broker submission calls.
- Ambiguous transport failures are isolated as `VERIFY_REQUIRED`; they are not treated as confirmed failures and are not automatically retried.

### Next

- Implement the minimal Decision & Position Sizing models and pure sizing functions.
- Implement OrderIntent, contract/pre-trade/price validators, and the DRY_RUN path.
- Implement atomic idempotency reservation and unresolved order reservations.
- Design Execution Reconciliation & Recovery Engine v2.
- Implement `db/migrations/001_create_run_state.sql`.
- Implement `RunRequest`, `RunResult`, `StageResult`, and the repository interface.
- Implement SQLite run/stage state transitions and transactional artifact storage.
- Wrap the existing analysis pipeline with an Orchestrator adapter.
- Run a fixed-fixture DataHub → Feature → Signal → Risk → Decision → Order smoke test.
- Generate minimal Report Engine JSON fixture output.
