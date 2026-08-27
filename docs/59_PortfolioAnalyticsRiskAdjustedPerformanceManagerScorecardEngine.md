# 59. Portfolio Analytics, Risk-Adjusted Performance & Manager Scorecard Engine v1

## 1. Purpose

Engine 59 is ADE's analytical performance layer built on top of the immutable Reporting Book-of-Record created by Engine 58.

It answers:

> Given the official portfolio, benchmark, decision, execution, risk and attribution records, how good was ADE's performance after adjusting for risk, drawdown, benchmark exposure, turnover, execution quality and decision quality — and which engines or decision types are improving or degrading?

Engine 59 does not rewrite official NAV, invent missing benchmark history, change past decisions, tune strategy parameters, or promote models. It calculates analytical metrics and scorecards from already-finalized records.

Core principle:

```text
58 = What officially happened?
59 = How good was what happened?

Official Book-of-Record is immutable.
Analytics are derived, versioned and reproducible.

Same finalized source snapshots
+ same analytics policy
+ same evaluation window
→ same metrics + same scorecards + same analytics hash.
```

---

## 2. Position in ADE architecture

```text
19 Accounting / NAV
46 Execution / Fill Quality
49 Outcome Attribution
51 Strategy Ensemble
52 Stress & Survival
53 Capital Preservation
54 Risk Governor
57 Decision Ledger
58 Reporting Book-of-Record
        ↓
┌──────────────────────────────────────────────────────┐
│ 59 Portfolio Analytics & Manager Scorecard          │
├──────────────────────────────────────────────────────┤
│ Observation Window Resolver                         │
│ Return / Benchmark Alignment                        │
│ Risk-Adjusted Performance                           │
│ Benchmark / Active-Risk Analytics                   │
│ Drawdown / Recovery Analytics                       │
│ Up/Down Capture                                     │
│ Tail / Downside Analytics                           │
│ Turnover / Cost Efficiency                          │
│ Decision Quality Analytics                          │
│ NO_ACTION Analytics                                 │
│ Strategy / Engine Scorecards                        │
│ Confidence / Sample Sufficiency                     │
│ Trend / Degradation Detection                       │
│ Immutable Analytics Snapshot                        │
└──────────────────────────────────────────────────────┘
        ↓
60+ monitoring / research / governance consumers
```

Engine 49 explains outcome attribution at decision and engine level. Engine 59 aggregates those observations into stable, period-aware performance analytics and management scorecards.

---

## 3. Responsibility boundary

### Engine 59 does

- consume finalized Engine 58 official report/performance observations;
- resolve valid observation windows using the trading calendar;
- calculate cumulative and annualized return metrics;
- calculate realized volatility and downside deviation;
- calculate Sharpe, Sortino and Calmar ratios;
- calculate benchmark alpha/beta, tracking error and Information Ratio when benchmark coverage is valid;
- calculate upside/downside capture;
- calculate drawdown depth, duration, recovery time and ulcer-style metrics;
- calculate win rate, hit rate, payoff ratio and profit factor where statistically meaningful;
- calculate turnover, cost drag and return-per-turnover;
- calculate execution-quality scorecards from Engine 46/47 outputs;
- calculate decision-quality scorecards from Engines 49 and 57;
- separately evaluate BUY/ADD/HOLD/REDUCE/EXIT/NO_ACTION cohorts;
- distinguish NO_ACTION downside protection from opportunity cost;
- calculate strategy- and engine-level rolling scorecards;
- label all metrics with sample size, coverage and confidence state;
- detect metric deterioration and trend breaks;
- create immutable analytical snapshots and manifests.

### Engine 59 does not

- change portfolio NAV or P&L;
- create benchmark observations that were not recorded by Engine 58;
- treat missing returns as zero;
- treat market-closed days as zero-return observations;
- change Signal weights;
- change Risk Governor thresholds;
- recommend trades directly;
- change ACTIVE strategies;
- use future outcomes in past analytics snapshots;
- optimize parameters based on the scorecard;
- replace Engine 49 attribution;
- replace Engine 50 walk-forward strategy research;
- replace Engine 48 governance.

---

## 4. Source-of-truth hierarchy

Engine 59 never recalculates official history from raw market data if the official Reporting BoR exists.

```text
Primary
58 performance_return_observations
58 benchmark_return_observations
58 portfolio_report_snapshots
58 decision_report_lines
58 fill_report_lines

Secondary
49 outcome attribution
46 execution quality
53 drawdown snapshots
54 risk snapshots
57 decision ledger
```

If an analytical metric disagrees with official cumulative return from Engine 58:

```text
ANALYTICS_BOR_RECONCILIATION_FAILED
→ metric set cannot FINALIZE.
```

---

## 5. Observation windows

Analytics are period-dependent. Every metric must carry a window definition.

Supported standard windows:

```text
5D
20D
60D
120D
252D
MTD
QTD
YTD
SINCE_INCEPTION
CUSTOM
```

A window stores:

```text
window_id
start_date
end_date
trading_day_count
portfolio_observation_count
benchmark_observation_count
market_closed_days_excluded
missing_observation_count
coverage_ratio
```

Rules:

```text
Market closed day → excluded.
Missing valid trading-day NAV → missing, never 0%.
Missing benchmark observation → benchmark-dependent metric N/A.
```

---

## 6. Return conventions

Daily portfolio return comes from Engine 58.

```text
r_p,t = NAV_t / NAV_t-1 - 1
```

Cumulative return:

```text
R_p = Π(1 + r_p,t) - 1
```

Annualized return for sufficiently long windows:

```text
AnnualizedReturn
= (1 + R_p)^(252 / N) - 1
```

where `N` is valid trading observations.

Do not annualize very short samples by default.

Initial policy:

```text
N < 20
→ ANNUALIZATION_SAMPLE_INSUFFICIENT
```

---

## 7. Risk-free rate policy

Sharpe and related metrics require an approved point-in-time risk-free series.

Examples of policy-configurable references:

```text
KRW short-term government rate
KOFR-derived daily series
approved cash proxy
```

Engine 59 must not silently assume 0% risk-free rate unless the analytics policy explicitly says so.

```text
risk_free.known_at <= analytics_cutoff
```

If missing:

```text
RISK_FREE_SERIES_UNAVAILABLE
→ Sharpe = N/A
```

---

## 8. Realized volatility

For daily return standard deviation `σ_d`:

```text
Annualized Volatility
= std(r_p) × sqrt(252)
```

Required supporting statistics:

```text
mean_daily_return
median_daily_return
std_daily_return
annualized_volatility
positive_day_ratio
negative_day_ratio
zero_return_ratio
```

A valid market-open 0% return is allowed. Market-closed N/A is not converted to zero.

---

## 9. Sharpe Ratio

Daily excess return:

```text
x_t = r_p,t - r_f,t
```

Annualized Sharpe:

```text
Sharpe
= mean(x_t) / std(x_t) × sqrt(252)
```

Guardrails:

```text
N < minimum_sharpe_observations
→ N/A / LOW_CONFIDENCE

std(x_t) approximately 0
→ SHARPE_UNDEFINED_ZERO_VARIANCE
```

A 100% cash portfolio with almost no variance must not produce an artificial infinite Sharpe.

---

## 10. Sortino Ratio

Downside deviation uses only returns below the policy target return `MAR`.

```text
d_t = min(0, r_p,t - MAR_t)

DownsideDeviation
= sqrt(mean(d_t^2)) × sqrt(252)
```

```text
Sortino
= AnnualizedExcessReturn / AnnualizedDownsideDeviation
```

Policy must store whether MAR is:

```text
0%
risk-free rate
benchmark return
custom hurdle
```

---

## 11. Calmar Ratio

```text
Calmar
= AnnualizedReturn / abs(MaxDrawdown)
```

Do not produce a misleading value for very short windows without meaningful drawdown history.

```text
CALMAR_SAMPLE_INSUFFICIENT
```

---

## 12. Maximum drawdown

Use the official NAV path, not recalculated synthetic prices.

```text
HWM_t = max(NAV_0 ... NAV_t)
DD_t  = NAV_t / HWM_t - 1
MaxDD = min(DD_t)
```

Store the full drawdown episode:

```text
peak_date
trough_date
recovery_date
peak_nav
trough_nav
max_drawdown_pct
days_peak_to_trough
days_trough_to_recovery
total_underwater_days
recovered_flag
```

If unrecovered:

```text
recovery_date = NULL
```

Never pretend the evaluation date is a recovery date.

---

## 13. Drawdown duration and recovery quality

Engine 53 controls risk during drawdown; Engine 59 evaluates the historical quality of that path.

Metrics:

```text
max_drawdown
average_drawdown
median_drawdown
max_underwater_days
average_underwater_days
recovery_factor
new_high_frequency
```

Recovery Factor:

```text
RecoveryFactor
= NetProfit / abs(MaxDrawdownAmount)
```

where both quantities come from the same accounting basis.

---

## 14. Ulcer Index

For drawdown percentages `DD_t`:

```text
UlcerIndex
= sqrt(mean(DD_t^2))
```

This penalizes both drawdown depth and persistence and is useful for distinguishing two strategies with identical MaxDD but very different underwater duration.

---

## 15. Benchmark alignment

Benchmark-dependent analytics require exact trading-date alignment.

```text
joined_observations
= INNER JOIN portfolio_return, benchmark_return
ON trading_date
AND both are finalized valid observations
```

Never:

```text
forward-fill missing benchmark return
backfill from future observation
assume missing benchmark = 0
```

Store:

```text
portfolio_count
benchmark_count
aligned_count
alignment_ratio
```

Initial policy example:

```text
alignment_ratio < 95%
→ benchmark analytics DEGRADED

alignment_ratio < 80%
→ benchmark analytics BLOCKED
```

---

## 16. Active return

```text
ActiveReturn_t
= r_p,t - r_b,t
```

Cumulative relative performance should preserve compounding where required.

Two separate concepts are stored:

```text
Arithmetic cumulative active return
Compounded relative wealth return
```

Do not silently mix them.

---

## 17. Tracking Error

```text
TE
= std(r_p - r_b) × sqrt(252)
```

Required minimum sample and alignment ratio apply.

---

## 18. Information Ratio

```text
IR
= mean(r_p - r_b)
  / std(r_p - r_b)
  × sqrt(252)
```

If tracking error is effectively zero:

```text
INFORMATION_RATIO_UNDEFINED_ZERO_TE
```

---

## 19. Beta and Jensen-style Alpha

Default simple model:

```text
r_p,t - r_f,t
= alpha_d
+ beta × (r_b,t - r_f,t)
+ ε_t
```

Annualized alpha approximation:

```text
alpha_annual
≈ alpha_daily × 252
```

Store:

```text
alpha
beta
r_squared
standard_error
observation_count
confidence_interval
```

Do not publish alpha without sample and fit quality.

Initial states:

```text
VALID
LOW_SAMPLE
LOW_FIT
UNAVAILABLE
```

---

## 20. Up Capture Ratio

Use only benchmark-positive aligned trading observations.

```text
UpCapture
= PortfolioReturn_on_Up_Market
  / BenchmarkReturn_on_Up_Market
```

Recommended implementation uses compounded returns over selected up-market observations.

Example interpretation:

```text
Up Capture 80%
→ ADE captured about 80% of benchmark's positive-market return.
```

---

## 21. Down Capture Ratio

Use benchmark-negative aligned observations.

```text
DownCapture
= PortfolioReturn_on_Down_Market
  / BenchmarkReturn_on_Down_Market
```

Lower magnitude can indicate downside protection.

Example:

```text
Down Capture 40%
→ when benchmark declined, portfolio experienced roughly 40% of benchmark decline.
```

Do not collapse Up Capture and Down Capture into one score without preserving both raw metrics.

---

## 22. Capture Efficiency

Optional summary:

```text
CaptureEfficiency
= UpCapture / abs(DownCapture)
```

Guardrails apply when downside capture approaches zero.

---

## 23. Tail and downside analytics

Metrics:

```text
worst_1d_return
worst_5d_return
best_1d_return
best_5d_return
VaR_95_historical
ExpectedShortfall_95
DownsideDeviation
negative_skew_indicator
```

Historical Expected Shortfall:

```text
ES95
= mean(returns <= empirical 5th percentile)
```

This is analytical observed-history ES. It is not a replacement for Engine 52 forward stress testing.

---

## 24. Hit rate and payoff statistics

Daily hit rate is not always meaningful for low-turnover portfolios. Engine 59 therefore supports multiple units:

```text
DAY
CLOSED_POSITION
DECISION_OUTCOME
SIGNAL_HORIZON
```

For closed positions:

```text
WinRate
= profitable_closed_positions / closed_positions

AverageWin
AverageLoss
PayoffRatio = AverageWin / abs(AverageLoss)

ProfitFactor
= GrossProfit / abs(GrossLoss)
```

If there are no losses:

```text
PROFIT_FACTOR_UNDEFINED_NO_LOSSES
```

not infinity.

---

## 25. Turnover analytics

Daily turnover must use a single approved convention.

Example policy:

```text
Turnover_t
= 0.5 × Σ |weight_t - weight_t-1 adjusted for flows|
```

Store both:

```text
gross_trade_turnover
portfolio_weight_turnover
```

Never mix the two.

Period metrics:

```text
annualized_turnover
average_daily_turnover
median_daily_turnover
maximum_daily_turnover
```

---

## 26. Cost drag

From official Execution / Accounting costs:

```text
TotalCost
= commissions
+ taxes
+ realized_slippage_cost
+ realized_market_impact
```

Cost Drag:

```text
CostDrag
= TotalCost / average_NAV
```

Also store:

```text
explicit_cost_bps
implicit_cost_bps
execution_shortfall_bps
cost_as_pct_of_gross_alpha
```

Do not treat opportunity cost as cash transaction cost.

---

## 27. Return per turnover

```text
ReturnPerTurnover
= NetReturn / Turnover
```

and where attribution permits:

```text
ActiveReturnPerTurnover
= ActiveReturn / Turnover
```

This helps identify strategies whose gross signal works but whose trading frequency consumes the alpha.

Guardrail:

```text
Turnover ≈ 0
→ metric N/A, not infinite.
```

---

## 28. Execution efficiency scorecard

Inputs from Engine 46/47:

```text
fill_ratio
implementation_shortfall
arrival_slippage
partial_fill_rate
cancel_rate
opportunity_cost
cost_model_bias
```

Initial execution score components:

```text
25% Fill Quality
25% Implementation Shortfall
20% Slippage Control
15% Cost Model Calibration
10% Latency / Completion
 5% Operational Stability
```

Score output:

```text
0~100
HEALTHY
WATCH
DEGRADED
CRITICAL
```

A score is never allowed to hide hard execution failures such as impossible fills or reconciliation breaks.

---

## 29. Decision analytics

Engine 57 gives immutable decision records; Engine 49 gives outcomes.

Engine 59 aggregates:

```text
BUY count
ADD count
HOLD count
REDUCE count
EXIT count
NO_ACTION count

Decision outcome hit rate
Mean 1D/5D/20D/60D active outcome
Median outcome
False positive rate
False negative rate
Decision-quality score
```

Every outcome metric must use a horizon that had fully elapsed by analytics cutoff.

```text
20D horizon not complete
→ outcome excluded from 20D scorecard
```

---

## 30. BUY / ADD scorecard

For BUY/ADD decisions:

```text
candidate_count
approved_count
executed_count
fill_adjusted_count
1D_active_return
5D_active_return
20D_active_return
60D_active_return
hit_rate_by_horizon
max_adverse_excursion
max_favorable_excursion
```

Decision result and execution result remain separate.

A correct BUY with no fill should not be scored as an executed-position return.

---

## 31. EXIT / REDUCE scorecard

For EXIT/REDUCE:

```text
post_exit_1D_return
post_exit_5D_return
post_exit_20D_return
loss_avoided
opportunity_cost
exit_efficiency
```

Engine 59 preserves reason types:

```text
SIGNAL_EXIT
RISK_EXIT
FORCED_EXIT
PROFIT_PROTECTION
TIME_EXIT
PORTFOLIO_REBALANCE
```

A forced risk exit is not deemed incorrect merely because the security rallied afterward.

---

## 32. NO_ACTION is a first-class analytics cohort

NO_ACTION subtypes are evaluated separately:

```text
NO_CANDIDATE
SIGNAL_REJECTED
RISK_BLOCKED
DATA_BLOCKED
OPERATIONAL_BLOCKED
MARKET_CLOSED
NO_RISK_HEADROOM
WITHIN_REBALANCE_BAND
EXECUTION_NOT_PERMITTED
```

Never aggregate all NO_ACTIONs into one hit-rate statistic.

---

## 33. NO_ACTION downside protection

For an eligible but blocked candidate or market-risk decision, Engine 49 may calculate what happened afterward under strictly point-in-time counterfactual rules.

Engine 59 aggregates:

```text
NO_ACTION downside avoided
NO_ACTION opportunity cost
NO_ACTION neutral outcome
```

Example:

```text
RISK_BLOCKED
Benchmark next day -6%
→ defensive protection observation
```

But:

```text
DATA_BLOCKED
Market next day -6%
```

must not be scored as evidence that the investment model predicted the decline.

---

## 34. NO_ACTION Opportunity Cost

For valid counterfactual observations produced by Engine 49:

```text
OpportunityCost_h
= CounterfactualReturn_h - ActualReturn_h
```

Store separately by subtype.

Examples:

```text
RISK_BLOCKED_OPPORTUNITY_COST
SIGNAL_REJECTED_OPPORTUNITY_COST
NO_RISK_HEADROOM_OPPORTUNITY_COST
```

DATA_BLOCKED and OPERATIONAL_BLOCKED are governance/safety observations and require separate interpretation.

---

## 35. Risk efficiency analytics

Measure return relative to risk budget actually consumed.

Metrics:

```text
average_gross_exposure
average_net_exposure
average_risk_budget
average_risk_utilization
active_return_per_unit_risk_budget
return_per_unit_volatility
return_per_unit_stress_budget
```

Example:

```text
Portfolio A return +8% at 95% risk utilization
Portfolio B return +7% at 40% risk utilization
```

Raw return alone should not imply A is superior.

---

## 36. Cash efficiency

Cash is an intentional risk outcome in ADE, not always idle failure.

Metrics:

```text
average_cash_weight
cash_return_contribution
cash_defensive_contribution
cash_opportunity_cost
cash_days_by_risk_state
```

Interpretation must preserve source reason:

```text
cash because no candidate
cash because risk blocked
cash because operational failure
cash because minimum cash policy
```

These are not equivalent.

---

## 37. Regime scorecard

Evaluate Engine 43 by regime:

```text
RISK_ON
NORMAL
RECOVERY
RISK_OFF
CRISIS
```

Metrics:

```text
portfolio_return
benchmark_return
active_return
volatility
max_drawdown
up_capture
down_capture
risk_utilization
opportunity_cost
loss_avoided
```

This supports questions such as:

```text
Does ADE preserve capital in RISK_OFF?
Does it re-risk too slowly in RECOVERY?
Does RISK_ON generate enough upside capture?
```

---

## 38. Strategy scorecard

For each Engine 51 strategy sleeve:

```text
strategy_return
active_return
volatility
Sharpe
Sortino
MaxDD
IC / RankIC where applicable
turnover
cost_drag
strategy_health
allocation_weight
risk_contribution
```

All strategy analytics use the strategy's actual allocation history, not a hindsight equal-weight reconstruction.

---

## 39. Engine scorecards

Engine 59 consumes attribution evidence to create stable operating scorecards for engines such as:

```text
38 Fundamental
39 Valuation
40 Expectations
41 Market Behavior
42 Signal Integration
43 Regime
44 Portfolio Construction
45 Lifecycle
46 Execution
51 Ensemble
52 Stress
53 Capital Preservation
54 Risk Governor
55 Operational Resilience
```

Scorecard design must respect responsibility boundaries.

Example Engine 42 metrics:

```text
5D / 20D / 60D Rank IC
Candidate precision
False positive rate
Confidence calibration
Coverage
```

Example Engine 54 metrics:

```text
loss avoided after risk block
opportunity cost after risk block
hard breach count
pretrade rejection quality
posttrade breach count
```

---

## 40. Manager Scorecard

The top-level ADE Manager Scorecard combines orthogonal dimensions rather than one raw-return number.

Initial v1 framework:

```text
25% Risk-Adjusted Performance
20% Capital Preservation
15% Benchmark Efficiency
10% Decision Quality
10% Execution Efficiency
10% Risk Discipline
 5% Operational Reliability
 5% Evidence / Reporting Quality
```

Output:

```text
manager_score 0~100
performance_state
confidence_state
binding_weakness
primary_strength
```

Example state bands:

```text
85~100  EXCELLENT
75~85   STRONG
65~75   ACCEPTABLE
50~65   WEAK
<50     CRITICAL_REVIEW
```

These labels are analytics, not automated strategy-promotion decisions.

---

## 41. Hard failures cannot be averaged away

Even if Manager Score is high, some conditions force a warning state.

```text
ACCOUNTING_RECONCILIATION_FAILURE
FUTURE_INFORMATION_VIOLATION
RISK_GOVERNOR_BYPASS
NON_REPRODUCIBLE_DECISION
CRITICAL_OPERATIONAL_FAILURE
AUDIT_HASH_FAILURE
```

Example:

```text
Return Score       95
Risk Score         90
Execution Score    92
Audit Integrity     FAIL

→ Manager state cannot be EXCELLENT.
```

---

## 42. Sample sufficiency

Every metric has a minimum sample policy.

Example initial policy:

```text
Sharpe / Sortino         >= 20 returns for provisional
                         >= 60 for standard

Beta / Alpha             >= 60 aligned returns

Up Capture               >= 10 up-market observations
Down Capture             >= 10 down-market observations

Decision hit rate        >= 20 matured outcomes
Engine scorecard         >= 30 relevant observations
```

States:

```text
INSUFFICIENT
PROVISIONAL
STANDARD
HIGH_CONFIDENCE
```

A metric with 3 observations must never be presented with the same visual/semantic authority as a metric with 300 observations.

---

## 43. Confidence intervals

Where useful, Engine 59 computes bootstrap confidence intervals using time-aware block bootstrap rather than iid resampling.

Supported metrics can include:

```text
mean active return
Sharpe
Information Ratio
hit rate
NO_ACTION opportunity cost
```

Store:

```text
estimate
lower_bound
upper_bound
confidence_level
method
block_length
sample_count
```

---

## 44. Rolling analytics

Supported rolling views:

```text
20D
60D
120D
252D
```

Metrics:

```text
rolling_return
rolling_volatility
rolling_sharpe
rolling_active_return
rolling_tracking_error
rolling_max_drawdown
rolling_turnover
rolling_decision_hit_rate
```

Rolling metrics use only observations known by each rolling end date.

---

## 45. Trend and degradation detection

The engine flags persistent deterioration, not single noisy points.

Example:

```text
60D Sharpe
1.3 → 1.0 → 0.6 → 0.2

20D Decision Hit Rate
62% → 54% → 46%
```

Possible outputs:

```text
PERFORMANCE_DEGRADING
RISK_ADJUSTED_PERFORMANCE_DEGRADING
DECISION_QUALITY_DEGRADING
EXECUTION_EFFICIENCY_DEGRADING
NO_ACTION_OPPORTUNITY_COST_RISING
```

But Engine 59 does not change parameters. It can emit analytics findings for Engine 49/50 research intake.

---

## 46. Change-point caution

A metric regime shift can be flagged using simple robust methods in v1:

```text
rolling median comparison
MAD-normalized shift
CUSUM-style warning
```

Complex online ML change-point methods are optional later.

The v1 priority is deterministic explainability.

---

## 47. Metric registry

All metrics are registered rather than hard-coded ad hoc.

Example:

```text
metric_id
metric_name
metric_family
formula_version
required_inputs
minimum_sample
annualization_policy
benchmark_required
risk_free_required
higher_is_better
valid_range
```

Examples:

```text
PERF_RETURN_CUM
PERF_VOL_ANN
PERF_SHARPE
PERF_SORTINO
PERF_CALMAR
PERF_MAX_DD
PERF_INFO_RATIO
PERF_TRACKING_ERROR
PERF_BETA
PERF_ALPHA
PERF_UP_CAPTURE
PERF_DOWN_CAPTURE
PERF_TURNOVER
PERF_COST_DRAG
DECISION_HIT_20D
NOACTION_OPPORTUNITY_COST_20D
EXEC_SHORTFALL_BPS
```

---

## 48. Database schema

Core tables:

```text
analytics_policies
analytics_policy_versions
analytics_metric_definitions

analytics_runs
analytics_windows
analytics_source_members

portfolio_performance_metrics
benchmark_performance_metrics
active_performance_metrics

drawdown_episodes
capture_metrics
tail_risk_metrics
turnover_efficiency_metrics
execution_analytics_metrics

decision_analytics_metrics
no_action_analytics_metrics
regime_analytics_metrics
strategy_analytics_metrics
engine_scorecards
manager_scorecards

analytics_trend_events
analytics_confidence_intervals
analytics_reason_events
analytics_manifests
```

---

## 49. `analytics_runs`

```text
analytics_run_id
portfolio_id
as_of_date
analytics_cutoff

reporting_snapshot_id
analytics_policy_id
analytics_policy_version
analytics_policy_hash

status
created_at
finalized_at

source_manifest_hash
output_manifest_hash
```

Status:

```text
PENDING
RUNNING
DEGRADED
FINALIZED
FAILED
```

---

## 50. `analytics_windows`

```text
window_id
analytics_run_id
window_type
start_date
end_date

expected_trading_days
portfolio_observations
benchmark_observations
aligned_observations

portfolio_coverage
benchmark_coverage
alignment_ratio

confidence_state
window_hash
```

---

## 51. `portfolio_performance_metrics`

```text
analytics_run_id
window_id
metric_id
metric_version

value
unit
sample_count
coverage_ratio
confidence_state

numerator_value
denominator_value

reason_code
input_hash
metric_hash
```

Storing numerator and denominator improves auditability for ratios.

---

## 52. `drawdown_episodes`

```text
drawdown_episode_id
portfolio_id

peak_date
trough_date
recovery_date

peak_nav
trough_nav

max_drawdown_pct
max_drawdown_amount

peak_to_trough_days
trough_to_recovery_days
underwater_days

recovered_flag
source_snapshot_hash
episode_hash
```

---

## 53. `decision_analytics_metrics`

```text
analytics_run_id
window_id

decision_type
decision_subtype
outcome_horizon

observation_count
matured_count

hit_rate
mean_active_return
median_active_return
false_positive_rate
false_negative_rate

loss_avoided
opportunity_cost

confidence_state
metric_hash
```

---

## 54. `manager_scorecards`

```text
scorecard_id
analytics_run_id
window_id

risk_adjusted_performance_score
capital_preservation_score
benchmark_efficiency_score
decision_quality_score
execution_efficiency_score
risk_discipline_score
operational_reliability_score
evidence_quality_score

manager_score
manager_state
confidence_state

primary_strength
binding_weakness
hard_failure_present

scorecard_hash
```

---

## 55. Point-in-time and cutoff rules

All Engine 59 inputs must satisfy:

```text
source.finalized_at <= analytics_cutoff
source.known_at <= analytics_cutoff
```

Outcome horizons must also have matured:

```text
outcome_horizon_end <= analytics_cutoff
```

Example:

```text
Decision date August 20
20 trading-day outcome ends September 17

Analytics as-of September 1
→ 20D outcome MUST NOT be included.
```

---

## 56. Restatement behavior

If Engine 58 publishes an official restated report, Engine 59 creates a new analytics run.

```text
Report v1
→ Analytics v1

Report v2 RESTATED
→ Analytics v2
```

Analytics v1 is not overwritten.

Store lineage:

```text
superseded_source_report_id
replacement_source_report_id
previous_analytics_run_id
restatement_reason
```

---

## 57. Official vs reconstructed analytics

Namespaces remain separated.

```text
OFFICIAL_BOR_ANALYTICS
RECONSTRUCTED_ANALYTICAL
RESEARCH_ANALYTICS
```

A historical reconstructed benchmark may support research analytics but cannot silently populate the official manager scorecard.

---

## 58. Algorithm overview

```python
def run_portfolio_analytics(ctx):
    policy = load_analytics_policy(ctx)
    report = load_finalized_reporting_snapshot(ctx)

    validate_source_integrity(report)
    validate_cutoff(report, ctx.analytics_cutoff)

    windows = resolve_windows(
        calendar=ctx.calendar,
        as_of=ctx.as_of_date,
        policy=policy,
    )

    results = []

    for window in windows:
        portfolio_returns = load_portfolio_returns(
            report,
            window,
        )

        benchmark_returns = load_benchmark_returns(
            report,
            window,
        )

        base_metrics = calculate_return_metrics(
            portfolio_returns,
            policy,
        )

        risk_metrics = calculate_risk_metrics(
            portfolio_returns,
            policy,
        )

        drawdown_metrics = calculate_drawdown_metrics(
            report.nav_path,
            window,
        )

        benchmark_metrics = calculate_benchmark_metrics(
            portfolio_returns,
            benchmark_returns,
            policy,
        )

        decision_metrics = calculate_decision_metrics(
            decisions=ctx.decision_ledger,
            outcomes=ctx.outcomes,
            window=window,
            cutoff=ctx.analytics_cutoff,
        )

        execution_metrics = calculate_execution_metrics(
            ctx.execution,
            window,
        )

        results.append(
            assemble_window_metrics(
                base_metrics,
                risk_metrics,
                drawdown_metrics,
                benchmark_metrics,
                decision_metrics,
                execution_metrics,
            )
        )

    scorecards = build_scorecards(results, ctx)

    validate_bor_reconciliation(results, report)
    validate_metric_invariants(results)

    return finalize_immutable_analytics_snapshot(
        results=results,
        scorecards=scorecards,
        policy=policy,
    )
```

---

## 59. Manager Score algorithm

```python
def build_manager_scorecard(metrics, policy):
    dimensions = {
        "risk_adjusted": score_risk_adjusted(metrics),
        "capital_preservation": score_capital_preservation(metrics),
        "benchmark_efficiency": score_benchmark_efficiency(metrics),
        "decision_quality": score_decisions(metrics),
        "execution_efficiency": score_execution(metrics),
        "risk_discipline": score_risk_discipline(metrics),
        "operational_reliability": score_operations(metrics),
        "evidence_quality": score_evidence(metrics),
    }

    confidence = resolve_scorecard_confidence(
        metrics,
        policy,
    )

    hard_failures = detect_hard_failures(metrics)

    weighted = weighted_score(
        dimensions,
        policy.dimension_weights,
    )

    state = classify_manager_state(
        weighted,
        hard_failures,
        confidence,
        policy,
    )

    return ManagerScorecard(
        dimensions=dimensions,
        manager_score=weighted,
        manager_state=state,
        confidence_state=confidence,
        hard_failures=hard_failures,
    )
```

---

## 60. Code structure

```text
portfolio_analytics/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── registry.py
├── repository.py
├── engine.py
│
├── adapters/
│   ├── reporting.py
│   ├── benchmark.py
│   ├── attribution.py
│   ├── execution.py
│   ├── decisions.py
│   ├── risk.py
│   └── operations.py
│
├── temporal.py
├── windows.py
├── alignment.py
├── coverage.py
├── risk_free.py
│
├── returns/
│   ├── cumulative.py
│   ├── annualized.py
│   └── active.py
│
├── risk/
│   ├── volatility.py
│   ├── downside.py
│   ├── sharpe.py
│   ├── sortino.py
│   ├── calmar.py
│   ├── var.py
│   └── expected_shortfall.py
│
├── benchmark/
│   ├── tracking_error.py
│   ├── information_ratio.py
│   ├── beta_alpha.py
│   └── capture.py
│
├── drawdown/
│   ├── episodes.py
│   ├── recovery.py
│   └── ulcer.py
│
├── turnover.py
├── costs.py
├── efficiency.py
│
├── decisions/
│   ├── buy.py
│   ├── exit.py
│   ├── no_action.py
│   └── horizons.py
│
├── scorecards/
│   ├── execution.py
│   ├── regime.py
│   ├── strategy.py
│   ├── engines.py
│   └── manager.py
│
├── confidence.py
├── bootstrap.py
├── rolling.py
├── trends.py
├── degradation.py
├── reconciliation.py
├── reason_codes.py
├── explainability.py
├── manifest.py
└── hashing.py
```

---

## 61. Reason codes

```text
ANALYTICS_FINALIZED
ANALYTICS_DEGRADED

REPORTING_BOR_MISSING
ANALYTICS_BOR_RECONCILIATION_FAILED

INSUFFICIENT_OBSERVATIONS
ANNUALIZATION_SAMPLE_INSUFFICIENT
BENCHMARK_COVERAGE_INSUFFICIENT
BENCHMARK_ALIGNMENT_INSUFFICIENT
RISK_FREE_SERIES_UNAVAILABLE

SHARPE_UNDEFINED_ZERO_VARIANCE
SORTINO_UNDEFINED_ZERO_DOWNSIDE
INFORMATION_RATIO_UNDEFINED_ZERO_TE
PROFIT_FACTOR_UNDEFINED_NO_LOSSES
RETURN_PER_TURNOVER_UNDEFINED_ZERO_TURNOVER

DRAWNDOWN_EPISODE_OPEN
DRAWDOWN_RECOVERY_CONFIRMED

RISK_ADJUSTED_PERFORMANCE_STRONG
RISK_ADJUSTED_PERFORMANCE_DEGRADING
DECISION_QUALITY_DEGRADING
EXECUTION_EFFICIENCY_DEGRADING
NO_ACTION_OPPORTUNITY_COST_RISING

DATA_BLOCKED_NOT_INVESTMENT_HIT
OPERATIONAL_BLOCKED_NOT_INVESTMENT_HIT
MARKET_CLOSED_EXCLUDED

OUTCOME_HORIZON_NOT_MATURED
FUTURE_OUTCOME_EXCLUDED

HARD_FAILURE_PRESENT
MANAGER_SCORE_PROVISIONAL
MANAGER_SCORE_STANDARD
MANAGER_SCORE_HIGH_CONFIDENCE

FUTURE_INFORMATION_GUARD
ANALYTICS_NAMESPACE_MISMATCH
RESTATED_SOURCE_ANALYTICS_REBUILT
```

---

## 62. Test plan: return and risk metrics

```text
A. Returns +1%, -1%, +2%
→ cumulative return uses compounding, not simple sum

B. Market-closed day between observations
→ excluded from N
→ no synthetic 0% return

C. Valid trading day with actual 0% portfolio return
→ preserve 0%

D. 19 observations
→ annualization provisional/blocked per policy

E. constant return series
→ volatility ≈ 0
→ infinite Sharpe forbidden

F. no negative downside observations
→ Sortino infinity forbidden

G. MaxDD path 100 → 120 → 90 → 120
→ peak/trough/recovery correctly resolved
```

---

## 63. Test plan: benchmark metrics

```text
H. portfolio and benchmark 100% aligned
→ TE / IR / beta calculations enabled

I. one benchmark trading day missing
→ no forward-fill
→ alignment ratio falls

J. alignment < policy threshold
→ benchmark analytics DEGRADED/BLOCKED

K. benchmark return identical to portfolio
→ TE ≈ 0
→ IR infinity forbidden

L. benchmark inception unavailable
→ since-inception active metrics N/A

M. reconstructed benchmark supplied to OFFICIAL namespace
→ BLOCKED
```

---

## 64. Test plan: drawdown and tail

```text
N. unrecovered drawdown at cutoff
→ recovery_date NULL

O. same MaxDD but longer underwater duration
→ Ulcer Index / duration metrics distinguish cases

P. 100 observations with defined 5% tail
→ historical ES uses worst tail observations

Q. future NAV observation included accidentally
→ FUTURE_INFORMATION_GUARD
```

---

## 65. Test plan: decision analytics

```text
R. BUY decision with complete 20D outcome
→ included in 20D hit rate

S. BUY decision with only 12D elapsed
→ excluded from 20D scorecard

T. RISK_BLOCKED then market -8%
→ loss-avoided observation permitted if Engine 49 valid counterfactual exists

U. DATA_BLOCKED then market -8%
→ cannot count as model hit

V. DATA_BLOCKED then market +10%
→ governance/safety opportunity cost tracked separately

W. MARKET_CLOSED NO_ACTION
→ excluded from investment hit-rate statistics

X. EXIT due hard risk followed by +20%
→ post-exit opportunity cost may be recorded
→ risk-rule compliance remains separately valid
```

---

## 66. Test plan: turnover and execution

```text
Y. turnover = 0
→ return-per-turnover infinity forbidden

Z. explicit fee + slippage + impact
→ total cost sum matches official execution/accounting

AA. opportunity cost present
→ not included in cash transaction cost

AB. partial fill 60/100
→ execution score uses actual fill data

AC. impossible fill from corrupted execution record
→ hard failure cannot be averaged into healthy score
```

---

## 67. Test plan: scorecards

```text
AD. excellent return, severe drawdown
→ capital preservation dimension penalized

AE. low return but strong downside protection
→ raw return low, risk/capital dimensions preserved

AF. manager score 90 + audit integrity failure
→ EXCELLENT state forbidden

AG. engine scorecard sample 5
→ HIGH_CONFIDENCE forbidden

AH. 60D metrics deteriorate for 3 consecutive windows
→ degradation event generated

AI. one bad daily observation only
→ persistent degradation not automatically generated
```

---

## 68. Test plan: reproducibility and temporal integrity

```text
AJ. same source/report/policy/window
→ identical metrics
→ identical scorecards
→ identical hashes

AK. Engine 58 report restated
→ new analytics run
→ old analytics immutable

AL. current benchmark series inserted into past analytics
→ BLOCKED

AM. current decision outcome inserted before horizon matured
→ BLOCKED

AN. RESEARCH analytics mixed into OFFICIAL manager score
→ BLOCKED
```

---

## 69. Critical invariants

```text
Official NAV modification by Engine 59 = 0
Official benchmark history fabrication = 0

Market-closed day converted to 0% return = 0
Missing benchmark converted to 0% = 0

Future return/outcome used in prior analytics = 0
Unmatured outcome used in horizon scorecard = 0

Infinite Sharpe from zero variance = 0
Infinite Information Ratio from zero TE = 0
Infinite return/turnover from zero turnover = 0

DATA_BLOCKED counted as investment prediction hit = 0
MARKET_CLOSED counted as NO_ACTION investment hit = 0

Opportunity cost mixed into realized cash P&L = 0
Reconstructed analytics mixed into official analytics = 0

Hard safety/audit failure averaged away by high performance score = 0

Historical analytics overwrite = 0
Historical scorecard overwrite = 0

Same finalized sources + same policy + same window
→ same metrics
→ same manager score
→ same analytics hash
```

---

## 70. Example ADE daily-to-manager path

Suppose official Engine 58 observations over a mature window show:

```text
ADE cumulative return       +8.2%
KOSPI cumulative return     +6.0%
Annualized volatility       11.5%
Max Drawdown                -4.8%
Tracking Error               6.1%
Turnover                    85%
Execution cost drag         -0.7%
```

Engine 59 may derive:

```text
Sharpe                       0.92
Sortino                      1.35
Information Ratio           0.58
Up Capture                    82%
Down Capture                  45%
```

Interpretation:

```text
ADE did not capture all upside,
but limited downside substantially.

Risk-adjusted and capture efficiency
may therefore be stronger than raw return alone suggests.
```

This analytical interpretation must still carry observation count, benchmark coverage and confidence state.

---

## 71. Example NO_ACTION analytics

Suppose during 20 RISK_BLOCKED decisions:

```text
8 cases  → market/candidate fell materially
7 cases  → roughly neutral
5 cases  → candidate rallied materially
```

Engine 59 records both:

```text
risk-block downside protection
risk-block opportunity cost
```

It does not label all 8 defensive observations as investment alpha and does not label all 5 rallies as risk-engine errors.

Decision quality requires the point-in-time context and Engine 49 attribution.

---

## 72. Integration with Engine 50 and Engine 48

Engine 59 may detect:

```text
20D Rank IC declining
NO_ACTION opportunity cost rising
RISK_OFF downside protection still strong
Execution cost drag worsening
```

It can publish:

```text
ANALYTICS_FINDING
```

for research intake.

Flow:

```text
59 analytics
→ 49/Research feedback intake
→ 50 controlled experiment
→ Challenger
→ 48 Governance
```

Forbidden:

```text
59 metric deterioration
→ automatic threshold change
```

---

## 73. Recommended implementation order

```text
1 immutable analytics domain models
2 DB migrations and metric registry
3 Engine 58 adapter / reconciliation
4 observation-window resolver
5 return / volatility / drawdown metrics
6 benchmark alignment
7 TE / IR / beta / alpha / capture
8 turnover / cost analytics
9 decision and NO_ACTION analytics
10 execution scorecard
11 strategy / engine scorecards
12 manager scorecard
13 confidence / minimum samples
14 rolling trend / degradation
15 manifests and hashing
16 full integration tests
```

---

## 74. Acceptance criteria for v1

Engine 59 v1 is considered complete only when:

```text
Official cumulative return exactly reconciles with Engine 58.
Market-closed and missing observations are handled without synthetic zeros.
Benchmark metrics fail closed when official benchmark coverage is missing.
Sharpe/Sortino/IR edge cases never create fake infinities.
Drawdown episodes reproduce the official NAV path.
NO_ACTION subtypes remain separated in all analytics.
DATA_BLOCKED is never counted as an investment-direction hit.
Outcome horizons are maturity-checked.
Manager Score includes explicit confidence/sample state.
Hard integrity failures cannot be averaged away.
Repeated runs are deterministic and hash-identical.
```

---

## 75. Resulting ADE architecture

```text
57 Decision Ledger
Why did the decision happen?
        ↓
58 Reporting Book-of-Record
What officially happened to portfolio and benchmark?
        ↓
59 Portfolio Analytics
How good was the result after accounting for
risk, drawdown, benchmark, cost and decision quality?
        ↓
49 / 50 / 48 feedback loop
What should be investigated, validated and governed next?
```

Engine 59 therefore closes the gap between an official performance record and a statistically disciplined assessment of ADE as an investment decision system.
