# 16. Data Snapshot & Lineage Engine v1

## 1. 목적

Data Snapshot & Lineage Engine은 ADE 실행에 사용된 시장 데이터, 계좌 상태, 정책 스냅샷, 중간 산출물의 정확한 버전과 생성 경로를 기록하여 결과의 재현성, 감사 가능성, 오류 추적성을 보장하는 데이터 거버넌스 계층이다.

이 엔진은 시장 데이터를 새로 수집하거나 투자 판단을 생성하지 않는다. DataHub, Data Quality, Portfolio State, Signal, Risk, Decision, Backtest, Report가 사용한 입력과 출력이 어떤 원천에서 어떤 변환을 거쳐 생성되었는지를 표준화하고 고정한다.

주요 목적은 다음과 같다.

- 실행별 불변 데이터 스냅샷 생성
- 원천 데이터와 파생 데이터의 계보 추적
- 입력·출력 스키마 버전 관리
- canonical 직렬화와 무결성 해시 생성
- 백테스트 재현성 보장
- 운영 결과의 감사 및 장애 원인 분석 지원
- 수정·재수집 데이터가 기존 결과에 미친 영향 분석
- 정책 스냅샷과 데이터 스냅샷의 결합 추적

## 2. 문제 정의

ADE의 동일한 전략과 정책을 사용하더라도 입력 데이터가 달라지면 결과는 달라진다.

예:

- 같은 거래일의 수정주가가 재수집으로 변경됨
- 공급자별 거래량 또는 종가가 다름
- 기업행사 반영 시점이 달라짐
- 누락 행을 보간하거나 제거함
- 계좌 잔고가 실행 중 변경됨
- 정책은 같지만 종목 유니버스가 달라짐
- 데이터 품질 규칙 버전이 변경됨

데이터 버전과 변환 이력이 저장되지 않으면 다음 문제가 발생한다.

1. 과거 의사결정을 동일하게 재현할 수 없다.
2. 백테스트 결과가 어떤 데이터 기준인지 설명할 수 없다.
3. 공급자 오류 또는 정정 데이터의 영향 범위를 파악하기 어렵다.
4. Report의 숫자를 원천 레코드까지 추적할 수 없다.
5. 동일 실행에서 일부 엔진이 다른 데이터 버전을 사용할 수 있다.
6. 오류가 데이터, 정책, 알고리즘 중 어디에서 발생했는지 분리하기 어렵다.

Data Snapshot & Lineage Engine은 모든 실행 입력을 명시적 스냅샷으로 고정하고, 각 산출물의 상위 입력을 방향성 그래프로 기록하여 이 문제를 해결한다.

## 3. 책임 경계

### 3.1 담당

- 원천 데이터셋 등록
- 데이터셋 버전 및 스키마 버전 관리
- 실행별 스냅샷 생성과 잠금
- 파일·테이블·레코드 범위의 무결성 해시 생성
- 데이터 변환 단계 및 부모-자식 계보 기록
- Data Quality 결과와 정제 데이터 연결
- 계좌 상태·정책 스냅샷·유니버스 스냅샷 연결
- 실행과 데이터 스냅샷 연결
- 재현성 manifest 생성
- 변경 데이터의 영향 실행 조회
- 보존 기간과 폐기 상태 관리

### 3.2 담당하지 않음

- 외부 API에서 시장 데이터 수집
- 가격·거래량의 업무적 정확성 판단
- 결측치 처리 정책 결정
- 신호 계산
- 리스크 판단
- 매수·매도 결정
- 주문 생성 또는 체결 처리
- API 키, 계좌 비밀번호, 접근 토큰 저장

## 4. ADE 내 위치

```text
External Market / Broker / Reference Sources
                    ↓
                DataHub
                    ↓
        Data Snapshot & Lineage Engine
          ├─ Source Registry
          ├─ Schema Registry
          ├─ Snapshot Builder
          ├─ Hash Calculator
          ├─ Lineage Graph
          ├─ Reproducibility Manifest
          └─ Snapshot Repository
                    ↓
             Immutable Snapshot
                    ↓
              Data Quality Engine
                    ↓
       Cleaned / Validated Data Snapshot
                    ↓
      Signal → Risk → Decision → Order
                    ↓
          Execution / Portfolio / Report

Configuration & Policy Engine
                    ↓
             Policy Snapshot
                    ↓
Integration Orchestrator ── binds ── Data Snapshot
```

Orchestrator는 실행 시작 시 정책 스냅샷과 데이터 스냅샷을 결합한 `RunReproducibilityContext`를 생성한다. 이후 모든 엔진은 이 컨텍스트에 포함된 데이터 참조만 사용한다.

## 5. 핵심 원칙

1. 실행에 바인딩된 데이터 스냅샷은 변경할 수 없다.
2. 원천 데이터 수정은 기존 스냅샷을 덮어쓰지 않고 새 버전을 생성한다.
3. 모든 파생 산출물은 최소 하나 이상의 부모 입력을 가져야 한다.
4. 동일한 정규화 데이터는 동일한 콘텐츠 해시를 생성해야 한다.
5. 해시는 canonical 직렬화 규칙과 함께 버전 관리한다.
6. 실행 결과에는 `snapshot_id`, `policy_snapshot_id`, `config_hash`, `lineage_root_id`가 포함되어야 한다.
7. 백테스트는 데이터 범위와 종목 유니버스를 스냅샷으로 고정한다.
8. 민감한 계좌 식별자는 마스킹하거나 별도 보안 저장소 참조만 기록한다.
9. 데이터 삭제 시에도 계보 메타데이터와 해시는 감사 정책에 따라 보존한다.
10. LIVE/PAPER 실행은 승인되지 않은 또는 품질 실패 스냅샷을 사용할 수 없다.

## 6. 핵심 용어

| 용어 | 의미 |
|---|---|
| Source | 외부 공급자, 브로커, 파일, 내부 테이블 등 데이터 원천 |
| Dataset | 동일한 의미와 스키마를 가진 논리적 데이터 집합 |
| Dataset Version | 수집 또는 정정 시점에 생성된 데이터 버전 |
| Snapshot | 특정 실행에서 사용할 데이터 범위를 불변으로 고정한 객체 |
| Artifact | 원천 또는 변환 과정에서 생성된 물리적·논리적 산출물 |
| Lineage Edge | 부모 산출물과 자식 산출물의 변환 관계 |
| Manifest | 재현에 필요한 정책, 데이터, 코드, 파라미터 참조 묶음 |
| Content Hash | 데이터 내용 기반 SHA-256 해시 |
| Schema Hash | 컬럼·타입·순서·제약조건 기반 해시 |

## 7. 입력 모델

```python
@dataclass(frozen=True)
class SnapshotRequest:
    run_id: str
    purpose: str
    mode: str
    market: str
    symbols: tuple[str, ...]
    start_at: datetime
    end_at: datetime
    dataset_refs: tuple[str, ...]
    policy_snapshot_id: str
    requested_by: str = "system"
    as_of: datetime | None = None
```

`purpose` 값:

- `ANALYSIS`
- `BACKTEST`
- `PAPER_EXECUTION`
- `LIVE_EXECUTION`
- `REPORT_REBUILD`
- `INCIDENT_REPLAY`

추가 입력:

- DataHub 수집 결과
- Data Quality 결과
- Portfolio State snapshot
- 종목 유니버스
- 거래일 캘린더
- 기업행사·분할·배당 기준 정보
- 코드 버전 또는 Git commit SHA
- Configuration & Policy snapshot

## 8. 출력 모델

```python
@dataclass(frozen=True)
class DataSnapshot:
    snapshot_id: str
    run_id: str
    purpose: str
    mode: str
    status: str
    market: str
    symbols: tuple[str, ...]
    range_start: datetime
    range_end: datetime
    as_of: datetime
    root_artifact_id: str
    lineage_root_id: str
    content_hash: str
    schema_hash: str
    row_count: int
    quality_status: str
    policy_snapshot_id: str
    manifest_id: str
    created_at: datetime
```

```python
@dataclass(frozen=True)
class ReproducibilityManifest:
    manifest_id: str
    run_id: str
    snapshot_id: str
    policy_snapshot_id: str
    config_hash: str
    code_version: str
    data_hash: str
    schema_hash: str
    universe_hash: str
    calendar_version: str
    transformation_versions: dict[str, str]
    created_at: datetime
```

## 9. 상태 모델

### 9.1 Snapshot 상태

```text
REQUESTED
   ↓
BUILDING
   ├─→ VALIDATING
   │       ├─→ READY
   │       ├─→ QUARANTINED
   │       └─→ FAILED
   └─→ FAILED

READY → LOCKED → RETAINED → EXPIRED
                     └────→ ARCHIVED
```

상태 의미:

| 상태 | 의미 |
|---|---|
| REQUESTED | 스냅샷 생성 요청 등록 |
| BUILDING | 데이터 범위·산출물 수집 중 |
| VALIDATING | 해시, 스키마, 품질 결과 검증 중 |
| READY | 실행 바인딩 가능 |
| LOCKED | 실행에 바인딩되어 변경 불가 |
| QUARANTINED | 품질 또는 무결성 문제로 격리 |
| FAILED | 생성 실패 |
| RETAINED | 보존 정책에 따라 유지 |
| ARCHIVED | 저비용 저장소로 이동 |
| EXPIRED | 보존 기간 종료 |

### 9.2 Artifact 상태

```text
REGISTERED → VERIFIED → ACTIVE
                    ├─→ SUPERSEDED
                    ├─→ QUARANTINED
                    └─→ DELETED_METADATA_RETAINED
```

## 10. 데이터베이스 설계

### 10.1 `data_sources`

```sql
CREATE TABLE IF NOT EXISTS data_sources (
    source_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    provider TEXT,
    market TEXT,
    endpoint_ref TEXT,
    timezone TEXT,
    status TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (source_type IN ('API','BROKER','FILE','DATABASE','DERIVED','MANUAL')),
    CHECK (status IN ('ACTIVE','DEGRADED','DISABLED','RETIRED'))
);
```

`endpoint_ref`에는 인증정보를 저장하지 않는다. 논리적 커넥터 이름 또는 비밀관리 시스템의 참조만 저장한다.

### 10.2 `datasets`

```sql
CREATE TABLE IF NOT EXISTS datasets (
    dataset_id TEXT PRIMARY KEY,
    dataset_name TEXT NOT NULL UNIQUE,
    domain TEXT NOT NULL,
    description TEXT,
    owner TEXT,
    retention_days INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (domain IN (
        'OHLCV','QUOTE','FUNDAMENTAL','CORPORATE_ACTION',
        'CALENDAR','UNIVERSE','PORTFOLIO','POLICY','DERIVED'
    )),
    CHECK (retention_days IS NULL OR retention_days >= 0)
);
```

### 10.3 `dataset_versions`

```sql
CREATE TABLE IF NOT EXISTS dataset_versions (
    dataset_version_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    version_no INTEGER NOT NULL,
    schema_version TEXT NOT NULL,
    schema_json TEXT NOT NULL,
    schema_hash TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    range_start TEXT,
    range_end TEXT,
    as_of TEXT NOT NULL,
    storage_uri TEXT NOT NULL,
    status TEXT NOT NULL,
    supersedes_version_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id),
    FOREIGN KEY (source_id) REFERENCES data_sources(source_id),
    FOREIGN KEY (supersedes_version_id) REFERENCES dataset_versions(dataset_version_id),
    UNIQUE (dataset_id, version_no),
    CHECK (row_count >= 0),
    CHECK (status IN ('REGISTERED','VERIFIED','ACTIVE','SUPERSEDED','QUARANTINED'))
);
```

### 10.4 `data_artifacts`

```sql
CREATE TABLE IF NOT EXISTS data_artifacts (
    artifact_id TEXT PRIMARY KEY,
    dataset_version_id TEXT,
    artifact_type TEXT NOT NULL,
    logical_name TEXT NOT NULL,
    storage_uri TEXT,
    media_type TEXT,
    compression TEXT,
    partition_json TEXT NOT NULL DEFAULT '{}',
    content_hash TEXT NOT NULL,
    hash_algorithm TEXT NOT NULL DEFAULT 'SHA256',
    byte_size INTEGER,
    row_count INTEGER,
    min_event_time TEXT,
    max_event_time TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (dataset_version_id) REFERENCES dataset_versions(dataset_version_id),
    CHECK (artifact_type IN (
        'RAW','NORMALIZED','VALIDATED','FEATURE','SIGNAL_INPUT',
        'PORTFOLIO_SNAPSHOT','UNIVERSE','MANIFEST','REPORT_INPUT'
    )),
    CHECK (byte_size IS NULL OR byte_size >= 0),
    CHECK (row_count IS NULL OR row_count >= 0)
);
```

### 10.5 `data_snapshots`

```sql
CREATE TABLE IF NOT EXISTS data_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    mode TEXT NOT NULL,
    market TEXT NOT NULL,
    range_start TEXT NOT NULL,
    range_end TEXT NOT NULL,
    as_of TEXT NOT NULL,
    status TEXT NOT NULL,
    root_artifact_id TEXT NOT NULL,
    lineage_root_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    schema_hash TEXT NOT NULL,
    universe_hash TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    quality_status TEXT NOT NULL,
    policy_snapshot_id TEXT NOT NULL,
    manifest_id TEXT,
    locked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (root_artifact_id) REFERENCES data_artifacts(artifact_id),
    CHECK (status IN (
        'REQUESTED','BUILDING','VALIDATING','READY','LOCKED',
        'QUARANTINED','FAILED','RETAINED','ARCHIVED','EXPIRED'
    )),
    CHECK (quality_status IN ('UNKNOWN','PASSED','WARNING','FAILED')),
    CHECK (row_count >= 0)
);
```

### 10.6 `snapshot_members`

```sql
CREATE TABLE IF NOT EXISTS snapshot_members (
    snapshot_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    member_role TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    required INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, artifact_id, member_role),
    FOREIGN KEY (snapshot_id) REFERENCES data_snapshots(snapshot_id) ON DELETE CASCADE,
    FOREIGN KEY (artifact_id) REFERENCES data_artifacts(artifact_id),
    CHECK (member_role IN (
        'MARKET_DATA','QUALITY_RESULT','PORTFOLIO_STATE','UNIVERSE',
        'CALENDAR','CORPORATE_ACTION','POLICY','REFERENCE'
    )),
    CHECK (required IN (0,1))
);
```

### 10.7 `lineage_nodes`

```sql
CREATE TABLE IF NOT EXISTS lineage_nodes (
    lineage_node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    reference_id TEXT NOT NULL,
    reference_version TEXT,
    content_hash TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    CHECK (node_type IN (
        'SOURCE','DATASET_VERSION','ARTIFACT','SNAPSHOT','POLICY_SNAPSHOT',
        'RUN','STAGE','DECISION','ORDER','EXECUTION','REPORT'
    ))
);
```

### 10.8 `lineage_edges`

```sql
CREATE TABLE IF NOT EXISTS lineage_edges (
    lineage_edge_id TEXT PRIMARY KEY,
    parent_node_id TEXT NOT NULL,
    child_node_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    transformation_name TEXT,
    transformation_version TEXT,
    parameters_hash TEXT,
    stage_name TEXT,
    run_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (parent_node_id) REFERENCES lineage_nodes(lineage_node_id),
    FOREIGN KEY (child_node_id) REFERENCES lineage_nodes(lineage_node_id),
    CHECK (parent_node_id <> child_node_id),
    CHECK (relation_type IN (
        'INGESTED_FROM','NORMALIZED_FROM','VALIDATED_FROM','FILTERED_FROM',
        'AGGREGATED_FROM','FEATURED_FROM','SNAPSHOT_OF','USED_BY',
        'PRODUCED_BY','REPORTED_FROM','SUPERSEDES'
    ))
);
```

권장 인덱스:

```sql
CREATE INDEX IF NOT EXISTS ix_lineage_edges_parent
ON lineage_edges(parent_node_id, created_at);

CREATE INDEX IF NOT EXISTS ix_lineage_edges_child
ON lineage_edges(child_node_id, created_at);

CREATE INDEX IF NOT EXISTS ix_snapshots_run
ON data_snapshots(run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_dataset_versions_as_of
ON dataset_versions(dataset_id, as_of DESC);
```

### 10.9 `reproducibility_manifests`

```sql
CREATE TABLE IF NOT EXISTS reproducibility_manifests (
    manifest_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    policy_snapshot_id TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    code_version TEXT NOT NULL,
    data_hash TEXT NOT NULL,
    schema_hash TEXT NOT NULL,
    universe_hash TEXT NOT NULL,
    calendar_version TEXT NOT NULL,
    transformation_versions_json TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (snapshot_id) REFERENCES data_snapshots(snapshot_id),
    UNIQUE (run_id)
);
```

### 10.10 `snapshot_events`

```sql
CREATE TABLE IF NOT EXISTS snapshot_events (
    event_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    message TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (snapshot_id) REFERENCES data_snapshots(snapshot_id) ON DELETE CASCADE,
    CHECK (event_type IN (
        'REQUESTED','BUILD_STARTED','ARTIFACT_ADDED','HASH_VERIFIED',
        'QUALITY_ATTACHED','READY','LOCKED','QUARANTINED','FAILED',
        'ARCHIVED','EXPIRED','REPLAYED'
    ))
);
```

## 11. Canonical 해시 규칙

### 11.1 정규화 규칙

- 컬럼 순서를 스키마 정의 순서로 고정
- 행 정렬 키를 명시적으로 정의
- 시간은 UTC ISO-8601로 변환
- 숫자는 locale 비의존 형식 사용
- NaN, null, 빈 문자열을 구분
- 부동소수점은 데이터셋별 scale 규칙 적용
- JSON 객체 키는 사전순 정렬
- 압축 방식이나 파일 경로는 콘텐츠 해시에 포함하지 않음
- 해시 규칙 버전을 manifest에 기록

### 11.2 참조 코드

```python
import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any


HASH_SPEC_VERSION = "1.0"


def normalize_scalar(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, float):
        if value != value:
            return {"__type__": "NaN"}
        return format(value, ".12g")
    return value


def canonical_json(value: Any) -> str:
    def convert(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {key: convert(obj[key]) for key in sorted(obj)}
        if isinstance(obj, (list, tuple)):
            return [convert(item) for item in obj]
        return normalize_scalar(obj)

    return json.dumps(
        convert(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_value(value: Any) -> str:
    payload = canonical_json(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
```

대규모 테이블은 전체 JSON 직렬화 대신 파티션별 해시를 계산한 뒤 Merkle root 방식으로 결합한다.

```python
def merkle_root(partition_hashes: list[str]) -> str:
    if not partition_hashes:
        return hashlib.sha256(b"").hexdigest()

    level = sorted(partition_hashes)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [
            hashlib.sha256((level[i] + level[i + 1]).encode()).hexdigest()
            for i in range(0, len(level), 2)
        ]
    return level[0]
```

## 12. Repository 인터페이스

```python
from typing import Any, Protocol


class SnapshotRepository(Protocol):
    def register_source(self, source: Any) -> str: ...
    def register_dataset(self, dataset: Any) -> str: ...
    def register_dataset_version(self, version: Any) -> str: ...
    def register_artifact(self, artifact: Any) -> str: ...
    def create_snapshot(self, request: SnapshotRequest) -> DataSnapshot: ...
    def add_snapshot_member(
        self,
        snapshot_id: str,
        artifact_id: str,
        role: str,
        required: bool = True,
    ) -> None: ...
    def attach_quality_result(self, snapshot_id: str, result: Any) -> None: ...
    def transition_snapshot(self, snapshot_id: str, target: str) -> DataSnapshot: ...
    def lock_snapshot(self, snapshot_id: str, run_id: str) -> DataSnapshot: ...
    def save_lineage_node(self, node: Any) -> str: ...
    def save_lineage_edge(self, edge: Any) -> str: ...
    def save_manifest(self, manifest: ReproducibilityManifest) -> str: ...
    def get_snapshot(self, snapshot_id: str) -> DataSnapshot | None: ...
    def get_run_manifest(self, run_id: str) -> ReproducibilityManifest | None: ...
    def find_affected_runs(self, artifact_id: str) -> list[str]: ...
```

## 13. 핵심 알고리즘

### 13.1 데이터셋 버전 등록

```text
수집 결과 수신
→ 스키마 정규화 및 schema_hash 계산
→ 파티션별 content_hash 계산
→ 전체 content_hash 생성
→ 기존 최신 버전과 비교
→ 내용이 동일하면 기존 버전 재사용
→ 내용이 다르면 새 dataset_version 생성
→ 이전 버전 SUPERSEDED 처리 여부 결정
→ 원천→버전→산출물 lineage 기록
```

동일 콘텐츠의 중복 등록은 멱등적으로 처리한다.

### 13.2 실행 스냅샷 생성

```python
def build_snapshot(request, artifacts, repository, quality_service):
    snapshot = repository.create_snapshot(request)
    repository.transition_snapshot(snapshot.snapshot_id, "BUILDING")

    selected = select_artifacts(
        artifacts=artifacts,
        market=request.market,
        symbols=request.symbols,
        start_at=request.start_at,
        end_at=request.end_at,
        as_of=request.as_of,
    )

    validate_required_coverage(request, selected)

    for sequence_no, artifact in enumerate(selected, start=1):
        verify_artifact_hash(artifact)
        repository.add_snapshot_member(
            snapshot.snapshot_id,
            artifact.artifact_id,
            role=artifact.member_role,
            required=True,
        )
        record_snapshot_lineage(snapshot, artifact, repository)

    repository.transition_snapshot(snapshot.snapshot_id, "VALIDATING")
    quality = quality_service.evaluate_snapshot(snapshot.snapshot_id)
    repository.attach_quality_result(snapshot.snapshot_id, quality)

    if quality.status == "FAILED":
        return repository.transition_snapshot(snapshot.snapshot_id, "QUARANTINED")

    finalized = calculate_snapshot_hashes(snapshot.snapshot_id, repository)
    repository.transition_snapshot(snapshot.snapshot_id, "READY")
    return finalized
```

### 13.3 스냅샷 잠금

잠금 조건:

- 상태가 `READY`
- 모든 필수 member 존재
- content hash 재검증 성공
- schema hash 일치
- 품질 상태가 모드별 허용값
- 정책 스냅샷 활성 상태
- 실행 ID가 아직 다른 스냅샷에 바인딩되지 않음

```python
def lock_for_run(snapshot_id, run_id, mode, repository):
    snapshot = repository.get_snapshot(snapshot_id)
    if snapshot is None:
        raise SnapshotNotFound(snapshot_id)
    if snapshot.status != "READY":
        raise SnapshotNotReady(snapshot.status)
    if mode in {"PAPER", "LIVE"} and snapshot.quality_status != "PASSED":
        raise SnapshotQualityRejected(snapshot.quality_status)
    verify_snapshot_integrity(snapshot, repository)
    return repository.lock_snapshot(snapshot_id, run_id)
```

### 13.4 Manifest 생성

```text
LOCKED snapshot 조회
→ policy snapshot 및 config_hash 조회
→ 실행 코드 버전 조회
→ 유니버스·거래일 캘린더 버전 조회
→ 모든 변환 단계 버전 수집
→ canonical manifest JSON 생성
→ manifest_hash 계산
→ 저장 후 run과 1:1 연결
```

### 13.5 계보 탐색

상향 추적:

```text
Decision
→ Signal output
→ Feature artifact
→ Validated market data
→ Raw market data
→ External source
```

하향 영향 분석:

```text
Corrected raw artifact
→ affected normalized artifacts
→ affected snapshots
→ affected runs
→ affected decisions/orders/reports
```

순환 계보는 허용하지 않는다. 새 edge 저장 시 DFS 또는 recursive CTE로 cycle 여부를 검증한다.

## 14. Orchestrator 통합

기존 실행 단계에 다음 단계를 추가한다.

```text
1. validate_request
2. resolve_policy_snapshot
3. load_market_data
4. register_dataset_versions
5. build_data_snapshot
6. validate_market_data
7. attach_quality_result
8. lock_data_snapshot
9. build_reproducibility_manifest
10. build_decision_context
11. run_existing_pipeline
12. attach_output_lineage
13. aggregate_result
14. build_report_fixture
```

실행 컨텍스트:

```python
@dataclass(frozen=True)
class RunReproducibilityContext:
    run_id: str
    policy_snapshot_id: str
    config_hash: str
    data_snapshot_id: str
    data_hash: str
    schema_hash: str
    universe_hash: str
    manifest_id: str
    code_version: str
```

각 Stage 출력에는 다음 메타데이터를 공통으로 포함한다.

```python
@dataclass(frozen=True)
class LineageMetadata:
    run_id: str
    stage_name: str
    input_artifact_ids: tuple[str, ...]
    output_artifact_id: str
    transformation_name: str
    transformation_version: str
    parameters_hash: str
```

## 15. 모드별 정책

| 모드 | Snapshot 요구사항 |
|---|---|
| DRY_RUN | WARNING 품질 허용 가능, manifest 필수 |
| PAPER | 품질 PASSED 필수, 계좌 식별자 마스킹 |
| LIVE_BLOCKED | 실계좌 데이터 접근 금지, 분석 데이터만 잠금 |
| LIVE | 품질 PASSED, 정책 승인, 최신성 SLA, 이중 무결성 검증 필수 |
| SIMULATED | 역사 데이터 범위와 유니버스 완전 고정 |
| INCIDENT_REPLAY | 원 실행 manifest를 그대로 재사용하거나 차이를 명시 |

LIVE 모드 추가 검증:

- 시세 최신성 SLA 이내
- 거래일 및 장 상태 일치
- 브로커 계좌 스냅샷 시점 기록
- 정정 대기 또는 격리 데이터 미포함
- 원천 공급자 상태 `ACTIVE`
- 데이터와 정책 스냅샷 모두 잠금 완료

## 16. 오류 모델

```python
class SnapshotError(Exception):
    pass


class SnapshotNotFound(SnapshotError):
    pass


class SnapshotNotReady(SnapshotError):
    pass


class SnapshotIntegrityError(SnapshotError):
    pass


class SnapshotCoverageError(SnapshotError):
    pass


class SnapshotQualityRejected(SnapshotError):
    pass


class SchemaMismatchError(SnapshotError):
    pass


class LineageCycleError(SnapshotError):
    pass
```

오류 처리 원칙:

- 무결성 오류는 재시도하지 않고 격리
- 일시적 저장소 오류만 제한 재시도
- 누락 범위는 자동 보간하지 않고 Data Quality 정책으로 위임
- 해시 불일치는 기존 산출물을 수정하지 않고 새 버전 생성
- 계보 저장 실패 시 해당 Stage 완료 처리 금지
- manifest 생성 실패 시 실행을 재현 불가 상태로 계속 진행하지 않음

## 17. 코드 구조

```text
lineage/
├── __init__.py
├── models.py              # Snapshot, Artifact, Manifest, Lineage models
├── service.py             # DataSnapshotLineageEngine
├── repository.py          # Repository protocol
├── sqlite_repository.py   # SQLite implementation
├── hashing.py             # canonical hash and Merkle root
├── schema.py              # schema normalization and hash
├── selector.py            # artifact range/symbol selection
├── graph.py               # lineage graph and cycle guard
├── manifest.py            # reproducibility manifest builder
├── policy.py              # mode-specific snapshot policy
└── exceptions.py

migrations/
└── 016_data_snapshot_lineage.sql

tests/
├── test_lineage_hashing.py
├── test_dataset_version.py
├── test_snapshot_builder.py
├── test_snapshot_lock.py
├── test_lineage_graph.py
├── test_manifest_builder.py
├── test_lineage_repository.py
├── test_lineage_integration.py
└── test_lineage_reproducibility.py
```

## 18. 서비스 코드 초안

```python
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class BuildSnapshotCommand:
    request: SnapshotRequest
    artifacts: tuple[object, ...]
    code_version: str
    config_hash: str


class DataSnapshotLineageEngine:
    def __init__(
        self,
        repository: SnapshotRepository,
        quality_service,
        snapshot_policy,
        manifest_builder,
    ):
        self.repository = repository
        self.quality_service = quality_service
        self.snapshot_policy = snapshot_policy
        self.manifest_builder = manifest_builder

    def build_and_lock(self, command: BuildSnapshotCommand):
        request = command.request
        self.snapshot_policy.validate_request(request)

        snapshot = build_snapshot(
            request=request,
            artifacts=command.artifacts,
            repository=self.repository,
            quality_service=self.quality_service,
        )

        if snapshot.status == "QUARANTINED":
            raise SnapshotQualityRejected(snapshot.quality_status)

        self.snapshot_policy.validate_lock(snapshot, request.mode)
        locked = lock_for_run(
            snapshot.snapshot_id,
            request.run_id,
            request.mode,
            self.repository,
        )

        manifest = self.manifest_builder.build(
            run_id=request.run_id,
            snapshot=locked,
            policy_snapshot_id=request.policy_snapshot_id,
            config_hash=command.config_hash,
            code_version=command.code_version,
        )
        self.repository.save_manifest(manifest)
        return locked, manifest
```

## 19. 테스트 계획

### 19.1 단위 테스트

#### Hashing

- 동일 데이터와 동일 정렬 규칙은 동일 해시 생성
- 행 순서가 달라도 정렬 키 적용 후 동일 해시 생성
- 값 변경 시 콘텐츠 해시 변경
- 컬럼 타입 변경 시 schema hash 변경
- UTC 변환 후 동일 시점은 동일 해시 생성
- NaN과 null은 서로 다른 표현으로 해시
- 빈 파티션 Merkle root가 결정적
- 홀수 개 파티션의 Merkle root 계산 정확성

#### Dataset Version

- 최초 데이터셋 버전 등록
- 동일 콘텐츠 재등록 시 기존 버전 재사용
- 수정 데이터 등록 시 새 버전 생성
- 새 버전이 이전 버전을 supersede
- 격리 버전은 ACTIVE 전환 불가
- 음수 row count 차단

#### Snapshot Builder

- 필수 artifact로 정상 snapshot 생성
- 종목 범위 누락 시 실패
- 날짜 범위 누락 시 실패
- artifact hash 불일치 시 QUARANTINED
- 품질 PASSED이면 READY
- 품질 FAILED이면 QUARANTINED
- 선택적 reference artifact 누락은 경고 처리
- 동일 요청과 동일 artifact 집합은 동일 snapshot content hash 생성

#### Snapshot Lock

- READY snapshot 잠금 성공
- READY가 아닌 상태 잠금 차단
- PAPER에서 WARNING 품질 차단
- LIVE에서 오래된 데이터 차단
- 동일 run에 두 개 snapshot 바인딩 차단
- LOCKED snapshot 수정 차단

#### Lineage Graph

- 부모→자식 edge 저장
- 존재하지 않는 node 참조 차단
- 자기 자신 edge 차단
- 간접 cycle 생성 차단
- 상향 원천 추적 결과 정확성
- 하향 영향 run 조회 정확성

#### Manifest

- 필수 필드 포함
- 동일 입력은 동일 manifest hash 생성
- code version 변경 시 manifest hash 변경
- policy snapshot 변경 시 manifest hash 변경
- universe 변경 시 manifest hash 변경

### 19.2 Repository 테스트

- snapshot 생성과 member 저장 원자성
- snapshot READY 전환과 hash 저장 원자성
- lineage node/edge 트랜잭션 롤백
- 외래키 제약 활성화
- concurrent dataset version 등록 시 중복 방지
- SQLite busy timeout 처리
- archived snapshot 메타데이터 조회

### 19.3 통합 테스트

1. 고정 OHLCV fixture를 DataHub 결과로 등록한다.
2. raw→normalized→validated lineage를 생성한다.
3. Data Quality PASSED 결과를 연결한다.
4. 정책 스냅샷과 함께 분석 snapshot을 생성한다.
5. snapshot을 run에 잠근다.
6. Signal, Risk, Decision 결과 node를 연결한다.
7. Report에서 Decision부터 원천 OHLCV까지 역추적한다.
8. 동일 fixture와 설정으로 재실행하여 동일 manifest hash를 확인한다.

### 19.4 백테스트 재현성 테스트

- 동일 코드·정책·데이터·유니버스는 동일 거래 결과 생성
- 수정주가 데이터 버전 변경 시 data hash와 결과가 함께 변경
- 미래 데이터 artifact가 snapshot에 포함되지 않음
- 테스트 기간 이후 기업행사 정보 사용 차단
- 종목 유니버스 snapshot이 survivorship bias 방지에 사용됨
- 거래일 캘린더 버전 고정

### 19.5 실패 주입 테스트

- 저장 도중 DB 연결 종료
- artifact storage URI 접근 실패
- content hash 불일치
- 스키마 레지스트리 오류
- quality service timeout
- lineage edge 저장 실패
- manifest 저장 실패
- 두 worker의 동시 snapshot 잠금
- 원천 데이터 정정 중 snapshot 생성

### 19.6 보안 테스트

- API key가 metadata 또는 manifest에 저장되지 않음
- 계좌번호가 마스킹됨
- storage URI에 credential query string 저장 차단
- 허용되지 않은 파일 경로 접근 차단
- artifact payload 대신 참조와 해시만 감사 로그에 저장

### 19.7 성능 테스트

- 1,000개 종목 × 10년 일봉 snapshot 생성 시간 측정
- 파티션별 병렬 해시 계산
- 100만 개 lineage edge 상향·하향 조회
- snapshot member bulk insert
- 동일 artifact 해시 캐시 효과 측정

## 20. 수용 기준

Data Snapshot & Lineage Engine v1은 다음 조건을 만족하면 완료로 본다.

1. 시장 데이터셋과 버전을 등록할 수 있다.
2. 실행별 불변 데이터 스냅샷을 생성하고 잠글 수 있다.
3. 원천→정제→신호→결정→리포트 계보를 양방향 조회할 수 있다.
4. 콘텐츠와 스키마 무결성 해시를 결정적으로 생성한다.
5. 정책·데이터·코드 버전이 포함된 재현성 manifest를 생성한다.
6. 동일 manifest로 백테스트 결과를 재현할 수 있다.
7. 수정 데이터가 영향을 준 실행과 결과를 찾을 수 있다.
8. 품질 실패 또는 무결성 실패 데이터는 PAPER/LIVE 실행에 사용되지 않는다.
9. SQLite 기반 단위·통합 테스트가 통과한다.
10. Report Engine이 manifest와 lineage 참조를 출력할 수 있다.

## 21. 구현 우선순위

1. 도메인 모델과 canonical hashing
2. SQLite migration 및 Repository
3. dataset/version/artifact 등록
4. snapshot builder와 상태 전이
5. snapshot lock 및 mode policy
6. lineage node/edge와 cycle guard
7. reproducibility manifest
8. Orchestrator adapter
9. fixture 기반 통합 테스트
10. Backtest 재현성 회귀 테스트
11. 영향 분석 query
12. 보존·아카이브 정책

## 22. 기존 엔진과의 연결 변경

### Integration Orchestrator

- `RunRequest` 검증 후 policy snapshot을 먼저 선택한다.
- DataHub 결과를 dataset version으로 등록한다.
- Data Quality 완료 후 snapshot을 잠근다.
- 잠금 전에는 Signal Engine을 실행하지 않는다.
- 최종 RunResult에 manifest ID를 포함한다.

### Run State Store

`ade_run_artifacts`에는 대규모 데이터 payload를 직접 저장하지 않고 다음 참조만 저장한다.

```json
{
  "snapshot_id": "snap_20260714_001",
  "manifest_id": "manifest_20260714_001",
  "content_hash": "...",
  "schema_hash": "...",
  "storage_uri": "dataset://kr_ohlcv/version/42"
}
```

### Backtest Engine

- `data_snapshot_id`와 `universe_hash`를 필수 입력으로 추가한다.
- 데이터 로더는 snapshot member 밖의 데이터를 조회할 수 없다.
- 결과 테이블에 `manifest_id`를 저장한다.

### Report Engine

리포트 상단에 다음을 표시한다.

- Data Snapshot ID
- Policy Snapshot ID
- Code Version
- Data Hash
- Manifest Hash
- 품질 상태
- 재현 가능 여부

## 23. 다음 설계 대상

다음 엔진은 **Audit & Compliance Engine v1**으로 한다.

이 엔진은 Run State, Policy, Data Lineage, Decision, Order, Execution 이벤트를 통합하여 다음을 제공한다.

- 변경 불가능한 감사 이벤트
- 운영자 행위 추적
- LIVE 승인 증적
- 예외 및 수동 개입 기록
- 규칙 위반 탐지
- 감사 리포트 및 보존 정책
