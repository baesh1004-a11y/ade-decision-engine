# 25. Execution Reconciliation & Recovery Engine v2

## 1. 목적

Execution Reconciliation & Recovery Engine v2는 내부 주문·체결 상태와 브로커 원장, 계좌 잔고, 미체결 내역을 대사하여 주문 생명주기를 확정하고 불확실 상태를 안전하게 복구하는 실행 후 통제 계층이다.

이 엔진은 새로운 투자 판단이나 주문을 만들지 않는다. `VERIFY_REQUIRED`, 부분체결, 응답 유실, 중복 이벤트, 지연 체결, 취소 경합처럼 내부 상태만으로 확정할 수 없는 상황을 브로커 증거와 대조해 표준 상태로 수렴시킨다.

## 2. 책임 경계

### 담당

- 내부 `order_submissions`, `order_executions`, `execution_events`와 브로커 상태 대사
- `VERIFY_REQUIRED` 주문의 접수 여부 확인
- 부분체결·복수 체결 이벤트 누적 검증
- 중복 체결 이벤트 제거
- 취소·정정·만료·거부 상태 확정
- 브로커 체결 수량과 내부 체결 수량 차이 탐지
- 계좌 현금·보유수량과 내부 회계원장 차이 탐지
- 자동 복구 가능 항목과 수동 검토 항목 분리
- 예약금·예약수량 해제 또는 유지 판단
- Portfolio Accounting, Audit, Report Engine용 정합성 이벤트 발행

### 담당하지 않음

- 신규 매수·매도 판단
- 주문 수량 확대 또는 가격 변경
- 불확실 주문의 자동 재주문
- 리스크 한도 변경
- 회계 정책 변경
- 브로커 원본 기록 삭제

## 3. 아키텍처

```text
Order Validation & Routing Engine
        ↓
Order Submission / VERIFY_REQUIRED
        ↓
Execution Monitor
        ↓
Execution Reconciliation & Recovery
   ├─ Internal State Loader
   ├─ Broker Evidence Collector
   ├─ Event Deduplicator
   ├─ Quantity / Cash Reconciler
   ├─ State Resolver
   ├─ Recovery Policy Engine
   └─ Reconciliation Journal
        ↓
Portfolio Accounting & Performance
Audit & Compliance
Report Engine
Manual Review Queue
```

## 4. 입력 모델

```python
@dataclass(frozen=True)
class ReconciliationRequest:
    reconciliation_id: str
    run_id: str
    account_id: str
    market: str
    order_request_id: str | None
    broker_order_id: str | None
    mode: str
    reason: str
    requested_at: datetime
```

추가 입력:

- 내부 주문 요청·전송·체결 상태
- 미해결 예약금·예약수량
- 브로커 주문 조회 결과
- 브로커 체결 내역
- 브로커 잔고·매도 가능 수량·매수 가능 금액
- 내부 포트폴리오 원장과 포지션
- 정책 스냅샷과 대사 허용 오차

## 5. 출력 모델

```python
@dataclass(frozen=True)
class ReconciliationResult:
    reconciliation_id: str
    order_request_id: str | None
    broker_order_id: str | None
    previous_status: str
    resolved_status: str
    resolution: str
    internal_filled_quantity: int
    broker_filled_quantity: int
    quantity_difference: int
    cash_difference: float
    position_difference: int
    reservation_action: str
    auto_recovered: bool
    manual_review_required: bool
    reason_codes: tuple[str, ...]
    evidence_hash: str
    completed_at: datetime
```

## 6. 표준 상태

| 상태 | 의미 |
|---|---|
| MATCHED | 내부와 브로커 상태 일치 |
| RECOVERED_SUBMITTED | 전송 응답은 불확실했으나 브로커 접수 확인 |
| RECOVERED_FILLED | 누락된 체결을 브로커 증거로 복구 |
| RECOVERED_CANCELLED | 취소 결과를 브로커 증거로 확정 |
| RECOVERED_REJECTED | 브로커 거부를 확정 |
| NO_BROKER_ORDER | 브로커 접수 없음이 확인됨 |
| PARTIAL_MISMATCH | 일부 필드는 일치하나 차이가 남음 |
| LEDGER_MISMATCH | 내부 회계·포지션과 브로커 잔고 불일치 |
| DUPLICATE_EVENT_IGNORED | 중복 체결 이벤트 제외 |
| MANUAL_REVIEW | 자동 복구 불가 |
| RECONCILIATION_FAILED | 조회·저장·증거 검증 실패 |

## 7. 핵심 불변식

```text
브로커 체결 수량은 주문 요청 수량을 초과할 수 없다.
동일 broker execution ID는 한 번만 원장에 반영한다.
VERIFY_REQUIRED는 대사 완료 전 자동 재전송할 수 없다.
내부 체결 수량은 승인된 브로커 체결 증거의 합과 일치해야 한다.
예약금·예약수량은 미해결 주문이 존재할 때 임의 해제하지 않는다.
복구 이벤트는 원본 이벤트를 수정하지 않고 append-only로 기록한다.
자동 복구는 금액·수량을 확대하지 않는다.
수동 조정은 요청자와 승인자를 분리하고 감사 이벤트를 남긴다.
```

## 8. 대사 알고리즘

### 8.1 증거 수집

```text
내부 주문·체결 상태 로드
→ broker_order_id 또는 client order key로 브로커 조회
→ 주문 상태·체결 목록·취소 결과 수집
→ 원본 응답 canonical JSON 저장
→ evidence hash 계산
```

### 8.2 이벤트 중복 제거

우선 키:

```text
broker + account_id + broker_order_id + broker_execution_id
```

보조 fingerprint:

```text
symbol + side + quantity + price + execution_time + broker_order_id
```

동일 키가 이미 처리된 경우 `DUPLICATE_EVENT_IGNORED`로 기록하며 회계원장에는 재반영하지 않는다.

### 8.3 수량 대사

```python
broker_filled = sum(unique_broker_fills.quantity)
internal_filled = sum(unique_internal_fills.quantity)
quantity_difference = broker_filled - internal_filled
```

판정:

- 차이 0: `MATCHED`
- 브로커 수량이 더 큼: 누락 체결 복구 후보
- 내부 수량이 더 큼: `MANUAL_REVIEW`
- 브로커 수량이 주문 수량 초과: CRITICAL 감사 위반

### 8.4 상태 확정

```python
if broker_order_not_found and transport_confirmed_not_sent:
    resolved = "NO_BROKER_ORDER"
elif broker_status == "FILLED" and broker_filled == requested_quantity:
    resolved = "RECOVERED_FILLED" if previous_status != "FILLED" else "MATCHED"
elif 0 < broker_filled < requested_quantity:
    resolved = "PARTIALLY_FILLED"
elif broker_status == "CANCELLED":
    resolved = "RECOVERED_CANCELLED"
elif broker_status == "REJECTED":
    resolved = "RECOVERED_REJECTED"
else:
    resolved = "MANUAL_REVIEW"
```

### 8.5 예약 처리

| 상태 | 예약금·예약수량 처리 |
|---|---|
| SUBMITTED / PARTIALLY_FILLED / VERIFY_REQUIRED | 잔여 수량만큼 유지 |
| FILLED | 전부 해제 후 회계 반영 |
| CANCELLED / REJECTED / EXPIRED / NO_BROKER_ORDER | 잔여 예약 해제 |
| MANUAL_REVIEW | 유지 |

예약 변경과 상태 확정은 가능한 한 동일 트랜잭션으로 저장한다.

## 9. 현금·포지션 대사

```text
expected_cash
= opening_cash
+ confirmed_sell_proceeds
- confirmed_buy_cost
- fees
- taxes
+ external_cash_flows
```

```text
expected_position(symbol)
= opening_quantity
+ confirmed_buy_quantity
- confirmed_sell_quantity
+ corporate_action_adjustments
```

허용 오차를 초과하면 `LEDGER_MISMATCH`를 발생시킨다.

기본 정책 예시:

| 항목 | 허용 오차 |
|---|---:|
| 체결 수량 | 0주 |
| 포지션 수량 | 0주 |
| 현금 | 10원 또는 브로커 반올림 규칙 |
| 평균 체결가 | 호가단위 이하 |
| 수수료·세금 | 정책별 반올림 오차 이하 |

## 10. 복구 정책

### 자동 복구 허용

- 브로커 주문 접수 확인 후 내부 상태를 SUBMITTED로 전환
- 누락된 고유 체결 이벤트 append
- 중복 이벤트 무시
- 확정 취소·거부·만료 상태 반영
- 잔여 예약금·예약수량 재계산

### 수동 검토 필수

- 내부 체결 수량이 브로커보다 큼
- 브로커 원장과 계좌 잔고가 서로 불일치
- 동일 execution ID에 서로 다른 수량·가격 존재
- broker_order_id 매핑 불가
- 금액·포지션 차이가 허용 오차 초과
- 실계좌에서 원인 불명 주문 발견
- 감사 해시 또는 원본 증거 누락

## 11. 데이터베이스

### `reconciliation_runs`

| 컬럼 | 설명 |
|---|---|
| reconciliation_id | 대사 실행 ID |
| run_id | ADE 실행 ID |
| account_id | 계좌 ID |
| market | 시장 |
| trigger_reason | VERIFY_REQUIRED/PERIODIC/EOD/MANUAL |
| status | RUNNING/COMPLETED/PARTIAL/FAILED |
| started_at, finished_at | 실행 시각 |
| evidence_hash | 전체 증거 해시 |
| error_count | 오류 수 |

### `reconciliation_items`

| 컬럼 | 설명 |
|---|---|
| item_id | 항목 ID |
| reconciliation_id | 대사 실행 ID |
| order_request_id | 내부 주문 ID |
| broker_order_id | 브로커 주문 ID |
| previous_status | 이전 상태 |
| resolved_status | 확정 상태 |
| internal_filled_quantity | 내부 체결 수량 |
| broker_filled_quantity | 브로커 체결 수량 |
| quantity_difference | 수량 차이 |
| cash_difference | 현금 차이 |
| position_difference | 포지션 차이 |
| resolution | MATCH/RECOVER/MANUAL_REVIEW |
| reason_codes | JSON |

### `reconciliation_evidence`

| 컬럼 | 설명 |
|---|---|
| evidence_id | 증거 ID |
| reconciliation_id | 대사 실행 ID |
| source_type | BROKER_ORDER/BROKER_FILL/BALANCE/INTERNAL |
| source_ref | 외부·내부 참조 ID |
| payload_json | 원본 또는 정규화 payload |
| payload_hash | SHA-256 |
| collected_at | 수집 시각 |

### `recovery_actions`

| 컬럼 | 설명 |
|---|---|
| recovery_action_id | 복구 동작 ID |
| item_id | 대사 항목 ID |
| action_type | APPEND_FILL/UPDATE_STATUS/RELEASE_RESERVATION/HOLD_RESERVATION |
| before_json | 이전 상태 |
| after_json | 변경 상태 |
| auto_applied | 자동 적용 여부 |
| approved_by | 수동 승인자 |
| created_at | 생성 시각 |

### `manual_review_cases`

| 컬럼 | 설명 |
|---|---|
| case_id | 검토 사건 ID |
| item_id | 대사 항목 ID |
| severity | INFO/WARNING/CRITICAL |
| case_type | LEDGER_MISMATCH/UNKNOWN_ORDER/CONFLICTING_EVIDENCE/etc |
| status | OPEN/UNDER_REVIEW/RESOLVED/REJECTED |
| assigned_to | 담당자 |
| resolution_note | 처리 내용 |
| created_at, resolved_at | 시각 |

## 12. 코드 구조

```text
execution/
  reconciliation/
    __init__.py
    models.py
    service.py
    evidence.py
    dedup.py
    resolver.py
    recovery.py
    repository.py
    policy.py
    manual_review.py

brokers/
  reconciliation_adapter.py

portfolio/
  reconciliation_bridge.py

tests/
  test_reconciliation_service.py
  test_reconciliation_dedup.py
  test_reconciliation_verify_required.py
  test_reconciliation_partial_fill.py
  test_reconciliation_ledger.py
  test_reconciliation_recovery.py
```

## 13. 참조 코드

```python
class ExecutionReconciliationService:
    def reconcile(self, request: ReconciliationRequest) -> ReconciliationResult:
        internal = self.repository.load_internal_state(request)
        evidence = self.broker.collect_evidence(request, internal)
        unique_fills = self.deduplicator.unique_fills(evidence.fills)

        broker_filled = sum(fill.quantity for fill in unique_fills)
        internal_filled = internal.filled_quantity
        resolution = self.resolver.resolve(
            internal=internal,
            broker_order=evidence.order,
            broker_fills=unique_fills,
        )

        plan = self.recovery_policy.build_plan(
            internal=internal,
            resolution=resolution,
            broker_filled=broker_filled,
            internal_filled=internal_filled,
        )

        with self.repository.transaction():
            self.repository.save_evidence(request, evidence)
            self.repository.apply_recovery_plan(plan)
            result = self.repository.complete_reconciliation(
                request=request,
                resolution=resolution,
                plan=plan,
            )

        self.publisher.publish(result)
        return result
```

## 14. 테스트 계획

### 단위 테스트

- 동일 broker execution ID가 한 번만 반영됨
- 부분체결 수량과 가중평균 체결가가 정확함
- VERIFY_REQUIRED 주문이 브로커 접수 확인 시 SUBMITTED로 복구됨
- 브로커 미접수 확정 시 NO_BROKER_ORDER로 종료됨
- FILLED 주문의 예약금·예약수량이 해제됨
- PARTIALLY_FILLED 주문은 잔여 수량 예약만 유지함
- 내부 체결 수량이 브로커보다 크면 자동 복구하지 않음
- 주문 수량 초과 체결 증거는 CRITICAL 처리
- 동일 입력과 증거는 동일 evidence hash를 생성함

### DB 테스트

- 증거·복구 동작·상태 확정이 원자적으로 저장됨
- append-only 실행 이벤트를 수정할 수 없음
- 동일 execution ID에 unique constraint 적용
- 재실행 시 이미 적용된 복구가 중복 반영되지 않음
- manual review case가 원본 evidence와 연결됨

### 통합 테스트

- Order Routing의 VERIFY_REQUIRED → Reconciliation → Execution Monitor → Portfolio Accounting 전체 흐름
- 부분체결 3회 후 전체 체결 수렴
- 취소 요청과 체결 이벤트 경합
- 브로커 응답 유실 후 주문 조회로 복구
- EOD 계좌 잔고와 내부 원장 대사
- 복구 결과가 Audit·Report에 전달됨

### 실패 주입 테스트

- 브로커 주문 조회 timeout
- 체결 조회 일부 누락
- DB commit 실패
- evidence 저장 후 recovery 적용 전 장애
- 동일 체결 이벤트 동시 수신
- broker_order_id가 없는 내부 주문
- 브로커가 서로 모순된 주문·체결 상태 반환

### 회귀·속성 테스트

- 체결 이벤트 순서가 바뀌어도 최종 수량·평균가 동일
- 같은 증거를 여러 번 대사해도 포지션·현금이 변하지 않음
- 자동 복구 후 체결 수량은 항상 주문 수량 이하
- 예약금·예약수량은 음수가 되지 않음
- 원장 재생 결과와 저장 포지션이 일치함

## 15. 완료 기준

- `VERIFY_REQUIRED` 주문의 브로커 접수 여부를 확정할 수 있다.
- 부분체결·전체체결·취소·거부·미접수를 표준 상태로 수렴시킨다.
- 동일 체결 이벤트를 중복 반영하지 않는다.
- 내부 체결·현금·포지션과 브로커 원장의 차이를 탐지한다.
- 자동 복구와 수동 검토 대상을 명확히 분리한다.
- 모든 증거와 복구 동작이 감사 가능한 append-only 기록으로 남는다.
- 자동 재주문 없이 주문 상태를 복구한다.

## 16. 구현 우선순위

1. broker execution ID 기반 중복 제거 저장소
2. `VERIFY_REQUIRED` 단건 대사 서비스
3. 부분체결 수량·평균가 대사
4. 예약금·예약수량 재계산
5. DRY_RUN/PAPER fixture 통합 테스트
6. EOD 계좌·원장 대사
7. Manual Review Queue
8. LIVE 브로커 조회 연결은 별도 안전 검증 후 활성화

## 17. 다음 설계 대상

다음은 **Portfolio Rebalancing & Exit Orchestration Engine v1**을 설계한다. 이 엔진은 보유 포지션의 목표 비중, 손절·추적손절·이익보호, 섹터·상관 집중도 변화, 현금 회복 필요성을 결합해 축소·청산·재균형 우선순위를 생성한다.