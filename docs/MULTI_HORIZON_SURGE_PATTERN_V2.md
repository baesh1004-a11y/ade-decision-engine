# Multi-Horizon Pre-Surge Pattern V2

## 목적

거래대금 약 10배 이벤트는 관찰 시작점으로만 사용한다. 이후 최대 500거래일을 추적하여 30% 상승을 처음 달성한 속도에 따라 급등 사례를 상호 배타적으로 분류하고, 각 급등 시작 직전 120거래일을 학습 패턴으로 저장한다.

## 급등 유형

| 유형 | 30% 최초 도달 | 속도 가중치 |
|---|---:|---:|
| FAST | 1~5거래일 | 1.00 |
| QUICK | 6~10거래일 | 0.90 |
| SWING | 11~15거래일 | 0.80 |
| POSITION | 16~20거래일 | 0.70 |

분류는 중복되지 않는다. 5일 안에 30%를 달성한 사례는 FAST 하나로만 저장한다.

## 패턴 생성

1. replay_events에서 거래대금 기준 이상 이벤트를 선택한다.
2. 이벤트 이후 최대 500거래일을 관찰한다.
3. 각 후보 시작일의 직전 종가를 기준가격으로 사용한다.
4. 향후 20거래일 고가 중 처음 +30%에 도달한 거래일을 찾는다.
5. 최초 도달일에 따라 FAST/QUICK/SWING/POSITION으로 분류한다.
6. 급등 시작 직전 120거래일 OHLCV, 주봉 형태, STO 3계층 구조를 저장한다.
7. 같은 급등을 반복 저장하지 않도록 20거래일 cooldown을 적용한다.

## 저장 항목

- surge_class
- surge_horizon_days
- target_hit_day
- surge_return_pct
- return_5d / return_10d / return_15d / return_20d
- speed_weight
- 급등직전 120거래일 OHLCV
- WeeklyShape JSON
- STO Structure JSON

기존 surge_patterns 테이블은 삭제하지 않으며 필요한 컬럼을 ALTER TABLE로 추가한다. 전체 재구축 시 V2 pattern_version으로 다시 저장한다.

## 추천 순위

현재 종목의 최근 120거래일과 과거 패턴을 비교한다.

- 차트 유사도 85% 이상
- STO 3계층 유사도 85% 이상
- 원시 유사도 = min(차트 유사도, STO 유사도)
- 속도 가중점수 = 원시 유사도 × speed_weight
- 최종 정렬에는 속도 가중점수와 매칭 사례 수 신뢰도를 반영한다.

따라서 같은 유사도라면 FAST가 QUICK보다, QUICK이 SWING보다 우선한다.

## 실행

```bash
python run_build_surge_patterns.py --market kr --full
python run_build_surge_patterns.py --market us --full
```

소규모 확인:

```bash
python run_build_surge_patterns.py --market kr --full --limit 100
```

전체 재구축 후 Daily Recommendation을 다시 실행해야 V2 추천 결과가 생성된다.
