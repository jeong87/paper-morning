# Paper Morning

![Paper Morning Logo](assets/paper-morning-logo.png)

Paper Morning is an automated paper briefing tool for medical/health AI researchers.
It fetches recent papers, ranks relevance with LLM + project context, and sends a concise email digest.

- Latest version: **[v0.5.0](VERSION)**
- License: `GNU AGPLv3` ([LICENSE](LICENSE))
- Privacy policy: [PRIVACY.md](PRIVACY.md)

## Live Demo
- Demo artifact in repo: [docs/demo/index.html](docs/demo/index.html)
- GitHub Pages URL format: `https://<github-username>.github.io/<repo-name>/demo/`
- If you see `404 There isn't a GitHub Pages site here`:
  1. Open repository `Settings -> Pages` and set source to **GitHub Actions**.
  2. Run workflow [deploy-demo-pages](.github/workflows/deploy-demo-pages.yml).
  3. Open the URL shown in the `github-pages` environment deployment.

## What It Does
1. Reads your project context and saved search queries.
2. Collects papers from arXiv, PubMed, Semantic Scholar, and optional Google Scholar (SerpAPI).
3. Scores each paper (1-10) with LLM relevance ranking.
4. Sends only high-relevance papers with short summaries by email.

## Key Features
- Personalized LLM relevance ranking using your active projects.
- Configurable cadence: `daily`, `every_3_days`, `weekly`.
- Duplicate suppression with history tracking (`sent_ids.json`).
- PubMed 429 retry/backoff handling.
- Gemini with automatic fallback (`3.1-pro` -> `3.1-flash` -> `2.5-flash`) and optional Cerebras backup.
- Output language control via `.env`:
  - `OUTPUT_LANGUAGE=en|ko|ja|es|...`

## Quick Start (Local Web Console)
1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Run web console:

```bash
python web_app.py --host 127.0.0.1 --port 5050
```

3. Open:

```text
http://127.0.0.1:5050
```

4. Configure keys/settings, then save topics/queries.

## GitHub Actions Mode (Recommended)
If you do not want your PC running 24/7, use Actions.

Required workflow files:
- `.github/workflows/paper-morning-digest.yml`
- `.github/workflows/paper-morning-bootstrap-topics.yml`

Required secrets:
- `PM_ENV_FILE` (full `.env` content)
- `PM_TOPICS_JSON` (full `user_topics.json` content)

Optional secret:
- `PM_PROJECTS_JSON` (project list only, for bootstrap query generation)

## Important Settings
- `SEND_FREQUENCY` / `SEND_ANCHOR_DATE`: cadence policy.
- `LOOKBACK_HOURS`: search window length.
- `LLM_MAX_CANDIDATES`: prefilter cap for LLM scoring.
- `OUTPUT_LANGUAGE`: summary language for LLM-generated reason/core/usefulness text.
- `ENABLE_GOOGLE_SCHOLAR` + `GOOGLE_SCHOLAR_API_KEY`: optional SerpAPI source.

## Build Distribution Files
### Windows
```powershell
.\build_windows.ps1
```

### Linux
```bash
chmod +x build_linux.sh
./build_linux.sh
```

## Demo Pages Deployment
This repo includes:
- demo generator script: `scripts/generate_demo_html.py`
- pages workflow: `.github/workflows/deploy-demo-pages.yml`

To publish demo on your fork:
1. Enable GitHub Pages source as **GitHub Actions**.
2. Run `deploy-demo-pages` workflow (or push to `main`).

## Troubleshooting (Quick)
- `Search query is empty`: generate and save topics/queries in Topic Editor.
- `PubMed 429`: retries are automatic, but adding `NCBI_API_KEY` is recommended.
- `Gemini model 404`: use a supported model (`gemini-3.1-pro` or `gemini-3.1-flash`).
- No email received: check sender/recipient addresses, spam folder, and auth config.

## Authentication Priority
1. Gmail App Password (current default for public beta users)
2. Google OAuth (available but currently not the default public path)

Gmail app password docs:
- https://myaccount.google.com/apppasswords

## Documentation
- Beginner (Korean): [docs/manuals/MANUAL_FIRSTTIME_KR.md](docs/manuals/MANUAL_FIRSTTIME_KR.md)
- Full operations (Korean): [docs/manuals/MANUAL_KR.md](docs/manuals/MANUAL_KR.md)
- Korean README (legacy): [docs/manuals/README_KR.md](docs/manuals/README_KR.md)

## Contact
- nineclas@gmail.com
