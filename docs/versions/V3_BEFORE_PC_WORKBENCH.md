# V3 백업 · PC 통합 워크벤치 도입 전

이 브랜치는 추천 생성, 추천 근거 비교, 추천 검증, 주문 관리가 각각 별도 Streamlit 페이지로 분리되어 있던 마지막 버전입니다.

## 화면 구조

- 추천 생성: 한국/미국 Daily Center
- 추천 근거 비교: AI Pattern Lab 기반 증거 뷰어
- 추천 검증: 시장·업종·위험 체크리스트
- 주문 실행: 한국/미국 Trading Desk

## 한계

사용자가 추천을 확인하고 주문하기까지 여러 페이지를 반복 이동해야 하며, PC 대형 화면에서 한 번에 전체 흐름을 파악하기 어렵습니다.

## 복원

```bash
git switch backup/v3-before-pc-workbench
```

기준 커밋: `3779aa9a89f6f89aa12bf5aad7a96b467eae93fd`
