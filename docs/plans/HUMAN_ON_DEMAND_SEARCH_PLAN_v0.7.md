# Paper Morning Human On-Demand Search Plan (v0.7 Draft)

## Goal
Turn the current preview-first experience into a proper **human on-demand paper search workflow**.

The user should be able to:
- visit the page when needed
- enter research context
- choose what kind of search they want
- retrieve ranked papers
- understand why those papers were selected

without setting up Gmail, scheduling, or automation first.

## Scope for this plan
Implement only the human-facing search path (`2-1`).

Defer:
- agent-specific tool/API contract
- multi-year JSON-first agent interface
- deeper local-app redesign beyond what is needed to support the new search model

## Product behavior to add

### A. Search intents
Add three explicit search intents in the primary UI:

1. `What's New`
- Goal: find recent papers related to the context.
- Retrieval priority: freshness first, then relevance.
- Default window: `30d`.

2. `Best Match`
- Goal: find papers that most closely fit the context, even if they are less recent.
- Retrieval priority: relevance first.
- Default window: `3y`.

3. `Discovery`
- Goal: include adjacent but transferable methods, datasets, and task formulations.
- Retrieval priority: broader relevance and transfer potential.
- Default window: `3y`.

### B. Time horizon control
Add explicit horizon controls:
- `7d`
- `30d`
- `180d`
- `1y`
- `3y`
- `5y`

This removes the current ambiguity between "latest" and "best fit".

### C. Result quality messaging
The UI should clearly distinguish between:
- no papers retrieved at all
- papers retrieved but none are recent enough
- papers retrieved but none passed the relevance threshold

When there are no suitable results, the user should see a useful explanation and the next recommended action.

### D. Search explanation
Show the following in the result view:
- selected search intent
- selected time horizon
- actual query plan used
- sources queried
- relevance model used
- reason/evidence for each selected paper

## Proposed UX structure

### Primary page layout
Use the current preview page as the base, but add:

1. Search controls
- Project name
- Research context
- Optional keywords
- Search intent
- Time horizon
- Output language
- Model
- API key

2. Result framing
- A clearer explanation of what each mode does
- A visible "you are searching for X over Y horizon" summary

3. Result view
- ranked paper cards
- clear relevance explanation
- evidence spans
- diagnostics hidden behind a collapsible panel or secondary section

### Suggested UI labels
- Main CTA: `Search Papers`
- Secondary CTA: `Open Last Result`
- Intent labels:
  - `What's New`
  - `Best Match`
  - `Discovery`

## Retrieval and ranking policy

### 1. What's New
- Use recent-first retrieval.
- Window is user-selected but defaults to `30d`.
- Ranking prompt should prefer direct relevance while preserving freshness.
- If no results are found, widen only within the selected intent rules and explain that the recent horizon may be too strict.

### 2. Best Match
- Use broader retrieval over the chosen horizon.
- Ranking prompt should strongly prefer direct context fit.
- Older but highly matched papers are acceptable.
- This is the mode that answers:
  - "I do not care if it is not from this week; just show me what fits my project best."

### 3. Discovery
- Use broader retrieval over the chosen horizon.
- Ranking prompt should allow adjacent, transferable work.
- Results should still require concrete usefulness, not generic buzzword overlap.

## Prompt policy changes
Prepare separate ranking policies per search intent.

### What's New prompt behavior
- Direct overlap favored
- Freshness awareness in the instruction
- Adjacent work allowed but lower priority

### Best Match prompt behavior
- Direct fit strongly favored
- Freshness is not the main criterion
- Strongly reusable methods may still surface, but behind direct-fit papers

### Discovery prompt behavior
- Allow adjacent methods and transferable insights
- Reward concrete reuse paths
- Keep generic overlap low

## Proposed implementation phases

### Phase 1: GitHub live preview update
Target files:
- `docs/preview/index.html`
- `README.md`

Work:
1. Add search intent selector
2. Add time horizon selector
3. Split retrieval behavior by intent
4. Split ranking prompts by intent
5. Improve no-result messaging
6. Update page copy so the product reads as search-first, not digest-first

Reason:
- This is the public front door.
- It is the fastest place to validate the new product story.

### Phase 2: Local web app alignment
Target files:
- `app/web_app.py`
- `app/paper_digest_app.py`

Work:
1. Add equivalent search intent and horizon controls to the local app
2. Allow on-demand search without framing it as preview-only
3. Keep local inbox and scheduled digest as optional follow-up actions
4. Update terminology from delivery-first to search-first where needed

Reason:
- The local app should not contradict the GitHub-facing product story.

### Phase 3: Shared internal search model cleanup
Target files:
- `app/paper_digest_app.py`
- supporting config/helpers

Work:
1. Normalize search intent names across preview and runtime
2. Normalize horizon handling across sources
3. Separate retrieval policy from delivery policy
4. Make result payload reusable for future agent mode

Reason:
- This keeps `2-2` easier later.

## Concrete repo work plan for Phase 1

### A. UI controls
- Add `search_intent` select to the preview page
- Add `time_horizon` select to the preview page
- Update descriptive copy for each mode

### B. Retrieval logic
- Convert the current fixed/adaptive recent logic into intent-aware retrieval
- For `Best Match` and `Discovery`, support longer windows directly
- Keep source-specific fallbacks if generated queries are too narrow

### C. Ranking logic
- Introduce intent-specific prompt builders
- Keep score threshold logic, but allow per-intent defaults if needed

### D. Result messaging
- Add clearer messages for:
  - no candidates retrieved
  - no candidates within selected horizon
  - no candidates passing threshold

### E. README / positioning
- Reframe README top section around search-first wording
- Keep digest wording only as an optional follow-up capability

## Acceptance criteria
1. A GitHub visitor can understand the product as a search tool before thinking about automation.
2. The user can explicitly request either recent papers or best-fit papers.
3. The result view shows both relevance reasoning and the search settings used.
4. The UI behaves sensibly when the selected horizon yields no useful papers.
5. The design remains compatible with future agent-mode reuse.

## Out of scope for this implementation batch
- API endpoint for agent use
- JSON schema for agent tool calls
- embedding/vector retrieval overhaul
- citations graph / author graph expansion
- full local app redesign beyond search-intent alignment

## Recommended defaults
1. Default landing intent: `Best Match`
2. Default horizon for `Best Match`: `1y`
3. Default horizon for `What's New`: `30d`
4. Diagnostics: collapsed by default
5. Public front door: keep the current README top structure, but route attention to GitHub live preview immediately under the top image / language switch
6. `Best Match` horizon options should still allow `3y` and `5y`

## Review decisions recorded
Approved implementation scope:
- implement Phase 1 first
- keep changes scoped to GitHub-facing preview + top-level README wording
- defer local app alignment to the next batch unless small compatibility edits are clearly necessary

Approved defaults:
- `Best Match` default horizon: `1y`
- diagnostics hidden by default behind a user-triggered toggle
- keep the current README top structure if it still routes users quickly into live preview
