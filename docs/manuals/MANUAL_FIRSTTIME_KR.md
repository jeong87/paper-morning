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
4. **중요:** Fork 직후에는 Actions가 비활성화될 수 있습니다.
5. 내 fork의 상단 `Actions` 탭으로 들어가서:
   - (최초 1회) `I understand my workflows, go ahead and enable them` 버튼을 눌러 활성화합니다.
6. 좌측 목록에 `paper-morning-bootstrap-topics`, `paper-morning-digest`가 보이면 정상입니다.

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

7. GitHub 웹에서 `.github/workflows/` 폴더가 보이면 정상입니다.

## 5. Secrets 2개 등록 (핵심)
경로:
`Repository > Settings > Secrets and variables > Actions > New repository secret`

초보자 핵심:
- Secret은 여러 개를 만드는 게 아니라, **아래 2개만** 만들면 됩니다.
- `PM_ENV_FILE`의 Value에는 `.env 형식 텍스트 전체`를 한 번에 넣습니다.
- `PM_TOPICS_JSON`의 Value에는 `JSON 텍스트 전체`를 한 번에 넣습니다.

반드시 등록할 Secret 이름:
1. `PM_ENV_FILE`
2. `PM_TOPICS_JSON`

### 5-1) PM_ENV_FILE 값 예시
1. `New repository secret` 클릭
2. Name 칸: `PM_ENV_FILE`
3. Secret(Value) 칸: 아래 텍스트 **전체**를 복사해서 붙여넣기
4. 내 정보로 수정 후 저장

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
OUTPUT_LANGUAGE=en

ENABLE_CEREBRAS_FALLBACK=true
CEREBRAS_API_KEY=
CEREBRAS_MODEL=gpt-oss-120b

NCBI_API_KEY=
SEMANTIC_SCHOLAR_API_KEY=
GOOGLE_SCHOLAR_API_KEY=
```

위 2,3단계에서 발급받은 값 넣는 위치:
- 2단계에서 만든 Gmail App Password -> `GMAIL_APP_PASSWORD=` 뒤에 공백 없이 입력
- 3단계에서 만든 Gemini API Key -> `GEMINI_API_KEY=` 뒤에 입력
- 개인 메일을 한국어로 받고 싶다면 -> `OUTPUT_LANGUAGE=ko` 로 변경
- 공개 기본값/예시는 영어 유지 시 -> `OUTPUT_LANGUAGE=en`

LLM 동작 순서(기본):
1. `ENABLE_GEMINI_ADVANCED_REASONING=true`면 기본 모델은 `gemini-3.1-pro`
2. `gemini-3.1-pro` 실패 시 `gemini-3.1-flash` 재시도
3. 그래도 실패 시 `gemini-2.5-flash` 재시도
4. Gemini 전체 실패 + Cerebras 키가 있으면 `gpt-oss-120b`로 폴백

### 5-2) PM_TOPICS_JSON 값 예시
1. `New repository secret` 클릭
2. Name 칸: `PM_TOPICS_JSON`
3. Secret(Value) 칸: 아래 JSON **전체**를 복사해서 붙여넣기
4. 프로젝트/키워드만 수정하고 저장

```json
{
  "projects": [
    {
      "name": "의료영상 분할 자동화",
      "context": "Automated lesion/organ segmentation from CT and MRI with robust generalization"
    },
    {
      "name": "임상 텍스트 기반 예후 예측",
      "context": "Early risk prediction from EHR notes and structured clinical variables"
    }
  ],
  "topics": [
    {
      "name": "Medical Imaging AI",
      "keywords": ["medical imaging", "segmentation", "detection", "vision transformer", "deep learning"],
      "arxiv_query": "(all:\"medical imaging\" OR all:radiology) AND (all:segmentation OR all:detection) AND (all:\"vision transformer\" OR all:\"deep learning\")",
      "pubmed_query": "(medical imaging OR radiology) AND (segmentation OR detection) AND (deep learning OR transformer)",
      "semantic_scholar_query": "medical imaging segmentation detection vision transformer deep learning",
      "google_scholar_query": "medical imaging segmentation detection vision transformer deep learning"
    }
  ]
}
```

주의:
- `topics`가 빈 배열이면 검색 쿼리가 없어서 실패합니다.
- JSON 수정 시 큰따옴표(`"`), 쉼표(`,`), 중괄호(`{}`), 대괄호(`[]`) 형식이 깨지지 않게 주의하세요.
- 형식이 깨지면 `PM_TOPICS_JSON is not valid JSON` 오류가 납니다.

## 6. 처음 실행 3단계
아래는 **GitHub 웹 UI에서 수동 실행하는 정확한 방법**입니다.

1. 상단 `Actions` 탭 클릭
2. (최초 1회라면) `I understand my workflows, go ahead and enable them` 클릭
3. 좌측 목록에서 `paper-morning-bootstrap-topics` 선택
4. 우측 `Run workflow` 클릭
5. `Use workflow from`는 `main` 유지, 필요하면 러너 옵션 선택 후 `Run workflow` 버튼으로 실행
6. 완료 후 좌측에서 `paper-morning-digest` 선택
7. `Run workflow` 클릭
8. 입력 옵션(Input)에서:
   - `Run mode`를 `dry_run`으로 선택
   - `Runner OS`를 선택
   - 다시 `Run workflow` 클릭
9. 같은 방식으로 한 번 더 실행하되:
   - `Run mode`를 `send_now`로 선택 후 실행

주의:
- `dry_run`, `send_now`는 코드 수정이 아니라 **Run workflow 입력 옵션**입니다.
- `.yml` 파일을 직접 고칠 필요 없습니다.

성공 기준:
1. dry_run에서 에러 없이 완료
2. send_now 후 메일이 실제 도착

## 7. 내일부터 자동으로 오게 만들기
1. 별도 버튼을 켜둘 필요 없습니다.
2. 기본 워크플로우에 이미 매일 08:47 KST(= 09:00 기준 내부 13분 선행) 스케줄이 들어 있습니다.
3. 다음 날 아침 메일이 오면 정상입니다.
4. 단, Actions가 Disable 상태면 자동 실행이 안 되므로 `Actions` 탭에서 활성화 상태를 확인하세요.

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
