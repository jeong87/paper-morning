# Paper Morning 매뉴얼

이 문서는 **고급 설정, 자동화, 이메일 발송, GitHub Actions 운영**을 다룹니다.  
처음 설치하는 사용자는 먼저 [MANUAL_FIRSTTIME_KR.md](./MANUAL_FIRSTTIME_KR.md)를 보세요.
에이전트/툴 연동 용도라면 [MANUAL_AGENT_KR.md](./MANUAL_AGENT_KR.md)를 보세요.

## 1. 현재 제품 방향
Paper Morning의 기본 경로는 이제 `search-first`입니다.

기본:
- 필요할 때 와서 검색
- 로컬 인박스에서 결과 확인
- 원하면 아침 팝업 자동 실행

선택:
- Gmail OAuth
- Gmail 앱 비밀번호
- GitHub Actions 자동화

즉, 이메일 발송은 핵심 기능이 아니라 **옵션 기능**입니다.

## 2. 실행 모드 요약
`local inbox`
- 기본값
- 메일 대신 로컬 결과 HTML/JSON 저장
- 브라우저에서 바로 다시 열 수 있음

`local morning popup`
- PC가 켜져 있고 앱이 실행 중일 때 사용
- 예약된 시각에 검색 후 브라우저 탭을 자동으로 띄움

`gmail_oauth`
- 선택 고급 기능
- Gmail OAuth 인증 필요

`gmail_app_password`
- 선택 fallback 기능
- Gmail 2단계 인증 + 앱 비밀번호 필요

## 3. 추천 운영 순서
1. 로컬 인박스로 검색 품질 검증
2. 필요하면 아침 팝업 켜기
3. 정말 필요할 때만 메일 전송 추가
4. 내 PC를 항상 켜둘 수 없다면 GitHub Actions로 자동화

## 4. 주요 환경변수
아래 값들은 `.env` 또는 `PM_ENV_FILE`에 들어갈 수 있습니다.

```env
# Delivery
DELIVERY_MODE=local_inbox

# Search defaults
SEARCH_INTENT_DEFAULT=best_match
SEARCH_TIME_HORIZON_DEFAULT=1y

# Local schedule
TIMEZONE=Asia/Seoul
SEND_HOUR=9
SEND_MINUTE=0

# Search / sources
MAX_PAPERS=5
MAX_SEARCH_QUERIES_PER_SOURCE=4
ARXIV_MAX_RESULTS_PER_QUERY=25
PUBMED_MAX_IDS_PER_QUERY=25
ENABLE_SEMANTIC_SCHOLAR=true
SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY=20
ENABLE_GOOGLE_SCHOLAR=false
GOOGLE_SCHOLAR_MAX_RESULTS_PER_QUERY=10

# LLM
ENABLE_LLM_AGENT=true
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.1-flash
ENABLE_GEMINI_ADVANCED_REASONING=true
LLM_MAX_CANDIDATES=30
LLM_RELEVANCE_THRESHOLD=6
OUTPUT_LANGUAGE=ko

# Optional keys
NCBI_API_KEY=
SEMANTIC_SCHOLAR_API_KEY=
GOOGLE_SCHOLAR_API_KEY=
```

설명:
- `DELIVERY_MODE=local_inbox`가 기본입니다.
- `SEARCH_INTENT_DEFAULT`와 `SEARCH_TIME_HORIZON_DEFAULT`는 홈 화면 기본 검색값을 정합니다.
- `LLM_MAX_CANDIDATES`는 Gemini listwise rerank에 보내는 shortlist 상한입니다.

## 5. Gmail OAuth
기술적으로는 가능합니다. 다만 공개 사용자 대상으로 기본값으로 쓰기엔 준비물이 있습니다.

필요한 것:
- Google Cloud OAuth client
- consent screen 설정
- redirect URI 정합성
- `gmail.send` scope 관련 운영 정책 확인

주의:
- 테스트 상태에서는 test user만 사용할 수 있습니다.
- 공개 사용자 대상으로 안정적으로 열려면 Google 쪽 검증 이슈를 점검해야 합니다.

따라서 추천 순서는:
1. 로컬 인박스
2. Gmail OAuth
3. Gmail 앱 비밀번호

## 6. Gmail 앱 비밀번호
가장 단순한 fallback 경로입니다.

필요한 값:
- `GMAIL_ADDRESS`
- `RECIPIENT_EMAIL`
- `GMAIL_APP_PASSWORD`

주의:
- 일반 Gmail 로그인 비밀번호가 아닙니다.
- 2단계 인증 활성화 후 발급한 16자리 앱 비밀번호를 써야 합니다.
- 발급 링크: https://myaccount.google.com/apppasswords

## 7. GitHub Actions 자동화
내 PC를 항상 켜둘 수 없다면 이 모드가 유용합니다.

필수 워크플로우:
- `.github/workflows/paper-morning-digest.yml`
- `.github/workflows/paper-morning-bootstrap-topics.yml`

필수 Secret:
- `PM_ENV_FILE`

선택 Secret:
- `PM_TOPICS_JSON`
- `PM_PROJECTS_JSON`

설명:
- `PM_ENV_FILE`에는 `.env` 전체 내용을 넣습니다.
- `PM_TOPICS_JSON`는 topic/query를 직접 관리할 때 사용합니다.
- `PM_PROJECTS_JSON`는 bootstrap query 생성용입니다.

## 8. GitHub Actions 운영 팁
`dry_run`
- 메일 없이 검색/수집/평가만 실행
- 자동화 품질 검증에 적합

`send_now`
- 실제 메일 또는 선택한 delivery 경로 실행

추천:
- 처음에는 반드시 `dry_run`
- 결과 품질과 인증 설정이 맞는지 확인한 뒤 `send_now`

## 9. 검색 품질 관련 메모
현재 검색 파이프라인은 다음 구조입니다.

1. 컨텍스트에서 검색식 생성
2. arXiv / PubMed 등에서 후보 수집
3. 기간 필터 적용
4. heuristic 우선순위 조정
5. Gemini listwise rerank

즉, 최종 Gemini 평가는 후보를 하나씩 따로 보는 방식이 아니라 shortlist를 한 번에 비교하는 방식입니다.

## 10. 문제 해결
`No candidates retrieved`
- 검색식이 너무 좁거나 source 응답이 부족할 수 있습니다.
- 기간을 늘리거나 키워드를 넓혀보세요.

`Quota exhausted`
- Gemini key quota가 부족할 수 있습니다.
- 앱은 가능한 폴백 모델을 순서대로 시도합니다.

`Popup blocked`
- 로컬 인박스/프리뷰는 새 탭을 열기 때문에 브라우저 팝업 허용이 필요할 수 있습니다.

`Missing email env vars`
- 이메일 기능을 켠 경우에만 필요한 오류입니다.
- `local_inbox`만 쓸 때는 이메일 관련 값이 없어도 됩니다.

## 11. 관련 문서
- 한글 README: [README_KR.md](./README_KR.md)
- 초보자 가이드: [MANUAL_FIRSTTIME_KR.md](./MANUAL_FIRSTTIME_KR.md)
- English README: [../../README.md](../../README.md)
