# 12. Report Engine

## Purpose

Report Engine은 ADE가 생성한 신호, 리스크 판단, 최종 의사결정, 주문, 체결, 포트폴리오 상태, 백테스트 결과를 사람이 검토 가능한 리포트로 변환한다. 이 엔진은 투자 판단을 새로 만들지 않으며, 기존 엔진들의 결과를 설명, 기록, 비교, 감사하기 위한 출력 계층이다.

## Scope

Report Engine v1은 다음을 담당한다.

- 일일 의사결정 리포트 생성
- 종목별 신호와 판단 근거 요약
- 리스크 제한 및 거절 사유 정리
- 주문/체결/미체결 상태 요약
- 포트폴리오 손익, 노출도, 현금 비중 요약
- 백테스트 결과 요약 리포트 생성
- 운영자 검토용 Markdown/HTML/JSON 출력
- 리포트 생성 이력과 원천 데이터 스냅샷 기록

Report Engine은 다음을 담당하지 않는다.

- 새로운 매수/매도 판단 생성
- 주문 실행
- 리스크 한도 변경
- 전략 파라미터 자동 변경
- 실계좌 API 호출

## Position in ADE Architecture

```text
Signal Engine
Risk Engine
Decision Engine
Order Engine
Execution Monitor
Portfolio State Engine
Backtest Engine
        ↓
Report Data Aggregator
        ↓
Report Engine
        ↓
Markdown / HTML / JSON / Dashboard
```

## Core Principles

1. Report Engine은 판단을 변경하지 않고 설명만 생성한다.
2. 모든 수치는 원천 엔진의 결과와 연결되어야 한다.
3. 리포트에는 핵심 판단, 근거, 리스크, 다음 확인사항이 포함되어야 한다.
4. 투자 성과는 수익률뿐 아니라 손실 위험과 노출도를 함께 표시한다.
5. 백테스트 리포트는 미래 수익 보장이 아니라 검증 결과로 표현한다.
6. 사람이 빠르게 읽을 수 있는 요약과 기계가 재처리할 수 있는 JSON을 함께 지원한다.
7. 실계좌 주문 가능 여부와 운영 모드는 리포트 상단에 명확히 표시한다.

## Inputs

| Input | Source | Description |
|---|---|---|
| report_date | Scheduler/User | report 기준일 |
| signals | Signal Engine | 종목별 신호 점수와 구성 점수 |
| risk_events | Risk Engine | 리스크 점수, 제한, 차단 사유 |
| decisions | Decision Engine | BUY/HOLD/REDUCE/SELL/REJECT/NO_ACTION |
| orders | Order Engine | 주문 생성 결과와 검증 상태 |
| executions | Execution Monitor | 체결, 부분체결, 거부, 취소 상태 |
| portfolio_state | Portfolio State Engine | 현금, 보유 종목, 평가금액, 손익 |
| backtest_result | Backtest Engine | 백테스트 성과와 리스크 지표 |
| run_metadata | Pipeline | 실행 모드, 데이터 스냅샷, 설정 해시 |

## Output

```python
ReportResult(
    report_id="rpt_20260710_daily",
    report_type="DAILY_DECISION",
    report_date="2026-07-10",
    mode="DRY_RUN",
    summary="3 BUY candidates, 7 WATCH, 2 REJECTED by risk limits",
    markdown_path="reports/2026-07-10_daily.md",
    json_path="reports/2026-07-10_daily.json",
    status="COMPLETED"
)
```

## Report Types

| Type | Purpose |
|---|---|
| DAILY_DECISION | 매일의 후보, 판단, 리스크, 주문 준비 상태 요약 |
| PORTFOLIO_STATUS | 현금, 보유 종목, 평가손익, 노출도 점검 |
| EXECUTION_SUMMARY | 주문/체결/미체결/거부/취소 결과 요약 |
| RISK_REVIEW | 리스크 제한, 차단 사유, 집중도, 손실 위험 점검 |
| BACKTEST_SUMMARY | 백테스트 성과, MDD, 승률, 거래 수, 재현성 정보 요약 |
| INCIDENT_REPORT | 데이터 오류, API 오류, 실행 실패 등 예외 상황 정리 |

## Main Components

| Component | Responsibility |
|---|---|
| ReportRunner | 리포트 생성 전체 흐름 제어 |
| ReportDataAggregator | 여러 엔진 결과를 하나의 리포트 데이터로 통합 |
| SummaryBuilder | 핵심 요약, 주요 숫자, 경고 문구 생성 |
| DecisionExplainer | 종목별 판단 근거와 거절 사유 정리 |
| RiskReporter | 리스크 이벤트, 한도 초과, 노출도 요약 |
| PortfolioReporter | 포트폴리오 손익과 보유 상태 요약 |
| BacktestReporter | 백테스트 성과와 위험 지표 요약 |
| ReportRenderer | Markdown, HTML, JSON 출력 생성 |
| ReportRepository | 리포트 이력과 원천 스냅샷 저장 |

## Database Design

### report_runs

| Column | Type | Description |
|---|---|---|
| report_id | TEXT PK | report id |
| created_at | TIMESTAMP | creation time |
| report_date | DATE | report 기준일 |
| report_type | TEXT | DAILY_DECISION/BACKTEST_SUMMARY/etc |
| mode | TEXT | DRY_RUN/PAPER/LIVE_BLOCKED/LIVE/SIMULATED |
| status | TEXT | PENDING/RUNNING/COMPLETED/FAILED |
| source_run_id | TEXT | pipeline/backtest/execution run id |
| config_hash | TEXT | report config hash |
| data_snapshot_id | TEXT | source data snapshot id |
| summary | TEXT | short human-readable summary |

### report_sections

| Column | Type | Description |
|---|---|---|
| section_id | TEXT PK | section id |
| report_id | TEXT FK | report id |
| section_type | TEXT | SUMMARY/SIGNALS/RISK/PORTFOLIO/ORDERS/BACKTEST |
| title | TEXT | section title |
| content_markdown | TEXT | rendered markdown section |
| severity | TEXT | INFO/WARNING/CRITICAL |
| sort_order | INTEGER | display order |

### report_artifacts

| Column | Type | Description |
|---|---|---|
| artifact_id | TEXT PK | artifact id |
| report_id | TEXT FK | report id |
| artifact_type | TEXT | MARKDOWN/HTML/JSON/CSV/PNG |
| path | TEXT | stored artifact path |
| checksum | TEXT | artifact checksum |
| created_at | TIMESTAMP | creation time |

### report_items

| Column | Type | Description |
|---|---|---|
| item_id | TEXT PK | item id |
| report_id | TEXT FK | report id |
| symbol | TEXT | optional stock symbol |
| decision | TEXT | BUY/HOLD/REDUCE/SELL/REJECT/NO_ACTION |
| signal_score | NUMERIC | signal score |
| risk_score | NUMERIC | risk score |
| severity | TEXT | INFO/WARNING/CRITICAL |
| reason | TEXT | explanation |
| source_ref | TEXT | source engine record id |

## Daily Decision Report Layout

```text
# ADE Daily Decision Report

1. Executive Summary
   - 실행 모드
   - 전체 후보 수
   - 매수 후보 수
   - 리스크 차단 수
   - 주문 생성 수
   - 체결/미체결 상태

2. Market and Data Status
   - 데이터 기준일
   - 데이터 품질 상태
   - 누락/이상 데이터 경고

3. Top Decisions
   - BUY / HOLD / REDUCE / SELL / REJECT / NO_ACTION
   - 종목별 점수와 핵심 사유

4. Risk Review
   - 한도 초과
   - 집중도
   - 변동성
   - 손실 제한

5. Portfolio Status
   - 총 평가금액
   - 현금 비중
   - 보유 종목 수
   - 일간 손익
   - 누적 손익

6. Orders and Executions
   - 주문 생성 결과
   - 체결/부분체결/미체결/거부
   - 실패 사유

7. Next Review Items
   - 사람이 확인해야 할 항목
   - 테스트 또는 데이터 보완 필요 항목
```

## Backtest Summary Report Layout

```text
# ADE Backtest Summary

1. Test Configuration
   - 기간
   - 대상 종목
   - 초기 자금
   - 수수료/세금/슬리피지
   - 설정 해시

2. Performance Summary
   - 최종 평가금액
   - 총 수익률
   - CAGR
   - 벤치마크 대비 성과

3. Risk Summary
   - Max Drawdown
   - 변동성
   - Sharpe Ratio
   - Sortino Ratio
   - 최대 손실 구간

4. Trade Statistics
   - 총 거래 수
   - 승률
   - Profit Factor
   - 평균 보유일
   - 회전율

5. Reliability Notes
   - 데이터 스냅샷
   - Look-ahead bias 방지 여부
   - 재현성 정보
   - 한계와 주의사항
```

## Algorithm

### 1. Create Report Run

```python
report_run = repository.create_report_run(
    report_type=config.report_type,
    report_date=config.report_date,
    mode=config.mode,
    source_run_id=config.source_run_id,
)
```

### 2. Aggregate Source Data

```python
data = aggregator.collect(
    report_date=config.report_date,
    include_signals=True,
    include_risk=True,
    include_decisions=True,
    include_orders=True,
    include_executions=True,
    include_portfolio=True,
)
```

### 3. Build Summary

```python
summary = summary_builder.build(data)
```

Summary rules:

| Condition | Report Severity |
|---|---|
| live order mode enabled | WARNING |
| data quality failure exists | CRITICAL |
| rejected decisions exist | INFO/WARNING depending on count |
| risk limit exceeded | WARNING |
| order failure exists | WARNING |
| execution error exists | CRITICAL |
| backtest config not reproducible | WARNING |

### 4. Explain Decisions

```python
items = decision_explainer.explain(
    decisions=data.decisions,
    signals=data.signals,
    risk_events=data.risk_events,
)
```

Each item should answer:

- What was decided?
- Why was it decided?
- Which score or rule drove the decision?
- Was it blocked or limited by risk?
- Does a human need to review it?

### 5. Render Artifacts

```python
markdown = renderer.render_markdown(report_data)
html = renderer.render_html(report_data)
json_payload = renderer.render_json(report_data)
```

### 6. Persist Report

```python
repository.save_sections(report_id, sections)
repository.save_items(report_id, items)
repository.save_artifacts(report_id, artifacts)
repository.complete_report(report_id, summary)
```

## Code Structure

```text
reports/
  __init__.py
  runner.py
  aggregator.py
  summary.py
  explain.py
  risk.py
  portfolio.py
  backtest.py
  renderer.py
  repository.py
  models.py
  templates/
    daily_decision.md.j2
    backtest_summary.md.j2
    risk_review.md.j2

tests/
  test_report_runner.py
  test_report_aggregator.py
  test_decision_explainer.py
  test_report_renderer.py
  test_report_repository.py
```

## Interface Draft

```python
@dataclass
class ReportConfig:
    report_type: str
    report_date: date
    mode: str = "DRY_RUN"
    source_run_id: str | None = None
    output_formats: tuple[str, ...] = ("markdown", "json")
    include_portfolio: bool = True
    include_orders: bool = True
    include_executions: bool = True


class ReportEngine:
    def generate(self, config: ReportConfig) -> ReportResult:
        """Generate an auditable ADE report from existing engine outputs."""
        raise NotImplementedError
```

## Test Plan

### Unit Tests

- creates report run with valid config
- rejects unsupported report type
- aggregator handles missing optional execution data
- summary marks data quality failure as CRITICAL
- decision explainer includes signal and risk reason
- rejected decision shows rejection reason
- renderer outputs valid Markdown
- renderer outputs JSON with required fields
- repository persists sections, items, and artifacts
- report completion stores summary and status

### Integration Tests

- generate daily report from fixture Signal/Risk/Decision/Order data
- generate execution summary from partial fill and rejected order data
- generate portfolio status from fixture holdings
- generate backtest summary from fixture backtest result
- report artifacts are reproducible for same source data
- failed source data collection marks report as FAILED without changing decisions

### Regression Tests

- same source data and config produce same report checksum
- missing executions do not break DRY_RUN report
- LIVE_BLOCKED mode is clearly displayed
- critical risk event appears in executive summary
- backtest report includes warning that results do not guarantee future performance

## Acceptance Criteria

Report Engine v1 is considered implemented when:

1. Daily decision report can be generated from existing engine outputs.
2. Backtest summary report can be generated from saved backtest results.
3. Markdown and JSON outputs are both supported.
4. Report records link back to source run ids and data snapshots.
5. Critical risk, data, and execution events appear in the executive summary.
6. Report generation never changes decisions, orders, or portfolio state.

## Next Step

After Report Engine v1 design, ADE design v0.1 has the complete core engine map. The next phase should shift from adding new engine designs to verifying and implementing the executable path:

```text
main.py / current pipeline
  ↓
DataHub → Data Quality → Signal → Risk → Decision
  ↓
Order/Execution in restricted or simulated mode
  ↓
Report
```
