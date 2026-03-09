# Paper-Morning v0.2.4 — 오픈 베타 재검사 및 쿼리 파이프라인 평가

> **검사 대상**: v0.2.4 (2026-03-03)  
> **이전 검사**: v0.1.4 (2026-03-01, `OPEN_BETA_RISK_PLAN.md`)

---

## Part 1: 오픈 베타 우려사항 재검사

### 해결 현황 요약

| # | 항목 | 이전 | v0.2.4 현재 | 판정 |
|---|------|------|-------------|------|
| 1 | API 키 평문 저장 | 🔴 미대응 | 🟢 `enforce_private_file_permissions()` 적용. Windows: `S_IREAD\|S_IWRITE`, Linux: `600` | **해결** |
| 2 | 웹 콘솔 인증 없음 | 🔴 미대응 | 🟢 `ensure_host_security()` + `WEB_PASSWORD` + 로그인 페이지 (`/login`) | **해결** |
| 3 | Gmail 무제한 발송 | 🔴 미대응 | 🟢 `check_send_cooldown()` + `SEND_NOW_COOLDOWN_SECONDS=300` | **해결** |
| 4 | API 비용 폭탄 | 🟠 미대응 | 🟡 `build_settings_warnings()`로 고위험 값 경고. Dry-Run에 LLM 호출 수 상한 표시. 월간 집계는 미구현 | **부분 해결** |
| 5 | 설치 허들 | 🟠 미대응 | 🟢 웹 Setup Wizard (`/setup`) + Gmail/Gemini/Cerebras 1클릭 헬스체크 | **해결** |
| 6 | PC 상시 의존 | 🟠 미대응 | 🟡 `register_windows_scheduled_task()` Home UI에서 실행 가능. macOS/Linux 미지원 | **부분 해결** |
| 7 | 중복 논문 반복 | 🟡 미대응 | 🟢 `filter_already_sent_papers()` + `sent_ids.json` (기본 14일) | **해결** |
| 8 | Rate Limit | 🟡 기존 대응 | 🟡 arXiv retry/backoff 유지. 실행 시각 지터(jitter)는 미구현 | **이전과 동일** |
| 9 | 오류 피드백 | 🟡 미대응 | 🟡 Setup Wizard에 헬스체크 있음. 전용 로그 뷰어 페이지는 미구현 | **부분 해결** |
| 10 | 법적/프라이버시 | 🟡 미대응 | 🔴 `LICENSE`, `PRIVACY.md` 파일 아직 없음 | **미해결** |

### 잔여 조치 항목 (우선순위순)

| 우선순위 | 항목 | 내용 |
|----------|------|------|
| 🔴 필수 | `LICENSE` 파일 추가 | MIT 또는 Apache 2.0. 라이선스 없으면 GitHub 공개 시 법적 모호성 |
| 🔴 필수 | `PRIVACY.md` 추가 | "데이터 외부 전송 없음" + 호출 대상(arXiv, PubMed, Google/Cerebras API) 명시 |
| 🟠 권장 | 발송 시각 지터 | 다수 사용자 동시 실행 시 arXiv/PubMed rate-limit 리스크 분산 |
| 🟠 권장 | 로그 파일 저장 + 뷰어 | `paper-morning.log` 자동 저장 → 웹 UI `/logs` 페이지 |
| 🟡 개선 | macOS `launchd` 등록 | Linux `cron`/`systemd` 가이드도 함께 |
| 🟡 개선 | API 월간 사용량 집계 | 로컬 카운터로 월간 LLM 호출 횟수 추적 |

---

## Part 2: 쿼리 파이프라인 평가

### 현재 파이프라인 흐름도

```
사용자 프로젝트(projects) 입력
         │
         ▼
Topic Editor → "Keyword / Query 생성" 클릭
         │
         ▼ (Gemini/Cerebras LLM 호출)
토픽 초안 생성 (name, keywords, arxiv_query, pubmed_query)
         │
         ▼ 사용자 수동 수정 가능
user_topics.json 에 저장
         │
         ▼ 매일 발송 시각 (스케줄러 또는 수동)
load_topic_configuration() ─── 저장된 쿼리만 그대로 읽음
         │
    ┌────┴────┐
    ▼         ▼
arXiv API   PubMed API  ← 정적 쿼리 문자열 전달
    │         │
    └────┬────┘
         ▼
    중복 제거 + 시간 필터 (since_utc)
         │
         ▼
prefilter_candidates_for_llm()  ← 키워드 점수로 상위 N개 선별
         │
         ▼
annotate_papers_with_llm()  ← LLM이 논문별 관련성 1~10 평가
         │
         ▼
filter_already_sent_papers()  ← sent_ids.json 중복 제거
         │
         ▼
compose_email_html() → 메일 발송
```

### 서비스 컨셉 관점에서의 평가

#### ✅ 잘 된 부분

| 항목 | 평가 |
|------|------|
| **LLM 2단계 구조** | 1차 키워드 사전필터 → 2차 LLM 정밀 평가. API 비용과 정확도의 균형이 좋음 |
| **쿼리 사용자 관리 (v0.2.4)** | 실행 때마다 LLM으로 쿼리를 새로 만들면 일관성 저하. 매번 같은 쿼리로 탐색하는 것이 "매일 정해진 관심사 모니터링" 컨셉에 맞음 |
| **Gemini→Cerebras 폴백** | LLM 한 곳이 장애나도 서비스 중단 안 됨. 무료 전용 사용자에게 중요 |
| **중복 필터** | 14일 이력으로 같은 논문 반복 방지. 서비스 필수 기능을 갖춤 |
| **빈 쿼리 가드** | 쿼리 없으면 실행 자체를 막아서 "0건 리포트" 혼란 방지 |

#### ⚠️ 우려/한계점

**1. 쿼리 노후화(Query Stale) 문제**

```
문제: 사용자가 최초 1회 쿼리를 생성하면, 연구 방향이 바뀌어도
      쿼리는 영원히 그대로 남음. 서비스 특성상 사용자의 관심사는
      시간이 지나면 변화하는데, 쿼리 갱신을 상기시키는 장치가 없음.
```

> **보완안**: 쿼리 생성 날짜를 `user_topics.json`에 기록하고, 30일 이상 경과 시 Home 대시보드에 "🔄 쿼리 점검을 권장합니다 (마지막 갱신: XX일 전)" 배너 표시

**2. arXiv 쿼리 문법 의존성**

```
현재: 쿼리 문자열이 arXiv OAI-PMH의 all: / ti: / abs: 문법에 직접 의존
예시: "(all:fundus OR all:retina) AND (all:stroke OR all:CAC)"

문제:
- 일반 사용자가 이 문법을 이해하기 어려움
- "Topic Editor"에서 수동 수정 시 문법 오류 → 0건 결과 → 원인 파악 난해
- PubMed Boolean 쿼리도 마찬가지
```

> **보완안 A (즉시)**: 쿼리 입력란에 "arXiv 쿼리 문법 도움말" 링크 + 예시 tooltip 추가
> **보완안 B (중기)**: "테스트 검색" 버튼 — 쿼리를 실제 arXiv/PubMed에 1회 실행하여 결과 수를 미리 확인

**3. 단일 소스 의존 (arXiv + PubMed만)**

```
서비스 컨셉: "사용자 맞춤형 논문을 자동으로 쏴준다"

한계:
- 의료 AI 분야에서 중요한 소스인 IEEE, MICCAI proceedings,
  bioRxiv, medRxiv 등이 빠져 있음
- CS 분야 중심 사용자에겐 arXiv가 충분하지만,
  임상/의료 쪽은 PubMed만으론 최신 프리프린트를 놓칠 수 있음
```

> **보완안**: 장기적으로 Semantic Scholar API (무료, 통합 검색) 추가 고려. 단기적으로는 현행 2소스로 충분하나, 소스 확장 가능 구조를 README에 언급

**4. LOOKBACK_HOURS의 구조적 맹점**

```
현재: LOOKBACK_HOURS=24 → 최근 24시간 내 게재된 논문만 수집
      PC가 주말에 꺼져있으면 금~일 논문을 놓침

문제:
- 사용자가 2~3일 쉬면 그 기간 논문이 영구 누락
- "매일 보내준다"는 서비스 약속과 "놓치면 영영 안 옴"이 충돌
```

> **보완안 A (즉시)**: 마지막 성공 발송 시각을 저장하고, 다음 실행 시 `since_utc = max(last_success, now - LOOKBACK_HOURS)` 로 계산. 주말 누락분 자동 보충
> **보완안 B**: `LOOKBACK_HOURS`를 서비스 내부적으로 72시간 이상으로 높이되, 중복 필터(`sent_ids.json`)가 이미 있으므로 재발송은 자동 방지

**5. LLM 프롬프트의 프로젝트 컨텍스트 길이 제한 없음**

```
현재: build_project_context_text()가 projects 전체를 프롬프트에 삽입
      사용자가 프로젝트를 10개 이상 + context를 길게 쓰면
      프롬프트 토큰 초과 → API 에러 또는 비용 급증
```

> **보완안**: 프로젝트 컨텍스트 합산 길이 제한 (예: 3000자) + 초과 시 경고

**6. PubMed에서 초록 없는 논문 처리**

```
현재: fetch_pubmed_abstracts()에서 초록을 별도 API로 가져옴
      초록이 없는 논문(conference abstract 등)은 abstract=""
      → LLM이 title만으로 평가 → 부정확한 점수

실제 비율: PubMed 검색 결과의 ~15-25%가 초록 없음
```

> **보완안**: `abstract`가 빈 논문은 LLM 평가에서 제외하거나, 프롬프트에 "abstract가 없는 논문은 낮은 점수를 부여하라" 가이드 추가

### 쿼리 파이프라인 개선 로드맵

```
즉시 (v0.2.5)
├── LOOKBACK 보충 로직 (마지막 성공 시각 기반)
├── 쿼리 생성 날짜 기록 + 노후 쿼리 경고 배너
└── arXiv/PubMed 쿼리 문법 도움말 tooltip

단기 (v0.3.x)
├── "테스트 검색" 버튼 (쿼리 결과 수 미리 확인)
├── 프로젝트 컨텍스트 길이 제한 + 경고
└── 초록 없는 논문 처리 정책

장기 (v1.x)
├── Semantic Scholar / bioRxiv 등 소스 추가
├── 사용자 피드백 루프: 받은 논문에 👍/👎 → 쿼리 자동 튜닝
└── 쿼리 자동 리프레시 제안 (월 1회 LLM으로 기존 쿼리 개선안 생성)
```
