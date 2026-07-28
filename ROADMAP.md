# ADE Master Roadmap

이 문서는 AI Decision Engine(ADE)의 설계, 구현, 테스트 진행 상황을 추적하는 기준 문서입니다.

## 현재 기준

- 저장소: `baesh1004-a11y/ade-decision-engine`
- 기준 버전: `ADE Design v0.1`
- 목표: 데이터 수집부터 신호, 리스크, 최종 의사결정, 주문, 체결 추적, 백테스트, 리포트까지 연결되는 투자 의사결정 엔진

## 상태 정의

| 상태 | 의미 |
|---|---|
| 설계 완료 | 아키텍처, 입력/출력, DB, 알고리즘, 테스트 계획 문서화 |
| 구현 존재 | 저장소에 실행 코드가 존재 |
| 테스트 존재 | 단위 또는 통합 테스트가 존재 |
| 실행 확인 | 실제 파이프라인 실행 결과가 확인됨 |

## 진행 현황

| No | 영역 | 설계 | 구현 | 테스트 | 실행 확인 | 비고 |
|---:|---|:---:|:---:|:---:|:---:|---|
| 1 | System Architecture | 완료 | 일부 | 일부 | 미확인 | 기존 통합 파이프라인 존재 |
| 2 | DataHub Engine | 완료 | 일부 | 일부 | 미확인 | CSV/Yahoo/KIS 수집 및 정규화 계층 |
| 3 | Data Quality Engine | 완료 | 일부 | 일부 | 미확인 | OHLCV 품질 검증 계층 |
| 4 | KIS Integration Layer | 완료 | 골격 | 미확인 | 미확인 | 실제 토큰/REST 호출 검증 필요 |
| 5 | Portfolio State Engine | 완료 | 미확인 | 미확인 | 미확인 | 현금, 포지션, 평가금액, 미체결 표준화 |
| 6 | Signal Engine | 완료 | Candidate 구현 존재 | 기존 테스트 확인 필요 | 미확인 | `strategy/candidate.py`에서 초기 신호 역할 수행 |
| 7 | Risk Engine | 완료 | 기존 구현 존재 | 기존 테스트 존재 | 미확인 | 새 설계와 현 구현 정합성 점검 필요 |
| 8 | Decision Engine Core | 완료 | 미확인 | 미확인 | 미확인 | BUY/HOLD/REDUCE/SELL/REJECT/NO_ACTION 설계 |
| 9 | Order Engine | 완료 | 미구현 | 계획 완료 | 미확인 | 기본 주문 생성, 검증, 전송 모드 설계 |
| 10 | Execution Monitor | 완료 | 미구현 | 계획 완료 | 미확인 | 체결, 미체결, 실패 추적과 포트폴리오/리포트 이벤트 발행 |
| 11 | Backtest Engine | 완료 | 미구현 | 계획 완료 | 미확인 | 과거 데이터 기반 전략 검증과 시뮬레이션 결과 산출 |
| 12 | Report Engine | 완료 | 미구현 | 계획 완료 | 미확인 | 일일 의사결정, 포트폴리오, 체결, 백테스트 리포트 생성 |
| 13 | Integration Orchestrator | 완료 | 기존 통합 흐름 존재 | 계획 완료 | 미확인 | 실행 ID, 단계 상태, 실패 격리, 감사 로그를 관리하는 상위 제어 계층 |
| 14 | Run State Store | 완료 | 미구현 | 계획 완료 | 미확인 | SQLite run/stage/artifact 저장, 상태 전이, 멱등성, 감사 추적 |
| 15 | Configuration & Policy Engine | 완료 | 미구현 | 계획 완료 | 미확인 | 정책 버전, 승인, 실행별 불변 스냅샷 관리 |
| 16 | Data Snapshot & Lineage Engine | 완료 | 미구현 | 계획 완료 | 미확인 | 데이터 무결성, 계보, 재현성 관리 |
| 17 | Audit & Compliance Engine | 완료 | 미구현 | 계획 완료 | 미확인 | 감사 이벤트와 통제 위반 탐지 |
| 18 | Scheduler & Trigger Engine | 완료 | 미구현 | 계획 완료 | 미확인 | 시장 세션과 스케줄 기반 실행 생성 |
| 19 | Portfolio Accounting & Performance Engine | 완료 | 미구현 | 계획 완료 | 미확인 | 현금, 원장, 손익, 수익률, 벤치마크 계산 |
| 20 | Market Regime & Feature Engine | 완료 | 미구현 | 계획 완료 | 미확인 | 특징량 생성과 시장 국면 분류 |
| 21 | Signal Generation & Ranking Engine | 완료 | 미구현 | 계획 완료 | 미확인 | 종목 신호, 신뢰도, 순위, 후보 선정 |
| 22 | Portfolio Risk & Exposure Engine | 완료 | 미구현 | 계획 완료 | 미확인 | 종목·섹터·상관 군집·현금·총 익스포저 한도 평가 |
| 23 | Decision & Position Sizing Engine | 완료 | 미구현 | 계획 완료 | 미확인 | 최종 행동, 목표 금액·수량, 하루 1종목 선정, 보호 규칙 |
| 24 | Order Validation & Routing Engine v2 | 완료 | 미구현 | 계획 완료 | 미확인 | 주문 직전 재검증, 가격 보호, 멱등성, 브로커 라우팅, 불확실 응답 격리 |
| 25 | Execution Reconciliation & Recovery Engine v2 | 완료 | 미구현 | 계획 완료 | 미확인 | VERIFY_REQUIRED, 부분체결, 중복체결, 응답 유실, 원장 불일치 대사·복구 |
| 26 | Portfolio Rebalancing & Exit Orchestration Engine v1 | 완료 | 미구현 | 계획 완료 | 미확인 | 손절·추적손절·이익보호·집중도·현금·낙폭 기반 축소 및 청산 우선순위 |
| 27 | Strategy Validation & Promotion Engine v1 | 완료 | 미구현 | 계획 완료 | 미확인 | 전략 검증, Champion–Challenger 비교, 단계별 승격·강등, 증거 Manifest 관리 |
| 28 | Strategy Monitoring & Drift Detection Engine v1 | 완료 | 미구현 | 계획 완료 | 미확인 | 운영 전략의 성능·위험·데이터·신호·체결 드리프트 탐지와 보호조치 요청 |
| 29 | Model Registry & Inference Governance Engine v1 | 완료 | 미구현 | 계획 완료 | 미확인 | 모델 버전·artifact·승인·배포·추론·Shadow·롤백과 재현성 통제 |

## 설계 진행률

```text
[██████████] 판단·주문·체결복구·리밸런싱·전략검증·모니터링·모델거버넌스·운영·감사 계층 설계 완료
```

## 현재 우선순위

1. Run State Store migration과 Repository 최소 구현
2. `RunRequest`, `RunResult`, `StageResult` 모델 구현
3. 기존 `main.py`/`ADEPipeline` adapter 작성
4. 고정 CSV fixture 기반 스모크 테스트
5. Candidate → Signal → Portfolio Risk → Decision 계약 정합성 검증
6. Decision & Position Sizing 최소 코드 구현
7. 손절·추적손절·이익보호 순수 함수와 Exit Proposal 모델 구현
8. OrderIntent와 순수 검증 함수 최소 구현
9. idempotency reservation과 DRY_RUN 경로 구현
10. broker execution ID 기반 중복 제거와 VERIFY_REQUIRED 단건 대사 구현
11. Strategy Validation 필수검사와 Evidence Manifest 최소 구현
12. Strategy Monitoring 기준선·PSI·건강 상태 resolver 최소 구현
13. Model Registry 모델·artifact checksum·승인 guard 최소 구현
14. 고정 모델 fixture 기반 결정론적 추론과 output guard 테스트

## 다음 작업

1. `db/migrations/001_create_run_state.sql` 구현
2. `core/run_models.py`, `core/run_repository.py`, `core/run_state_store.py` 구현
3. run/stage 상태 전이 단위 테스트 작성
4. 기존 파이프라인을 Orchestrator stage로 래핑
5. DataHub → Feature → Signal → Risk → Decision fixture 통합 테스트
6. `decision/models.py`, `decision/sizing.py`, `decision/engine.py` 최소 구현
7. `portfolio/rebalancing/models.py`, `exit_rules.py`, `constraints.py`, `sizing.py` 최소 구현
8. Rebalancing → Decision → OrderIntent 고정 포트폴리오 fixture 테스트
9. `order/models.py`, `order/contract.py`, `order/pretrade.py`, `order/pricing.py` 최소 구현
10. SQLite idempotency reservation과 `DryRunBrokerAdapter` 구현
11. `execution/reconciliation/` 모델·중복 제거·resolver 최소 구현
12. VERIFY_REQUIRED → broker evidence → 상태 확정 fixture 테스트
13. `strategy_validation/models.py`, `mandatory.py`, `manifest.py` 최소 구현
14. 고정 Backtest 결과로 BACKTEST_APPROVED/REJECTED 판정 테스트
15. `strategy_monitoring/models.py`, `baselines.py`, `distribution.py`, `health.py` 최소 구현
16. 고정 PAPER fixture로 HEALTHY/DEGRADED/CRITICAL 판정 테스트
17. `model_governance/models.py`, `registry.py`, `manifest.py`, `contract.py` 최소 구현
18. 승인된 고정 sklearn fixture의 등록·추론·hash 재현성 테스트
19. Champion–Challenger Shadow 결과 비교와 rollback request fixture 테스트
20. 기존 Candidate/Risk/Position/Entry/Exit adapter 작성
21. Report Engine용 최소 JSON fixture 생성

## 운영 원칙

- 설계 완료와 구현 완료를 명확히 구분한다.
- 테스트 존재와 실제 실행 확인을 별도로 관리한다.
- GitHub 커밋 SHA 확인 전에는 반영 완료로 간주하지 않는다.
- 외부 주문 연동은 별도 검증 전까지 제한 모드로 유지한다.
- 모든 엔진은 입력/출력, 책임 경계, DB, 알고리즘, 테스트 계획을 가진다.
- 기존 동작 코드를 먼저 검증한 뒤 구조 변경을 수행한다.
- Orchestrator는 투자 판단을 생성하거나 엔진 결과를 임의로 변경하지 않는다.
- Run State Store는 상태를 기록하되 최종 투자 판단이나 재시도 정책을 결정하지 않는다.
- 완료 상태의 run은 되살리지 않으며 재실행 시 새 run ID를 생성한다.
- stage 상태 변경과 산출물 저장은 가능한 한 동일 트랜잭션으로 처리한다.
- Portfolio Risk Engine의 하드 차단은 Decision Engine이 무시할 수 없다.
- 승인 후 예상 포트폴리오는 모든 현금·집중도·익스포저 한도를 준수해야 한다.
- Decision Engine의 매수 금액과 수량은 Risk 승인값을 초과할 수 없다.
- 신규 진입은 하루 최대 1종목이며 매도·축소는 이 한도에 포함하지 않는다.
- 만료되거나 서로 다른 run의 Signal/Risk Snapshot은 결합하지 않는다.
- Order Engine은 Decision/Risk 승인 수량과 금액을 확대할 수 없다.
- 동일 주문 의도는 멱등성 키 기준으로 최대 한 번만 브로커에 전송한다.
- 불확실 브로커 응답은 `VERIFY_REQUIRED`로 격리하며 자동 재주문하지 않는다.
- `LIVE_BLOCKED`에서는 실계좌 브로커 submit 호출이 발생해서는 안 된다.
- 동일 broker execution ID는 포트폴리오와 회계 원장에 한 번만 반영한다.
- 대사 복구는 원본 이벤트를 수정하지 않고 append-only recovery event로 기록한다.
- 내부 체결 수량이 브로커 체결 수량보다 큰 경우 자동 복구하지 않고 수동 검토한다.
- 미해결 주문이 존재하는 동안 예약금·예약수량을 임의 해제하지 않는다.
- 손절·강제축소·강제청산은 신규 매수보다 먼저 평가한다.
- Exit Proposal 수량은 보유수량·매도가능수량·미체결 예약수량 한도를 초과할 수 없다.
- 체결 대사가 완료되지 않은 포지션은 자동 리밸런싱하지 않고 수동 검토한다.
- 동일 입력 스냅샷과 정책은 결정론적인 Exit Proposal과 hash를 생성해야 한다.
- 백테스트 성과만으로 PAPER 또는 LIVE 승격을 확정하지 않는다.
- 필수 안전 검증 실패는 높은 수익률이나 종합 점수로 상쇄할 수 없다.
- 전략 승격 검증은 데이터·정책·코드·Universe·비용 가정을 불변 Manifest로 기록한다.
- Champion 대비 명확한 개선 증거가 없으면 기존 전략을 유지한다.
- LIVE 승격은 명시적 승인 없이는 확정할 수 없다.
- SUSPENDED 전략은 Scheduler와 Orchestrator에서 신규 실행을 차단해야 한다.
- Strategy Monitoring은 투자 판단이나 주문을 직접 수정하지 않고 건강 상태와 보호조치 요청만 생성한다.
- 하드 안전 위반은 종합 건강 점수와 무관하게 `CRITICAL`로 처리한다.
- `CRITICAL` 또는 `UNKNOWN` 전략은 정책에 따라 신규 진입과 신규 run을 차단해야 한다.
- 자동 보호조치는 신규 진입 차단과 실행 격리에 한정하며 강제청산은 Rebalancing Engine을 거쳐야 한다.
- 감시 기준선과 탐지 결과는 불변 버전과 result hash로 재현 가능해야 한다.
- 모델 artifact는 checksum, 전처리기, feature schema, 학습 데이터, 코드, 정책, 검증 증거가 결합된 Manifest 없이 배포할 수 없다.
- 승인되지 않거나 승인이 만료된 모델은 PAPER·SHADOW·LIVE 추론에 사용할 수 없다.
- 모델 출력은 Portfolio Risk hard block과 Decision·Order 계약을 우회할 수 없다.
- 추론 실패나 INVALID 출력은 기본 매수 신호로 대체하지 않고 해당 입력을 차단하거나 DEGRADED 처리한다.
- 모델 롤백은 사전에 승인된 이전 배포 버전으로만 수행하며 모든 변경을 감사 기록으로 남긴다.
