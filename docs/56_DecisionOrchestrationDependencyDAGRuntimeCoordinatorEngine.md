# 56. Decision Orchestration, Dependency DAG & End-to-End Runtime Coordinator Engine v1

## 1. Purpose

Engine 56 is the end-to-end runtime coordination layer of ADE. It determines which engines must run, in what order, against which point-in-time snapshots, before which cutoffs, under which dependency conditions, and with which retry/replay semantics.

It answers:

> Given a decision cycle, which exact data and engine outputs are allowed to participate in the final ADE decision, and how do we prove that the full run is temporally valid and reproducible?

Engine 56 does not create alpha, choose securities, set risk limits, or execute orders. It orchestrates the engines that do those jobs.

Core principles:

```text
A correct engine run in the wrong order is still an incorrect ADE decision.

A late result is not allowed to become an on-time result retroactively.

A partially successful pipeline is not automatically a valid decision pipeline.

Same run specification + same frozen inputs + same code/policy bindings
→ same orchestration outcome.
```

---

## 2. Position in ADE architecture

```text
Trading Calendar / Scheduler / Clock
                ↓
        Decision Cycle Trigger
                ↓
┌──────────────────────────────────────────────┐
│ 56 Decision Orchestration & Runtime         │
├──────────────────────────────────────────────┤
│ Run Specification                            │
│ Dependency DAG                               │
│ Cutoff / Deadline Control                    │
│ Snapshot Freeze                              │
│ Engine Scheduling                            │
│ Failure Propagation                          │
│ Retry / Resume                               │
│ Partial Run Resolution                       │
│ Decision Freeze                              │
│ Replay                                       │
│ End-to-End Run Manifest                      │
└──────────────────────────────────────────────┘
       ↓        ↓        ↓        ↓
     38~55 ADE analytical/risk/control engines
                ↓
        Final Decision Snapshot
                ↓
         23 / 24 / 46 Execution path
```

Engine 55 determines whether components are healthy. Engine 54 resolves financial and operational risk permissions. Engine 56 determines whether the required dependency chain was executed correctly and on time.

---

## 3. Responsibility boundary

### 56 does

- define decision-cycle run types;
- load the authoritative engine dependency graph;
- resolve active code/policy/model bindings as of the cycle time;
- freeze point-in-time input snapshots;
- assign deadlines and cutoffs to nodes;
- schedule dependency-ready engine runs;
- enforce prerequisite completion;
- prevent future or late information from contaminating a frozen decision;
- propagate failure/degradation states through the DAG;
- retry only retryable failures;
- resume interrupted runs safely;
- determine whether a partial pipeline may finalize;
- freeze the final decision input set;
- create immutable end-to-end manifests;
- support deterministic historical replay;
- provide run-lineage evidence to Governance, Explainability, Reporting, and Audit.

### 56 does not

- repair bad market data by guessing;
- override Engine 55 health restrictions;
- override Engine 54 risk restrictions;
- modify Alpha scores;
- make BUY/SELL decisions itself;
- execute broker orders;
- move late results into an already frozen decision;
- silently change active policy/model versions mid-run.

---

## 4. Decision cycle types

ADE supports explicit run types.

```text
EOD_DECISION
INTRADAY_MONITOR
PREOPEN_EXECUTION_CHECK
POSTTRADE_RECONCILIATION
RESEARCH_REPLAY
HISTORICAL_REPLAY
RECOVERY_RESUME
EMERGENCY_RISK_REDUCTION
```

Each run type has a different DAG and different permission set.

Example:

```text
EOD_DECISION
→ full analytical + risk pipeline

PREOPEN_EXECUTION_CHECK
→ no recomputation of prior EOD alpha by default
→ refresh execution/risk/health inputs only

EMERGENCY_RISK_REDUCTION
→ skip alpha-generating branches if necessary
→ preserve risk reduction path
```

---

## 5. Run specification

Every run begins with an immutable `RunSpecification`.

```python
RunSpecification(
    run_id,
    run_type,
    portfolio_id,
    market,
    trading_date,
    evaluation_time,
    decision_cutoff,
    execution_earliest_time,
    dag_version,
    orchestration_policy_id,
    orchestration_policy_hash,
    governance_binding_snapshot_id,
    created_at,
)
```

The run specification is frozen before any analytical node is executed.

---

## 6. Dependency DAG

The runtime graph is explicit and versioned.

Illustrative EOD chain:

```text
Calendar / Clock
      ↓
Market Data Finalization
      ├──────────────┐
      ↓              ↓
Corporate Actions   Benchmark
      ↓              ↓
Instrument / Universe
      ↓
38 Fundamental PIT
      ↓
39 Valuation / Factor
      ├──────────────┐
      ↓              ↓
40 Expectations     41 Market Behavior
      └──────┬───────┘
             ↓
        20 Market Regime
             ↓
        43 Regime Adaptation
             ↓
        42 Signal Integration
             ↓
        51 Strategy Ensemble
             ↓
        52 Stress Testing
             ↓
        53 Capital Preservation
             ↓
        55 Operational Health
             ↓
        54 Risk Governor
             ↓
        44 Portfolio Construction
             ↓
        45 Trade Lifecycle
             ↓
        23 Decision / Position Sizing
             ↓
        Decision Freeze
             ↓
        34 Cost + 46 Execution Simulation
```

The real graph may contain parallel branches. The DAG controls readiness, not file-number order.

---

## 7. DAG node contract

Every node has a common orchestration contract.

```python
DagNodeDefinition(
    node_id,
    engine_id,
    engine_version,
    required_dependencies,
    optional_dependencies,
    criticality,
    run_condition,
    timeout_seconds,
    retry_policy_id,
    freshness_contract_id,
    cutoff_class,
    output_contract_version,
)
```

Node criticality:

```text
MANDATORY
CONDITIONALLY_MANDATORY
OPTIONAL
OBSERVABILITY_ONLY
```

A missing `MANDATORY` node prevents normal finalization.

---

## 8. Dependency edge contract

Edges are also versioned.

```python
DagEdge(
    upstream_node,
    downstream_node,
    dependency_type,
    required_output_type,
    temporal_rule,
    failure_propagation_rule,
)
```

Dependency types:

```text
HARD
SOFT
ORDERING_ONLY
DATA_LINEAGE
CONTROL
```

Example:

```text
Market Data Finalization
  --HARD--> Market Behavior

Dashboard Renderer
  --SOFT--> Reporting
```

---

## 9. Cutoff model

Every EOD decision cycle contains explicit timing boundaries.

```text
market_close_time
market_data_finalization_deadline
fundamental_cutoff
expectations_cutoff
signal_cutoff
decision_cutoff
execution_earliest_time
```

Example policy:

```text
15:30 KRX close
15:40 primary EOD data expected
15:50 market snapshot finalization cutoff
16:00 analytical input freeze
16:15 signal cutoff
16:20 risk cutoff
16:25 decision freeze
next valid session = earliest execution
```

Times are examples and remain policy-driven.

---

## 10. Late data rule

If information becomes known after the relevant cutoff, it cannot be inserted into the frozen decision.

```text
known_at <= node_cutoff
```

Otherwise:

```text
LATE_INFORMATION_EXCLUDED
```

Example:

```text
16:24 Decision inputs freeze
16:27 corporate announcement arrives

→ not part of 16:24 decision
→ becomes eligible for a later run
```

This applies even if the late information would have improved the decision.

---

## 11. Snapshot freeze layers

56 defines several freeze points.

```text
INPUT_FREEZE
FEATURE_FREEZE
SIGNAL_FREEZE
RISK_FREEZE
DECISION_FREEZE
EXECUTION_CONTEXT_FREEZE
```

Each freeze records:

```text
freeze_id
freeze_type
freeze_time
included_snapshot_ids
excluded_late_snapshot_ids
binding_versions
manifest_hash
```

A downstream engine may read only snapshots admitted into the relevant freeze set.

---

## 12. Point-in-time binding resolution

Code, policy, strategy, and model bindings are resolved at run creation.

```text
resolve ACTIVE artifact
as_of run.evaluation_time
```

After binding freeze:

```text
mid-run model promotion
→ current run unaffected
→ next eligible run may use new version
```

This prevents mixed-version decisions.

---

## 13. Engine readiness

A node becomes runnable only when:

```text
all HARD dependencies complete
required frozen inputs available
health permits execution
cutoff not violated
node not already finalized
```

State:

```text
WAITING
READY
RUNNING
SUCCEEDED
DEGRADED
FAILED
TIMED_OUT
SKIPPED_DEPENDENCY
CANCELLED
FINALIZED
```

---

## 14. Parallel scheduling

Independent branches should execute concurrently.

Example:

```text
39 Factor complete
        ↓
┌─────────────────┬─────────────────┐
40 Expectations   41 Market Behavior
└─────────────────┴─────────────────┘
        ↓ join
42 Signal
```

The join waits for mandatory upstream branches but does not wait for irrelevant optional nodes.

---

## 15. Deterministic scheduler ordering

When multiple nodes become READY simultaneously, execution ordering must be deterministic where ordering can affect resource or state behavior.

Tie-break:

```text
1 criticality
2 dependency depth
3 configured priority
4 engine_id
5 node_id
```

No random scheduler order may change final logical output.

---

## 16. Failure classes

Failures are classified before retry.

```text
TRANSIENT
PERMANENT
DATA_QUALITY
TEMPORAL_VIOLATION
DEPENDENCY_FAILURE
POLICY_VIOLATION
RESOURCE_EXHAUSTION
CODE_ERROR
UNKNOWN
```

Examples:

```text
HTTP 503              → TRANSIENT
Database lock timeout → TRANSIENT
Schema mismatch       → PERMANENT/POLICY
Future information    → TEMPORAL_VIOLATION
Missing finalized NAV → DATA_QUALITY
```

---

## 17. Retry policy

Only retryable failures are retried.

```text
TRANSIENT
RESOURCE_EXHAUSTION (bounded)
```

Example policy:

```text
max_attempts = 3
backoff = exponential
jitter = deterministic seed or bounded configured value
retry_deadline <= node cutoff
```

Never blind-retry:

```text
TEMPORAL_VIOLATION
FUTURE_INFORMATION
SCHEMA_MISMATCH
POLICY_VIOLATION
AUTHORIZATION_FAILURE
```

---

## 18. Retry must not cross the cutoff invisibly

Suppose a node fails at 16:14 and its cutoff is 16:15.

If retry completes at 16:16:

```text
technical result = available
run-admissible result = false
```

Reason:

```text
RESULT_COMPLETED_AFTER_CUTOFF
```

The result may be stored but not admitted into that frozen decision.

---

## 19. Failure propagation

A failed node affects descendants according to dependency type.

```text
HARD dependency failure
→ downstream SKIPPED_DEPENDENCY

SOFT dependency failure
→ downstream may run DEGRADED

CONTROL block
→ downstream execution restricted
```

Root-cause lineage is preserved.

Example:

```text
Market Data Finalization FAILED
        ↓
41 Market Behavior SKIPPED_DEPENDENCY
        ↓
42 Signal cannot finalize
        ↓
54 Risk Governor new risk blocked
```

Do not create three independent incidents when there is one root cause.

---

## 20. Safe partial-run policy

Some run types may finalize with optional branches missing.

Example:

```text
Optional news enrichment failed
but
all mandatory PIT/Signal/Risk nodes valid
→ EOD decision may finalize DEGRADED
```

But:

```text
Accounting unreconciled
or
Risk Governor missing
→ normal decision cannot finalize
```

Finalization states:

```text
FULLY_VALID
VALID_DEGRADED
NO_NEW_RISK_VALID
RISK_REDUCTION_ONLY_VALID
INVALID
ABORTED
```

---

## 21. Decision freeze

Once the decision input set is finalized:

```text
DECISION_FREEZE
```

records all upstream snapshots used.

After this point:

```text
late feature update
late model run
late data correction
```

cannot mutate the decision.

A new run must be created if policy permits reevaluation.

---

## 22. Re-evaluation policy

Not every new fact creates a new decision run.

Eligible re-evaluation triggers may include:

```text
MATERIAL_CORPORATE_EVENT
CRITICAL_MARKET_EVENT
GOVERNANCE_OVERRIDE
RISK_EMERGENCY
ACCOUNTING_CORRECTION
MANUAL_RESEARCH_REPLAY
```

Each trigger creates a new run id and new manifest.

Never overwrite the original run.

---

## 23. Resume semantics

After process interruption, 56 resumes from immutable completed nodes.

```text
SUCCEEDED + matching input hash + matching code/policy binding
→ reuse

RUNNING at crash
→ mark INTERRUPTED
→ rerun only if idempotent/retry-safe
```

Completed node output is never recomputed merely because the coordinator restarted.

---

## 24. Idempotency

Every node run receives an idempotency key.

```text
idempotency_key
=
hash(
  parent_run_id,
  node_id,
  input_manifest_hash,
  engine_version,
  policy_hash
)
```

Same key cannot produce two independently accepted finalized outputs.

---

## 25. Re-run vs replay

Distinguish:

```text
RETRY
same run, same frozen inputs, transient failure recovery

RERUN
new run using current eligible inputs

REPLAY
historical reconstruction using historical bindings and PIT inputs
```

These must not share semantics.

---

## 26. Historical replay

Historical replay resolves:

```text
historical calendar
historical active artifact bindings
historical policy versions
historical universe
historical data known_at
historical operational constraints when available
```

It does not use today's active configuration.

```text
CURRENT_ACTIVE_CONFIG_IN_HISTORICAL_REPLAY
→ BLOCKED
```

unless the run is explicitly a research counterfactual.

---

## 27. Research replay isolation

Research runs are isolated from production decision state.

```text
RESEARCH_REPLAY
→ may use challenger artifacts
→ cannot write LIVE/PAPER active decision state
→ cannot create broker-routable orders
```

Research manifests carry:

```text
research_only = true
```

---

## 28. Runtime environment separation

Explicit environments:

```text
RESEARCH
BACKTEST
PAPER
LIVE_SHADOW
LIVE
```

Bindings, permissions, and persistence targets are environment-scoped.

```text
PAPER run
→ cannot mutate LIVE state
```

---

## 29. Decision eligibility gate

Before final decision computation:

```text
calendar valid
clock healthy
input freeze valid
mandatory nodes complete
PIT checks pass
Signal freeze valid
Risk Governor final
Operational mode compatible
Accounting state acceptable
no unresolved critical governance block
```

If any required condition fails:

```text
DECISION_NOT_ELIGIBLE
```

---

## 30. Execution handoff contract

56 hands the final decision to execution with an immutable envelope.

```python
ExecutionHandoff(
    decision_run_id,
    decision_snapshot_id,
    decision_freeze_id,
    risk_envelope_id,
    operational_health_snapshot_id,
    earliest_execution_time,
    expires_at,
    allowed_actions,
    order_intents,
    handoff_hash,
)
```

Execution must reject expired or mismatched handoffs.

---

## 31. Pre-open execution refresh

A valid EOD decision does not guarantee next-session execution safety.

Before execution:

```text
refresh 55 Operational Health
refresh 54 Risk Governor execution-sensitive inputs
refresh cash / positions / open orders
refresh trading halt / price-limit state
```

But do not silently recompute prior EOD alpha unless a new decision run is created.

---

## 32. End-to-end manifest

Every finalized orchestration run produces an immutable manifest containing:

```text
run specification
DAG version
node definitions
edge definitions
active artifact bindings
policy bindings
input snapshot ids
freeze ids
node start/end times
node states
retry attempts
excluded late data
failure root causes
finalization state
decision snapshot id
risk envelope id
operational snapshot id
execution handoff id
input hash
output hash
manifest hash
```

This manifest is the authoritative proof of what ADE knew and used.

---

## 33. Manifest hash chain

Node manifests roll into the run manifest.

```text
Node A hash ─┐
Node B hash ─┤
Node C hash ─┼→ Run Manifest Hash
Freeze hash ─┤
Binding hash ┘
```

Any change to a supposedly historical dependency causes manifest mismatch.

---

## 34. Database schema

Core tables:

```text
orchestration_policies
orchestration_dag_versions
orchestration_node_definitions
orchestration_edge_definitions

orchestration_runs
orchestration_run_bindings
orchestration_node_runs
orchestration_node_attempts

orchestration_freezes
orchestration_freeze_members

orchestration_failures
orchestration_failure_impacts
orchestration_retries

orchestration_decision_handoffs
orchestration_replay_requests

orchestration_reason_events
orchestration_run_manifests
```

---

## 35. `orchestration_runs`

```text
run_id
run_type
environment
portfolio_id
market
trading_date

evaluation_time
decision_cutoff
execution_earliest_time

dag_version
policy_id
policy_hash

governance_binding_snapshot_id

state
finalization_state

created_at
started_at
finalized_at

input_hash
output_hash
manifest_hash
```

---

## 36. `orchestration_node_runs`

```text
node_run_id
run_id
node_id
engine_id

resolved_engine_version
resolved_policy_hash

state
criticality

ready_at
started_at
completed_at
cutoff_at

input_manifest_hash
output_snapshot_id
output_hash

attempt_count
late_result_flag

root_failure_id

reason_codes
```

---

## 37. `orchestration_node_attempts`

```text
attempt_id
node_run_id
attempt_no

started_at
ended_at

worker_id
failure_class
error_code
retryable

input_hash
raw_output_hash

accepted_output
```

A rejected late output may exist in attempts while never becoming the node's accepted output.

---

## 38. `orchestration_freezes`

```text
freeze_id
run_id
freeze_type

freeze_time
cutoff_time

status
member_count

policy_hash
manifest_hash
```

`orchestration_freeze_members`:

```text
freeze_id
source_type
source_id
known_at
snapshot_hash
included
exclusion_reason
```

---

## 39. Run state machine

```text
CREATED
→ BINDINGS_FROZEN
→ INPUTS_FREEZING
→ RUNNING
→ DECISION_ELIGIBILITY_CHECK
→ DECISION_FROZEN
→ FINALIZED
```

Failure branches:

```text
RUNNING
→ DEGRADED
→ INVALID
→ ABORTED
```

Recovery branch:

```text
INTERRUPTED
→ RECOVERY_VALIDATION
→ RUNNING
```

---

## 40. Node state machine

```text
PENDING
→ WAITING
→ READY
→ RUNNING
→ SUCCEEDED
→ FINALIZED
```

Failure paths:

```text
RUNNING → FAILED
RUNNING → TIMED_OUT
FAILED  → RETRY_WAIT → READY
WAITING → SKIPPED_DEPENDENCY
ANY     → CANCELLED
```

---

## 41. Core scheduling algorithm

```python
def execute_run(ctx):
    spec = create_and_freeze_run_spec(ctx)
    bindings = resolve_and_freeze_bindings(spec)
    dag = load_dag(spec.dag_version)

    freeze_initial_inputs(spec, dag)

    while not terminal(spec.run_id):
        update_dependency_states(spec.run_id)

        ready_nodes = resolve_ready_nodes(
            run_id=spec.run_id,
            now=ctx.clock.now(),
        )

        for node in deterministic_order(ready_nodes):
            if node.cutoff_at < ctx.clock.now():
                mark_cutoff_missed(node)
                propagate_failure(node)
                continue

            dispatch(node)

        collect_completed_attempts(spec.run_id)
        accept_only_cutoff_valid_outputs(spec.run_id)
        propagate_failures(spec.run_id)

        if decision_eligibility_reached(spec.run_id):
            break

    eligibility = evaluate_decision_eligibility(spec.run_id)

    if not eligibility.allowed:
        return finalize_non_decision_run(spec.run_id, eligibility)

    decision_freeze = freeze_decision_inputs(spec.run_id)
    decision = compute_final_decision(decision_freeze)

    return finalize_run_manifest(
        spec.run_id,
        decision,
        decision_freeze,
    )
```

---

## 42. Ready-node resolution

```python
def node_is_ready(node, run):
    if node.state not in {"WAITING", "PENDING"}:
        return False

    if not all_hard_dependencies_finalized(node, run):
        return False

    if has_failed_hard_dependency(node, run):
        return False

    if not required_inputs_frozen(node, run):
        return False

    if not health_allows_engine_run(node, run):
        return False

    if current_time() > node.cutoff_at:
        return False

    return True
```

---

## 43. Failure propagation algorithm

```python
def propagate_failure(failed_node):
    for edge in downstream_edges(failed_node):
        child = edge.child

        if edge.dependency_type == "HARD":
            mark_skipped_dependency(
                child,
                root_failure=failed_node.root_failure_id,
            )

        elif edge.dependency_type == "SOFT":
            mark_degraded_dependency(child)
```

---

## 44. Cutoff acceptance algorithm

```python
def accept_output(attempt, node):
    if attempt.completed_at > node.cutoff_at:
        record_reason("RESULT_COMPLETED_AFTER_CUTOFF")
        return False

    if attempt.output_known_at > node.cutoff_at:
        record_reason("OUTPUT_KNOWN_AFTER_CUTOFF")
        return False

    if attempt.binding_hash != node.frozen_binding_hash:
        record_reason("MIDRUN_BINDING_MISMATCH")
        return False

    return True
```

---

## 45. Code structure

```text
orchestration/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── repository.py
├── engine.py
│
├── run_spec.py
├── environments.py
├── bindings.py
├── dag.py
├── nodes.py
├── edges.py
├── scheduler.py
├── readiness.py
├── deterministic_order.py
│
├── cutoffs.py
├── clock.py
├── temporal.py
│
├── freezes/
│   ├── inputs.py
│   ├── features.py
│   ├── signals.py
│   ├── risk.py
│   ├── decision.py
│   └── execution.py
│
├── failures.py
├── propagation.py
├── retries.py
├── resume.py
├── idempotency.py
│
├── eligibility.py
├── partial_runs.py
├── finalization.py
│
├── replay.py
├── historical.py
├── research.py
│
├── handoff.py
├── manifests.py
├── hashing.py
├── explainability.py
└── reason_codes.py
```

---

## 46. Reason codes

```text
ORCHESTRATION_RUN_CREATED
BINDINGS_FROZEN
INPUT_FREEZE_COMPLETED
FEATURE_FREEZE_COMPLETED
SIGNAL_FREEZE_COMPLETED
RISK_FREEZE_COMPLETED
DECISION_FREEZE_COMPLETED

MANDATORY_DEPENDENCY_MISSING
OPTIONAL_DEPENDENCY_MISSING
HARD_DEPENDENCY_FAILED
SOFT_DEPENDENCY_DEGRADED
SKIPPED_DEPENDENCY

NODE_TIMEOUT
NODE_TRANSIENT_FAILURE
NODE_PERMANENT_FAILURE
NODE_POLICY_VIOLATION
NODE_TEMPORAL_VIOLATION

RETRY_SCHEDULED
RETRY_EXHAUSTED
RESULT_COMPLETED_AFTER_CUTOFF
OUTPUT_KNOWN_AFTER_CUTOFF

LATE_INFORMATION_EXCLUDED
MIDRUN_BINDING_MISMATCH
CURRENT_ACTIVE_CONFIG_IN_HISTORICAL_REPLAY

DECISION_ELIGIBLE
DECISION_NOT_ELIGIBLE
VALID_DEGRADED_RUN
NO_NEW_RISK_VALID_RUN
RISK_REDUCTION_ONLY_VALID_RUN
INVALID_RUN

RUN_INTERRUPTED
RUN_RESUMED
IDEMPOTENCY_REUSE
IDEMPOTENCY_CONFLICT

EXECUTION_HANDOFF_CREATED
EXECUTION_HANDOFF_EXPIRED
EXECUTION_HANDOFF_MISMATCH

MANIFEST_RECONCILIATION_FAILED
MANIFEST_HASH_MISMATCH
```

---

## 47. Testing plan

### Unit tests

```text
A. DAG cycle introduced
→ validation fails before runtime

B. Mandatory dependency missing
→ downstream never READY

C. Soft dependency fails
→ downstream can run DEGRADED where policy allows

D. Node result completed before cutoff
→ accepted

E. Node result completes one second after cutoff
→ stored but not admitted

F. Future known_at in input freeze
→ excluded / block according to criticality

G. Mid-run model promotion
→ frozen current run binding unchanged

H. Two READY nodes
→ deterministic tie-break order

I. Retryable 503
→ bounded retry

J. Schema mismatch
→ no blind retry

K. Retry completes after cutoff
→ output rejected for this decision

L. Coordinator crash after node success
→ resume reuses finalized node

M. Same idempotency key with conflicting output
→ IDEMPOTENCY_CONFLICT
```

### Integration tests

```text
N. Full healthy EOD DAG
→ FULLY_VALID
→ decision freeze
→ run manifest

O. Optional reporting node failure
→ valid analytical decision unaffected

P. Market Data Finalization failure
→ behavior/signal chain skipped
→ no new risk decision

Q. Accounting reconciliation failure
→ decision path limited by 55/54

R. Risk Governor unavailable
→ normal BUY decision cannot finalize

S. Operational Health = NEW_RISK_BLOCKED
→ analytical nodes may finish
→ final new-risk permission remains blocked

T. Late earnings event after decision freeze
→ original decision immutable
→ eligible only in new run

U. Next-session broker failure
→ EOD decision remains immutable
→ execution handoff blocked at pre-open refresh
```

### Replay tests

```text
V. Historical replay for 2025 date
→ historical active bindings resolved
→ current model not injected

W. Research replay with challenger
→ isolated from PAPER/LIVE state

X. Same historical manifest replay
→ same admitted inputs
→ same node outputs
→ same final hash
```

### Concurrency tests

```text
Y. Expectations and Market Behavior run in parallel
→ join waits for both mandatory outputs

Z. Duplicate coordinator dispatch
→ idempotency prevents duplicate finalized node output
```

---

## 48. Critical invariants

```text
DAG cycle in ACTIVE graph = 0

Future input admitted into frozen decision = 0
Late output admitted after cutoff = 0

Mid-run binding change affecting current run = 0

Mandatory failed dependency with downstream NORMAL finalization = 0

Decision without Risk Governor final state = 0
Decision without Operational Health state = 0

Current ACTIVE artifact silently used in historical replay = 0

Coordinator restart duplicating accepted node output = 0

Retry beyond cutoff becoming retroactively on-time = 0

Research run creating LIVE/PAPER broker-routable order = 0

Pre-open execution using expired decision handoff = 0

Historical decision mutation after DECISION_FREEZE = 0

Same run spec + same frozen inputs + same bindings + same code
→ same orchestration result
→ same finalization state
→ same manifest hash
```

---

## 49. Architecture consequences

With Engine 56, ADE transitions from a collection of engines into a single reproducible decision runtime.

```text
Before 56
-----------
Engine A ran
Engine B ran
Engine C ran
Result exists

But:
Which data versions?
Which cutoff?
Which model versions?
Was B late?
Did C see a different universe?
Was the final decision reproducible?

After 56
--------
One run_id
One DAG version
One binding freeze
One set of cutoff rules
One admitted input set
One decision freeze
One end-to-end manifest
```

This makes every ADE decision answerable with:

```text
What did ADE know?
When did it know it?
Which engines ran?
Which versions ran?
Which outputs were excluded?
Which risk/health state was binding?
Why was the decision allowed or blocked?
Can the exact run be replayed?
```

---

## 50. Interface with Engines 54 and 55

The safety chain becomes:

```text
55 Operational Resilience
"Can the system be trusted to run?"
        ↓
54 Risk Governor
"Can the portfolio accept this risk?"
        ↓
56 Runtime Coordinator
"Were all required inputs and controls executed
in the correct order, on time, under frozen bindings?"
        ↓
Decision Freeze
        ↓
Execution Handoff
```

A positive Alpha signal cannot bypass any of the three layers.

---

## 51. Recommended implementation order

```text
1. immutable RunSpecification models
2. DAG/node/edge registry
3. DAG cycle validator
4. SQLite/PostgreSQL migrations
5. cutoff and clock contracts
6. binding freeze
7. input freeze
8. node readiness resolver
9. deterministic scheduler
10. node attempt + retry state machine
11. failure propagation
12. decision eligibility gate
13. decision freeze
14. execution handoff
15. resume/idempotency
16. historical replay
17. run manifest + hashing
18. end-to-end fixed-fixture tests
```

---

## 52. Fixed EOD integration fixture

Create a permanent integration fixture with:

```text
50 securities
2 benchmarks
4 sectors
1 corporate action
1 earnings event
1 late event
1 stale optional source
1 transient API failure
1 retry
1 excluded post-cutoff result
1 Risk Governor binding constraint
1 Operational Health degraded component
```

Expected result must include deterministic:

```text
node state sequence
freeze membership
excluded late items
retry count
binding set
risk state
decision eligibility
decision snapshot hash
run manifest hash
```

This fixture becomes the canonical regression test for the complete ADE runtime.
