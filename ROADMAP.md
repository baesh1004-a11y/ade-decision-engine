# ADE Master Roadmap

이 문서는 AI Decision Engine(ADE)의 설계/구현 진행 상황을 추적하는 기준 문서입니다.

## 현재 기준

- 저장소: `baesh1004-a11y/ade-decision-engine`
- 기준 버전: `ADE Design v0.1`
- 목표: 데이터 수집부터 신호, 리스크, 최종 의사결정, 주문, 체결 추적, 백테스트, 리포트까지 연결되는 투자 의사결정 엔진 설계

## 진행 현황

| No | 영역 | 상태 | 비고 |
|---:|---|:---:|---|
| 1 | System Architecture | 완료 | 전체 데이터/판단/주문 흐름 정의 |
| 2 | DataHub Engine | 완료 | CSV/Yahoo/KIS 수집 및 정규화 계층 |
| 3 | Data Quality Engine | 완료 | OHLCV 품질 검증 계층 |
| 4 | KIS Integration Layer | 설계 완료 | 실제 API 연결은 별도 검증 필요 |
| 5 | Portfolio State Engine | 설계 완료 | 현금, 포지션, 평가금액, 미체결 표준화 |
| 6 | Signal Engine | 설계 완료 | 추세/모멘텀/거래량/변동성 점수화 |
| 7 | Risk Engine | 설계 완료 | 매수 가능 여부, 한도, 위험 점수 산출 |
| 8 | Decision Engine Core | 설계 완료 | BUY/HOLD/REDUCE/SELL/REJECT/NO_ACTION 결정 |
| 9 | Order Engine | 예정 | 주문 생성/검증/전송 |
| 10 | Execution Monitor | 예정 | 체결/미체결/실패 추적 |
| 11 | Backtest Engine | 예정 | 과거 데이터 기반 전략 검증 |
| 12 | Report Engine | 예정 | 일별 판단/성과/리스크 리포트 |

## 설계 진행률

```text
[███████░░░] 약 70%
```

## 다음 작업

1. Order Engine v1 설계
2. Execution Monitor v1 설계
3. Backtest Engine v1 설계
4. Report Engine v1 설계
5. 설계 문서와 실제 코드 구조 정합성 점검

## 운영 원칙

- 설계 완료와 구현 완료를 명확히 구분한다.
- GitHub 커밋 SHA 확인 전에는 반영 완료로 간주하지 않는다.
- 실계좌 주문 기능은 명시적 검증 전까지 차단한다.
- 모든 엔진은 입력/출력, 책임 경계, DB, 알고리즘, 테스트 계획을 가진다.
