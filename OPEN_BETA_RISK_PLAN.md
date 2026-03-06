# Paper-Morning 오픈 베타 배포 우려사항 및 보완 계획

> **전제**: 불특정 다수에게 공개 배포 (GitHub/웹사이트 등)  
> **현재 버전**: paper-morning v0.1.4  
> **작성일**: 2026-03-01

---

## 우려사항 전체 요약

| # | 카테고리 | 심각도 | 현재 상태 |
|---|----------|--------|-----------|
| 1 | 보안 — API 키 노출 위험 | 🔴 높음 | 로컬 `.env` 평문 저장 |
| 2 | 보안 — 웹 콘솔 인증 없음 | 🔴 높음 | 로컬 토큰만 있음, 외부 접근 시 무방비 |
| 3 | Gmail 계정 악용 가능성 | 🔴 높음 | 사용자 Gmail로 무제한 발송 가능 |
| 4 | 외부 API 비용 폭탄 | 🟠 중간 | Gemini 호출 횟수 상한 없음 |
| 5 | 설치·설정 허들 | 🟠 중간 | Gmail 앱 비밀번호, API 키 2~3개 발급 필요 |
| 6 | PC 상시 가동 의존 | 🟠 중간 | 절전/종료 시 발송 누락 |
| 7 | 중복 논문 반복 수신 | 🟡 낮음 | 발송 이력 없음 |
| 8 | arXiv/PubMed Rate Limit | 🟡 낮음 | 다수 배포 시 IP 공유 차단 가능 |
| 9 | 오류 피드백 부족 | 🟡 낮음 | 실패 시 사용자 대응 어려움 |
| 10 | 법적/저작권/개인정보 | 🟡 낮음 | 명시적 이용약관 없음 |

---

## 상세 분석 및 보완 계획

---

### 1. 🔴 보안 — API 키 평문 저장

**문제**
- `GMAIL_APP_PASSWORD`, `GEMINI_API_KEY`, `CEREBRAS_API_KEY` 등이 OS 파일시스템에 **평문 `.env`** 로 저장됨
- Windows: `%APPDATA%\paper-morning\.env`, Linux: `~/.config/paper-morning/.env`
- 악성 소프트웨어나 다른 프로세스가 해당 파일을 읽으면 즉시 노출

**보완 계획**

| 단계 | 방법 | 난이도 |
|------|------|--------|
| 즉시 | `GMAIL_APP_PASSWORD`를 단일 용도(이 앱 전용) 앱 비밀번호로 제한, 매뉴얼에 강조 | 낮음 |
| 단기 | Windows: `keyring` 라이브러리로 자격증명을 Windows Credential Manager에 저장 | 중간 |
| 단기 | Linux: `.env` 파일 권한을 `chmod 600`으로 강제 설정 | 낮음 |
| 장기 | 비밀값은 암호화 후 저장 (`cryptography` 라이브러리 + 기기별 salt) | 높음 |

```python
# 즉시 적용 가능한 파일 권한 강화 (bootstrap_runtime_files 내 추가)
import stat
env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # rw------- (600)
```

---

### 2. 🔴 보안 — 웹 콘솔 인증 부재

**문제**
- 현재 `X-App-Token` 은 **같은 프로세스 내 POST 요청만 보호**
- `--host 0.0.0.0` 또는 서버 배포 시 → 네트워크에서 접근 가능한 모든 사람이 Settings를 변경하거나 이메일을 발송할 수 있음
- 오픈 베타 사용자가 실수로 서버 배포 후 외부 노출 가능성 높음

**보완 계획**

| 단계 | 방법 |
|------|------|
| 즉시 | `--host` 기본값이 `127.0.0.1`임을 매뉴얼에 **경고 박스**로 명시 |
| 단기 | 최초 실행 시 브라우저에서 **비밀번호 설정 강제** (미설정 시 모든 기능 잠금) |
| 단기 | 로그인 페이지 추가: `WEB_PASSWORD` 환경변수로 설정, Flask session 기반 인증 |
| 장기 | `--host 0.0.0.0` 입력 시 비밀번호 미설정이면 시작 거부 |

```python
# web_app.py 시작부에 추가 가능한 최소 방어 로직
if args.host != "127.0.0.1" and not os.getenv("WEB_PASSWORD"):
    print("ERROR: --host을 127.0.0.1 외로 지정 시 WEB_PASSWORD 환경변수가 필요합니다.")
    sys.exit(1)
```

---

### 3. 🔴 Gmail 계정 악용 가능성

**문제**
- **Send Now** 버튼이 토큰 인증만 통과하면 횟수 제한 없이 호출 가능
- 악의적 사용자가 단시간에 수십 회 호출 → Gmail 하루 발송 한도 초과 → Google 계정 임시 잠금
- 앱 비밀번호는 Google 계정 전체에 영향을 미침

**보완 계획**

| 단계 | 방법 |
|------|------|
| 즉시 | `send_now` 잡에 **최소 재발송 대기 시간** 적용 (같은 날 1회 제한) |
| 단기 | 마지막 발송 타임스탬프를 상태 파일에 저장, 일정 시간 내 재호출 시 거부 |
| 매뉴얼 | Gmail 앱 비밀번호는 "이 앱 전용으로만 사용"하고, 필요 시 언제든지 구글에서 삭제 가능하다는 안내 추가 |

```python
# 간단한 발송 쿨다운 예시 (web_app.py 내 global 변수 활용)
import time
last_send_time = 0.0
SEND_COOLDOWN_SECONDS = 300  # 5분

def check_send_cooldown():
    global last_send_time
    elapsed = time.time() - last_send_time
    if elapsed < SEND_COOLDOWN_SECONDS:
        return False, f"{int(SEND_COOLDOWN_SECONDS - elapsed)}초 후 재시도 가능합니다."
    last_send_time = time.time()
    return True, ""
```

---

### 4. 🟠 외부 API 비용 폭탄

**문제**
- Gemini API는 현재 무료 티어가 있지만 **고사용량 배포 환경에서는 유료 전환** 가능
- `LLM_MAX_CANDIDATES=20`, `LLM_BATCH_SIZE=8` 기본값이 높게 설정되어 있어, 사용자가 실수로 큰 쿼리를 여러 번 실행하면 예상치 못한 비용 발생
- CEREBRAS 등 유료 API도 마찬가지

**보완 계획**

| 단계 | 방법 |
|------|------|
| 즉시 | 매뉴얼에 "Gemini 무료 티어 사용량 한도 확인" 링크 추가 |
| 단기 | `MAX_SEARCH_QUERIES_PER_SOURCE`와 `LLM_MAX_CANDIDATES`에 소프트 상한 경고 추가 (예: 설정값 > 30이면 UI 경고) |
| 단기 | Dry-Run 실행 시 예상 API 호출 수를 화면에 표시 |
| 장기 | 월간 API 호출량 로컬 집계 + 임계치 초과 시 경고 |

---

### 5. 🟠 설치·설정 허들 (UX 진입 장벽)

**문제**
- Gmail 앱 비밀번호 발급 (2단계 인증 선행 필요)
- Gemini API 키 발급
- (선택) NCBI, Cerebras 키까지 최대 4개 계정/키 필요
- 비개발자 대상 배포 시 이탈률 매우 높을 것

**보완 계획**

| 단계 | 방법 |
|------|------|
| 즉시 | 온보딩 마법사(`onboarding_wizard.py`)를 웹 UI에 통합: 처음 접속 시 단계별 Setup Wizard 페이지 표시 |
| 단기 | 각 키 입력란 옆에 "🔗 발급 방법" 버튼으로 공식 가이드 링크 |
| 단기 | 설정 없이도 **키워드 기반 폴백 모드**가 자동 동작함을 UI에서 명시 |
| 단기 | 최초 실행 시 **헬스체크 화면**: Gmail 연결 테스트, Gemini API 유효성 테스트를 버튼 하나로 수행 |
| 장기 | Gmail 대신 **SMTP 범용 지원** (Outlook, Naver, Daum 등) → Gmail 의존도 탈피 |

---

### 6. 🟠 PC 상시 가동 의존

**문제**
- 현재는 사용자 PC의 Python 프로세스가 살아있어야 스케줄링 동작
- 일반 사용자는 절전/종료로 인한 발송 누락을 자연스럽게 경험하게 됨
- "어제 논문 왜 안 왔어요?" 문의가 가장 빈번한 유형이 될 것

**보완 계획**

| 단계 | 방법 |
|------|------|
| 즉시 | 매뉴얼에 Windows 작업 스케줄러(`register_task.ps1`) 등록 방법을 1순위 안내 |
| 단기 | 앱 내에서 "Windows 작업 스케줄러 등록" 버튼 추가 (현재 `register_task.ps1` 스크립트를 UI에서 실행) |
| 단기 | macOS: `launchd` plist 자동 생성 지원 |
| 장기 | **서버리스 호스팅 가이드** 제공 (Railway, Render 등 무료 티어 서버에 1회 배포하는 방법 문서화) |

---

### 7. 🟡 중복 논문 반복 수신

**문제**
- 발송 이력이 없어서 동일 논문이 매일 반복 등장 가능 (특히 LOOKBACK_HOURS가 48 이상일 때)
- 사용자 불만의 주요 원인이 될 수 있음

**보완 계획**

| 단계 | 방법 |
|------|------|
| 단기 | 발송된 `paper_id` 목록을 로컬 JSON 파일에 저장 |
| 단기 | 다음 실행 시 이미 발송된 ID는 제외 (최근 7~30일치 보관) |
| 장기 | SQLite DB로 전환하여 이력 관리 + 웹 UI에서 "발송 이력 보기" 페이지 추가 |

```python
# 간단한 이력 관리 (sent_ids.json)
import json
from pathlib import Path

def load_sent_ids(path: Path) -> set:
    if path.exists():
        return set(json.loads(path.read_text()))
    return set()

def save_sent_ids(path: Path, ids: set):
    path.write_text(json.dumps(list(ids)))

# run_digest 내에서:
sent_path = data_dir / "sent_ids.json"
sent_ids  = load_sent_ids(sent_path)
papers    = [p for p in papers if p.paper_id not in sent_ids]
sent_ids.update(p.paper_id for p in final_papers)
save_sent_ids(sent_path, sent_ids)
```

---

### 8. 🟡 arXiv / PubMed Rate Limit

**문제**
- arXiv: `User-Agent` 헤더와 재시도 로직이 이미 구현되어 있음 (강점)
- PubMed: NCBI_API_KEY 없으면 IP당 초당 3회 제한 → 다수 사용자가 유사 시각 실행 시 차단 가능성
- 특히 기본값인 09:00에 모두 동시 실행하면 같은 IP대역(예: 기업망) 에서 차단될 수 있음

**보완 계획**

| 단계 | 방법 |
|------|------|
| 즉시 | NCBI API 키 발급을 설정 UI에서 적극 권장 (선택 → 권장으로 격상) |
| 단기 | 실행 시각에 ±3분 내 랜덤 지터(jitter) 추가하여 동시 호출 분산 |
| 매뉴얼 | arXiv 이용 정책 링크 포함, 존중 안내 |

```python
# 발송 시각 랜덤 지터 (scheduler 등록 시)
import random
jitter_seconds = random.randint(-180, 180)
actual_send_time = base_time + timedelta(seconds=jitter_seconds)
```

---

### 9. 🟡 오류 피드백 부족

**문제**
- 현재 오류 메시지가 `Task Status` 패널에 짧게 표시되고 사라짐
- 로그 파일이 없거나 사용자가 찾기 어려움
- 비개발자 사용자가 문제 해결에 막막함을 느낄 것

**보완 계획**

| 단계 | 방법 |
|------|------|
| 단기 | 로컬 로그 파일 자동 저장 (`data_dir/paper-morning.log`) 후 웹 UI에서 "로그 보기" 페이지 추가 |
| 단기 | 자주 발생하는 오류 코드 → 한국어 친화적 메시지 매핑 |
| 단기 | "설정 진단" 버튼: Gmail/Gemini 연결 테스트를 UI에서 1클릭으로 실행 |
| 장기 | GitHub Issues 링크를 Manual 페이지 하단에 추가 |

---

### 10. 🟡 법적 / 저작권 / 개인정보

**문제**
- 논문 초록을 LLM으로 요약하여 재배포 → arXiv 이용약관(CC 라이선스) 준수 여부 확인 필요
- PubMed 초록 사용: NLM 이용약관 확인 필요
- 사용자의 Gmail 인증정보, Gemini API 키를 본인 PC에 저장 — 앱이 이를 수집하지 않음을 명시해야 함
- 향후 클라우드 버전 전환 시 개인정보보호법(국내) / GDPR(해외) 고려 필요

**보완 계획**

| 단계 | 방법 |
|------|------|
| 즉시 | README 및 앱 내에 "이 앱은 사용자 데이터를 외부로 전송하지 않습니다" 명시 |
| 단기 | `LICENSE` 파일 추가 (MIT 또는 Apache 2.0 권장) |
| 단기 | `PRIVACY.md` 추가: 로컬 저장 항목, 외부 호출 대상(arXiv, PubMed, Google Gemini API) 명시 |
| 장기 | arXiv / NLM 이용약관 검토 후 요약 방식 적법성 확인 |

---

## 오픈 베타 전 필수 체크리스트

```
[ ] (1) 파일 권한 chmod 600 적용 (bootstrap 시 자동 설정)
[ ] (2) --host 0.0.0.0 시 비밀번호 강제 안내 추가
[ ] (3) Send Now 쿨다운 로직 적용
[ ] (4) 최초 실행 시 Setup Wizard 페이지 표시
[ ] (5) Windows 작업 스케줄러 등록 버튼 UI에 추가
[ ] (6) 중복 논문 필터 (sent_ids.json) 적용
[ ] (7) README에 프라이버시 안내 추가
[ ] (8) LICENSE 파일 추가
[ ] (9) NCBI_API_KEY를 "권장"으로 격상
[ ] (10) 로그 파일 로컬 저장 + 웹 UI 로그 뷰어
```

---

## 우선순위별 로드맵

```
🔴 오픈 베타 전 필수 (v0.2.0)
├── Send Now 쿨다운
├── --host 외부 접근 경고 및 비밀번호 옵션
├── 파일 권한 강화
└── README 프라이버시 / LICENSE 추가

🟠 오픈 베타 초기 (v0.2.x)
├── 웹 기반 Setup Wizard
├── 중복 논문 필터 (sent_ids.json)
├── 로그 뷰어 페이지
└── 작업 스케줄러 등록 버튼

🟡 오픈 베타 안정화 (v0.3.x)
├── keyring 기반 자격증명 저장
├── SMTP 범용화 (Gmail 외)
├── API 비용 경고 UI
└── 발송 이력 DB + 히스토리 뷰어
```
