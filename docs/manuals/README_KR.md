# Paper Morning

![Paper Morning Logo](../../assets/paper-morning-logo.png)

**Paper Morning**은 의료/AI 연구자를 위한 자동 논문 브리핑 도구입니다.  
프로젝트 맥락을 넣어두면, 매일(또는 3일/주간) 최신 논문을 모아 관련성 점수 기반으로 선별하고 메일로 전달합니다.

- 최신 기준 버전: **[v0.5.0](../../VERSION)**
- 라이선스: `GNU AGPLv3` (`LICENSE`)
- 개인정보/외부 전송 정책: `PRIVACY.md`

## 한 줄 요약
- 내가 정의한 연구 프로젝트 기준으로 논문을 자동 탐색
- LLM(Gemini, 필요 시 Cerebras 폴백)으로 관련성 평가 + 다국어 요약(`OUTPUT_LANGUAGE`)
- 스케줄 발송(매일 / 3일마다 / 주간)
- GitHub Actions 모드로 PC를 꺼도 자동 발송 가능

## 처음 사용자라면 여기부터
- [초보자용 단계별 가이드](./MANUAL_FIRSTTIME_KR.md)
- [운영/고급 설정 포함 전체 매뉴얼](./MANUAL_KR.md)

## 어떤 흐름으로 동작하나요?
1. Topic Editor에서 프로젝트와 쿼리를 저장합니다.
2. 소스(arXiv, PubMed, Semantic Scholar, Google Scholar-SerpAPI)에서 논문을 수집합니다.
3. LLM이 1~10점 관련성 점수를 매깁니다.
4. 임계값 이상 논문만 한국어 요약과 함께 메일로 전송합니다.

## 주요 기능
- 프로젝트 맥락 기반 LLM relevance ranking
- 관련도 점수 분포/통과 건수 진단 리포트
- 중복 발송 방지(`sent_ids.json`)
- PubMed 429 자동 재시도/백오프
- Google Scholar(SerpAPI) 선택 연동
- 발송 주기 옵션
  - `daily`
  - `every_3_days`
  - `weekly`
- 3일/주간 주기에서는 LLM 후보 상한(`LLM_MAX_CANDIDATES`)을 비선형 확장

## 빠른 시작 (로컬 UI)
1. 의존성 설치

```bash
pip install -r deps/requirements.txt
```

2. 웹 콘솔 실행

```bash
python app/web_app.py --host 127.0.0.1 --port 5050
```

또는

- Windows: `tools/start_web_console.bat`
- Linux/macOS: `./tools/start_web_console.sh`

3. 브라우저에서 접속

```text
http://127.0.0.1:5050
```

4. Setup Wizard / Settings에서 키 입력 후 Topic Editor에서 쿼리 저장

## GitHub Actions 모드 (권장)
로컬 PC를 24시간 켜두기 어렵다면 Actions 모드가 가장 편합니다.

### 필수 워크플로우
- 자동 발송: `../../.github/workflows/paper-morning-digest.yml`
- 초기 쿼리 자동생성: `../../.github/workflows/paper-morning-bootstrap-topics.yml`

### 필수 Secret
- `PM_ENV_FILE` : `.env` 전체 내용
- `PM_TOPICS_JSON` : `user_topics.json` 전체 내용

### 선택 Secret
- `PM_PROJECTS_JSON` : 프로젝트 목록만 담은 JSON (초기 쿼리 생성용)

### 스케줄
- 워크플로우 트리거는 매일 08:47 KST(= 23:47 UTC, 전날)
- 내부적으로 지연 완화를 위해 사용자가 지정한 시각보다 13분 먼저 트리거합니다.
- 실제 메일 발송은 `SEND_FREQUENCY` 정책(`daily/every_3_days/weekly`)에 따라 결정

## 핵심 설정값
`SEND_FREQUENCY` / `SEND_ANCHOR_DATE`
- 발송 주기 제어
- `SEND_ANCHOR_DATE`를 기준으로 3일/7일 주기 계산

`LOOKBACK_HOURS`
- 최근 몇 시간 이내 논문을 수집할지 설정
- 주기형 발송에서는 최소 주기 길이(예: weekly면 최소 168h)로 자동 보정

`LLM_MAX_CANDIDATES`
- 기본 후보 상한
- 3일/주간 주기에서는 토큰 폭증을 막기 위해 비선형 확장 적용

`ENABLE_GOOGLE_SCHOLAR` / `GOOGLE_SCHOLAR_API_KEY`
- Google Scholar 수집 활성화(SerpAPI 키 필요)

## 소스별 참고
- arXiv: 기본 제공
- PubMed: `NCBI_API_KEY` 넣으면 안정성 향상
- Semantic Scholar: API 키 권장
- Google Scholar: 공식 API가 아니라 SerpAPI 연동 방식

## 배포 파일 만들기
아래 명령은 **저장소 루트**에서 실행합니다.

### Windows
```powershell
.\tools\build_windows.ps1
```

### Linux
```bash
chmod +x tools/build_linux.sh
./tools/build_linux.sh
```

## 문제 해결 빠른 체크
- `검색 쿼리 없음`: Topic Editor에서 쿼리 생성 후 저장했는지 확인
- `PubMed 429`: 앱이 자동 재시도하지만, `NCBI_API_KEY` 설정 권장
- `Gemini 모델 404`: 모델명 확인 (`gemini-3.1-pro` 또는 `gemini-3.1-flash`)
- 메일 미수신: 발신/수신 주소, 스팸함, 인증 방식 확인

## 인증 방식 우선순위
1. **Gmail 앱 비밀번호 (현재 기본 권장)**
2. **Google OAuth (보류/실험)**

### Gmail 앱 비밀번호 안내
- 일반 계정 비밀번호가 아닙니다.
- 2단계 인증 활성화 후 16자리 앱 비밀번호를 사용해야 합니다.
- 발급 링크: https://myaccount.google.com/apppasswords

### Google OAuth 안내 (보류)
- 현재 공개 배포 기본 경로에서는 OAuth를 기본값으로 쓰지 않습니다.
- 안정화/운영정책 확정 전까지는 Gmail 앱 비밀번호 방식을 사용하세요.

## 문의
- `nineclas@gmail.com`
