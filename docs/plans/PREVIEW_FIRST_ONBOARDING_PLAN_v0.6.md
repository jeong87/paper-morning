# Paper Morning Preview-First Onboarding Plan (v0.6 Draft)

## Why this plan exists
The current setup path still asks users to solve automation (GitHub Actions + email delivery + secrets) before they see product value.
For non-developers, this creates early drop-off.

## My opinion on the proposal
I agree with the core direction.

- Strongly agree: **preview-first** should replace email-first in onboarding.
- Strongly agree: users should provide project intent, not raw `PM_TOPICS_JSON` or search queries at first run.
- Strongly agree: template repo is a better mental model than fork for non-developers.
- Strongly agree: local-first default is safer for cost and friction; Actions should be the advanced path.
- Agree with caveat: local setup app is the best UX, but should be phased after preview-first + config simplification.

## Product principle to adopt
**First click = personalized result.**
Not “first click = automation plumbing”.

---

## Implementation boundary (how far to implement)

### Phase 1 (implement now, target v0.6.x)
Focus: remove onboarding friction without building a desktop app yet.

1. Preview-first onboarding (email optional)
- Make onboarding success state “preview generated” instead of “email sent”.
- Promote dry-run output to user-facing preview card/page.
- Keep send-now behind an explicit advanced toggle.

2. Project-description-first input model
- Onboarding requires only:
  - what user is working on
  - optional keywords
  - papers per digest
  - preview now
- `PM_PROJECTS_JSON` is primary onboarding input.
- `PM_TOPICS_JSON` becomes generated artifact (bootstrap output), hidden by default.

3. Template-first entry path in docs
- Replace “Fork this repo” wording with “Create from template”.
- Keep fork instructions as fallback/advanced note only.

4. Secrets scope reduction
- Move non-secret settings to tracked config file(s) in repo.
- Keep only true secrets in GitHub Secrets:
  - `GEMINI_API_KEY`
  - `GMAIL_APP_PASSWORD` (when email path enabled)
- Add schema validation for user-editable config.

5. Cost/transparency guardrails
- Document local-first as recommended default.
- Mark Actions schedule/cost implications clearly for private repos.
- Keep Actions as advanced automation mode.

### Phase 2 (next release, target v0.7.x)
Focus: automate GitHub plumbing with minimal user clicks.

1. `gh`-based setup bootstrapper (CLI)
- Auth, template creation, secret upload, workflow enable/run in one flow.
- Provide guided prompts + retry-safe steps.

2. Better preview artifacts in Actions
- Upload `digest_preview.html` artifact for manual dry-run workflows.
- Provide direct links in workflow summary.

3. Quick-try side doors
- Add Colab quick-try notebook (preview-only).
- Add optional Codespaces quick-start note for technical evaluators.

### Phase 3 (later, v0.8+ backlog)
- Desktop setup app (GUI) for full click-through provisioning.
- Static setup wizard (GitHub Pages) if desktop app is deferred.
- Optional API-based provisioning path (with strict security model).

---

## Concrete repo work plan (Phase 1)

### A. Backend / runtime
- `app/paper_digest_app.py`
  - Add explicit preview payload/renderer path.
  - Ensure dry-run produces human-readable preview consistently.
  - Keep email send path optional and decoupled.
- `scripts/gha_prepare_runtime.py`
  - Support new non-secret config file loading.
  - Keep backward compatibility with current secrets block during migration.

### B. Web console UX
- `app/web_app.py`
  - Onboarding success target: preview screen.
  - Collapse advanced settings (email transport, raw query editing) by default.
  - Add clear mode switch: Preview mode vs Daily automation mode.

### C. Onboarding CLI
- `app/onboarding_wizard.py`
  - Ask for project description first.
  - Generate bootstrap input; avoid raw topic JSON prompts.
  - Offer optional email setup after preview success.

### D. Docs
- `README.md`
  - Reframe Quick Start around preview-first.
  - Template-first wording and local-first default.
- `docs/manuals/MANUAL_FIRSTTIME_EN.md`
- `docs/manuals/MANUAL_FIRSTTIME_KR.md`
  - Move email setup to “optional next step”.
  - Clarify Actions as advanced path.

### E. Config model
- Introduce tracked non-secret config file (draft):
  - `config/projects.yaml` (or `config/projects.md`)
- Keep sensitive keys in env/secrets only.

---

## Acceptance criteria for Phase 1
1. New user can generate a personalized preview without configuring Gmail.
2. New user does not need to hand-edit `PM_TOPICS_JSON` in initial flow.
3. Docs use template-first wording in primary onboarding path.
4. Non-secret config is editable in repo and validated.
5. Existing users remain functional (backward compatibility preserved).

## Risks and mitigations
- Migration confusion between old/new config formats.
  - Mitigation: dual-read compatibility + migration guide + clear deprecation window.
- Users expecting instant daily automation from first click.
  - Mitigation: explicit two-step messaging (Preview first, Automation second).
- Added complexity in UI flow.
  - Mitigation: keep default path minimal; advanced settings collapsed.

## Decision needed before implementation starts
1. Non-secret config format final choice: `YAML` vs `Markdown+frontmatter`.
2. Whether to keep GitHub Actions polling at current cadence for advanced mode.
3. Preferred scope for Phase 2 bootstrapper: Python script only vs cross-platform binary packaging.
