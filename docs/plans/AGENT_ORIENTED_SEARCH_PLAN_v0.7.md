# Paper Morning Agent-Oriented Search Plan (v0.7 Draft)

## Goal
Define the delayed `2-2` direction as a concrete product and implementation plan:

- not a daily digest app for humans
- not a separate engine from the human search path
- a structured paper-search tool that a research agent can call reliably

The purpose of this plan is to turn the earlier "agent mode" idea into an explicit contract that can be implemented later without ambiguity.

## Why this exists
The current `2-1` direction makes Paper Morning work well for human on-demand search.

The next strategic extension is:
- an AI agent provides a research context
- Paper Morning retrieves papers over a configurable horizon
- Paper Morning ranks them by practical relevance
- Paper Morning returns structured JSON instead of HTML cards

This turns the product into a reusable search component for:
- literature review agents
- hypothesis-generation agents
- project-planning agents
- biomedical RAG bootstrap workflows

## Product definition
Paper Morning agent mode should be positioned as:

**A research-context paper retrieval and reranking tool that returns machine-usable JSON for downstream agents.**

Short framing:
- "Find papers that match a research context and return structured evidence."

Longer framing:
- "Paper Morning helps research agents retrieve, rank, and explain papers for a specific project context over recent or multi-year horizons."

## Strategic principle
Agent mode is **a second interface over the same core engine**, not a second product.

Shared engine:
- context normalization
- query generation
- source retrieval
- horizon filtering
- heuristic prioritization
- listwise LLM reranking
- evidence extraction

Different surface:
- human mode -> HTML cards, browser flow, local inbox
- agent mode -> JSON contract, status codes, stable fields

## Security model
Agent mode should not expose raw model-provider credentials to downstream agents.

Recommended first implementation:
- agent -> local Paper Morning endpoint
- Paper Morning -> Gemini / OPENAI-compatible local server / fallback provider
- provider keys stay in `.env` or OS keyring only

This means:
- the agent receives only a local broker token such as `AGENT_API_TOKEN`
- the agent never receives `GEMINI_API_KEY`
- the same pattern works for:
  - local OpenAI-compatible servers such as LM Studio or vLLM
  - commercial APIs such as Gemini

Initial security boundaries:
- local-only HTTP endpoint
- separate agent token, distinct from the browser UI token
- provider credentials resolved only inside the Paper Morning backend

## Scope for this plan
Define now:
- agent-facing tool contract
- request schema
- response schema
- status model
- ranking/retrieval behavior by mode
- recommended first technical surface
- phased implementation plan

Do not implement in this document:
- hosted cloud API
- remote multi-tenant service
- billing/auth system
- MCP packaging details
- agent memory/orchestration layer

## Primary use cases

### 1. Literature grounding
An agent asks:
- "Find the strongest-fit papers for this research project over the last 3 years."

### 2. Recent update check
An agent asks:
- "Find recent papers from the last 30 days that are directly useful to this project."

### 3. Discovery expansion
An agent asks:
- "Find adjacent but transferable methods over the last 5 years."

### 4. RAG/bootstrap input generation
An agent asks for:
- top relevant papers
- stable metadata
- evidence spans
- direct URLs

and uses the results to build a downstream reading or retrieval queue.

## Non-goals
Agent mode should not initially try to:
- summarize full PDFs
- do citation graph expansion
- do author graph analysis
- act as a remote public SaaS endpoint
- replace a general scholarly search platform

It should do one thing well:
- take a research context
- find papers
- rank them
- explain them
- return structured output

## Recommended first shipping surface
Recommended order:

1. Shared internal Python function
- canonical interface for reuse by preview, local app, and future endpoints

2. Local HTTP JSON endpoint on the existing web app
- easiest for external local agents to call
- reuses the existing runtime and config

3. Optional CLI wrapper
- useful for shell-driven agent pipelines

Defer:
- public hosted API
- MCP server packaging
- remote OAuth/auth flows for agent clients

## Canonical request contract

### Request object
```json
{
  "project_name": "Optional short label",
  "research_context": "Required free-text project context",
  "keywords": ["optional", "keyword", "list"],
  "search_intent": "best_match",
  "time_horizon": "3y",
  "top_k": 10,
  "output_language": "en",
  "model": "gemini-3.1-flash",
  "include_diagnostics": false,
  "source_policy": {
    "arxiv": true,
    "pubmed": true,
    "semantic_scholar": true,
    "google_scholar": false
  }
}
```

### Required fields
- `research_context`

### Optional fields
- `project_name`
- `keywords`
- `search_intent`
- `time_horizon`
- `top_k`
- `output_language`
- `model`
- `include_diagnostics`
- `source_policy`

### Defaults
- `project_name`: derived from context
- `keywords`: empty list
- `search_intent`: `best_match`
- `time_horizon`: `1y`
- `top_k`: `10`
- `output_language`: `en`
- `model`: runtime default Gemini model
- `include_diagnostics`: `false`
- `source_policy`: runtime source defaults

### Valid enums
`search_intent`
- `whats_new`
- `best_match`
- `discovery`

`time_horizon`
- `7d`
- `30d`
- `180d`
- `1y`
- `3y`
- `5y`

## Canonical response contract

### Top-level response object
```json
{
  "status": "ok",
  "request": {
    "project_name": "Foundation model for endoscopy triage",
    "search_intent": "best_match",
    "time_horizon": "3y",
    "top_k": 10,
    "output_language": "en"
  },
  "meta": {
    "intent_label": "Best Match",
    "requested_horizon_label": "3 years",
    "window_used_label": "last 3 years",
    "query_plan_label": "generated query",
    "used_model": "gemini-3.1-flash",
    "sources_queried": ["arXiv", "PubMed"],
    "scanned_count": 84,
    "selected_count": 10,
    "threshold_used": 6.0
  },
  "topic": {
    "name": "Endoscopy triage foundation models",
    "keywords": ["endoscopy", "foundation model", "triage"],
    "arxiv_query": "...",
    "pubmed_query": "...",
    "semantic_scholar_query": "...",
    "google_scholar_query": "..."
  },
  "papers": [
    {
      "rank": 1,
      "id": "arxiv:2501.12345",
      "title": "Paper title",
      "authors": "Author A, Author B",
      "source": "arXiv",
      "url": "https://...",
      "published_at": "2026-01-12T00:00:00Z",
      "relevance_score": 8.5,
      "relevance_reason": "Why it matches",
      "core_point": "Key finding summary",
      "usefulness": "How the agent/user could use it",
      "evidence_spans": ["title snippet", "abstract snippet"]
    }
  ],
  "diagnostics": []
}
```

## Response statuses

### `ok`
- Papers were found and returned.

### `no_candidates`
- No candidates were retrieved from sources.

### `outside_horizon`
- Candidates existed, but none remained inside the requested horizon.

### `below_threshold`
- Candidates were retrieved, but none passed the intended threshold.
- Optional fallback papers may still be returned if the interface chooses to expose nearest candidates.

### `partial_source_failure`
- Some sources failed, but at least one source succeeded and usable results were produced.

### `error`
- Request validation failed or the pipeline could not complete.

## Result item requirements
Each returned paper should include:
- stable rank in returned order
- stable source identifier if available
- title
- authors
- source
- canonical URL
- published timestamp
- relevance score
- short relevance reason
- short core-point summary
- short practical usefulness note
- evidence spans grounded in title/abstract

Agent mode should avoid HTML-specific fields and avoid presentation-only labels.

## Search behavior by mode

### `whats_new`
Purpose:
- recent updates first

Behavior:
- recent-first retrieval
- adaptive lookback up to requested horizon
- direct relevance still required
- freshness matters more than in other modes

Recommended defaults:
- horizon `30d`
- threshold `6.0`

### `best_match`
Purpose:
- strongest fit to the project, even if not extremely recent

Behavior:
- direct-horizon retrieval
- relevance-first reranking
- direct project matches score highest
- highly reusable methods can still rank well

Recommended defaults:
- horizon `1y`
- threshold `6.0`

### `discovery`
Purpose:
- broaden search to adjacent but transferable work

Behavior:
- direct-horizon retrieval
- broader reuse logic in ranking prompt
- still requires concrete usefulness, not generic buzzword overlap

Recommended defaults:
- horizon `3y`
- threshold `5.5`

## Shared retrieval and ranking pipeline

### Stage 1. Input normalization
- derive missing project name
- normalize keywords
- validate mode and horizon

### Stage 2. Query generation
- generate one topic profile from context
- produce source-specific queries
- keep query output machine-parseable

### Stage 3. Query fallback
- if generated query is too narrow, build broader heuristic fallback query

### Stage 4. Multi-source retrieval
- query arXiv
- query PubMed
- optionally query Semantic Scholar
- optionally query Google Scholar

### Stage 5. Horizon filtering
- apply requested horizon
- for `whats_new`, optionally expand lookback stepwise until the requested horizon limit

### Stage 6. Heuristic prioritization
- prioritize candidates before LLM reranking
- use intent-aware weighting for:
  - title hits
  - abstract hits
  - recency

### Stage 7. Listwise LLM reranking
- send the shortlist in one batch
- do not score one-by-one in isolation
- return grounded explanations and evidence spans

### Stage 8. Thresholding and fallback behavior
- keep per-intent thresholds
- optionally include near-threshold fallback items when no item passes
- clearly mark that fallback behavior in metadata/status

### Stage 9. JSON serialization
- return stable machine-usable schema
- no HTML-specific dependencies

## Stability requirements for agent use
Agent mode must optimize for stability more than visual polish.

Required properties:
- machine-parseable request/response
- stable field names
- explicit status codes
- explicit query plan metadata
- explicit source list
- listwise reranking for better cross-paper calibration
- evidence-aware high-score gating

## Diagnostics policy
Diagnostics should be off by default for agents unless requested.

When `include_diagnostics=true`, include:
- source fetch warnings
- query plan used
- horizon/window chosen
- candidate counts by source
- shortlist size sent to Gemini
- fallback model used
- final threshold stats

Diagnostics should remain plain-text arrays or simple structured lists, not HTML blobs.

## Failure and fallback policy

### Query generation failure
- return `error`
- include machine-usable message

### All retrieval fails
- return `error` or `no_candidates` depending on whether sources failed vs returned empty

### Some retrieval fails
- continue if at least one source works
- return `partial_source_failure` if usable output still exists

### Gemini quota/model issue
- try model fallback chain first
- fail only after fallback models are exhausted
- include final model-attempt summary in diagnostics if enabled

### No high-scoring papers
- prefer status `below_threshold`
- optionally expose fallback nearest papers if the caller asked for them later

## Recommended API surface for first implementation

### Internal Python function
Suggested canonical signature:

```python
search_papers_for_agent(
    research_context: str,
    project_name: str = "",
    keywords: list[str] | None = None,
    search_intent: str = "best_match",
    time_horizon: str = "1y",
    top_k: int = 10,
    output_language: str = "en",
    model: str | None = None,
    include_diagnostics: bool = False,
    source_policy: dict | None = None,
) -> dict
```

### Local HTTP endpoint
Suggested endpoint:
- `POST /api/agent/search`

Response content type:
- `application/json`

Reason:
- easiest path for local research agents or orchestration scripts
- can reuse the existing web app runtime
- keeps provider keys inside the local Paper Morning process

### Optional CLI wrapper
Suggested command:

```bash
python app/paper_digest_app.py --agent-search --input request.json
```

Reason:
- useful for automation tools that prefer process-based tool invocation

## Suggested implementation phases

### Phase A. Extract shared search engine
Target:
- remove preview-only assumptions
- remove delivery-specific assumptions from core search path

Deliverables:
- shared internal search function
- shared result model

### Phase B. Add agent JSON interface
Target:
- local HTTP endpoint and/or CLI wrapper

Deliverables:
- request validation
- structured response
- status codes

### Phase C. Documentation and examples
Deliverables:
- example request JSON
- example response JSON
- example agent usage flow

### Phase D. Optional future packaging
Possible later surfaces:
- MCP server wrapper
- lightweight SDK helper
- remote authenticated API

Defer all of these until local agent utility is validated.

## Proposed file targets for later implementation
- `app/paper_digest_app.py`
- `app/web_app.py`
- new helper module such as `app/agent_search.py`
- docs in `docs/manuals/`

## Acceptance criteria
1. An external local agent can submit a research context and receive valid JSON without using email or HTML.
2. The same underlying ranking logic is shared with the human search path.
3. The returned papers include enough metadata and explanation to be reusable by downstream tools.
4. The interface can represent:
   - success
   - no results
   - partial retrieval failure
   - threshold failure
   - hard error
5. The implementation does not require a hosted backend or new cloud service to be useful.

## Open decisions to resolve later
1. Should first ship expose both CLI and HTTP, or only HTTP?
2. Should `Semantic Scholar` be enabled by default in agent mode?
3. Should fallback below-threshold papers be returned by default, or only when explicitly requested?
4. Should agent mode include raw abstracts in the output, or keep output compact and let downstream agents fetch details as needed?

## Recommendation recorded here
- Keep `2-2` as the next major interface after `2-1`, not as a separate product.
- Reuse the same retrieval and reranking engine.
- First implementation should ship as:
  - shared Python function
  - local HTTP JSON endpoint
- Defer hosted API and MCP packaging until after local agent value is validated.
