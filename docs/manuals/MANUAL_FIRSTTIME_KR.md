# Paper Morning 초보자 매뉴얼 (Preview-First)

이 문서는 처음 사용하는 분을 위한 빠른 가이드입니다.
핵심 목표는 **자동화보다 먼저, 내 주제에 맞는 미리보기 결과를 바로 확인하는 것**입니다.

## 0) 5분 체크리스트
1. Gemini API Key 1개
2. Python 3.11+
3. 로컬에 이 저장소 코드
4. (선택) 나중에 Gmail/GitHub 계정

## 1) 먼저 성공해야 할 것
먼저 할 일:
- 프로젝트 설명 입력
- 검색 결과 1회 생성

나중에 할 일:
- 이메일 발송 설정
- GitHub Actions 자동화 설정

## 2) Gemini API Key 발급
1. Google AI Studio 접속
2. `Get API key` 클릭
3. 키 복사 및 보관

링크:
- https://aistudio.google.com/app/apikey

## 3) 첫 미리보기 생성 (로컬 권장)
1. 의존성 설치:

```bash
pip install -r deps/requirements.txt
```

2. 웹 콘솔 실행:

```bash
python app/web_app.py --host 127.0.0.1 --port 5050
```

3. 브라우저 열기:

```text
http://127.0.0.1:5050/setup
```

4. 필수 항목 입력:
- Onboarding mode: `Preview mode`
- 프로젝트 이름
- 프로젝트 컨텍스트(연구 맥락)
- 키워드(선택)
- Gemini API Key

5. `Save and Search Now` 클릭
6. Dashboard에서 확인:
- `Latest Preview Output`
- 상단 논문 카드/진단 정보
- 점수 분포(`9-10 / 7-8 / 5-6 / 1-4 / 0`)
- 스코어링 목록(`score | title`)으로 임계값 조정 가능

검색 결과 품질이 괜찮으면 아래 선택 단계를 진행하세요.

## 4) 선택: 이메일 발송 켜기 (미리보기 후)
`/setup`의 **Automation + email transport (advanced)** 를 열고 입력:
- `GMAIL_ADDRESS`
- `RECIPIENT_EMAIL`
- `GMAIL_APP_PASSWORD` (SMTP 모드)
- 타임존/발송 시각

Gmail 앱 비밀번호 안내:
- https://myaccount.google.com/apppasswords

## 5) 선택: GitHub Actions 자동화 켜기
### 5-1) 템플릿으로 내 저장소 만들기 (권장)
온보딩 기본 경로는 Fork보다 **Use this template** 입니다.

### 5-2) 워크플로우 활성화
내 저장소에서:
1. `Actions` 탭 클릭
2. (최초 1회) `I understand my workflows, go ahead and enable them` 클릭

### 5-3) Secret 등록
경로:
- `Repository > Settings > Secrets and variables > Actions > New repository secret`

필수:
1. `PM_ENV_FILE` (`.env` 전체 텍스트)

선택:
1. `PM_TOPICS_JSON` (`user_topics.json` 전체 텍스트)
2. `PM_PROJECTS_JSON` (bootstrap용 프로젝트 목록)

참고:
- 민감하지 않은 프로젝트 설정은 `config/projects.yaml` 파일로 관리 가능
- Preview-first 전환 후 `PM_TOPICS_JSON`는 필수가 아닙니다

### 5-4) 수동 첫 실행
1. `paper-morning-digest` 실행
2. `Run mode`를 `dry_run`으로 선택
3. 로그/미리보기 결과 확인
4. 이메일 설정 완료 후 `send_now` 1회 실행

## 6) private repo 비용 주의
- private 저장소는 GitHub Actions 무료 분(minute) 한도가 있습니다.
- 짧은 주기 스케줄은 월 한도를 빨리 소모할 수 있습니다.
- 시작은 local preview/local setup 경로를 권장합니다.

## 7) 자주 나는 오류
1. `Search query is empty`
- 원인: 토픽 쿼리가 아직 생성/저장되지 않음
- 해결: setup에서 preview 실행(자동 bootstrap) 또는 Topic Editor에서 생성/저장

2. `No LLM relevance reason generated`
- 원인: LLM 요약 비활성 또는 LLM 호출 실패
- 해결: `GEMINI_API_KEY`, 모델명, `ENABLE_LLM_AGENT=true` 확인

3. `Missing required env vars for email`
- 원인: 이메일 필드 미입력
- 해결: preview-only 단계에서는 정상, 이메일 발송을 켤 때만 입력

4. `PM_TOPICS_JSON is not valid JSON`
- 원인: JSON 형식 깨짐
- 해결: 따옴표(`"`), 쉼표(`,`), 괄호(`{}`, `[]`) 형식 확인

## 8) 문의
- nineclas@gmail.com
