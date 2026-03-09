# Paper Morning Globalization Plan (v0.5.0)

## Goal
- Prepare Paper Morning for global distribution channels (Reddit, LinkedIn, X, etc.).
- Improve first impression (English README + live demo) and report readability (email UI refresh).
- Add configurable output language for LLM summaries.

## Scope
1. README in English (primary project entry).
2. Multi-language summary mode via `.env`:
   - `OUTPUT_LANGUAGE` (default: `en`)
   - LLM summary prompt follows this language.
   - Replace Korean hardcoded backend report texts with English.
3. Email visual upgrade:
   - score emphasis with color + larger typography
   - cleaner cards with spacing, borders, title emphasis
   - keep diagnostics section at the bottom
4. Demo mode + GitHub Pages:
   - generate static HTML preview from sample data
   - publish demo through Pages workflow
   - add README demo link

## Design Decisions
- Keep current Korean manuals (`MANUAL_KR.md`, `MANUAL_FIRSTTIME_KR.md`) for existing users.
- Use English as backend/report default labels.
- Keep internal data compatibility:
  - parse legacy LLM keys (`*_ko`) if present
  - write/read new neutral keys for future outputs
- Demo data must be synthetic and privacy-safe.

## Implementation Steps
1. Backend language config
   - Add `output_language` in `AppConfig`
   - Parse/validate `OUTPUT_LANGUAGE` in `load_config`
   - Add `.env.example`, web settings keys/defaults, onboarding wizard support
2. LLM prompt localization
   - In LLM ranking prompt, request summary/reason in `OUTPUT_LANGUAGE`
   - Parse both legacy and new JSON response keys
3. Backend text localization cleanup
   - Convert Korean diagnostics and recovery messages to English
4. Email HTML redesign
   - score badge component with color bands
   - improved spacing, typography, divider lines, card look
5. Demo mode
   - Add `scripts/generate_demo_html.py`
   - Generate `docs/demo/index.html` from mock papers/stats
6. GitHub Pages workflow
   - Add `.github/workflows/deploy-demo-pages.yml`
   - Upload/deploy `docs/` content
7. Docs
   - Rewrite root README in English
   - Add demo link + language option documentation
8. Release metadata
   - Update `VERSION` to `0.5.0`
   - Update `CHANGELOG.md`

## Validation Checklist
- `python -m py_compile paper_digest_app.py web_app.py onboarding_wizard.py scripts/generate_demo_html.py`
- `python scripts/generate_demo_html.py` creates `docs/demo/index.html`
- `python paper_digest_app.py --run-once --dry-run` works with `OUTPUT_LANGUAGE=en`
- No Korean hardcoded strings remain in `paper_digest_app.py` user-facing report text.

## Out of Scope (this round)
- Full UI i18n for web console labels/navigation.
- Per-user multi-locale frontend language toggle.
