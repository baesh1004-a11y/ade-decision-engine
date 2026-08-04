# 36. Instrument Master & Security Identity Resolution Engine v1

## 1. 목적

Instrument Master & Security Identity Resolution Engine은 ADE 전 계층이 동일한 종목·증권·경제적 자산을 동일한 식별자로 해석하도록 보장하는 기준 엔진이다.

한국 시장에서는 종목코드가 영구 식별자가 아니다. 종목명 변경, 단축코드 변경, 시장 이전, 합병, 인적분할, 물적분할, 주식교환, 상장폐지, 재상장, 우선주 구분, ETF·ETN·SPAC 구분이 발생할 수 있다. 따라서 `005930` 같은 거래용 코드를 곧바로 내부 영구 ID로 사용하면 다음 오류가 발생할 수 있다.

- 과거 가격과 현재 종목을 잘못 연결
- 종목코드 변경 후 보유 포지션 소실
- 합병 전후 수익률을 단순 연속계열로 오인
- 동일 종목을 공급원별로 중복 등록
- 보통주·우선주·ETF를 동일 기업으로 잘못 결합
- 상장폐지 종목을 신규 매수 Universe에 잔존
- 미래에 알려진 종목 관계를 과거 백테스트에 사용

이 엔진의 목적은 다음 네 가지다.

1. 거래 가능한 증권에 불변 내부 식별자를 부여한다.
2. 발행사, 증권, 거래소 상장, 거래코드를 분리한다.
3. 시간에 따라 변하는 코드·이름·상태를 point-in-time으로 관리한다.
4. 합병·분할·코드 변경 관계를 명시적 lineage로 보존한다.

이 엔진은 Signal, Risk, Decision, 주문을 생성하지 않는다.

---

## 2. 책임 범위

### 2.1 수행 책임

- 발행사·증권·상장·거래코드의 기준 레코드 생성
- KRX 단축코드, ISIN, 공급업체 심볼, 브로커 코드 매핑
- 종목명·시장·상장상태·상품유형의 유효기간 관리
- 보통주·우선주·ETF·ETN·REIT·SPAC 등 상품 분류
- 종목코드 변경, 시장 이전, 합병, 분할, 상장폐지 lineage 관리
- point-in-time 조회
- 원천 간 식별자 충돌 탐지
- 보유 포지션과 과거 데이터의 안정적 재연결
- canonical identity snapshot과 hash 생성

### 2.2 비책임

- 종목 적격성 결정
- 기업행동 금액·비율 계산
- 가격 조정계수 계산
- 투자 신호 산출
- 매수·매도 판단
- 주문 전송
- 포트폴리오 회계

Universe Selection Engine은 이 엔진의 canonical instrument를 받아 적격성을 판정한다.
Corporate Actions Engine은 이 엔진의 lineage와 corporate-action 관계를 이용하지만 경제적 조건 계산은 독립적으로 수행한다.

---

## 3. 핵심 개념 모델

ADE 내부에서는 다음 객체를 분리한다.

```text
Issuer
  └─ 경제적 발행 주체

Security
  └─ 발행사가 발행한 권리 단위
     예: 삼성전자 보통주, 삼성전자 우선주

Listing
  └─ 특정 시장에 상장된 거래 가능 단위
     예: KOSPI 상장 삼성전자 보통주

Trading Identifier
  └─ 특정 기간 동안 사용되는 거래 코드
     예: KRX short code, ISIN, broker symbol
```

### 3.1 영구 내부 ID

```text
issuer_id     = UUID
security_id   = UUID
listing_id    = UUID
identifier_id = UUID
```

내부 영구 ID는 외부 코드 변경과 무관하게 유지한다.

### 3.2 시간 가변 속성

다음 필드는 덮어쓰지 않고 유효기간 레코드로 저장한다.

- 종목명
- 영문명
- 단축코드
- ISIN
- 시장 구분
- 상장 상태
- 상품 유형
- 거래 통화
- 거래 단위
- 액면가
- 거래정지 상태

모든 point-in-time 속성은 최소 다음 필드를 가진다.

```text
valid_from
valid_to
known_at
recorded_at
source_id
revision
```

`valid_from`은 시장에서 효력이 발생한 시점이고, `known_at`은 ADE가 해당 정보를 알 수 있었던 시점이다.

---

## 4. 아키텍처

```text
KRX 종목 마스터 / 상장 정보
DART 발행사·공시 정보
브로커 종목 코드
시장데이터 공급업체 심볼
기업행동 이벤트
        ↓
Raw Identity Ingestion
   ├─ 원천 payload 보존
   ├─ 수신 시각 기록
   └─ 원본 checksum 생성
        ↓
Normalization
   ├─ 코드 형식 정규화
   ├─ 이름·시장·상품유형 정규화
   ├─ 날짜·시간 표준화
   └─ source-specific schema 변환
        ↓
Entity Resolution
   ├─ exact identifier match
   ├─ temporal validity match
   ├─ issuer/security/listing 분리
   ├─ ambiguity detection
   └─ manual review isolation
        ↓
Lineage Resolver
   ├─ code change
   ├─ market transfer
   ├─ merger
   ├─ spin-off
   ├─ delisting/relisting
   └─ predecessor/successor graph
        ↓
Canonical Instrument Snapshot
   ├─ immutable manifest
   ├─ source evidence
   ├─ mapping confidence
   └─ snapshot hash
        ↓
DataHub / Market Finalization
Universe / Corporate Actions
Feature / Signal / Risk
Paper Trading / Accounting
Explainability / Audit
```

---

## 5. 상태 모델

### 5.1 식별 해석 상태

| 상태 | 의미 | 후속 처리 |
|---|---|---|
| `RESOLVED` | 단일 canonical 객체로 확정 | 정상 사용 |
| `RESOLVED_DEGRADED` | 단일 객체이나 일부 보조 필드 불완전 | 제한적 사용 |
| `AMBIGUOUS` | 둘 이상의 후보가 동일 수준으로 일치 | 자동 결합 금지 |
| `CONFLICTED` | 핵심 식별자 또는 유효기간 충돌 | 차단 |
| `UNRESOLVED` | canonical 후보 없음 | 격리 |
| `RETIRED` | 과거 식별자, 현재 사용 종료 | 과거 조회만 허용 |

### 5.2 상장 상태

```text
PRE_LISTED
ACTIVE
SUSPENDED
DELISTING_PROCESS
DELISTED
RELISTED
TERMINATED
```

`SUSPENDED`는 listing의 상태이며 security의 존재가 사라지는 것은 아니다.

---

## 6. 식별자 우선순위

초기 우선순위는 다음과 같다.

```text
1. 동일 시장·유효기간의 공식 KRX listing identifier
2. 동일 security에 연결된 ISIN
3. DART issuer identity + security class
4. 브로커 instrument code
5. 허가된 market-data vendor symbol
6. 종목명·시장·날짜 기반 보조 매칭
```

종목명 단독 매칭은 canonical 확정 근거로 사용할 수 없다.

### 6.1 하드 매칭

다음 조건은 높은 신뢰도로 자동 결합할 수 있다.

- 동일 KRX 단축코드 + 유효기간 비중첩
- 동일 ISIN + 동일 security class
- 공식 코드변경 이벤트의 predecessor/successor
- 공식 합병·분할 이벤트의 명시적 승계 관계

### 6.2 소프트 매칭

다음 조건은 후보 점수 계산에는 사용할 수 있지만 단독 확정은 금지한다.

- 정규화 종목명
- 발행사명
- 동일 시장
- 유사 상장일
- 동일 업종
- 동일 액면가

---

## 7. 해석 알고리즘

### 7.1 기본 resolver

```python
from dataclasses import dataclass
from enum import Enum
from typing import Sequence

class ResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    RESOLVED_DEGRADED = "RESOLVED_DEGRADED"
    AMBIGUOUS = "AMBIGUOUS"
    CONFLICTED = "CONFLICTED"
    UNRESOLVED = "UNRESOLVED"

@dataclass(frozen=True)
class IdentityObservation:
    source: str
    market: str
    symbol: str | None
    isin: str | None
    issuer_name: str | None
    security_class: str | None
    effective_at: str
    known_at: str

@dataclass(frozen=True)
class ResolutionResult:
    status: ResolutionStatus
    issuer_id: str | None
    security_id: str | None
    listing_id: str | None
    confidence: float
    reason_codes: tuple[str, ...]


def resolve_identity(
    observation: IdentityObservation,
    candidates: Sequence[object],
) -> ResolutionResult:
    hard_matches = exact_temporal_matches(observation, candidates)

    if has_core_conflict(hard_matches):
        return ResolutionResult(
            status=ResolutionStatus.CONFLICTED,
            issuer_id=None,
            security_id=None,
            listing_id=None,
            confidence=0.0,
            reason_codes=("CORE_IDENTIFIER_CONFLICT",),
        )

    if len(hard_matches) == 1:
        match = hard_matches[0]
        return resolved_result(match, confidence=1.0)

    scored = score_soft_candidates(observation, candidates)
    top = select_unambiguous_top(scored)

    if top is None and scored:
        return ambiguous_result(scored)

    if top is None:
        return unresolved_result()

    if top.score < 0.90:
        return degraded_result(top)

    return resolved_result(top, confidence=top.score)
```

### 7.2 point-in-time 조회

특정 평가시각 `T`에서 사용 가능한 identity는 다음 조건을 모두 만족해야 한다.

```text
valid_from <= T < valid_to
known_at <= T
revision is latest known revision at T
status != superseded
```

```python
def as_of(records, evaluation_time):
    eligible = [
        row for row in records
        if row.valid_from <= evaluation_time
        and (row.valid_to is None or evaluation_time < row.valid_to)
        and row.known_at <= evaluation_time
    ]
    return latest_known_revision(eligible, evaluation_time)
```

미래에 발표된 코드변경·합병 관계를 과거 실행에 사용해서는 안 된다.

### 7.3 코드 변경

```text
Listing L1
 ├─ identifier A: 2020-01-01 ~ 2026-08-09
 └─ identifier B: 2026-08-10 ~ open
```

코드 변경 시 `listing_id`는 유지하고 identifier 레코드만 교체한다.

### 7.4 시장 이전

KOSDAQ에서 KOSPI로 이전하는 경우 거래소 listing의 법적·운영적 성격에 따라 새 `listing_id`를 생성할 수 있다. 이때 동일 `security_id` 아래에 predecessor/successor 관계를 기록한다.

```text
security_id = 동일
old_listing_id → successor → new_listing_id
```

### 7.5 합병

합병은 코드 변경으로 처리하지 않는다.

```text
predecessor security A
predecessor security B
        ↓ MERGER
successor security C
```

A와 B의 과거 가격·포지션을 C에 단순 이어붙이지 않는다. Corporate Actions Engine과 Portfolio Accounting Engine이 교환비율과 원가배분을 별도로 적용한다.

### 7.6 인적분할

```text
predecessor security A
        ↓ SPIN_OFF
successor security B
successor security C
```

하나의 과거 security가 복수 successor로 갈 수 있으므로 lineage는 1:1이 아니라 방향성 그래프로 관리한다.

---

## 8. 데이터베이스

### 8.1 `issuers`

```sql
CREATE TABLE issuers (
    issuer_id TEXT PRIMARY KEY,
    legal_name TEXT NOT NULL,
    country_code TEXT NOT NULL,
    corporate_registration_no TEXT,
    dart_corp_code TEXT,
    created_at TEXT NOT NULL,
    retired_at TEXT
);

CREATE UNIQUE INDEX ux_issuers_dart_code
ON issuers(dart_corp_code)
WHERE dart_corp_code IS NOT NULL;
```

### 8.2 `securities`

```sql
CREATE TABLE securities (
    security_id TEXT PRIMARY KEY,
    issuer_id TEXT NOT NULL,
    security_type TEXT NOT NULL,
    security_class TEXT NOT NULL,
    currency TEXT NOT NULL,
    issue_date TEXT,
    termination_date TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (issuer_id) REFERENCES issuers(issuer_id)
);
```

### 8.3 `listings`

```sql
CREATE TABLE listings (
    listing_id TEXT PRIMARY KEY,
    security_id TEXT NOT NULL,
    exchange_code TEXT NOT NULL,
    market_code TEXT NOT NULL,
    listed_at TEXT,
    delisted_at TEXT,
    status TEXT NOT NULL,
    trading_currency TEXT NOT NULL,
    lot_size INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (security_id) REFERENCES securities(security_id)
);
```

### 8.4 `instrument_identifiers`

```sql
CREATE TABLE instrument_identifiers (
    identifier_id TEXT PRIMARY KEY,
    listing_id TEXT NOT NULL,
    identifier_type TEXT NOT NULL,
    identifier_value TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    known_at TEXT NOT NULL,
    source_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    supersedes_identifier_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (listing_id) REFERENCES listings(listing_id)
);

CREATE UNIQUE INDEX ux_identifier_value_period
ON instrument_identifiers(
    identifier_type,
    identifier_value,
    valid_from,
    revision
);
```

### 8.5 `instrument_names`

```sql
CREATE TABLE instrument_names (
    name_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    language_code TEXT NOT NULL,
    name_type TEXT NOT NULL,
    name_value TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    known_at TEXT NOT NULL,
    source_id TEXT NOT NULL,
    revision INTEGER NOT NULL
);
```

### 8.6 `listing_status_history`

```sql
CREATE TABLE listing_status_history (
    status_event_id TEXT PRIMARY KEY,
    listing_id TEXT NOT NULL,
    status TEXT NOT NULL,
    effective_at TEXT NOT NULL,
    known_at TEXT NOT NULL,
    source_id TEXT NOT NULL,
    reason_code TEXT,
    revision INTEGER NOT NULL,
    FOREIGN KEY (listing_id) REFERENCES listings(listing_id)
);
```

### 8.7 `instrument_lineage_edges`

```sql
CREATE TABLE instrument_lineage_edges (
    edge_id TEXT PRIMARY KEY,
    predecessor_entity_type TEXT NOT NULL,
    predecessor_entity_id TEXT NOT NULL,
    successor_entity_type TEXT NOT NULL,
    successor_entity_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    effective_at TEXT NOT NULL,
    known_at TEXT NOT NULL,
    corporate_action_id TEXT,
    confidence TEXT NOT NULL,
    source_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    supersedes_edge_id TEXT,
    created_at TEXT NOT NULL
);
```

### 8.8 `identity_resolution_runs`

```sql
CREATE TABLE identity_resolution_runs (
    run_id TEXT PRIMARY KEY,
    evaluation_time TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    input_manifest_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    output_snapshot_hash TEXT
);
```

### 8.9 `identity_resolution_results`

```sql
CREATE TABLE identity_resolution_results (
    result_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    source_observation_id TEXT NOT NULL,
    status TEXT NOT NULL,
    issuer_id TEXT,
    security_id TEXT,
    listing_id TEXT,
    confidence TEXT NOT NULL,
    reason_hash TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES identity_resolution_runs(run_id)
);
```

### 8.10 `identity_resolution_reasons`

```sql
CREATE TABLE identity_resolution_reasons (
    reason_id TEXT PRIMARY KEY,
    result_id TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    observed_value TEXT,
    expected_value TEXT,
    evidence_ref TEXT,
    reason_hash TEXT NOT NULL,
    FOREIGN KEY (result_id) REFERENCES identity_resolution_results(result_id)
);
```

---

## 9. 핵심 Reason Code

```text
IDENTITY_EXACT_MATCH
IDENTITY_ISIN_MATCH
IDENTITY_KRX_CODE_MATCH
IDENTITY_TEMPORAL_MATCH
IDENTITY_SOFT_MATCH
IDENTITY_LOW_CONFIDENCE
IDENTITY_NOT_FOUND
IDENTITY_AMBIGUOUS
CORE_IDENTIFIER_CONFLICT
IDENTIFIER_VALIDITY_OVERLAP
MARKET_MISMATCH
SECURITY_CLASS_MISMATCH
ISSUER_MISMATCH
DUPLICATE_ACTIVE_IDENTIFIER
FUTURE_IDENTITY_INFORMATION
CODE_CHANGE_CONFIRMED
MARKET_TRANSFER_CONFIRMED
MERGER_LINEAGE_CONFIRMED
SPIN_OFF_LINEAGE_CONFIRMED
DELISTED_IDENTIFIER_RETIRED
MANUAL_REVIEW_REQUIRED
```

각 사유는 자연어 문장만 저장하지 않고 다음 구조를 가진다.

```text
reason_code
severity
observed_value
expected_value
source_reference
effective_at
known_at
reason_hash
```

---

## 10. Canonical Snapshot

Snapshot은 특정 평가시각에서 후속 엔진이 사용할 수 있는 기준 identity 집합이다.

```json
{
  "evaluation_time": "2026-08-04T09:00:00+09:00",
  "policy_version": "instrument-master-v1",
  "issuers": [],
  "securities": [],
  "listings": [],
  "active_identifiers": [],
  "lineage_edges": [],
  "excluded_conflicts": [],
  "source_manifest_hash": "...",
  "snapshot_hash": "..."
}
```

Canonical JSON은 다음 원칙으로 hash한다.

- key 정렬
- 배열은 canonical ID 순 정렬
- 날짜는 ISO-8601 UTC 또는 명시적 timezone
- Decimal은 문자열
- null과 누락을 구분
- 원천 수신 순서에 영향받지 않음

```python
import hashlib
import json


def canonical_hash(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
```

---

## 11. 엔진 실행 순서

```text
1. 원천별 instrument master 수신
2. 원본 payload와 checksum 저장
3. 필드·코드·날짜 정규화
4. 기존 canonical issuer/security/listing 후보 검색
5. hard identifier + temporal match 실행
6. core conflict 검사
7. soft candidate scoring 실행
8. RESOLVED / AMBIGUOUS / CONFLICTED 결정
9. 코드 변경·시장 이전·합병·분할 lineage 적용
10. point-in-time active identifier 계산
11. 충돌·미해결 항목 격리
12. canonical snapshot 생성
13. snapshot hash 및 evidence manifest 저장
14. DataHub·Universe·Corporate Actions에 발행
```

---

## 12. 정책

초기 정책은 다음과 같다.

| 항목 | 기준 |
|---|---|
| 종목명 단독 자동 결합 | 금지 |
| 동일 active KRX 코드 중복 | 하드 충돌 |
| 동일 ISIN·다른 security class | 하드 충돌 |
| soft match 자동확정 최소 점수 | 0.90 |
| 1·2위 후보 점수 차이 | 최소 0.10 |
| 미래 known_at 정보 | 사용 금지 |
| 상장폐지 identifier | 과거 조회만 허용 |
| 합병·분할 | 단순 코드 변경 처리 금지 |
| 수동 override | 승인자·근거·유효기간 필수 |

정책은 코드 상수가 아니라 버전과 hash를 가진 불변 Snapshot으로 저장한다.

---

## 13. 수동 Override

수동 매핑은 허용하되 다음을 강제한다.

```text
override_id
observation_id
canonical_entity_id
approved_by
approved_at
effective_from
effective_to
justification
evidence_ref
policy_version
override_hash
```

수동 override로 다음 하드 규칙을 해제할 수 없다.

- 서로 다른 security class 강제 결합
- 서로 다른 유효기간의 코드를 동시 active 처리
- 미래 정보를 과거 실행에 사용
- 합병·분할 관계를 단순 동일 identity로 변환

---

## 14. 코드 구조

```text
instrument_master/
├── models.py
├── enums.py
├── contracts.py
├── policies.py
├── adapters/
│   ├── krx.py
│   ├── dart.py
│   ├── broker.py
│   └── vendor.py
├── normalization.py
├── temporal.py
├── candidate_search.py
├── matching.py
├── scoring.py
├── conflicts.py
├── lineage.py
├── point_in_time.py
├── overrides.py
├── reason_codes.py
├── manifest.py
├── hashing.py
├── repository.py
└── engine.py
```

### 14.1 핵심 모델

```python
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class EntityType(str, Enum):
    ISSUER = "ISSUER"
    SECURITY = "SECURITY"
    LISTING = "LISTING"

class IdentifierType(str, Enum):
    KRX_SHORT_CODE = "KRX_SHORT_CODE"
    ISIN = "ISIN"
    BROKER_CODE = "BROKER_CODE"
    VENDOR_SYMBOL = "VENDOR_SYMBOL"

@dataclass(frozen=True)
class InstrumentIdentifier:
    identifier_id: str
    listing_id: str
    identifier_type: IdentifierType
    value: str
    valid_from: datetime
    valid_to: datetime | None
    known_at: datetime
    revision: int
```

### 14.2 엔진 계약

```python
@dataclass(frozen=True)
class IdentityResolutionRequest:
    run_id: str
    evaluation_time: datetime
    policy_version: str
    observation_ids: tuple[str, ...]
    input_manifest_hash: str

@dataclass(frozen=True)
class IdentityResolutionResponse:
    run_id: str
    status: str
    resolved_count: int
    ambiguous_count: int
    conflicted_count: int
    unresolved_count: int
    snapshot_hash: str | None
```

---

## 15. 안전 불변식

```text
동일 listing에는 동일 시점 active KRX short code가 최대 1개다.

동일 identifier_type + identifier_value는
동일 시점에 둘 이상의 active listing으로 자동 연결되지 않는다.

보통주와 우선주는 동일 security_id를 공유하지 않는다.

코드 변경은 listing_id를 변경하지 않는다.

합병·분할은 단순 코드 변경으로 처리하지 않는다.

상장폐지는 issuer/security 삭제를 의미하지 않는다.

known_at > evaluation_time인 정보는 과거 실행에서 사용하지 않는다.

AMBIGUOUS 또는 CONFLICTED 결과는 후속 신규매수 Universe에 전달하지 않는다.

과거 identity revision은 수정·삭제하지 않는다.

동일 입력·정책·평가시각이면 동일 snapshot hash를 생성한다.
```

---

## 16. 테스트 계획

### 16.1 단위 테스트

#### 식별자 정규화

- KRX 단축코드 앞자리 0 보존
- ISIN 대문자 정규화
- 공백·하이픈 제거 정책 검증
- 공급업체 suffix 분리

#### 시간 검증

- `valid_from` 경계 포함
- `valid_to` 경계 제외
- 미래 `known_at` 차단
- revision 선택
- 유효기간 중첩 탐지

#### 해석

- exact KRX code match
- exact ISIN match
- 종목명 단독 match 거부
- 동일 점수 후보 2개 → AMBIGUOUS
- security class 불일치 → CONFLICTED

### 16.2 고정 통합 시나리오

```text
A. 정상 KOSPI 보통주
→ issuer/security/listing 생성
→ KRX code와 ISIN 연결
→ RESOLVED

B. 종목명 변경
→ 동일 issuer/security/listing 유지
→ name history revision 추가

C. 단축코드 변경
→ old identifier RETIRED
→ new identifier ACTIVE
→ listing_id 유지

D. KOSDAQ → KOSPI 이전상장
→ security_id 유지
→ predecessor listing과 successor listing 연결

E. 보통주와 우선주
→ issuer_id 동일
→ security_id 분리
→ listing_id 분리

F. 합병
→ predecessor securities 2개
→ successor security 1개
→ MERGER lineage edge
→ 가격계열 자동 연결 금지

G. 인적분할
→ predecessor 1개
→ successor 2개
→ SPIN_OFF lineage edge 2건

H. 상장폐지
→ listing DELISTED
→ identifier RETIRED
→ issuer/security 보존

I. 공급원 충돌
→ 동일 KRX 코드가 서로 다른 active listing을 지시
→ CONFLICTED
→ snapshot에서 격리

J. 미래 코드변경 정보
→ known_at이 평가시각 이후
→ 과거 snapshot에서 미사용
```

### 16.3 속성 테스트

```text
입력 순서 변경 → snapshot hash 동일

active identifier 기간은 겹치지 않음

동일 listing의 active primary KRX code 수 <= 1

보통주·우선주 security_id는 항상 다름

AMBIGUOUS/CONFLICTED listing의 신규매수 전달 수 = 0

과거 revision 삭제 수 = 0

future known_at 사용 수 = 0

lineage graph의 self-loop 수 = 0
```

### 16.4 장애 테스트

- 원천 하나 미수신
- KRX와 브로커 코드 불일치
- DB 저장 중 장애
- snapshot 생성 후 manifest 저장 실패
- 중복 실행
- 동일 observation 재수신
- 정정 데이터 순서 역전 도착

DB 트랜잭션이 중단되면 final snapshot을 발행하지 않는다.

### 16.5 계약 테스트

- DataHub가 `listing_id` 기준으로 OHLCV를 저장하는지 확인
- Universe가 `security_type`, `listing_status`를 정확히 읽는지 확인
- Corporate Actions가 predecessor/successor lineage를 참조하는지 확인
- Paper Trading이 코드 변경 후에도 기존 포지션을 동일 listing으로 유지하는지 확인
- Report가 현재 코드와 당시 거래 코드를 구분해 표시하는지 확인

---

## 17. 구현 우선순위

```text
1. 불변 Issuer/Security/Listing/Identifier 모델
2. SQLite migration
3. KRX short code·ISIN 정규화
4. temporal validity 조회
5. exact match resolver
6. core conflict detector
7. soft scoring과 ambiguity guard
8. 코드 변경 lineage
9. 시장 이전·합병·분할 lineage
10. canonical snapshot hash
11. DataHub·Universe adapter
12. 고정 fixture 통합 테스트
```

---

## 18. 완료 기준

다음 조건을 만족하면 v1 최소 구현 완료로 본다.

- KRX 고정 종목 마스터 fixture를 canonical model로 적재
- 동일 종목의 이름·코드 변경 이력을 point-in-time 조회
- 보통주·우선주를 별도 security로 유지
- 상장폐지 후에도 과거 OHLCV와 포지션 lineage 보존
- 합병·분할을 predecessor/successor graph로 표현
- AMBIGUOUS·CONFLICTED 항목을 Universe 신규매수에서 차단
- 동일 입력 재실행 시 동일 snapshot hash 생성
- SQLite 저장·재로드 후 동일 결과 재현

---

## 19. 다음 연계 작업

1. `instrument_master/models.py` 구현
2. `db/migrations/036_create_instrument_master.sql` 작성
3. KRX·DART 고정 fixture 작성
4. `point_in_time.py`와 temporal overlap 검사 구현
5. Universe Selection Engine의 종목키를 `listing_id`로 통일
6. Corporate Actions Engine의 lineage 입력 계약 연결
7. Paper Trading 포지션의 외부 종목코드 의존 제거
8. Report Engine에 당시 코드와 현재 코드 동시 표시
