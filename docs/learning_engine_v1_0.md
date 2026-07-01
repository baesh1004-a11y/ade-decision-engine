# ADE Engine #7: Learning Engine v1.0

## Purpose

The Learning Engine is the feedback layer of ADE.

It answers:

> Which rules are working, which rules are weak, and what should be adjusted conservatively?

The engine does not automatically rewrite production strategy code. It produces auditable recommendations that can later be reviewed or applied by a controlled deployment process.

## Scope of v1.0

v1.0 supports rule-level performance learning from historical samples.

It evaluates:

- Sample count.
- Win rate.
- Average realized return.
- Average alpha versus expected return.
- Conservative rule recommendations.

## Input

```python
LearningSample(
    engine="candidate",
    rule="trend_alignment",
    action="BUY",
    expected_return=0.02,
    realized_return=0.05,
    holding_days=20,
    risk_level="LOW",
)
```

## Output

```json
{
  "engine_version": "learning-engine-v1.0.0",
  "sample_count": 30,
  "learning_score": 82,
  "action": "APPLY_CONSERVATIVE_BOOST",
  "recommendations": [
    {
      "engine": "candidate",
      "rule": "trend_alignment",
      "sample_count": 10,
      "win_rate": 0.7,
      "avg_return": 0.035,
      "avg_alpha": 0.012,
      "recommendation": "BOOST_WEIGHT",
      "confidence": 1.0,
      "reason": "Rule has strong win rate and non-negative alpha"
    }
  ],
  "weak_rules": [],
  "strong_rules": ["candidate:trend_alignment"],
  "reasons": []
}
```

## Recommendations

| Recommendation | Meaning |
|---|---|
| KEEP_COLLECTING | Not enough samples yet. |
| KEEP_WEIGHT | Performance is acceptable. |
| BOOST_WEIGHT | Rule is persistently strong. |
| REDUCE_WEIGHT | Rule underperforms expected return. |
| REVIEW_OFF | Rule is weak and should be reviewed for deactivation. |

## Actions

| Action | Meaning |
|---|---|
| KEEP_CURRENT_RULES | No immediate change. |
| APPLY_CONSERVATIVE_BOOST | Strong rule can be cautiously boosted. |
| REVIEW_RULES | Weak rules should be reviewed before deployment. |

## Core Algorithm

For each `(engine, rule)` group:

```text
win_rate = positive realized returns / samples
avg_return = mean(realized_return)
avg_alpha = mean(realized_return - expected_return)
confidence = sample_count / min_samples, capped at 1.0
```

Decision logic:

```text
sample_count < min_samples
    -> KEEP_COLLECTING

win_rate >= strong_win_rate and avg_return > 0 and avg_alpha >= 0
    -> BOOST_WEIGHT

win_rate < weak_win_rate and avg_return < 0
    -> REVIEW_OFF

avg_alpha < -1%
    -> REDUCE_WEIGHT

else
    -> KEEP_WEIGHT
```

## Database

`learning_decisions` stores the daily learning decision summary.

## Tests

```bash
pytest tests/test_learning_engine.py
```

Covered cases:

- Strong rule boost.
- Weak rule review.
- Negative alpha reduction.
- Insufficient sample collection.
- Multiple rule grouping.
- Dict payload compatibility.
- Empty samples.
- Invalid holding days.

## v2.0 Expansion

Learning Engine v2.0 should add:

- Walk-forward validation.
- Regime-specific learning.
- Rule decay and freshness weighting.
- Bayesian confidence intervals.
- Automatic parameter proposal files.
- Human approval workflow before production changes.
