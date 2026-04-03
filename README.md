# Paper Morning

[![Paper Morning Logo](assets/papermorning2.png)](https://raw.githack.com/jeong87/paper-morning/main/docs/preview/index.html)

**[EN](README.md) | [KR](docs/manuals/README_KR.md)**

Paper Morning is a research-context paper search engine for medical and health AI work.
It turns a project description into search queries, retrieves papers, reranks them by practical relevance, and explains why they matter.

- Latest version: **[v0.7.1](VERSION)**
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

## Product Direction
Paper Morning is no longer centered on "send me papers every morning."

The core product is now:
- a human-facing on-demand paper search tool
- a local agent-facing paper search tool with structured JSON output

The old digest and email workflows still exist, but they are now optional follow-up features.

## 2-1 Human Search
Use Paper Morning when you want to check for relevant papers on demand.

What it supports:
- `What's New`: recent updates first
- `Best Match`: strongest-fit papers in the selected horizon
- `Discovery`: adjacent but transferable work
- Time horizons from `7d` to `5y`
- Local inbox storage and browser-based result viewing

Best fit for:
- researchers exploring a new direction
- people who want context-fit papers, not just the newest papers
- users who do not want to set up email first

## 2-2 Agent Search
Paper Morning can also act as a local paper-search tool for research agents.

What it supports:
- local HTTP JSON endpoint: `POST /api/agent/search`
- CLI JSON mode: `python app/paper_digest_app.py --agent-search ...`
- brokered local auth via `AGENT_API_TOKEN`
- Gemini or a local/self-hosted OPENAI-compatible backend

Security model:
- your agent gets only `AGENT_API_TOKEN`
- Paper Morning keeps `GEMINI_API_KEY` or local backend credentials in `.env` or OS keyring
- the agent never needs to see raw provider keys

Best fit for:
- literature review agents
- planning / scouting agents
- local tool pipelines that need structured paper search output

## How It Works
Shared engine for both human and agent paths:

1. Read research context
2. Generate source-specific search queries
3. Retrieve candidates from arXiv, PubMed, Semantic Scholar, and optional Google Scholar
4. Apply intent-aware horizon filtering
5. Build a shortlist
6. Run listwise LLM reranking across the shortlist
7. Return either:
   - HTML result view for humans
   - structured JSON for agents

## Start Here
- Live preview first: [Open Live Web Preview](https://raw.githack.com/jeong87/paper-morning/main/docs/preview/index.html)
- Human local usage: [docs/manuals/MANUAL_FIRSTTIME_EN.md](docs/manuals/MANUAL_FIRSTTIME_EN.md)
- Agent/tool usage: [docs/manuals/MANUAL_AGENT_EN.md](docs/manuals/MANUAL_AGENT_EN.md)
- Korean README: [docs/manuals/README_KR.md](docs/manuals/README_KR.md)

## Optional Workflows
These are still supported, but they are no longer the main product story.

### Local install and local UI
If you want to actually use Paper Morning on your machine:

```bash
pip install -r deps/requirements.txt
python app/local_ui_launcher.py
```

Main local UI:

```text
http://127.0.0.1:5050
```

### Local inbox and morning popup
You can keep the app running and let it open the default search result automatically at your scheduled time.

Relevant settings:
- `DELIVERY_MODE=local_inbox`
- `AUTO_OPEN_DIGEST_WINDOW=true`
- `SEARCH_INTENT_DEFAULT`
- `SEARCH_TIME_HORIZON_DEFAULT`

### Email delivery
Email is optional.

Priority:
1. Local Inbox
2. Gmail OAuth
3. Gmail App Password

Docs:
- Gmail app password: https://myaccount.google.com/apppasswords
- Full ops manual: [docs/manuals/MANUAL_EN.md](docs/manuals/MANUAL_EN.md)

### GitHub Actions automation
Use this only if you really want unattended automation without relying on a running local PC.

Required workflow files:
- `.github/workflows/paper-morning-digest.yml`
- `.github/workflows/paper-morning-bootstrap-topics.yml`

Required secret:
- `PM_ENV_FILE`

Optional secrets:
- `PM_TOPICS_JSON`
- `PM_PROJECTS_JSON`

Tracked non-secret config:
- `config/projects.yaml`

## Important Settings
- `SEARCH_INTENT_DEFAULT`: default local search mode
- `SEARCH_TIME_HORIZON_DEFAULT`: default local search horizon
- `LLM_MAX_CANDIDATES`: shortlist cap for listwise reranking
- `OUTPUT_LANGUAGE`: language for LLM-generated explanation fields
- `AGENT_API_TOKEN`: local broker token for agent mode
- `ENABLE_OPENAI_COMPAT_FALLBACK`: enable LM Studio / vLLM / other OpenAI-style local backend
- `ENABLE_GOOGLE_SCHOLAR` + `GOOGLE_SCHOLAR_API_KEY`: optional SerpAPI source

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
1. Enable GitHub Pages source as **GitHub Actions**
2. Run `deploy-demo-pages` workflow or push to `main`

## Template-First Repository Setup
For onboarding, prefer:
- `Use this template` -> create your own repository instance

Fallback:
- fork only if you explicitly need upstream fork linkage

## Actions Cost Note (Private Repos)
- GitHub Free private repos include limited Actions minutes
- frequent automation can exceed the free tier quickly
- local-first search and local scheduling remain the cheaper default path

## Troubleshooting (Quick)
- `Search query is empty`: generate and save topics/queries in Topic Editor
- `PubMed 429`: retries are automatic, but adding `NCBI_API_KEY` is recommended
- `Gemini model 404 / quota`: the preview and runtime try multiple Gemini fallbacks before failing
- Agent `403 Forbidden`: check `AGENT_API_TOKEN` and confirm the request is coming from the local machine
- No email received: check sender/recipient addresses, spam folder, and auth config

## Documentation
- Beginner (English): [docs/manuals/MANUAL_FIRSTTIME_EN.md](docs/manuals/MANUAL_FIRSTTIME_EN.md)
- Full operations (English): [docs/manuals/MANUAL_EN.md](docs/manuals/MANUAL_EN.md)
- Agent/tool integration (English): [docs/manuals/MANUAL_AGENT_EN.md](docs/manuals/MANUAL_AGENT_EN.md)
- Scoring policy (English): [docs/manuals/SCORING_POLICY_EN.md](docs/manuals/SCORING_POLICY_EN.md)
- Beginner (Korean): [docs/manuals/MANUAL_FIRSTTIME_KR.md](docs/manuals/MANUAL_FIRSTTIME_KR.md)
- Full operations (Korean): [docs/manuals/MANUAL_KR.md](docs/manuals/MANUAL_KR.md)
- Agent/tool integration (Korean): [docs/manuals/MANUAL_AGENT_KR.md](docs/manuals/MANUAL_AGENT_KR.md)
- Scoring policy (Korean): [docs/manuals/SCORING_POLICY_KR.md](docs/manuals/SCORING_POLICY_KR.md)
- Korean README: [docs/manuals/README_KR.md](docs/manuals/README_KR.md)

## Contact
- nineclas@gmail.com
