# 03. Data Quality Engine

## Purpose

Data Quality Engine은 DataHub에 저장된 가격 데이터가 분석과 의사결정에 사용할 수 있는 수준인지 검증한다.

## Validation Rules

| Rule | Description |
|---|---|
| REQUIRED_COLUMNS | open, high, low, close, volume 필수 |
| DATE_ORDER | 날짜 오름차순 정렬 필요 |
| DUPLICATE_DATE | 동일 symbol/date 중복 차단 |
| OHLC_CONSISTENCY | high >= open/close/low, low <= open/close/high |
| NON_NEGATIVE_VOLUME | 거래량 음수 차단 |
| MIN_HISTORY | 최소 히스토리 길이 필요 |
| MISSING_VALUE | 결측값 탐지 |

## Output

```python
QualityResult(
    passed=True,
    errors=[],
    warnings=[],
    row_count=252,
)
```

## Failure Handling

- Error가 있으면 Signal Engine 투입을 차단한다.
- Warning은 저장하되, Decision Engine에서 신뢰도 조정에 활용할 수 있다.
- 품질 검증 결과는 실행 로그로 남긴다.

## Architecture

```text
price_bars
  ↓
validate_prices()
  ↓
QualityResult
  ↓
Signal Engine eligibility
```
