# Paper Morning Beginner Manual (Preview-First)

This guide is for first-time users.
The goal is simple: **get your first personalized digest preview first**.
Automation and email can be enabled after preview quality is confirmed.

## 0) 5-minute checklist
1. One Gemini API key
2. Python 3.11+
3. This repository on your machine
4. (Optional later) Gmail + GitHub account

## 1) First success target
Do this first:
- Enter your project description
- Generate one digest preview

Do this later:
- Configure email delivery
- Configure GitHub Actions automation

## 2) Create a Gemini API key
1. Open Google AI Studio
2. Click `Get API key`
3. Copy and store the key

Link:
- https://aistudio.google.com/app/apikey

## 3) Generate your first preview (local, recommended)
1. Install dependencies:

```bash
pip install -r deps/requirements.txt
```

2. Run web console:

```bash
python app/web_app.py --host 127.0.0.1 --port 5050
```

3. Open:

```text
http://127.0.0.1:5050/setup
```

4. Fill these required fields:
- Onboarding mode: `Preview mode`
- Project name
- Project context
- Optional keywords
- Gemini API key

5. Click `Save and Preview Now`
6. Go to Dashboard and check:
- `Latest Preview Output`
- top paper cards and diagnostics

If this preview looks relevant, move to optional steps below.

## 4) Optional: enable email delivery (after preview)
In `/setup`, open **Automation + email transport (advanced)** and fill:
- `GMAIL_ADDRESS`
- `RECIPIENT_EMAIL`
- `GMAIL_APP_PASSWORD` (SMTP mode)
- timezone and send-time settings

Gmail app password docs:
- https://myaccount.google.com/apppasswords

## 5) Optional: enable GitHub Actions automation
### 5-1) Create your own repo from template (recommended)
Use **Use this template** on GitHub instead of Fork for onboarding.

### 5-2) Enable workflows
In your new repo:
1. Open `Actions`
2. (First time only) click `I understand my workflows, go ahead and enable them`

### 5-3) Add secrets
Path:
- `Repository > Settings > Secrets and variables > Actions > New repository secret`

Required:
1. `PM_ENV_FILE` (full `.env` style block)

Optional:
1. `PM_TOPICS_JSON` (full `user_topics.json` block)
2. `PM_PROJECTS_JSON` (project list block for bootstrap)

Notes:
- Non-secret project config can stay in tracked file: `config/projects.yaml`
- `PM_TOPICS_JSON` is no longer mandatory for preview-first migration

### 5-4) Manual first run
1. Run `paper-morning-digest`
2. Set `Run mode` = `dry_run`
3. Confirm preview/log output
4. Only after email setup, run once with `Run mode` = `send_now`

## 6) Cost/safety note for private repos
- Private repos have limited free GitHub Actions minutes.
- High-frequency schedules can consume monthly quota quickly.
- Local-first preview/setup is the safest starter path.

## 7) Quick troubleshooting
1. `Search query is empty`
- Cause: no generated/saved topic queries yet
- Fix: run preview from setup (auto-bootstrap), or generate/save in Topic Editor

2. `No LLM relevance reason generated`
- Cause: LLM summary disabled or LLM call failed/fallback exhausted
- Fix: verify `GEMINI_API_KEY`, model, and `ENABLE_LLM_AGENT=true`

3. `Missing required env vars for email`
- Cause: email fields are empty
- Fix: expected if preview-only mode; fill email fields only when enabling delivery

4. `PM_TOPICS_JSON is not valid JSON`
- Cause: malformed JSON in secret
- Fix: validate JSON syntax (`"`, `,`, `{}`, `[]`)

## 8) Contact
- nineclas@gmail.com
