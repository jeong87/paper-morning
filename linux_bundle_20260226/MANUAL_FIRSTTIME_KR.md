# Paper Morning 초보자용 매뉴얼

이 문서는 "처음 설치하는 사용자"를 위한 안내입니다.
아래 순서대로만 하면, 내 PC를 켜두지 않아도 GitHub Actions가 매일 자동으로 메일을 보냅니다.

## 0. 5분 준비물 체크
1. Gmail 계정 1개
2. GitHub 계정 1개
3. Gemini API Key 1개
4. 이 저장소 코드가 올라간 GitHub Repository 1개

## 1. 가장 먼저 이해할 것
1. 실제 실행은 GitHub 서버에서 돌아갑니다.
2. 그래서 개인 노트북을 24시간 켜둘 필요가 없습니다.
3. 메일 발송 시각은 기본 한국시간 오전 9시입니다.
4. 사용자가 해야 하는 핵심은 "Secret 2개 등록"입니다.

## 2. Gmail 앱 비밀번호 만들기 (가장 중요)
1. Google 계정에서 2단계 인증을 먼저 켭니다.
2. 아래 링크로 들어갑니다.
3. 앱 비밀번호 16자리를 생성합니다.
4. 공백 없이 붙여서 보관합니다.

링크:
- https://myaccount.google.com/apppasswords

주의:
- 이 16자리는 Gmail 로그인 비밀번호가 아닙니다.
- 반드시 앱 비밀번호를 써야 합니다.

## 3. Gemini API Key 만들기
1. 아래 링크 접속
2. "Get API key"로 키 발급
3. 복사해서 보관

링크:
- https://aistudio.google.com/app/apikey

## 4. 저장소 준비 (Fork 권장)
1. 원본 Paper Morning 저장소 페이지에서 `Fork`를 누릅니다.
2. 내 계정으로 복사된 저장소(내 fork)를 엽니다.
3. 이후 설정/실행은 내 fork 저장소에서 진행하면 됩니다.

선택:
- 직접 새 저장소에 올리고 싶다면 아래 명령으로 진행해도 됩니다.

```bash
git init
git add .
git commit -m "paper-morning init"
git branch -M main
git remote add origin https://github.com/<내계정>/<내레포>.git
git push -u origin main
```

4. GitHub 웹에서 `.github/workflows/` 폴더가 보이면 정상입니다.

## 5. Secrets 2개 등록 (핵심)
경로:
`Repository > Settings > Secrets and variables > Actions > New repository secret`

반드시 등록할 Secret:
1. `PM_ENV_FILE`
2. `PM_TOPICS_JSON`

### 5-1) PM_ENV_FILE 값 예시
아래를 그대로 붙여넣고, 내 값으로 바꿔 저장하세요.

```env
GMAIL_ADDRESS=your_sender@gmail.com
RECIPIENT_EMAIL=your_receiver@gmail.com
GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx

TIMEZONE=Asia/Seoul
SEND_HOUR=9
SEND_MINUTE=0
SEND_FREQUENCY=daily
SEND_ANCHOR_DATE=2026-01-01
LOOKBACK_HOURS=24

MAX_PAPERS=5
MAX_SEARCH_QUERIES_PER_SOURCE=4
ARXIV_MAX_RESULTS_PER_QUERY=25
PUBMED_MAX_IDS_PER_QUERY=25
ENABLE_SEMANTIC_SCHOLAR=true
SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY=20
ENABLE_GOOGLE_SCHOLAR=false
GOOGLE_SCHOLAR_MAX_RESULTS_PER_QUERY=10

ENABLE_LLM_AGENT=true
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.1-pro
ENABLE_GEMINI_ADVANCED_REASONING=true
LLM_BATCH_SIZE=5
LLM_MAX_CANDIDATES=30
LLM_RELEVANCE_THRESHOLD=6

ENABLE_CEREBRAS_FALLBACK=true
CEREBRAS_API_KEY=
CEREBRAS_MODEL=gpt-oss-120b

NCBI_API_KEY=
SEMANTIC_SCHOLAR_API_KEY=
GOOGLE_SCHOLAR_API_KEY=
```

LLM 동작 순서(기본):
1. `ENABLE_GEMINI_ADVANCED_REASONING=true`면 기본 모델은 `gemini-3.1-pro`
2. `gemini-3.1-pro` 실패 시 `gemini-3.1-flash` 재시도
3. 그래도 실패 시 `gemini-2.5-flash` 재시도
4. Gemini 전체 실패 + Cerebras 키가 있으면 `gpt-oss-120b`로 폴백

### 5-2) PM_TOPICS_JSON 값 예시
아래를 그대로 붙여넣고 시작해도 됩니다.

```json
{
  "projects": [
    {
      "name": "안저영상 기반 뇌졸중 예측",
      "context": "Fundus image based stroke risk prediction using multimodal deep learning"
    },
    {
      "name": "안저영상 기반 CAC score > 0 분류",
      "context": "Retinal biomarkers to classify CAC score above zero"
    }
  ],
  "topics": [
    {
      "name": "Fundus + Stroke",
      "keywords": ["fundus", "retina", "stroke", "deep learning"],
      "arxiv_query": "(all:fundus OR all:retina) AND (all:stroke) AND (all:deep learning)",
      "pubmed_query": "(fundus OR retina) AND stroke AND (deep learning)",
      "semantic_scholar_query": "fundus retina stroke deep learning risk prediction",
      "google_scholar_query": "fundus retina stroke deep learning risk prediction"
    }
  ]
}
```

주의:
- `topics`가 빈 배열이면 검색 쿼리가 없어서 실패합니다.

## 6. 처음 실행 3단계
1. `Actions` 탭에서 `paper-morning-bootstrap-topics` 1회 실행
2. `Actions` 탭에서 `paper-morning-digest`를 `dry_run`으로 1회 실행
3. 같은 워크플로우를 `send_now`로 1회 실행

성공 기준:
1. dry_run에서 에러 없이 완료
2. send_now 후 메일이 실제 도착

## 7. 내일부터 자동으로 오게 만들기
1. 별도 버튼을 켜둘 필요 없습니다.
2. 기본 워크플로우에 이미 매일 08:47 KST(= 09:00 기준 내부 13분 선행) 스케줄이 들어 있습니다.
3. 다음 날 아침 메일이 오면 정상입니다.

## 8. 자주 막히는 지점과 바로 해결법
1. `Missing required env vars for email: GMAIL_ADDRESS`
원인: `PM_ENV_FILE`에 해당 값 누락
해결: Secret 다시 열어 전체 값 재붙여넣기

2. `535 Username and Password not accepted`
원인: Gmail 주소와 앱 비밀번호 계정이 다르거나, 일반 비밀번호 사용
해결: 같은 계정의 앱 비밀번호 재발급 후 저장

3. `Not Found ... gemini-...:generateContent`
원인: 잘못된 모델명
해결: `GEMINI_MODEL`을 `gemini-3.1-pro` 또는 `gemini-3.1-flash`로 변경

4. `query keyword 없음`
원인: topics 쿼리 비어 있음
해결: bootstrap workflow 실행 후 생성된 topics로 교체

5. PubMed 429
원인: 호출량 제한
해결: `NCBI_API_KEY`를 넣으면 안정성이 좋아집니다.

## 9. 운영하면서 자주 하는 수정
1. 수집 기간 늘리기: `LOOKBACK_HOURS=120` (최근 5일)
2. 필터 완화: `LLM_RELEVANCE_THRESHOLD=6` 또는 `5`
3. 메일 개수 조절: `MAX_PAPERS=5` -> `10`
4. 발송 주기 변경:
`SEND_FREQUENCY=daily` / `every_3_days` / `weekly`

## 10. 팀원에게 전달할 때 한 줄 안내
"레포를 clone/fork해서 Secrets에 `PM_ENV_FILE`, `PM_TOPICS_JSON` 두 개만 넣고, Actions에서 dry_run -> send_now 한 번씩 실행하면 다음날부터 자동 발송됩니다."

## 11. 문의
- nineclas@gmail.com
