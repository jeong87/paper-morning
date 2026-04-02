# Paper Morning Product Direction Reset (v0.7 Draft)

## Why this reset exists
The product currently presents itself too much as a daily paper delivery tool.
That is no longer the best center of gravity.

The durable value is not "sending papers every morning".
The durable value is "finding papers that actually match a research context, and explaining why they matter".

Daily delivery should remain available, but as an optional delivery mode rather than the product definition.

## Direction to adopt
Paper Morning should be repositioned as a **research-context paper search and relevance engine**.

The product should support two interfaces over the same core engine:

1. Human on-demand mode
- A person comes when needed, clicks search, and checks whether there are new or highly relevant papers.
- This becomes the primary product path for the next phase.

2. Agent-oriented mode
- An AI agent asks for papers matching a research context over a configurable multi-year horizon.
- This becomes a later product path, not part of the immediate implementation batch.

## Product thesis
**Core value = retrieve, rank, and explain papers for a specific research context.**

Not:
- email infrastructure
- Gmail setup
- daily automation
- delivery plumbing

Those are optional wrappers around the core engine.

## Strategic decisions

### 1. Move "daily digest" out of the core concept
- Keep the feature.
- Stop positioning it as the default mental model.
- Present it as an optional output mode for users who explicitly want scheduled delivery.

### 2. Make on-demand human search the primary experience
- Primary path: open page -> enter context -> choose search intent -> run -> inspect results.
- The current GitHub live preview becomes the natural starting point for this transition.
- The local UI should later align to the same product model.

### 3. Treat agent mode as a second interface, not a separate engine
- Retrieval, ranking, evidence extraction, and mode logic should be shared.
- Only the surface changes:
  - human mode: cards / preview HTML / controls
  - agent mode: structured JSON tool output

### 4. Shift from "latest only" to "fit + freshness" as separate user intents
The product must support at least three search intents:

1. `What's New`
- Prioritize recent papers.
- Good for checking recent updates.

2. `Best Match`
- Prioritize context fit even if papers are not extremely recent.
- Good for literature grounding.

3. `Discovery`
- Allow adjacent methods, datasets, and transferable work.
- Good for expanding the search space.

## What remains valid from the current project
- Research-context input model
- Query generation from project context
- Multi-source retrieval
- LLM relevance scoring and evidence spans
- HTML preview rendering
- Local inbox / optional delivery layer
- Per-mode relevance prompt logic

These should be reused, not discarded.

## What gets deprioritized
- Email-first onboarding
- "Morning digest" language as the primary positioning
- Gmail configuration as part of the core activation path
- Automation-heavy docs as the front door

## Immediate scope boundary
For the next implementation batch, do **only 2-1**.

Implement now:
- human on-demand search mode
- better control over search intent and time range
- better support for "not necessarily latest, but highly relevant" retrieval
- better GitHub-first preview experience

Do not implement now:
- agent-specific API/tool contract
- agent JSON endpoint
- full agent workflow docs
- deeper automation redesign for agent usage

## Proposed product framing
Short framing:
- "Search papers that fit your research context."

Longer framing:
- "Paper Morning helps researchers and research agents find papers that match a specific project context, rank them by practical relevance, and explain why they matter."

## User-facing concept update
Recommended top-level experience:

1. Search now
- The main action.

2. Choose search intent
- `What's New`
- `Best Match`
- `Discovery`

3. Choose time horizon
- recent windows for freshness checks
- longer windows for literature fit

4. Review ranked results with explanations
- score
- relevance reason
- usefulness
- evidence

5. Optional outputs
- save locally
- open preview
- schedule delivery later

## Success criteria for this direction change
1. New users understand the product without reading about Gmail or scheduling first.
2. A user can run a meaningful search without enabling any delivery system.
3. The product can return useful results even when the best papers are not extremely recent.
4. Daily delivery remains available, but no longer blocks the main value path.
5. The future agent mode can reuse the same retrieval and ranking engine.

## Risks

### Risk: product becomes too broad
Mitigation:
- Keep the next phase focused on one primary interface: human on-demand mode.

### Risk: existing users still expect digest-first behavior
Mitigation:
- Keep digest intact as an optional mode.
- Reframe, do not remove.

### Risk: "best match" searches become slow or noisy
Mitigation:
- Separate search intents and use different retrieval/ranking policies by mode.

## Decision recorded here
Approved implementation target for the next step:
- Proceed with `2-1` only.
- Defer `2-2` until after the human on-demand mode is validated.
