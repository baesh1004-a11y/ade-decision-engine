# Model Registry & Inference Governance Engine v1

## 1. 목적

Model Registry & Inference Governance Engine은 ADE에서 사용하는 통계·머신러닝·딥러닝 모델의 등록, 버전 관리, 승인, 배포, 추론 기록, 성능 검증, 롤백을 통제하는 계층이다.

이 엔진은 투자 판단을 직접 생성하지 않는다. Signal, Market Regime, Risk, Strategy Monitoring 등이 사용하는 모델을 안전하고 재현 가능한 형태로 공급하고, 어떤 모델이 어떤 입력과 설정으로 어떤 결과를 생성했는지 증거를 남긴다.

## 2. 책임 경계

### 담당

- 모델 정의와 버전 등록
- 학습 데이터·코드·특징량·정책 버전 연결
- 모델 artifact checksum과 서명 검증
- 모델 승인 상태와 배포 단계 관리
- 추론 요청의 입력 계약 검증
- 모델·전처리기·임계값의 원자적 로딩
- 추론 결과, latency, 품질 상태, 설명값 저장
- Champion–Challenger, Shadow, Canary 배포 지원
- 성능 저하·오류 발생 시 이전 승인 버전 롤백
- Strategy Validation·Monitoring·Audit 엔진과 증거 연계

### 담당하지 않음

- 매수·매도 판단 확정
- 포지션 크기 결정
- 리스크 한도 변경
- 주문 생성·전송
- 체결·회계 처리
- 학습 데이터 수집 또는 특징량 자체 계산

## 3. 아키텍처

```text
Training / Research Pipeline
        ↓
Model Candidate + Evidence Manifest
        ↓
Model Registry
   ├─ Model Definition
   ├─ Model Version
   ├─ Artifact Store Reference
   ├─ Approval Workflow
   ├─ Deployment Alias
   └─ Rollback Pointer
        ↓
Inference Governance
   ├─ Input Contract Validator
   ├─ Feature Snapshot Resolver
   ├─ Model Loader
   ├─ Prediction Executor
   ├─ Explanation Generator
   ├─ Output Guard
   └─ Inference Journal
        ↓
Signal / Regime / Risk / Monitoring Engine
        ↓
Audit & Compliance / Report / Drift Detection
```

## 4. 핵심 원칙

1. 모델 파일만으로 배포하지 않고 데이터·코드·특징량·전처리·정책·검증 결과를 하나의 Manifest로 묶는다.
2. 승인되지 않은 모델 버전은 PAPER·LIVE 추론에 사용할 수 없다.
3. 모델과 전처리기, feature schema, threshold는 하나의 불변 배포 단위로 관리한다.
4. 동일 모델 버전과 동일 Feature Snapshot은 결정론적 모드에서 동일 결과를 생성해야 한다.
5. 추론 입력에 미래 데이터나 다른 run의 snapshot이 섞이면 차단한다.
6. 모델 출력은 업무 규칙과 Risk hard block을 우회할 수 없다.
7. 추론 장애 시 임의의 기본 BUY 신호를 만들지 않는다.
8. 롤백은 이전 승인 버전으로만 허용하고 모든 변경을 감사 이벤트로 기록한다.

## 5. 상태 모델

### 모델 버전 상태

```text
DRAFT
→ REGISTERED
→ VALIDATING
→ REJECTED
→ APPROVED_BACKTEST
→ APPROVED_PAPER
→ APPROVED_SHADOW
→ APPROVED_LIVE_BLOCKED
→ APPROVED_LIVE
→ DEPRECATED
→ RETIRED
```

### 배포 상태

```text
PENDING → DEPLOYING → ACTIVE
                    ├→ FAILED
                    ├→ ROLLED_BACK
                    └→ SUSPENDED
```

### 추론 상태

```text
RECEIVED → VALIDATING → RUNNING
                         ├→ SUCCEEDED
                         ├→ DEGRADED
                         ├→ REJECTED
                         └→ FAILED
```

## 6. 입력과 출력

### 입력

```python
InferenceRequest(
    inference_id="inf_20260728_000001",
    run_id="run_20260728_001",
    model_alias="signal_ranker_champion",
    model_version=None,
    feature_snapshot_id="fs_20260728_close",
    schema_version="signal_feature_v3",
    mode="PAPER",
    symbols=["005930", "000660"],
    requested_at="2026-07-28T15:40:00+09:00",
)
```

### 출력

```python
InferenceResult(
    inference_id="inf_20260728_000001",
    model_version_id="mdl_signal_ranker_1.4.2",
    deployment_id="dep_signal_ranker_paper_014",
    status="SUCCEEDED",
    predictions={"005930": 0.73, "000660": 0.81},
    explanations={"000660": {"trend_20d": 0.18, "volume": 0.12}},
    input_hash="...",
    output_hash="...",
    latency_ms=37,
)
```

## 7. 데이터베이스

### `model_definitions`

| 컬럼 | 설명 |
|---|---|
| `model_id` | 논리 모델 ID |
| `name` | 모델명 |
| `purpose` | SIGNAL/REGIME/RISK/MONITORING |
| `owner` | 책임자 |
| `created_at` | 생성 시각 |
| `status` | ACTIVE/DEPRECATED |

### `model_versions`

| 컬럼 | 설명 |
|---|---|
| `model_version_id` | 모델 버전 ID |
| `model_id` | 논리 모델 ID |
| `semantic_version` | 버전 |
| `framework` | sklearn/xgboost/pytorch/etc |
| `artifact_uri` | 모델 artifact 위치 |
| `artifact_hash` | SHA-256 |
| `preprocessor_hash` | 전처리기 hash |
| `feature_schema_version` | 입력 특징량 계약 |
| `training_data_snapshot_id` | 학습 데이터 스냅샷 |
| `code_commit_sha` | 학습 코드 commit |
| `policy_snapshot_id` | 임계값·정책 snapshot |
| `evidence_manifest_hash` | 검증 증거 hash |
| `status` | 모델 버전 상태 |
| `created_at` | 생성 시각 |

### `model_approvals`

| 컬럼 | 설명 |
|---|---|
| `approval_id` | 승인 ID |
| `model_version_id` | 승인 대상 |
| `target_stage` | PAPER/SHADOW/LIVE_BLOCKED/LIVE |
| `requested_by` | 요청자 |
| `approved_by` | 승인자 |
| `decision` | APPROVED/REJECTED |
| `reason` | 승인 사유 |
| `expires_at` | 승인 만료 |
| `created_at` | 시각 |

### `model_deployments`

| 컬럼 | 설명 |
|---|---|
| `deployment_id` | 배포 ID |
| `model_alias` | champion/challenger alias |
| `model_version_id` | 실제 버전 |
| `mode` | BACKTEST/PAPER/SHADOW/LIVE_BLOCKED/LIVE |
| `traffic_pct` | Canary 트래픽 비율 |
| `status` | 배포 상태 |
| `previous_deployment_id` | 롤백 대상 |
| `started_at`, `ended_at` | 유효 기간 |

### `inference_runs`

| 컬럼 | 설명 |
|---|---|
| `inference_id` | 추론 ID |
| `run_id` | ADE 실행 ID |
| `deployment_id` | 배포 ID |
| `model_version_id` | 모델 버전 |
| `feature_snapshot_id` | 입력 snapshot |
| `input_hash`, `output_hash` | 무결성 hash |
| `status` | 추론 상태 |
| `latency_ms` | 지연 시간 |
| `error_type`, `error_message` | 오류 |
| `created_at` | 시각 |

### `inference_predictions`

| 컬럼 | 설명 |
|---|---|
| `prediction_id` | 예측 ID |
| `inference_id` | 추론 ID |
| `entity_key` | 종목/시장 key |
| `prediction_value` | 예측값 |
| `confidence` | 신뢰도 |
| `explanation_json` | 설명값 |
| `quality_status` | VALID/DEGRADED/INVALID |

### `model_rollbacks`

| 컬럼 | 설명 |
|---|---|
| `rollback_id` | 롤백 ID |
| `from_deployment_id` | 문제 배포 |
| `to_deployment_id` | 복구 배포 |
| `trigger_type` | MANUAL/HEALTH/ERROR/COMPLIANCE |
| `reason` | 사유 |
| `requested_by`, `approved_by` | 요청·승인 |
| `created_at` | 시각 |

## 8. 핵심 알고리즘

### 8.1 모델 등록

```text
모델 artifact 수신
→ SHA-256 계산
→ feature schema와 preprocessor 검증
→ training data snapshot·code commit 연결
→ validation evidence manifest 검증
→ model_version 생성
→ REGISTERED 상태 저장
```

### 8.2 추론 실행

```python
def infer(request, registry, feature_store, runtime):
    deployment = registry.resolve_alias(request.model_alias, request.mode)
    version = registry.get_version(deployment.model_version_id)

    assert version.status in allowed_statuses(request.mode)
    assert approval_is_valid(version, request.mode)

    snapshot = feature_store.get(request.feature_snapshot_id)
    validate_same_run_or_declared_lineage(request, snapshot)
    validate_schema(snapshot, version.feature_schema_version)
    validate_freshness(snapshot, request.mode)

    bundle = runtime.load_atomic_bundle(
        model_uri=version.artifact_uri,
        expected_model_hash=version.artifact_hash,
        expected_preprocessor_hash=version.preprocessor_hash,
    )

    inputs = bundle.preprocessor.transform(snapshot.payload)
    predictions = bundle.model.predict(inputs)
    guarded = validate_outputs(predictions, version.policy_snapshot_id)

    return persist_inference_result(request, deployment, version, snapshot, guarded)
```

### 8.3 Output Guard

다음 조건은 추론 결과를 `INVALID` 또는 `DEGRADED`로 처리한다.

- NaN/Inf 출력
- 확률 범위 이탈
- 허용되지 않은 클래스
- 종목 수와 결과 수 불일치
- confidence 최소 기준 미달
- 설명값 합계·형식 오류
- feature 품질 상태가 INVALID
- 출력 분포가 배포 기준선을 심각하게 이탈

`INVALID` 출력은 Signal·Risk·Decision 입력으로 전달하지 않는다.

### 8.4 Champion–Challenger

```text
동일 Feature Snapshot
→ Champion 추론
→ Challenger Shadow 추론
→ 결과 차이·순위 상관·latency·오류율 비교
→ Strategy Monitoring에 관측치 전달
→ Strategy Validation이 승격 근거로 사용
```

### 8.5 자동 롤백 요청

다음은 롤백 요청 조건이다.

- artifact checksum 불일치
- 추론 실패율 임계치 초과
- latency SLO 지속 위반
- NaN/Inf 또는 schema 오류 반복
- Strategy Monitoring `CRITICAL`
- Audit & Compliance 하드 위반

자동으로 새 모델을 선택하지 않는다. 사전에 등록된 `previous_deployment_id` 또는 승인된 fallback 버전으로만 롤백한다.

## 9. 코드 구조

```text
model_governance/
├── models.py
├── registry.py
├── repository.py
├── manifest.py
├── approvals.py
├── deployment.py
├── resolver.py
├── loader.py
├── contract.py
├── inference.py
├── output_guard.py
├── shadow.py
└── rollback.py

tests/
├── test_model_registry.py
├── test_model_manifest.py
├── test_model_approval.py
├── test_model_alias_resolver.py
├── test_inference_contract.py
├── test_inference_determinism.py
├── test_output_guard.py
├── test_shadow_comparison.py
└── test_model_rollback.py
```

## 10. 참조 모델

```python
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelVersion:
    model_version_id: str
    model_id: str
    semantic_version: str
    artifact_uri: str
    artifact_hash: str
    preprocessor_hash: str
    feature_schema_version: str
    training_data_snapshot_id: str
    code_commit_sha: str
    policy_snapshot_id: str
    status: str


@dataclass(frozen=True)
class InferenceResult:
    inference_id: str
    model_version_id: str
    deployment_id: str
    status: str
    predictions: dict[str, float]
    explanations: dict[str, dict[str, float]]
    input_hash: str
    output_hash: str
    latency_ms: int
    warnings: tuple[str, ...] = ()
```

## 11. 테스트 계획

### 단위 테스트

- artifact hash 일치 시 등록 성공
- artifact hash 불일치 시 등록 거부
- feature schema 불일치 시 추론 차단
- 승인되지 않은 PAPER/LIVE 모델 차단
- 만료된 승인 차단
- 동일 입력·모델의 결정론적 출력 검증
- NaN/Inf 출력 차단
- confidence 미달 시 DEGRADED
- alias가 정확한 모델 버전으로 해석되는지 검증
- 롤백이 승인된 이전 버전으로만 수행되는지 검증

### DB 테스트

- 동일 model/version 중복 등록 방지
- ACTIVE alias 단일성 보장
- deployment와 approval 외래키 무결성
- inference run과 prediction 원자적 저장
- terminal deployment 상태 재활성화 차단

### 통합 테스트

- Feature Snapshot → 모델 추론 → Signal 입력 변환
- 동일 snapshot의 Champion–Challenger 병행 추론
- Strategy Validation 승인 결과와 배포 상태 연결
- Strategy Monitoring CRITICAL → 신규 추론 차단·롤백 요청
- Audit 이벤트에 모델·배포·추론 hash 포함
- Report Engine이 모델 버전과 설명값을 표시

### 실패 주입 테스트

- 모델 artifact 누락
- 로딩 timeout
- 메모리 부족
- 전처리기 버전 불일치
- feature store 지연
- DB 저장 실패
- Shadow 모델만 실패
- 배포 도중 프로세스 중단

### 회귀·성능 테스트

- 고정 fixture에서 모델 업그레이드 전후 순위 변화 비교
- 3,000종목 batch 추론 latency 측정
- 메모리 상한 검증
- 모델 캐시 hit/miss 검증
- 같은 입력 snapshot으로 재실행한 output hash 일치

## 12. 완료 기준

- 모델 버전과 artifact checksum을 등록할 수 있다.
- 승인 상태에 따라 BACKTEST/PAPER/SHADOW/LIVE 사용을 통제할 수 있다.
- Feature Snapshot과 모델 버전을 결합해 재현 가능한 추론 결과를 저장한다.
- NaN·schema mismatch·승인 만료·artifact 변조를 차단한다.
- Champion–Challenger 추론 결과를 비교할 수 있다.
- 문제 배포를 승인된 이전 버전으로 롤백할 수 있다.
- 모든 추론이 Audit·Monitoring·Report에서 추적 가능하다.

## 13. 구현 우선순위

1. `ModelVersion`, `ModelDeployment`, `InferenceRequest`, `InferenceResult` 모델
2. SQLite Model Registry Repository
3. artifact checksum과 Manifest 검증기
4. mode별 승인 상태 guard
5. alias resolver와 atomic model bundle loader
6. inference input/output contract validator
7. 고정 sklearn fixture 기반 결정론적 추론 테스트
8. Champion–Challenger shadow 비교
9. Strategy Monitoring 연계와 rollback request
