# 01. System Architecture

## Purpose

AI Decision Engine(ADE)는 시장 데이터, 계좌 상태, 신호, 리스크, 최종 의사결정을 분리된 엔진으로 구성하여 투자 판단을 구조화하는 시스템이다.

## Core Flow

```text
Market Data
  ↓
DataHub Engine
  ↓
Data Quality Engine
  ↓
Portfolio State Engine
  ↓
Signal Engine
  ↓
Risk Engine
  ↓
Decision Engine Core
  ↓
Order Engine
  ↓
Execution Monitor
  ↓
Report / Backtest
```

## Engine Responsibility

| Engine | Responsibility |
|---|---|
| DataHub | 가격 데이터 수집, 정규화, 저장 |
| Data Quality | OHLCV 오류, 중복, 결측, 데이터 부족 검증 |
| KIS Integration | KIS OpenAPI 연결 어댑터 |
| Portfolio State | 현금, 보유종목, 평가금액, 비중, 미체결 표준화 |
| Signal | 종목별 매수/관망/무시 후보 신호 산출 |
| Risk | 위험 한도, 매수 가능 금액, 차단 사유 판단 |
| Decision | BUY/HOLD/REDUCE/SELL/REJECT/NO_ACTION 최종 결정 |
| Order | 주문 요청 생성 및 사전 검증 |
| Execution | 체결, 부분체결, 미체결, 실패 추적 |
| Backtest | 과거 데이터 기반 성과 검증 |
| Report | 판단 로그, 수익률, 리스크 리포트 생성 |

## Design Principles

- 각 엔진은 하나의 책임만 가진다.
- 모든 판단은 입력과 출력 모델을 가진다.
- 주문 실행은 Decision Engine이 아니라 Order Engine의 책임이다.
- Risk Engine의 하드 차단 조건은 Decision Engine이 무시할 수 없다.
- 모든 판단은 사유를 남겨야 한다.
