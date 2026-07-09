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

### Updated

- Separated design, implementation, test, and execution status in `ROADMAP.md`.
- Documented the current Candidate Decision Engine as the existing Signal role.
- Added the migration plan from `strategy/candidate.py` to Signal Engine v1.0.
- Clarified that existing implementation must be smoke-tested before structural refactoring.
- Marked Backtest Engine design as complete while keeping implementation status as not started.
- Updated design progress to approximately 90%.

### Notes

- This version records architecture and reference design.
- KIS OpenAPI integration is documented as a design layer.
- Backtest Engine uses historical replay, simulated fills, portfolio simulation, metrics calculation, and reproducible configuration.
- Backtest results are validation evidence, not proof of future performance.

### Next

- Inspect `main.py`, `core/`, `strategy/`, `indicators/`, `pattern/`, and `tests/`.
- Run a basic pipeline smoke test.
- Reconcile existing Risk implementation with the new Risk Engine design.
- Design Report Engine v1.
- Prepare Backtest fixture datasets and regression tests.
