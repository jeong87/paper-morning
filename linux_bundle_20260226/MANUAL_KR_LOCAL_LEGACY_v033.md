# Paper Digest 사용자 매뉴얼

## 1) 앱이 하는 일
- 매일 지정 시각(기본 09:00)에 최신 논문을 수집합니다.
- Topic Editor에서 사용자가 요청할 때만 LLM이 검색 키워드/쿼리를 생성합니다.
- 매일 실행은 저장된 쿼리를 그대로 사용합니다. (자동 재생성 없음)
- 수집 소스: arXiv, PubMed, (선택) Semantic Scholar
- LLM이 논문 관련도를 1~10점으로 평가하고, 기준점 이상만 선별합니다.
- 선별 논문의 핵심 포인트/활용성을 한국어로 요약해서 Gmail로 보냅니다.

## 2) 실행 방법 (일반 사용자)
1. `PaperDigestLocalUI.exe`를 더블클릭합니다.
2. 브라우저가 자동으로 열리면 먼저 `Setup Wizard`에서 초기 설정을 완료합니다.
3. 이후 `Home / Settings / Topic Editor / Manual` 메뉴를 사용합니다.

Linux 사용자는:
1. `PaperDigestLocalUI` 실행 파일에 실행 권한을 부여합니다. (`chmod +x PaperDigestLocalUI`)
2. `./PaperDigestLocalUI`를 실행합니다.

## 3) 로컬 실행 시 주의
- 이 앱은 내 PC에서 스케줄러가 동작합니다.
- 매일 자동 발송을 받으려면 발송 시각에 PC가 켜져 있어야 합니다.
- PC를 꺼도 자동 발송되게 하려면 항상 켜진 서버에 배포해야 합니다.
- 기본값으로는 로컬 접근(127.0.0.1)만 허용됩니다.
- `--host 0.0.0.0` 같은 외부 접근 모드는 기본 차단되며, 테스트 목적일 때만
  `ALLOW_INSECURE_REMOTE_WEB=true` + `WEB_PASSWORD`를 함께 설정하세요.
- 배포판(`PaperDigestLocalUI.exe`/`PaperDigestLocalUI`)의 설정 파일은 실행 폴더가 아니라 사용자 데이터 폴더에 저장됩니다.
  - Windows: `%APPDATA%\\paper-morning`
  - Linux: `~/.config/paper-morning`
- 구버전(v0.1.0~v0.1.2)에서 실행 폴더에 저장된 `.env`, `user_topics.json`은 첫 실행 시 자동 이전됩니다.
- 자동 이전을 확실히 적용하려면, 업데이트 파일을 **기존 설치 폴더에 덮어쓰기**하는 방식으로 배포하세요.
- `start_web_console.bat` / `start_web_console.sh`로 소스 실행해도 동일한 사용자 데이터 폴더 설정을 사용합니다.

## 4) Settings 입력
필수 항목:
- `GMAIL_ADDRESS`: 발송에 사용할 Gmail 주소
- `RECIPIENT_EMAIL`: 수신 메일 주소

이메일 인증 필수 조건(둘 중 하나):
- `GMAIL_APP_PASSWORD`: Gmail 앱 비밀번호(16자리, SMTP 방식)
- Google OAuth 연동: `ENABLE_GOOGLE_OAUTH=true` + `Google 로그인 연결`
  - Client ID/Secret은 Settings에 직접 입력하거나, 배포판 내장 번들(`google_oauth_bundle.json`)을 사용할 수 있습니다.

권장 항목:
- `GEMINI_API_KEY`: LLM 기반 키워드 생성/관련도 평가/요약에 사용
- `GEMINI_MODEL`: 기본값 `gemini-3.1-flash`
- `ENABLE_GEMINI_ADVANCED_REASONING=true`: 고급 추론 모드 사용 시 `gemini-3.1-pro` 강제 적용
- `ENABLE_CEREBRAS_FALLBACK=true`: Gemini 실패 시 Cerebras 자동 백업 호출
- `CEREBRAS_API_KEY`: Cerebras 백업 모델 사용 시 필요
- `CEREBRAS_MODEL`: 기본값 `gpt-oss-120b`
- `NCBI_API_KEY`: PubMed 처리량 안정화를 위해 권장
- `ENABLE_SEMANTIC_SCHOLAR=true`: Semantic Scholar 소스 사용
- `SEMANTIC_SCHOLAR_API_KEY`: Semantic Scholar API 키(권장)
- `SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY`: Semantic Scholar 쿼리당 최대 수집 건수(기본 20)
- `WEB_PASSWORD`: 외부 접근 시 웹 콘솔 로그인 비밀번호
- `USE_KEYRING`: 가능하면 비밀값을 OS 키체인(자격 증명 관리자)에 저장
- `ALLOW_INSECURE_REMOTE_WEB`: HTTPS 없는 원격 노출 허용(기본 `false`, 비권장)
- `SEND_NOW_COOLDOWN_SECONDS`: Send Now 연속 실행 제한(기본 300초)
- `SENT_HISTORY_DAYS`: 이미 보낸 논문 ID 중복 제외 기간(기본 14일)

보안 표시 정책:
- `GMAIL_APP_PASSWORD`, `GEMINI_API_KEY`, `CEREBRAS_API_KEY`, `WEB_PASSWORD` 입력칸은 화면에 항상 빈칸으로 보입니다.
- `USE_KEYRING=true`이면 비밀값은 `.env` 평문 대신 `keyring://...` 참조로 저장됩니다(지원 환경).
- 빈칸 상태로 저장하면 기존 값은 유지됩니다.

운영 권장값(기본값):
- `MAX_PAPERS=5`
- `MAX_SEARCH_QUERIES_PER_SOURCE=4`
- `ARXIV_MAX_RESULTS_PER_QUERY=25`
- `PUBMED_MAX_IDS_PER_QUERY=25`
- `SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY=20`
- `LLM_MAX_CANDIDATES=30` (최대 50)
- `LLM_RELEVANCE_THRESHOLD=7`

## 5) Topic Editor 사용법
1. **Projects 테이블**에 `Project Name` / `Context`를 입력합니다.
   - 최초 실행 시 기본 프로젝트/쿼리는 비어 있는 상태입니다.
2. `Keyword / Query 생성` 버튼을 누르면 LLM이 topic 초안을 생성합니다.
   - 기본: Gemini 사용
   - Gemini 실패 + fallback 활성화 시: Cerebras 사용
3. **Topics / Queries 테이블**에서 키워드, arXiv 쿼리, PubMed 쿼리, Semantic Scholar 쿼리를 수동 수정할 수 있습니다.
4. `Save Topics`를 눌러 저장합니다.
5. 이후 Daily 실행은 방금 저장된 쿼리 상태 하나만 사용합니다.

## 6) Home 버튼 설명
- `Run Dry-Run`: 메일 발송 없이 오늘 수집/선별 결과만 실행합니다.
- `Send Now`: 지금 즉시 실제 메일을 1회 발송합니다.
  - 쿨다운(기본 300초) 내 재실행은 자동 차단됩니다.
- `Reload Scheduler`: 변경된 시간/설정을 스케줄러에 즉시 반영합니다.
- `Windows Task`: Windows 작업 스케줄러에 매일 자동 실행 작업을 등록합니다.
- `Task Status`: 진행률(Progress Bar), 현재 단계, 오류 메시지를 표시합니다.
- `Google OAuth 상태`: 연결/미연결 상태, 연동 계정, 클라이언트 소스(설정값/내장 번들)를 표시합니다.
- Home에서도 `Google 로그인 연결` / `연결 해제`를 바로 실행할 수 있습니다.
- Dry-run/메일 본문에는 선택 진단 정보(수집 건수, 점수 분포, threshold 통과 건수, 최종 선택 건수)가 함께 표시됩니다.
- `Logs` 메뉴: `paper-morning.log` 최근 로그를 브라우저에서 확인합니다.

## 7) 키 발급 방법
### 7-1) GEMINI_API_KEY 발급 (권장)
1. Google AI Studio 접속: `https://aistudio.google.com/`
2. Google 계정 로그인
3. `Get API key` 또는 `API keys` 메뉴에서 키 생성
4. 생성한 키를 `Settings > GEMINI_API_KEY`에 붙여넣고 저장
5. 사용량/요금 정책: `https://ai.google.dev/gemini-api/docs/rate-limits` 참고

### 7-2) GMAIL_APP_PASSWORD 발급 (SMTP 방식일 때)
1. Google 계정 보안 설정: `https://myaccount.google.com/security`
2. `2-Step Verification`(2단계 인증) 먼저 활성화
3. 같은 보안 페이지에서 `App passwords` 진입
4. 앱 비밀번호 16자리 생성
5. 생성한 16자 값을 `Settings > GMAIL_APP_PASSWORD`에 입력

### 7-3) Google OAuth 자동연동 (앱 비밀번호 대체)
1. Google Cloud Console 접속: `https://console.cloud.google.com/`
2. 프로젝트 선택/생성 후 `APIs & Services > Credentials`로 이동
3. `Create Credentials > OAuth client ID` 생성 (유형: `Web application`)
4. Authorized Redirect URI 추가
   - `http://127.0.0.1:5050/oauth/google/callback`
   - (선택) `http://localhost:5050/oauth/google/callback`
5. 발급된 Client ID / Client Secret을 앱 `Settings`에 입력 (또는 배포판 내장 번들 사용)
   - `ENABLE_GOOGLE_OAUTH=true`
   - `GOOGLE_OAUTH_USE_FOR_GMAIL=true`
   - `GOOGLE_OAUTH_CLIENT_ID`
   - `GOOGLE_OAUTH_CLIENT_SECRET`
6. `Google 로그인 연결` 버튼 클릭 후 Google 계정 승인
7. 연결 성공 시 `GOOGLE_OAUTH_CONNECTED_EMAIL`이 표시되고, Gmail API 발송이 활성화됩니다.

배포자(테스터 배포용) 권장:
- `google_oauth_bundle.template.json`을 복사해 `google_oauth_bundle.json` 생성
- 여기에 `client_id`, `client_secret`(필수), `redirect_uri`(선택) 입력 후 앱과 같은 폴더에 배포
- 그러면 최종 사용자는 Settings 입력 없이 Home의 `Google 로그인 연결`만 누르면 됩니다.

### 7-4) NCBI_API_KEY (선택)
- PubMed 처리량 안정화를 위해 입력을 권장합니다.
- NCBI 계정에서 API Key를 발급받아 `NCBI_API_KEY`에 입력합니다.

### 7-5) CEREBRAS_API_KEY 발급 (선택, Gemini 실패 대비용)
1. Cerebras Cloud 접속: `https://cloud.cerebras.ai/`
2. 계정 로그인 후 API Key 생성 메뉴로 이동
3. API 키 발급
4. `Settings`에서 다음 항목 입력
   - `ENABLE_CEREBRAS_FALLBACK` 체크
   - `CEREBRAS_API_KEY` 입력
   - `CEREBRAS_MODEL`은 기본값 `gpt-oss-120b` 권장

### 7-6) SEMANTIC_SCHOLAR_API_KEY 발급 (선택)
1. Semantic Scholar API 페이지: `https://www.semanticscholar.org/product/api`
2. 계정/키 발급 절차 진행
3. `Settings > SEMANTIC_SCHOLAR_API_KEY`에 입력
4. 키가 없어도 동작은 가능하지만, 키를 쓰면 호출 안정성이 좋아집니다.

## 8) 문제 해결
- 최초 실행 시 홈 대신 Setup Wizard가 뜨는 것이 정상입니다.
- 외부 접근 모드(`--host 0.0.0.0`)에서 실행이 거부되면
  `ALLOW_INSECURE_REMOTE_WEB=true` + `WEB_PASSWORD`를 확인하세요.
- `Send Now` 후 반응이 없으면 `Task Status` 패널의 상태/오류를 확인하세요.
- 메일이 안 오면 Gmail 인증 상태(앱 비밀번호 또는 OAuth 연결), 수신 주소, 스팸함을 먼저 확인하세요.
- OAuth 사용 중이면 `Settings > Google 연동 계정` 표시와 `연결 진단`의 `google_oauth_gmail` 결과를 확인하세요.
- `Keyword / Query 생성`이 실패하면 `GEMINI_API_KEY` 또는 `CEREBRAS_API_KEY` 설정과 인터넷 연결을 확인하세요.
- `Send Now`/`Run Dry-Run` 시 "검색 쿼리가 없습니다"가 뜨면 Topic Editor에서 쿼리를 생성/입력하고 저장하세요.
- 상세 오류 원인은 `Logs` 메뉴에서 확인하세요.
- 화면이 예전 버전처럼 보이면 실행 중인 `PaperDigestLocalUI.exe`를 모두 종료한 뒤 다시 실행하세요.
