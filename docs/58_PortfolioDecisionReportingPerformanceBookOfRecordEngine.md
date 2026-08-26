# 58. Portfolio & Decision Reporting, Performance Book-of-Record & Regulatory-Grade Report Engine v1

## 1. Purpose

Engine 58 is ADE's authoritative reporting and performance book-of-record layer.

It converts already-finalized accounting, benchmark, decision-ledger, risk, operational-health, execution, and attribution snapshots into immutable daily, periodic, portfolio, strategy, and decision reports.

It answers:

> What is the official ADE portfolio state and performance for a given reporting date, what decisions and executions produced it, how did it perform versus the valid point-in-time benchmark, what risks constrained the portfolio, and can the published report be reproduced exactly later?

Engine 58 does not create Alpha, invent missing prices, backfill unknown benchmark values from hindsight, modify portfolio accounting, or reinterpret a frozen decision. It is a reporting book-of-record, not a trading engine.

Core principles:

```text
Accounting is the source of portfolio truth.
Decision Ledger is the source of decision truth.
Risk Governor is the source of risk-permission truth.
Execution is the source of fill truth.
Benchmark snapshots are point-in-time and versioned.
A report may summarize truth, but must never manufacture truth.

Same finalized source snapshots + same reporting policy
→ same report payload + same totals + same report hash.
```

---

## 2. Position in ADE architecture

```text
19 Portfolio Accounting / NAV
25 Reconciliation
31 Paper Trading / Broker State
34 Transaction Cost
46 Execution Simulation / Realized Fills
49 Outcome Attribution
51 Strategy Ensemble
52 Stress & Survival
53 Capital Preservation
54 Risk Governor
55 Operational Resilience
56 Runtime Coordinator
57 Decision Ledger / Explainability Graph
Benchmark / Index Snapshot
Trading Calendar
        ↓
┌──────────────────────────────────────────────────────┐
│ 58 Reporting & Performance Book-of-Record           │
├──────────────────────────────────────────────────────┤
│ Reporting Cutoff Resolver                           │
│ Portfolio BoR Snapshot                              │
│ Holdings / Cash / Exposure                          │
│ Trade & Fill Reporting                              │
│ Decision Reporting                                  │
│ Performance / Benchmark                             │
│ Attribution Summary                                 │
│ Risk / Stress / Drawdown                            │
│ Data & Operational Quality Disclosure               │
│ Daily / Weekly / Monthly / Periodic Reports         │
│ Restatement / Supersession                          │
│ Distribution Manifest                               │
│ Integrity / Reproduction                            │
└──────────────────────────────────────────────────────┘
        ↓
Human report / API / dashboard / archive
```

Engine 57 proves why a decision happened. Engine 58 proves what the official portfolio and performance record was and packages the relevant decision evidence into a reproducible report.

---

## 3. Responsibility boundary

### 58 does

- define one authoritative report cutoff for each market/trading date;
- consume only finalized source snapshots permitted by the report cutoff;
- create immutable portfolio reporting snapshots;
- report holdings, cash, NAV, realized/unrealized P&L, costs, and exposure;
- report BUY, ADD, HOLD, REDUCE, EXIT, REJECT, and NO_ACTION decisions from Engine 57;
- preserve NO_ACTION subtype and binding reason;
- report requested orders separately from actual fills;
- report partial fills, unfilled quantities, slippage, fees, taxes, and impact;
- calculate daily and cumulative returns from the accounting book of record;
- calculate point-in-time benchmark returns from a valid benchmark inception snapshot;
- distinguish unavailable benchmark history from zero benchmark return;
- calculate active return and relative performance only when comparable observations exist;
- report risk state, binding constraints, headroom, stress state, and drawdown state;
- disclose data-quality, operational, and reconciliation caveats;
- create daily, weekly, monthly, year-to-date, since-inception, and custom-period reports;
- support report supersession without mutating the original report;
- generate deterministic JSON/report payloads and hashes;
- support audit reconstruction from report → decision → source evidence.

### 58 does not

- generate trading candidates;
- change signal scores;
- alter risk permissions;
- change execution fills;
- recalculate accounting using an alternative convention without a new accounting snapshot;
- infer a missing benchmark inception level from future data;
- treat a market-closed day as a zero-return trading observation;
- treat DATA_BLOCKED or MARKET_CLOSED as an investment-success observation;
- rewrite prior reports in place;
- create a live order;
- replace Engine 49 detailed outcome attribution.

---

## 4. Reporting Book-of-Record hierarchy

ADE separates four books.

```text
1 ACCOUNTING BOOK
  cash, positions, NAV, P&L

2 EXECUTION BOOK
  orders, fills, costs, unfilled quantity

3 DECISION BOOK
  finalized decisions and reasons

4 REPORTING BOOK
  immutable presentation of 1~3 plus benchmark/risk disclosures
```

The Reporting Book cannot override the other books.

If Engine 58 detects a disagreement such as:

```text
Accounting position = 80 shares
Execution accepted fills = 75 shares
```

it must not choose whichever value makes the report balance.

It records:

```text
REPORT_SOURCE_RECONCILIATION_FAILED
```

and blocks FINAL publication when the discrepancy exceeds policy tolerance.

---

## 5. Report types

```text
DAILY_PORTFOLIO
DAILY_DECISION
DAILY_PERFORMANCE
WEEKLY_REVIEW
MONTHLY_REVIEW
YTD_REVIEW
SINCE_INCEPTION
CUSTOM_PERIOD
TRADE_CONFIRMATION
RISK_REPORT
STRESS_REPORT
AUDIT_REPORT
RESTATEMENT_NOTICE
```

A standard ADE daily paper-trading report is a composite of:

```text
DAILY_PORTFOLIO
+ DAILY_DECISION
+ DAILY_PERFORMANCE
+ RISK_REPORT summary
```

---

## 6. Report states

```text
DRAFT
SOURCE_PENDING
VALIDATING
FINALIZED
DISTRIBUTED
SUPERSEDED
REVOKED
```

Only `FINALIZED` or `DISTRIBUTED` reports are official Book-of-Record outputs.

`DRAFT` output must never be used as the next day's portfolio input.

---

## 7. Reporting cutoff model

A report is defined by an explicit cutoff.

```python
ReportingCutoff(
    market,
    trading_date,
    report_type,
    valuation_time,
    source_cutoff_time,
    benchmark_cutoff_time,
    decision_cutoff_time,
    accounting_cutoff_time,
)
```

For an EOD Korean-market report, the policy might require:

```text
Market session finalized
Corporate actions resolved
Official close available
Benchmark close available
Accounting reconciled
Decision Freeze finalized
Operational health snapshot finalized
```

A news item or filing that becomes known after the report's source cutoff may appear only in a later report or as an explicitly labeled subsequent event.

It cannot alter the frozen report rationale.

---

## 8. Trading-day versus calendar-day semantics

Engine 58 distinguishes:

```text
TRADING_DAY
MARKET_CLOSED
UNSCHEDULED_CLOSURE
DATA_UNAVAILABLE
```

On `MARKET_CLOSED`:

```text
new daily market return observation = NONE
benchmark daily return observation = NONE
portfolio trading-day return = NONE
```

The report may carry forward the latest NAV for informational display, but must not create an artificial 0.00% trading observation.

Therefore:

```text
MARKET_CLOSED return = N/A
```

not:

```text
MARKET_CLOSED return = 0.00%
```

This prevents closed days from diluting realized volatility, hit rates, and other time-series statistics.

---

## 9. Portfolio snapshot contract

Every official report references exactly one finalized accounting snapshot.

```python
PortfolioReportSnapshot(
    report_snapshot_id,
    portfolio_id,
    trading_date,
    valuation_time,
    accounting_snapshot_id,
    reconciliation_snapshot_id,
    cash,
    market_value,
    nav,
    realized_pnl,
    unrealized_pnl,
    accrued_costs,
    gross_exposure,
    net_exposure,
    position_count,
    report_currency,
)
```

No value may be recomputed from a different price source inside the reporting layer.

---

## 10. Holdings reporting

For every held security:

```text
security_id
ticker
security_name
quantity
average_cost
valuation_price
market_value
portfolio_weight
unrealized_pnl
unrealized_return
realized_pnl_to_date
strategy_lineage
position_state
```

The report preserves valuation-price provenance:

```text
price_snapshot_id
price_type
observed_at
finalized_at
```

If a security is suspended and no valid new valuation exists, the report must use the Accounting Engine's approved valuation policy and disclose it.

---

## 11. Cash reporting

Cash is a first-class portfolio asset.

Report fields:

```text
settled_cash
unsettled_cash
reserved_cash
available_cash
accrued_fees
accrued_taxes
cash_weight
minimum_cash_required
cash_headroom
```

The daily ADE paper portfolio requirement:

```text
minimum cash >= 10%
```

is reported as a constraint result, not merely as a displayed percentage.

---

## 12. Decision reporting contract

Engine 58 consumes Engine 57 Decision Ledger entries.

For each candidate or final decision it may display:

```text
security
alpha_score
confidence_score
adjusted_signal_score
candidate_state
risk_state
buy_permission
decision_type
decision_subtype
primary_reason
binding_constraint
```

If Alpha/Confidence were not computable in the frozen decision, Engine 58 prints:

```text
N/A
```

and the actual reason, for example:

```text
PIT_FACTOR_SNAPSHOT_NOT_MATERIALIZED
```

It must never replace missing scores with narrative estimates.

---

## 13. NO_ACTION reporting

`NO_ACTION` is always reported with subtype.

```text
NO_CANDIDATE
SIGNAL_REJECTED
RISK_BLOCKED
DATA_BLOCKED
OPERATIONAL_BLOCKED
MARKET_CLOSED
NO_RISK_HEADROOM
WITHIN_REBALANCE_BAND
NO_ORDER_AFTER_NETTING
EXECUTION_NOT_PERMITTED
```

Example:

```text
Decision        NO_ACTION
Subtype         RISK_BLOCKED
Candidate       ELIGIBLE
Risk State      RISK_OFF
BUY Permission  BLOCKED
Primary Reason  STRESS_LIMIT_BINDING
```

This differs materially from:

```text
Decision        NO_ACTION
Subtype         DATA_BLOCKED
Alpha           N/A
Primary Reason  PIT_FEATURE_SNAPSHOT_MISSING
```

The reporting layer must preserve that distinction.

---

## 14. Candidate-table policy

A daily candidate table must be traceable to the frozen candidate universe.

Each row has:

```text
rank
security_id
signal_state
alpha
confidence
adjusted_signal
risk_state
risk_headroom
decision
primary_reason
```

Candidates may not be added retrospectively because they performed well after the report date.

The top-N reporting rule is versioned in the reporting policy.

---

## 15. Order versus fill reporting

Engine 58 reports three separate quantities:

```text
DECISION QUANTITY
ORDER QUANTITY
FILLED QUANTITY
```

Example:

```text
Decision      BUY 100
Order         BUY 100
Fill          BUY 65
Unfilled      35
```

Portfolio accounting must reflect only 65 shares.

The report may not present the intended 100 shares as an actual transaction.

---

## 16. Trade reporting

Per trade/fill:

```text
security
action
order_type
decision_time
order_time
fill_time
requested_quantity
filled_quantity
remaining_quantity
reference_price
fill_price
notional
fees
taxes
slippage_bps
market_impact_bps
implementation_shortfall
execution_state
```

No same-day-close fill is reported for an EOD decision when Engine 46 prohibited such execution.

---

## 17. Transaction-cost presentation

Costs are separated into:

```text
Broker / explicit fee
Tax
Spread cost
Slippage
Market impact
Other explicit charge
```

Accounting cash P&L includes only accounting-recognized cash costs.

Opportunity cost from unfilled orders is shown in execution-quality disclosure and does not contaminate cash P&L.

---

## 18. Daily return calculation

The authoritative return comes from accounting NAV.

When no external flows occur:

```text
Daily Return
= NAV_t / NAV_(t-1) - 1
```

When flows exist, the accounting engine's approved flow-adjusted methodology must be used.

Engine 58 references the method ID and does not silently switch between simple return, TWR, and money-weighted return.

---

## 19. Performance methodologies

Supported methods:

```text
SIMPLE_DAILY_CHAIN
TIME_WEIGHTED_RETURN
MONEY_WEIGHTED_RETURN
IRR
```

Default portfolio performance book:

```text
TIME_WEIGHTED_RETURN
```

if external cash flows are possible.

The report stores:

```text
performance_method
performance_policy_id
performance_policy_hash
```

---

## 20. Cumulative return

For valid trading observations:

```text
Cumulative Return
= Π(1 + r_t) - 1
```

It is not:

```text
sum(daily returns)
```

Market-closed observations are excluded rather than inserted as artificial zeros.

---

## 21. Benchmark Book-of-Record

Engine 58 introduces an authoritative benchmark inception record.

```python
BenchmarkInception(
    portfolio_id,
    benchmark_id,
    inception_trading_date,
    inception_value,
    source_snapshot_id,
    known_at,
    benchmark_policy_id,
)
```

Once established, all cumulative relative-performance reports use this record.

This removes the historical problem:

```text
ADE cumulative return = available
KOSPI cumulative return = N/A
```

provided a valid inception snapshot was created prospectively.

---

## 22. Missing historical benchmark rule

If no valid benchmark inception snapshot exists for a historical portfolio start date, Engine 58 does not fabricate it from a later data lookup in the official Book-of-Record.

It records:

```text
BENCHMARK_INCEPTION_NOT_RECORDED
```

and leaves official since-inception benchmark performance unavailable.

A separate research/reconstructed benchmark series may be created, but must be labeled:

```text
RECONSTRUCTED_NON_OFFICIAL
```

and cannot silently replace the original report.

---

## 23. Daily benchmark return

```text
Benchmark Daily Return
= benchmark_close_t / benchmark_close_(previous trading day) - 1
```

Only finalized benchmark closes are allowed.

If the benchmark close is missing:

```text
BENCHMARK_DAILY_RETURN = N/A
ACTIVE_RETURN = N/A
```

not zero.

---

## 24. Active return

When both portfolio and benchmark returns are valid:

```text
Daily Active Return
= Portfolio Daily Return - Benchmark Daily Return
```

For cumulative performance:

```text
Portfolio cumulative = Π(1+r_p)-1
Benchmark cumulative = Π(1+r_b)-1
Active cumulative = Portfolio cumulative - Benchmark cumulative
```

The report must clearly distinguish arithmetic difference from compounded relative wealth ratio.

Optional relative wealth:

```text
Relative Wealth
= (1 + Portfolio cumulative)
  / (1 + Benchmark cumulative)
```

---

## 25. Benchmark change policy

Changing KOSPI to KODEX 200 or another benchmark does not rewrite history.

A benchmark binding has validity intervals:

```text
benchmark_id
valid_from
valid_to
binding_reason
policy_version
```

Reports show each period using the benchmark active at that time, or generate a separately labeled constant-benchmark analytical report.

---

## 26. Risk reporting

Engine 58 consumes Engine 54's final Risk Envelope.

Report fields:

```text
risk_state
buy_permission
add_permission
gross_limit
current_gross
risk_utilization
risk_headroom
minimum_cash
single_name_limit
sector_limit
strategy_cluster_limit
binding_constraint
binding_source_engine
```

The daily report should explain:

```text
Signal ELIGIBLE
but
Risk Headroom = 0
→ NO_ACTION / RISK_BLOCKED
```

without blending Signal and Risk into one score.

---

## 27. Drawdown reporting

From Engine 53:

```text
high_water_mark
current_nav
drawdown_pct
drawdown_state
drawdown_velocity
capital_preservation_multiplier
recovery_state
```

Drawdown is always calculated against the official accounting HWM, not against an independently recomputed reporting HWM.

---

## 28. Stress reporting

From Engine 52:

```text
survival_state
survival_score
stress_loss
stress_drawdown
liquidation_days
correlation_diversification_loss
recommended_risk_multiplier
hard_survival_breach
```

A hard survival breach cannot be hidden by an average high score in the report summary.

---

## 29. Operational-quality disclosure

From Engine 55:

```text
operational_mode
critical_failure_count
degraded_component_count
stale_component_count
unknown_component_count
buy_permission
binding_component
binding_reason
```

Example:

```text
Portfolio data available
Signal attractive
but
Broker order API FAILED

Decision may be valid
Execution permission = BLOCKED
```

The report distinguishes decision validity from execution availability.

---

## 30. Orchestration disclosure

From Engine 56:

```text
run_id
run_type
dag_version
decision_cutoff
input_freeze_id
decision_freeze_id
run_state
late_result_count
failure_count
```

A report is not FINAL if the referenced decision run is invalid for the requested report type.

---

## 31. Decision-proof link

Every report decision line references Engine 57:

```text
decision_id
decision_manifest_hash
decision_proof_root_hash
primary_reason
```

Thus:

```text
Daily Report
→ Decision Ledger
→ Evidence Graph
→ Frozen Source Snapshots
```

is navigable and verifiable.

---

## 32. Attribution reporting

Engine 58 reports summarized Engine 49 attribution without rewriting the original decision rationale.

Examples:

```text
RISK_OFF_DOWNSIDE_AVOIDED
RECOVERY_OPPORTUNITY_COST
SIGNAL_SELECTION_CONTRIBUTION
EXECUTION_SHORTFALL
DATA_GOVERNANCE_PROTECTED
```

The report distinguishes:

```text
Original reason
vs
Subsequent outcome
```

A future outcome never becomes a causal reason in the original report.

---

## 33. Daily standard ADE report schema

The canonical daily report contains:

```text
1 Header / disclaimer
2 ADE versions and run IDs
3 Market / benchmark summary
4 Candidate Signal / Risk / Decision table
5 Orders / fills / costs
6 Holdings / cash / NAV
7 Daily P&L and cumulative performance
8 Benchmark and active performance
9 Risk / stress / drawdown
10 Primary reasons and blocked reasons
11 Data / operational-quality disclosure
12 Decision proof / report hashes
```

For paper trading, the disclaimer is mandatory:

```text
This report is a simulated investment record for ADE validation.
It is not investment advice or a recommendation to trade.
```

---

## 34. Report-source completeness gate

A report can be FINAL only when mandatory source classes are complete.

For a trading-day daily report:

```text
Accounting FINALIZED
Reconciliation valid or within approved tolerance
Trading calendar resolved
Benchmark finalized or explicitly unavailable
Decision Ledger finalized
Risk Governor finalized
Operational Health finalized
Orchestration run finalized
```

Execution is mandatory only when orders/fills existed.

If no orders existed, explicit `NO_ORDER` evidence is sufficient.

---

## 35. Mandatory versus optional fields

Mandatory fields for any trading-day daily report:

```text
portfolio_id
trading_date
nav
cash
holdings
portfolio_daily_return
decision_type or explicit no-decision state
risk_state
operational_mode
report_status
source_manifest_hash
report_hash
```

Conditionally mandatory:

```text
benchmark return  if valid benchmark close exists
fills             if orders were executed
NO_ACTION subtype if decision = NO_ACTION
restatement link  if report supersedes prior report
```

Optional analytical sections may not block the official core report.

---

## 36. Restatement model

Reports are immutable.

If a source is later corrected, Engine 58 creates a new report version.

```text
Report v1 FINALIZED
        ↓
late accounting correction
        ↓
Report v2 FINALIZED
supersedes v1
```

v1 remains stored.

Fields:

```text
report_version
supersedes_report_id
superseded_by_report_id
restatement_reason
restatement_materiality
```

---

## 37. Restatement materiality

Initial policy categories:

```text
NON_MATERIAL
MATERIAL_PERFORMANCE
MATERIAL_POSITION
MATERIAL_DECISION_DISCLOSURE
MATERIAL_RISK_DISCLOSURE
CRITICAL_INTEGRITY
```

Examples:

```text
security display-name typo
→ NON_MATERIAL

NAV changed 0.20%
→ MATERIAL_PERFORMANCE depending on policy

position quantity changed
→ MATERIAL_POSITION

Decision subtype changed
→ MATERIAL_DECISION_DISCLOSURE
```

---

## 38. Correction versus new information

A correction fixes information that was wrong at the original cutoff.

New information was not available then.

```text
CORRECTION
may cause restatement

NEW_INFORMATION_AFTER_CUTOFF
does not restate original report
```

This distinction prevents future information from rewriting historical records.

---

## 39. Report distribution modes

```text
INTERNAL
PAPER_TRADING
LIVE_SHADOW
LIVE_INTERNAL
EXTERNAL_AUDIT
```

Distribution policy controls which fields are visible but does not alter the core numbers.

Redaction is a presentation operation, never a recalculation.

---

## 40. Machine-readable report payload

Canonical JSON structure:

```json
{
  "report": {},
  "portfolio": {},
  "performance": {},
  "benchmark": {},
  "candidates": [],
  "decisions": [],
  "orders": [],
  "fills": [],
  "risk": {},
  "stress": {},
  "drawdown": {},
  "operational_health": {},
  "orchestration": {},
  "attribution": {},
  "disclosures": [],
  "source_manifest": {},
  "integrity": {}
}
```

All human reports are rendered from this canonical payload.

---

## 41. Human rendering policy

Human reports must never be the primary data record.

```text
Canonical structured payload
        ↓
renderer
        ↓
Markdown / HTML / PDF / dashboard
```

If a rendered sentence differs from structured values, the structured payload wins and rendering validation must fail.

---

## 42. Unit and precision policy

The report policy defines precision explicitly.

Example:

```text
KRW                  integer won
portfolio weight     2 decimals
return               2 decimals displayed, higher precision stored
bps                  1 decimal displayed
quantity             integer shares unless instrument supports fractions
NAV                   integer won display, exact decimal internally
```

Rounding occurs only at presentation boundaries.

Components must reconcile using full precision.

---

## 43. P&L reconciliation

The report validates:

```text
Ending NAV
=
Beginning NAV
+ Trading P&L
+ Income
- Costs
+ External Flows
+ Other approved accounting adjustments
```

within tolerance.

Failure:

```text
REPORT_PNL_RECONCILIATION_FAILED
```

blocks FINAL status.

---

## 44. Holdings reconciliation

```text
Beginning quantity
+ buys filled
- sells filled
+ corporate-action quantity adjustment
= ending quantity
```

for every security.

A mismatch blocks official holdings publication unless an approved reconciliation exception exists.

---

## 45. Performance-chain integrity

For each report date:

```text
previous finalized report
→ current finalized report
```

is linked.

Fields:

```text
previous_report_id
previous_nav
current_nav
period_return
chain_hash
```

A missing date is allowed only when explained by:

```text
MARKET_CLOSED
PORTFOLIO_NOT_INCEPTED
REPORT_REVOKED
```

Unexpected chain gaps generate an integrity error.

---

## 46. Benchmark-chain integrity

Benchmark series uses the same trading calendar.

The engine verifies:

```text
portfolio return observation dates
vs
benchmark observation dates
```

Active performance is computed only on aligned valid observations.

No calendar-day forward fill is allowed for missing benchmark closes.

---

## 47. Since-inception performance

An official since-inception report requires:

```text
portfolio inception snapshot
benchmark inception snapshot
continuous official performance chain
```

If benchmark inception is missing:

```text
portfolio since inception = valid
benchmark since inception = unavailable
active since inception = unavailable
```

and the reason is disclosed.

---

## 48. Strategy reporting

When Engine 51 has multiple strategy sleeves, Engine 58 reports:

```text
strategy_id
strategy_weight
strategy_nav
strategy_return
strategy_drawdown
strategy_health
strategy_contribution
strategy_risk_budget
```

Cross-strategy netting does not destroy strategy lineage.

The aggregate execution may be one order, but strategy-level reporting uses the preserved attribution map.

---

## 49. Portfolio-compliance reporting

Each report includes hard constraint checks:

```text
leverage <= policy
cash >= minimum
single name <= cap
sector <= cap
industry <= cap
strategy <= cap
cluster <= cap
new positions today <= limit
```

States:

```text
PASS
NEAR_LIMIT
BREACH
NOT_APPLICABLE
UNKNOWN
```

`UNKNOWN` is never rendered as PASS.

---

## 50. Data-quality disclosure

Report disclosure examples:

```text
BENCHMARK_CLOSE_MISSING
VALUATION_PRICE_STALE
CORPORATE_ACTION_PENDING
PIT_FEATURE_SNAPSHOT_MISSING
ACCOUNTING_RECONCILIATION_DEGRADED
SOURCE_CONFLICT
```

The reporting layer cannot hide them merely because the final NAV exists.

---

## 51. Official versus reconstructed reports

Two namespaces are mandatory:

```text
OFFICIAL_BOR
RECONSTRUCTED_ANALYTICAL
```

Historical reconstruction may improve analysis, but it cannot overwrite official historical publication.

An analytical reconstruction displays:

```text
NOT OFFICIAL BOOK-OF-RECORD
```

and references the reconstruction methodology.

---

## 52. Replay reporting

Given recent ADE replay work, Engine 58 explicitly separates:

```text
LIVE/PAPER actual path
REPLAY target path
```

A replay report may contain:

```text
actual_decision
replay_decision
path_divergence_date
resynchronization_date
performance_difference
```

but replay holdings and P&L must never be merged into the official live/paper Book-of-Record.

---

## 53. Replay divergence disclosure

Example:

```text
Actual path
NO_ACTION

Replay target
BUY KODEX KOSDAQ 150

Divergence begins
2026-08-XX

Resynchronizes
2026-08-YY or OPEN
```

This is analytical evidence only.

It cannot be used to claim the original portfolio actually held the replay target.

---

## 54. Regulatory-grade audit attributes

Every report stores:

```text
who/what generated it
generation time
source cutoff
source snapshot IDs
source hashes
reporting policy ID/hash
accounting method ID/hash
benchmark policy ID/hash
renderer version
report hash
previous report hash
```

The chain permits independent verification.

---

## 55. Report manifest

```python
ReportManifest(
    report_id,
    report_version,
    portfolio_id,
    trading_date,
    report_type,
    reporting_policy_id,
    reporting_policy_hash,
    source_cutoff_time,
    accounting_snapshot_id,
    benchmark_snapshot_id,
    decision_freeze_id,
    risk_snapshot_id,
    operational_snapshot_id,
    orchestration_run_id,
    source_manifest_hash,
    payload_hash,
    report_hash,
)
```

---

## 56. Hash-chain design

Official daily reports can form a chain:

```text
Report D-1 hash
      ↓
Report D hash
      ↓
Report D+1 hash
```

The current report hash includes `previous_report_hash`.

A historical mutation breaks the chain.

---

## 57. Database schema

Core tables:

```text
reporting_policies
reporting_policy_versions

report_runs
report_manifests
report_source_members

portfolio_report_snapshots
holding_report_lines
cash_report_lines

performance_report_snapshots
performance_return_observations
performance_chain_links

benchmark_bindings
benchmark_inceptions
benchmark_report_snapshots
benchmark_return_observations

candidate_report_lines
decision_report_lines
order_report_lines
fill_report_lines

risk_report_snapshots
stress_report_snapshots
drawdown_report_snapshots
operational_report_snapshots

report_disclosures
report_integrity_checks

report_distributions
report_restatements
report_supersession_links

replay_report_snapshots
replay_path_divergences
```

---

## 58. `report_runs`

```text
report_run_id
report_id
portfolio_id
trading_date
report_type
report_namespace

source_cutoff_time
started_at
completed_at

status

reporting_policy_id
reporting_policy_version
reporting_policy_hash

source_manifest_hash
payload_hash
report_hash

previous_report_id
previous_report_hash
```

---

## 59. `portfolio_report_snapshots`

```text
report_snapshot_id
report_id
accounting_snapshot_id
reconciliation_snapshot_id

valuation_time
currency

beginning_nav
ending_nav
cash
market_value

gross_exposure
net_exposure

position_count

realized_pnl
unrealized_pnl
income
costs
external_flows

snapshot_hash
```

---

## 60. `performance_return_observations`

```text
observation_id
portfolio_id
trading_date

observation_state

portfolio_return
benchmark_return
active_return

portfolio_cumulative_return
benchmark_cumulative_return
active_cumulative_return
relative_wealth

performance_method
benchmark_id

source_report_id
observation_hash
```

`observation_state`:

```text
VALID
MARKET_CLOSED
BENCHMARK_MISSING
PORTFOLIO_NOT_INCEPTED
INVALID
```

---

## 61. `decision_report_lines`

```text
line_id
report_id
decision_id
security_id

alpha_score
confidence_score
adjusted_signal_score
candidate_state

risk_state
buy_permission
risk_headroom

decision_type
decision_subtype
primary_reason_code
binding_constraint_id

decision_proof_root_hash
line_hash
```

---

## 62. `report_disclosures`

```text
disclosure_id
report_id
category
severity
code
message_template_id
source_snapshot_id
is_blocking
created_at
disclosure_hash
```

Categories:

```text
DATA_QUALITY
BENCHMARK
ACCOUNTING
EXECUTION
RISK
OPERATIONAL
METHODOLOGY
RESTATEMENT
REPLAY
LEGAL
```

---

## 63. `report_restatements`

```text
restatement_id
original_report_id
replacement_report_id

reason_code
materiality

source_correction_id
known_at
approved_at

restatement_hash
```

---

## 64. Code structure

```text
reporting/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── repository.py
├── engine.py
│
├── adapters/
│   ├── accounting.py
│   ├── reconciliation.py
│   ├── benchmark.py
│   ├── decisions.py
│   ├── execution.py
│   ├── attribution.py
│   ├── risk.py
│   ├── stress.py
│   ├── drawdown.py
│   ├── operational.py
│   └── orchestration.py
│
├── cutoffs.py
├── trading_days.py
├── source_registry.py
├── completeness.py
│
├── portfolio.py
├── holdings.py
├── cash.py
├── trades.py
├── decisions.py
│
├── performance/
│   ├── returns.py
│   ├── twr.py
│   ├── mwr.py
│   ├── chaining.py
│   └── precision.py
│
├── benchmark/
│   ├── bindings.py
│   ├── inception.py
│   ├── alignment.py
│   └── relative.py
│
├── compliance.py
├── disclosures.py
├── reconciliation.py
│
├── replay/
│   ├── actual_path.py
│   ├── target_path.py
│   ├── divergence.py
│   └── comparison.py
│
├── restatement.py
├── supersession.py
│
├── payload.py
├── renderers/
│   ├── markdown.py
│   ├── html.py
│   ├── json.py
│   └── pdf_contract.py
│
├── integrity.py
├── manifests.py
└── hashing.py
```

---

## 65. Core daily-report algorithm

```python
def build_daily_report(ctx):
    policy = load_reporting_policy(ctx)
    cutoff = resolve_reporting_cutoff(ctx, policy)

    sources = load_source_snapshots(
        portfolio_id=ctx.portfolio_id,
        trading_date=ctx.trading_date,
        cutoff=cutoff,
    )

    validate_point_in_time(sources, cutoff)
    validate_source_finalization(sources)

    calendar_state = resolve_trading_day(ctx)

    portfolio = build_portfolio_report_snapshot(
        accounting=sources.accounting,
        reconciliation=sources.reconciliation,
    )

    decisions = build_decision_lines(
        decision_ledger=sources.decision_ledger,
    )

    trades = build_trade_lines(
        orders=sources.orders,
        fills=sources.fills,
    )

    benchmark = resolve_benchmark_report(
        portfolio_id=ctx.portfolio_id,
        trading_date=ctx.trading_date,
        benchmark_sources=sources.benchmark,
        calendar_state=calendar_state,
    )

    performance = calculate_authoritative_performance(
        portfolio=portfolio,
        benchmark=benchmark,
        previous_report=sources.previous_report,
        method=policy.performance_method,
        calendar_state=calendar_state,
    )

    risk = summarize_risk(sources.risk)
    stress = summarize_stress(sources.stress)
    drawdown = summarize_drawdown(sources.drawdown)
    operations = summarize_operational_health(sources.operational)

    disclosures = collect_disclosures(
        sources=sources,
        benchmark=benchmark,
        performance=performance,
    )

    validate_pnl_reconciliation(portfolio, trades)
    validate_holdings_reconciliation(portfolio, trades)
    validate_performance_chain(performance)

    payload = build_canonical_payload(
        portfolio=portfolio,
        performance=performance,
        benchmark=benchmark,
        decisions=decisions,
        trades=trades,
        risk=risk,
        stress=stress,
        drawdown=drawdown,
        operations=operations,
        disclosures=disclosures,
    )

    return finalize_immutable_report(payload, policy)
```

---

## 66. Benchmark inception algorithm

```python
def establish_benchmark_inception(ctx):
    assert ctx.portfolio_inception_is_final
    assert ctx.benchmark_snapshot.is_final
    assert ctx.benchmark_snapshot.known_at <= ctx.cutoff

    if existing_inception(ctx.portfolio_id):
        raise BenchmarkInceptionAlreadyExists()

    return BenchmarkInception(
        portfolio_id=ctx.portfolio_id,
        benchmark_id=ctx.benchmark_id,
        inception_trading_date=ctx.trading_date,
        inception_value=ctx.benchmark_snapshot.close,
        source_snapshot_id=ctx.benchmark_snapshot.id,
        known_at=ctx.benchmark_snapshot.known_at,
        benchmark_policy_id=ctx.policy.id,
    )
```

Historical hindsight creation is not permitted in `OFFICIAL_BOR` mode.

---

## 67. Trading-day return algorithm

```python
def compute_daily_return(current, previous, calendar_state):
    if calendar_state == "MARKET_CLOSED":
        return ReturnObservation(state="MARKET_CLOSED", value=None)

    if not current.finalized or not previous.finalized:
        return ReturnObservation(state="INVALID", value=None)

    return ReturnObservation(
        state="VALID",
        value=current.nav / previous.nav - 1.0,
    )
```

---

## 68. NO_ACTION renderer rule

```python
def render_no_action(decision):
    assert decision.decision_type == "NO_ACTION"
    assert decision.decision_subtype is not None
    assert decision.primary_reason_code is not None

    return {
        "decision": "NO_ACTION",
        "subtype": decision.decision_subtype,
        "primary_reason": decision.primary_reason_code,
        "binding_constraint": decision.binding_constraint_id,
    }
```

A generic unlabeled `NO_ACTION` is invalid.

---

## 69. Restatement algorithm

```python
def restate_report(original, corrected_sources, reason):
    assert original.status in {"FINALIZED", "DISTRIBUTED"}

    replacement = rebuild_from_corrected_sources(
        original_report=original,
        corrected_sources=corrected_sources,
    )

    replacement.supersedes_report_id = original.report_id

    create_restatement_link(
        original=original,
        replacement=replacement,
        reason=reason,
    )

    mark_superseded_without_mutating(original)

    return replacement
```

---

## 70. Report publication gate

A report cannot become FINAL when any of the following applies:

```text
ACCOUNTING_NOT_FINALIZED
CRITICAL_RECONCILIATION_FAILURE
DECISION_LEDGER_INCOMPLETE
RISK_SNAPSHOT_MISSING
OPERATIONAL_SNAPSHOT_MISSING
ORCHESTRATION_RUN_INVALID
REPORT_PNL_RECONCILIATION_FAILED
REPORT_HOLDINGS_RECONCILIATION_FAILED
REPORT_HASH_INTEGRITY_FAILED
```

Benchmark missing does not necessarily block portfolio reporting, but it blocks benchmark/active-return fields and creates a mandatory disclosure.

---

## 71. Reason codes

```text
REPORT_FINALIZED
REPORT_SOURCE_PENDING
REPORT_VALIDATION_FAILED

ACCOUNTING_SOURCE_MISSING
ACCOUNTING_NOT_FINALIZED
REPORT_PNL_RECONCILIATION_FAILED
REPORT_HOLDINGS_RECONCILIATION_FAILED

BENCHMARK_INCEPTION_NOT_RECORDED
BENCHMARK_CLOSE_MISSING
BENCHMARK_ALIGNMENT_FAILED
BENCHMARK_RETURN_UNAVAILABLE
ACTIVE_RETURN_UNAVAILABLE
RECONSTRUCTED_BENCHMARK_NON_OFFICIAL

MARKET_CLOSED_RETURN_NOT_OBSERVED
UNSCHEDULED_MARKET_CLOSURE

DECISION_LEDGER_INCOMPLETE
NO_ACTION_SUBTYPE_MISSING
DECISION_PROOF_MISSING

ORDER_FILL_MISMATCH
PARTIAL_FILL_REPORTED
UNFILLED_QUANTITY_REPORTED

RISK_DISCLOSURE_REQUIRED
STRESS_DISCLOSURE_REQUIRED
DRAWDOWN_DISCLOSURE_REQUIRED
OPERATIONAL_DISCLOSURE_REQUIRED

DATA_QUALITY_DISCLOSURE_REQUIRED
SOURCE_CONFLICT_DISCLOSED
STALE_VALUATION_DISCLOSED

PERFORMANCE_CHAIN_GAP
BENCHMARK_CHAIN_GAP

REPORT_RESTATEMENT_CREATED
REPORT_SUPERSEDED
REPORT_REVOKED

REPLAY_PATH_DIVERGED
REPLAY_PATH_RESYNCHRONIZED
REPLAY_NON_OFFICIAL

FUTURE_INFORMATION_GUARD
REPORT_SOURCE_AFTER_CUTOFF
REPORT_HASH_INTEGRITY_FAILED
```

---

## 72. Unit tests

```text
A. Normal trading day, no positions
NAV valid
cash 100%
→ daily return computed
→ holdings empty
→ report FINAL

B. Market closed
→ portfolio return N/A
→ benchmark return N/A
→ no artificial 0% observation

C. NO_ACTION / RISK_BLOCKED
→ subtype and binding reason present

D. NO_ACTION without subtype
→ FINAL blocked

E. Alpha unavailable because PIT data missing
→ report N/A
→ invented score forbidden

F. Order 100, fill 65
→ trade reports 65 actual
→ unfilled 35
→ holdings reflect 65 only

G. EOD BUY decision
→ same-day-close fill absent

H. Benchmark inception recorded
→ cumulative benchmark valid prospectively

I. Benchmark inception missing historically
→ official cumulative benchmark N/A
→ no hindsight fabrication

J. Benchmark close missing one trading day
→ active return N/A for that day
→ no forward fill

K. Accounting NAV mismatch
→ FINAL blocked

L. Position reconciliation mismatch
→ FINAL blocked

M. Risk snapshot missing
→ FINAL blocked

N. Operational health missing
→ FINAL blocked

O. Optional attribution missing
→ core report may FINAL with disclosure

P. Late corporate filing after report cutoff
→ original report unchanged

Q. Corrected accounting source
→ new report version
→ old report SUPERSEDED, not mutated

R. Human renderer rounds 0.12654
→ display policy applied
→ stored exact value unchanged

S. Report hash payload mutation
→ integrity failure

T. Same sources + same policy
→ same payload hash and report hash
```

---

## 73. Integration tests

```text
1. 56 Decision Freeze
→ 57 Ledger
→ 58 report contains same primary reason

2. 54 Risk BUY BLOCKED
→ 57 NO_ACTION/RISK_BLOCKED
→ 58 same subtype, no narrative drift

3. 55 Broker-order API failure
→ decision may remain valid
→ execution report shows blocked execution

4. 46 partial fill
→ 19 accounting quantity
→ 58 fill and holding reconcile

5. 49 subsequent opportunity cost
→ original reason remains unchanged
→ attribution appears only in outcome section

6. 51 strategy netting
→ aggregate fill one order
→ strategy attribution lineage retained

7. 52 survival hard breach
→ risk disclosure cannot be hidden

8. 53 drawdown state change
→ daily report reflects accounting HWM state

9. Replay target path divergence
→ replay report changes
→ official portfolio report remains unchanged

10. Restated NAV
→ replacement performance chain rebuilt prospectively from corrected point
→ supersession links complete
```

---

## 74. Property tests

```text
Ending NAV reconciliation error within tolerance
or report never FINAL

Official active return exists
only if both portfolio and benchmark return exist

MARKET_CLOSED never adds a valid return observation

NO_ACTION always has subtype

FILLED quantity never exceeds requested quantity

Holding quantity equals accounting quantity

Report source known_at never exceeds source cutoff

Official report never consumes RECONSTRUCTED_NON_OFFICIAL benchmark as official

Restatement never mutates original payload hash

Same input manifest + reporting policy
→ same canonical payload
→ same report hash
```

---

## 75. Failure-injection tests

```text
Database timeout during report build
→ no partial FINAL report

Renderer failure after payload finalized
→ canonical report remains valid
→ distribution retry possible

Benchmark vendor outage
→ portfolio report available
→ benchmark fields unavailable + disclosure

Accounting failure
→ report FINAL blocked

Decision ledger DB failure
→ report FINAL blocked

Hash store failure
→ report FINAL blocked

Distribution API failure
→ report remains FINALIZED
→ distribution state failed/retryable
```

---

## 76. Performance tests

Targets for initial PAPER environment:

```text
Daily portfolio report < 2 seconds after all mandatory sources ready
1,000 candidate lines < 1 second table materialization
10,000 fill lines < 3 seconds aggregation
5-year daily performance chain replay < 10 seconds
```

Performance optimization must not relax validation or change deterministic ordering.

---

## 77. Deterministic ordering

All collections use stable ordering.

Example:

```text
Candidate lines:
rank ASC
security_id ASC

Holdings:
portfolio_weight DESC
security_id ASC

Fills:
fill_time ASC
fill_sequence ASC
fill_id ASC

Disclosures:
severity DESC
category ASC
code ASC
```

This ensures identical report hashes across reruns.

---

## 78. Security and access control

Report namespaces may have different visibility.

```text
PAPER
LIVE_SHADOW
LIVE
EXTERNAL_AUDIT
```

Access control applies after canonical report creation.

A user without permission may receive a redacted rendering, but the canonical Book-of-Record remains unchanged.

---

## 79. Retention

Official report artifacts and manifests are append-only and retained according to governance policy.

At minimum retain:

```text
canonical payload
source manifest
hashes
policy version
renderer version
distribution records
restatement lineage
```

---

## 80. Initial PAPER daily report requirements

For the current ADE virtual portfolio policy, Engine 58 must always expose:

```text
1 ADE logic/version
2 Candidate Signal/Risk/Decision
3 Virtual buys/sells: price, quantity, amount
4 Holdings and cash
5 Daily return and cumulative return
6 KOSPI or approved benchmark performance comparison
7 Decision rationale and risk-block reasons
8 Simulation / not-investment-advice disclosure
```

Portfolio constraints displayed:

```text
Initial capital       10,000,000 KRW
Leverage              none
Minimum cash          10%
Maximum single name   10%
Maximum new buys/day  1
```

These are sourced from the active portfolio/risk policy, not hard-coded in the renderer.

---

## 81. Migration plan for existing ADE daily reports

Phase 1:

```text
Continue human-readable reports
but generate canonical structured payload first.
```

Phase 2:

```text
Persist accounting/benchmark/decision/report IDs.
```

Phase 3:

```text
Establish prospective BenchmarkInception.
```

Phase 4:

```text
Generate Markdown/HTML entirely from Engine 58 payload.
```

Phase 5:

```text
Enable immutable restatement and audit-chain verification.
```

Historical reports without complete source snapshots remain legacy records and are not silently upgraded to official Engine-58 reports.

---

## 82. Initial implementation order

```text
1 Immutable report models/enums/contracts
2 Reporting policy + cutoff resolver
3 Source manifest registry
4 Portfolio/accounting adapter
5 Holdings/cash reporting
6 Decision Ledger adapter
7 NO_ACTION subtype validation
8 Order/fill reporting
9 Benchmark binding/inception tables
10 Daily/cumulative performance chain
11 Risk/stress/drawdown/operational summaries
12 Disclosures
13 Reconciliation gates
14 Canonical payload
15 Hashing/manifest
16 Markdown renderer
17 Restatement/supersession
18 Replay-report namespace
19 Integration tests
20 Historical-chain tests
```

---

## 83. Initial implementation interfaces

```python
class ReportingEngine:
    def build_daily(self, request: DailyReportRequest) -> FinalReport:
        ...

    def build_periodic(self, request: PeriodicReportRequest) -> FinalReport:
        ...

    def restate(self, request: RestatementRequest) -> FinalReport:
        ...

    def verify(self, report_id: str) -> IntegrityResult:
        ...
```

```python
class BenchmarkBook:
    def establish_inception(self, request): ...
    def resolve_binding(self, as_of_time): ...
    def daily_return(self, trading_date): ...
    def cumulative_return(self, start, end): ...
```

```python
class PerformanceBook:
    def append_observation(self, observation): ...
    def validate_chain(self, portfolio_id): ...
    def since_inception(self, portfolio_id): ...
```

---

## 84. Example official daily record

```text
Trading Date        2026-08-25
Portfolio NAV       9,883,000 KRW
Cash                9,883,000 KRW
Equity Exposure     0%

Decision            NO_ACTION
Subtype             RISK_BLOCKED
Primary Reason      RECOVERY_NOT_CONFIRMED

Portfolio Return    0.00%
Benchmark Return    +0.68%
Active Return       -0.68%p

Cumulative Return   -1.17%
Benchmark Cumulative
                    unavailable if no valid official inception exists

Risk State          RISK_OFF / EARLY_RECOVERY

Report Namespace    OFFICIAL_BOR
```

The exact values are examples of schema usage; Engine 58 itself never invents them and only consumes frozen source snapshots.

---

## 85. Example after prospective benchmark inception

Suppose a new official benchmark inception is established on date D:

```text
Portfolio inception NAV    9,883,000
KOSPI inception level      6,742.74
```

Future reports calculate both official chains prospectively.

```text
Portfolio cumulative      +3.20%
KOSPI cumulative          +1.10%
Active cumulative         +2.10%p
```

No historical pre-D benchmark series is backfilled into the official Book-of-Record unless governance explicitly creates a separately labeled reconstruction.

---

## 86. Explainability requirement for displayed numbers

Every material number in an official report must answer:

```text
Where did this number come from?
Which snapshot produced it?
Which methodology transformed it?
Which policy version governed it?
Was it known by the reporting cutoff?
```

Material report fields therefore carry hidden lineage IDs in the canonical payload even if the human display omits them.

---

## 87. Report-level confidence is not investment confidence

Engine 58 may expose:

```text
REPORT_DATA_QUALITY = HIGH / DEGRADED / LOW
```

This describes report completeness and source quality.

It must never be confused with Engine 42 investment `Confidence Score`.

---

## 88. Report-quality state

```text
COMPLETE
COMPLETE_WITH_DISCLOSURES
DEGRADED
BLOCKED
```

Examples:

```text
Benchmark missing but portfolio/accounting complete
→ COMPLETE_WITH_DISCLOSURES

Accounting unreconciled
→ BLOCKED

Optional attribution missing
→ COMPLETE_WITH_DISCLOSURES
```

---

## 89. Primary report integrity invariants

```text
Final report without finalized accounting = 0

Final trading-day report without Decision Ledger state = 0

NO_ACTION without subtype = 0

Future source after cutoff in original report = 0

Market-closed day recorded as valid 0% return = 0

Benchmark missing recorded as 0% return = 0

Official historical benchmark fabricated from hindsight = 0

Requested order quantity reported as filled quantity = 0

Partial fill omitted = 0

Cash/holding values inconsistent with accounting = 0

Outcome attribution inserted into original rationale = 0

Replay path merged into official Book-of-Record = 0

Restatement mutating original report = 0

Rendered output differing from canonical payload = 0

Same inputs + same policy producing different report hash = 0
```

---

## 90. End-to-end acceptance scenarios

### Scenario A — Normal BUY

```text
Signal ELIGIBLE
Risk ALLOWED
Decision BUY
Next-session partial fill
Accounting updates position
Benchmark available

→ report shows signal, permission, decision, actual fill, cost, holding, NAV, return, benchmark and proof hash.
```

### Scenario B — NO_ACTION / RISK_BLOCKED

```text
Signal ELIGIBLE
Risk Governor BLOCKED
No order

→ report shows NO_ACTION/RISK_BLOCKED and binding constraint.
```

### Scenario C — DATA_BLOCKED

```text
PIT factor unavailable
Alpha N/A
No valid candidate evaluation

→ report shows N/A, DATA_BLOCKED and no invented score.
```

### Scenario D — Market closed

```text
No trading session

→ return N/A
→ benchmark N/A
→ no fill
→ no performance observation added.
```

### Scenario E — Execution unavailable

```text
Decision BUY valid
Broker order health FAILED next morning

→ decision remains BUY
→ execution blocked
→ holding unchanged
→ report differentiates decision from execution.
```

### Scenario F — Restatement

```text
Late discovery of incorrect accounting quantity

→ original report preserved
→ corrected report generated
→ supersession chain created.
```

---

## 91. Relationship to Engines 54~57

```text
54 Risk Governor
"Is risk expansion permitted?"

55 Operational Resilience
"Can the system be trusted and can actions be executed safely?"

56 Runtime Coordinator
"Did all required components run with correct cutoff, dependency, and version?"

57 Decision Ledger
"Why exactly did this decision occur?"

58 Reporting Book-of-Record
"What is the official portfolio/performance record, and can the published report be reproduced exactly?"
```

---

## 92. Why Engine 58 matters to ADE

Without Engine 58, ADE can make auditable decisions but its historical daily reports can still drift because different days may use different presentation assumptions, benchmark treatment, performance arithmetic, or hindsight data.

Engine 58 closes that gap.

```text
Decision truth
+ Execution truth
+ Accounting truth
+ Benchmark truth
+ Risk truth
        ↓
58 Reporting Book-of-Record
        ↓
One reproducible official record
```

It transforms ADE daily paper-trading reports from narrative summaries into a deterministic performance record suitable for replay, model evaluation, governance, and audit.

---

## 93. Recommended next engine

The natural next layer is:

```text
59. Portfolio Analytics, Risk-Adjusted Performance & Manager Scorecard Engine
```

Engine 58 establishes the authoritative reporting/performance Book-of-Record. Engine 59 can then safely compute advanced analytics such as Sharpe, Sortino, Information Ratio, capture ratios, tracking error, beta, rolling alpha, turnover efficiency, drawdown recovery, decision hit rate, NO_ACTION opportunity cost, and engine/strategy scorecards without contaminating the official accounting record.
