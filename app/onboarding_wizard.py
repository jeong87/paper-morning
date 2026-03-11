import getpass
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List

from paper_digest_app import (
    CEREBRAS_API_BASE_DEFAULT,
    bootstrap_runtime_files,
    enforce_private_file_permissions,
    store_secret_value,
)


DEFAULT_PROJECTS = [
    {
        "name": "Retina-based Stroke Prediction",
        "context": "Fundus image based stroke risk prediction.",
    },
    {
        "name": "Retina CAC > 0 Classification",
        "context": "Fundus image based classification of whether CAC score is greater than zero.",
    },
    {
        "name": "Endoscopy Foundation Model",
        "context": "Foundation model training for endoscopy videos.",
    },
    {
        "name": "Hand Hygiene Detection",
        "context": "CCTV-based handwashing detection in hospitals to prevent infection.",
    },
]


def prompt_text(
    label: str,
    default: str = "",
    required: bool = False,
    secret: bool = False,
) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        raw = (
            getpass.getpass(f"{label}{suffix}: ")
            if secret
            else input(f"{label}{suffix}: ")
        )
        value = raw.strip() or default.strip()
        if required and not value:
            print("This field is required.")
            continue
        return value


def prompt_int(label: str, default: int, min_value: int, max_value: int) -> int:
    while True:
        raw = input(f"{label} [{default}]: ").strip()
        value = default if not raw else raw
        try:
            parsed = int(value)
        except ValueError:
            print("Please enter an integer.")
            continue
        if parsed < min_value or parsed > max_value:
            print(f"Please enter a value between {min_value} and {max_value}.")
            continue
        return parsed


def prompt_float(label: str, default: float, min_value: float) -> float:
    while True:
        raw = input(f"{label} [{default}]: ").strip()
        value = default if not raw else raw
        try:
            parsed = float(value)
        except ValueError:
            print("Please enter a numeric value.")
            continue
        if parsed < min_value:
            print(f"Please enter a value >= {min_value}.")
            continue
        return parsed


def prompt_yes_no(label: str, default_yes: bool = True) -> bool:
    default_hint = "Y/n" if default_yes else "y/N"
    while True:
        raw = input(f"{label} [{default_hint}]: ").strip().lower()
        if not raw:
            return default_yes
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("Please answer y or n.")


def parse_keywords(raw: str) -> List[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def collect_topics() -> List[Dict[str, Any]]:
    topic_count = prompt_int(
        "How many topics do you want to prefill now? (0 allowed, can configure later in Topic Editor)",
        0,
        0,
        30,
    )
    topics: List[Dict[str, Any]] = []
    for idx in range(1, topic_count + 1):
        print(f"\nTopic #{idx}")
        name = prompt_text("Topic name", required=True)

        keywords: List[str] = []
        while not keywords:
            raw_keywords = prompt_text(
                "Keywords (comma separated, e.g. retina, stroke, risk prediction)",
                required=True,
            )
            keywords = parse_keywords(raw_keywords)
            if not keywords:
                print("Please provide at least one keyword.")

        arxiv_query = prompt_text(
            "arXiv query (optional now, but required before digest run)",
            default="",
            required=False,
        )
        pubmed_query = prompt_text(
            "PubMed query (optional now, but required before digest run)",
            default="",
            required=False,
        )
        semantic_query = prompt_text(
            "Semantic Scholar query (optional now, but recommended)",
            default="",
            required=False,
        )

        topic = {"name": name, "keywords": keywords}
        if arxiv_query:
            topic["arxiv_query"] = arxiv_query
        if pubmed_query:
            topic["pubmed_query"] = pubmed_query
        if semantic_query:
            topic["semantic_scholar_query"] = semantic_query
        topics.append(topic)

    return topics


def collect_projects() -> List[Dict[str, Any]]:
    if prompt_yes_no("Use built-in project context template?", default_yes=True):
        return DEFAULT_PROJECTS

    count = prompt_int("How many active projects do you want to describe?", 3, 1, 20)
    projects: List[Dict[str, Any]] = []
    for idx in range(1, count + 1):
        print(f"\nProject #{idx}")
        name = prompt_text("Project name", required=True)
        context = prompt_text(
            "Project context (current goals, methods, constraints)",
            required=True,
        )
        projects.append({"name": name, "context": context})
    return projects


def write_env_file(path: Path, values: Dict[str, str]) -> None:
    values_to_write = dict(values)
    use_keyring = str(values_to_write.get("USE_KEYRING", "true")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if use_keyring:
        for secret_key in [
            "GMAIL_APP_PASSWORD",
            "GEMINI_API_KEY",
            "CEREBRAS_API_KEY",
            "SEMANTIC_SCHOLAR_API_KEY",
            "WEB_PASSWORD",
            "GOOGLE_OAUTH_CLIENT_SECRET",
            "GOOGLE_OAUTH_REFRESH_TOKEN",
        ]:
            values_to_write[secret_key] = store_secret_value(
                secret_key,
                values_to_write.get(secret_key, ""),
            )

    lines = [
        f"GMAIL_ADDRESS={values_to_write['GMAIL_ADDRESS']}",
        f"GMAIL_APP_PASSWORD={values_to_write['GMAIL_APP_PASSWORD']}",
        f"RECIPIENT_EMAIL={values_to_write['RECIPIENT_EMAIL']}",
        "",
        f"TIMEZONE={values_to_write['TIMEZONE']}",
        f"SEND_HOUR={values_to_write['SEND_HOUR']}",
        f"SEND_MINUTE={values_to_write['SEND_MINUTE']}",
        "",
        f"LOOKBACK_HOURS={values_to_write['LOOKBACK_HOURS']}",
        f"MAX_PAPERS={values_to_write['MAX_PAPERS']}",
        f"MIN_RELEVANCE_SCORE={values_to_write['MIN_RELEVANCE_SCORE']}",
        f"ARXIV_MAX_RESULTS_PER_QUERY={values_to_write['ARXIV_MAX_RESULTS_PER_QUERY']}",
        f"PUBMED_MAX_IDS_PER_QUERY={values_to_write['PUBMED_MAX_IDS_PER_QUERY']}",
        f"ENABLE_SEMANTIC_SCHOLAR={values_to_write['ENABLE_SEMANTIC_SCHOLAR']}",
        f"SEMANTIC_SCHOLAR_API_KEY={values_to_write['SEMANTIC_SCHOLAR_API_KEY']}",
        f"SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY={values_to_write['SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY']}",
        f"MAX_SEARCH_QUERIES_PER_SOURCE={values_to_write['MAX_SEARCH_QUERIES_PER_SOURCE']}",
        "",
        f"NCBI_API_KEY={values_to_write['NCBI_API_KEY']}",
        f"USER_TOPICS_FILE={values_to_write['USER_TOPICS_FILE']}",
        f"WEB_PASSWORD={values_to_write['WEB_PASSWORD']}",
        f"ALLOW_INSECURE_REMOTE_WEB={values_to_write['ALLOW_INSECURE_REMOTE_WEB']}",
        f"USE_KEYRING={values_to_write['USE_KEYRING']}",
        f"ENABLE_GOOGLE_OAUTH={values_to_write['ENABLE_GOOGLE_OAUTH']}",
        f"GOOGLE_OAUTH_USE_FOR_GMAIL={values_to_write['GOOGLE_OAUTH_USE_FOR_GMAIL']}",
        f"GOOGLE_OAUTH_CLIENT_ID={values_to_write['GOOGLE_OAUTH_CLIENT_ID']}",
        f"GOOGLE_OAUTH_CLIENT_SECRET={values_to_write['GOOGLE_OAUTH_CLIENT_SECRET']}",
        f"GOOGLE_OAUTH_REFRESH_TOKEN={values_to_write['GOOGLE_OAUTH_REFRESH_TOKEN']}",
        f"GOOGLE_OAUTH_CONNECTED_EMAIL={values_to_write['GOOGLE_OAUTH_CONNECTED_EMAIL']}",
        f"GOOGLE_OAUTH_REDIRECT_URI={values_to_write['GOOGLE_OAUTH_REDIRECT_URI']}",
        f"SETUP_WIZARD_COMPLETED={values_to_write['SETUP_WIZARD_COMPLETED']}",
        f"SEND_NOW_COOLDOWN_SECONDS={values_to_write['SEND_NOW_COOLDOWN_SECONDS']}",
        f"SENT_HISTORY_DAYS={values_to_write['SENT_HISTORY_DAYS']}",
        "",
        f"ENABLE_LLM_AGENT={values_to_write['ENABLE_LLM_AGENT']}",
        f"GEMINI_API_KEY={values_to_write['GEMINI_API_KEY']}",
        f"ENABLE_GEMINI_ADVANCED_REASONING={values_to_write['ENABLE_GEMINI_ADVANCED_REASONING']}",
        f"GEMINI_MODEL={values_to_write['GEMINI_MODEL']}",
        f"OUTPUT_LANGUAGE={values_to_write['OUTPUT_LANGUAGE']}",
        f"ENABLE_CEREBRAS_FALLBACK={values_to_write['ENABLE_CEREBRAS_FALLBACK']}",
        f"CEREBRAS_API_KEY={values_to_write['CEREBRAS_API_KEY']}",
        f"CEREBRAS_MODEL={values_to_write['CEREBRAS_MODEL']}",
        f"CEREBRAS_API_BASE={values_to_write['CEREBRAS_API_BASE']}",
        f"GEMINI_MAX_PAPERS={values_to_write['GEMINI_MAX_PAPERS']}",
        f"LLM_RELEVANCE_THRESHOLD={values_to_write['LLM_RELEVANCE_THRESHOLD']}",
        f"LLM_BATCH_SIZE={values_to_write['LLM_BATCH_SIZE']}",
        f"LLM_MAX_CANDIDATES={values_to_write['LLM_MAX_CANDIDATES']}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    enforce_private_file_permissions(path)


def main() -> int:
    print("=== Paper Digest Onboarding Wizard ===")
    env_path, _ = bootstrap_runtime_files()
    print("This wizard will create .env and user_topics.json.\n")
    print(f"Env path: {env_path}\n")

    gmail_address = prompt_text("Gmail address", required=True)
    recipient_email = prompt_text("Recipient email", default=gmail_address, required=True)
    enable_google_oauth = prompt_yes_no(
        "Enable Google OAuth Gmail integration? (recommended for no-app-password setup)",
        default_yes=False,
    )
    if enable_google_oauth:
        print("Google OAuth mode selected. You can leave app password empty.")
        print("Refresh token will be saved after clicking 'Connect Google OAuth' in Web Console.\n")
        gmail_app_password = prompt_text(
            "Gmail App Password (optional fallback, can be blank)",
            default="",
            required=False,
            secret=True,
        )
    else:
        gmail_app_password = prompt_text("Gmail App Password (16 chars)", required=True, secret=True)

    timezone_name = prompt_text("Timezone (e.g. America/New_York, Europe/London, Asia/Seoul)", default="UTC")
    send_hour = prompt_int("Send hour (0-23)", 9, 0, 23)
    send_minute = prompt_int("Send minute (0-59)", 0, 0, 59)

    lookback_hours = prompt_int("Lookback hours", 24, 1, 720)
    max_papers = prompt_int("Max papers per email", 5, 1, 200)
    min_relevance_score = prompt_float("Min relevance score", 6.0, 0.0)
    arxiv_max = prompt_int("arXiv max results per query", 25, 1, 500)
    pubmed_max = prompt_int("PubMed max IDs per query", 25, 1, 500)
    enable_semantic_scholar = prompt_yes_no("Enable Semantic Scholar source?", default_yes=True)
    semantic_scholar_api_key = prompt_text(
        "Semantic Scholar API key (optional, improves quota)",
        default="",
        required=False,
        secret=True,
    )
    semantic_scholar_max_results = prompt_int(
        "Semantic Scholar max results per query",
        20,
        1,
        100,
    )
    max_search_queries = prompt_int("Max search queries per source", 4, 1, 20)
    send_now_cooldown_seconds = prompt_int("Send-now cooldown seconds", 300, 0, 86400)
    sent_history_days = prompt_int("Duplicate history days", 14, 1, 365)
    ncbi_api_key = prompt_text("NCBI API key (optional, improves PubMed throughput)", default="")
    web_password = prompt_text(
        "Web console password (optional, required only for non-local host)",
        default="",
        secret=True,
    )
    allow_insecure_remote_web = prompt_yes_no(
        "Allow insecure remote web host (0.0.0.0) without TLS? (NOT recommended)",
        default_yes=False,
    )
    use_keyring = prompt_yes_no(
        "Store secrets in OS keychain when available?",
        default_yes=True,
    )
    google_oauth_use_for_gmail = True
    google_oauth_client_id = ""
    google_oauth_client_secret = ""
    google_oauth_redirect_uri = ""
    if enable_google_oauth:
        google_oauth_client_id = prompt_text("Google OAuth Client ID", required=True)
        google_oauth_client_secret = prompt_text("Google OAuth Client Secret", required=True, secret=True)
        google_oauth_redirect_uri = prompt_text(
            "Google OAuth Redirect URI (leave empty to use local default)",
            default="",
            required=False,
        )
    enable_llm_summary = prompt_yes_no("Enable Gemini research assistant mode?", default_yes=True)
    gemini_api_key = ""
    enable_gemini_advanced_reasoning = True
    gemini_model = "gemini-3.1-flash"
    output_language = "en"
    enable_cerebras_fallback = True
    cerebras_api_key = ""
    cerebras_model = "gpt-oss-120b"
    cerebras_api_base = CEREBRAS_API_BASE_DEFAULT
    gemini_max_papers = 5
    llm_relevance_threshold = 7.0
    llm_batch_size = 8
    llm_max_candidates = 30
    if enable_llm_summary:
        gemini_api_key = prompt_text("Gemini API key", required=True, secret=True)
        enable_gemini_advanced_reasoning = prompt_yes_no(
            "Use advanced reasoning mode (Gemini 3.1 Pro)?",
            default_yes=True,
        )
        gemini_model = prompt_text("Gemini model", default="gemini-3.1-flash")
        output_language = prompt_text(
            "Summary output language code (e.g., en, ko, ja, es)",
            default="en",
        )
        enable_cerebras_fallback = prompt_yes_no(
            "Enable Cerebras fallback when Gemini fails?",
            default_yes=True,
        )
        if enable_cerebras_fallback:
            cerebras_api_key = prompt_text(
                "Cerebras API key (optional, set now or later in Settings)",
                default="",
                required=False,
                secret=True,
            )
            cerebras_model = prompt_text("Cerebras model", default="gpt-oss-120b")
            cerebras_api_base = prompt_text(
                "Cerebras API base",
                default=CEREBRAS_API_BASE_DEFAULT,
            )
        gemini_max_papers = prompt_int("Max papers kept after LLM scoring", 5, 1, 200)
        llm_relevance_threshold = prompt_float("LLM relevance pass threshold (1-10)", 7.0, 1.0)
        llm_batch_size = prompt_int("LLM batch size", 5, 1, 50)
        llm_max_candidates = prompt_int("Max candidates for LLM scoring", 30, 1, 80)

    topics = collect_topics()
    projects = collect_projects()
    topics_file = "user_topics.json"

    env_values = {
        "GMAIL_ADDRESS": gmail_address,
        "GMAIL_APP_PASSWORD": gmail_app_password,
        "RECIPIENT_EMAIL": recipient_email,
        "TIMEZONE": timezone_name,
        "SEND_HOUR": str(send_hour),
        "SEND_MINUTE": str(send_minute),
        "SEND_FREQUENCY": "daily",
        "SEND_ANCHOR_DATE": "2026-01-01",
        "LOOKBACK_HOURS": str(lookback_hours),
        "MAX_PAPERS": str(max_papers),
        "MIN_RELEVANCE_SCORE": str(min_relevance_score),
        "ARXIV_MAX_RESULTS_PER_QUERY": str(arxiv_max),
        "PUBMED_MAX_IDS_PER_QUERY": str(pubmed_max),
        "ENABLE_SEMANTIC_SCHOLAR": "true" if enable_semantic_scholar else "false",
        "SEMANTIC_SCHOLAR_API_KEY": semantic_scholar_api_key,
        "SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY": str(semantic_scholar_max_results),
        "ENABLE_GOOGLE_SCHOLAR": "false",
        "GOOGLE_SCHOLAR_API_KEY": "",
        "GOOGLE_SCHOLAR_MAX_RESULTS_PER_QUERY": "10",
        "MAX_SEARCH_QUERIES_PER_SOURCE": str(max_search_queries),
        "NCBI_API_KEY": ncbi_api_key,
        "USER_TOPICS_FILE": topics_file,
        "WEB_PASSWORD": web_password,
        "ALLOW_INSECURE_REMOTE_WEB": "true" if allow_insecure_remote_web else "false",
        "USE_KEYRING": "true" if use_keyring else "false",
        "ENABLE_GOOGLE_OAUTH": "true" if enable_google_oauth else "false",
        "GOOGLE_OAUTH_USE_FOR_GMAIL": "true" if google_oauth_use_for_gmail else "false",
        "GOOGLE_OAUTH_CLIENT_ID": google_oauth_client_id,
        "GOOGLE_OAUTH_CLIENT_SECRET": google_oauth_client_secret,
        "GOOGLE_OAUTH_REFRESH_TOKEN": "",
        "GOOGLE_OAUTH_CONNECTED_EMAIL": "",
        "GOOGLE_OAUTH_REDIRECT_URI": google_oauth_redirect_uri,
        "SETUP_WIZARD_COMPLETED": "true",
        "SEND_NOW_COOLDOWN_SECONDS": str(send_now_cooldown_seconds),
        "SENT_HISTORY_DAYS": str(sent_history_days),
        "ENABLE_LLM_AGENT": "true" if enable_llm_summary else "false",
        "GEMINI_API_KEY": gemini_api_key,
        "ENABLE_GEMINI_ADVANCED_REASONING": "true" if enable_gemini_advanced_reasoning else "false",
        "GEMINI_MODEL": gemini_model,
        "OUTPUT_LANGUAGE": output_language,
        "ENABLE_CEREBRAS_FALLBACK": "true" if enable_cerebras_fallback else "false",
        "CEREBRAS_API_KEY": cerebras_api_key,
        "CEREBRAS_MODEL": cerebras_model,
        "CEREBRAS_API_BASE": cerebras_api_base,
        "GEMINI_MAX_PAPERS": str(gemini_max_papers),
        "LLM_RELEVANCE_THRESHOLD": str(llm_relevance_threshold),
        "LLM_BATCH_SIZE": str(llm_batch_size),
        "LLM_MAX_CANDIDATES": str(llm_max_candidates),
    }

    topics_path = (env_path.parent / topics_file).resolve()

    if env_path.exists():
        backup = env_path.with_name(env_path.name + ".bak")
        shutil.copy2(env_path, backup)
        print(f"Existing .env backed up to: {backup}")

    if topics_path.exists():
        backup = topics_path.with_name(topics_path.name + ".bak")
        shutil.copy2(topics_path, backup)
        print(f"Existing {topics_file} backed up to: {backup}")

    write_env_file(env_path, env_values)
    topics_path.write_text(
        json.dumps({"projects": projects, "topics": topics}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    query_count = 0
    for topic in topics:
        if not isinstance(topic, dict):
            continue
        if (
            str(topic.get("arxiv_query", "")).strip()
            or str(topic.get("pubmed_query", "")).strip()
            or str(topic.get("semantic_scholar_query", "")).strip()
        ):
            query_count += 1

    print("\nSetup complete.")
    print(f"Saved env: {env_path}")
    print(f"Saved topics: {topics_path}")
    if query_count == 0:
        print(
            "No search query configured yet. Open Topic Editor and run 'Keyword / Query Generation' "
            "or enter queries manually before Send Now."
        )
    print("Next steps:")
    print("1) python app/paper_digest_app.py --run-once --dry-run")
    print("2) python app/paper_digest_app.py --run-once")
    print("3) python app/paper_digest_app.py  (always-on scheduler mode)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
