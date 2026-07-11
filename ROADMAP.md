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

## 설계 진행률

```text
[██████████] 핵심 엔진 및 통합 제어 설계 완료
```

## 현재 우선순위

1. 기존 기본 파이프라인이 정상 실행되는지 확인
2. Integration Orchestrator 최소 구현으로 기존 파이프라인 래핑
3. 고정 CSV fixture 기반 스모크 테스트 작성
4. Candidate → Signal 전환은 병행 구조로 점진 적용
5. Risk/Decision 설계와 기존 구현의 정합성 검증

## 다음 작업

1. `RunRequest`, `RunResult`, `StageResult` 모델 구현
2. `ade_runs`, `ade_run_stages` SQLite repository 구현
3. `main.py`와 `ADEPipeline`용 adapter 작성
4. DataHub → Signal → Risk → Decision 스모크 테스트
5. Report Engine용 최소 JSON fixture 생성

## 운영 원칙

- 설계 완료와 구현 완료를 명확히 구분한다.
- 테스트 존재와 실제 실행 확인을 별도로 관리한다.
- GitHub 커밋 SHA 확인 전에는 반영 완료로 간주하지 않는다.
- 외부 주문 연동은 별도 검증 전까지 제한 모드로 유지한다.
- 모든 엔진은 입력/출력, 책임 경계, DB, 알고리즘, 테스트 계획을 가진다.
- 기존 동작 코드를 먼저 검증한 뒤 구조 변경을 수행한다.
- Orchestrator는 투자 판단을 생성하거나 엔진 결과를 임의로 변경하지 않는다.
