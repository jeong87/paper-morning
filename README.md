# Paper Morning

[![Paper Morning Logo](assets/papermorning2.png)](https://raw.githack.com/jeong87/paper-morning/main/docs/preview/index.html)

**[EN](README.md) | [KR](docs/manuals/README_KR.md)**

Paper Morning is a research-context paper search tool for medical/health AI researchers.
It turns a project description into search queries, retrieves papers, ranks them by practical relevance, and explains why they matter. Local inbox and scheduled digest delivery remain available as optional follow-up modes.

- Latest version: **[v0.7.0](VERSION)**
- License: `GNU AGPLv3` ([LICENSE](LICENSE))
- Privacy policy: [PRIVACY.md](PRIVACY.md)

## Try Live Web Preview (No Download)
If you want to understand the product from GitHub first:

- <a href="https://raw.githack.com/jeong87/paper-morning/main/docs/preview/index.html">Open Live Web Preview</a>

What happens on that page:
- The page itself explains what Paper Morning does before you run anything
- Enter your research context, choose a search mode, and paste a Gemini API key
- The page generates search queries from your context
- It retrieves real candidates from arXiv and PubMed based on your chosen intent and time horizon
- It ranks and summarizes them with Gemini
- It opens the ranked result page in a new browser tab

Notes:
- Client-side only (runs in your browser)
- No actual email is sent from this page
- Best for first-impression validation before local install

## What It Does
1. Reads your project context and saved search queries.
2. Collects papers from arXiv, PubMed, Semantic Scholar, and optional Google Scholar (SerpAPI).
3. Scores each paper (1-10) with LLM relevance ranking.
4. Lets you inspect results on demand, then optionally save or deliver them later.

## Key Features
- Personalized LLM relevance ranking using your active projects.
- Search intents for recent updates, best-fit papers, and broader discovery.
- Local agent interface with brokered credentials and JSON output.
- Per-project mail cadence (`daily` / `every_3_days` / `weekly`) in Topic Editor.
- Local inbox mode with browser popup scheduling on a running PC.
- Configurable cadence: `daily`, `every_3_days`, `weekly`.
- Duplicate suppression with history tracking (`sent_ids.json`).
- PubMed 429 retry/backoff handling.
- Gemini with automatic fallback (`3.1-pro` -> `3.1-flash` -> `3.0-pro` -> `3.0-flash` -> `2.5-pro` -> `2.5-flash`) and optional Cerebras backup.
- Output language control via `.env`:
  - `OUTPUT_LANGUAGE=en|ko|ja|es|...`

## Quick Start
- Beginner (English): [docs/manuals/MANUAL_FIRSTTIME_EN.md](docs/manuals/MANUAL_FIRSTTIME_EN.md)
- Full operations (English): [docs/manuals/MANUAL_EN.md](docs/manuals/MANUAL_EN.md)
- Agent/tool integration (English): [docs/manuals/MANUAL_AGENT_EN.md](docs/manuals/MANUAL_AGENT_EN.md)
- Beginner (Korean): [docs/manuals/MANUAL_FIRSTTIME_KR.md](docs/manuals/MANUAL_FIRSTTIME_KR.md)
- Full operations (Korean): [docs/manuals/MANUAL_KR.md](docs/manuals/MANUAL_KR.md)
- Agent/tool integration (Korean): [docs/manuals/MANUAL_AGENT_KR.md](docs/manuals/MANUAL_AGENT_KR.md)

## Recommended First Path (Search-First, Local)
Generate your first personalized search result before email or automation setup.

1. Install dependencies:

```bash
pip install -r deps/requirements.txt
```

2. Run local launcher:

```bash
python app/local_ui_launcher.py
```

3. The browser opens automatically. On first run, Setup Wizard opens automatically.
4. Fill project description + Gemini key, then click `Save and Search Now`.

This verifies product value first without Gmail or GitHub Actions setup. After setup, the default path is:
- Click one button to search and open the latest result in a browser tab
- Or keep the local UI running and let the scheduled morning popup open automatically

## GitHub Actions Mode (Advanced Automation)
Use this only after local search quality is confirmed and you really want automation.

Required workflow files:
- `.github/workflows/paper-morning-digest.yml`
- `.github/workflows/paper-morning-bootstrap-topics.yml`

Required secrets:
- `PM_ENV_FILE` (full `.env` content)

Optional secret:
- `PM_TOPICS_JSON` (full `user_topics.json` content)
- `PM_PROJECTS_JSON` (project list only, for bootstrap query generation)

Tracked non-secret config:
- `config/projects.yaml` (project descriptions used for bootstrap/default onboarding)

## Important Settings
- `ONBOARDING_MODE`: `preview` (default) or `daily`.
- `SEARCH_INTENT_DEFAULT`: default local search mode (`best_match`, `whats_new`, `discovery`).
- `SEARCH_TIME_HORIZON_DEFAULT`: default local search horizon (`7d`, `30d`, `180d`, `1y`, `3y`, `5y`).
- `SEND_FREQUENCY` / `SEND_ANCHOR_DATE`: cadence policy.
- `LOOKBACK_HOURS`: legacy fallback window for digest-style collection.
- `LLM_MAX_CANDIDATES`: shortlist cap for listwise LLM reranking.
- `OUTPUT_LANGUAGE`: summary language for LLM-generated reason/core/usefulness text.
- `ENABLE_GOOGLE_SCHOLAR` + `GOOGLE_SCHOLAR_API_KEY`: optional SerpAPI source.

## Local Web Console
Main path for onboarding and preview-first setup:

```text
http://127.0.0.1:5050
```

## Agent Mode
Paper Morning can also be used as a local paper-search tool for research agents.

Security model:
- your agent gets `AGENT_API_TOKEN`
- Paper Morning keeps `GEMINI_API_KEY` or local backend credentials in `.env` / keyring
- the agent never needs to see raw provider keys

Interfaces:
- Local HTTP JSON endpoint: `POST /api/agent/search`
- CLI JSON mode: `python app/paper_digest_app.py --agent-search ...`

## Build Distribution Files
### Windows
```powershell
.\tools\build_windows.ps1
```

### Linux
```bash
chmod +x tools/build_linux.sh
./tools/build_linux.sh
```

## Demo Pages Deployment
This repo includes:
- demo generator script: `scripts/generate_demo_html.py`
- pages workflow: `.github/workflows/deploy-demo-pages.yml`

To publish demo on your fork:
1. Enable GitHub Pages source as **GitHub Actions**.
2. Run `deploy-demo-pages` workflow (or push to `main`).

Repo settings TODO (outside code):
- Fill GitHub About fields (`description`, `website`, `topics`).
- Publish the first tagged GitHub Release.

## Template-First Repository Setup
For global onboarding, prefer:
- `Use this template` -> create your own repository instance

Fallback (advanced):
- fork workflow if you explicitly need upstream fork linkage.

## Actions Cost Note (Private Repos)
- GitHub Free private repos include limited Actions minutes.
- If your workflow runs frequently (for example every 15 minutes), usage can exceed free minutes.
- Local-first preview and local scheduling are recommended for cost-safe onboarding.

## Troubleshooting (Quick)
- `Search query is empty`: generate and save topics/queries in Topic Editor.
- `PubMed 429`: retries are automatic, but adding `NCBI_API_KEY` is recommended.
- `Gemini model 404 / quota`: the live preview now retries multiple Gemini fallbacks automatically before surfacing an error.
- No email received: check sender/recipient addresses, spam folder, and auth config.

## Delivery Priority
1. Local Inbox (default, no email credentials required)
2. Gmail OAuth (optional advanced mode)
3. Gmail App Password (optional fallback)

Gmail app password docs:
- https://myaccount.google.com/apppasswords

## Documentation
- Beginner (English): [docs/manuals/MANUAL_FIRSTTIME_EN.md](docs/manuals/MANUAL_FIRSTTIME_EN.md)
- Full operations (English): [docs/manuals/MANUAL_EN.md](docs/manuals/MANUAL_EN.md)
- Beginner (Korean): [docs/manuals/MANUAL_FIRSTTIME_KR.md](docs/manuals/MANUAL_FIRSTTIME_KR.md)
- Full operations (Korean): [docs/manuals/MANUAL_KR.md](docs/manuals/MANUAL_KR.md)
- Korean README (legacy): [docs/manuals/README_KR.md](docs/manuals/README_KR.md)

## Contact
- nineclas@gmail.com
