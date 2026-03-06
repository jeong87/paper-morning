# Daily Paper Digest (Medical AI)

Version: `paper-morning v0.3.3`  
Release notes: `CHANGELOG.md`

This app sends a daily paper report by email.

Legal/Privacy:
- License: `LICENSE` (GNU AGPLv3)
- Privacy: `PRIVACY.md`

Pipeline (LLM-assisted, saved-query execution):
1. In `Topic Editor`, generate or manually edit arXiv/PubMed/Semantic Scholar queries, then save them to `user_topics.json`.
2. Daily run reads the saved queries as-is (no automatic per-run query regeneration).
3. Collect candidate papers from arXiv, PubMed, and (optionally) Semantic Scholar.
4. Use Gemini to score relevance for each paper (1-10).
5. Keep papers with score >= `LLM_RELEVANCE_THRESHOLD` (default 7).
6. For passed papers, include Korean summaries:
   - Core point (3-4 short lines)
   - Why useful for your project (3-4 short lines)

Fallback:
- If Gemini fails and Cerebras fallback is enabled/keyed, `gpt-oss-120b` is used as backup.
- If LLM calls still fail (or no LLM key exists), keyword ranking fallback is used.
- Already-sent paper IDs are tracked locally and excluded (default: last 14 days).
- If no search query is configured, digest run is blocked with a setup message.
- Runtime logs are persisted at `paper-morning.log` and viewable in Web Console `/logs`.

## GitHub Actions Mode (Cloud, Recommended)

If you do not want to keep your local PC on 24/7, use GitHub Actions.

- Workflow file: `.github/workflows/paper-morning-digest.yml`
- Daily schedule: `00:00 UTC` (= `09:00 KST`)
- Manual trigger supports runner selection:
  - `ubuntu-latest`
  - `windows-latest`
  - `macos-latest`
- Manual trigger supports:
  - `send_now` (real email)
  - `dry_run` (no email)

Required GitHub Secrets:
- `PM_ENV_FILE`: multiline `.env` content
- `PM_TOPICS_JSON`: full `user_topics.json` content

Runtime behavior in Actions:
1. `scripts/gha_prepare_runtime.py` restores runtime files under `ci_runtime/`.
2. App runs once via `python paper_digest_app.py --run-once` (or `--dry-run`).
3. Logs are uploaded as workflow artifacts.

See `MANUAL_KR.md` for full Korean setup instructions.

## Quick Start

1) Install dependencies

```bash
pip install -r requirements.txt
```

2) Run onboarding wizard (`.env` + `user_topics.json`)

```bash
python onboarding_wizard.py
```

3) Dry-run test

```bash
python paper_digest_app.py --run-once --dry-run
```

4) Real send now

```bash
python paper_digest_app.py --run-once
```

## Web Console

Run local web UI (Python):

```bash
python web_app.py --host 127.0.0.1 --port 5050
```

One-click local launcher (opens browser automatically):

```bat
start_web_console.bat
```

Linux/macOS (Python environment):

```bash
./start_web_console.sh
```

Open browser:

```text
http://127.0.0.1:5050
```

First launch behavior:
- If core settings are missing, Web Console redirects to `Setup Wizard`.
- `Send Now` is protected by cooldown (`SEND_NOW_COOLDOWN_SECONDS`, default 300s).
- Home page includes `Windows Task` action to register Windows Task Scheduler automatically.
- Home page now includes Google OAuth connection/status panel (`Google 로그인 연결` / `연결 해제`).

## Local vs Web Hosting

- Local PC mode: your computer must be ON at send time (e.g., 09:00).
- Hosted web mode: if deployed to an always-on server, your local PC does not need to be ON.
- Security:
  - non-local host (`--host` not `127.0.0.1`) is blocked by default.
  - set `ALLOW_INSECURE_REMOTE_WEB=true` + `WEB_PASSWORD` only for controlled temporary testing.
  - production remote use should be behind HTTPS reverse proxy.

## Config Persistence (Packaged App)

- Packaged executables now store `.env` and `user_topics.json` in a per-user data folder.
- On first launch, legacy settings in the executable folder are auto-migrated.
- This prevents settings loss when replacing `dist` files during updates.
- Source launcher (`start_web_console.bat` / `start_web_console.sh`) now uses the same per-user config path.

## Required Keys

Required:
- `GMAIL_ADDRESS`
- One of:
  - `GMAIL_APP_PASSWORD` (legacy SMTP mode), or
  - Google OAuth connection (`ENABLE_GOOGLE_OAUTH=true`, connected `GOOGLE_OAUTH_REFRESH_TOKEN`)

Recommended:
- `GEMINI_API_KEY` (for LLM-first ranking)

Optional:
- `NCBI_API_KEY` (higher PubMed throughput)
- `SEMANTIC_SCHOLAR_API_KEY` (Semantic Scholar quota)

## Main Environment Variables

- `ENABLE_LLM_AGENT=true`
- `ENABLE_GEMINI_ADVANCED_REASONING=false` (when `true`, force `gemini-3.1-pro`)
- `GEMINI_MODEL=gemini-3.1-flash`
- `USE_KEYRING=true`
- `ENABLE_GOOGLE_OAUTH=false`
- `GOOGLE_OAUTH_USE_FOR_GMAIL=true`
- `GOOGLE_OAUTH_CLIENT_ID=...`
- `GOOGLE_OAUTH_CLIENT_SECRET=...`
- `GOOGLE_OAUTH_REDIRECT_URI=http://127.0.0.1:5050/oauth/google/callback` (optional)
- `LLM_RELEVANCE_THRESHOLD=7`
- `LLM_BATCH_SIZE=5`
- `LLM_MAX_CANDIDATES=30` (runtime max: 50)
- `MAX_SEARCH_QUERIES_PER_SOURCE=4`
- `ENABLE_SEMANTIC_SCHOLAR=true`
- `SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY=20`
- `MAX_PAPERS=5`

See `.env.example` for the full list.

## Google Auto-Connect (OAuth)

If you want "Google login -> automatic Gmail linkage" without app-password:

1. In Google Cloud Console, create OAuth client credentials (Web application).
2. Add Authorized Redirect URI:
   - `http://127.0.0.1:5050/oauth/google/callback`
   - (optional) `http://localhost:5050/oauth/google/callback`
3. In Web Console `Settings`, set:
   - `ENABLE_GOOGLE_OAUTH=true`
   - `GOOGLE_OAUTH_CLIENT_ID`
   - `GOOGLE_OAUTH_CLIENT_SECRET`
4. Click `Google 로그인 연결` and complete consent.
5. The app stores refresh token (`GOOGLE_OAUTH_REFRESH_TOKEN`) and uses Gmail API send path automatically.

Distributor mode (recommended for beta/public users):
- Put `google_oauth_bundle.json` (with `client_id`, `client_secret`, optional `redirect_uri`) next to the executable.
- End users can then click `Google 로그인 연결` directly from **Home** without manually entering client ID/secret in Settings.

Notes:
- If OAuth send fails, app falls back to SMTP only when `GMAIL_APP_PASSWORD` exists.
- With `USE_KEYRING=true`, OAuth secrets are stored via OS keychain reference.

## user_topics.json format

```json
{
  "projects": [
    {
      "name": "Retina Stroke/CAC",
      "context": "Fundus-based stroke and CAC risk prediction pipeline."
    }
  ],
  "topics": [
    {
      "name": "Retina + Stroke/CAC",
      "keywords": ["fundus", "retina", "stroke", "cac"],
      "arxiv_query": "(all:fundus OR all:retina) AND (all:stroke OR all:CAC)",
      "pubmed_query": "(fundus OR retina) AND (stroke OR CAC)",
      "semantic_scholar_query": "fundus retina stroke CAC risk prediction deep learning"
    }
  ]
}
```

- `projects` is used as LLM prompt context (relevance scoring/summarization + query generation button in Topic Editor).
- `topics` stores the single active query state used by daily runs.

## Windows Packaging

Build executables:

```powershell
.\build_windows.ps1
```

Main files for end users:
- `dist\PaperDigestLocalUI.exe` (double-click: server starts + browser opens)
- `dist\PaperDigestSetup.exe` (interactive setup wizard)
- `dist\PaperDigest.exe` (CLI scheduler/one-shot sender)
- `dist\.env.example`, `dist\google_oauth_bundle.template.json`, `dist\user_topics.template.json`, `dist\MANUAL_KR.md`, `dist\LICENSE`, `dist\PRIVACY.md` (support files)

Register daily task (09:00):

```powershell
.\register_task.ps1 -UseExe -RunAt "09:00" -TaskName "DailyPaperDigest"
```

## Linux Packaging

Build executables on Linux:

```bash
chmod +x build_linux.sh
./build_linux.sh
```

Main files for end users:
- `dist/PaperDigestLocalUI` (launch local web console)
- `dist/PaperDigestSetup` (interactive setup wizard)
- `dist/PaperDigest` (CLI scheduler/one-shot sender)
- `dist/.env.example`, `dist/google_oauth_bundle.template.json`, `dist/user_topics.template.json`, `dist/MANUAL_KR.md`, `dist/LICENSE`, `dist/PRIVACY.md` (support files)

Notes:
- Linux binary must be built on Linux.
- For daily 09:00 run, register cron/systemd timer on the target Linux machine.

