# 61. Configuration, Policy & Parameter Registry / Change-Control Engine v1

## 1. Purpose

Engine 61 is ADE's authoritative configuration control plane. It registers, versions, validates, approves, promotes, resolves, freezes and audits every decision-relevant policy, threshold, weight, limit, cutoff, SLO, model parameter and runtime configuration used by ADE.

It answers:

> Which exact configuration values were authorized for this engine, portfolio, market, environment and decision timestamp — and can ADE prove that no unversioned, unapproved, stale, future-dated or mid-run configuration influenced the decision?

Core principle:

```text
No decision-relevant magic numbers.
No configuration without identity and version.
No ACTIVE configuration without approval.
No mid-run configuration mutation.
No current policy in historical replay.

Same input data
+ same model bindings
+ same configuration snapshot
+ same evaluation cutoff
→ same engine behavior
→ same decision.
```

Engine 61 does not own investment logic. It owns the authorized values that investment, risk, operational and reporting logic are permitted to use.

---

## 2. Why Engine 61 is required now

By Engine 60, ADE contains many policy values distributed across the architecture, including:

- Signal family weights and candidate thresholds;
- confidence thresholds and conflict penalties;
- regime transition windows and hysteresis;
- position and sector caps;
- volatility and correlation thresholds;
- stress scenarios and survival gates;
- drawdown thresholds and re-risk ladders;
- Risk Governor limits and permissions;
- execution participation and slippage assumptions;
- calibration shrinkage limits;
- governance promotion thresholds;
- orchestration cutoffs and retry policies;
- operational freshness tolerances;
- reporting definitions;
- analytics windows;
- monitoring KPI/SLO limits.

If these remain scattered in Python constants, YAML files, database rows and deployment environment variables, ADE cannot reliably answer:

```text
Why was the Signal threshold 65 on this date?
Why did the portfolio allow 30% sector exposure?
Which drawdown policy was ACTIVE in this replay?
Did the threshold change before or after the decision freeze?
Was PAPER using the same config as LIVE?
Who approved the change?
What downstream engines were affected?
```

Engine 61 makes configuration itself a first-class, immutable, point-in-time governed artifact.

---

## 3. Position in ADE architecture

```text
Research / Operators / Governance
        ↓
Configuration Change Request
        ↓
┌──────────────────────────────────────────────────────┐
│ 61 Configuration / Policy / Parameter Registry     │
├──────────────────────────────────────────────────────┤
│ Namespace Registry                                  │
│ Schema Registry                                     │
│ Typed Parameter Registry                            │
│ Policy Bundles                                      │
│ Validation                                          │
│ Dependency / Impact Graph                           │
│ Approval Workflow                                   │
│ Environment Promotion                               │
│ Effective Dating                                    │
│ ACTIVE Binding Resolution                           │
│ Runtime Configuration Freeze                        │
│ Rollback                                            │
│ Immutable Audit                                     │
└──────────────────────────────────────────────────────┘
        ↓
48 Governance
56 Runtime Coordinator
        ↓
38~60 ADE Engines
```

Runtime engines must resolve configuration through Engine 61 or through a frozen Engine 61 snapshot supplied by Engine 56. They must not independently choose a policy row or read mutable ad-hoc configuration.

---

## 4. Responsibility boundary

### Engine 61 does

- register decision-relevant configuration namespaces;
- define typed configuration schemas;
- issue immutable configuration version identities;
- validate value type, units, range and cross-field rules;
- manage policy bundles containing multiple parameters;
- manage effective dates and expiry dates;
- manage scope inheritance and explicit overrides;
- resolve ACTIVE configuration point-in-time;
- calculate configuration diffs;
- calculate downstream dependency and impact graphs;
- require approval according to change criticality;
- promote configurations across RESEARCH, BACKTEST, PAPER, LIVE_SHADOW and LIVE;
- freeze configuration snapshots for Engine 56 runs;
- preserve historical bindings;
- support controlled rollback to previously approved versions;
- emit configuration lineage, reason codes and hashes.

### Engine 61 does not

- decide whether a model itself is statistically superior — Engine 50/48;
- decide whether current portfolio risk is acceptable — Engine 54;
- decide whether the platform is operationally healthy — Engine 55;
- orchestrate the execution DAG — Engine 56;
- modify frozen historical decisions — prohibited;
- silently infer missing configuration values;
- allow runtime engines to overwrite ACTIVE configuration.

---

## 5. Configuration artifact taxonomy

Every registered object is one of:

```text
PARAMETER
THRESHOLD
WEIGHT
LIMIT
MULTIPLIER
ENUM_POLICY
TIME_POLICY
WINDOW_POLICY
FEATURE_FLAG
ALGORITHM_POLICY
SCENARIO_POLICY
SLO_POLICY
BUNDLE
```

Examples:

```text
signal.candidate.alpha_min                THRESHOLD
signal.family.market_behavior.weight      WEIGHT
regime.risk_off.risk_budget               MULTIPLIER
portfolio.single_name.max_weight          LIMIT
execution.max_adv_participation           LIMIT
orchestration.decision_cutoff              TIME_POLICY
monitoring.accounting_reconciliation.slo  SLO_POLICY
stress.ai_semiconductor_bust               SCENARIO_POLICY
```

All values must declare explicit units where applicable.

```text
0.10            + unit=PERCENT_OF_NAV
5               + unit=TRADING_DAYS
250             + unit=BASIS_POINTS
16:24:00        + unit=ASIA_SEOUL_LOCAL_TIME
```

A raw number without semantic unit is not valid for a decision-critical parameter.

---

## 6. Namespace design

Configuration keys use stable hierarchical names.

```text
ade.<domain>.<component>.<parameter>
```

Examples:

```text
ade.signal.candidate.alpha_min
ade.signal.candidate.confidence_min
ade.regime.transition.risk_off_to_recovery.confirmations
ade.portfolio.single_name.max_weight
ade.portfolio.minimum_cash.weight
ade.lifecycle.hard_stop.loss_pct
ade.execution.market.max_adv_participation
ade.stress.survival.max_drawdown
ade.drawdown.rerisk.max_daily_increase
ade.risk_governor.permission.risk_off.buy
ade.operational.market_data.close.max_age_minutes
ade.orchestration.eod.decision_cutoff
ade.reporting.benchmark.official_required
ade.analytics.sharpe.min_sample
ade.monitoring.future_information.max_events
```

Namespaces are immutable once published. Renames are implemented by deprecating the old key and registering a new key with migration lineage.

---

## 7. Typed configuration contract

```python
@dataclass(frozen=True)
class ParameterDefinition:
    parameter_key: str
    data_type: str
    unit: str | None
    nullable: bool
    minimum: Decimal | None
    maximum: Decimal | None
    allowed_values: tuple[str, ...] | None
    default_policy: str
    criticality: str
    owner_engine: int
    description: str
```

Allowed data types include:

```text
BOOLEAN
INTEGER
DECIMAL
STRING
ENUM
DURATION
LOCAL_TIME
TIMESTAMP
JSON_OBJECT
VECTOR
MATRIX
```

Decision-critical decimals should use fixed precision rather than binary floating-point persistence.

---

## 8. No implicit defaults

The runtime policy is conservative:

```text
MISSING CRITICAL CONFIG
!= DEFAULT
```

Default values may exist only when the parameter definition explicitly declares a default policy and that default is itself versioned and approved.

For TIER_0/TIER_1 configuration:

```text
missing value
→ CONFIGURATION_INCOMPLETE
→ new risk blocked
```

A Python function signature such as:

```python
def evaluate(alpha_min=65):
```

must not become the authoritative source of a decision threshold.

Preferred pattern:

```python
def evaluate(features, config: SignalPolicy):
```

where `SignalPolicy` originates from the frozen Engine 61 snapshot.

---

## 9. Configuration scopes

A configuration version is bound to an explicit scope.

```text
GLOBAL
MARKET
PORTFOLIO
STRATEGY
ENGINE
SECURITY_CLASS
ENVIRONMENT
```

Example hierarchy:

```text
GLOBAL
  ↓
MARKET = KR
  ↓
PORTFOLIO = ADE_PAPER_01
  ↓
STRATEGY = QUALITY_MOMENTUM
```

Scope-specific values may override broader values only if the parameter definition allows override.

Example:

```text
GLOBAL minimum_cash = 10%
PORTFOLIO ADE_PAPER_01 minimum_cash = 15%
```

If override is allowed, final resolved value = 15%.

But for non-overridable safety settings:

```text
GLOBAL leverage_allowed = false
PORTFOLIO tries true
→ OVERRIDE_NOT_PERMITTED
```

---

## 10. Scope resolution precedence

Resolution order is explicit and deterministic.

```text
1 exact portfolio/strategy scope
2 portfolio scope
3 market scope
4 environment scope
5 global scope
```

However, safety constraints use conservative inheritance when appropriate.

Example:

```text
GLOBAL single_name_hard_cap = 10%
PORTFOLIO target cap        = 7%

absolute hard cap = 10%
effective target  = 7%
```

A child scope may become more conservative than its parent but must not relax a parent hard safety constraint without a separately authorized exception mechanism.

---

## 11. Version lifecycle

Every configuration artifact follows:

```text
DRAFT
→ VALIDATING
→ VALIDATED
→ APPROVAL_PENDING
→ APPROVED
→ SCHEDULED
→ ACTIVE
→ SUPERSEDED
→ RETIRED
```

Failure states:

```text
REJECTED
QUARANTINED
ROLLED_BACK
```

Critical rule:

```text
DRAFT != APPROVED
APPROVED != ACTIVE
```

A version may be approved yet scheduled to become effective next Monday at 00:00 KST.

---

## 12. Effective dating

Every binding has:

```text
known_at
valid_from
valid_to
effective_from
effective_to
```

Point-in-time resolution requires:

```text
known_at <= evaluation_time
and
effective_from <= evaluation_time
and
(effective_to is NULL or evaluation_time < effective_to)
```

A configuration approved at 18:00 cannot be used by a 16:24 frozen decision, even if its `valid_from` business date is the same day.

---

## 13. Environment segregation

Environments are first-class:

```text
RESEARCH
BACKTEST
PAPER
LIVE_SHADOW
LIVE
```

Configuration promotion follows a controlled path.

```text
RESEARCH
→ BACKTEST
→ PAPER
→ LIVE_SHADOW
→ LIVE
```

A PAPER configuration is not automatically LIVE-approved.

```text
PAPER_ACTIVE != LIVE_ACTIVE
```

Research parameter searches are explicitly isolated from official runtime policies.

---

## 14. Policy bundles

Many engines require mutually consistent groups of settings. These are promoted as atomic bundles.

Example Signal bundle:

```text
signal_policy_v7
├─ quality_weight = 0.25
├─ valuation_weight = 0.25
├─ expectations_weight = 0.20
├─ behavior_weight = 0.30
├─ alpha_min = 65
├─ confidence_min = 60
└─ adjusted_signal_min = 55
```

The bundle is valid only if:

```text
sum(weights) = 1.0
threshold ordering valid
all referenced feature families exist
all parameter versions share compatible effective dating
```

Runtime must not mix `alpha_min` from v7 with weights from v6 unless an explicitly defined bundle permits it.

---

## 15. Cross-field validation

Validation is not limited to individual ranges.

Examples:

```text
minimum_cash_weight >= 0.10
single_name_max_weight <= 0.10
sector_max_weight >= single_name_max_weight

buy_threshold > hold_threshold
hold_threshold > reduce_threshold
reduce_threshold > exit_threshold

max_daily_risk_increase <= max_weekly_risk_increase

train_end < validation_start
validation_end < test_start

risk_off_budget <= normal_budget
crisis_budget <= risk_off_budget
```

Invalid bundles cannot become APPROVED.

---

## 16. Change classification

Every change is classified by blast radius and safety relevance.

```text
CLASS_0 EMERGENCY_SAFETY
CLASS_1 CRITICAL
CLASS_2 MATERIAL
CLASS_3 STANDARD
CLASS_4 COSMETIC
```

Examples:

```text
GLOBAL leverage permission       CLASS_0/1
Risk Governor hard limit         CLASS_1
Signal alpha threshold           CLASS_2
Analytics rolling window         CLASS_3
Dashboard label                  CLASS_4
```

Required validation and approvals increase with criticality.

---

## 17. Configuration diff

Every change request calculates a semantic diff.

```text
Parameter                              Old      New      Delta
----------------------------------------------------------------
ade.portfolio.single_name.max_weight   10%      8%      -2%p
ade.signal.candidate.alpha_min          65       68      +3
ade.regime.risk_off.risk_budget         0.50     0.40    -0.10
```

Diff must distinguish:

```text
ADDED
REMOVED
VALUE_CHANGED
TYPE_CHANGED
UNIT_CHANGED
SCOPE_CHANGED
EFFECTIVE_DATE_CHANGED
DEPENDENCY_CHANGED
```

Type or unit changes are migration-level changes and cannot be treated as ordinary value edits.

---

## 18. Dependency and impact graph

Every parameter records its consumers.

Example:

```text
ade.signal.candidate.alpha_min
        ↓
42 Signal Integration
        ↓
44 Portfolio Construction
        ↓
54 Risk Governor / Decision Path
        ↓
58 Reporting / 59 Analytics
```

A proposed change produces:

```text
DIRECT_CONSUMERS
TRANSITIVE_CONSUMERS
DECISION_PATH_IMPACT
RISK_PATH_IMPACT
REPORTING_IMPACT
REPLAY_IMPACT
```

This prevents changing a seemingly small threshold without knowing downstream consequences.

---

## 19. Change request contract

```python
@dataclass(frozen=True)
class ConfigurationChangeRequest:
    change_request_id: UUID
    namespace: str
    base_version_id: UUID
    proposed_values: dict
    target_scope: str
    target_environment: str
    requested_effective_from: datetime
    change_class: str
    rationale: str
    evidence_refs: tuple[str, ...]
    requested_by: str
```

Every material change must include rationale and evidence lineage.

---

## 20. Approval policy

Illustrative initial policy:

```text
CLASS_4
automated validation only

CLASS_3
1 owner approval

CLASS_2
owner + governance approval

CLASS_1
owner + risk/governance approval
+ PAPER/LIVE_SHADOW validation

CLASS_0
emergency authorized path
+ mandatory post-event review
```

Separation-of-duties can require:

```text
requester != approver
```

for CLASS_1 and LIVE changes.

---

## 21. Emergency changes

Emergency configuration changes must be conservative-only by default.

Examples:

```text
reduce gross exposure limit
increase minimum cash
block BUY
lower ADV participation
shorten stale-data tolerance only if operationally safe
```

Emergency changes that increase risk require stronger authorization and are not the default path.

Every emergency change includes:

```text
incident_id
reason
approver
expiry_time
rollback_target
post_event_review_required=true
```

Temporary emergency overrides must expire automatically unless explicitly renewed.

---

## 22. Runtime binding resolution

Engine 56 requests a frozen configuration snapshot before the run begins.

```python
resolve_configuration(
    environment="PAPER",
    market="KR",
    portfolio_id="ADE_PAPER_01",
    evaluation_time="2026-08-29T16:24:00+09:00",
    required_namespaces=[...],
)
```

Output:

```python
ConfigurationSnapshot(
    snapshot_id=...,
    resolved_parameters=...,
    source_version_ids=...,
    bindings=...,
    policy_hash=...,
    snapshot_hash=...,
)
```

Engine 56 freezes this snapshot into the run manifest.

---

## 23. No mid-run mutation

Example:

```text
16:20 Run starts
16:22 signal threshold 65 → 70 promoted
16:24 Decision cutoff
```

The running decision continues to use 65 if 65 was present in its frozen snapshot.

The new threshold 70 is used only by a new run whose configuration freeze occurs after the new binding becomes effective.

Reason code:

```text
MID_RUN_CONFIGURATION_CHANGE_IGNORED
```

---

## 24. Historical replay

Historical replay resolves configuration as of the historical evaluation timestamp.

```text
Replay 2026-05-15
→ use configuration ACTIVE on 2026-05-15
```

Forbidden:

```text
Replay 2026-05-15
→ use today's ACTIVE threshold
```

Reason code:

```text
CURRENT_CONFIGURATION_IN_HISTORICAL_REPLAY
```

Research may deliberately compare old vs new configuration, but that run is labelled RESEARCH/COUNTERFACTUAL rather than official replay.

---

## 25. Rollback

Rollback never mutates historical versions.

```text
v10 ACTIVE
↓ incident
v9 approved rollback target
↓
close v10 binding
create new binding to v9
```

The rollback event records:

```text
from_version
rollback_version
incident_id
approved_by
effective_time
reason
```

A RETIRED or QUARANTINED version cannot be used as rollback target without revalidation.

---

## 26. Configuration drift detection

Engine 61 compares expected and observed runtime configuration hashes.

```text
Expected snapshot hash
!= runtime-reported hash
→ CONFIGURATION_DRIFT_DETECTED
```

Examples:

- container environment variable differs from registry;
- local YAML file was edited manually;
- code uses hidden fallback constant;
- one node loads old configuration cache;
- database replica returns stale binding.

Critical drift in a decision path is emitted to Engine 55/60 and may block new risk through Engine 54.

---

## 27. Cache policy

Runtime caching is allowed only with identity preservation.

Every cache entry includes:

```text
configuration_snapshot_id
snapshot_hash
created_at
expires_at
```

Cache refresh cannot silently change the configuration used by an already frozen run.

---

## 28. Configuration completeness gate

Each engine publishes a required configuration contract.

Example Engine 42:

```text
REQUIRED
signal family weights
alpha threshold
confidence threshold
adjusted signal threshold
conflict threshold
candidate gate policy

OPTIONAL
diagnostic formatting policy
```

Before execution:

```text
required config complete
+ schema compatible
+ approved
+ effective
+ fresh binding
→ READY
```

Otherwise:

```text
CONFIGURATION_NOT_READY
```

---

## 29. Database schema

### 29.1 `configuration_namespaces`

```text
namespace_id PK
namespace_key UNIQUE
owner_engine
owner_team
criticality
description
created_at
deprecated_at
```

### 29.2 `configuration_parameter_definitions`

```text
parameter_definition_id PK
namespace_id FK
parameter_key UNIQUE
data_type
unit
nullable
minimum_value
maximum_value
allowed_values_json
default_policy
allow_scope_override
criticality
schema_version
created_at
```

### 29.3 `configuration_versions`

```text
configuration_version_id PK
namespace_id FK
version_number
state
change_class
content_json
schema_version
content_hash
created_by
created_at
known_at
```

Unique:

```text
(namespace_id, version_number)
```

### 29.4 `configuration_version_members`

```text
configuration_version_id FK
parameter_definition_id FK
value_json
normalized_value
value_hash
```

### 29.5 `configuration_scopes`

```text
scope_id PK
scope_type
scope_key
parent_scope_id
market
environment
created_at
```

### 29.6 `configuration_bindings`

```text
binding_id PK
scope_id FK
namespace_id FK
configuration_version_id FK
environment
known_at
effective_from
effective_to
binding_state
binding_hash
created_at
```

Constraint:

```text
no overlapping ACTIVE bindings for same
(scope, namespace, environment, time interval)
```

### 29.7 `configuration_change_requests`

```text
change_request_id PK
base_version_id
proposed_version_id
scope_id
target_environment
change_class
rationale
requested_effective_from
requested_by
requested_at
state
impact_hash
```

### 29.8 `configuration_change_diffs`

```text
diff_id PK
change_request_id FK
parameter_key
change_type
old_value
new_value
delta_json
risk_classification
```

### 29.9 `configuration_approvals`

```text
approval_id PK
change_request_id FK
approval_role
approver
approval_state
comments
approved_at
approval_hash
```

### 29.10 `configuration_dependencies`

```text
dependency_id PK
parameter_key
consumer_engine
consumer_component
required_flag
impact_type
created_at
```

### 29.11 `configuration_snapshots`

```text
snapshot_id PK
environment
market
portfolio_id
evaluation_time
created_at
snapshot_hash
```

### 29.12 `configuration_snapshot_members`

```text
snapshot_id FK
parameter_key
resolved_value
source_version_id
source_binding_id
scope_id
member_hash
```

### 29.13 `configuration_rollbacks`

```text
rollback_id PK
incident_id
from_version_id
to_version_id
scope_id
environment
approved_by
effective_time
reason
rollback_hash
```

### 29.14 `configuration_drift_events`

```text
drift_event_id PK
component_id
expected_snapshot_id
expected_hash
observed_hash
severity
detected_at
resolved_at
reason_codes
```

### 29.15 `configuration_reason_events`

Append-only reason/event ledger.

### 29.16 `configuration_manifests`

Immutable manifests containing schema, versions, bindings, approvals, dependencies and hashes.

---

## 30. Indexing

Required indexes:

```text
configuration_bindings(
  scope_id,
  namespace_id,
  environment,
  effective_from,
  effective_to
)

configuration_versions(namespace_id, state, known_at)
configuration_snapshot_members(snapshot_id, parameter_key)
configuration_change_requests(state, requested_at)
configuration_drift_events(component_id, detected_at)
```

Historical PIT resolution must remain efficient without replacing point-in-time correctness with a mutable current-state cache.

---

## 31. Core resolution algorithm

```python
def resolve_snapshot(ctx, required_parameters):
    definitions = registry.load_definitions(required_parameters)

    candidates = repository.load_effective_bindings(
        environment=ctx.environment,
        market=ctx.market,
        portfolio_id=ctx.portfolio_id,
        strategy_id=ctx.strategy_id,
        evaluation_time=ctx.evaluation_time,
    )

    resolved = {}

    for definition in definitions:
        matches = select_scope_candidates(
            definition=definition,
            candidates=candidates,
        )

        value = resolve_by_precedence_and_safety(
            definition,
            matches,
        )

        validate_runtime_value(definition, value)
        resolved[definition.parameter_key] = value

    validate_cross_field_rules(resolved)
    validate_approval_and_state(resolved)

    return finalize_configuration_snapshot(resolved)
```

---

## 32. Change validation algorithm

```python
def validate_change_request(request):
    base = load_version(request.base_version_id)
    proposed = materialize_proposed_version(request)

    schema_results = validate_schema(proposed)
    field_results = validate_ranges_and_units(proposed)
    cross_results = validate_cross_field_rules(proposed)

    diff = semantic_diff(base, proposed)
    impact = dependency_graph.calculate_impact(diff)

    required_approvals = approval_policy.resolve(
        change_class=request.change_class,
        environment=request.target_environment,
        impact=impact,
    )

    return ChangeValidationResult(
        valid=all_passed(
            schema_results,
            field_results,
            cross_results,
        ),
        diff=diff,
        impact=impact,
        required_approvals=required_approvals,
    )
```

---

## 33. Promotion algorithm

```python
def promote_configuration(change_request, now):
    validation = require_validated(change_request)
    approvals = require_all_approvals(change_request)

    assert validation.passed
    assert approvals.complete

    target = change_request.proposed_version

    if target.environment == "LIVE":
        require_live_shadow_evidence(target)

    binding = create_scheduled_binding(
        version=target,
        effective_from=change_request.requested_effective_from,
    )

    return immutable_promotion_event(binding)
```

Activation is performed at the effective timestamp. It does not mutate earlier bindings.

---

## 34. Risk direction validator

For safety-sensitive values, Engine 61 understands conservative direction.

Examples:

```text
minimum_cash_weight
higher = more conservative

gross_exposure_limit
lower = more conservative

max_adv_participation
lower = more conservative

BUY permission
BLOCKED = more conservative

risk_budget_multiplier
lower = more conservative
```

This allows emergency change validation:

```python
if emergency and not change.is_more_conservative():
    require_elevated_emergency_approval()
```

---

## 35. Parameter migration

If a parameter changes meaning, create a new schema/key.

Bad:

```text
max_position = 10
# previously percent, now millions KRW
```

Good:

```text
ade.portfolio.single_name.max_weight_pct
ade.portfolio.single_name.max_notional_krw
```

Migrations contain explicit transformation rules and cannot rewrite historical snapshots.

---

## 36. Code structure

```text
configuration_control/
├── models.py
├── enums.py
├── contracts.py
├── schemas.py
├── registry.py
├── repository.py
├── engine.py
│
├── namespaces.py
├── definitions.py
├── units.py
├── normalization.py
│
├── validation/
│   ├── types.py
│   ├── ranges.py
│   ├── cross_fields.py
│   ├── safety.py
│   └── compatibility.py
│
├── scopes/
│   ├── hierarchy.py
│   ├── precedence.py
│   └── overrides.py
│
├── versions.py
├── bindings.py
├── effective_dating.py
├── resolver.py
├── snapshots.py
│
├── changes/
│   ├── requests.py
│   ├── diff.py
│   ├── classification.py
│   ├── impact.py
│   └── approvals.py
│
├── dependencies.py
├── promotions.py
├── environments.py
├── emergency.py
├── rollback.py
├── migrations.py
├── drift.py
├── cache.py
│
├── reason_codes.py
├── explainability.py
├── manifest.py
└── hashing.py
```

---

## 37. Runtime client interface

Runtime engines should consume typed policy objects rather than arbitrary dictionary lookups.

```python
class ConfigurationClient(Protocol):
    def get_snapshot(
        self,
        snapshot_id: UUID,
    ) -> ConfigurationSnapshot: ...

    def resolve_typed_policy(
        self,
        snapshot_id: UUID,
        policy_type: type[T],
    ) -> T: ...
```

Example:

```python
signal_policy = config.resolve_typed_policy(
    snapshot_id=run.configuration_snapshot_id,
    policy_type=SignalIntegrationPolicy,
)
```

---

## 38. Example typed policy

```python
@dataclass(frozen=True)
class SignalIntegrationPolicy:
    quality_weight: Decimal
    valuation_weight: Decimal
    expectations_weight: Decimal
    behavior_weight: Decimal

    alpha_min: Decimal
    confidence_min: Decimal
    adjusted_signal_min: Decimal

    conflict_high_threshold: Decimal
```

Validation:

```python
assert sum([
    quality_weight,
    valuation_weight,
    expectations_weight,
    behavior_weight,
]) == Decimal("1.0")
```

---

## 39. Engine 56 integration

Before a decision run:

```text
56 Create Run Specification
        ↓
61 Resolve Configuration Snapshot
        ↓
56 Freeze Snapshot ID + Hash
        ↓
DAG Execution
```

Every node receives:

```text
run_id
configuration_snapshot_id
configuration_snapshot_hash
```

A node that reports a different configuration hash fails:

```text
RUNTIME_CONFIGURATION_HASH_MISMATCH
```

---

## 40. Engine 48 integration

Engine 48 governs artifacts; Engine 61 governs configuration.

```text
48
Which model / policy artifact is approved?

61
Which exact parameter version is ACTIVE
for this scope/environment/time?
```

Material configuration changes can themselves be registered as Engine 48 governance artifacts where policy requires.

No conflict exists if authority is separated:

```text
48 = approval/governance authority
61 = configuration registry/resolution authority
```

---

## 41. Engine 54 integration

Critical Risk Governor limits must be Engine 61 parameters.

Examples:

```text
minimum_cash
single_name_hard_cap
sector_cap
new_risk_limit
BUY/ADD permissions by risk state
```

If Engine 61 critical risk configuration is unavailable:

```text
54
UNKNOWN RISK CONFIGURATION
→ NEW_RISK_BLOCKED
```

Unknown config is not converted to permissive defaults.

---

## 42. Engine 55/60 integration

Engine 55 receives:

```text
CONFIGURATION_REGISTRY_HEALTH
CONFIGURATION_SNAPSHOT_HEALTH
CONFIGURATION_DRIFT_STATE
```

Engine 60 monitors:

```text
configuration_resolution_success_rate
critical_config_missing_count
configuration_drift_count
unapproved_runtime_config_count
stale_binding_count
promotion_failure_rate
rollback_count
emergency_override_age
```

Suggested zero-tolerance KPI:

```text
UNAPPROVED_RUNTIME_CONFIGURATION = 0
```

---

## 43. Reason codes

```text
CONFIGURATION_READY
CONFIGURATION_INCOMPLETE
CONFIGURATION_SCHEMA_INVALID
CONFIGURATION_VALUE_OUT_OF_RANGE
CONFIGURATION_UNIT_MISMATCH
CONFIGURATION_CROSS_FIELD_INVALID

CONFIGURATION_VERSION_NOT_APPROVED
CONFIGURATION_VERSION_NOT_ACTIVE
CONFIGURATION_BINDING_NOT_FOUND
CONFIGURATION_BINDING_OVERLAP
CONFIGURATION_BINDING_EXPIRED
CONFIGURATION_BINDING_FUTURE

SCOPE_OVERRIDE_APPLIED
OVERRIDE_NOT_PERMITTED
PARENT_SAFETY_LIMIT_BINDING

CHANGE_REQUEST_VALIDATED
CHANGE_REQUEST_REJECTED
CHANGE_APPROVAL_INCOMPLETE
SEPARATION_OF_DUTIES_VIOLATION

CHANGE_IMPACT_HIGH
DEPENDENCY_IMPACT_REVIEW_REQUIRED

CONFIGURATION_PROMOTED
CONFIGURATION_SCHEDULED
CONFIGURATION_ACTIVATED
CONFIGURATION_SUPERSEDED
CONFIGURATION_ROLLED_BACK

EMERGENCY_OVERRIDE_ACTIVE
EMERGENCY_OVERRIDE_EXPIRED
EMERGENCY_RISK_INCREASE_REQUIRES_APPROVAL

MID_RUN_CONFIGURATION_CHANGE_IGNORED
CURRENT_CONFIGURATION_IN_HISTORICAL_REPLAY

CONFIGURATION_DRIFT_DETECTED
RUNTIME_CONFIGURATION_HASH_MISMATCH
HIDDEN_RUNTIME_DEFAULT_DETECTED

FUTURE_CONFIGURATION_GUARD
CONFIGURATION_PIT_VIOLATION
```

---

## 44. Unit tests

### Registry and type safety

```text
A. decimal parameter receives string
→ validation fail

B. 12% single-name cap with maximum 10%
→ VALUE_OUT_OF_RANGE

C. bps value supplied as percent
→ UNIT_MISMATCH

D. unknown enum
→ validation fail
```

### Cross-field tests

```text
E. Signal weights sum 0.95
→ bundle invalid

F. BUY threshold 60 / HOLD threshold 65
→ threshold ordering invalid

G. crisis risk budget > normal budget
→ bundle invalid
```

### Scope tests

```text
H. GLOBAL min cash 10%
PORTFOLIO min cash 15%
→ resolved 15%

I. GLOBAL leverage false
PORTFOLIO leverage true
→ override rejected
```

### Effective dating

```text
J. configuration known_at 17:00
Decision cutoff 16:24
→ use 0 times

K. configuration effective tomorrow
→ today's run cannot use

L. ACTIVE binding expires 15:00
run 16:00
→ binding unavailable
```

### Runtime freeze

```text
M. run freezes threshold 65
threshold 70 activated mid-run
→ run remains 65

N. retry after threshold change
same run
→ remains frozen 65
```

### Replay

```text
O. historical replay May
current policy August
→ current policy rejected

P. research counterfactual explicitly requests August policy
→ allowed only RESEARCH namespace
```

### Approval

```text
Q. CLASS_1 LIVE change with owner only
→ approval incomplete

R. requester approves own restricted change
→ separation-of-duties violation
```

### Rollback

```text
S. active v10 incident
approved v9
→ new binding v9
→ v10 history unchanged

T. rollback target QUARANTINED
→ rollback rejected
```

### Drift

```text
U. expected hash A / runtime hash B
→ drift event

V. hidden local default differs from snapshot
→ runtime hash mismatch
```

---

## 45. Integration tests

```text
1. 56 creates PAPER run
→ 61 resolves full snapshot
→ all mandatory engines receive same snapshot hash

2. 42 reports config hash different from run freeze
→ node fail
→ BUY path invalid

3. 54 critical config missing
→ NEW_RISK_BLOCKED

4. 61 registry temporarily unavailable after freeze
→ running job may use already validated immutable freeze
→ new run cannot create new freeze

5. 61 registry unavailable before run
→ decision-critical run cannot start normally

6. configuration promotion happens between INPUT_FREEZE and DECISION_FREEZE
→ current run unchanged

7. PAPER config promoted to LIVE without required approval
→ LIVE binding not created

8. emergency conservative minimum-cash increase
→ effective binding created
→ downstream Risk Governor tightens

9. expired emergency override
→ explicit previous approved binding restored/resolved

10. identical historical manifest replay
→ identical configuration snapshot hash
→ identical engine input policy hashes
```

---

## 46. Property / invariant tests

```text
For every finalized run:

exactly one frozen configuration snapshot exists

all mandatory decision nodes reference that snapshot
or an explicitly declared namespace sub-snapshot

all used versions satisfy:
known_at <= run evaluation_time

every ACTIVE binding is approved

historical replay does not resolve versions
that were not active at historical time
```

---

## 47. Failure-injection tests

Inject:

```text
registry DB unavailable
stale replica
conflicting ACTIVE bindings
corrupted configuration hash
schema version mismatch
expired cache
clock skew
partial bundle
approval row missing
```

Expected behavior:

```text
never silently fall back to permissive config
never mix bundle versions accidentally
never use future binding
block new risk where critical configuration cannot be trusted
preserve already frozen immutable runs where safe
```

---

## 48. Migration plan from scattered configuration

Implementation should be staged.

### Phase 1 — inventory

Search repository for:

```text
numeric constants
threshold literals
weights
risk limits
cutoffs
window sizes
retry counts
SLO targets
```

Classify each as:

```text
CODE CONSTANT
ALGORITHM CONSTANT
CONFIGURATION PARAMETER
SAFETY LIMIT
```

Not every numeric constant belongs in Engine 61; mathematical constants remain code.

### Phase 2 — critical configuration first

Migrate:

```text
54 Risk Governor
55 Operational Resilience
56 Runtime cutoffs
42 Signal thresholds
44 Portfolio hard limits
53 Drawdown limits
```

### Phase 3 — execution / analytics / monitoring

Migrate 34/46/47/58/59/60 policies.

### Phase 4 — reject hidden runtime constants

Add static/code review checks for known decision-relevant literals where practical.

---

## 49. Example ADE PAPER policy snapshot

Illustrative only; values remain policy-controlled:

```yaml
environment: PAPER
market: KR
portfolio: ADE_PAPER_01

portfolio:
  leverage_allowed: false
  minimum_cash_weight: 0.10
  single_name_max_weight: 0.10
  daily_new_positions_max: 1

signal:
  alpha_min: 65
  confidence_min: 60
  adjusted_signal_min: 55

execution:
  max_adv_participation: 0.01

reporting:
  official_benchmark_required: true
```

This YAML is only a rendered representation. The authoritative source is the immutable Engine 61 snapshot and its hash.

---

## 50. Explainability

Every resolved value must answer:

```text
parameter
resolved value
unit
source version
source binding
scope
approval state
known_at
effective interval
why this scope won
whether a parent safety rule constrained it
```

Example:

```text
Parameter
ade.portfolio.minimum_cash.weight

Resolved
15%

Source
portfolio ADE_PAPER_01 policy v4

Parent
GLOBAL minimum 10%

Resolution
portfolio override permitted
15% is more conservative

Effective
2026-09-01 00:00 KST
```

---

## 51. Audit requirements

Every material lifecycle event is append-only:

```text
CREATE_VERSION
VALIDATE
REQUEST_APPROVAL
APPROVE
REJECT
SCHEDULE
ACTIVATE
SUPERSEDE
ROLLBACK
QUARANTINE
EXPIRE_OVERRIDE
RESOLVE_SNAPSHOT
DETECT_DRIFT
```

Each event records previous-event hash where supported, allowing tamper-evident audit chains.

---

## 52. Security and authorization

Configuration write paths require role-based authorization.

Example roles:

```text
CONFIG_READER
CONFIG_AUTHOR
ENGINE_OWNER
RISK_APPROVER
GOVERNANCE_APPROVER
LIVE_OPERATOR
EMERGENCY_OPERATOR
AUDITOR
```

Read access to runtime configuration can be broad; mutation access must be narrow.

Runtime application credentials should be read-only for configuration definitions and snapshots.

---

## 53. Core invariants

```text
Unversioned decision configuration = 0

Unapproved ACTIVE configuration = 0

Critical missing configuration
silently defaulted = 0

Future configuration used in past decision = 0

Current configuration used in official historical replay = 0

Mid-run configuration mutation = 0

Overlapping ACTIVE bindings for same scope/namespace = 0

Parent hard safety limit relaxed by ordinary child override = 0

PAPER ACTIVE automatically treated as LIVE ACTIVE = 0

Emergency override without expiry = 0
unless explicitly permanent and normally approved

Runtime hash != frozen snapshot hash
accepted silently = 0

Historical configuration version mutated = 0
Historical binding mutated = 0
Historical snapshot mutated = 0

Same scope + environment + evaluation_time
+ same registry state
→ same resolved values
→ same snapshot hash
```

---

## 54. Implementation order

```text
1 ParameterDefinition / Namespace immutable models
2 DB migrations
3 Units and type validation
4 Version lifecycle
5 Scope hierarchy
6 Effective-dating resolver
7 Policy bundles / cross-field validation
8 Snapshot materialization and hashing
9 Engine 56 freeze integration
10 Engine 54/55 critical configuration integration
11 Change request / semantic diff
12 Dependency impact graph
13 Approval workflow
14 Environment promotion
15 Emergency override
16 Rollback
17 Drift detection
18 Repository-wide configuration inventory and migration
19 Integration / PIT replay tests
20 Control Tower telemetry
```

---

## 55. Acceptance criteria for v1

Engine 61 v1 is implementation-ready when:

```text
- all decision-critical parameters have stable keys and schemas;
- Signal, Risk Governor, Operational and Orchestration critical policies can be resolved point-in-time;
- Engine 56 can freeze one immutable configuration snapshot per run;
- mid-run policy promotion cannot change the running decision;
- historical replay resolves historical ACTIVE configuration;
- missing critical configuration blocks new risk rather than defaulting permissively;
- PAPER and LIVE bindings are independently governed;
- configuration diffs and dependency impact are auditable;
- rollback creates new bindings without rewriting history;
- runtime drift is detectable by snapshot hash;
- deterministic replay tests pass.
```

---

## 56. Relationship to Engines 54~60

```text
54 Risk Governor
What financial risk limits apply?
        ↑
61 supplies the approved limit values

55 Operational Resilience
Can the system be trusted?
        ↑
61 supplies operational policy values
and reports configuration health

56 Runtime Coordinator
Which exact settings does this run use?
        ↑
61 resolves + freezes them

57 Decision Ledger
Why did the decision happen?
        ↑
configuration snapshot becomes evidence

58 Reporting
What official result is recorded?
        ↑
report policy comes from 61

59 Analytics
How is performance measured?
        ↑
metric definitions/windows are versioned in 61

60 Control Tower
Is ADE operating within tolerance?
        ↑
SLO/alert parameters come from 61
and configuration drift becomes telemetry
```

Engine 61 therefore removes a major source of hidden non-determinism from ADE: uncontrolled configuration.

---

## 57. Next engine

A natural next step is:

**62. Master Data, Semantic Contract & Schema Evolution Engine**

Engine 61 governs configuration values. Engine 62 should govern the meaning and compatibility of the data objects those values operate on: canonical field definitions, units, entity identifiers, schemas, contracts, version compatibility, producer/consumer lineage and backward-compatible migrations.

Together:

```text
61
What exact approved configuration applies?

62
What exactly does each data field/object mean,
and can producers/consumers safely exchange it?
```

This prevents a future ADE version from being reproducible at the policy layer while silently changing the semantic meaning of inputs underneath it.
