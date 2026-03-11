# Paper Morning Manual (GitHub Actions Operations)

Target audience:
- Users who want reliable daily digest delivery without keeping a local machine online
- Users who want controlled test runs on GitHub-hosted runners

This document is the full operations guide for GitHub Actions mode.

If you are new, start here first:
- `MANUAL_FIRSTTIME_EN.md`

## 1) Core behavior
- Delivery time follows your own timezone (`TIMEZONE`) and send time (`SEND_HOUR`, `SEND_MINUTE`)
- Works independently from your local PC power state
- Manual runs support runner OS selection:
  - `ubuntu-latest`
  - `windows-latest`
  - `macos-latest`
- Run modes:
  - `send_now`: send real email
  - `dry_run`: collect/rank only, no email send

## 2) Execution flow
1. A scheduled or manual GitHub Actions workflow starts.
2. Runtime files are reconstructed from secrets (`PM_ENV_FILE`, `PM_TOPICS_JSON`).
3. `app/paper_digest_app.py --run-once` executes.
4. Logs and artifacts are uploaded for inspection.

Main workflow:
- `.github/workflows/paper-morning-digest.yml`

## 3) Initial setup

### 3-1) Repository readiness
1. Fork this repo (recommended) or push it to your own repo.
2. Open the `Actions` tab and ensure workflows are enabled.
3. (First time after fork) if shown, click `I understand my workflows, go ahead and enable them`.
4. Ensure workflow files exist under `.github/workflows/`.

### 3-2) Register repository secrets
Path:
- `Repository > Settings > Secrets and variables > Actions`

Required:
1. `PM_ENV_FILE`
2. `PM_TOPICS_JSON`

Optional:
3. `PM_PROJECTS_JSON` (bootstrap convenience)

#### A) `PM_ENV_FILE` reference
```env
# Mail
GMAIL_ADDRESS=your_sender@gmail.com
RECIPIENT_EMAIL=your_receiver@gmail.com
GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx

# Schedule / Time
# Use your own IANA timezone (examples: America/New_York, Europe/London, Asia/Seoul)
TIMEZONE=America/New_York
SEND_HOUR=9
SEND_MINUTE=0
SEND_FREQUENCY=daily
SEND_ANCHOR_DATE=2026-01-01
LOOKBACK_HOURS=24

# Search / Selection
MAX_PAPERS=5
MAX_SEARCH_QUERIES_PER_SOURCE=4
ARXIV_MAX_RESULTS_PER_QUERY=25
PUBMED_MAX_IDS_PER_QUERY=25
ENABLE_SEMANTIC_SCHOLAR=true
SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY=20
ENABLE_GOOGLE_SCHOLAR=false
GOOGLE_SCHOLAR_MAX_RESULTS_PER_QUERY=10

# LLM
ENABLE_LLM_AGENT=true
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.1-pro
ENABLE_GEMINI_ADVANCED_REASONING=true
LLM_BATCH_SIZE=5
LLM_MAX_CANDIDATES=30
LLM_RELEVANCE_THRESHOLD=6
OUTPUT_LANGUAGE=en

# Fallback (optional)
ENABLE_CEREBRAS_FALLBACK=true
CEREBRAS_API_KEY=
CEREBRAS_MODEL=gpt-oss-120b

# Optional API keys
NCBI_API_KEY=
SEMANTIC_SCHOLAR_API_KEY=
GOOGLE_SCHOLAR_API_KEY=
```

Language note:
- Keep public defaults in repo as `en`.
- For personal Korean digests, set `OUTPUT_LANGUAGE=ko` in your own `PM_ENV_FILE`.

#### B) `PM_TOPICS_JSON` reference
```json
{
  "projects": [
    {
      "name": "Medical image segmentation automation",
      "context": "Automated lesion and organ segmentation from CT and MRI with robust generalization"
    },
    {
      "name": "Clinical NLP prognosis",
      "context": "Early risk prediction from EHR notes and structured clinical variables"
    }
  ],
  "topics": [
    {
      "name": "Medical Imaging AI",
      "keywords": ["medical imaging", "segmentation", "detection", "vision transformer", "deep learning"],
      "arxiv_query": "(all:\"medical imaging\" OR all:radiology) AND (all:segmentation OR all:detection) AND (all:\"vision transformer\" OR all:\"deep learning\")",
      "pubmed_query": "(medical imaging OR radiology) AND (segmentation OR detection) AND (deep learning OR transformer)",
      "semantic_scholar_query": "medical imaging segmentation detection vision transformer deep learning",
      "google_scholar_query": "medical imaging segmentation detection vision transformer deep learning"
    }
  ]
}
```

Important:
- Empty `topics` or missing source queries will block runs.
- Query lifecycle is user-managed; daily runs use saved query state.

## 4) Bootstrap workflow (recommended for first setup)
Workflow:
- `.github/workflows/paper-morning-bootstrap-topics.yml`

Steps:
1. Open Actions and run `paper-morning-bootstrap-topics`.
2. Keep `projects_lines` empty to use secrets as source:
  - Priority 1: `PM_PROJECTS_JSON`
  - Priority 2: `PM_TOPICS_JSON.projects`
3. Download artifact `generated_user_topics.json`.
4. Replace `PM_TOPICS_JSON` with that content.
5. Run digest workflow in `dry_run` mode to validate.

## 5) Automatic schedule
Configured cron:
- `*/15 * * * *` (UTC, every 15 minutes)

Delivery behavior:
- Workflow polling is frequent, but real delivery happens only when all checks pass:
  - local send-time window (`TIMEZONE` + `SEND_HOUR` + `SEND_MINUTE`)
  - cadence policy (`SEND_FREQUENCY` / `SEND_ANCHOR_DATE`)
  - local-date lock (only once per local date)
- `send_now` bypasses cadence for immediate testing

## 6) Manual run procedure
1. Open Actions.
2. Select `paper-morning-digest`.
3. Click `Run workflow`.
4. Choose:
  - Runner OS
  - Run mode (`dry_run` or `send_now`)
5. Monitor logs and artifact output.

Recommended test order:
1. `dry_run` on `ubuntu-latest`
2. `send_now` on `ubuntu-latest`
3. Optional compatibility checks on Windows/macOS runners

## 7) Output verification
- Actions step logs: real-time progress and errors
- Artifact: `paper-morning-logs-*`
  - Includes runtime data/log files for root-cause analysis

## 8) Operating changes
Most operations can be done by secret updates only (no code commit needed).

1. Change topics/queries:
- update `PM_TOPICS_JSON`

2. Change keys/mail/threshold/schedule:
- update `PM_ENV_FILE`

3. Apply immediately:
- run `paper-morning-digest` manually

## 9) Security recommendations
- Never commit plaintext secrets to code, docs, issues, or PR comments.
- Use private repos for personal operation when possible.
- Rotate app passwords and API keys periodically.
- Keep collaborator permissions minimal.

## 10) Common errors and fixes
1. `535 Username and Password not accepted`
- Use matching Gmail address + app password pair

2. `PM_TOPICS_JSON is not valid JSON`
- Validate JSON syntax and save again

3. `...gemini...generateContent Not Found`
- Replace model with supported one (`gemini-3.1-pro` / `gemini-3.1-flash`)

4. Repeated "no relevant papers"
- Increase `LOOKBACK_HOURS` (e.g., 120)
- Relax queries and threshold (`LLM_RELEVANCE_THRESHOLD`)

5. PubMed 429
- Retries/backoff are built in
- Add `NCBI_API_KEY` for stability

6. Google Scholar returns 0
- Confirm `ENABLE_GOOGLE_SCHOLAR=true`
- Confirm `GOOGLE_SCHOLAR_API_KEY` is set

## 11) Contact
- nineclas@gmail.com
