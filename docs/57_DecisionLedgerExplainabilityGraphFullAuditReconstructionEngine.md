# 57. Decision Ledger, Explainability Graph & Full Audit Reconstruction Engine v1

## 1. Purpose

Engine 57 is ADE's authoritative decision-ledger, explainability-graph, and full-audit reconstruction layer.

It answers:

> For one BUY, ADD, HOLD, REDUCE, EXIT, REJECT, or NO_ACTION decision, can ADE reconstruct exactly which point-in-time data, features, models, policies, risk limits, portfolio state, operational state, orchestration run, and execution assumptions caused that outcome?

Engine 57 does not generate alpha, alter a decision, override risk, or execute an order. It turns already-finalized ADE evidence into an immutable causal/audit graph and human-readable explanation package.

Core principles:

```text
A decision without lineage is not auditable.

A human-readable explanation without machine-verifiable evidence is not sufficient.

NO_ACTION is a first-class decision and must be explainable.

Explanation must describe what actually happened in the engine,
not invent a plausible story after the fact.

Same frozen decision + same evidence graph policy
→ same ledger entry + same explanation graph + same hash.
```

---

## 2. Position in ADE architecture

```text
38~41 Feature Engines
        ↓
42 Signal Integration
        ↓
43 Regime Adaptation
        ↓
51 Strategy Ensemble
        ↓
52 Stress Testing
        ↓
53 Capital Preservation
        ↓
55 Operational Resilience
        ↓
54 Risk Governor
        ↓
44 Portfolio Construction
        ↓
45 Trade Lifecycle
        ↓
23 Decision / Position Sizing
        ↓
56 Decision Orchestration
        ↓
Decision Freeze / Run Manifest
        ↓
┌──────────────────────────────────────────────┐
│ 57 Decision Ledger & Explainability Graph   │
├──────────────────────────────────────────────┤
│ Decision Ledger                              │
│ Evidence Registry                            │
│ Causal / Dependency Graph                    │
│ Reason-Code Resolution                       │
│ Counterfactual Boundary                      │
│ Human Explanation                            │
│ Machine Audit Bundle                         │
│ Historical Reconstruction                    │
│ Integrity Verification                       │
└──────────────────────────────────────────────┘
        ↓
12 Reporting / Audit / Governance / Research
        ↓
External review or internal post-mortem
```

Engine 56 proves that the pipeline ran with the correct timing and dependencies. Engine 57 proves why the resulting decision was what it was.

---

## 3. Responsibility boundary

### 57 does

- create one immutable ledger entry for every finalized decision;
- preserve BUY, ADD, HOLD, REDUCE, EXIT, REJECT, and NO_ACTION outcomes;
- register every evidence object that materially participated in the decision;
- connect evidence objects through a directed explainability graph;
- distinguish causal, constraining, supporting, contextual, and excluded evidence;
- resolve reason-code hierarchy and binding reasons;
- reconstruct the exact active model/policy/version lineage;
- reconstruct the exact point-in-time portfolio and risk state;
- prove which information was excluded because it arrived late or failed validation;
- generate deterministic human-readable explanation summaries;
- export machine-verifiable audit bundles;
- verify graph completeness and hash integrity;
- support historical replay and post-mortem reconstruction.

### 57 does not

- create new trading signals;
- modify Alpha or Confidence;
- change risk limits;
- select a different candidate after seeing the outcome;
- rewrite a frozen decision;
- use future market outcomes to justify the original decision;
- silently infer missing evidence;
- replace Engine 49 outcome attribution;
- replace Engine 48 governance approvals.

---

## 4. First-class decision types

Every finalized portfolio/security decision has an explicit type.

```text
BUY
ADD
HOLD
REDUCE
EXIT
FORCE_EXIT
REJECT
NO_ACTION
```

`NO_ACTION` must have a subtype.

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

This prevents all inactive outcomes from collapsing into one ambiguous bucket.

---

## 5. Decision Ledger contract

Every finalized decision creates one immutable ledger object.

```python
DecisionLedgerEntry(
    decision_id,
    run_id,
    portfolio_id,
    security_id,
    strategy_id,
    trading_date,
    evaluation_time,
    decision_type,
    decision_subtype,
    decision_state,
    requested_action,
    approved_action,
    target_weight,
    target_quantity,
    execution_earliest_time,
    primary_reason_code,
    binding_constraint_id,
    decision_snapshot_id,
    decision_manifest_hash,
    created_at,
)
```

A portfolio-level NO_ACTION may have `security_id = NULL`, while security-specific REJECT decisions retain the security identity.

---

## 6. Evidence object model

Every material input becomes a typed evidence node.

```text
RAW_DATA
NORMALIZED_DATA
FUNDAMENTAL_SNAPSHOT
FACTOR_SNAPSHOT
EXPECTATION_SNAPSHOT
MARKET_BEHAVIOR_SNAPSHOT
REGIME_SNAPSHOT
SIGNAL_SNAPSHOT
STRATEGY_ALLOCATION_SNAPSHOT
STRESS_SNAPSHOT
DRAWDOWN_SNAPSHOT
OPERATIONAL_HEALTH_SNAPSHOT
RISK_ENVELOPE
PORTFOLIO_SNAPSHOT
LIFECYCLE_SNAPSHOT
DECISION_SNAPSHOT
EXECUTION_CONTEXT
POLICY_ARTIFACT
MODEL_ARTIFACT
GOVERNANCE_BINDING
ORCHESTRATION_FREEZE
REASON_EVENT
EXCLUDED_EVIDENCE
```

Common contract:

```python
EvidenceNode(
    evidence_id,
    evidence_type,
    source_engine,
    source_snapshot_id,
    entity_type,
    entity_id,
    observed_at,
    known_at,
    valid_from,
    valid_until,
    status,
    value_digest,
    artifact_version,
    policy_hash,
    model_hash,
    evidence_hash,
)
```

---

## 7. Explainability graph

The graph is directed and typed.

```text
Raw Data
   ↓ DERIVED_FROM
Feature
   ↓ CONTRIBUTES_TO
Family Score
   ↓ CONTRIBUTES_TO
Alpha / Confidence
   ↓ EVALUATED_BY
Candidate Gate
   ↓ CONSTRAINED_BY
Risk Governor
   ↓ CONSTRAINED_BY
Portfolio Construction
   ↓ RESOLVED_AS
Decision
```

Graph edge types:

```text
DERIVED_FROM
NORMALIZED_FROM
CONTRIBUTES_TO
SUPPORTS
OPPOSES
CONSTRAINS
BLOCKS
OVERRIDES
SELECTED_BY
EXCLUDED_BY
SUPERSEDES
DEPENDS_ON
BOUND_BY
RESOLVED_AS
EXECUTES_AS
ATTRIBUTED_TO
```

Every edge may contain quantitative contribution metadata.

```python
EvidenceEdge(
    edge_id,
    from_evidence_id,
    to_evidence_id,
    edge_type,
    contribution_value,
    contribution_unit,
    rank,
    is_binding,
    reason_code,
    edge_hash,
)
```

---

## 8. Causal evidence vs contextual evidence

The graph must distinguish evidence that actually changed the outcome from evidence that was merely informative.

```text
CAUSAL
CONSTRAINING
SUPPORTING
OPPOSING
CONTEXTUAL
EXCLUDED
```

Example:

```text
Samsung Alpha = 81
Confidence = 87
Candidate = ELIGIBLE

Risk Headroom = 0%
BUY Permission = BLOCKED

Result = NO_ACTION
```

In this case:

```text
Signal evidence
→ SUPPORTING

Risk headroom constraint
→ CAUSAL + BINDING

Macro news not consumed by any active feature
→ CONTEXTUAL or EXCLUDED
```

The explanation must not claim that contextual news caused the decision.

---

## 9. Binding reason resolution

A decision may have many reason codes. Engine 57 resolves a deterministic primary/binding reason hierarchy.

Default precedence:

```text
1 SYSTEM / GOVERNANCE SAFETY
2 DATA / TEMPORAL INTEGRITY
3 OPERATIONAL SAFETY
4 SURVIVAL / CAPITAL PRESERVATION
5 HARD PORTFOLIO RISK
6 REGIME / STRATEGY RISK
7 SIGNAL / CONFIDENCE
8 PORTFOLIO OPTIMIZATION
9 EXECUTION FEASIBILITY
10 INFORMATIONAL CONTEXT
```

Example:

```text
ALPHA_STRONG
CONFIDENCE_HIGH
RISK_OFF
CRITICAL_MARKET_DATA_STALE

Primary reason
= CRITICAL_MARKET_DATA_STALE
```

A strong Alpha is preserved in the graph but cannot become the primary explanation when a higher-priority hard block exists.

---

## 10. Positive and negative evidence balance

Human explanations must show both supporting and opposing evidence when both materially existed.

Example:

```text
Supporting
- Expectations revision positive
- 60D relative strength positive
- Alpha 78

Opposing
- Confidence 58 below threshold
- RISK_OFF regime

Binding
- Confidence minimum = 65

Decision
- REJECTED_CONFIDENCE
```

This prevents explanations from becoming one-sided post-hoc narratives.

---

## 11. Excluded evidence ledger

One of the most important audit features is proving what ADE did **not** use.

Excluded evidence reason codes include:

```text
ARRIVED_AFTER_INPUT_FREEZE
KNOWN_AFTER_DECISION_CUTOFF
FUTURE_INFORMATION
SOURCE_CONFLICT
STALE_DATA
SCHEMA_INVALID
PERIOD_MISMATCH
SCOPE_MISMATCH
FAILED_DEPENDENCY
QUARANTINED_ARTIFACT
NOT_ACTIVE_AT_DECISION_TIME
RESEARCH_ONLY_ARTIFACT
```

Example:

```text
16:24 Decision Freeze
16:31 earnings release arrives

→ earnings release stored as evidence
→ status = EXCLUDED
→ reason = ARRIVED_AFTER_INPUT_FREEZE
```

The old decision remains unchanged.

---

## 12. Point-in-time audit reconstruction

Historical reconstruction must resolve all objects using their original decision time.

```text
Decision Time T
        ↓
Active Governance Binding at T
Active Policy at T
Active Model at T
Universe at T
Portfolio at T
Market Data known by T
Features known by T
Risk Envelope at T
Operational Health at T
```

Forbidden:

```text
current ACTIVE model → past decision
current Universe → past decision
latest corrected financials → original decision
current risk policy → historical decision
future outcome → original explanation
```

Historical audit reconstructs the original decision, not a modern reinterpretation.

---

## 13. Decision proof bundle

Each decision can export a machine-verifiable proof bundle.

```text
decision.json
run_manifest.json
input_freeze.json
feature_manifest.json
signal_snapshot.json
risk_envelope.json
portfolio_snapshot.json
operational_health.json
governance_bindings.json
reason_events.json
evidence_nodes.json
evidence_edges.json
excluded_evidence.json
explanation.json
checksums.json
```

The bundle root hash is:

```text
DecisionProofHash
= H(
    sorted(component_hashes)
  + decision_id
  + run_id
  + evaluation_time
  + schema_version
)
```

---

## 14. Merkle-style evidence integrity

For large graphs, Engine 57 may use hierarchical hashes.

```text
Raw Evidence Hashes
        ↓
Feature Manifest Hash
        ↓
Signal Manifest Hash
        ↓
Risk Manifest Hash
        ↓
Decision Manifest Hash
        ↓
Decision Proof Root Hash
```

Changing one historical input must change the root hash.

Historical objects themselves remain immutable; a corrected replay creates a new proof bundle.

---

## 15. Explanation levels

Engine 57 generates several deterministic explanation levels.

```text
L0 SUMMARY
L1 DECISION REASONS
L2 SIGNAL / RISK DETAIL
L3 FULL EVIDENCE TRACE
L4 MACHINE AUDIT BUNDLE
```

Example L0:

```text
NO_ACTION because the candidate passed the signal gate but the central Risk Governor blocked new risk under RISK_OFF conditions.
```

Example L1:

```text
Candidate: ELIGIBLE
Alpha: 78
Confidence: 84
Risk State: RISK_OFF
BUY Permission: BLOCKED
Binding constraint: STRESS_LIMIT
Final decision: NO_ACTION / RISK_BLOCKED
```

L3 can traverse all contributing features and source snapshots.

---

## 16. Explanation generation rules

Human text must be generated from structured graph facts only.

Required rules:

```text
No unsupported causal language.
No invented score.
No missing threshold invention.
No future outcome in original explanation.
No contextual evidence promoted to causal evidence.
No hidden hard block.
No omission of binding reason.
```

Template variables must point to exact graph nodes.

---

## 17. Explainability contribution model

When engines provide contribution values, Engine 57 preserves them.

Example:

```text
Alpha = 74

Quality       +18
Valuation     +14
Expectations  +17
Behavior      +29
Conflict       -4
```

The graph stores:

```text
QUALITY_SCORE --(+18)--> ALPHA
VALUATION_SCORE --(+14)--> ALPHA
EXPECTATIONS_SCORE --(+17)--> ALPHA
BEHAVIOR_SCORE --(+29)--> ALPHA
CONFLICT --(-4)--> ALPHA
```

Engine 57 does not recompute these contributions; it validates and displays them.

---

## 18. Constraint explainability

For portfolio and risk decisions, the explanation must show projected-before/after values.

Example:

```text
Sector cap          20%
Current sector      18%
Proposed BUY         5%
Projected sector    23%

→ exceeds cap by 3%p
→ order resized or rejected
```

This is superior to a generic `SECTOR_LIMIT_BINDING` label alone.

---

## 19. NO_ACTION explainability

A NO_ACTION ledger entry must answer four questions.

```text
1 Was there a candidate?
2 If yes, did Signal approve it?
3 If yes, what downstream gate blocked it?
4 If no candidate, why were candidates rejected?
```

Examples:

```text
NO_CANDIDATE
→ 0 securities passed Signal gate

RISK_BLOCKED
→ 2 securities passed Signal
→ BUY permission BLOCKED by Risk Governor

DATA_BLOCKED
→ Signal not computed because required PIT snapshot missing

MARKET_CLOSED
→ no trading session; no decision sample counted for signal quality
```

---

## 20. Order and execution lineage

If a decision generates an order, lineage continues.

```text
Decision
→ Approved Target
→ Order Intent
→ Pre-Trade Risk Check
→ Broker/Paper Order
→ Fill Events
→ Portfolio Accounting
```

Engine 57 records the mapping but does not replace Engines 34/46/19.

For partial fills:

```text
Decision BUY 100
Order approved 100
Filled 65
Remaining 35
```

The audit graph must not imply that the portfolio received 100 shares.

---

## 21. Outcome boundary

Engine 49 owns outcome attribution. Engine 57 may link later outcomes but must keep the original decision explanation frozen.

```text
Decision Explanation at T
        ↓ immutable
Outcome at T+20D
        ↓
49 Attribution
        ↓
linked as AFTER-THE-FACT OUTCOME
```

An outcome edge may be:

```text
ATTRIBUTED_TO
VALIDATED_BY_OUTCOME
CONTRADICTED_BY_OUTCOME
```

but never changes the original reason graph.

---

## 22. Counterfactual boundary

Engine 57 may display counterfactuals generated by approved engines, but must label them explicitly.

```text
ACTUAL DECISION
NO_ACTION

COUNTERFACTUAL
If stress multiplier had been 1.00 instead of 0.40,
projected BUY capacity would have been 6%.
```

Counterfactual nodes cannot be merged into the actual causal path.

```text
actual_graph != counterfactual_graph
```

---

## 23. Decision graph completeness checks

Before a ledger entry is FINALIZED, Engine 57 verifies required paths.

For BUY:

```text
Signal Snapshot
Risk Envelope
Portfolio Snapshot
Operational Health
Orchestration Freeze
Decision Snapshot
```

must all exist.

For DATA_BLOCKED NO_ACTION:

```text
failed/missing dependency evidence
Operational Health or Orchestration evidence
Decision Snapshot
```

must exist.

Missing mandatory lineage produces:

```text
AUDIT_GRAPH_INCOMPLETE
```

and prevents audit-finalized status.

---

## 24. Graph cycle rules

The causal graph must be acyclic within one decision time.

Allowed cross-time link:

```text
Decision T
→ Outcome T+20D
```

Not allowed:

```text
Outcome T+20D
→ original Signal T
→ original Decision T
```

A detected same-decision causal cycle produces:

```text
EXPLAINABILITY_GRAPH_CYCLE
```

---

## 25. Database design

Primary tables:

```text
decision_ledger_entries

decision_evidence_nodes
decision_evidence_edges

decision_reason_resolutions
decision_binding_constraints

decision_excluded_evidence

decision_explanation_snapshots

decision_audit_bundles
decision_audit_bundle_members

decision_integrity_checks

decision_reconstruction_runs

decision_audit_reason_events
decision_audit_manifests
```

---

## 26. `decision_ledger_entries`

```text
decision_id              PK
run_id
portfolio_id
security_id              nullable
strategy_id              nullable
trading_date
evaluation_time

decision_type
decision_subtype
decision_state

requested_action
approved_action

target_weight
target_quantity
execution_earliest_time

primary_reason_code
binding_constraint_id

orchestration_freeze_id
decision_snapshot_id

schema_version
created_at

ledger_hash
```

Unique constraint example:

```text
(run_id, portfolio_id, security_id, decision_type, decision_snapshot_id)
```

---

## 27. `decision_evidence_nodes`

```text
evidence_id              PK
decision_id

evidence_type
source_engine
source_snapshot_id

entity_type
entity_id

observed_at
known_at
valid_from
valid_until

status
causal_role

artifact_version
policy_hash
model_hash

value_digest
evidence_hash
```

`causal_role`:

```text
CAUSAL
CONSTRAINING
SUPPORTING
OPPOSING
CONTEXTUAL
EXCLUDED
```

---

## 28. `decision_evidence_edges`

```text
edge_id                  PK
decision_id
from_evidence_id
to_evidence_id

edge_type
contribution_value
contribution_unit

is_binding
rank
reason_code

edge_hash
```

Foreign keys require both nodes to belong to the same decision graph unless explicitly marked as cross-decision/cross-time linkage.

---

## 29. `decision_reason_resolutions`

```text
resolution_id
decision_id

reason_code
reason_category
priority
severity

source_engine
source_evidence_id

is_primary
is_binding

resolution_order
resolution_hash
```

Exactly one primary reason is required for a finalized decision.

---

## 30. `decision_excluded_evidence`

```text
excluded_id
decision_id

source_type
source_id
known_at
received_at

exclusion_reason
exclusion_engine

would_have_affected_stage

content_hash
exclusion_hash
```

This table is crucial for defending the temporal integrity of past decisions.

---

## 31. `decision_explanation_snapshots`

```text
explanation_id
decision_id

explanation_level
language
schema_version

template_version

structured_facts_json
rendered_text

source_graph_hash
explanation_hash
created_at
```

Rendered text is immutable for a given explanation version. A better wording template creates a new explanation snapshot without rewriting the original decision.

---

## 32. `decision_audit_bundles`

```text
bundle_id
decision_id

bundle_version
created_at

ledger_hash
graph_root_hash
run_manifest_hash
policy_manifest_hash
model_manifest_hash

proof_root_hash
integrity_state

bundle_hash
```

---

## 33. Reconstruction run model

Historical reconstruction is separate from original creation.

```python
DecisionReconstructionRequest(
    decision_id,
    reconstruction_time,
    mode="ORIGINAL_AS_OF",
    verify_hashes=True,
    regenerate_text=False,
)
```

Modes:

```text
ORIGINAL_AS_OF
VERIFY_ONLY
FULL_GRAPH_REBUILD
COMPARE_TO_REPLAY
```

`ORIGINAL_AS_OF` must use the original frozen bindings and evidence.

---

## 34. Core algorithm

```python
def build_decision_audit(ctx):
    decision = load_frozen_decision(ctx.decision_id)
    run = load_orchestration_manifest(decision.run_id)

    assert_decision_is_frozen(decision)
    verify_run_manifest(run)

    evidence = collect_material_evidence(
        decision=decision,
        run=run,
    )

    evidence = classify_causal_roles(
        decision=decision,
        evidence=evidence,
    )

    excluded = collect_excluded_evidence(
        decision=decision,
        run=run,
    )

    graph = build_typed_evidence_graph(
        decision=decision,
        evidence=evidence,
        excluded=excluded,
    )

    verify_temporal_integrity(graph, decision.evaluation_time)
    verify_no_illegal_cycles(graph)
    verify_required_lineage(graph, decision)

    reasons = resolve_reason_hierarchy(
        decision=decision,
        graph=graph,
    )

    explanation = render_explanation_from_graph(
        decision=decision,
        graph=graph,
        reasons=reasons,
    )

    bundle = build_proof_bundle(
        decision=decision,
        run=run,
        graph=graph,
        reasons=reasons,
        explanation=explanation,
    )

    verify_bundle_integrity(bundle)

    return finalize_immutable_audit_snapshot(bundle)
```

---

## 35. Reason hierarchy algorithm

```python
def resolve_primary_reason(reason_events, policy):
    eligible = [
        r for r in reason_events
        if r.material_to_decision
    ]

    eligible.sort(
        key=lambda r: (
            policy.category_priority[r.category],
            -r.severity,
            r.source_engine,
            r.reason_code,
        )
    )

    primary = eligible[0]

    return primary
```

Tie-breaking must be deterministic.

---

## 36. Human explanation renderer

Renderer takes structured facts only.

```python
def render_summary(decision, graph, primary_reason):
    facts = select_summary_facts(
        graph=graph,
        decision=decision,
        max_supporting=3,
        max_opposing=3,
    )

    return template_engine.render(
        template_id=decision_template(decision),
        decision=decision,
        primary_reason=primary_reason,
        facts=facts,
    )
```

The renderer cannot query arbitrary current market data.

---

## 37. Code structure

```text
decision_audit/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── repository.py
├── engine.py
│
├── adapters/
│   ├── orchestration.py
│   ├── fundamentals.py
│   ├── factors.py
│   ├── expectations.py
│   ├── market_behavior.py
│   ├── signals.py
│   ├── regime.py
│   ├── strategy.py
│   ├── stress.py
│   ├── drawdown.py
│   ├── operational_health.py
│   ├── risk_governor.py
│   ├── portfolio.py
│   ├── lifecycle.py
│   ├── execution.py
│   ├── governance.py
│   └── outcomes.py
│
├── ledger.py
├── evidence_registry.py
├── evidence_collector.py
├── causal_roles.py
├── graph.py
├── edges.py
├── excluded.py
├── temporal.py
├── reason_resolution.py
├── binding_reasons.py
│
├── completeness.py
├── cycles.py
├── integrity.py
│
├── explanations/
│   ├── facts.py
│   ├── templates.py
│   ├── summary.py
│   ├── detailed.py
│   └── renderer.py
│
├── bundles/
│   ├── builder.py
│   ├── checksums.py
│   ├── merkle.py
│   └── exporter.py
│
├── reconstruction.py
├── replay_compare.py
├── reason_codes.py
├── manifest.py
└── hashing.py
```

---

## 38. API contracts

### Get decision explanation

```python
GetDecisionExplanationRequest(
    decision_id,
    level="L1",
    language="ko",
)
```

```python
GetDecisionExplanationResult(
    decision_id,
    decision_type,
    primary_reason,
    supporting_facts,
    opposing_facts,
    binding_constraints,
    rendered_text,
    graph_hash,
    explanation_hash,
)
```

### Reconstruct decision

```python
ReconstructDecisionRequest(
    decision_id,
    mode="ORIGINAL_AS_OF",
)
```

```python
ReconstructDecisionResult(
    integrity_state,
    original_decision_hash,
    reconstructed_decision_hash,
    graph_match,
    missing_evidence,
    mismatched_hashes,
)
```

---

## 39. Integrity states

```text
VERIFIED
VERIFIED_WITH_NONMATERIAL_GAPS
INCOMPLETE
HASH_MISMATCH
TEMPORAL_VIOLATION
GRAPH_INVALID
UNRECONSTRUCTABLE
```

Only `VERIFIED` and policy-approved `VERIFIED_WITH_NONMATERIAL_GAPS` may be marked audit-valid.

---

## 40. Key reason codes

```text
DECISION_AUDIT_VERIFIED
DECISION_AUDIT_INCOMPLETE

PRIMARY_REASON_RESOLVED
BINDING_CONSTRAINT_RESOLVED

AUDIT_GRAPH_INCOMPLETE
EXPLAINABILITY_GRAPH_CYCLE
EVIDENCE_HASH_MISMATCH
RUN_MANIFEST_HASH_MISMATCH
DECISION_HASH_MISMATCH

FUTURE_EVIDENCE_IN_GRAPH
LATE_EVIDENCE_EXCLUDED
EXCLUDED_EVIDENCE_MISSING_REASON

CONTEXTUAL_EVIDENCE_PROMOTED_TO_CAUSAL
UNSUPPORTED_CAUSAL_CLAIM

MISSING_SIGNAL_LINEAGE
MISSING_RISK_LINEAGE
MISSING_PORTFOLIO_LINEAGE
MISSING_OPERATIONAL_LINEAGE
MISSING_ORCHESTRATION_LINEAGE

MULTIPLE_PRIMARY_REASONS
PRIMARY_REASON_NOT_MATERIAL

NO_ACTION_SUBTYPE_REQUIRED
NO_ACTION_CAUSE_UNRESOLVED

COUNTERFACTUAL_MIXED_WITH_ACTUAL
OUTCOME_CONTAMINATED_ORIGINAL_EXPLANATION

HISTORICAL_BINDING_MISMATCH
CURRENT_ARTIFACT_USED_IN_HISTORICAL_AUDIT

AUDIT_BUNDLE_VERIFIED
AUDIT_BUNDLE_ROOT_HASH_MISMATCH
```

---

## 41. Unit test plan

```text
A. BUY decision with full lineage
→ graph complete
→ one primary reason
→ VERIFIED

B. Alpha strong / Risk Governor blocked
→ Signal shown as supporting
→ Risk block primary

C. NO_ACTION / NO_CANDIDATE
→ subtype required
→ candidate count = 0 evidence present

D. NO_ACTION / DATA_BLOCKED
→ missing PIT snapshot represented as cause
→ no invented Alpha

E. Market closed
→ MARKET_CLOSED subtype
→ no signal-quality causal claim

F. Late earnings event after freeze
→ excluded evidence node
→ original explanation unchanged

G. Contextual macro news present but not consumed
→ CONTEXTUAL
→ cannot become primary reason

H. Missing Risk Governor snapshot for BUY
→ AUDIT_GRAPH_INCOMPLETE

I. Same-decision graph cycle
→ GRAPH_INVALID

J. One historical evidence row mutated
→ root hash mismatch

K. Two primary reasons
→ FINALIZATION blocked

L. Partial fill 65 / ordered 100
→ execution lineage shows 65 actual shares

M. Counterfactual result
→ separate graph branch
→ actual graph unchanged

N. 20D outcome linked later
→ original explanation hash unchanged

O. Explanation regenerated with new template
→ new explanation snapshot
→ same decision ledger hash

P. Historical reconstruction
→ original model/policy bindings restored

Q. Current ACTIVE model supplied to old decision
→ blocked

R. identical frozen decision replay
→ identical graph root hash
```

---

## 42. Integration test plan

### Scenario 1 — Signal approved, risk blocked

```text
Alpha                 82
Confidence            86
Candidate              ELIGIBLE
Risk State             RISK_OFF
BUY Permission         BLOCKED
Decision               NO_ACTION
```

Expected:

```text
primary reason = RISK_GOVERNOR_RISK_OFF
signal evidence = SUPPORTING
risk evidence = CAUSAL / BINDING
NO_ACTION subtype = RISK_BLOCKED
```

### Scenario 2 — Data block before Signal

```text
Factor Snapshot       missing
Signal                NOT_COMPUTED
Decision              NO_ACTION
```

Expected:

```text
NO_ACTION subtype = DATA_BLOCKED
primary reason = MISSING_REQUIRED_PIT_SNAPSHOT
no fabricated signal value
```

### Scenario 3 — order resized

```text
Target BUY             10%
Sector current         18%
Sector hard cap        20%
Approved target         2%
```

Expected graph:

```text
Portfolio target 10%
→ constrained by sector cap
→ resized to 2%
→ BUY 2%
```

### Scenario 4 — Operational block

```text
Signal ELIGIBLE
Financial risk NORMAL
Accounting reconciliation FAILED
```

Expected:

```text
primary reason = ACCOUNTING_RECONCILIATION_FAILED
BUY blocked
Alpha remains visible but non-binding
```

### Scenario 5 — emergency risk reduction

```text
Alpha high
Existing position
Survival state CRITICAL
Action REDUCE
```

Expected:

```text
Capital preservation path primary
Signal path contextual/supporting only
REDUCE allowed despite BUY block
```

---

## 43. Property-based tests

For arbitrary valid graphs:

```text
exactly one primary reason for finalized decision
all binding edges terminate in a decision ancestor
all evidence known_at <= allowed cutoff unless EXCLUDED
all actual causal nodes are reachable from decision root
no same-decision causal cycles
all hashes deterministic under stable sorting
```

Generate randomized graph permutations and verify output hash is invariant to input ordering.

---

## 44. Temporal tests

```text
Decision cutoff        16:20
Evidence known_at      16:19:59
→ allowed

Evidence known_at      16:20:01
→ actual causal graph forbidden
→ EXCLUDED

Correction published next day
→ original evidence unchanged
→ corrected replay gets new decision/audit bundle
```

---

## 45. Negative tests

```text
invent missing Alpha in explanation
→ fail

promote news headline to causal evidence without edge
→ fail

use future return in original rationale
→ fail

omit hard binding risk reason
→ fail

rewrite old rendered explanation in place
→ fail

attach current policy to historical decision
→ fail

merge counterfactual path into actual path
→ fail
```

---

## 46. Performance considerations

Decision graphs can become large. v1 should optimize for deterministic correctness first.

Recommended approach:

```text
hot path
→ write ledger IDs + manifest references

post-finalization audit path
→ materialize detailed graph

report path
→ query precomputed explanation snapshots
```

The decision itself must not wait for expensive L3/L4 rendering if the required raw lineage IDs are already frozen.

---

## 47. Indexing strategy

Recommended indexes:

```text
decision_ledger_entries(run_id)
decision_ledger_entries(portfolio_id, evaluation_time)
decision_ledger_entries(security_id, evaluation_time)

decision_evidence_nodes(decision_id, evidence_type)
decision_evidence_nodes(source_engine, source_snapshot_id)

decision_evidence_edges(decision_id, from_evidence_id)
decision_evidence_edges(decision_id, to_evidence_id)

decision_reason_resolutions(decision_id, is_primary)

decision_excluded_evidence(decision_id, exclusion_reason)
```

---

## 48. Retention policy

Decision ledger and proof hashes are long-lived records.

```text
Decision Ledger            permanent
Reason Resolution          permanent
Manifest Hashes            permanent
Evidence Graph metadata    permanent
Rendered explanations      versioned, long-lived
Large raw payload copies   policy-dependent; reference by immutable snapshot ID
```

Do not duplicate raw market datasets unnecessarily; retain immutable source references and hashes.

---

## 49. Privacy / security boundary

Audit export must support redaction without changing the underlying internal proof.

Example:

```text
internal bundle
→ full broker/account identifiers

external audit bundle
→ pseudonymized portfolio/account IDs
→ same internal object hashes referenced through signed mapping
```

Secrets, API keys, credentials, and unrestricted personal identifiers must never enter the explainability graph.

---

## 50. Relationship to Engine 48 Governance

Engine 48 answers:

```text
Was this model/policy approved for use?
```

Engine 57 answers:

```text
Which approved model/policy actually participated in this decision?
```

The graph includes the governance binding as evidence.

---

## 51. Relationship to Engine 49 Outcome Attribution

Engine 49 answers:

```text
Was the decision good after outcomes became known?
```

Engine 57 answers:

```text
Why was the original decision made at that time?
```

These must never be conflated.

---

## 52. Relationship to Engine 56 Runtime Coordinator

Engine 56 provides:

```text
Run Specification
DAG Version
Node Inputs
Node Outputs
Cutoffs
Freeze IDs
Binding Snapshot
Run Manifest
```

Engine 57 consumes these as authoritative orchestration evidence.

Engine 57 must not reconstruct an alternative runtime ordering from intuition.

---

## 53. Report-facing schema

Daily ADE reports should eventually consume a structured explanation view such as:

```json
{
  "decision": "NO_ACTION",
  "subtype": "RISK_BLOCKED",
  "candidate": "SECURITY_123",
  "signal": {
    "alpha": 78,
    "confidence": 84,
    "state": "ELIGIBLE"
  },
  "risk": {
    "state": "RISK_OFF",
    "buy_permission": "BLOCKED",
    "binding_constraint": "STRESS_LIMIT"
  },
  "primary_reason": "RISK_GOVERNOR_RISK_OFF",
  "supporting_reasons": [
    "SIGNAL_ELIGIBLE",
    "RELATIVE_STRENGTH_POSITIVE"
  ],
  "opposing_reasons": [
    "STRESS_LIMIT_BINDING"
  ],
  "audit_hash": "..."
}
```

The report layer must display these fields rather than synthesize unsupported reasons independently.

---

## 54. Recommended implementation order

```text
1 immutable ledger models
2 database migrations
3 evidence-node registry
4 evidence-edge registry
5 orchestration adapter
6 Signal/Risk/Portfolio adapters
7 reason hierarchy
8 NO_ACTION subtype resolver
9 excluded-evidence ledger
10 graph completeness validator
11 temporal validator
12 deterministic graph hashing
13 explanation fact selector
14 deterministic text templates
15 proof-bundle builder
16 historical reconstruction
17 property-based graph tests
18 end-to-end daily report integration
```

---

## 55. Critical invariants

```text
Finalized decision without ledger entry = 0

BUY/ADD without Signal lineage = 0
BUY/ADD without Risk lineage = 0
BUY/ADD without Operational lineage = 0
BUY/ADD without Orchestration lineage = 0

NO_ACTION without subtype = 0
NO_ACTION without causal reason = 0

Future evidence in original causal graph = 0
Late evidence retroactively causal = 0

Current ACTIVE artifact in historical audit = 0

Unsupported causal statement = 0
Contextual evidence promoted to causal = 0

Multiple primary reasons = 0
Missing binding hard block in explanation = 0

Counterfactual mixed with actual path = 0
Outcome contaminating original rationale = 0

Historical ledger mutation = 0
Historical graph mutation = 0
Historical explanation overwrite = 0

Same frozen decision + same evidence policy
→ same graph
→ same primary reason
→ same proof root hash
```

---

## 56. Example — full NO_ACTION reconstruction

```text
Security
SK Hynix
        ↓
40 Expectations
positive event/revision
        ↓
41 Market Behavior
relative strength positive
        ↓
42 Signal
Alpha 79
Confidence 82
ELIGIBLE
        ↓
43 Regime
RISK_OFF
        ↓
52 Stress
HIGH_RISK
        ↓
54 Risk Governor
BUY BLOCKED
Binding = STRESS_LIMIT
        ↓
44 Portfolio Construction
No target increase
        ↓
23 Decision
NO_ACTION / RISK_BLOCKED
        ↓
56 Decision Freeze
immutable
        ↓
57 Audit
Primary reason = STRESS_LIMIT_BINDING
Supporting = ELIGIBLE_SIGNAL
Excluded = post-cutoff news
Proof root hash = H(...)
```

This explanation is materially different from saying simply "market risk was high." It identifies the exact binding constraint and preserves the fact that the security itself had a positive signal.

---

## 57. Example — full BUY reconstruction

```text
39 Factor
Value 72
Quality 81
        ↓
40 Expectations
Revision 76
        ↓
41 Behavior
Momentum 83
        ↓
42 Signal
Alpha 79
Confidence 88
Candidate ELIGIBLE
        ↓
54 Risk Governor
NORMAL
Risk Headroom 8%
BUY ALLOWED
        ↓
44 Portfolio Construction
Target 7%
Single-name cap 10%
Sector cap OK
        ↓
45 Lifecycle
ENTRY_ELIGIBLE
        ↓
23 Decision
BUY 7%
        ↓
56 Freeze
        ↓
57 Ledger / Graph
```

If next-day execution fills only 5.8%, execution lineage is appended without rewriting the original 7% target decision.

---

## 58. Definition of done for v1

Engine 57 v1 is complete when ADE can select any historical decision ID and deterministically answer:

```text
What was decided?
When was it decided?
Which data was known at that time?
Which data was explicitly excluded?
Which model/policy versions were active?
Which features and scores supported or opposed the action?
Which constraint was binding?
Why did the final action differ from the raw signal, if it did?
What portfolio state was assumed?
What operational state was assumed?
Which orchestration freeze authorized the evidence set?
Can every referenced object be hash-verified?
Can the same explanation graph be reconstructed later?
```

If any of these cannot be answered for a finalized decision, the ADE audit trail is incomplete.
