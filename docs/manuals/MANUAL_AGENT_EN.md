# Paper Morning Agent Manual

Target audience:
- local research agents
- tool-calling scripts
- developers integrating Paper Morning into a larger workflow

This manual explains how to use Paper Morning as a local paper-search tool for agents without exposing raw provider API keys.

## 1) Security model
Do not give your agent:
- `GEMINI_API_KEY`
- `OPENAI_COMPAT_API_KEY`
- `CEREBRAS_API_KEY`

Give your agent only:
- `AGENT_API_TOKEN`

Flow:
1. agent calls local Paper Morning
2. Paper Morning reads provider credentials from `.env` or OS keyring
3. Paper Morning performs query generation, retrieval, and reranking
4. Paper Morning returns structured JSON

Current boundary:
- HTTP endpoint is local-only
- non-loopback requests are rejected
- token is checked separately from the browser UI token

## 2) Supported backend patterns

### Option A. Gemini
Use Paper Morning with Gemini as the search/rerank provider.

Required:
```env
ENABLE_LLM_AGENT=true
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.1-flash
AGENT_API_TOKEN=your_local_broker_token
```

### Option B. Local OPENAI-compatible server
Use a local or self-hosted server such as:
- LM Studio
- vLLM
- OpenAI-compatible Ollama bridge

Example:
```env
ENABLE_OPENAI_COMPAT_FALLBACK=true
OPENAI_COMPAT_API_BASE=http://127.0.0.1:1234/v1
OPENAI_COMPAT_MODEL=qwen2.5-14b-instruct
OPENAI_COMPAT_API_KEY=
AGENT_API_TOKEN=your_local_broker_token
```

Notes:
- `OPENAI_COMPAT_API_KEY` is optional for local servers that do not require bearer auth.
- If Gemini is configured, Paper Morning currently tries Gemini first, then the OPENAI-compatible backend, then Cerebras fallback.

## 3) HTTP agent endpoint

Endpoint:
```text
POST http://127.0.0.1:5050/api/agent/search
```

Headers:
```text
Authorization: Bearer <AGENT_API_TOKEN>
Content-Type: application/json
```

Alternative auth header:
```text
X-Agent-Token: <AGENT_API_TOKEN>
```

### Minimal request
```json
{
  "research_context": "Find papers on retinal foundation models for triage",
  "search_intent": "best_match",
  "time_horizon": "1y",
  "top_k": 5
}
```

### Rich request
```json
{
  "project_name": "Retina triage foundation model",
  "research_context": "We are building a retinal foundation model for screening and triage under low-label settings.",
  "keywords": ["retina", "triage", "foundation model", "screening"],
  "search_intent": "discovery",
  "time_horizon": "3y",
  "top_k": 10,
  "output_language": "en",
  "include_diagnostics": true,
  "source_policy": {
    "arxiv": true,
    "pubmed": true,
    "semantic_scholar": true,
    "google_scholar": false
  }
}
```

### cURL example
```bash
curl -X POST http://127.0.0.1:5050/api/agent/search \
  -H "Authorization: Bearer your_local_broker_token" \
  -H "Content-Type: application/json" \
  -d '{
    "research_context": "Find recent papers on multimodal ICU foundation models",
    "search_intent": "whats_new",
    "time_horizon": "30d",
    "top_k": 5
  }'
```

## 4) CLI mode
Paper Morning also supports direct CLI JSON output without HTTP.

### Minimal CLI example
```bash
python app/paper_digest_app.py \
  --agent-search \
  --research-context "Find papers on multimodal ICU foundation models" \
  --search-intent best_match \
  --time-horizon 1y \
  --top-k 5 \
  --pretty-json
```

### Request file example
Create `request.json`:
```json
{
  "project_name": "ICU multimodal model",
  "research_context": "Find high-fit papers on multimodal ICU representation learning and prognosis.",
  "keywords": ["ICU", "multimodal", "representation learning", "prognosis"],
  "search_intent": "best_match",
  "time_horizon": "3y",
  "top_k": 8,
  "include_diagnostics": true
}
```

Run:
```bash
python app/paper_digest_app.py --agent-search --agent-request-file request.json --pretty-json
```

Read from stdin:
```bash
cat request.json | python app/paper_digest_app.py --agent-search --agent-request-file - --pretty-json
```

## 5) Response shape
Top-level fields:
- `status`
- `request`
- `meta`
- `topic`
- `papers`
- `diagnostics`

Important paper fields:
- `title`
- `url`
- `published_at`
- `relevance_score`
- `relevance_reason`
- `core_point`
- `usefulness`
- `evidence_spans`

Status values currently used:
- `ok`
- `no_candidates`
- `outside_horizon`
- `below_threshold`
- `error`

## 6) Search controls

`search_intent`
- `whats_new`: recent updates first
- `best_match`: strongest fit in the selected horizon
- `discovery`: adjacent but transferable work

`time_horizon`
- `7d`
- `30d`
- `180d`
- `1y`
- `3y`
- `5y`

`top_k`
- max papers returned
- current runtime clamp: `1..50`

## 7) Recommended usage patterns

### For an agent framework
Use the HTTP endpoint when:
- the agent can call local tools over HTTP
- you want a stable broker boundary
- you do not want the agent process to touch provider credentials

### For a local script pipeline
Use CLI mode when:
- you want simple subprocess integration
- you want stdout JSON
- you do not want to manage HTTP auth headers

## 8) Common failures
1. `403 Forbidden`
- wrong or missing `AGENT_API_TOKEN`
- request not coming from loopback/local machine

2. `research_context is required`
- request body is missing the main search prompt

3. `No LLM provider available`
- configure Gemini, OPENAI-compatible backend, or Cerebras fallback

4. Empty results / `below_threshold`
- broaden horizon
- switch from `best_match` to `discovery`
- relax the research context if it is too narrow

## 9) Recommended setup sequence
1. Confirm search quality in the normal local UI first
2. Set `AGENT_API_TOKEN`
3. Choose provider path:
   - Gemini
   - local OPENAI-compatible backend
4. Test with CLI
5. Integrate via HTTP if needed
