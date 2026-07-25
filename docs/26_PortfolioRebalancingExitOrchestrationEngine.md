# 26. Portfolio Rebalancing & Exit Orchestration Engine v1

## 1. 목적

Portfolio Rebalancing & Exit Orchestration Engine은 보유 포지션의 축소·청산·유지 우선순위를 통합적으로 결정하는 포트폴리오 관리 계층이다.

이 엔진은 신규 종목을 발굴하지 않는다. Signal, Risk, Portfolio Accounting, Market Regime 결과를 사용하여 다음 행동을 조정한다.

- 손절 및 강제 청산
- 추적손절과 이익 보호
- 신호 약화에 따른 축소
- 종목·섹터·상관 군집 집중도 완화
- 최소 현금 비중 회복
- 포트폴리오 변동성 및 낙폭 축소
- 여러 매도 후보의 실행 우선순위 결정

## 2. 책임 경계

### 담당

- 보유 종목별 Exit Trigger 평가
- 강제 청산·축소·선택적 리밸런싱 분류
- 포트폴리오 수준의 현금·집중도·변동성 목표 복구
- 매도 대상과 수량 우선순위 산정
- 동일 종목의 중복 Exit Intent 방지
- Decision & Position Sizing Engine에 표준 Exit Proposal 전달
- 실행 이유, 정책, 스냅샷, 계산 근거 저장

### 담당하지 않음

- 신규 매수 후보 생성
- 브로커 주문 전송
- 체결 상태 확정
- 원장 직접 수정
- 과거 체결 기록 수정
- Risk Engine의 하드 차단 해제

## 3. 아키텍처

```text
Portfolio State / Accounting Snapshot
        +
Position Signal / Exit Signal
        +
Portfolio Risk & Exposure
        +
Market Regime / Volatility
        +
Rebalancing Policy
        ↓
Portfolio Rebalancing & Exit Orchestration Engine
   ├─ Position Exit Evaluator
   ├─ Protection Rule Evaluator
   ├─ Concentration Resolver
   ├─ Cash Recovery Planner
   ├─ Portfolio Risk Reducer
   ├─ Exit Priority Ranker
   ├─ Quantity Planner
   └─ Conflict / Duplicate Guard
        ↓
Exit Proposal
        ↓
Decision & Position Sizing Engine
        ↓
Order Validation & Routing Engine
```

## 4. 입력

```python
RebalanceInput(
    run_id="RUN-20260725-001",
    portfolio_snapshot_id="PF-20260725-CLOSE",
    risk_snapshot_id="RSK-20260725-001",
    signal_snapshot_id="SIG-20260725-001",
    regime_snapshot_id="REG-20260725-001",
    nav=10_036_000,
    cash=9_223_000,
    high_watermark_nav=10_100_000,
    daily_pnl_pct=-0.004,
    drawdown_pct=-0.0063,
    positions=[...],
    policy=RebalancingPolicy(),
)
```

보유 종목 입력에는 최소한 다음 정보가 필요하다.

- symbol
- quantity, sellable_quantity
- average_cost, current_price
- market_value, portfolio_weight
- unrealized_pnl_pct
- highest_price_since_entry
- holding_days
- sector, correlation_cluster
- signal_action, signal_score, confidence
- volatility_pct, liquidity_value
- open_sell_quantity
- pending_exit_intent_id

## 5. 출력

```python
ExitProposal(
    proposal_id="EXIT-20260725-0001",
    symbol="005930",
    action="REDUCE",
    priority="HIGH",
    reason_codes=["TRAILING_STOP", "SIGNAL_WEAKENING"],
    requested_quantity=1,
    target_remaining_quantity=2,
    reference_price=260_000,
    urgency_score=78.4,
    expected_cash_after=9_483_000,
    policy_version="rebalance-v1",
    status="PROPOSED",
)
```

가능한 행동:

| Action | 의미 |
|---|---|
| HOLD | 포지션 유지 |
| REDUCE | 일부 축소 |
| SELL | 전량 청산 |
| FORCE_REDUCE | 리스크 한도 복구를 위한 강제 축소 |
| FORCE_EXIT | 하드 리스크 또는 거래 불능 위험에 따른 전량 청산 |
| DEFER | 매도 필요성은 있으나 실행 조건 불충족 |
| MANUAL_REVIEW | 데이터·원장·체결 불일치로 자동 처리 금지 |

## 6. 정책 기본값

| Policy | Default | 설명 |
|---|---:|---|
| hard_stop_loss_pct | -7% | 전량 청산 손절 기준 |
| reduce_loss_pct | -4% | 일부 축소 검토 기준 |
| trailing_stop_pct | 8% | 고점 대비 하락 기준 |
| take_profit_start_pct | 12% | 이익 보호 시작 기준 |
| take_profit_reduce_ratio | 25% | 1차 이익 실현 비율 |
| signal_exit_threshold | 35 | 약한 신호 청산 검토 기준 |
| max_symbol_weight_pct | 10% | 종목 최대 비중 |
| max_sector_weight_pct | 30% | 섹터 최대 비중 |
| max_cluster_weight_pct | 25% | 상관 군집 최대 비중 |
| min_cash_buffer_pct | 10% | 최소 현금 비중 |
| max_total_exposure_pct | 90% | 최대 총 익스포저 |
| max_daily_loss_pct | 2% | 일일 손실 한도 |
| drawdown_reduce_start_pct | 5% | 포트폴리오 축소 시작 낙폭 |
| drawdown_force_reduce_pct | 10% | 강제 축소 낙폭 |
| min_trade_amount | 100_000 | 최소 리밸런싱 금액 |
| exit_cooldown_minutes | 30 | 중복 Exit Intent 방지 시간 |

정책은 Configuration & Policy Engine의 승인된 불변 스냅샷으로 제공되어야 한다.

## 7. 규칙 우선순위

낮은 우선순위 규칙이 높은 우선순위 규칙을 상쇄할 수 없다.

```text
1. 거래정지·상장폐지·회계 불일치 수동 검토
2. FORCE_EXIT 하드 리스크
3. 손절 및 치명적 신호 붕괴
4. FORCE_REDUCE 포트폴리오 한도 복구
5. 추적손절과 이익 보호
6. 신호 약화에 따른 일반 REDUCE / SELL
7. 집중도·현금·변동성 리밸런싱
8. HOLD
```

## 8. 포지션 보호 규칙

### 8.1 손절

```python
if unrealized_pnl_pct <= hard_stop_loss_pct:
    action = "SELL"
    reason = "HARD_STOP_LOSS"
```

Risk Engine이 `FORCE_EXIT`를 반환한 경우 손익 여부와 무관하게 전량 청산 후보로 만든다.

### 8.2 추적손절

```python
peak_drawdown_pct = current_price / highest_price_since_entry - 1

if peak_drawdown_pct <= -trailing_stop_pct:
    action = "REDUCE" if signal_score >= signal_exit_threshold else "SELL"
```

### 8.3 이익 보호

```python
if unrealized_pnl_pct >= take_profit_start_pct and signal_is_weakening:
    reduce_quantity = floor(quantity * take_profit_reduce_ratio)
```

단순 수익 달성만으로 자동 매도하지 않는다. 신호 약화, 변동성 급증, 국면 악화 중 하나 이상을 함께 확인한다.

### 8.4 신호 붕괴

- `SELL` 또는 `AVOID` 신호: 전량 청산 우선 검토
- `REDUCE` 신호: 목표 비중까지 축소
- 신호 만료·품질 불량: 신규 확대 금지, Exit는 다른 보호 규칙으로만 수행

## 9. 포트폴리오 리밸런싱 규칙

### 9.1 종목 집중도

```python
excess_value = max(0, position_value - nav * max_symbol_weight_pct)
```

초과 금액 이상을 축소하되 최소 주문 단위와 sellable quantity를 적용한다.

### 9.2 섹터·상관 군집 집중도

집중 그룹 내 축소 순서는 다음 점수로 정한다.

```python
exit_priority_score = (
    weak_signal_score * 0.30
    + loss_risk_score * 0.25
    + volatility_score * 0.15
    + liquidity_score * 0.10
    + concentration_contribution * 0.20
)
```

- 신호가 약한 종목 우선
- 손실 위험이 큰 종목 우선
- 집중도 기여가 큰 종목 우선
- 동일 조건이면 유동성이 높은 종목을 먼저 축소하여 시장 충격을 줄인다

### 9.3 현금 하한 복구

```python
cash_shortfall = max(0, nav * min_cash_buffer_pct - cash)
```

필요 현금만큼 매도 후보를 우선순위대로 선택한다. 예상 세금·수수료를 반영한 순유입 현금을 사용한다.

### 9.4 총 익스포저 복구

```python
exposure_excess = max(0, invested_value - nav * max_total_exposure_pct)
```

현금 하한과 총 익스포저 조건이 동시에 위반되면 더 큰 매도 필요금액을 기준으로 한다.

### 9.5 포트폴리오 낙폭 대응

| Drawdown | 행동 |
|---:|---|
| 0% ~ -5% | 정상 정책 |
| -5% 이하 | 신규 매수 제한, 고위험 포지션 축소 검토 |
| -10% 이하 | FORCE_REDUCE, 목표 총 익스포저 하향 |
| -15% 이하 | 비필수 포지션 대폭 축소, 수동 검토 경고 |

시장 국면이 `HIGH_VOL` 또는 `LIQUIDITY_STRESS`이면 축소 계수를 강화한다.

## 10. 수량 계획

```python
required_sell_value = max(
    symbol_excess,
    sector_recovery_need,
    cluster_recovery_need,
    cash_shortfall,
    exposure_excess,
    drawdown_reduction_need,
)

raw_quantity = ceil(required_sell_value / reference_price)
requested_quantity = min(
    raw_quantity,
    sellable_quantity - open_sell_quantity,
    position_quantity,
)
```

전량 청산 규칙이 아니면 매도 후 잔여 포지션이 최소 주문금액 미만의 잔여물(dust)이 되는지 검사한다. 잔여물이 발생하면 전량 청산 또는 축소 보류 정책을 적용한다.

## 11. 충돌 처리

- `SELL`과 `HOLD`가 충돌하면 우선순위가 높은 보호 규칙을 따른다.
- 여러 규칙이 동일 종목을 축소하면 최대 필요 수량을 사용하되 보유·매도가능 수량을 초과하지 않는다.
- 기존 미체결 매도 주문이 있으면 해당 예약수량을 차감한다.
- `VERIFY_REQUIRED` 또는 대사 미완료 주문이 존재하면 추가 Exit Intent 생성을 차단하고 `MANUAL_REVIEW`로 보낸다.
- Exit Engine은 이미 제출된 주문을 직접 취소하거나 수정하지 않는다.

## 12. 데이터베이스

### `rebalance_runs`

| Column | Type | Description |
|---|---|---|
| run_id | TEXT PK | 리밸런싱 실행 ID |
| portfolio_snapshot_id | TEXT | 포트폴리오 스냅샷 |
| risk_snapshot_id | TEXT | 리스크 스냅샷 |
| signal_snapshot_id | TEXT | 신호 스냅샷 |
| regime_snapshot_id | TEXT | 시장 국면 스냅샷 |
| policy_version | TEXT | 정책 버전 |
| status | TEXT | PENDING/RUNNING/COMPLETED/FAILED |
| started_at | TIMESTAMP | 시작 시각 |
| finished_at | TIMESTAMP | 종료 시각 |
| input_hash | TEXT | 입력 해시 |
| output_hash | TEXT | 결과 해시 |

### `exit_evaluations`

| Column | Type | Description |
|---|---|---|
| evaluation_id | TEXT PK | 평가 ID |
| run_id | TEXT FK | 실행 ID |
| symbol | TEXT | 종목 코드 |
| current_quantity | INTEGER | 현재 수량 |
| sellable_quantity | INTEGER | 매도 가능 수량 |
| current_weight | NUMERIC | 현재 비중 |
| pnl_pct | NUMERIC | 평가손익률 |
| peak_drawdown_pct | NUMERIC | 진입 후 고점 대비 하락률 |
| signal_score | NUMERIC | 신호 점수 |
| risk_status | TEXT | 리스크 상태 |
| selected_action | TEXT | 선택 행동 |
| urgency_score | NUMERIC | 긴급도 |
| reason_codes_json | JSON | 사유 코드 |
| created_at | TIMESTAMP | 생성 시각 |

### `exit_proposals`

| Column | Type | Description |
|---|---|---|
| proposal_id | TEXT PK | 제안 ID |
| run_id | TEXT FK | 실행 ID |
| symbol | TEXT | 종목 코드 |
| action | TEXT | REDUCE/SELL/FORCE_REDUCE/FORCE_EXIT |
| requested_quantity | INTEGER | 요청 수량 |
| target_remaining_quantity | INTEGER | 목표 잔여수량 |
| reference_price | NUMERIC | 기준 가격 |
| expected_net_cash | NUMERIC | 예상 순현금 유입 |
| priority_rank | INTEGER | 실행 순위 |
| status | TEXT | PROPOSED/ACCEPTED/REJECTED/EXPIRED |
| decision_id | TEXT | 후속 Decision ID |
| proposal_hash | TEXT | 결정론적 해시 |
| expires_at | TIMESTAMP | 만료 시각 |

### `rebalance_constraints`

| Column | Type | Description |
|---|---|---|
| constraint_id | TEXT PK | 제약 ID |
| run_id | TEXT FK | 실행 ID |
| constraint_type | TEXT | CASH/SYMBOL/SECTOR/CLUSTER/EXPOSURE/DRAWDOWN |
| current_value | NUMERIC | 현재 값 |
| limit_value | NUMERIC | 한도 값 |
| recovery_value | NUMERIC | 복구 필요 금액 |
| status | TEXT | OK/BREACHED/RECOVERED/PARTIAL |

### `rebalance_events`

append-only 이벤트 저널로 `RUN_CREATED`, `POSITION_EVALUATED`, `PROPOSAL_CREATED`, `PROPOSAL_ACCEPTED`, `PROPOSAL_EXPIRED`, `MANUAL_REVIEW_REQUIRED`를 기록한다.

## 13. 알고리즘

```python
def plan_rebalance(input: RebalanceInput) -> RebalanceResult:
    validate_snapshot_contracts(input)
    run = repository.create_run(input)

    constraints = calculate_portfolio_constraints(input)
    evaluations = []

    for position in input.positions:
        evaluation = evaluate_position_exit(
            position=position,
            portfolio=input,
            constraints=constraints,
            policy=input.policy,
        )
        evaluations.append(evaluation)

    if has_unreconciled_execution(input):
        return manual_review(run, evaluations, "UNRECONCILED_EXECUTION")

    proposals = merge_overlapping_exit_needs(evaluations)
    proposals = rank_exit_proposals(proposals)
    proposals = allocate_required_sell_value(
        proposals=proposals,
        constraints=constraints,
        nav=input.nav,
        cash=input.cash,
    )
    proposals = apply_sellable_and_open_order_limits(proposals)
    proposals = remove_below_minimum_or_dust_proposals(proposals)

    verify_projected_portfolio(input, proposals)
    repository.complete_run(run, constraints, evaluations, proposals)
    return RebalanceResult(run_id=run.run_id, proposals=proposals)
```

## 14. 코드 구조

```text
portfolio/rebalancing/
  __init__.py
  models.py
  policy.py
  engine.py
  exit_rules.py
  protection.py
  constraints.py
  ranking.py
  sizing.py
  conflict.py
  repository.py

 tests/
  test_rebalance_exit_rules.py
  test_rebalance_constraints.py
  test_rebalance_ranking.py
  test_rebalance_sizing.py
  test_rebalance_conflicts.py
  test_rebalance_integration.py
```

## 15. 인터페이스 초안

```python
@dataclass(frozen=True)
class ExitProposal:
    proposal_id: str
    run_id: str
    symbol: str
    action: str
    requested_quantity: int
    target_remaining_quantity: int
    reference_price: float
    expected_net_cash: float
    priority_rank: int
    reason_codes: tuple[str, ...]
    expires_at: datetime


class PortfolioRebalancingEngine:
    def plan(self, request: RebalanceInput) -> RebalanceResult:
        ...
```

## 16. 불변식

- Exit 수량은 0보다 크고 sellable quantity 이하이다.
- 동일 종목의 동시 Exit Proposal 합계는 매도 가능 수량을 초과하지 않는다.
- `FORCE_EXIT`은 목표 잔여수량 0이다.
- Exit Engine은 Risk·Decision 승인보다 공격적인 매수 행동을 생성하지 않는다.
- 매도 제안 후 예상 포트폴리오는 위반된 제약을 악화시키지 않는다.
- 원장·브로커 대사가 미완료이면 자동 Exit Proposal을 제출하지 않는다.
- 동일 입력 스냅샷과 정책은 동일한 proposal hash를 생성한다.
- 제안 만료 후에는 Order Engine 입력으로 사용할 수 없다.
- 모든 결과는 원인 규칙과 입력 스냅샷으로 역추적 가능하다.

## 17. 테스트 계획

### 단위 테스트

- -7% 손실에서 SELL 생성
- -4% 손실에서 REDUCE 검토
- 고점 대비 8% 하락 시 trailing stop 작동
- 수익 12% 이상과 신호 약화 시 일부 이익 보호
- 종목 10% 초과분만 축소
- 현금 10% 미달 시 필요 현금만큼 매도 계획
- 섹터·상관 군집 초과 시 약한 신호 종목 우선
- sellable quantity와 미체결 매도수량 반영
- 최소 주문금액과 dust 처리
- 동일 종목 다중 규칙 병합

### 통합 테스트

- Portfolio Accounting Snapshot → Rebalancing → Decision → OrderIntent 변환
- `FORCE_REDUCE`가 신규 BUY보다 먼저 처리되는지 확인
- Execution Reconciliation 미완료 시 `MANUAL_REVIEW`
- 매도 체결 후 현금·집중도·총 익스포저 한도 복구 확인
- Report Engine이 제안·결정·체결 결과를 설명 가능한지 확인

### 속성 기반 테스트

무작위 포트폴리오와 정책을 생성해 다음을 검증한다.

- 제안 수량 합계가 보유 및 매도 가능 수량을 초과하지 않음
- 예상 현금이 매도 전보다 감소하지 않음
- 종목·섹터·군집·총 익스포저 위반도가 악화되지 않음
- 동일 입력에서 결과 순위와 hash가 결정론적임

### 실패 주입 테스트

- 가격 누락 또는 stale quote
- Portfolio Snapshot과 Risk Snapshot run 불일치
- 원장 수량과 브로커 수량 불일치
- DB 저장 실패
- 중복 Trigger
- 제안 생성 후 정책 버전 변경
- Order Engine 전달 전 proposal 만료

### 회귀 테스트

- 기존 Decision Engine의 손절·추적손절 규칙 결과 보존
- 동일 fixture에서 정책 변경 전후 차이 명시
- FORCE_EXIT이 일반 HOLD 신호에 의해 취소되지 않음

### 성능 테스트

- 1,000개 보유 포지션 평가 1초 이내 목표
- 3,000개 종목 메타데이터와 섹터·군집 계산 3초 이내 목표
- 동일 포트폴리오 동시 요청 시 중복 Proposal 0건

## 18. 완료 기준

- 보유 종목별 HOLD/REDUCE/SELL/FORCE_REDUCE/FORCE_EXIT 판단 가능
- 손절·추적손절·이익보호 규칙의 우선순위 테스트 통과
- 현금·종목·섹터·군집·총 익스포저 복구 계획 산출
- 중복·미체결·대사 미완료 상황에서 안전 차단
- Decision Engine이 소비할 수 있는 표준 Exit Proposal 생성
- 결과와 정책·스냅샷·사유 코드의 감사 추적 가능

## 19. 구현 순서

1. `models.py`, `policy.py` 도메인 모델
2. 순수 함수 기반 손절·추적손절·이익보호 규칙
3. 포트폴리오 제약 계산기
4. Exit Proposal 병합·순위화·수량 계산
5. SQLite repository와 proposal hash
6. Decision & Position Sizing adapter
7. 고정 포트폴리오 fixture 통합 테스트
8. Order/Execution/Reconciliation 연계 테스트

## 20. 현재 상태

| 영역 | 상태 |
|---|---|
| Architecture | 설계 완료 |
| Database | 설계 완료 |
| Algorithm | 설계 완료 |
| Code | 참조 구조 작성, 실제 구현 미완료 |
| Tests | 계획 완료 |
| Execution | 미확인 |
