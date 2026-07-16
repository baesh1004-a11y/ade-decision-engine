# ADE Pre-Surge Pattern Algorithm v1

## 목적

현재 종목의 최근 120거래일이 과거의 **1주일 급등 직전 120거래일**과 얼마나 유사한지 비교하여 단기 급등 가능 후보를 찾는다.

## 핵심 철학

거래대금 폭발은 매수 시점이 아니라 장기 관찰을 시작하는 기준이다.

1. 과거 거래대금이 120일 평균의 약 10배 이상 발생한 종목을 관찰 대상으로 등록한다.
2. 거래대금 이벤트 이후 최대 500거래일 동안 가격을 추적한다.
3. 직전 종가 대비 향후 5거래일 최고가가 30% 이상 상승한 시점을 찾는다.
4. 급등 시작 직전까지의 120거래일을 하나의 학습 패턴으로 저장한다.
5. 현재 전체 활성 종목의 최근 120거래일과 과거 패턴을 비교한다.
6. 차트 유사도와 STO 3계층 유사도가 각각 85% 이상인 종목만 추천 후보로 남긴다.

## 기존 알고리즘 보존

기존 Replay 추천 엔진은 삭제하지 않는다.

- 기존 구현: `recommendation/event_recommender.py`
- 기존 Replay DB: `replay_events`, `replay_event_flow`, `replay_event_vectors`
- 변경 전 Git 상태 백업 브랜치: `backup/pre-surge-pattern-v1-20260717`

Daily Recommendation의 기본 엔진만 `SurgePatternRecommender`로 전환한다.

## 신규 데이터 구조

### surge_patterns

급등직전 패턴의 메타데이터를 저장한다.

- 원본 거래대금 이벤트
- 거래대금 배수
- 패턴 시작일과 종료일
- 급등 시작일과 최고점일
- 5거래일 최고상승률
- 거래대금 이벤트부터 급등까지의 거래일 수
- 120일 주봉 차트 특징
- STO 단기·중기·장기 구조

### surge_pattern_bars

각 패턴의 120거래일 OHLCV와 시작일 대비 정규화 종가를 저장한다.

## 급등 정의

기본값:

```text
직전 거래일 종가 대비
향후 5거래일 중 최고가가
30% 이상 상승
```

겹치는 급등 구간을 반복 저장하지 않도록 기본 20거래일 cooldown을 적용한다.

## 추천 순서

```text
현재 활성 종목 전체
→ 최근 120거래일 추출
→ 과거 급등직전 패턴과 차트 비교
→ 차트 유사도 85% 이상
→ STO 3계층 유사도 85% 이상
→ Top 매칭 패턴 저장
→ 최종 유사도와 매칭 사례 수로 정렬
```

최종 유사도는 차트와 STO 중 낮은 점수를 사용한다. 한 요소만 높고 다른 요소가 낮은 종목이 추천되는 것을 막기 위한 보수적 기준이다.

## 구축 명령

한국장:

```bash
python run_build_replay_db.py --full
python run_build_surge_patterns.py --market kr --full
```

미국장:

```bash
python run_build_us_market_db.py
python run_build_us_replay_db.py --full
python run_build_surge_patterns.py --market us --full
```

기본 관찰 기준은 거래대금 10배, 관찰기간 500거래일, 급등 기준 5거래일 30%다.

실험 시:

```bash
python run_build_surge_patterns.py --market kr --full --money-ratio 10 --observation-days 500 --surge-return 30
```

## 대시보드

`Surge Pattern Lab`에서 다음을 확인한다.

- 추천종목 선택
- 매칭된 과거 급등직전 패턴 선택
- 현재 120일과 과거 120일 정규화 차트 중첩 비교
- 차트 유사도
- STO 3계층 유사도
- 단기·중기·장기 STO 값 비교
- 원본 거래대금 이벤트와 실제 급등 결과
- 급등직전 패턴 전체 라이브러리
