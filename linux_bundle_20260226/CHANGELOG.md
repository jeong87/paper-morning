# Changelog

All notable changes to **paper-morning** are documented in this file.

## [0.4.1] - 2026-03-09

### Changed
- GitHub Actions scheduled trigger updated to reduce top-of-hour delay risk:
  - `cron: "47 23 * * *"` (KST 08:47, internal 13-minute early trigger for default 09:00 send)
- Local schedulers now trigger **13 minutes earlier** than user-defined send time:
  - applies to CLI scheduler (`paper_digest_app.py` non-`--run-once`)
  - applies to Web Console scheduler refresh path
- Email content order updated:
  - paper content appears first
  - `Selection diagnostics` block moved to the end
- Repository root cleanup:
  - moved archival planning/inspection docs into `docs/archive/`

### Docs
- README improvements:
  - added clickable links for beginner/full manuals
  - version text now links to `VERSION`
  - schedule section updated for internal 13-minute early trigger
- Manuals updated to reflect the new internal trigger time and archive path changes.

## [0.4.0] - 2026-03-06

### Added
- Added configurable send cadence:
  - `SEND_FREQUENCY=daily|every_3_days|weekly`
  - `SEND_ANCHOR_DATE=YYYY-MM-DD`
- Added Google Scholar source integration (SerpAPI-based):
  - `ENABLE_GOOGLE_SCHOLAR`
  - `GOOGLE_SCHOLAR_API_KEY`
  - `GOOGLE_SCHOLAR_MAX_RESULTS_PER_QUERY`
  - `google_scholar_query` field in topic rows
- Added beginner-friendly bootstrap support updates:
  - topic-generation prompts now include `google_scholar_query`
  - bootstrap output schema updated accordingly

### Changed
- Scheduler now supports cadence policy at send time:
  - daily trigger can skip non-due days for 3-day/weekly mode
  - manual `Send Now` in Web Console bypasses cadence (`force_send`) for immediate testing
- `LOOKBACK_HOURS` is automatically raised to at least cadence window (e.g., weekly >= 168h).
- `LLM_MAX_CANDIDATES` upper cap raised to `80`.
- For 3-day/weekly cadence, effective LLM candidate cap is expanded with a non-linear scaling rule (sublinear) to control token growth.
- PubMed 429 handling was already improved in prior patch and remains active.

### Docs/UI
- README overhauled to Korean-first style with logo and simpler onboarding flow.
- README now places Gmail app-password guidance at the end (legacy/compat path).
- Settings/Setup UI now expose:
  - send cadence fields
  - Google Scholar toggle/key/per-query result limit
  - updated LLM candidate cap guidance (max 80)
- Topic Editor table now includes `Google Scholar Query` column.
- App version bumped to `paper-morning v0.4.0`.

## [0.3.3] - 2026-03-05

### Added
- Added `License` page in Web Console navigation (`/license`):
  - shows current license text (`LICENSE`)
  - includes support contact message: `nineclas@gmail.com`

### Changed
- Improved LLM JSON parsing robustness:
  - auto-repair for invalid backslash escapes
  - relaxed JSON parse retry (`strict=False`) for malformed control characters
- Default keyword relevance threshold (`MIN_RELEVANCE_SCORE`) changed from `3.0` to `6.0`:
  - runtime default
  - Web Console default
  - onboarding default
  - `.env.example` / `dist/.env.example` / linux bundle example
- App version bumped to `paper-morning v0.3.3`.

## [0.3.2] - 2026-03-05

### Added
- Added Gemini advanced reasoning toggle:
  - `ENABLE_GEMINI_ADVANCED_REASONING`
  - when enabled, app forces `gemini-3.1-pro`
- Added UI checkbox in Setup/Settings for advanced reasoning mode.

### Changed
- Default Gemini model updated to `gemini-3.1-flash`.
- `LLM_MAX_CANDIDATES` default changed from `20` to `30`.
- Runtime cap for `LLM_MAX_CANDIDATES` set to `50`.
- Settings UI now indicates candidate cap (max 50).
- App version bumped to `paper-morning v0.3.2`.

## [0.3.1] - 2026-03-05

### Added
- Added distributor-level OAuth bundle support:
  - `google_oauth_bundle.json` (optional) can provide default `client_id` / `client_secret` / `redirect_uri`.
  - Users can click Google login without manually entering Client ID/Secret when bundle is included.
- Added `google_oauth_bundle.template.json` to project/dist support files.
- Added Home dashboard OAuth panel:
  - current OAuth status visualization
  - connected account display
  - client source indicator (Settings vs bundled)
  - direct `Google 로그인 연결` / `연결 해제` actions.

### Changed
- OAuth client resolution now uses priority:
  1) Settings (`.env`) values
  2) bundled defaults (`google_oauth_bundle.json`)
- Setup/Settings pages now show bundled OAuth availability and source info.
- License changed from MIT to GNU AGPLv3 (`LICENSE` replaced with AGPLv3 text).
- App version bumped to `paper-morning v0.3.1`.

## [0.3.0] - 2026-03-05

### Added
- Added Google OAuth "auto-connect" flow for Gmail sending:
  - `/oauth/google/start` launches Google login/consent
  - `/oauth/google/callback` stores refresh token and connected account email
  - `/oauth/google/disconnect` unlinks OAuth credentials
- Added settings/setup UI fields for OAuth:
  - `ENABLE_GOOGLE_OAUTH`
  - `GOOGLE_OAUTH_USE_FOR_GMAIL`
  - `GOOGLE_OAUTH_CLIENT_ID`
  - `GOOGLE_OAUTH_CLIENT_SECRET`
  - `GOOGLE_OAUTH_REDIRECT_URI`
  - read-only style status via `GOOGLE_OAUTH_CONNECTED_EMAIL`
- Added OAuth healthcheck status in Setup diagnostics (`google_oauth_gmail`).

### Changed
- Email sending now supports dual path:
  - primary: Gmail API via OAuth (when configured/enabled)
  - fallback: SMTP app-password path (existing behavior)
- If OAuth send fails and SMTP app password is not configured, user-facing error now explains exactly what to fix.
- `is_setup_completed` now accepts either:
  - Gmail app password mode, or
  - complete Google OAuth Gmail mode.
- `.env.example` and onboarding wizard updated for OAuth config keys.
- Onboarding now supports OAuth-first setup (app password optional when OAuth mode is selected).

### Version
- App version bumped to `paper-morning v0.3.0`.

## [0.2.7] - 2026-03-05

### Fixed
- Reduced sensitive-data exposure risk in error paths:
  - Gemini requests now send API key via header (`x-goog-api-key`) instead of URL query parameter.
  - LLM/API exception texts are masked before returning to UI or storing task error state.
- Fixed `Send Now` cooldown timing:
  - cooldown timestamp is now recorded only after a successful send.
- Fixed selection diagnostics mismatch when LLM no-pass fallback goes to keyword mode:
  - ranking mode/counts/buckets now stay consistent with the actual mode used.

### Security
- Non-local web binding is now blocked by default.
  - To allow temporary insecure remote access, both `ALLOW_INSECURE_REMOTE_WEB=true` and `WEB_PASSWORD` are required.
- Added optional OS keychain-backed secret storage:
  - `USE_KEYRING=true` (default) stores secret fields in OS secure storage when available.
  - `.env` stores key references (e.g., `keyring://GEMINI_API_KEY`) instead of plaintext where supported.

### Changed
- Setup/Settings now expose:
  - `ALLOW_INSECURE_REMOTE_WEB`
  - `USE_KEYRING`

### Version
- App version bumped to `paper-morning v0.2.7`.

## [0.2.6] - 2026-03-03

### Changed
- Lowered default `LLM_BATCH_SIZE` from `8` to `5` to reduce per-run LLM burst load and improve free-tier stability.

### Version
- App version bumped to `paper-morning v0.2.6`.

## [0.2.5] - 2026-03-03

### Added
- Added `LICENSE` (MIT).
- Added `PRIVACY.md` describing local-data behavior and external API destinations.
- Added persistent log file output:
  - `paper-morning.log` under user app data directory
  - log rotation (2MB x 5 backups)
- Added Web Console log viewer:
  - `/logs` page
  - `/logs/content` live tail endpoint
- Added Semantic Scholar source integration:
  - new source fetch path in digest pipeline
  - optional API key support (`SEMANTIC_SCHOLAR_API_KEY`)
  - source toggle and per-query limit settings

### Changed
- Topic schema extended with `semantic_scholar_query`.
- Topic generation prompt now requests:
  - `arxiv_query`
  - `pubmed_query`
  - `semantic_scholar_query`
- Settings and Setup Wizard now expose Semantic Scholar controls.
- Build scripts now copy `LICENSE` and `PRIVACY.md` into `dist`.

### Version
- App version bumped to `paper-morning v0.2.5`.

## [0.2.4] - 2026-03-03

### Changed
- Query lifecycle is now strictly user-managed:
  - queries are generated only when user explicitly clicks `Keyword / Query 생성` in Topic Editor
  - daily runs use the saved query state only (no per-run LLM query regeneration)
- Removed search fallback chain to built-in defaults.
- Removed implicit query auto-build from topic keywords in runtime loading.

### Added
- Pre-run guard in Web Console (`Run Dry-Run` / `Send Now`):
  - if no query is configured, job start is blocked with setup guidance.
- Runtime guard in digest pipeline:
  - if both arXiv/PubMed query lists are empty, run fails fast with actionable message.

### Version
- App version bumped to `paper-morning v0.2.4`.

## [0.2.3] - 2026-03-03

### Fixed
- Fixed intermittent zero-candidate issue caused by over-narrow LLM-generated search queries.
  - When LLM-generated queries return 0 candidates, the app now automatically retries with:
    1) configured queries from `user_topics.json`, then
    2) built-in default queries.
- Added query-strategy diagnostics to report which query source was ultimately used.

### Changed
- App version bumped to `paper-morning v0.2.3`.

## [0.2.2] - 2026-03-01

### Added
- Added richer selection diagnostics in digest output:
  - collected counts (arXiv/PubMed/total)
  - ranking mode/threshold
  - score distribution buckets
  - final reason when 0 papers are selected
- Added duplicate paper suppression via local `sent_ids.json` history (default 14 days).
- Added first-run `Setup Wizard` page in Web Console, including one-click health checks:
  - Gmail SMTP login test
  - Gemini key test
  - Cerebras key test
- Added `Send Now` cooldown guard (`SEND_NOW_COOLDOWN_SECONDS`, default 300s).
- Added Windows Task Scheduler registration action in Home (`register_task.ps1` execution).
- Added host security guard:
  - non-local host binding now requires `WEB_PASSWORD`.
  - optional login screen when `WEB_PASSWORD` is configured.

### Changed
- App version bumped to `paper-morning v0.2.2`.
- `.env` writing now enforces private file permission tightening where possible.
- Settings now include:
  - `WEB_PASSWORD`
  - `SEND_NOW_COOLDOWN_SECONDS`
  - `SENT_HISTORY_DAYS`
  - operational warnings for high API-risk values
- Added setup/help links for Gmail/Gemini/Cerebras key issuance in UI.
- `NCBI_API_KEY` guidance was elevated to recommended.
- Build outputs now include `register_task.ps1` in `dist`.

## [0.2.1] - 2026-03-01

### Added
- Added LLM fallback chain: Gemini first, then Cerebras (`gpt-oss-120b`) when Gemini fails.
- Added new env/config keys:
  - `ENABLE_CEREBRAS_FALLBACK`
  - `CEREBRAS_API_KEY`
  - `CEREBRAS_MODEL`
  - `CEREBRAS_API_BASE`
- Topic Editor query generation now uses the same Gemini -> Cerebras fallback path.
- Settings page now includes Cerebras fallback toggle/key/model/base fields.

### Changed
- App version bumped to `paper-morning v0.2.1`.
- Onboarding wizard and `.env.example` now include Cerebras fallback configuration fields.
- LLM execution gating now runs when either Gemini is available or Cerebras fallback is enabled+configured.

## [0.2.0] - 2026-03-01

### Changed
- Web Console UI refreshed across Home/Settings/Topic Editor/Manual pages based on `docs/archive/UI_IMPROVEMENT_PLAN.md`.
  - New SaaS-style layout with left sidebar navigation and active page highlighting.
  - Updated visual system (design tokens, cards, badges, button hierarchy, responsive behavior).
- Home dashboard redesigned:
  - action cards (`Dry-Run`, `Send Now`, `Reload Scheduler`)
  - richer task status panel with status badge/start/end/progress
  - collapsible last dry-run output panel
- Settings redesigned from table layout to sectioned form cards.
  - unified send-time picker (`input[type=time]`) with hidden `SEND_HOUR` / `SEND_MINUTE` mapping
  - improved labels/help text and clearer grouping
- Topic Editor usability updated:
  - page header and cleaner section structure
  - stronger action styling (`btn-success`, `btn-danger`)
  - sticky save bar at bottom
  - generate button loading-state label update
- Manual page now uses page-header style for visual consistency.
- App version bumped to `paper-morning v0.2.0`.

### Compatibility
- Existing backend behavior and endpoints are preserved.
- Existing POST token validation flow is preserved.

## [0.1.4] - 2026-02-28

### Fixed
- Unified config path behavior between packaged launchers and source launchers.
  - `start_web_console.bat` / `start_web_console.sh` now use the same per-user config store as executable builds.
- Resolved case where source-launch users saw empty/default settings after upgrading.

### Changed
- App version bumped to `paper-morning v0.1.4`.

## [0.1.3] - 2026-02-28

### Added
- Persistent user config storage for packaged app builds:
  - `.env` and `user_topics.json` are now stored in per-user OS data directory.
- Automatic legacy migration on first launch:
  - migrates old `.env` / topic files from executable-folder layout (`v0.1.0~0.1.2`) to new persistent path.

### Changed
- App version bumped to `paper-morning v0.1.3`.
- Web Settings page now shows active `.env` path to reduce confusion across update folders.
- Onboarding wizard now writes to the same runtime config path used by the app.

### Fixed
- Prevented update-time config loss caused by `dist` folder replacement.
- Added safe numeric env parsing fallback to avoid crashes on blank numeric values.

## [0.1.2] - 2026-02-28

### Security
- Added local request token protection for all Web Console `POST` endpoints.
  - `X-App-Token` header for JS requests
  - hidden `app_token` field for form posts
- Replaced hard-coded Flask `secret_key` with runtime secret generation (or `WEB_APP_SECRET_KEY` env override).

### Changed
- App version bumped to `paper-morning v0.1.2`.
- Web Console title now displays runtime version from `VERSION` file.
- When `GMAIL_APP_PASSWORD` is saved from Settings, all whitespace is removed automatically.

### Fixed
- Stopped implicit fallback to built-in topic/query defaults when `user_topics.json` exists but is empty.
  - Empty topic config now stays empty until user explicitly configures projects/topics.
- LLM query generation is skipped when there is no project context.
- arXiv retry behavior improved:
  - retry only transient HTTP statuses (`429/5xx`) and network timeout/connection errors
  - fail fast on non-retryable HTTP errors

## [0.1.1] - 2026-02-28

### Added
- Added async task UX in Web Console Home:
  - background jobs for `Run Dry-Run`, `Send Now`, `Reload Scheduler`
  - progress bar + live status polling + error panel
- Added Markdown preview rendering for `Manual` page.
- Added table-based Topic Editor UI:
  - Projects table (`name`, `context`)
  - Topics table (`name`, `keywords`, `arxiv_query`, `pubmed_query`)
  - Gemini-based `Keyword / Query 생성` action and editable result save
- Added Linux packaging scripts:
  - `build_linux.sh`
  - `start_web_console.sh`
- Added `VERSION` file and changelog tracking.

### Changed
- Version defined as `paper-morning v0.1.1`.
- Settings secret fields (`GMAIL_APP_PASSWORD`, `GEMINI_API_KEY`) are hidden by default in UI.
- Blank save behavior for secret fields preserves existing stored value.
- Runtime config reload forces `.env` refresh per task execution in `load_config(...)`.
- One-click launcher auto-selects next available port if requested port is in use.
- arXiv fetch hardening:
  - retry/backoff on transient errors (including 429)
  - skip only failed arXiv query instead of failing full job
  - per-query request spacing
  - hard cap for arXiv `max_results` to reduce rate-limit risk
- Packaging removes generated local secrets/user files from `dist` before copying support files.
- `user_topics.template.json` default changed to empty projects/topics.

### Fixed
- Fixed issue where newly saved credentials from Settings were not immediately reflected during `Send Now` in the same running process.
- Reduced full-job failures caused by arXiv `429` responses.

## [0.1.0] - 2026-02-26

### Initial release
- Windows-first local app with Web Console + scheduler.
- Daily paper collection from arXiv and PubMed.
- LLM-assisted query generation, relevance scoring, and Korean summaries.
- Gmail delivery pipeline and setup wizard executable.
