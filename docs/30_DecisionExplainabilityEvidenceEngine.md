# Decision Explainability & Evidence Engine v1

## 1. 목적

Decision Explainability & Evidence Engine은 ADE가 생성한 Signal, Risk, Decision, Rebalancing, Order 결과를 사람이 검증할 수 있는 일관된 설명과 불변 증거 묶음으로 변환하는 계층이다.

이 엔진은 새로운 투자 판단을 만들거나 기존 판단을 수정하지 않는다. 이미 확정된 엔진 출력과 Snapshot을 읽어 "무엇을 판단했는가", "왜 그렇게 판단했는가", "어떤 규칙이 허용·축소·차단했는가", "결과를 재현할 수 있는가"를 구조화한다.

## 2. 책임 경계

### 담당

- Signal·Risk·Decision·Exit·Order 결과의 증거 수집
- 원인 규칙, 기여 요인, 차단 사유의 표준화
- 후보 간 비교 설명과 최종 선택 이유 생성
- `NO_ACTION`, `REJECT`, `FORCE_EXIT` 전용 설명 생성
- 입력·정책·모델·코드·결과 hash를 결합한 Evidence Bundle 생성
- 사용자용 요약과 감사용 상세 설명의 분리
- 설명 완전성, 정합성, 충실도 검증
- Report, Audit, Strategy Validation, Monitoring에 설명 증거 제공

### 담당하지 않음

- Signal 점수 재계산
- Risk 상태 변경
- Decision 또는 주문 수량 변경
- 모델 학습·추론
- 포트폴리오 회계 처리
- 자연어 설명만을 근거로 주문 승인

## 3. 아키텍처

```text
Data / Feature / Model Inference Evidence
        +
Signal Snapshot
        +
Risk Snapshot
        +
Decision / Exit Proposal
        +
Order Validation Result
        +
Policy / Code / Model Versions
        ↓
Decision Explainability & Evidence Engine
   ├─ Evidence Collector
   ├─ Contract & Lineage Validator
   ├─ Reason Normalizer
   ├─ Contribution Resolver
   ├─ Counterfactual Boundary Resolver
   ├─ Explanation Composer
   ├─ Fidelity / Completeness Validator
   ├─ Evidence Bundle Hasher
   └─ Explanation Repository
        ↓
Report Engine / Audit & Compliance
Strategy Validation / Monitoring
Dashboard / Manual Review
```

## 4. 핵심 원칙

1. 설명은 원본 판단을 해석할 뿐 새 판단을 생성하지 않는다.
2. 설명에 포함된 수치와 상태는 반드시 저장된 Snapshot과 일치해야 한다.
3. Risk hard block과 강제청산 사유는 Signal의 긍정 요인보다 우선 표시한다.
4. `NO_ACTION`은 설명 실패가 아니라 유효한 최종 결정이다.
5. 자연어 문장보다 구조화된 reason code와 evidence reference를 기준 기록으로 사용한다.
6. 모델 기여도는 예측 설명이며 인과관계로 표현하지 않는다.
7. 설명 생성 실패가 주문 결과를 임의 변경하지 않지만, 필수 증거 누락은 신규 실행을 차단할 수 있다.
8. 동일 입력·정책·모델·결과는 동일한 canonical Evidence Bundle hash를 생성해야 한다.

## 5. 설명 계층

### L1 사용자 요약

- 최종 행동
- 핵심 근거 3개 이내
- 주요 리스크 차단 사유
- 가격·수량·금액
- 모의/실행 모드

### L2 운영 상세

- 후보 순위와 점수
- Risk 한도와 적용 결과
- Position sizing 계산
- Exit·Order 검증 결과
- 사용한 Snapshot·정책·모델 버전

### L3 감사 증거

- 전체 입력 참조
- reason code 전부
- 규칙 평가 순서
- 모델 출력과 설명값
- lineage·hash·commit SHA
- 생성기 버전과 schema version

## 6. 상태 모델

### 설명 상태

```text
PENDING
→ COLLECTING
→ VALIDATING
→ COMPOSING
   ├→ COMPLETE
   ├→ DEGRADED
   ├→ REJECTED
   └→ FAILED
```

- `COMPLETE`: 필수 증거와 설명이 모두 유효
- `DEGRADED`: 판단은 존재하지만 비필수 설명 요소가 누락
- `REJECTED`: cross-run 혼합, hash 불일치, 필수 증거 누락
- `FAILED`: 저장소 또는 생성기 오류

### 증거 중요도

```text
MANDATORY > MATERIAL > SUPPORTING
```

- `MANDATORY`: Decision, Risk hard block, 주문 수량·금액, Snapshot lineage
- `MATERIAL`: Signal 점수, regime, sizing factor, exit rule
- `SUPPORTING`: 뉴스 태그, 보조 지표, 시각화 설명

## 7. 표준 reason code

```text
SIGNAL_POSITIVE_MOMENTUM
SIGNAL_POSITIVE_QUALITY
SIGNAL_WEAK_CONFIDENCE
RISK_SYMBOL_LIMIT
RISK_SECTOR_LIMIT
RISK_CORRELATION_LIMIT
RISK_MIN_CASH
RISK_DAILY_LOSS_BLOCK
RISK_DRAWDOWN_BLOCK
RISK_DATA_QUALITY_BLOCK
DECISION_HIGHER_RANKED_CANDIDATE
DECISION_DAILY_ENTRY_LIMIT
DECISION_NO_VALID_CANDIDATE
EXIT_STOP_LOSS
EXIT_TRAILING_STOP
EXIT_PROFIT_PROTECTION
EXIT_FORCE_REDUCE
ORDER_APPROVAL_EXPIRED
ORDER_QUOTE_STALE
ORDER_PRICE_COLLAR
ORDER_INSUFFICIENT_BUYING_POWER
ORDER_VERIFY_REQUIRED
```

reason code는 `category`, `severity`, `rule_version`, `observed_value`, `threshold`, `effect`, `evidence_ref`를 가진다.

## 8. 입력과 출력

### 입력

```python
ExplanationRequest(
    explanation_id="exp_20260729_000001",
    run_id="run_20260729_001",
    decision_id="dec_20260729_005930",
    audience="OPERATOR",
    locale="ko-KR",
    requested_levels=["L1", "L2", "L3"],
    requested_at="2026-07-29T09:00:00+09:00",
)
```

### 출력

```python
DecisionExplanation(
    explanation_id="exp_20260729_000001",
    run_id="run_20260729_001",
    decision_id="dec_20260729_005930",
    action="NO_ACTION",
    status="COMPLETE",
    headline="유효한 신규 매수 후보가 없어 주문하지 않음",
    primary_reasons=[
        "DECISION_NO_VALID_CANDIDATE",
        "RISK_DAILY_LOSS_BLOCK",
    ],
    evidence_bundle_id="evb_20260729_000001",
    explanation_hash="sha256:...",
)
```

## 9. 데이터베이스

### `explanation_requests`

| 컬럼 | 설명 |
|---|---|
| `explanation_id` | 설명 요청 ID |
| `run_id` | ADE run ID |
| `decision_id` | 대상 판단 ID |
| `audience` | USER/OPERATOR/AUDITOR |
| `locale` | 언어·지역 |
| `requested_levels_json` | L1/L2/L3 |
| `status` | 설명 상태 |
| `created_at`, `completed_at` | 시각 |

### `decision_explanations`

| 컬럼 | 설명 |
|---|---|
| `explanation_id` | 설명 ID |
| `action` | BUY/HOLD/REDUCE/SELL/REJECT/NO_ACTION |
| `headline` | 요약 제목 |
| `summary_json` | 구조화 요약 |
| `narrative_text` | 자연어 설명 |
| `completeness_score` | 필수 증거 완전성 |
| `fidelity_status` | PASS/DEGRADED/FAIL |
| `generator_version` | 설명 생성기 버전 |
| `schema_version` | 출력 계약 버전 |
| `explanation_hash` | canonical hash |

### `explanation_reasons`

| 컬럼 | 설명 |
|---|---|
| `reason_id` | 이유 ID |
| `explanation_id` | 설명 ID |
| `reason_code` | 표준 코드 |
| `category` | SIGNAL/RISK/DECISION/EXIT/ORDER |
| `severity` | INFO/WARN/BLOCK/CRITICAL |
| `priority` | 표시 순서 |
| `observed_value` | 관측값 |
| `threshold_value` | 기준값 |
| `effect` | APPROVE/REDUCE/BLOCK/FORCE_EXIT |
| `evidence_ref` | 원본 증거 참조 |

### `evidence_bundles`

| 컬럼 | 설명 |
|---|---|
| `evidence_bundle_id` | Bundle ID |
| `run_id` | run ID |
| `decision_id` | Decision ID |
| `signal_snapshot_id` | Signal Snapshot |
| `risk_snapshot_id` | Risk Snapshot |
| `feature_snapshot_id` | Feature Snapshot |
| `policy_snapshot_id` | Policy Snapshot |
| `model_version_ids_json` | 사용 모델 버전 |
| `code_commit_sha` | 실행 코드 commit |
| `artifact_refs_json` | 관련 artifact 목록 |
| `canonical_payload_hash` | 전체 증거 hash |
| `created_at` | 생성 시각 |

### `evidence_items`

| 컬럼 | 설명 |
|---|---|
| `evidence_item_id` | 증거 항목 ID |
| `evidence_bundle_id` | Bundle ID |
| `evidence_type` | SNAPSHOT/RULE/METRIC/MODEL/ORDER |
| `importance` | MANDATORY/MATERIAL/SUPPORTING |
| `source_ref` | 원본 위치 |
| `source_hash` | 원본 hash |
| `payload_json` | 최소 증거 payload |
| `validation_status` | VALID/MISSING/MISMATCH |

### `counterfactual_boundaries`

| 컬럼 | 설명 |
|---|---|
| `boundary_id` | 경계 ID |
| `explanation_id` | 설명 ID |
| `factor_name` | 변경 요인 |
| `observed_value` | 실제 값 |
| `required_boundary` | 결정이 달라지는 최소 경계 |
| `alternative_action` | 경계 통과 시 가능한 행동 |
| `method` | RULE_EXACT/LOCAL_APPROXIMATION |
| `quality_status` | VALID/DEGRADED/UNAVAILABLE |

## 10. 알고리즘

### 10.1 Evidence 수집

```text
1. decision_id로 최종 Decision 조회
2. 동일 run_id의 Signal/Risk/Feature/Policy Snapshot 조회
3. Exit Proposal과 Order Validation 결과가 있으면 연결
4. 모델 추론을 사용한 경우 inference_id와 model version 연결
5. 각 source hash 검증
6. cross-run 또는 만료 Snapshot 발견 시 REJECTED
```

### 10.2 이유 우선순위 결정

```text
CRITICAL / FORCE_EXIT
→ Risk hard block
→ Order rejection / VERIFY_REQUIRED
→ Position sizing 축소
→ 최종 후보 선택 이유
→ Signal 긍정·부정 요인
→ 보조 설명
```

동일 우선순위에서는 `effect severity → rule priority → reason code` 순으로 결정론적으로 정렬한다.

### 10.3 완전성 점수

```text
mandatory_total = MANDATORY 증거 수
mandatory_valid = VALID인 MANDATORY 증거 수
material_total = MATERIAL 증거 수
material_valid = VALID인 MATERIAL 증거 수

completeness =
    0.8 * mandatory_valid / mandatory_total
  + 0.2 * material_valid / max(material_total, 1)
```

- MANDATORY 누락 1개 이상: 최대 `DEGRADED`
- Decision 또는 Risk hard-block 증거 누락: `REJECTED`
- `completeness >= 0.95`: `COMPLETE` 후보

### 10.4 충실도 검증

다음 불변식을 검사한다.

```text
설명 action == Decision action
설명 수량 <= Decision 승인 수량
설명 금액 <= Decision 승인 금액
Risk BLOCK을 APPROVED로 서술하지 않음
NO_ACTION에 가상 주문을 생성하지 않음
FORCE_EXIT 사유를 일반 HOLD보다 낮게 표시하지 않음
표시 수치 == 원본 evidence 수치
```

하나라도 위반하면 `fidelity_status=FAIL`이며 설명을 보고서 기준 기록으로 사용하지 않는다.

### 10.5 Counterfactual 경계

규칙 기반 판단에서만 정확 경계를 제공한다.

예:

```text
관측 종목 비중: 9.7%
정책 최대 비중: 10.0%
예상 매수 후 비중: 12.4%
결정 변경 경계: 주문 금액을 2.7%p 이상 축소
```

모델 기반 local approximation은 "결정 원인"이 아니라 "주변 민감도"로 표시한다.

### 10.6 Canonical hash

```text
canonical_payload = sort_keys({
  run_id,
  decision_id,
  source_hashes,
  normalized_reasons,
  generator_version,
  schema_version,
})

explanation_hash = SHA256(canonical_json(canonical_payload))
```

자연어 표현이나 locale은 감사 기준 hash와 분리한다. 구조화된 이유와 증거가 동일하면 언어가 달라도 동일한 evidence hash를 유지한다.

## 11. 코드 구조

```text
explainability/
├── models.py
├── reason_codes.py
├── collector.py
├── lineage.py
├── normalizer.py
├── contributions.py
├── counterfactual.py
├── composer.py
├── fidelity.py
├── hashing.py
├── repository.py
└── engine.py
```

### 핵심 모델

```python
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

Action = Literal["BUY", "HOLD", "REDUCE", "SELL", "REJECT", "NO_ACTION"]
Severity = Literal["INFO", "WARN", "BLOCK", "CRITICAL"]

@dataclass(frozen=True)
class ExplanationReason:
    code: str
    category: str
    severity: Severity
    effect: str
    observed_value: Decimal | None
    threshold_value: Decimal | None
    evidence_ref: str

@dataclass(frozen=True)
class EvidenceBundle:
    bundle_id: str
    run_id: str
    decision_id: str
    source_hashes: tuple[str, ...]
    reasons: tuple[ExplanationReason, ...]
    canonical_hash: str
```

### 엔진 골격

```python
class DecisionExplainabilityEngine:
    def __init__(self, collector, composer, validator, repository):
        self.collector = collector
        self.composer = composer
        self.validator = validator
        self.repository = repository

    def explain(self, request):
        evidence = self.collector.collect(request)
        evidence.validate_same_run()
        reasons = normalize_and_rank(evidence)
        explanation = self.composer.compose(request, evidence, reasons)
        result = self.validator.validate(explanation, evidence)
        self.repository.save_atomic(evidence, result)
        return result
```

### 이유 정렬 순수 함수

```python
SEVERITY_ORDER = {
    "CRITICAL": 0,
    "BLOCK": 1,
    "WARN": 2,
    "INFO": 3,
}


def rank_reasons(reasons):
    return tuple(sorted(
        reasons,
        key=lambda r: (
            SEVERITY_ORDER[r.severity],
            r.category,
            r.code,
            r.evidence_ref,
        ),
    ))
```

## 12. API 계약

```text
POST /v1/explanations
GET  /v1/explanations/{explanation_id}
GET  /v1/decisions/{decision_id}/explanation
GET  /v1/evidence-bundles/{bundle_id}
POST /v1/explanations/{explanation_id}/verify
```

응답은 구조화 JSON을 기준으로 하며 자연어 narrative는 파생 필드로 취급한다.

## 13. 실패 처리

| 실패 | 처리 |
|---|---|
| Decision 없음 | REJECTED |
| cross-run Snapshot | REJECTED + 감사 이벤트 |
| 필수 source hash 불일치 | REJECTED + 신규 실행 차단 요청 |
| 보조 설명값 누락 | DEGRADED |
| 자연어 생성 실패 | 구조화 설명만 저장 |
| DB 저장 실패 | FAILED, 원본 판단은 변경하지 않음 |
| 설명과 Decision 불일치 | fidelity FAIL + Audit alert |

## 14. 보안과 개인정보

- API key, 계좌번호, 토큰, 인증 header를 Evidence Bundle에 저장하지 않는다.
- broker payload는 allowlist 필드만 보존한다.
- 사용자용 설명에는 내부 경로, stack trace, 비밀 설정값을 노출하지 않는다.
- 감사용 상세 정보 접근은 역할 기반 권한으로 제한한다.

## 15. 테스트 계획

### 단위 테스트

1. reason severity와 rule priority 정렬
2. cross-run Snapshot 차단
3. 필수 증거 누락 시 REJECTED
4. 보조 증거 누락 시 DEGRADED
5. Decision action과 설명 action 일치
6. Risk hard block 우선 표시
7. `NO_ACTION` 설명 생성
8. `FORCE_EXIT` 설명 생성
9. canonical payload 정렬과 hash 재현성
10. locale 변경 시 evidence hash 불변
11. counterfactual rule boundary 계산
12. 민감정보 redaction

### 고정 fixture

```text
A. BUY 승인 + 수량 축소
B. Signal 강함 + Risk symbol limit 차단
C. 후보 없음 + NO_ACTION
D. 손절선 이탈 + FORCE_EXIT
E. 주문 응답 불확실 + VERIFY_REQUIRED
F. 모델 출력 INVALID + 신규 진입 차단
```

### 통합 테스트

```text
Feature Snapshot
→ Model Inference
→ Signal
→ Portfolio Risk
→ Decision
→ Rebalancing
→ Order Validation
→ Explainability
→ Report
```

검증 항목:

- 모든 artifact가 동일 run에 속하는가
- 보고서 수치가 원본 Decision·Accounting과 일치하는가
- BUY/SELL/NO_ACTION 각각 필수 이유가 존재하는가
- 설명 생성기가 주문 호출을 발생시키지 않는가
- 동일 fixture 재실행 시 explanation hash가 동일한가

### 속성 기반 테스트

- 설명 수량은 Decision 승인 수량을 초과하지 않는다.
- Risk hard block이 존재하면 설명에 반드시 BLOCK 이상 severity로 포함된다.
- 원본 action을 변경하면 이전 explanation hash와 같을 수 없다.
- evidence 순서를 섞어도 canonical hash는 동일하다.
- 서로 다른 run의 artifact를 결합하면 항상 거부된다.

### 장애 테스트

- Snapshot repository timeout
- 일부 model explanation 누락
- 중복 reason event
- 잘못된 Decimal 형식
- DB transaction rollback
- 매우 긴 narrative 생성 결과

## 16. 수용 기준

- BUY/HOLD/REDUCE/SELL/REJECT/NO_ACTION 모두 구조화 설명 가능
- Decision과 Risk hard block의 필수 증거 누락을 탐지
- 동일 fixture에서 동일 evidence/explanation hash 생성
- 사용자용 L1과 감사용 L3를 동일 Evidence Bundle에서 생성
- 자연어 생성 실패 시에도 구조화 JSON 설명 보존
- Explainability Engine 경로에서 주문·포트폴리오 상태 변경 호출 0건

## 17. 구현 우선순위

1. `ExplanationReason`, `EvidenceItem`, `EvidenceBundle` 불변 모델
2. 표준 reason code registry
3. 동일 run·hash 검증 Collector
4. 결정론적 reason normalizer와 ranker
5. fidelity·completeness validator
6. canonical hash 생성기
7. SQLite Repository와 원자적 저장
8. BUY/RISK_BLOCK/NO_ACTION/FORCE_EXIT 고정 fixture
9. Report Engine JSON adapter
10. 모델 explanation과 counterfactual boundary 확장
