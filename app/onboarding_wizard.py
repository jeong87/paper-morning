import getpass
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List

from paper_digest_app import (
    CEREBRAS_API_BASE_DEFAULT,
    bootstrap_runtime_files,
    normalize_delivery_mode,
    enforce_private_file_permissions,
    get_default_data_dir,
    normalize_relevance_mode,
    run_digest,
    load_config,
    store_secret_value,
)
from projects_config import DEFAULT_PROJECTS_CONFIG_FILE, write_projects_config


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


def prompt_relevance_mode(default: str = "balanced") -> str:
    while True:
        value = prompt_text(
            "Relevance mode (strict / balanced / discovery)",
            default=default,
            required=True,
        )
        lowered = value.strip().lower()
        if lowered in {"strict", "balanced", "discovery"}:
            normalized = normalize_relevance_mode(lowered)
            return normalized
        print("Please choose strict, balanced, or discovery.")


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
        relevance_mode = prompt_relevance_mode(default="balanced")

        arxiv_query = prompt_text(
            "arXiv query (optional now, but recommended before local search)",
            default="",
            required=False,
        )
        pubmed_query = prompt_text(
            "PubMed query (optional now, but recommended before local search)",
            default="",
            required=False,
        )
        semantic_query = prompt_text(
            "Semantic Scholar query (optional now, but recommended)",
            default="",
            required=False,
        )

        topic = {"name": name, "keywords": keywords, "relevance_mode": relevance_mode}
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
        f"DELIVERY_MODE={values_to_write['DELIVERY_MODE']}",
        f"AUTO_OPEN_DIGEST_WINDOW={values_to_write['AUTO_OPEN_DIGEST_WINDOW']}",
        "",
        f"GMAIL_ADDRESS={values_to_write['GMAIL_ADDRESS']}",
        f"GMAIL_APP_PASSWORD={values_to_write['GMAIL_APP_PASSWORD']}",
        f"RECIPIENT_EMAIL={values_to_write['RECIPIENT_EMAIL']}",
        "",
        f"TIMEZONE={values_to_write['TIMEZONE']}",
        f"SEND_HOUR={values_to_write['SEND_HOUR']}",
        f"SEND_MINUTE={values_to_write['SEND_MINUTE']}",
        f"SEARCH_INTENT_DEFAULT={values_to_write['SEARCH_INTENT_DEFAULT']}",
        f"SEARCH_TIME_HORIZON_DEFAULT={values_to_write['SEARCH_TIME_HORIZON_DEFAULT']}",
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
        f"PROJECTS_CONFIG_FILE={values_to_write['PROJECTS_CONFIG_FILE']}",
        f"USER_TOPICS_FILE={values_to_write['USER_TOPICS_FILE']}",
        f"ONBOARDING_MODE={values_to_write['ONBOARDING_MODE']}",
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
    print("=== Paper Morning Preview-First Onboarding Wizard ===")
    env_path, _ = bootstrap_runtime_files()
    print("This wizard creates .env + config/projects.yaml + user_topics.json.\n")
    print(f"Env path: {env_path}\n")

    print("[Step 1] Project description")
    project_name = prompt_text("What are you working on? (project name)", required=True)
    project_context = prompt_text("Project context (goal/method/constraints)", required=True)
    project_keywords = parse_keywords(prompt_text("Optional keywords (comma separated)", default=""))
    projects = [{"name": project_name, "context": project_context, "keywords": project_keywords}]

    print("\n[Step 2] Search defaults")
    max_papers = prompt_int("How many papers per search result?", 5, 1, 50)
    output_language = prompt_text("Output language (en/ko/ja/es/...)", default="en")
    search_intent_default = prompt_text(
        "Default search intent (best_match / whats_new / discovery)",
        default="best_match",
        required=True,
    ).strip().lower()
    if search_intent_default not in {"best_match", "whats_new", "discovery"}:
        search_intent_default = "best_match"
    search_time_horizon_default = prompt_text(
        "Default time horizon (7d / 30d / 180d / 1y / 3y / 5y)",
        default="1y",
        required=True,
    ).strip().lower()
    if search_time_horizon_default not in {"7d", "30d", "180d", "1y", "3y", "5y"}:
        search_time_horizon_default = "1y"

    print("\n[Step 3] LLM key for query generation + summaries")
    gemini_api_key = prompt_text("Gemini API key (required for preview-first flow)", required=True, secret=True)
    enable_gemini_advanced_reasoning = prompt_yes_no(
        "Use advanced reasoning mode (Gemini 3.1 Pro)?",
        default_yes=True,
    )
    gemini_model = prompt_text("Gemini model", default="gemini-3.1-flash")
    enable_cerebras_fallback = prompt_yes_no(
        "Enable Cerebras fallback when Gemini fails?",
        default_yes=True,
    )
    cerebras_api_key = ""
    cerebras_model = "gpt-oss-120b"
    cerebras_api_base = CEREBRAS_API_BASE_DEFAULT
    if enable_cerebras_fallback:
        cerebras_api_key = prompt_text("Cerebras API key (optional)", default="", required=False, secret=True)
        cerebras_model = prompt_text("Cerebras model", default="gpt-oss-120b")
        cerebras_api_base = prompt_text("Cerebras API base", default=CEREBRAS_API_BASE_DEFAULT)

    print("\n[Step 4] Optional morning popup / email settings")
    timezone_name = prompt_text("Timezone (e.g. America/New_York, Europe/London, Asia/Seoul)", default="UTC")
    send_hour = prompt_int("Send hour (0-23)", 9, 0, 23)
    send_minute = prompt_int("Send minute (0-59)", 0, 0, 59)
    auto_open_digest_window = prompt_yes_no("Open the saved search result automatically at the scheduled time when the app is running?", default_yes=True)
    configure_email_now = prompt_yes_no("Configure Gmail delivery now? (optional)", default_yes=False)

    gmail_address = ""
    recipient_email = ""
    gmail_app_password = ""
    enable_google_oauth = False
    google_oauth_use_for_gmail = True
    google_oauth_client_id = ""
    google_oauth_client_secret = ""
    google_oauth_redirect_uri = ""
    delivery_mode = "local_inbox"
    if configure_email_now:
        raw_delivery_mode = prompt_text(
            "Delivery mode (gmail_oauth / gmail_app_password)",
            default="gmail_oauth",
            required=True,
        )
        delivery_mode = normalize_delivery_mode(raw_delivery_mode)
        gmail_address = prompt_text("Gmail address", required=True)
        recipient_email = prompt_text("Recipient email", default=gmail_address, required=True)
        enable_google_oauth = delivery_mode == "gmail_oauth"
        if enable_google_oauth:
            google_oauth_client_id = prompt_text("Google OAuth Client ID", required=True)
            google_oauth_client_secret = prompt_text("Google OAuth Client Secret", required=True, secret=True)
            google_oauth_redirect_uri = prompt_text(
                "Google OAuth Redirect URI (optional)",
                default="",
                required=False,
            )
            gmail_app_password = prompt_text("Gmail App Password (optional fallback)", default="", secret=True)
        else:
            gmail_app_password = prompt_text("Gmail App Password (16 chars)", required=True, secret=True)

    use_keyring = prompt_yes_no("Store secrets in OS keychain when available?", default_yes=True)

    lookback_hours = 24
    min_relevance_score = 6.0
    arxiv_max = 25
    pubmed_max = 25
    enable_semantic_scholar = True
    semantic_scholar_api_key = ""
    semantic_scholar_max_results = 20
    max_search_queries = 4
    send_now_cooldown_seconds = 300
    sent_history_days = 14
    ncbi_api_key = ""
    web_password = ""
    allow_insecure_remote_web = False
    topics_file = "user_topics.json"
    projects_config_file = DEFAULT_PROJECTS_CONFIG_FILE

    env_values = {
        "GMAIL_ADDRESS": gmail_address,
        "GMAIL_APP_PASSWORD": gmail_app_password,
        "RECIPIENT_EMAIL": recipient_email,
        "DELIVERY_MODE": delivery_mode,
        "AUTO_OPEN_DIGEST_WINDOW": "true" if auto_open_digest_window else "false",
        "TIMEZONE": timezone_name,
        "SEND_HOUR": str(send_hour),
        "SEND_MINUTE": str(send_minute),
        "SEARCH_INTENT_DEFAULT": search_intent_default,
        "SEARCH_TIME_HORIZON_DEFAULT": search_time_horizon_default,
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
        "PROJECTS_CONFIG_FILE": projects_config_file,
        "USER_TOPICS_FILE": topics_file,
        "ONBOARDING_MODE": "preview" if delivery_mode == "local_inbox" else "daily",
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
        "ENABLE_LLM_AGENT": "true",
        "GEMINI_API_KEY": gemini_api_key,
        "ENABLE_GEMINI_ADVANCED_REASONING": "true" if enable_gemini_advanced_reasoning else "false",
        "GEMINI_MODEL": gemini_model,
        "OUTPUT_LANGUAGE": output_language,
        "ENABLE_CEREBRAS_FALLBACK": "true" if enable_cerebras_fallback else "false",
        "CEREBRAS_API_KEY": cerebras_api_key,
        "CEREBRAS_MODEL": cerebras_model,
        "CEREBRAS_API_BASE": cerebras_api_base,
        "GEMINI_MAX_PAPERS": "5",
        "LLM_RELEVANCE_THRESHOLD": "6",
        "LLM_BATCH_SIZE": "5",
        "LLM_MAX_CANDIDATES": "30",
    }

    topics_path = (env_path.parent / topics_file).resolve()
    projects_path = (env_path.parent / projects_config_file).resolve()

    if env_path.exists():
        backup = env_path.with_name(env_path.name + ".bak")
        shutil.copy2(env_path, backup)
        print(f"Existing .env backed up to: {backup}")

    if topics_path.exists():
        backup = topics_path.with_name(topics_path.name + ".bak")
        shutil.copy2(topics_path, backup)
        print(f"Existing {topics_file} backed up to: {backup}")

    write_env_file(env_path, env_values)
    write_projects_config(projects_path, projects)
    topics_path.write_text(
        json.dumps({"projects": projects, "topics": []}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    enforce_private_file_permissions(topics_path)

    print("\nSetup complete (preview-first).")
    print(f"Saved env: {env_path}")
    print(f"Saved projects config: {projects_path}")
    print(f"Saved topics scaffold: {topics_path}")
    print("Next steps (recommended):")
    print("1) python app/web_app.py --host 127.0.0.1 --port 5050")
    print("2) Open /setup, click 'Save and Search Now'")
    print("3) After preview quality check, optionally enable morning popup or Gmail delivery")

    if prompt_yes_no("Run local dry-run preview now? (topics must be generated first in web setup)", default_yes=False):
        try:
            config = load_config(require_email_credentials=False)
            output = run_digest(config, dry_run=True, print_dry_run_output=False)
            preview_file = get_default_data_dir() / "onboarding_preview.txt"
            preview_file.parent.mkdir(parents=True, exist_ok=True)
            preview_file.write_text(output, encoding="utf-8")
            print(f"Dry-run completed. Preview text saved: {preview_file}")
        except Exception as exc:
            print(f"Dry-run preview failed: {exc}")
            print("Tip: open Web Setup and generate preview once to bootstrap topic queries.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
