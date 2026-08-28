# 60. System Monitoring, KPI/SLO, Alerting & Control Tower Engine v1

## 1. Purpose

Engine 60 is ADE's operational control-tower layer. It continuously consumes finalized technical, data, risk, decision, execution and performance telemetry and converts that telemetry into reproducible KPI/SLO states, alerts, incidents, escalation decisions and safety recommendations.

It answers:

> Is ADE operating within its approved service, data-quality, decision-quality, risk, execution and performance tolerances right now — and if not, what is failing, how severe is it, who/what is affected, and should new risk be restricted, blocked or escalated to a kill-switch candidate?

Core principle:

```text
Monitoring is not decoration.
Monitoring is part of the decision-control system.

Unknown critical health != healthy.
A high portfolio return cannot hide a broken risk or data control.
A noisy alert must not become an automatic kill switch.

Same finalized telemetry
+ same monitoring policy
+ same evaluation cutoff
→ same KPI state
→ same SLO state
→ same alert / incident decision
→ same control-tower hash.
```

---

## 2. Position in ADE architecture

```text
54 Risk Governor
55 Operational Resilience
56 Runtime Orchestration
57 Decision Ledger
58 Reporting Book-of-Record
59 Portfolio Analytics
        ↓
┌────────────────────────────────────────────────────────┐
│ 60 Monitoring / KPI / SLO / Alerting Control Tower   │
├────────────────────────────────────────────────────────┤
│ Telemetry Registry                                     │
│ KPI Evaluation                                         │
│ SLI / SLO Evaluation                                   │
│ Error Budget                                           │
│ Trend / Drift Detection                                │
│ Alert Deduplication                                    │
│ Incident Correlation                                   │
│ Root-Cause Candidate Graph                             │
│ Escalation                                             │
│ Safety Recommendation                                 │
│ Kill-Switch Candidate Generation                      │
│ Control-Tower Snapshot                                 │
└────────────────────────────────────────────────────────┘
        ↓
54 Risk Governor HARD/SOFT input
55 Operational Resilience
48 Governance / Kill Switch approval
56 Runtime Coordinator
Human / automated reporting consumers
```

Engine 60 does not replace Engine 55. Engine 55 answers whether the operational platform is safe enough to operate. Engine 60 supervises the entire ADE estate, including investment, risk, performance and operational health, and converts deviations into control events.

---

## 3. Responsibility boundary

### Engine 60 does

- register monitorable ADE components, metrics and dependencies;
- consume immutable telemetry from Engines 38~59 and platform infrastructure;
- calculate KPI values and states;
- calculate Service Level Indicators (SLIs);
- evaluate Service Level Objectives (SLOs);
- calculate error-budget consumption and burn rates;
- distinguish point-in-time spikes from persistent degradation;
- perform rolling trend, drift and control-chart checks;
- deduplicate repeated alerts;
- correlate alerts into incidents;
- estimate likely root-cause candidates using dependency lineage;
- assign severity and blast radius;
- generate risk-control recommendations;
- generate kill-switch candidates for governance review;
- expose a deterministic control-tower snapshot;
- preserve alert, incident and recovery history immutably.

### Engine 60 does not

- modify official NAV or P&L;
- modify historical decisions;
- directly change Alpha or Signal weights;
- directly activate a new model;
- directly execute orders;
- directly flip a governance kill switch in v1;
- infer that missing telemetry is normal;
- use future telemetry in a past monitoring snapshot;
- hide a hard failure behind a composite average score.

---

## 4. Monitoring domains

All KPIs and SLOs belong to a monitoring domain.

```text
DATA
ENGINE_RUNTIME
ORCHESTRATION
DECISION
RISK
PORTFOLIO
EXECUTION
ACCOUNTING
PERFORMANCE
GOVERNANCE
AUDIT
INFRASTRUCTURE
```

Each domain has independent criticality and escalation policies.

Examples:

```text
DATA
- finalized market-data freshness
- corporate-action completeness
- source conflict rate

ENGINE_RUNTIME
- job success rate
- latency
- deterministic replay rate

DECISION
- decision finalization timeliness
- decision lineage completeness
- NO_ACTION subtype completeness

RISK
- risk-governor availability
- hard-limit breach count
- pre-trade reject correctness

EXECUTION
- fill reconciliation
- slippage model bias
- order API availability

ACCOUNTING
- NAV reconciliation
- cash reconciliation
- position reconciliation

PERFORMANCE
- drawdown
- tracking error
- decision-quality deterioration

AUDIT
- decision proof verification
- hash-chain integrity
```

---

## 5. Telemetry contract

All monitored observations use a common envelope.

```python
TelemetryObservation(
    observation_id,
    metric_id,
    component_id,
    domain,
    scope_type,
    scope_id,
    observed_at,
    known_at,
    value,
    unit,
    quality_state,
    source_snapshot_id,
    source_engine,
    source_version,
    tags,
    evidence_hash,
)
```

Temporal rule:

```text
known_at <= monitoring_cutoff
```

Future observations are rejected.

---

## 6. Metric registry

Each metric is versioned.

```text
metric_id
metric_version
name
domain
unit
aggregation
criticality
expected_frequency
freshness_limit
valid_min
valid_max
missing_data_policy
slo_eligible
owner_scope
```

Metric types:

```text
GAUGE
COUNTER
RATE
RATIO
DURATION
STATE
DISTRIBUTION
EVENT_COUNT
```

Examples:

```text
market_data_finalization_latency_seconds
engine_success_rate_20d
risk_governor_snapshot_age_seconds
nav_reconciliation_difference_krw
execution_fill_ratio
slippage_bias_bps_20d
portfolio_drawdown_pct
decision_audit_verified_ratio
benchmark_coverage_ratio
```

---

## 7. Criticality tiers

Use the same safety philosophy as Engine 55 but at control-tower scope.

```text
TIER_0 SAFETY CRITICAL
TIER_1 DECISION CRITICAL
TIER_2 QUALITY CRITICAL
TIER_3 OBSERVABILITY / OPTIONAL
```

Typical TIER_0 examples:

```text
Risk Governor availability
Accounting reconciliation
Position reconciliation
Broker order/cancel channel health
System clock integrity
Governance kill-switch state
Decision-freeze integrity
```

Rule:

```text
TIER_0 hard failure
cannot be averaged away by healthy TIER_1~3 metrics.
```

---

## 8. KPI states

Every KPI produces both a raw value and a state.

```text
UNKNOWN
HEALTHY
WATCH
DEGRADED
CRITICAL
INVALID
```

Example policy:

```text
market_data_finalization_latency

<= 5 min     HEALTHY
5~10 min     WATCH
10~30 min    DEGRADED
> 30 min     CRITICAL
missing      UNKNOWN
```

`UNKNOWN` on a critical KPI is never mapped to `HEALTHY`.

---

## 9. SLI / SLO model

An SLI is the measured service indicator.

Examples:

```text
Daily Decision Run Success
Risk Snapshot Availability
Decision Audit Completeness
Accounting Reconciliation Success
Execution Handoff Availability
```

An SLO stores:

```text
slo_id
slo_version
name
domain
scope
window
objective
target_value
comparison_operator
minimum_sample_count
criticality
error_budget_policy
```

Example:

```text
SLO: Risk Governor Availability
Window: 30D trading sessions
Target: >= 99.9%
```

---

## 10. Initial ADE SLO catalogue

Initial PAPER/LIVE_SHADOW targets are intentionally strict for safety-critical controls.

| SLO | Initial target |
|---|---:|
| TIER_0 Accounting reconciliation | 100% |
| TIER_0 Decision freeze integrity | 100% |
| TIER_0 Risk-governor availability | 100% on decision cycles |
| TIER_0 future-information violation | 0 events |
| Decision ledger completeness | 100% |
| Decision proof verification | 100% |
| Mandatory engine success | >= 99.5% |
| Critical market-data finalization | >= 99.5% within cutoff |
| Benchmark valid coverage | >= 99% when benchmark required |
| Execution/accounting fill reconciliation | 100% |
| Runtime orchestration deadline success | >= 99% |

These values are policy snapshots, not hardcoded constants.

---

## 11. Error budgets

For an SLO objective `S`:

```text
Allowed Failure Rate
= 1 - S
```

Example:

```text
SLO = 99.5%
Allowed failure = 0.5%
```

Error budget consumption:

```text
ErrorBudgetConsumption
= observed_bad_events / allowed_bad_events
```

States:

```text
< 50%       HEALTHY
50~80%      WATCH
80~100%     DEGRADED
> 100%      EXHAUSTED
```

Safety-critical zero-tolerance SLOs use event-based logic instead of division by zero.

```text
future_information_violation > 0
→ ZERO_TOLERANCE_SLO_BREACH
```

---

## 12. Burn-rate monitoring

Waiting until a 30-day SLO is already violated is too slow.

Calculate short and long burn rates.

```text
BurnRate
= observed_failure_rate / allowed_failure_rate
```

Typical windows:

```text
1H / 6H
1D / 7D
5 trading days / 20 trading days
```

Initial example:

```text
Burn >= 14.4 on short window
AND Burn >= 6 on longer window
→ PAGE / CRITICAL

Burn >= 6 on short window
AND Burn >= 3 on longer window
→ HIGH
```

Exact thresholds are policy controlled.

---

## 13. Investment-control KPIs

Engine 60 monitors investment controls without becoming an Alpha engine.

Examples:

```text
risk_headroom_pct
risk_utilization_pct
hard_limit_breach_count
passive_limit_breach_count
new_risk_block_rate
portfolio_drawdown_pct
stress_survival_score
strategy_cluster_concentration
market_regime_transition_frequency
```

A risk KPI can trigger alert/escalation, but Engine 60 does not itself rewrite portfolio weights.

---

## 14. Signal and decision-quality KPIs

From Engines 42, 49, 57 and 59:

```text
candidate_generation_rate
signal_confidence_calibration_error
false_positive_rate_20d
false_negative_rate_20d
no_action_rate
no_action_risk_blocked_rate
no_action_data_blocked_rate
decision_hit_rate_20d
decision_quality_score
decision_lineage_completeness
```

Important rule:

```text
High DATA_BLOCKED rate
is an operational/data-quality alert,
not an investment-performance failure.
```

---

## 15. Execution KPIs

```text
order_acceptance_rate
fill_ratio
partial_fill_rate
implementation_shortfall_bps
slippage_bias_bps
execution_latency_ms
cancel_failure_rate
broker_order_api_availability
```

Example:

```text
20D predicted slippage bias > +5 bps
AND sample >= 100
→ EXECUTION_MODEL_UNDERSTATES_COST
```

This may create a calibration/research alert rather than immediate trading halt unless severity or tail loss requires it.

---

## 16. Accounting and reconciliation KPIs

These are primarily TIER_0.

```text
nav_reconciliation_difference
cash_reconciliation_difference
position_reconciliation_difference
fill_to_position_reconciliation_rate
unresolved_break_count
break_age_seconds
```

Initial hard rule:

```text
material accounting mismatch
→ CRITICAL
→ NEW_RISK_BLOCK_RECOMMENDED
```

No composite score may override it.

---

## 17. Performance KPIs

From Engine 59:

```text
rolling_20d_active_return
rolling_60d_information_ratio
rolling_60d_sharpe
max_drawdown
ulcer_index
down_capture
turnover_efficiency
decision_quality_score
manager_score
```

Performance deterioration is normally not a TIER_0 operational incident.

It can create:

```text
MODEL_REVIEW
STRATEGY_REVIEW
RISK_BUDGET_REVIEW
```

but does not automatically trigger kill switch without corresponding hard-risk evidence.

---

## 18. Baselines and anomaly detection

Static thresholds alone are insufficient.

Supported baseline types:

```text
FIXED_POLICY_THRESHOLD
ROLLING_MEDIAN_MAD
EWMA
SEASONAL_BASELINE
REGIME_CONDITIONAL_BASELINE
```

Robust z-score:

```text
z_robust
= (x - median) / (1.4826 × MAD)
```

Example:

```text
execution latency normally 80~120ms
current 450ms
fixed SLA still 1s

→ not SLA violation
→ but anomaly WATCH/DEGRADED possible.
```

---

## 19. Control charts

For persistent drift, support:

```text
EWMA
CUSUM
rolling quantile
consecutive-threshold rule
```

Example:

```text
slippage residual
+2,+3,+4,+5,+6,+7 bps
```

may be more important than a single +9 bps spike.

Reason:

```text
PERSISTENT_EXECUTION_DRIFT
```

---

## 20. Alert lifecycle

Alerts have explicit states.

```text
OPEN
ACKNOWLEDGED
SUPPRESSED
ESCALATED
RESOLVED
CLOSED
```

An alert stores:

```text
alert_id
alert_rule_id
severity
first_seen_at
last_seen_at
occurrence_count
component
scope
metric
current_value
threshold
state
incident_id
reason_codes
```

Historical alerts are append-only event streams.

---

## 21. Alert severity

```text
INFO
WARNING
HIGH
CRITICAL
EMERGENCY
```

Semantics:

```text
INFO
informational event only

WARNING
watch condition; no automatic risk restriction

HIGH
material degradation; new-risk restriction may be recommended

CRITICAL
safety or decision-critical control failure; block recommendation

EMERGENCY
systemic safety condition; kill-switch candidate
```

---

## 22. Alert deduplication

Repeated observations of the same fault must not create thousands of independent alerts.

Deduplication key example:

```text
rule_id
+ component_id
+ scope_id
+ root_cause_signature
```

Repeated events increment:

```text
occurrence_count
last_seen_at
```

while preserving raw telemetry separately.

---

## 23. Suppression policy

Suppressing an alert does not suppress the underlying health state.

```text
Alert UI suppressed
!=
Risk input suppressed
```

Maintenance windows may suppress notification noise, but TIER_0 hard failures remain visible to Engines 54/55.

---

## 24. Incident correlation

Multiple alerts can share one root cause.

Example:

```text
Market Data API failure
  ↓
Market finalization late
41 Market Behavior skipped
42 Signal unavailable
56 Decision degraded
58 report delayed
```

Engine 60 should create one incident with multiple impacts rather than five unrelated incidents.

Correlation inputs:

```text
dependency graph
time proximity
shared source
shared error signature
shared snapshot lineage
```

---

## 25. Incident model

```text
incident_id
severity
status
opened_at
resolved_at
root_cause_state
root_cause_component
blast_radius
risk_impact
operational_mode_impact
kill_switch_candidate
primary_reason_code
```

Incident states:

```text
DETECTED
TRIAGED
MITIGATING
MONITORING_RECOVERY
RESOLVED
CLOSED
```

---

## 26. Root-cause candidate graph

Root cause is not always known immediately.

Store ranked candidates:

```text
candidate_component
confidence
supporting_alerts
dependency_distance
temporal_alignment
error_signature_match
```

Do not fabricate certainty.

```text
ROOT_CAUSE_UNKNOWN
```

is a valid state.

---

## 27. Blast radius

An incident must identify affected scopes.

```text
GLOBAL
MARKET
PORTFOLIO
STRATEGY
ENGINE
SECURITY
DATA_SOURCE
EXECUTION_CHANNEL
REPORTING_ONLY
```

Example:

```text
Broker order API failure
→ execution channel blast radius
→ BUY/ADD/REDUCE/EXIT may all be affected

Benchmark feed failure
→ benchmark analytics/reporting blast radius
→ trading may remain valid if benchmark is non-critical to current decision policy
```

---

## 28. Control recommendations

Engine 60 does not directly trade. It emits control recommendations.

```text
NO_CONTROL_CHANGE
WATCH_ONLY
RESTRICT_NEW_RISK
BLOCK_NEW_RISK
RISK_REDUCTION_ONLY
SAFE_HALT_RECOMMENDED
KILL_SWITCH_CANDIDATE
MODEL_REVIEW_REQUIRED
DATA_SOURCE_FAILOVER_REQUIRED
```

These recommendations are consumed by Engines 54, 55, 48 and 56 according to their authority.

---

## 29. Kill-switch candidate generation

Engine 60 can create a kill-switch candidate but cannot activate it automatically in v1.

Candidate triggers may include:

```text
future-information violation
unreconciled positions + active trading
Risk Governor unavailable
Decision freeze integrity failure
repeated impossible fills
system-clock integrity failure
critical audit hash failure
multiple correlated TIER_0 failures
```

Output:

```text
kill_switch_candidate_id
scope
recommended_switch_type
severity
evidence_bundle
created_at
```

Activation remains Engine 48 Governance authority.

---

## 30. Example severity resolution

```text
Signal hit rate down 15%
→ WARNING / MODEL_REVIEW

Execution slippage bias +8bps for 20D
→ HIGH / CALIBRATION_REVIEW

Market data 20min late
→ HIGH / NEW_RISK_RESTRICT

Accounting reconciliation failure
→ CRITICAL / NEW_RISK_BLOCK

Risk Governor unavailable + broker trading active
→ EMERGENCY / KILL_SWITCH_CANDIDATE
```

---

## 31. Recovery confirmation

Alerts/incidents do not resolve on the first healthy tick.

```text
FAST DETECT
SLOW RECOVER
```

Example policy:

```text
HIGH
→ 2 consecutive healthy checks

CRITICAL
→ 3 healthy checks
+ required reconciliation pass

EMERGENCY
→ explicit governance clearance
```

This avoids flapping.

---

## 32. Flapping detection

If a metric repeatedly crosses a threshold:

```text
HEALTHY → CRITICAL → HEALTHY → CRITICAL
```

create:

```text
ALERT_FLAPPING_DETECTED
```

and increase hysteresis / incident persistence according to policy.

---

## 33. Control-tower global state

The entire ADE platform receives one summary state.

```text
GREEN
YELLOW
ORANGE
RED
BLACK
```

Suggested semantics:

```text
GREEN
all critical systems healthy

YELLOW
watch / localized degradation

ORANGE
material degradation; new-risk restriction likely

RED
critical control failure; new risk blocked

BLACK
systemic safety failure; safe halt / kill-switch candidate
```

This is a summary only. Detailed binding reasons must remain available.

---

## 34. Global state resolution

Never calculate the global state by simple averaging.

Priority:

```text
EMERGENCY incident
> CRITICAL TIER_0
> HIGH TIER_0/TIER_1
> error-budget exhaustion
> persistent degradation
> performance-quality warnings
```

Example:

```text
99 healthy KPIs
1 TIER_0 accounting failure
→ RED, not GREEN.
```

---

## 35. Control-tower snapshot

```text
snapshot_id
portfolio_id
evaluation_time
monitoring_policy_id
monitoring_policy_hash

global_state
operational_mode

open_info_alerts
open_warning_alerts
open_high_alerts
open_critical_alerts
open_emergency_alerts

open_incidents
critical_incidents

slo_count
slo_breached_count
error_budget_exhausted_count

new_risk_recommendation
kill_switch_candidate_count

binding_domain
binding_component
binding_reason_code

source_manifest_hash
snapshot_hash
```

---

## 36. Database design

Core tables:

```text
monitoring_policies
monitoring_policy_versions

monitoring_component_registry
monitoring_metric_definitions
monitoring_slo_definitions
monitoring_alert_rules

monitoring_telemetry_observations
monitoring_metric_snapshots
monitoring_sli_observations
monitoring_slo_snapshots
monitoring_error_budget_snapshots

monitoring_alerts
monitoring_alert_events
monitoring_alert_suppressions

monitoring_incidents
monitoring_incident_alert_links
monitoring_root_cause_candidates
monitoring_incident_impacts

monitoring_control_recommendations
monitoring_kill_switch_candidates

monitoring_control_tower_snapshots
monitoring_reason_events
monitoring_manifests
```

---

## 37. `monitoring_metric_definitions`

```text
metric_id
metric_version
name
domain
metric_type
unit
component_type
criticality
aggregation
expected_frequency_seconds
freshness_limit_seconds
missing_data_policy
valid_min
valid_max
created_at
retired_at
definition_hash
```

---

## 38. `monitoring_slo_snapshots`

```text
snapshot_id
slo_id
scope_type
scope_id
window_start
window_end

objective
good_events
total_events
sli_value

allowed_bad_events
observed_bad_events
error_budget_remaining
burn_rate_short
burn_rate_long

slo_state
reason_codes
snapshot_hash
```

---

## 39. `monitoring_alerts`

```text
alert_id
alert_rule_id
component_id
scope_type
scope_id
severity
state
first_seen_at
last_seen_at
occurrence_count
current_value
threshold_value
incident_id
primary_reason_code
alert_hash
```

---

## 40. `monitoring_incidents`

```text
incident_id
severity
status
opened_at
last_updated_at
resolved_at
root_cause_state
root_cause_component_id
blast_radius
risk_impact
operational_impact
kill_switch_candidate
primary_reason_code
incident_hash
```

---

## 41. Retention model

Raw high-frequency telemetry may use tiered retention.

```text
Raw high-frequency telemetry
→ short/medium retention

Daily aggregates
SLO snapshots
Alerts
Incidents
Control recommendations
Decision-linked telemetry
→ long-term immutable retention
```

Any telemetry used as evidence for a finalized decision, incident or audit bundle must be retained at least as long as that artifact.

---

## 42. Algorithms: metric evaluation

```python
def evaluate_metric(obs, definition, baseline, policy):
    validate_temporal_integrity(obs)
    validate_schema(obs, definition)

    if obs is None:
        return state_for_missing(definition.missing_data_policy)

    if not within_valid_range(obs.value, definition):
        return MetricState.INVALID

    static_state = evaluate_static_thresholds(obs, policy)
    anomaly_state = evaluate_anomaly(obs, baseline, policy)

    return most_severe(static_state, anomaly_state)
```

---

## 43. Algorithms: SLO evaluation

```python
def evaluate_slo(observations, slo, cutoff):
    valid = filter_known_at(observations, cutoff)
    valid = filter_window(valid, slo.window)

    if len(valid) < slo.minimum_sample_count:
        return SLOResult(state="INSUFFICIENT_SAMPLE")

    good = count_good_events(valid, slo)
    total = len(valid)
    sli = good / total

    budget = calculate_error_budget(sli, total, slo)
    burn = calculate_multiwindow_burn(valid, slo)

    return resolve_slo_state(sli, budget, burn, slo)
```

---

## 44. Algorithms: alert evaluation

```python
def evaluate_alert(metric_snapshot, rule, previous_alert):
    triggered = rule.evaluate(metric_snapshot)

    if not triggered:
        return evaluate_recovery(previous_alert, metric_snapshot, rule)

    key = build_dedup_key(rule, metric_snapshot)

    if previous_alert and previous_alert.dedup_key == key:
        return append_occurrence(previous_alert, metric_snapshot)

    return open_new_alert(rule, metric_snapshot)
```

---

## 45. Algorithms: incident correlation

```python
def correlate_incidents(alerts, dependency_graph, policy):
    clusters = deterministic_cluster(
        alerts,
        keys=[
            "shared_source",
            "dependency_path",
            "error_signature",
            "time_window",
        ],
    )

    return [
        build_incident(cluster, dependency_graph, policy)
        for cluster in clusters
    ]
```

Clustering must be deterministic. Random clustering without a fixed policy/seed is prohibited for official incident lineage.

---

## 46. Algorithms: safety recommendation

```python
def resolve_control_recommendation(snapshot):
    if snapshot.has_emergency:
        return "KILL_SWITCH_CANDIDATE"

    if snapshot.has_tier0_critical:
        return "BLOCK_NEW_RISK"

    if snapshot.has_high_safety_degradation:
        return "RESTRICT_NEW_RISK"

    if snapshot.error_budget_exhausted_critical:
        return "RESTRICT_NEW_RISK"

    return "NO_CONTROL_CHANGE"
```

Actual permissions remain authority of Engines 54/55/48.

---

## 47. Code structure

```text
control_tower/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── registry.py
├── repository.py
├── engine.py
│
├── adapters/
│   ├── data_health.py
│   ├── runtime.py
│   ├── orchestration.py
│   ├── risk.py
│   ├── portfolio.py
│   ├── execution.py
│   ├── accounting.py
│   ├── governance.py
│   ├── audit.py
│   └── analytics.py
│
├── telemetry.py
├── freshness.py
├── quality.py
├── baselines.py
├── anomalies.py
├── control_charts.py
│
├── sli.py
├── slo.py
├── error_budget.py
├── burn_rate.py
│
├── alerts/
│   ├── rules.py
│   ├── evaluator.py
│   ├── dedup.py
│   ├── suppression.py
│   ├── flapping.py
│   └── recovery.py
│
├── incidents/
│   ├── correlation.py
│   ├── root_cause.py
│   ├── blast_radius.py
│   ├── severity.py
│   └── lifecycle.py
│
├── controls/
│   ├── recommendations.py
│   ├── risk_restriction.py
│   └── kill_switch_candidates.py
│
├── dashboard_snapshot.py
├── reason_codes.py
├── explainability.py
├── manifest.py
└── hashing.py
```

---

## 48. Reason codes

```text
MONITORING_HEALTHY
MONITORING_DEGRADED
CONTROL_TOWER_ORANGE
CONTROL_TOWER_RED
CONTROL_TOWER_BLACK

CRITICAL_TELEMETRY_MISSING
TELEMETRY_STALE
TELEMETRY_INVALID

SLO_WARNING
SLO_BREACHED
ERROR_BUDGET_LOW
ERROR_BUDGET_EXHAUSTED
ERROR_BUDGET_BURN_HIGH
ZERO_TOLERANCE_SLO_BREACH

METRIC_ANOMALY_DETECTED
PERSISTENT_METRIC_DRIFT
ALERT_FLAPPING_DETECTED

ACCOUNTING_RECONCILIATION_ALERT
RISK_GOVERNOR_UNAVAILABLE
DECISION_FREEZE_INTEGRITY_ALERT
FUTURE_INFORMATION_ALERT
AUDIT_INTEGRITY_ALERT
EXECUTION_RECONCILIATION_ALERT

NEW_RISK_RESTRICTION_RECOMMENDED
NEW_RISK_BLOCK_RECOMMENDED
SAFE_HALT_RECOMMENDED
KILL_SWITCH_CANDIDATE_CREATED

ROOT_CAUSE_UNKNOWN
ROOT_CAUSE_CANDIDATE_IDENTIFIED
INCIDENT_BLAST_RADIUS_GLOBAL

RECOVERY_CONFIRMATION_PENDING
INCIDENT_RECOVERY_CONFIRMED
FUTURE_INFORMATION_GUARD
```

---

## 49. Explainability output

A control event must answer:

```text
What failed?
Where?
When did it start?
How severe is it?
What objective or threshold was violated?
Is the problem local or systemic?
What downstream engines/decisions are affected?
What control action is recommended?
What evidence supports that recommendation?
What evidence is missing?
```

Example:

```text
CONTROL TOWER
State             RED

Incident
Accounting Reconciliation Failure

Severity          CRITICAL
Started           15:58:21
Affected          Portfolio ADE-PAPER-01

Observed
ADE cash          4,000,000
Broker cash       3,200,000
Difference          800,000

Binding Rule
TIER_0_ACCOUNTING_RECONCILIATION

Recommendation
BLOCK_NEW_RISK

BUY               BLOCK recommended
ADD               BLOCK recommended
REDUCE / EXIT      conditional on position reconciliation
```

---

## 50. Test plan — metric and SLO

```text
A. Healthy 30D SLO
99.9% target, all successful
→ HEALTHY

B. SLO objective breached
→ SLO_BREACHED

C. SLO still passing but short burn rate extreme
→ early HIGH alert

D. Zero-tolerance future-information event = 1
→ immediate CRITICAL/EMERGENCY

E. Critical metric missing
→ UNKNOWN/CRITICAL policy
→ never HEALTHY

F. 100 healthy metrics + one TIER_0 failure
→ global GREEN prohibited
```

---

## 51. Test plan — alerts and incidents

```text
G. Same alert repeats 100 times
→ one alert + occurrence_count 100

H. Alert clears for one tick after CRITICAL
→ immediate resolve prohibited

I. Flapping threshold
→ ALERT_FLAPPING_DETECTED

J. Market-data outage causes five downstream failures
→ one correlated root incident

K. Root cause uncertain
→ ROOT_CAUSE_UNKNOWN allowed

L. TIER_3 dashboard failure
→ no trading kill recommendation
```

---

## 52. Test plan — risk and controls

```text
M. Accounting reconciliation failure
→ BLOCK_NEW_RISK recommendation

N. Risk Governor unavailable
→ CRITICAL
→ KILL_SWITCH candidate possible by policy

O. Signal performance weak only
→ MODEL_REVIEW
→ no immediate kill switch

P. Slippage bias deteriorates gradually
→ drift alert before hard SLA breach

Q. Performance manager score falls below 50
→ review alert
→ not automatic safe halt

R. Multiple independent TIER_0 failures
→ EMERGENCY / BLACK candidate
```

---

## 53. Test plan — temporal and replay

```text
S. Telemetry known after monitoring cutoff
→ past snapshot usage 0

T. Current SLO policy used in historical replay
→ BLOCKED unless explicitly research namespace

U. Late telemetry corrects prior raw source
→ old control-tower snapshot immutable
→ new snapshot/version only

V. Same telemetry + policy + cutoff
→ same KPI states
→ same SLO results
→ same alerts
→ same incidents
→ same hash
```

---

## 54. Test plan — integration with Engine 54/55/48/56

```text
W. Engine 60 recommends BLOCK_NEW_RISK
→ Engine 54 receives constraint input

X. Engine 60 CRITICAL operational incident
→ Engine 55 receives degradation input

Y. Kill-switch candidate
→ Engine 48 approval path required
→ Engine 60 cannot activate directly

Z. Decision run occurs while control state RED
→ Engine 56 records control-tower snapshot in run manifest
```

---

## 55. Core invariants

```text
Future telemetry in past control state = 0

Critical UNKNOWN mapped to HEALTHY = 0

TIER_0 hard failure hidden by average score = 0

Zero-tolerance violation ignored by error-budget average = 0

Alert suppression removing underlying risk state = 0

Repeated same event generating unbounded independent alerts = 0

Single healthy tick resolving CRITICAL incident = 0

Performance weakness alone directly activates kill switch = 0

Engine 60 directly executes trade = 0
Engine 60 directly changes Alpha = 0
Engine 60 directly activates ACTIVE model = 0
Engine 60 directly activates kill switch in v1 = 0

Historical alert mutation = 0
Historical incident mutation = 0
Historical SLO snapshot mutation = 0

Same finalized telemetry
+ same monitoring policy
+ same cutoff
→ same global state
→ same control recommendation
→ same hash
```

---

## 56. Example end-to-end control flow

```text
15:50
Market data finalization delayed

15:55
KPI market_data_latency = DEGRADED
Alert WARNING

16:05
Critical cutoff exceeded
KPI = CRITICAL
SLO burn high

16:06
Incident opened
Root cause candidate = primary market-data vendor
Blast radius = DATA / SIGNAL / DECISION

16:07
Control recommendation
BLOCK_NEW_RISK

16:08
54 Risk Governor receives HARD input
55 Operational Resilience moves to NEW_RISK_BLOCKED

16:10
56 Decision Runtime can still finalize
NO_ACTION / DATA_BLOCKED
with control-tower evidence

16:20
Backup source recovers

16:21
First healthy check
RECOVERY_CONFIRMATION_PENDING

16:30
Required consecutive checks complete
Incident MONITORING_RECOVERY → RESOLVED

Next valid run
new risk can be reconsidered by 54/55.
```

---

## 57. Relationship to Engines 54~59

```text
54 Risk Governor
"Can this financial risk be accepted?"

55 Operational Resilience
"Is the system safe enough to operate?"

56 Runtime Coordinator
"Did the whole decision cycle execute correctly?"

57 Decision Audit
"Why exactly was this decision made?"

58 Reporting BoR
"What officially happened?"

59 Analytics
"How good was the result?"

60 Control Tower
"Is the whole ADE system currently operating within approved tolerances,
and what must be escalated when it is not?"
```

Engine 60 closes the supervisory loop around ADE rather than creating another investment signal.

---

## 58. Implementation sequence

Recommended implementation order:

```text
1. immutable metric / component registry
2. telemetry contract and repository
3. freshness + missing-data semantics
4. KPI threshold evaluator
5. SLI / SLO evaluator
6. error-budget + burn-rate engine
7. anomaly / drift evaluator
8. alert lifecycle + dedup
9. incident correlation + blast radius
10. safety recommendation resolver
11. kill-switch candidate contract
12. Engine 54/55/48/56 adapters
13. control-tower snapshot + manifest/hash
14. deterministic replay tests
15. chaos / failure-injection integration tests
```

---

## 59. v1 acceptance criteria

Engine 60 v1 is not complete until all of the following are true:

```text
- every TIER_0 component has at least one explicit KPI and SLO;
- missing critical telemetry has deterministic semantics;
- alert deduplication is deterministic;
- incident correlation preserves source lineage;
- error-budget burn can trigger pre-breach warning;
- critical recovery requires confirmation;
- kill-switch candidates require Engine 48 governance;
- Engine 54 consumes control recommendations;
- Engine 56 stores the control-tower snapshot in run lineage;
- historical monitoring replay is reproducible;
- no monitoring output can silently rewrite official decision/accounting history.
```

---

## 60. Next architectural step

With Engine 60, ADE now has a supervisory operating layer:

```text
Decision
→ Risk
→ Execution
→ Accounting
→ Reporting
→ Analytics
→ Monitoring
→ Incident / Control
→ Risk / Operations / Governance
```

The natural next engine is:

```text
61. Configuration, Policy & Parameter Registry / Change-Control Engine
```

Its role should be to centralize every threshold, weight, SLO, risk limit, cutoff, feature definition and runtime parameter currently distributed across ADE engines; provide effective-dating, schema validation, dependency impact analysis, approval workflow, environment promotion, rollback and historical as-of resolution; and guarantee that no production decision depends on an unversioned or silently modified configuration value.
