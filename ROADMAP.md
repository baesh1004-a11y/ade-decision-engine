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
| 9 | Order Engine | 완료 | 미구현 | 계획 완료 | 미확인 | 주문 생성, 검증, 전송 준비. 운영 모드는 별도 승인 전 제한 |
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

## 설계 진행률

```text
[██████████] 현재 계획된 핵심 판단·운영·감사 계층 설계 완료
```

## 현재 우선순위

1. Run State Store migration과 Repository 최소 구현
2. `RunRequest`, `RunResult`, `StageResult` 모델 구현
3. 기존 `main.py`/`ADEPipeline` adapter 작성
4. 고정 CSV fixture 기반 스모크 테스트
5. Candidate → Signal → Portfolio Risk → Decision 계약 정합성 검증
6. Decision & Position Sizing 최소 코드 구현
7. Order Validation & Routing Engine v2 상세 설계

## 다음 작업

1. `db/migrations/001_create_run_state.sql` 구현
2. `core/run_models.py`, `core/run_repository.py`, `core/run_state_store.py` 구현
3. run/stage 상태 전이 단위 테스트 작성
4. 기존 파이프라인을 Orchestrator stage로 래핑
5. DataHub → Feature → Signal → Risk → Decision fixture 통합 테스트
6. `decision/models.py`, `decision/sizing.py`, `decision/engine.py` 최소 구현
7. 기존 Candidate/Risk/Position/Entry/Exit adapter 작성
8. Report Engine용 최소 JSON fixture 생성

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
