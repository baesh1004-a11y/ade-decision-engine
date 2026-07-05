# 04. KIS Integration Layer

## Purpose

KIS Integration Layer는 한국투자증권 OpenAPI와 ADE 내부 모델 사이의 어댑터이다. 외부 API 응답을 내부 `PriceBar`, `BrokerBalance`, `Position`, `OrderResult` 형태로 변환한다.

## Boundary

- KIS Layer는 판단하지 않는다.
- KIS Layer는 외부 API 호출과 응답 정규화만 담당한다.
- 실계좌 주문은 별도 안전 검증 전까지 비활성화한다.

## Components

| Component | Responsibility |
|---|---|
| KISAuthClient | access token 발급/갱신 |
| KISPriceDownloader | 일봉/시세 조회 |
| KISBrokerAdapter | 잔고, 보유종목, 주문 인터페이스 |
| KISMapper | KIS 응답을 ADE 모델로 변환 |

## Architecture

```text
KIS OpenAPI
  ↓
KISAuthClient
  ↓
KISPriceDownloader / KISBrokerAdapter
  ↓
ADE internal models
  ↓
DataHub / Portfolio State / Order Engine
```

## Required Environment Variables

```text
KIS_APP_KEY
KIS_APP_SECRET
KIS_ACCOUNT_NO
KIS_BASE_URL
KIS_MODE=mock|real
```

## Safety Rules

- API key, secret, account number must never be committed.
- Default mode is mock/dry-run.
- Real order execution requires explicit policy enablement.

## Implementation Status

| Task | Status |
|---|---|
| Adapter design | Done |
| Token issuance test | Pending |
| REST price call test | Pending |
| Balance query test | Pending |
| DataHub sync integration | Pending |
