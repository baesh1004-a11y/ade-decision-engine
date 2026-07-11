# Integration Orchestrator v1

## 1. 목적

Integration Orchestrator는 ADE의 개별 엔진을 새로 판단하는 엔진이 아니라 전체 실행을 통제하는 상위 제어 계층이다.

현재 `main.py`와 `core/pipeline.py`의 실행 흐름을 대체하지 않고 다음 기능을 추가한다.

- 실행 요청 표준화
- 실행 ID 및 단계 상태 관리
- 실패 격리와 안전한 중단
- 제한적 재시도
- 입력/출력 스냅샷 기록
- Report Engine용 표준 결과 생성

## 2. 책임 경계

### 담당

- 실행 모드와 단계 순서 결정
- 단계별 시작, 완료, 실패 기록
- 선행 조건, 타임아웃, 재시도 정책 적용
- 실패 시 후속 단계 차단
- 최종 실행 결과 집계

### 담당하지 않음

- 시장 데이터 정확성 판단
- 신호, 리스크, 주문 판단 생성
- 주문 가격 또는 수량 수정
- 체결 및 포트폴리오 결과 조작

## 3. 아키텍처

```text
Run Request
    ↓
Integration Orchestrator
    ├─ Context Builder
    ├─ Stage Planner
    ├─ Policy Guard
    ├─ Stage Executor
    ├─ State Recorder
    └─ Result Aggregator
          ↓
DataHub → Data Quality → Portfolio State
          ↓
Signal → Risk → Decision
          ↓
Order → Execution → Backtest → Report
```

## 4. 실행 상태

### Run 상태

```text
CREATED → VALIDATING → RUNNING
                       ├→ SUCCEEDED
                       ├→ PARTIAL_SUCCESS
                       ├→ FAILED
                       └→ CANCELLED
```

### Stage 상태

```text
PENDING → RUNNING → SUCCEEDED
                  ├→ SKIPPED
                  ├→ RETRYING
                  └→ FAILED
```

## 5. 입력/출력 모델

```python
@dataclass(frozen=True)
class RunRequest:
    mode: str
    market: str
    ticker: str
    start: str | None = None
    end: str | None = None
    account_balance: float = 0.0
    cash: float = 0.0
    market_regime: str = "SIDEWAY"
    correlation_id: str | None = None
    requested_by: str = "system"


@dataclass
class RunResult:
    run_id: str
    correlation_id: str
    mode: str
    status: str
    stages: list[dict]
    decisions: dict
    errors: list[str]
    warnings: list[str]
```

필수 검증:

- 지원 시장 여부
- ticker 공백 여부
- 음수 계좌 금액 차단
- 시작일과 종료일 순서
- 운영 모드별 허용 단계 확인

## 6. 데이터베이스

### `ade_runs`

| 컬럼 | 설명 |
|---|---|
| `run_id` | 실행 고유 ID |
| `correlation_id` | 연관 실행 추적 ID |
| `run_mode` | 실행 모드 |
| `market`, `ticker` | 분석 대상 |
| `status` | 실행 상태 |
| `requested_by` | 요청 주체 |
| `started_at`, `finished_at` | 실행 시간 |
| `error_count`, `warning_count` | 오류와 경고 수 |
| `config_json` | 실행 설정 스냅샷 |

인덱스: `(ticker, started_at)`, `(status, started_at)`, `(correlation_id)`

### `ade_run_stages`

| 컬럼 | 설명 |
|---|---|
| `stage_id` | 단계 ID |
| `run_id` | 실행 ID |
| `stage_name` | 단계 이름 |
| `sequence_no` | 실행 순서 |
| `status` | 단계 상태 |
| `attempt` | 시도 횟수 |
| `duration_ms` | 실행 시간 |
| `input_hash`, `output_hash` | 입력/출력 무결성 |
| `error_type`, `error_message` | 오류 정보 |

### `ade_run_artifacts`

| 컬럼 | 설명 |
|---|---|
| `artifact_id` | 산출물 ID |
| `run_id` | 실행 ID |
| `stage_name` | 생성 단계 |
| `artifact_type` | INPUT/OUTPUT/REPORT/LOG |
| `schema_version` | 스키마 버전 |
| `payload_json` | 직렬화 결과 |
| `payload_hash` | 무결성 해시 |

인증정보와 민감정보는 저장하지 않는다.

## 7. 분석 실행 단계

```text
1. validate_request
2. load_market_data
3. validate_market_data
4. build_decision_context
5. run_existing_pipeline
6. aggregate_result
7. build_report_fixture
```

기존 코드 매핑:

| 단계 | 현재 구현 |
|---|---|
| `load_market_data` | `main.load_market_data()` |
| `build_decision_context` | `DecisionContext(...)` |
| `run_existing_pipeline` | `ADEPipeline().run(context)` |
| `aggregate_result` | `context.decisions`, `context.errors` |

## 8. 핵심 알고리즘

```text
요청 검증
→ run_id 생성
→ 실행 레코드 생성
→ 모드별 Stage Plan 생성
→ 각 단계 선행 조건 확인
→ 단계 실행 및 상태 기록
→ 일시 오류만 제한 재시도
→ 치명 오류 발생 시 후속 단계 차단
→ 결과와 오류 집계
→ 최종 상태 결정
→ Report fixture 생성
→ RunResult 반환
```

최종 상태 결정:

```python
if critical_stage_failed:
    status = "FAILED"
elif optional_stage_failed or warnings:
    status = "PARTIAL_SUCCESS"
else:
    status = "SUCCEEDED"
```

재시도 원칙:

- 기본 재시도 0회
- 외부 데이터 조회의 일시 오류만 최대 2회
- 검증 오류와 계산 오류는 재시도하지 않음
- 동일 요청 재실행 시 기존 성공 결과 재사용 가능

## 9. 코드 구조

```text
core/
├── orchestrator.py
├── run_models.py
├── run_policy.py
├── stage_executor.py
└── run_repository.py

tests/
├── test_orchestrator_unit.py
├── test_orchestrator_failure.py
├── test_orchestrator_idempotency.py
└── test_orchestrator_smoke.py
```

참조 코드:

```python
class IntegrationOrchestrator:
    def __init__(self, repository, policy, stages):
        self.repository = repository
        self.policy = policy
        self.stages = stages

    def run(self, request):
        self.policy.validate(request)
        run = self.repository.create_run(request)
        state = {"request": request, "decisions": {}, "errors": []}
        results = []

        for stage in self.stages.build_plan(request.mode):
            if self._dependency_failed(stage, results):
                results.append(self.repository.skip_stage(run.id, stage.name))
                continue
            try:
                self.repository.start_stage(run.id, stage.name)
                state = stage.execute(state)
                results.append(self.repository.complete_stage(run.id, stage.name, state))
            except Exception as exc:
                results.append(self.repository.fail_stage(run.id, stage.name, exc))
                state["errors"].append(f"{stage.name}: {exc}")
                if stage.critical:
                    break

        status = self._resolve_status(results, state["errors"])
        return self.repository.complete_run(run.id, status, state, results)
```

실제 구현에서는 기존 `DecisionContext`와 `ADEPipeline`을 adapter로 연결한다.

## 10. 기존 코드 통합 전략

### 1단계: 래핑

기존 `run_single_analysis()` 내부 로직을 유지하고 Orchestrator 단계로 감싼다.

```text
Orchestrator
  └─ ExistingPipelineAdapter
       ├─ load_market_data()
       ├─ DecisionContext(...)
       └─ ADEPipeline().run(context)
```

### 2단계: 출력 표준화

- `DecisionContext.decisions` → `RunResult.decisions`
- `DecisionContext.errors` → `RunResult.errors`
- 콘솔 출력 → Report Engine용 JSON fixture

### 3단계: 점진 분리

처음에는 기존 `ADEPipeline.run()`을 하나의 단계로 사용한다. 스모크 테스트와 회귀 테스트가 확보된 뒤 DataHub, Signal, Risk, Decision 단계로 분리한다.

## 11. 테스트 계획

### 단위 테스트

- 정상 요청 검증
- 빈 ticker 차단
- 음수 계좌 금액 차단
- critical 단계 실패 시 후속 단계 미실행
- optional 단계 실패 시 `PARTIAL_SUCCESS`
- 일시 오류 최대 2회 재시도
- 동일 요청 멱등성 확인

### 통합 테스트

1. 고정 CSV fixture로 전체 분석 실행
2. Candidate, Risk, Position, Entry 결과 존재 확인
3. 현재 포지션 입력 시 Exit 결과 확인
4. DB의 run 상태와 stage 상태 일치 확인
5. Report fixture에 run ID, decisions, errors 포함 확인

### 스모크 테스트

```bash
python main.py --market kr --ticker 005930 --start 20240101 --end 20261231
```

확인 항목:

- 프로세스 종료 코드 0
- Candidate/Risk/Position/Entry 출력
- 치명적 traceback 없음
- Backtest summary 출력
- 실행 시간 기록

외부 데이터 의존성을 제거한 fixture 기반 스모크 테스트를 별도로 둔다.

### 실패 주입 테스트

- 데이터 수집 timeout
- 빈 DataFrame
- OHLCV 필수 컬럼 누락
- Risk Engine 예외
- Report Engine 예외
- DB 기록 실패

## 12. 구현 우선순위

1. `RunRequest`, `RunResult`, `StageResult`
2. SQLite run/stage repository
3. 기존 파이프라인 adapter
4. 분석 모드 Orchestrator
5. fixture 기반 스모크 테스트
6. Report fixture JSON
7. 백테스트와 모의 실행 모드 확장

## 13. 완료 기준

- 실행마다 고유 run ID 생성
- 단계별 상태 DB 기록
- 기존 파이프라인을 Orchestrator를 통해 실행
- 치명 단계 실패 시 후속 단계 차단
- 표준 결과 JSON 생성
- 고정 fixture 스모크 테스트 통과
