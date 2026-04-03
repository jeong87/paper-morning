# Paper Morning

[![Paper Morning Logo](../../assets/papermorning2.png)](https://raw.githack.com/jeong87/paper-morning/main/docs/preview/index_ko.html)

**[EN](../../README.md) | [KR](README_KR.md)**

Paper Morning은 의료/헬스케어 AI 연구를 위한 `연구 컨텍스트 기반 논문 검색 엔진`입니다.
프로젝트 설명을 입력하면 검색식을 만들고, 실제 논문 후보를 모은 뒤, 어떤 논문이 왜 더 맞는지까지 다시 정리해줍니다.

- 최신 버전: **[v0.7.1](../../VERSION)**
- 라이선스: `GNU AGPLv3` ([LICENSE](../../LICENSE))
- 개인정보/외부 전송 정책: [PRIVACY.md](../../PRIVACY.md)

## Try Live Web Preview (No Download)
GitHub에서 먼저 제품이 무엇을 하는지 확인하고 싶다면:

- <a href="https://raw.githack.com/jeong87/paper-morning/main/docs/preview/index_ko.html">라이브 웹 프리뷰 열기</a>

이 페이지에서 일어나는 일:
- 페이지 자체에서 Paper Morning이 무엇을 하는지 먼저 설명합니다
- 연구 컨텍스트, 검색 모드, Gemini API key를 입력합니다
- 컨텍스트에서 검색식을 생성합니다
- 선택한 모드와 기간에 맞춰 arXiv, PubMed에서 실제 후보 논문을 가져옵니다
- Gemini로 후보를 다시 평가하고 요약합니다
- 결과를 새 브라우저 탭 HTML로 보여줍니다

참고:
- 전부 브라우저 안에서 실행됩니다
- 이 페이지에서는 실제 이메일이 발송되지 않습니다
- 설치 전에 첫인상을 확인하는 용도로 가장 적합합니다

## 현재 제품 방향
이제 Paper Morning의 중심은 `매일 논문을 보내주는 앱`이 아닙니다.

현재 핵심은 두 가지입니다.
- 사람이 필요할 때 직접 들어와서 쓰는 온디맨드 논문 검색 도구
- 로컬 에이전트가 JSON으로 호출할 수 있는 논문 검색 도구

예전의 digest, 이메일, 자동화 기능은 그대로 남아 있지만 이제는 `옵션 기능`입니다.

## 2-1 사람용 검색
사람이 필요할 때 직접 들어와서 관련 논문을 찾는 경로입니다.

지원하는 것:
- `What's New`: 최신 논문 우선
- `Best Match`: 선택한 기간 안에서 가장 잘 맞는 논문 우선
- `Discovery`: 인접하지만 전이 가능한 방법론까지 포함
- `7d`부터 `5y`까지 기간 선택
- 로컬 인박스 저장과 브라우저 기반 결과 열람

잘 맞는 사용자:
- 새 연구 방향을 빠르게 훑고 싶은 연구자
- 단순 최신순보다 내 주제에 맞는 논문을 보고 싶은 사용자
- 이메일 설정 없이 먼저 품질을 확인하고 싶은 사용자

## 2-2 에이전트용 검색
Paper Morning을 로컬 연구 에이전트용 논문 검색 툴로 쓰는 경로입니다.

지원하는 것:
- 로컬 HTTP JSON endpoint: `POST /api/agent/search`
- CLI JSON 모드: `python app/paper_digest_app.py --agent-search ...`
- `AGENT_API_TOKEN` 기반 로컬 broker 인증
- Gemini 또는 로컬/자체호스팅 OPENAI-compatible backend

보안 모델:
- 에이전트는 `AGENT_API_TOKEN`만 받습니다
- `GEMINI_API_KEY`나 로컬 LLM provider key는 Paper Morning 백엔드만 봅니다
- 에이전트는 raw provider key를 알 필요가 없습니다

잘 맞는 사용자:
- literature review agent
- 연구 스카우팅/기획 agent
- 구조화된 논문 검색 결과가 필요한 로컬 툴 파이프라인

## 내부 동작 방식
사람용 경로와 에이전트용 경로는 같은 검색 엔진을 공유합니다.

1. 연구 컨텍스트를 읽습니다
2. 소스별 검색식을 생성합니다
3. arXiv, PubMed, Semantic Scholar, 선택적으로 Google Scholar에서 후보를 모읍니다
4. 검색 모드와 기간에 맞춰 후보를 거릅니다
5. shortlist를 만듭니다
6. shortlist 전체를 한 번에 보는 listwise LLM rerank를 수행합니다
7. 결과를 사람에게는 HTML로, 에이전트에게는 JSON으로 돌려줍니다

## 어디서 시작하면 되나
- 프리뷰부터 보기: [라이브 웹 프리뷰](https://raw.githack.com/jeong87/paper-morning/main/docs/preview/index_ko.html)
- 사람용 로컬 사용: [MANUAL_FIRSTTIME_KR.md](./MANUAL_FIRSTTIME_KR.md)
- 에이전트/툴 연동: [MANUAL_AGENT_KR.md](./MANUAL_AGENT_KR.md)
- English README: [../../README.md](../../README.md)

## 옵션 기능
아래 기능들은 아직 지원하지만, 더 이상 제품의 첫 설명 영역은 아닙니다.

### 로컬 설치와 로컬 UI
실제로 로컬에서 쓰고 싶다면:

```bash
pip install -r deps/requirements.txt
python app/local_ui_launcher.py
```

로컬 UI:

```text
http://127.0.0.1:5050
```

### 로컬 인박스와 아침 팝업
앱을 켜둔 상태라면, 예약된 시간에 기본 검색 결과를 자동으로 띄우게 할 수 있습니다.

관련 설정:
- `DELIVERY_MODE=local_inbox`
- `AUTO_OPEN_DIGEST_WINDOW=true`
- `SEARCH_INTENT_DEFAULT`
- `SEARCH_TIME_HORIZON_DEFAULT`

### 이메일 발송
이메일은 이제 기본 경로가 아니라 선택 기능입니다.

우선순위:
1. Local Inbox
2. Gmail OAuth
3. Gmail App Password

관련 문서:
- Gmail app password: https://myaccount.google.com/apppasswords
- 전체 운영 매뉴얼: [MANUAL_KR.md](./MANUAL_KR.md)

### GitHub Actions 자동화
로컬 PC를 켜두지 않고 자동 실행하고 싶을 때만 쓰는 고급 경로입니다.

필수 workflow:
- `.github/workflows/paper-morning-digest.yml`
- `.github/workflows/paper-morning-bootstrap-topics.yml`

필수 secret:
- `PM_ENV_FILE`

선택 secret:
- `PM_TOPICS_JSON`
- `PM_PROJECTS_JSON`

비밀이 아닌 추적 설정:
- `config/projects.yaml`

## 중요한 설정들
- `SEARCH_INTENT_DEFAULT`: 기본 검색 모드
- `SEARCH_TIME_HORIZON_DEFAULT`: 기본 검색 기간
- `LLM_MAX_CANDIDATES`: listwise rerank shortlist 상한
- `OUTPUT_LANGUAGE`: LLM 설명 텍스트 언어
- `AGENT_API_TOKEN`: agent mode용 로컬 broker token
- `ENABLE_OPENAI_COMPAT_FALLBACK`: LM Studio, vLLM 등 OpenAI-style local backend 사용 여부
- `ENABLE_GOOGLE_SCHOLAR` + `GOOGLE_SCHOLAR_API_KEY`: 선택적 SerpAPI source

## 배포 파일 만들기
### Windows
```powershell
.\tools\build_windows.ps1
```

### Linux
```bash
chmod +x tools/build_linux.sh
./tools/build_linux.sh
```

## Demo Pages 배포
이 저장소에는 다음이 포함되어 있습니다.
- demo 생성 스크립트: `scripts/generate_demo_html.py`
- pages workflow: `.github/workflows/deploy-demo-pages.yml`

fork에서 공개 demo를 배포하려면:
1. GitHub Pages source를 **GitHub Actions**로 설정
2. `deploy-demo-pages` workflow 실행 또는 `main`에 push

## 템플릿 기반 저장소 시작
온보딩 용도로는 다음을 권장합니다.
- `Use this template` -> 새 저장소 생성

fallback:
- upstream fork 연결이 꼭 필요할 때만 fork

## Actions 비용 메모
- private repo의 GitHub Actions는 무료 시간이 제한적입니다
- 자주 자동화를 돌리면 금방 무료 구간을 넘길 수 있습니다
- 기본 경로는 여전히 local-first 검색과 로컬 스케줄링입니다

## 빠른 문제 해결
- `Search query is empty`: Topic Editor에서 query를 생성하고 저장하세요
- `PubMed 429`: 자동 재시도는 들어가 있지만 `NCBI_API_KEY` 추가를 권장합니다
- `Gemini model 404 / quota`: 프리뷰와 런타임 모두 여러 Gemini fallback을 먼저 시도합니다
- Agent `403 Forbidden`: `AGENT_API_TOKEN`과 로컬 요청 여부를 확인하세요
- 이메일이 오지 않음: sender/recipient 주소, 스팸함, 인증 설정을 확인하세요

## 문서
- 초보자 가이드: [MANUAL_FIRSTTIME_KR.md](./MANUAL_FIRSTTIME_KR.md)
- 전체 운영/자동화: [MANUAL_KR.md](./MANUAL_KR.md)
- 에이전트/툴 연동: [MANUAL_AGENT_KR.md](./MANUAL_AGENT_KR.md)
- scoring policy: [SCORING_POLICY_KR.md](./SCORING_POLICY_KR.md)
- Beginner (English): [MANUAL_FIRSTTIME_EN.md](./MANUAL_FIRSTTIME_EN.md)
- Full operations (English): [MANUAL_EN.md](./MANUAL_EN.md)
- Agent/tool integration (English): [MANUAL_AGENT_EN.md](./MANUAL_AGENT_EN.md)
- Scoring policy (English): [SCORING_POLICY_EN.md](./SCORING_POLICY_EN.md)
- English README: [../../README.md](../../README.md)

## 문의
- `nineclas@gmail.com`
