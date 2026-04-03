# Paper Morning 에이전트 연동 매뉴얼

대상:
- 로컬 연구용 에이전트
- 툴 호출 스크립트
- Paper Morning을 다른 워크플로우에 붙이려는 개발자

이 문서는 Paper Morning을 `에이전트용 논문 검색 툴`로 사용할 때의 설정과 호출 방법을 설명합니다.

같이 보면 좋은 문서:
- `SCORING_POLICY_KR.md`

## 1. 보안 모델
에이전트에게 직접 넘기면 안 되는 값:
- `GEMINI_API_KEY`
- `OPENAI_COMPAT_API_KEY`
- `CEREBRAS_API_KEY`

에이전트에게 넘겨도 되는 값:
- `AGENT_API_TOKEN`

흐름:
1. 에이전트가 로컬 Paper Morning에 요청
2. Paper Morning이 `.env` 또는 OS keyring에서 provider 자격증명을 읽음
3. Paper Morning이 검색식 생성, 논문 수집, 재랭킹 수행
4. Paper Morning이 구조화된 JSON 반환

현재 경계:
- HTTP endpoint는 로컬에서만 열림
- loopback이 아닌 요청은 차단됨
- 브라우저 UI 토큰과 에이전트 토큰은 분리됨

## 2. 지원하는 백엔드 방식

### 옵션 A. Gemini 사용
```env
ENABLE_LLM_AGENT=true
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.1-flash
AGENT_API_TOKEN=your_local_broker_token
```

### 옵션 B. 로컬 OPENAI-compatible 서버 사용
예:
- LM Studio
- vLLM
- OpenAI-compatible Ollama bridge

```env
ENABLE_OPENAI_COMPAT_FALLBACK=true
OPENAI_COMPAT_API_BASE=http://127.0.0.1:1234/v1
OPENAI_COMPAT_MODEL=qwen2.5-14b-instruct
OPENAI_COMPAT_API_KEY=
AGENT_API_TOKEN=your_local_broker_token
```

참고:
- 로컬 서버가 bearer auth를 요구하지 않으면 `OPENAI_COMPAT_API_KEY`는 비워도 됩니다.
- 현재는 Gemini가 설정되어 있으면 Gemini를 먼저 시도하고, 실패 시 OPENAI-compatible backend, 그 다음 Cerebras fallback 순서로 갑니다.

## 3. HTTP agent endpoint

Endpoint:
```text
POST http://127.0.0.1:5050/api/agent/search
```

헤더:
```text
Authorization: Bearer <AGENT_API_TOKEN>
Content-Type: application/json
```

대체 헤더:
```text
X-Agent-Token: <AGENT_API_TOKEN>
```

### 최소 요청 예시
```json
{
  "research_context": "망막 triage용 foundation model 관련 논문을 찾아줘",
  "search_intent": "best_match",
  "time_horizon": "1y",
  "top_k": 5
}
```

### 확장 요청 예시
```json
{
  "project_name": "Retina triage foundation model",
  "research_context": "우리는 적은 라벨 환경에서 retinal screening과 triage를 위한 foundation model을 만들고 있다.",
  "keywords": ["retina", "triage", "foundation model", "screening"],
  "search_intent": "discovery",
  "time_horizon": "3y",
  "top_k": 10,
  "output_language": "ko",
  "include_diagnostics": true,
  "source_policy": {
    "arxiv": true,
    "pubmed": true,
    "semantic_scholar": true,
    "google_scholar": false
  }
}
```

### cURL 예시
```bash
curl -X POST http://127.0.0.1:5050/api/agent/search \
  -H "Authorization: Bearer your_local_broker_token" \
  -H "Content-Type: application/json" \
  -d '{
    "research_context": "multimodal ICU foundation model 관련 최근 논문을 찾아줘",
    "search_intent": "whats_new",
    "time_horizon": "30d",
    "top_k": 5
  }'
```

## 4. CLI 모드
HTTP 없이 stdout JSON만 받고 싶다면 CLI 모드를 쓰면 됩니다.

### 최소 예시
```bash
python app/paper_digest_app.py \
  --agent-search \
  --research-context "multimodal ICU foundation model 관련 논문을 찾아줘" \
  --search-intent best_match \
  --time-horizon 1y \
  --top-k 5 \
  --pretty-json
```

### request file 예시
`request.json`
```json
{
  "project_name": "ICU multimodal model",
  "research_context": "multimodal ICU representation learning과 prognosis에 잘 맞는 논문을 찾아줘.",
  "keywords": ["ICU", "multimodal", "representation learning", "prognosis"],
  "search_intent": "best_match",
  "time_horizon": "3y",
  "top_k": 8,
  "include_diagnostics": true
}
```

실행:
```bash
python app/paper_digest_app.py --agent-search --agent-request-file request.json --pretty-json
```

stdin 사용:
```bash
cat request.json | python app/paper_digest_app.py --agent-search --agent-request-file - --pretty-json
```

## 5. 응답 구조
최상위 필드:
- `status`
- `request`
- `meta`
- `topic`
- `papers`
- `diagnostics`

중요한 paper 필드:
- `title`
- `url`
- `published_at`
- `relevance_score`
- `relevance_reason`
- `core_point`
- `usefulness`
- `evidence_spans`

현재 사용되는 status:
- `ok`
- `no_candidates`
- `outside_horizon`
- `below_threshold`
- `error`

## 6. 검색 제어값

`search_intent`
- `whats_new`: 최신 논문 우선
- `best_match`: 선택한 기간 안에서 가장 잘 맞는 논문 우선
- `discovery`: 인접하지만 전이 가능한 방법론까지 포함

`time_horizon`
- `7d`
- `30d`
- `180d`
- `1y`
- `3y`
- `5y`

`top_k`
- 반환할 논문 수
- 현재 런타임 상한: `1..50`

## 7. 추천 사용 패턴

### 에이전트 프레임워크에 붙일 때
HTTP endpoint가 맞는 경우:
- 에이전트가 로컬 HTTP tool 호출을 지원할 때
- provider key를 에이전트 프로세스에 노출하고 싶지 않을 때
- broker 경계를 명확히 두고 싶을 때

### 로컬 스크립트 파이프라인에 붙일 때
CLI가 맞는 경우:
- subprocess로 붙이고 싶을 때
- stdout JSON이 편할 때
- HTTP 헤더 처리를 줄이고 싶을 때

## 8. 자주 생기는 문제
1. `403 Forbidden`
- `AGENT_API_TOKEN`이 틀렸거나 비어 있음
- 요청이 로컬 머신이 아닌 곳에서 들어옴

2. `research_context is required`
- 요청 본문에 핵심 검색 문맥이 없음

3. `No LLM provider available`
- Gemini, OPENAI-compatible backend, Cerebras fallback 중 하나를 설정해야 함

4. 결과가 비거나 `below_threshold`
- 기간을 넓혀보기
- `best_match` 대신 `discovery` 사용
- context가 너무 좁다면 조금 완화

## 9. 추천 설정 순서
1. 먼저 일반 로컬 UI에서 검색 품질 확인
2. `AGENT_API_TOKEN` 설정
3. provider 경로 선택
   - Gemini
   - local OPENAI-compatible backend
4. CLI로 먼저 테스트
5. 필요하면 HTTP로 통합
