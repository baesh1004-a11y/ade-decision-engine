# ADE Explainable AI Engine v1

## Purpose

Explainable AI Engine turns ADE decisions into human-readable explanations.

It answers:

```text
Why BUY?
Why WATCH?
Why AVOID?
What evidence supports this decision?
What risks should be watched?
```

## Implemented Components

```text
explain/models.py
explain/evidence.py
explain/narrative.py
explain/formatter.py
explain/engine.py
core/pipeline.py
```

## Pipeline Integration

`ADEPipeline` now includes explainability by default.

```python
ADEPipeline(use_explainability=True)
```

Flow:

```text
Pattern Memory
    ↓
Pattern Context
    ↓
Probability
    ↓
Calibration
    ↓
Candidate
    ↓
Risk / Position / Entry
    ↓
Explainable AI
    ↓
Explanation Report
```

## Output

Pipeline now adds:

```json
{
  "explanation": {
    "engine_version": "explainable-ai-v1.0.0",
    "ticker": "NVDA",
    "decision": "WATCHLIST",
    "confidence": 0.72,
    "summary": "NVDA는 관심종목으로 관찰할 만합니다...",
    "evidence": [],
    "warnings": [],
    "narrative": "# ADE Decision Explanation: NVDA...",
    "metadata": {
      "evidence_count": 8,
      "warning_count": 1
    }
  }
}
```

## Evidence Categories

The engine extracts evidence from:

```text
Pattern Memory
Pattern Matching
Pattern Context
Probability
Calibration
Candidate
Risk
Position
Entry
Exit
```

## Example

```python
from explain.engine import ExplainableAIEngine
from explain.formatter import ExplanationFormatter

report = ExplainableAIEngine().explain("NVDA", decisions).to_dict()
markdown = ExplanationFormatter().to_markdown(report)
```

## Markdown Example

```text
# ADE 설명 리포트: NVDA

- 최종 판단: WATCHLIST
- 신뢰도: 72.00%

## 근거
- Pattern / Average Similarity: 82.00% (supportive)
- Probability / Upside Probability: 64.00% (supportive)
- Risk / Risk Level: LOW (supportive)

## 주의사항
- Position: size was capped by Risk Engine
```

## Tests

```bash
pytest tests/test_explainable_ai.py
pytest tests/test_ade_pipeline.py
```

## Current Limitations

v1 is deterministic and template-based.

```text
No LLM narrative generation yet
No visual report yet
No HTML/PDF output yet
No chart explanation yet
```

## Next Step

Adaptive Learning v2.

It should use backtest and calibration results to update rule weights:

```text
Rule performance
    ↓
Weight update
    ↓
Candidate / Probability scoring adjustment
```
