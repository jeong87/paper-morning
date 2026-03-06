# Paper Morning 매뉴얼 (GitHub Actions 운영판)

문서 대상:
- "내 PC를 24시간 켜두지 않고" 매일 자동 발송을 받고 싶은 사용자
- Ubuntu / Windows / macOS 러너에서 수동 테스트도 하고 싶은 사용자

현재 문서는 **GitHub Actions 기준 운영 매뉴얼**입니다.
기존 로컬 실행 중심 매뉴얼은 아래 백업 파일에 보존되어 있습니다.
- `MANUAL_KR_LOCAL_LEGACY_v033.md`

## 1) 이 버전의 핵심
- 매일 아침 9시(KST)에 GitHub 서버에서 자동 실행
- 내 PC 전원 상태와 무관하게 동작
- 수동 실행 시 러너 OS 선택 가능
  - `ubuntu-latest`
  - `windows-latest`
  - `macos-latest`
- 실행 모드 선택 가능
  - `send_now`: 실제 메일 발송
  - `dry_run`: 메일 없이 수집/평가만 실행

## 2) 동작 구조
1. GitHub Actions가 스케줄 또는 수동 트리거로 실행됩니다.
2. Repository Secret에 저장된 설정(`PM_ENV_FILE`)과 주제/쿼리(`PM_TOPICS_JSON`)를 런타임 파일로 복원합니다.
3. `paper_digest_app.py --run-once`를 실행합니다.
4. 결과 로그는 Actions 실행 로그 + Artifact로 확인합니다.

워크플로우 파일:
- `.github/workflows/paper-morning-digest.yml`

## 3) 최초 설정 (중요)

### 3-1) 저장소 준비
1. GitHub에 이 프로젝트를 올리거나(또는 fork) 기본 브랜치(`main`)를 준비합니다.
2. Actions 탭이 활성화되어 있는지 확인합니다.

### 3-2) Repository Secret 2개 등록
경로:
- `GitHub 저장소 > Settings > Secrets and variables > Actions > New repository secret`

필수 Secret:
1. `PM_ENV_FILE`
2. `PM_TOPICS_JSON`

#### A) PM_ENV_FILE 예시
아래를 기반으로 본인 값으로 바꿔서 그대로 저장하세요.

```env
# Mail
GMAIL_ADDRESS=your_sender@gmail.com
RECIPIENT_EMAIL=your_receiver@gmail.com
GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx

# Schedule / Time
TIMEZONE=Asia/Seoul
SEND_HOUR=9
SEND_MINUTE=0
RECENT_HOURS=24

# Search / Selection
MAX_PAPERS=5
MAX_SEARCH_QUERIES_PER_SOURCE=4
ARXIV_MAX_RESULTS_PER_QUERY=25
PUBMED_MAX_IDS_PER_QUERY=25
ENABLE_SEMANTIC_SCHOLAR=true
SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY=20

# LLM
ENABLE_LLM_AGENT=true
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.1-flash
ENABLE_GEMINI_ADVANCED_REASONING=true
LLM_BATCH_SIZE=5
LLM_MAX_CANDIDATES=30
LLM_RELEVANCE_THRESHOLD=7

# Fallback (optional)
ENABLE_CEREBRAS_FALLBACK=true
CEREBRAS_API_KEY=your_cerebras_api_key
CEREBRAS_MODEL=gpt-oss-120b

# Optional keys
NCBI_API_KEY=
SEMANTIC_SCHOLAR_API_KEY=
```

주의:
- `GMAIL_APP_PASSWORD`는 Gmail 웹 비밀번호가 아닙니다.
- 2단계 인증 활성화 후 생성한 16자리 앱 비밀번호를 넣어야 합니다.
- 발급 링크: `https://myaccount.google.com/apppasswords`

#### B) PM_TOPICS_JSON 예시

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
    },
    {
      "name": "내시경 동영상 foundation 모델 학습",
      "context": "Endoscopy video foundation model pretraining and adaptation"
    },
    {
      "name": "CCTV 손씻기 탐지",
      "context": "Hospital infection prevention by hand hygiene detection from CCTV"
    }
  ],
  "topics": [
    {
      "name": "Fundus + Stroke",
      "keywords": ["fundus", "retina", "stroke", "deep learning"],
      "arxiv_query": "(all:fundus OR all:retina) AND (all:stroke) AND (all:deep learning)",
      "pubmed_query": "(fundus OR retina) AND stroke AND (deep learning)",
      "semantic_scholar_query": "fundus retina stroke deep learning risk prediction"
    }
  ]
}
```

주의:
- `topics`가 비어 있으면 실행 시 "검색 쿼리 없음"으로 실패합니다.
- 쿼리는 "프로젝트 변경 시에만" 갱신하고, 일일 실행에서는 저장된 쿼리를 그대로 사용합니다.

## 4) 자동 실행 (매일 9시)
스케줄은 워크플로우에 이미 설정되어 있습니다.
- `cron: "0 0 * * *"` = 매일 00:00 UTC = 한국시간 09:00

동작 조건:
- 기본 브랜치에 워크플로우 파일이 존재
- `PM_ENV_FILE`, `PM_TOPICS_JSON` 두 Secret이 정상 등록
- Gmail/LLM 키가 유효

## 5) 수동 실행 (OS/모드 선택)
1. `Actions` 탭으로 이동
2. `paper-morning-digest` 워크플로우 선택
3. `Run workflow` 클릭
4. 옵션 선택
   - `Runner OS`: ubuntu / windows / macos
   - `Run mode`: `send_now` 또는 `dry_run`
5. 실행 로그에서 진행 상태 확인

권장 테스트 순서:
1. `dry_run` + `ubuntu-latest`
2. `send_now` + `ubuntu-latest`
3. 필요 시 `windows-latest`, `macos-latest` 호환 테스트

## 6) 결과 확인
- 실행 로그: Actions 각 Step 콘솔
- Artifact: `paper-morning-logs-*`
  - `ci_runtime/data/`가 업로드됩니다.
  - 실패 원인 분석 시 Artifact 로그를 우선 확인하세요.

## 7) 설정 변경 방법
일반적으로 파일 커밋 없이 Secret만 바꿔서 운영합니다.

1. 주제/쿼리 변경
- `PM_TOPICS_JSON` 수정

2. 키/메일/임계값 변경
- `PM_ENV_FILE` 수정

3. 실행 즉시 반영 테스트
- Actions에서 `Run workflow` 수동 실행

## 8) 보안 운영 권장
- Secret은 절대 코드/README/이슈에 평문으로 올리지 마세요.
- 개인 테스트 외 저장소는 private 권장
- 최소 권한으로 repo collaborator 관리
- 정기적으로 앱 비밀번호/API 키 회전

## 9) 자주 발생하는 오류

1. `535 Username and Password not accepted`
- Gmail 주소와 앱 비밀번호 계정이 서로 다른 경우
- 앱 비밀번호 대신 일반 비밀번호를 입력한 경우
- 해결: 같은 계정 쌍으로 재발급/재입력

2. `PM_TOPICS_JSON is not valid JSON`
- JSON 문법 오류(쉼표, 따옴표, 괄호)
- 해결: JSON validator로 확인 후 다시 저장

3. `Not Found ... gemini-...:generateContent`
- 존재하지 않는 모델명 사용
- 해결: `GEMINI_MODEL` 값을 지원 모델명으로 수정

4. "관련 논문 없음"이 반복
- `RECENT_HOURS`가 너무 짧거나 쿼리가 과도하게 좁음
- 해결: 시간창 확대(예: 120), 쿼리 완화, threshold 점검

## 10) Linux/Windows/macOS 관련 안내
- 실행 환경은 GitHub 러너이므로 로컬 OS 준비가 필요 없습니다.
- 수동 실행에서 러너 OS를 바꿔 동일 워크플로우를 검증할 수 있습니다.
- 실제 "매일 자동 발송"은 기본적으로 스케줄 잡힌 Ubuntu job이 담당합니다.

## 11) 문의
- 기능/오류 문의: `nineclas@gmail.com`
