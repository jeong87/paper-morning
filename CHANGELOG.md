# Changelog

## 0.7.0

- Repositioned Paper Morning as a search-first research-context paper search tool.
- Kept daily digest delivery as an optional layer instead of the core concept.
- Upgraded the GitHub live preview with search intents, broader horizon control, and clearer no-result handling.
- Added local search-first Home UI with `Best Match`, `What's New`, and `Discovery` modes.
- Added `SEARCH_INTENT_DEFAULT` and `SEARCH_TIME_HORIZON_DEFAULT` for local morning popup defaults.
- Switched local LLM reranking from small batch scoring to listwise reranking over the shortlisted candidate set.
- Added search metadata to saved local inbox results so intent, horizon, and query-plan context are visible later.
- Updated onboarding, sample env, and beginner docs to match the search-first flow.
