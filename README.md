# ADE: AI Decision Engine

ADE는 한국/미국 주식 데이터를 기반으로 후보 선정, 포지션 크기, 진입 타이밍, 청산, 포트폴리오, 리스크, 학습 피드백까지 연결하는 Python 기반 AI 투자 의사결정 엔진입니다.

이 프로젝트는 매수·매도 추천을 보장하는 자동매매 시스템이 아니라, 의사결정을 구조화하고 검증하기 위한 투자 분석 엔진입니다.

## 현재 기준

```text
ADE v1.0 Integrated Decision Engine
ADE Design v0.1 Core Architecture Specifications
```

`ADE Design v0.1`은 최근 설계한 DataHub, Data Quality, KIS Integration, Portfolio State, Signal, Risk, Decision Engine Core의 책임 경계와 입력/출력, DB, 알고리즘, 테스트 계획을 문서화한 기준선입니다.

## v1.0 엔진 구성

```text
Market Data
    ↓
Indicator Pipeline
    ↓
Candidate Decision Engine
    ↓
Risk Engine
    ↓
Position Sizing Engine
    ↓
Entry Timing Engine
    ↓
Exit Decision Engine
    ↓
Portfolio Manager Engine
    ↓
Learning Engine
```

## ADE Core Architecture

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
Backtest / Report
```

## 핵심 엔진

| Engine | 역할 |
|---|---|
| DataHub | 가격 데이터 수집, 정규화, 저장 |
| Data Quality | OHLCV 오류, 중복, 결측, 데이터 부족 검증 |
| KIS Integration | KIS OpenAPI 연결 어댑터 |
| Portfolio State | 현금, 보유종목, 평가금액, 비중, 미체결 표준화 |
| Signal | 종목별 매수/관망/무시 후보 신호 산출 |
| Risk | 위험 한도, 허용 금액, 차단 사유 판단 |
| Decision | BUY/HOLD/REDUCE/SELL/REJECT/NO_ACTION 최종 결정 |
| Candidate | 후보 종목 판단 |
| Position Sizing | 매수 비중과 수량 산출 |
| Entry Timing | 진입 시점 판단 |
| Exit Decision | 익절, 손절, 트레일링, 시간청산 판단 |
| Portfolio Manager | 계좌 전체 비중, 섹터, 현금, 리밸런싱 판단 |
| Learning | 룰별 성과 학습 및 보수적 조정 권고 |

## 통합 파이프라인

v1.0부터는 `DecisionContext` 기반 통합 파이프라인을 제공합니다.

```python
from core.context import DecisionContext
from core.pipeline import ADEPipeline

context = DecisionContext(
    market="us",
    ticker="NVDA",
    market_data=df,
    account_balance=100_000_000,
    cash=50_000_000,
    equity_peak=105_000_000,
    market_regime="SIDEWAY",
)

result = ADEPipeline().run(context)
print(result.to_dict())
```

## 실행

```bash
pip install -r requirements.txt
python main.py
python main.py --market us --ticker NVDA
```

보유 포지션 청산 판단까지 포함하려면:

```bash
python main.py --market us --ticker NVDA \
  --entry-price 100 \
  --holding-shares 100 \
  --highest-price 120 \
  --holding-days 20 \
  --stop-loss-price 95
```

## 테스트

```bash
pytest
pytest tests/test_ade_pipeline.py
pytest tests/test_risk_engine.py
pytest tests/test_learning_engine.py
```

## 프로젝트 구조

```text
collector/      한국/미국 데이터 수집
core/           DecisionContext 및 통합 파이프라인
indicators/     기술지표 계산
pattern/        차트 벡터화 및 유사도 계산
strategy/       의사결정 엔진
database/       SQLite 우선 DB 스키마
docs/           엔진별 설계 문서
tests/          단위 및 통합 테스트
```

## 주요 문서

```text
ROADMAP.md
CHANGELOG.md

docs/01_System_Architecture.md
docs/02_DataHub.md
docs/03_DataQuality.md
docs/04_KISIntegration.md
docs/05_PortfolioState.md
docs/06_SignalEngine.md
docs/07_RiskEngine.md
docs/08_DecisionEngine.md

docs/ade_v1_integrated_pipeline.md
docs/candidate_decision_engine_v0_2.md
docs/position_sizing_engine_v1_0.md
docs/entry_timing_engine_v1_0.md
docs/exit_decision_engine_v1_0.md
docs/portfolio_manager_engine_v1_0.md
docs/risk_engine_v1_0.md
docs/learning_engine_v1_0.md
```

## 주의

이 프로젝트는 투자 판단 보조 도구이며, 수익률이나 매수·매도 결과를 보장하지 않습니다. 실제 투자에는 별도의 검증, 리스크 관리, 세무·법률 검토가 필요합니다.
