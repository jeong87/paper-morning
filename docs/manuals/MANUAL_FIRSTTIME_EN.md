# Paper Morning Beginner Manual

This guide is for first-time users.
If you follow the steps in order, GitHub Actions will send your digest automatically every morning, even when your PC is off.

## 0) 5-minute checklist
1. One Gmail account
2. One GitHub account
3. One Gemini API key
4. This repository in your GitHub account (fork or your own repo)

## 1) What to understand first
1. The digest job runs on GitHub Actions runners.
2. Your personal laptop does not need to stay on 24/7.
3. Delivery time follows your own timezone and send-time settings.
4. The critical setup is registering two repository secrets.

## 2) Create a Gmail app password (most important)
1. Enable 2-step verification on your Google account.
2. Open the app password page.
3. Generate a 16-character app password.
4. Save it without spaces.

Link:
- https://myaccount.google.com/apppasswords

Notes:
- This is not your normal Gmail login password.
- You must use an app password for SMTP mode.

## 3) Create a Gemini API key
1. Open Google AI Studio.
2. Click `Get API key`.
3. Copy and store the key.

Link:
- https://aistudio.google.com/app/apikey

## 4) Prepare your repository (fork recommended)
1. Open the Paper Morning repository page and click `Fork`.
2. Open your forked repository.
3. Continue all setup and runs from your fork.
4. **Important:** after forking, workflows can be disabled by default.
5. Open the `Actions` tab in your fork:
   - (first time only) click `I understand my workflows, go ahead and enable them`.
6. Confirm workflow names are visible in the left panel:
   - `paper-morning-bootstrap-topics`
   - `paper-morning-digest`
7. Confirm `.github/workflows/` exists in your fork.

## 5) Register required secrets
Path:
- `Repository > Settings > Secrets and variables > Actions > New repository secret`

Beginner clarification:
- You do **not** create many secrets for each env key.
- You only create **two** secrets.
- `PM_ENV_FILE` value = one full `.env-style` text block.
- `PM_TOPICS_JSON` value = one full JSON text block.

Required secret names:
1. `PM_ENV_FILE`
2. `PM_TOPICS_JSON`

### 5-1) Example `PM_ENV_FILE`
1. Click `New repository secret`
2. Name: `PM_ENV_FILE`
3. Secret (Value): paste the **entire block** below
4. Replace with your own values and save

```env
GMAIL_ADDRESS=your_sender@gmail.com
RECIPIENT_EMAIL=your_receiver@gmail.com
GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx

# Use your own IANA timezone (examples: America/New_York, Europe/London, Asia/Seoul)
TIMEZONE=America/New_York
SEND_HOUR=9
SEND_MINUTE=0
SEND_FREQUENCY=daily
SEND_ANCHOR_DATE=2026-01-01
LOOKBACK_HOURS=24

MAX_PAPERS=5
MAX_SEARCH_QUERIES_PER_SOURCE=4
ARXIV_MAX_RESULTS_PER_QUERY=25
PUBMED_MAX_IDS_PER_QUERY=25
ENABLE_SEMANTIC_SCHOLAR=true
SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY=20
ENABLE_GOOGLE_SCHOLAR=false
GOOGLE_SCHOLAR_MAX_RESULTS_PER_QUERY=10

ENABLE_LLM_AGENT=true
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.1-pro
ENABLE_GEMINI_ADVANCED_REASONING=true
LLM_BATCH_SIZE=5
LLM_MAX_CANDIDATES=30
LLM_RELEVANCE_THRESHOLD=6
OUTPUT_LANGUAGE=en

ENABLE_CEREBRAS_FALLBACK=true
CEREBRAS_API_KEY=
CEREBRAS_MODEL=gpt-oss-120b

NCBI_API_KEY=
SEMANTIC_SCHOLAR_API_KEY=
GOOGLE_SCHOLAR_API_KEY=
```

Where to place keys from Sections 2 and 3:
- Gmail app password from Section 2 -> `GMAIL_APP_PASSWORD=...` (no spaces)
- Gemini API key from Section 3 -> `GEMINI_API_KEY=...`
- If you want personal Korean digests -> set `OUTPUT_LANGUAGE=ko`
- For public default/example -> keep `OUTPUT_LANGUAGE=en`

### 5-2) Example `PM_TOPICS_JSON`
1. Click `New repository secret`
2. Name: `PM_TOPICS_JSON`
3. Secret (Value): paste the **entire JSON** below
4. Edit only project/topic content and save

```json
{
  "projects": [
    {
      "name": "Medical image segmentation automation",
      "context": "Automated lesion and organ segmentation from CT and MRI with robust generalization"
    },
    {
      "name": "Clinical note prognosis prediction",
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

JSON warning:
- Keep JSON syntax valid when editing (`"`, `,`, `{}`, `[]`).
- If syntax breaks, you will see `PM_TOPICS_JSON is not valid JSON`.

## 6) First run in 3 steps
Use the GitHub UI steps below (no code edit needed):

1. Open the `Actions` tab.
2. (First time only) click `I understand my workflows, go ahead and enable them`.
3. Select `paper-morning-bootstrap-topics` from the left panel.
4. Click `Run workflow` on the right.
5. Keep branch as `main`, choose options if needed, then click `Run workflow`.
6. Select `paper-morning-digest`.
7. Click `Run workflow`.
8. In Inputs:
   - set `Run mode` to `dry_run`
   - choose `Runner OS`
   - click `Run workflow`
9. Run it once more with:
   - `Run mode` = `send_now`

Note:
- `dry_run` / `send_now` are workflow input options.
- You do not edit source code or workflow yaml for this test.

Success criteria:
1. `dry_run` completes without errors.
2. `send_now` delivers an actual email.

## 7) Daily automation
No extra button is required.
The workflow already includes a scheduled trigger.
The workflow polls every 15 minutes, and the app sends only near your configured local time.
You should receive the next day digest automatically if secrets are valid.
If Actions is still disabled in your fork, daily automation will not run.

## 8) Quick troubleshooting
1. `Missing required env vars for email`
- Cause: incomplete `PM_ENV_FILE`
- Fix: re-save full env content in secret

2. `535 Username and Password not accepted`
- Cause: wrong account pair or normal password used
- Fix: use matching Gmail address + app password pair

3. `...gemini...generateContent Not Found`
- Cause: unsupported Gemini model name
- Fix: use `gemini-3.1-pro` or `gemini-3.1-flash`

4. `Search query is empty`
- Cause: empty `topics`/queries
- Fix: run bootstrap or update `PM_TOPICS_JSON`

5. PubMed 429
- Cause: API rate limiting
- Fix: add `NCBI_API_KEY` for more stable runs

## 9) Contact
- nineclas@gmail.com
