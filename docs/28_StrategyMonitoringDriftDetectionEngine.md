# Strategy Monitoring & Drift Detection Engine v1

## 1. 목적

Strategy Monitoring & Drift Detection Engine은 PAPER, SHADOW, LIVE_BLOCKED, LIVE 단계에서 운용되는 전략의 성능·위험·데이터·특징량·신호·체결 품질 변화를 지속적으로 측정하고, 기준선 대비 유의미한 열화를 탐지하는 운영 감시 계층이다.

이 엔진은 새로운 매수·매도 판단을 생성하지 않는다. 감시 결과를 Strategy Validation & Promotion Engine, Scheduler, Orchestrator, Audit & Compliance Engine에 전달해 전략 유지·경고·강등·중단 검토를 지원한다.

## 2. 책임 경계

### 담당

- 전략 버전별 운영 기준선 등록
- 실현 성과와 예상 성과 비교
- 수익률·위험·거래 품질·데이터·특징량·신호 분포 변화 탐지
- 시장 국면별 성능 열화 감지
- Champion–Challenger 운영 성과 비교
- 경보 생성, 억제, 집계, 해제
- 자동 보호조치 제안 및 승인 필요 상태 생성
- Strategy Validation 재검증 Trigger 발행
- 감시 증거와 원인 분석용 스냅샷 저장

### 담당하지 않음

- 신규 전략 개발
- 주문 생성 또는 주문 수량 변경
- 브로커 주문 재전송
- 포트폴리오 손익 원장 수정
- 전략의 LIVE 승격 승인
- 원천 데이터 정정

## 3. 아키텍처

```text
Strategy Version / Baseline
          +
Portfolio Accounting & Performance
          +
Signal / Risk / Decision / Order / Execution
          +
Data Snapshot / Feature Snapshot / Market Regime
          ↓
Strategy Monitoring & Drift Detection
   ├─ Metric Collector
   ├─ Baseline Resolver
   ├─ Performance Drift Detector
   ├─ Risk Drift Detector
   ├─ Data & Feature Drift Detector
   ├─ Signal / Decision Drift Detector
   ├─ Execution Quality Detector
   ├─ Regime Attribution Analyzer
   ├─ Alert Correlator
   └─ Protective Action Recommender
          ↓
Audit & Compliance
Strategy Validation & Promotion
Scheduler / Orchestrator
Report Engine
```

## 4. 감시 대상

| 범주 | 대표 지표 |
|---|---|
| 성과 | 일간·누적 수익률, 초과수익률, CAGR, Sharpe, Sortino, Profit Factor |
| 위험 | MDD, 변동성, downside deviation, VaR/Expected Shortfall, 손실 연속일 |
| 거래 | 승률, 평균 손익, 회전율, 보유기간, 슬리피지, 체결률, 거부율 |
| 익스포저 | 종목·섹터·상관군집 집중도, 현금 비중, 총 익스포저 |
| 데이터 | 결측률, 지연, 스키마 변화, 가격 이상치, Snapshot 불일치 |
| 특징량 | 평균·분산·분위수 변화, PSI, KS statistic, Wasserstein distance |
| 신호 | 신호 빈도, 점수 분포, confidence, conflict index, rank turnover |
| 의사결정 | BUY/HOLD/REDUCE/SELL/REJECT 비율, Risk 차단률, NO_ACTION 비율 |
| 실행 | 평균 체결 지연, 부분체결률, VERIFY_REQUIRED 비율, 중복 이벤트 비율 |
| 운영 | run 실패율, stage 지연, 재시도율, 데이터 공급자 오류율 |

## 5. 상태 모델

### Strategy Health

```text
HEALTHY
  ├→ WATCH
  ├→ DEGRADED
  ├→ CRITICAL
  └→ UNKNOWN
```

| 상태 | 의미 |
|---|---|
| HEALTHY | 기준선 안에서 정상 동작 |
| WATCH | 단기 편차가 있으나 보호조치 불필요 |
| DEGRADED | 지속적 성능·위험·품질 열화, 재검증 필요 |
| CRITICAL | 하드 안전 위반 또는 심각한 손실·운영 장애 |
| UNKNOWN | 데이터 부족·지연·무결성 문제로 평가 불가 |

### Alert 상태

```text
OPEN → ACKNOWLEDGED → MITIGATING → RESOLVED
  └──────────────────────────────→ SUPPRESSED
```

동일 원인과 전략 버전의 반복 경보는 deduplication key로 집계한다.

## 6. 입력 모델

```python
@dataclass(frozen=True)
class MonitoringRequest:
    strategy_id: str
    strategy_version: str
    environment: str
    as_of: datetime
    lookback_days: int
    baseline_id: str | None = None
    market_regime_snapshot_id: str | None = None
    requested_by: str = "scheduler"


@dataclass(frozen=True)
class MetricObservation:
    metric_name: str
    value: float
    observed_at: datetime
    window_start: datetime
    window_end: datetime
    dimension: dict[str, str]
    source_ref: str
    quality_status: str = "VALID"
```

## 7. 출력 모델

```python
@dataclass(frozen=True)
class DriftFinding:
    finding_id: str
    strategy_id: str
    strategy_version: str
    detector_type: str
    metric_name: str
    severity: str
    observed_value: float | None
    baseline_value: float | None
    deviation_score: float | None
    reason_code: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class StrategyHealthResult:
    strategy_id: str
    strategy_version: str
    health_status: str
    health_score: float
    findings: tuple[DriftFinding, ...]
    recommended_action: str
    requires_approval: bool
    result_hash: str
```

권고 행동:

- `NO_ACTION`
- `INCREASE_MONITORING`
- `REVALIDATE`
- `BLOCK_NEW_ENTRIES`
- `REDUCE_RISK_BUDGET`
- `DEMOTE_TO_SHADOW`
- `SUSPEND_STRATEGY`
- `MANUAL_REVIEW`

## 8. 기준선 설계

기준선은 전략 버전, 시장, Universe, 비용 가정, 시장 국면, 운영 단계별로 분리한다.

| Baseline 유형 | 설명 |
|---|---|
| VALIDATION | 승격 검증 당시 기대 분포와 성과 범위 |
| ROLLING | 최근 정상 기간의 이동 기준선 |
| CHAMPION | 현재 Champion 전략 운영 결과 |
| REGIME | BULL/BEAR/SIDEWAY/HIGH_VOL 등 국면별 기준 |
| EXECUTION | 브로커·시장별 체결 품질 기준 |

기준선 변경은 새 버전을 생성하며 과거 기준선을 덮어쓰지 않는다.

## 9. 데이터베이스

### `monitoring_baselines`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| baseline_id | TEXT PK | 기준선 ID |
| strategy_id | TEXT | 전략 ID |
| strategy_version | TEXT | 전략 버전 |
| baseline_type | TEXT | VALIDATION/ROLLING/CHAMPION/REGIME/EXECUTION |
| environment | TEXT | PAPER/SHADOW/LIVE_BLOCKED/LIVE |
| regime | TEXT | optional market regime |
| metric_definition_json | TEXT | 지표와 임계치 정의 |
| distribution_json | TEXT | 기준 분포 |
| source_manifest_id | TEXT | 검증 증거 Manifest |
| valid_from | TEXT | 유효 시작 |
| valid_to | TEXT | 유효 종료 |
| status | TEXT | ACTIVE/RETIRED |
| baseline_hash | TEXT | 무결성 해시 |

### `monitoring_runs`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| monitoring_run_id | TEXT PK | 감시 실행 ID |
| strategy_id | TEXT | 전략 ID |
| strategy_version | TEXT | 전략 버전 |
| baseline_id | TEXT | 사용 기준선 |
| as_of | TEXT | 평가 시점 |
| window_start | TEXT | 관측 시작 |
| window_end | TEXT | 관측 종료 |
| health_status | TEXT | 결과 상태 |
| health_score | REAL | 0~100 |
| recommended_action | TEXT | 권고 행동 |
| result_hash | TEXT | 결과 해시 |
| created_at | TEXT | 생성 시각 |

### `metric_observations`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| observation_id | TEXT PK | 관측 ID |
| monitoring_run_id | TEXT FK | 감시 실행 |
| metric_name | TEXT | 지표명 |
| metric_value | REAL | 관측값 |
| dimension_json | TEXT | regime/sector/broker 등 차원 |
| quality_status | TEXT | VALID/DEGRADED/MISSING/INVALID |
| source_ref | TEXT | 원천 레코드 |
| observed_at | TEXT | 관측 시각 |

### `drift_findings`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| finding_id | TEXT PK | 탐지 ID |
| monitoring_run_id | TEXT FK | 감시 실행 |
| detector_type | TEXT | PERFORMANCE/RISK/DATA/FEATURE/SIGNAL/EXECUTION |
| metric_name | TEXT | 대상 지표 |
| severity | TEXT | INFO/WARNING/CRITICAL |
| observed_value | REAL | 관측값 |
| baseline_value | REAL | 기준값 |
| deviation_score | REAL | 표준화 편차 |
| reason_code | TEXT | 표준 사유 |
| evidence_json | TEXT | 증거 참조 |
| created_at | TEXT | 생성 시각 |

### `monitoring_alerts`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| alert_id | TEXT PK | 경보 ID |
| strategy_id | TEXT | 전략 ID |
| strategy_version | TEXT | 전략 버전 |
| deduplication_key | TEXT UNIQUE | 중복 집계 키 |
| severity | TEXT | INFO/WARNING/CRITICAL |
| status | TEXT | OPEN/ACKNOWLEDGED/MITIGATING/RESOLVED/SUPPRESSED |
| first_seen_at | TEXT | 최초 탐지 |
| last_seen_at | TEXT | 최근 탐지 |
| occurrence_count | INTEGER | 반복 횟수 |
| owner | TEXT | 담당자/시스템 |
| resolution_note | TEXT | 조치 결과 |

### `protective_action_requests`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| action_request_id | TEXT PK | 요청 ID |
| alert_id | TEXT FK | 원천 경보 |
| action_type | TEXT | BLOCK_NEW_ENTRIES/REDUCE_RISK_BUDGET/etc |
| requested_scope_json | TEXT | 전략·계좌·시장 범위 |
| requires_approval | INTEGER | 승인 필요 여부 |
| status | TEXT | REQUESTED/APPROVED/REJECTED/APPLIED/EXPIRED |
| expires_at | TEXT | 만료 시각 |
| created_at | TEXT | 생성 시각 |

## 10. 핵심 탐지 알고리즘

### 10.1 성과 열화

```python
excess_return_gap = observed_excess_return - baseline_excess_return
sharpe_ratio_gap = observed_sharpe - baseline_sharpe
profit_factor_ratio = observed_profit_factor / max(baseline_profit_factor, 1e-9)
```

예시 규칙:

- 20거래일 초과수익이 기준선보다 2표준편차 이상 낮으면 `WATCH`
- 60거래일 Sharpe가 기준선의 50% 미만이면 `DEGRADED`
- MDD가 승인 한도의 90% 이상이면 `CRITICAL`
- 연속 손실일이 기준선 99분위수를 초과하면 `DEGRADED`

### 10.2 분포 변화

Population Stability Index:

```python
psi = sum((actual_pct - expected_pct) * log(actual_pct / expected_pct))
```

기본 해석:

| PSI | 상태 |
|---:|---|
| < 0.10 | 안정 |
| 0.10~0.25 | WATCH |
| > 0.25 | DEGRADED |

PSI는 단독 강등 근거가 아니라 데이터 품질, 표본 수, 시장 국면과 함께 평가한다.

### 10.3 신호·의사결정 변화

```python
buy_rate = buy_decisions / evaluated_symbols
risk_block_rate = rejected_by_risk / candidate_count
rank_turnover = changed_top_n / top_n
no_action_rate = no_action_days / observed_days
```

- BUY 빈도 급증과 변동성 급증이 동시에 발생하면 과잉 진입 경보
- Risk 차단률 급증은 Signal–Risk 계약 불일치 또는 시장 위험 변화로 분류
- NO_ACTION 비율 급증은 데이터 결함, 신호 붕괴, 정책 과잉 제한을 구분해 진단

### 10.4 체결 품질 변화

```python
slippage_bps = side_sign * (fill_price - reference_price) / reference_price * 10_000
fill_rate = filled_quantity / requested_quantity
verify_required_rate = verify_required_orders / submitted_orders
```

- 슬리피지와 체결 지연이 동시에 악화하면 route 또는 유동성 문제
- VERIFY_REQUIRED 비율 급증 시 신규 LIVE 주문 차단 검토
- 브로커 오류와 내부 run 실패가 동시 발생하면 운영 장애로 분류

### 10.5 건강 점수

```python
health_score = 100 - (
    performance_penalty * 0.30
    + risk_penalty * 0.25
    + data_feature_penalty * 0.15
    + signal_decision_penalty * 0.10
    + execution_penalty * 0.15
    + operational_penalty * 0.05
)
```

하드 안전 위반은 종합 점수와 무관하게 `CRITICAL`로 승격한다.

## 11. 상태 판정 우선순위

```text
1. 감사·안전 하드 위반
2. 데이터 무결성 평가 불가
3. 손실·낙폭 한도 위반
4. 실행 품질 심각 악화
5. 지속 성능 열화
6. 특징량·신호 분포 변화
7. 단기 통계 편차
```

```python
if hard_safety_violation:
    health = "CRITICAL"
elif required_data_missing:
    health = "UNKNOWN"
elif critical_risk_or_execution:
    health = "CRITICAL"
elif persistent_degradation:
    health = "DEGRADED"
elif temporary_deviation:
    health = "WATCH"
else:
    health = "HEALTHY"
```

## 12. 보호조치 정책

| 조건 | 권고 조치 | 자동 적용 |
|---|---|---|
| 단기 성과 편차 | INCREASE_MONITORING | 가능 |
| PSI > 0.25 지속 | REVALIDATE | Trigger만 자동 |
| MDD 한도 90% 도달 | BLOCK_NEW_ENTRIES | 정책에 따라 가능 |
| VERIFY_REQUIRED 급증 | BLOCK_NEW_ENTRIES | 가능 |
| 하드 감사 위반 | SUSPEND_STRATEGY | 즉시 차단 가능 |
| 장기 성능 열화 | DEMOTE_TO_SHADOW | 승인 필요 |
| 데이터 무결성 평가 불가 | MANUAL_REVIEW | 자동 격리 |

자동 보호조치는 신규 진입 차단이나 실행 격리에 한정한다. 기존 포지션 강제청산은 Portfolio Rebalancing & Exit Orchestration Engine의 검증을 거쳐야 한다.

## 13. 코드 구조

```text
strategy_monitoring/
├── __init__.py
├── models.py
├── baselines.py
├── collectors.py
├── performance.py
├── risk.py
├── distribution.py
├── signal_drift.py
├── execution.py
├── attribution.py
├── health.py
├── alerts.py
├── actions.py
└── repository.py

tests/
├── test_monitoring_models.py
├── test_performance_drift.py
├── test_distribution_drift.py
├── test_signal_drift.py
├── test_execution_drift.py
├── test_health_resolution.py
├── test_alert_deduplication.py
└── test_monitoring_integration.py
```

## 14. 참조 코드

```python
class StrategyMonitoringEngine:
    def __init__(self, repository, collectors, detectors, health_resolver, action_policy):
        self.repository = repository
        self.collectors = collectors
        self.detectors = detectors
        self.health_resolver = health_resolver
        self.action_policy = action_policy

    def evaluate(self, request: MonitoringRequest) -> StrategyHealthResult:
        baseline = self.repository.resolve_baseline(request)
        observations = self.collectors.collect(request)

        findings = []
        for detector in self.detectors:
            findings.extend(detector.detect(observations, baseline, request))

        health_status, health_score = self.health_resolver.resolve(
            observations=observations,
            findings=findings,
        )
        action = self.action_policy.recommend(health_status, findings)
        result = build_health_result(request, health_status, health_score, findings, action)
        self.repository.save_result(result, observations)
        return result
```

## 15. 통합 방식

### Strategy Validation & Promotion

- `DEGRADED` 지속 시 재검증 계획 생성
- `CRITICAL` 시 전략 단계 강등 또는 중단 요청
- Champion–Challenger 운영 성과를 동일 기간·비용으로 비교

### Scheduler & Orchestrator

- HEALTHY: 기존 스케줄 유지
- WATCH: 감시 주기 확대
- DEGRADED: 신규 진입 제한 Run Policy 적용
- CRITICAL: 전략 신규 실행 차단
- UNKNOWN: 데이터 복구 전 신규 판단 차단

### Audit & Compliance

다음 이벤트를 append-only로 기록한다.

- `MONITORING_RUN_STARTED`
- `DRIFT_FINDING_CREATED`
- `STRATEGY_HEALTH_CHANGED`
- `PROTECTIVE_ACTION_REQUESTED`
- `PROTECTIVE_ACTION_APPLIED`
- `MONITORING_ALERT_RESOLVED`

## 16. 표준 Reason Code

- `PERFORMANCE_EXCESS_RETURN_DEGRADED`
- `SHARPE_RATIO_DEGRADED`
- `MAX_DRAWDOWN_NEAR_LIMIT`
- `LOSS_STREAK_ABNORMAL`
- `FEATURE_PSI_HIGH`
- `FEATURE_DISTRIBUTION_SHIFT`
- `SIGNAL_FREQUENCY_SHIFT`
- `RISK_BLOCK_RATE_SPIKE`
- `NO_ACTION_RATE_SPIKE`
- `SLIPPAGE_DEGRADED`
- `FILL_RATE_DEGRADED`
- `VERIFY_REQUIRED_RATE_SPIKE`
- `DATA_QUALITY_UNAVAILABLE`
- `REGIME_MISMATCH`
- `HARD_SAFETY_VIOLATION`

## 17. 테스트 계획

### 단위 테스트

- HEALTHY 기준선 내 관측값은 경보를 만들지 않는다.
- PSI 경계값 0.10과 0.25를 정확히 분류한다.
- MDD 하드 한도 위반은 건강 점수와 무관하게 CRITICAL이다.
- 데이터 부족 시 UNKNOWN을 반환한다.
- 동일 입력과 기준선은 동일 result hash를 생성한다.
- BUY 빈도·Risk 차단률·NO_ACTION 비율을 정확히 계산한다.
- 슬리피지 방향을 BUY/SELL별로 정확히 계산한다.

### DB 테스트

- 기준선 버전은 불변이며 기존 행을 덮어쓰지 않는다.
- 동일 deduplication key 경보는 occurrence_count만 증가한다.
- 감시 결과와 관측값은 동일 트랜잭션으로 저장한다.
- 보호조치 승인·적용·만료 상태 전이를 검증한다.

### 통합 테스트

- Portfolio Accounting 결과에서 성과 지표를 수집한다.
- Feature Snapshot 변화가 PSI finding으로 연결된다.
- Signal 분포 변화가 Strategy Validation 재검증 Trigger를 만든다.
- VERIFY_REQUIRED 급증이 신규 진입 차단 요청을 만든다.
- CRITICAL 결과가 Scheduler/Orchestrator에서 신규 run을 차단한다.
- 보호조치가 기존 주문을 재전송하거나 원장을 수정하지 않는다.

### 회귀 테스트

- 동일 데이터·정책·코드·기준선은 동일 건강 상태를 반환한다.
- 비용 상승은 실행 품질 악화로 반영되되 데이터 드리프트로 오분류되지 않는다.
- 시장 국면 전환은 regime baseline 적용 후 과도한 오탐을 만들지 않는다.

### 실패 주입 테스트

- Portfolio metric source timeout
- Feature Snapshot 누락
- 기준선 조회 실패
- DB 저장 실패
- 중복 Scheduler Trigger
- 잘못된 전략 버전
- Audit 이벤트 발행 실패

### 통계적 테스트

- 정상 분포에서 목표 false positive rate 이하 유지
- 인위적 평균·분산 변화 탐지율 검증
- 작은 표본에서 경보를 보류하거나 LOW_CONFIDENCE로 표시
- 다중 지표 검사 시 FDR 제어 검증

### 성능 테스트

- 전략 100개, 지표 200개 기준 일일 감시 완료 시간 측정
- 5년 관측치의 rolling baseline 재계산 성능
- 경보 폭주 시 deduplication과 저장 처리량 검증

## 18. 완료 기준

- 전략 버전별 불변 기준선을 등록·조회할 수 있다.
- 성과·위험·데이터·특징량·신호·체결·운영 드리프트를 탐지한다.
- HEALTHY/WATCH/DEGRADED/CRITICAL/UNKNOWN 상태를 결정론적으로 반환한다.
- 경보 중복 집계와 해제 이력을 감사 가능하게 저장한다.
- CRITICAL 하드 위반은 신규 전략 실행을 차단할 수 있다.
- 강등·중단은 명시적 정책과 승인 경계를 준수한다.
- 동일 입력·기준선·정책은 동일 result hash를 생성한다.

## 19. 구현 우선순위

1. `models.py`의 Baseline, Observation, Finding, HealthResult 구현
2. 수익률·MDD·Sharpe·슬리피지 수집기 구현
3. PSI와 단순 z-score detector 구현
4. 건강 상태 우선순위 resolver 구현
5. SQLite baseline/run/finding/alert repository 구현
6. 고정 PAPER fixture 기반 HEALTHY/DEGRADED/CRITICAL 테스트
7. Scheduler와 Strategy Validation Trigger 연결
8. 보호조치 승인 워크플로 통합

## 20. 현재 상태

| 영역 | 상태 |
|---|---|
| Architecture | 설계 완료 |
| Database | 설계 완료 |
| Algorithm | 설계 완료 |
| Code | 미구현 |
| Tests | 계획 완료 |
| Execution | 미확인 |
