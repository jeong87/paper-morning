# Privacy Policy (Local App)

Last updated: 2026-03-06

## Summary
- This app runs on your local machine.
- The app does not send your data to a vendor-owned backend server operated by this project.
- External network calls occur only to public literature APIs and user-configured AI/email providers.

## What is stored locally
- `.env` (settings + secret references or credentials)
- `user_topics.json` (projects/topics/queries)
- `sent_ids.json` (dedupe history)
- `paper-morning.log` (runtime logs)

When `USE_KEYRING=true` (default), secret fields are stored in OS keychain where available,
and `.env` keeps reference values (for example, `keyring://GEMINI_API_KEY`).

These files are stored in per-user app data folders:
- Windows: `%APPDATA%\paper-morning`
- Linux: `~/.config/paper-morning`
- macOS: `~/Library/Application Support/paper-morning`

## External destinations (when enabled/configured)
- arXiv API: `https://export.arxiv.org/api/query`
- PubMed (NCBI E-utilities):
  - `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi`
  - `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi`
  - `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi`
- Semantic Scholar API:
  - `https://api.semanticscholar.org/graph/v1/paper/search`
- Google Scholar via SerpAPI (if enabled/configured):
  - `https://serpapi.com/search.json`
- Google Gemini API (if `GEMINI_API_KEY` is set)
- Cerebras API (if fallback is enabled and `CEREBRAS_API_KEY` is set)
- Gmail SMTP (`smtp.gmail.com:465`) for email delivery

## Data sent to external services
- Literature queries from `user_topics.json` (arXiv/PubMed/Semantic Scholar/Google Scholar query strings)
- Candidate paper metadata (title/abstract/etc.) to LLM providers for relevance scoring/summarization
- Email content to Gmail SMTP for delivery

## Data not collected by this project
- No centralized user account system
- No centralized telemetry/analytics endpoint maintained by this project
- No remote storage by this project

## User responsibility
- Keep API keys/app passwords private.
- Do not share `.env` with others.
- Review each third-party provider's terms and privacy policy separately.
