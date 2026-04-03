import argparse
import base64
import html
import json
import logging
import os
import re
import shutil
import smtplib
import stat
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple
from zoneinfo import ZoneInfo

import feedparser
import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import dotenv_values, load_dotenv
from xml.etree import ElementTree
from projects_config import DEFAULT_PROJECTS_CONFIG_FILE, read_projects_config
from scoring_policy import (
    LLM_RELEVANCE_MODE_DEFAULT,
    get_relevance_mode_policy,
    normalize_relevance_mode,
    relevance_mode_label,
    relevance_mode_threshold,
)

try:
    import keyring
except Exception:  # pragma: no cover - optional dependency
    keyring = None


ARXIV_API_URL = "https://export.arxiv.org/api/query"
PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
PUBMED_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
GOOGLE_SCHOLAR_SERPAPI_URL = "https://serpapi.com/search.json"
GEMINI_API_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
CEREBRAS_API_BASE_DEFAULT = "https://api.cerebras.ai/v1"
OPENAI_COMPAT_API_BASE_DEFAULT = ""
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SEND_API_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

HTTP_TIMEOUT_SECONDS = 30
GEMINI_TIMEOUT_SECONDS = 60
CEREBRAS_TIMEOUT_SECONDS = 60
ARXIV_MAX_RETRY_ATTEMPTS = 3
ARXIV_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
ARXIV_QUERY_INTERVAL_SECONDS = 1.0
ARXIV_MAX_RESULTS_HARD_LIMIT = 50
PUBMED_MAX_RETRY_ATTEMPTS = 4
PUBMED_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
PUBMED_QUERY_INTERVAL_NO_KEY_SECONDS = 0.45
PUBMED_QUERY_INTERVAL_WITH_KEY_SECONDS = 0.12
PUBMED_RETRY_BACKOFF_BASE_SECONDS = 1.0
PUBMED_RETRY_BACKOFF_MAX_SECONDS = 8.0
SEMANTIC_SCHOLAR_QUERY_INTERVAL_SECONDS = 1.0
SEMANTIC_SCHOLAR_MAX_RESULTS_HARD_LIMIT = 100
SEMANTIC_SCHOLAR_FIELDS = (
    "paperId,title,abstract,url,authors,publicationDate,year,externalIds"
)
GOOGLE_SCHOLAR_QUERY_INTERVAL_SECONDS = 1.2
GOOGLE_SCHOLAR_MAX_RESULTS_HARD_LIMIT = 20
ZERO_RESULT_RETRY_ATTEMPTS = 2
ZERO_RESULT_RETRY_SLEEP_SECONDS = 2.0
ARXIV_REQUEST_HEADERS = {
    "User-Agent": "PaperDigest/1.0 (contact: local-user)",
}
APP_DATA_DIR_NAME = "paper-morning"
ENV_PATH_ENV_KEY = "PAPER_DIGEST_ENV_PATH"
APP_DATA_DIR_ENV_KEY = "PAPER_DIGEST_DATA_DIR"
SECRET_REF_PREFIX = "keyring://"
KEYRING_SERVICE_NAME = "paper-morning"
GOOGLE_OAUTH_BUNDLE_FILENAME = "google_oauth_bundle.json"
INTERNAL_SCHEDULE_ADVANCE_MINUTES = 13
LLM_RELEVANCE_MODE_DEFAULT = "balanced"
DELIVERY_MODE_LOCAL_INBOX = "local_inbox"
DELIVERY_MODE_GMAIL_OAUTH = "gmail_oauth"
DELIVERY_MODE_GMAIL_APP_PASSWORD = "gmail_app_password"
SEARCH_INTENT_DEFAULT = "best_match"
SEARCH_TIME_HORIZON_DEFAULT = "1y"
TIME_HORIZON_OPTIONS: Dict[str, Dict[str, Any]] = {
    "7d": {"hours": 24 * 7, "label": "Last 7 days"},
    "30d": {"hours": 24 * 30, "label": "Last 30 days"},
    "180d": {"hours": 24 * 180, "label": "Last 6 months"},
    "1y": {"hours": 24 * 365, "label": "Last 1 year"},
    "3y": {"hours": 24 * 365 * 3, "label": "Last 3 years"},
    "5y": {"hours": 24 * 365 * 5, "label": "Last 5 years"},
}
SEARCH_INTENT_POLICIES: Dict[str, Dict[str, Any]] = {
    "best_match": {
        "label": "Best Match",
        "description": "Search within the selected time window and rank for strongest project fit.",
        "default_horizon": "1y",
        "horizon_options": ["180d", "1y", "3y", "5y"],
        "arxiv_sort": "relevance",
        "pubmed_sort": "relevance",
        "arxiv_max_results": 60,
        "pubmed_max_results": 80,
        "semantic_max_results": 40,
        "google_scholar_max_results": 20,
        "min_score": 6.0,
    },
    "whats_new": {
        "label": "What's New",
        "description": "Prefer the newest directly useful papers, widening the window only when needed.",
        "default_horizon": "30d",
        "horizon_options": ["7d", "30d", "180d", "1y"],
        "arxiv_sort": "submittedDate",
        "pubmed_sort": "pub date",
        "arxiv_max_results": 70,
        "pubmed_max_results": 90,
        "semantic_max_results": 45,
        "google_scholar_max_results": 20,
        "min_score": 6.0,
    },
    "discovery": {
        "label": "Discovery",
        "description": "Allow adjacent methods and high-upside transfer papers within a broader window.",
        "default_horizon": "3y",
        "horizon_options": ["180d", "1y", "3y", "5y"],
        "arxiv_sort": "relevance",
        "pubmed_sort": "relevance",
        "arxiv_max_results": 80,
        "pubmed_max_results": 100,
        "semantic_max_results": 50,
        "google_scholar_max_results": 25,
        "min_score": 5.5,
    },
}
WHATS_NEW_ADAPTIVE_STEPS = ["7d", "30d", "180d", "1y", "3y", "5y"]


def normalize_delivery_mode(raw: Any) -> str:
    value = clean_text(str(raw or "")).lower()
    if value in {"gmail_oauth", "oauth", "google_oauth"}:
        return DELIVERY_MODE_GMAIL_OAUTH
    if value in {"gmail_app_password", "gmail", "smtp", "app_password"}:
        return DELIVERY_MODE_GMAIL_APP_PASSWORD
    return DELIVERY_MODE_LOCAL_INBOX


def normalize_search_intent(raw: Any) -> str:
    value = clean_text(str(raw or "")).lower()
    if value in {"latest", "recent", "new", "whats_new", "what's new"}:
        return "whats_new"
    if value in {"discover", "discovery", "explore", "exploratory"}:
        return "discovery"
    return SEARCH_INTENT_DEFAULT


def get_search_intent_policy(intent: Any) -> Dict[str, Any]:
    return SEARCH_INTENT_POLICIES[normalize_search_intent(intent)]


def search_intent_label(intent: Any) -> str:
    return str(get_search_intent_policy(intent).get("label", "Best Match"))


def normalize_time_horizon_key(raw: Any, intent: Any = None) -> str:
    value = clean_text(str(raw or "")).lower()
    if value in TIME_HORIZON_OPTIONS:
        normalized = value
    elif value in {"6m", "half_year"}:
        normalized = "180d"
    elif value in {"12m"}:
        normalized = "1y"
    else:
        normalized = ""
    policy = get_search_intent_policy(intent)
    allowed = policy.get("horizon_options", [])
    if normalized and normalized in allowed:
        return normalized
    default_horizon = str(policy.get("default_horizon", SEARCH_TIME_HORIZON_DEFAULT))
    if default_horizon in TIME_HORIZON_OPTIONS:
        return default_horizon
    return SEARCH_TIME_HORIZON_DEFAULT


def time_horizon_hours(key: Any, intent: Any = None) -> int:
    normalized = normalize_time_horizon_key(key, intent)
    return int(TIME_HORIZON_OPTIONS.get(normalized, TIME_HORIZON_OPTIONS[SEARCH_TIME_HORIZON_DEFAULT])["hours"])


def time_horizon_label(key: Any, intent: Any = None) -> str:
    normalized = normalize_time_horizon_key(key, intent)
    return str(TIME_HORIZON_OPTIONS.get(normalized, TIME_HORIZON_OPTIONS[SEARCH_TIME_HORIZON_DEFAULT])["label"])


def delivery_mode_label(mode: str) -> str:
    normalized = normalize_delivery_mode(mode)
    if normalized == DELIVERY_MODE_GMAIL_OAUTH:
        return "Gmail OAuth"
    if normalized == DELIVERY_MODE_GMAIL_APP_PASSWORD:
        return "Gmail App Password"
    return "Local Inbox"


def delivery_requires_email(mode: str) -> bool:
    return normalize_delivery_mode(mode) in {
        DELIVERY_MODE_GMAIL_OAUTH,
        DELIVERY_MODE_GMAIL_APP_PASSWORD,
    }


@dataclass
class TopicProfile:
    name: str
    keywords: Dict[str, float]
    relevance_mode: str = LLM_RELEVANCE_MODE_DEFAULT


@dataclass
class ResearchProject:
    name: str
    context: str
    send_frequency: str = "daily"
    send_interval_days: int = 1


@dataclass
class Paper:
    paper_id: str
    title: str
    abstract: str
    url: str
    authors: List[str]
    published_at_utc: datetime
    source: str
    score: float = 0.0
    topic: str = ""
    project_name: str = ""
    relevance_mode: str = LLM_RELEVANCE_MODE_DEFAULT
    relevance_threshold: float = 0.0
    matched_keywords: List[str] = None
    llm_relevance_text: str = ""
    llm_core_point_text: str = ""
    llm_usefulness_text: str = ""
    llm_evidence_spans: List[str] = field(default_factory=list)


@dataclass
class SearchRequest:
    intent: str
    time_horizon_key: str
    time_horizon_hours: int
    intent_label: str
    time_horizon_label: str


@dataclass
class AppConfig:
    gmail_address: str
    gmail_app_password: str
    recipient_email: str
    delivery_mode: str
    auto_open_digest_window: bool
    enable_google_oauth: bool
    google_oauth_use_for_gmail: bool
    google_oauth_client_id: str
    google_oauth_client_secret: str
    google_oauth_refresh_token: str
    timezone_name: str
    send_hour: int
    send_minute: int
    send_time_window_minutes: int
    search_intent_default: str
    search_time_horizon_default: str
    max_papers: int
    lookback_hours: int
    min_relevance_score: float
    arxiv_max_results_per_query: int
    pubmed_max_ids_per_query: int
    ncbi_api_key: str
    topic_profiles: List[TopicProfile]
    research_projects: List[ResearchProject]
    arxiv_queries: List[str]
    pubmed_queries: List[str]
    semantic_scholar_queries: List[str]
    enable_semantic_scholar: bool
    semantic_scholar_api_key: str
    semantic_scholar_max_results_per_query: int
    google_scholar_queries: List[str]
    enable_google_scholar: bool
    google_scholar_api_key: str
    google_scholar_max_results_per_query: int
    enable_llm_agent: bool
    gemini_api_key: str
    gemini_model: str
    openai_compat_api_key: str
    openai_compat_model: str
    openai_compat_api_base: str
    enable_openai_compat_fallback: bool
    cerebras_api_key: str
    cerebras_model: str
    cerebras_api_base: str
    enable_cerebras_fallback: bool
    gemini_max_papers: int
    llm_relevance_threshold: float
    llm_max_candidates_base: int
    llm_max_candidates: int
    max_search_queries_per_source: int
    sent_history_days: int
    send_frequency: str
    send_interval_days: int
    send_anchor_date: str
    output_language: str

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)


@dataclass
class DigestStats:
    arxiv_candidates: int = 0
    pubmed_candidates: int = 0
    semantic_scholar_candidates: int = 0
    google_scholar_candidates: int = 0
    total_candidates: int = 0
    post_time_filter_candidates: int = 0
    ranking_mode: str = "keyword"
    ranking_threshold: float = 0.0
    scoring_candidates: int = 0
    scored_count: int = 0
    pass_count: int = 0
    score_buckets: Dict[str, int] = field(default_factory=dict)
    llm_fallback_reason: str = ""
    llm_fallback_score_buckets: Dict[str, int] = field(default_factory=dict)
    llm_fallback_scored_examples: List[str] = field(default_factory=list)
    estimated_llm_calls_upper_bound: int = 0
    duplicates_filtered: int = 0
    final_selected: int = 0
    query_strategy: str = "saved-topics"
    relevance_policy_summary: List[str] = field(default_factory=list)
    send_frequency: str = "daily"
    lookback_hours: int = 24
    llm_max_candidates_base: int = 0
    llm_max_candidates_effective: int = 0
    zero_candidate_recovery_steps: List[str] = field(default_factory=list)
    llm_agent_enabled: bool = False
    llm_provider_ready: bool = False
    scored_examples: List[str] = field(default_factory=list)
    project_cadence_summary: List[str] = field(default_factory=list)
    project_cadence_filtered_out: int = 0
    search_intent: str = SEARCH_INTENT_DEFAULT
    search_intent_label: str = "Best Match"
    requested_time_horizon_key: str = SEARCH_TIME_HORIZON_DEFAULT
    requested_time_horizon_label: str = "Last 1 year"
    window_used_hours: int = 0
    window_used_label: str = ""
    query_plan_label: str = ""
    search_notice: str = ""
    no_results_reason: str = ""


def mask_sensitive_text(text: str, extra_values: List[str] | None = None) -> str:
    masked = str(text or "")
    patterns = [
        (r"([?&](?:key|api_key)=)[^&\s]+", r"\1[REDACTED]"),
        (r"(authorization\s*:\s*bearer\s+)[^\s,;]+", r"\1[REDACTED]"),
        (r"(Bearer\s+)[^\s,;]+", r"\1[REDACTED]"),
        (r"(AIza[0-9A-Za-z_\-]{16,})", "[REDACTED]"),
    ]
    for pattern, repl in patterns:
        masked = re.sub(pattern, repl, masked, flags=re.IGNORECASE)
    for raw in extra_values or []:
        value = str(raw or "").strip()
        if value and len(value) >= 6:
            masked = masked.replace(value, "[REDACTED]")
    return masked


def resolve_secret_value(secret_name: str, raw_value: str) -> str:
    value = str(raw_value or "").strip()
    if not value:
        return ""
    if not value.lower().startswith(SECRET_REF_PREFIX):
        return value
    alias = value[len(SECRET_REF_PREFIX) :].strip() or secret_name
    if keyring is None:
        logging.warning("Secret reference exists but keyring is unavailable: %s", secret_name)
        return ""
    try:
        return str(keyring.get_password(KEYRING_SERVICE_NAME, alias) or "").strip()
    except Exception as exc:
        logging.warning("Failed to read secret from keyring for %s: %s", secret_name, mask_sensitive_text(str(exc)))
        return ""


def is_keyring_available() -> bool:
    return keyring is not None


def store_secret_value(secret_name: str, raw_value: str) -> str:
    value = str(raw_value or "").strip()
    if not value:
        return ""
    if value.lower().startswith(SECRET_REF_PREFIX):
        return value
    if keyring is None:
        return value
    try:
        keyring.set_password(KEYRING_SERVICE_NAME, secret_name, value)
        return f"{SECRET_REF_PREFIX}{secret_name}"
    except Exception as exc:
        logging.warning(
            "Failed to store secret in keyring for %s. Falling back to .env plaintext. reason=%s",
            secret_name,
            mask_sensitive_text(str(exc)),
        )
        return value


def can_use_google_oauth_for_gmail(config: AppConfig) -> bool:
    return (
        config.enable_google_oauth
        and config.google_oauth_use_for_gmail
        and bool(config.google_oauth_client_id)
        and bool(config.google_oauth_client_secret)
        and bool(config.google_oauth_refresh_token)
    )


def refresh_google_oauth_access_token(config: AppConfig) -> str:
    if not can_use_google_oauth_for_gmail(config):
        raise ValueError("Google OAuth Gmail sending is not fully configured.")
    try:
        response = requests.post(
            GOOGLE_OAUTH_TOKEN_URL,
            data={
                "client_id": config.google_oauth_client_id,
                "client_secret": config.google_oauth_client_secret,
                "refresh_token": config.google_oauth_refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"Google OAuth token refresh failed: {mask_sensitive_text(str(exc))}") from exc
    payload = response.json()
    access_token = str(payload.get("access_token", "")).strip()
    if not access_token:
        raise RuntimeError("Google OAuth token refresh returned no access token.")
    return access_token


def send_email_via_google_oauth(config: AppConfig, message_text: str) -> None:
    access_token = refresh_google_oauth_access_token(config)
    raw = base64.urlsafe_b64encode(message_text.encode("utf-8")).decode("ascii").rstrip("=")
    try:
        response = requests.post(
            GMAIL_SEND_API_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"raw": raw},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"Gmail API send failed: {mask_sensitive_text(str(exc))}") from exc


def setup_logging() -> None:
    handlers: List[logging.Handler] = [logging.StreamHandler()]
    log_path = get_log_file_path()
    file_handler_ready = False
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_path,
                maxBytes=2 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
        )
        file_handler_ready = True
    except Exception as exc:
        print(f"[WARN] Failed to initialize log file handler at {log_path}: {exc}", file=sys.stderr)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )
    if file_handler_ready:
        logging.info("Logging to file: %s", log_path)


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    normalized = clean_text(str(value or "")).lower()
    if not normalized:
        return default
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def parse_arxiv_datetime(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def parse_pubmed_datetime(value: str) -> datetime | None:
    if not value:
        return None
    formats = ["%Y/%m/%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d", "%Y %b %d", "%Y %b"]
    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_semantic_datetime(publication_date: str, year: object) -> datetime | None:
    value = clean_text(publication_date)
    if value:
        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                parsed = datetime.strptime(value, fmt)
                return parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass

    try:
        year_int = int(str(year).strip())
    except (TypeError, ValueError):
        return None
    if year_int < 1900 or year_int > 3000:
        return None
    return datetime(year_int, 1, 1, tzinfo=timezone.utc)


def parse_google_scholar_datetime(raw_text: str, now_utc: datetime) -> datetime | None:
    text = clean_text(raw_text)
    if not text:
        return None
    lowered = text.lower()
    relative_match = re.search(r"(\d+)\s+(day|days|week|weeks|month|months|year|years)\s+ago", lowered)
    if relative_match:
        value = int(relative_match.group(1))
        unit = relative_match.group(2)
        if "day" in unit:
            return now_utc - timedelta(days=value)
        if "week" in unit:
            return now_utc - timedelta(days=value * 7)
        if "month" in unit:
            return now_utc - timedelta(days=value * 30)
        if "year" in unit:
            return now_utc - timedelta(days=value * 365)

    years = re.findall(r"(19\d{2}|20\d{2})", text)
    if years:
        try:
            year_value = int(years[-1])
            return datetime(year_value, 1, 1, tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def get_runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_project_root_dir() -> Path:
    runtime_dir = get_runtime_base_dir()
    if (runtime_dir / "VERSION").exists():
        return runtime_dir
    parent = runtime_dir.parent
    if (parent / "VERSION").exists():
        return parent
    return Path.cwd().resolve()


def get_default_data_dir() -> Path:
    override = os.getenv(APP_DATA_DIR_ENV_KEY, "").strip()
    if override:
        return Path(override).expanduser().resolve()

    if os.name == "nt":
        appdata = os.getenv("APPDATA", "").strip()
        base = Path(appdata) if appdata else (Path.home() / "AppData" / "Roaming")
        return (base / APP_DATA_DIR_NAME).resolve()
    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / APP_DATA_DIR_NAME).resolve()
    return (Path.home() / ".config" / APP_DATA_DIR_NAME).resolve()


def get_log_file_path() -> Path:
    return (get_default_data_dir() / "paper-morning.log").resolve()


def get_latest_preview_path() -> Path:
    return (get_default_data_dir() / "digest_preview.json").resolve()


def get_local_inbox_dir() -> Path:
    return (get_default_data_dir() / "local_inbox").resolve()


def save_preview_payload(payload: Dict[str, Any]) -> Path:
    preview_path = get_latest_preview_path()
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    enforce_private_file_permissions(preview_path)

    inbox_dir = get_local_inbox_dir()
    inbox_dir.mkdir(parents=True, exist_ok=True)
    generated_at = clean_text(str(payload.get("generated_at_utc", "")))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if generated_at:
        parsed = parse_iso_datetime(generated_at)
        if parsed is not None:
            stamp = parsed.strftime("%Y%m%dT%H%M%S%fZ")
    archive_path = inbox_dir / f"{stamp}.json"
    archive_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    enforce_private_file_permissions(archive_path)
    return preview_path


def resolve_env_path() -> Path:
    explicit = os.getenv(ENV_PATH_ENV_KEY, "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    return (get_default_data_dir() / ".env").resolve()


def resolve_topics_file_path(user_topics_file: str, env_path: Path | None = None) -> Path:
    path_value = clean_text(user_topics_file) or "user_topics.json"
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        base_dir = (env_path or resolve_env_path()).parent
        path = base_dir / path
    return path.resolve()


def load_google_oauth_bundle_defaults() -> Dict[str, str]:
    """
    Load distributor-bundled OAuth client defaults.
    Search order:
    1) user data directory (same folder as active .env)
    2) runtime base directory (exe/script directory)
    3) current working directory
    """
    default = {"client_id": "", "client_secret": "", "redirect_uri": ""}
    candidates = [
        (resolve_env_path().parent / GOOGLE_OAUTH_BUNDLE_FILENAME).resolve(),
        (get_runtime_base_dir() / GOOGLE_OAUTH_BUNDLE_FILENAME).resolve(),
        Path(GOOGLE_OAUTH_BUNDLE_FILENAME).expanduser().resolve(),
    ]
    seen: set[str] = set()
    for path in candidates:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            logging.warning("Failed to read %s: %s", path, mask_sensitive_text(str(exc)))
            continue
        if not isinstance(payload, dict):
            logging.warning("Invalid OAuth bundle format (dict expected): %s", path)
            continue
        return {
            "client_id": clean_text(str(payload.get("client_id", ""))),
            "client_secret": clean_text(str(payload.get("client_secret", ""))),
            "redirect_uri": clean_text(str(payload.get("redirect_uri", ""))),
        }
    return default


def _legacy_search_dirs() -> List[Path]:
    project_root = get_project_root_dir()
    candidates = [
        Path.cwd(),
        get_runtime_base_dir(),
        project_root,
        project_root / "config",
        project_root / "templates",
        project_root / "docs" / "manuals",
        project_root / "assets",
        project_root / "tools",
    ]
    unique_dirs: List[Path] = []
    seen = set()
    for item in candidates:
        resolved = item.resolve()
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        unique_dirs.append(resolved)
    return unique_dirs


def _find_legacy_file(path_value: str, search_dirs: List[Path]) -> Path | None:
    direct = Path(path_value).expanduser()
    if direct.is_absolute():
        return direct if direct.exists() else None

    for base_dir in search_dirs:
        candidate = (base_dir / direct).resolve()
        if candidate.exists():
            return candidate
    return None


def find_resource_file(path_candidates: List[str], search_dirs: List[Path]) -> Path | None:
    for candidate in path_candidates:
        found = _find_legacy_file(candidate, search_dirs)
        if found:
            return found
    return None


def _copy_if_needed(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    if source.resolve() == target.resolve():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def enforce_private_file_permissions(path: Path) -> None:
    if not path.exists():
        return
    try:
        if os.name == "nt":
            # Windows ACL handling is out-of-scope here; restrict to read/write for current user.
            path.chmod(stat.S_IREAD | stat.S_IWRITE)
        else:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except Exception as exc:
        logging.debug("Could not enforce private file permissions for %s: %s", path, exc)


def build_score_buckets(scores: List[float]) -> Dict[str, int]:
    buckets = {"9-10": 0, "7-8": 0, "5-6": 0, "1-4": 0, "0": 0}
    for score in scores:
        if score >= 9.0:
            buckets["9-10"] += 1
        elif score >= 7.0:
            buckets["7-8"] += 1
        elif score >= 5.0:
            buckets["5-6"] += 1
        elif score >= 1.0:
            buckets["1-4"] += 1
        else:
            buckets["0"] += 1
    return buckets


def build_scored_examples(papers: List["Paper"], limit: int = 25) -> List[str]:
    if not papers:
        return []
    ordered = sorted(
        papers,
        key=lambda item: (item.score, item.published_at_utc),
        reverse=True,
    )
    examples: List[str] = []
    for paper in ordered[: max(1, limit)]:
        title = clean_text(paper.title)
        if len(title) > 96:
            title = title[:93].rstrip() + "..."
        examples.append(f"{paper.score:.1f} | {title}")
    return examples


def get_sent_history_path() -> Path:
    return (get_default_data_dir() / "sent_ids.json").resolve()


def get_scheduled_send_lock_path() -> Path:
    return (get_default_data_dir() / "last_scheduled_send_local_date.json").resolve()


def parse_iso_datetime(raw: str) -> datetime | None:
    value = clean_text(raw)
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_sent_history(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    history: Dict[str, str] = {}
    for paper_id, sent_at in payload.items():
        key = clean_text(str(paper_id))
        value = clean_text(str(sent_at))
        if key and value:
            history[key] = value
    return history


def save_sent_history(path: Path, history: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    enforce_private_file_permissions(path)


def load_scheduled_send_lock(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        "local_date": clean_text(str(payload.get("local_date", ""))),
        "sent_at_utc": clean_text(str(payload.get("sent_at_utc", ""))),
        "timezone": clean_text(str(payload.get("timezone", ""))),
    }


def save_scheduled_send_lock(path: Path, local_date: str, sent_at_utc: datetime, timezone_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "local_date": clean_text(local_date),
        "sent_at_utc": sent_at_utc.astimezone(timezone.utc).isoformat(),
        "timezone": clean_text(timezone_name),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    enforce_private_file_permissions(path)


def should_send_now(config: AppConfig, now_utc: datetime) -> Tuple[bool, str, date]:
    local_now = now_utc.astimezone(config.timezone)
    local_date = local_now.date()
    scheduled_local = local_now.replace(
        hour=config.send_hour,
        minute=config.send_minute,
        second=0,
        microsecond=0,
    )
    distance_minutes = abs((local_now - scheduled_local).total_seconds()) / 60.0
    window = max(1, config.send_time_window_minutes)
    if distance_minutes > window:
        return (
            False,
            (
                f"Outside send window ({window}m). "
                f"Now={local_now:%H:%M}, target={config.send_hour:02d}:{config.send_minute:02d} "
                f"({config.timezone_name})"
            ),
            local_date,
        )

    lock_path = get_scheduled_send_lock_path()
    lock = load_scheduled_send_lock(lock_path)
    if lock.get("local_date") == local_date.isoformat() and lock.get("timezone") == config.timezone_name:
        return (
            False,
            f"Already sent for local date {local_date.isoformat()} ({config.timezone_name}).",
            local_date,
        )

    return True, "Within configured send window.", local_date


def filter_already_sent_papers(
    papers: List[Paper],
    now_utc: datetime,
    history_days: int,
) -> Tuple[List[Paper], Dict[str, str], int]:
    history_path = get_sent_history_path()
    history = load_sent_history(history_path)
    cutoff = now_utc - timedelta(days=max(1, history_days))

    pruned: Dict[str, str] = {}
    for paper_id, sent_at in history.items():
        parsed = parse_iso_datetime(sent_at)
        if parsed and parsed >= cutoff:
            pruned[paper_id] = parsed.isoformat()

    filtered = [paper for paper in papers if paper.paper_id not in pruned]
    duplicates = max(0, len(papers) - len(filtered))
    return filtered, pruned, duplicates

def bootstrap_runtime_files() -> Tuple[Path, Path]:
    env_path = resolve_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    search_dirs = _legacy_search_dirs()

    if not env_path.exists():
        legacy_env = _find_legacy_file(".env", search_dirs)
        if legacy_env and _copy_if_needed(legacy_env, env_path):
            logging.info("Migrated .env to persistent path: %s", env_path)

    if not env_path.exists():
        env_example = find_resource_file(
            [".env.example", "config/.env.example"],
            search_dirs,
        )
        if env_example and _copy_if_needed(env_example, env_path):
            logging.info("Bootstrapped .env from .env.example: %s", env_path)
        else:
            env_path.write_text("", encoding="utf-8")
    enforce_private_file_permissions(env_path)

    env_map = dotenv_values(str(env_path)) if env_path.exists() else {}
    topics_setting = str(env_map.get("USER_TOPICS_FILE") or "user_topics.json").strip()
    topics_path = resolve_topics_file_path(topics_setting, env_path=env_path)
    topics_path.parent.mkdir(parents=True, exist_ok=True)

    if not topics_path.exists():
        legacy_topics = _find_legacy_file(topics_setting, search_dirs)
        if legacy_topics and _copy_if_needed(legacy_topics, topics_path):
            logging.info("Migrated topics file to persistent path: %s", topics_path)
        else:
            fallback_topics = _find_legacy_file("user_topics.json", search_dirs)
            if fallback_topics and _copy_if_needed(fallback_topics, topics_path):
                logging.info("Migrated default topics file to persistent path: %s", topics_path)

    if not topics_path.exists():
        template = find_resource_file(
            ["user_topics.template.json", "config/user_topics.template.json"],
            search_dirs,
        )
        if template and _copy_if_needed(template, topics_path):
            logging.info("Bootstrapped topics file from template: %s", topics_path)
        else:
            topics_path.write_text(
                json.dumps({"projects": [], "topics": []}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    os.environ[ENV_PATH_ENV_KEY] = str(env_path)
    return env_path, topics_path


def normalize_string_list(value: object) -> List[str]:
    if isinstance(value, list):
        return [clean_text(str(item)) for item in value if clean_text(str(item))]
    if isinstance(value, str):
        return [clean_text(part) for part in value.split(",") if clean_text(part)]
    return []


def coerce_keyword_weights(raw_keywords: object) -> Dict[str, float]:
    keyword_weights: Dict[str, float] = {}
    if isinstance(raw_keywords, dict):
        for key, value in raw_keywords.items():
            term = clean_text(str(key)).lower()
            if not term:
                continue
            try:
                keyword_weights[term] = float(value)
            except (TypeError, ValueError):
                continue
        return keyword_weights
    if isinstance(raw_keywords, list):
        for value in raw_keywords:
            term = clean_text(str(value)).lower()
            if term:
                keyword_weights[term] = 2.0
        return keyword_weights
    if isinstance(raw_keywords, str):
        for value in raw_keywords.split(","):
            term = clean_text(value).lower()
            if term:
                keyword_weights[term] = 2.0
        return keyword_weights
    return keyword_weights


def dedupe_list(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def extract_query_terms(text: str) -> List[str]:
    raw = clean_text(text).lower()
    if not raw:
        return []
    tokens = re.findall(r"[a-z0-9][a-z0-9\-\+_]{1,}", raw)
    stopwords = {
        "and",
        "or",
        "not",
        "all",
        "title",
        "abstract",
        "mesh",
        "terms",
        "field",
        "fields",
    }
    result: List[str] = []
    seen = set()
    for token in tokens:
        if token in stopwords or token.isdigit():
            continue
        if token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result


def build_relaxed_queries_for_source(
    queries: List[str],
    source: str,
    project_terms: List[str],
) -> List[str]:
    terms: List[str] = []
    for query in queries:
        terms.extend(extract_query_terms(query))
    terms.extend(project_terms[:12])
    terms = dedupe_list([term for term in terms if term])
    if not terms:
        return []

    if source == "arxiv":
        or_terms = " OR ".join(f"all:{term}" for term in terms[:6])
        simple_terms = " ".join(terms[:5])
        return dedupe_list([or_terms, simple_terms])
    if source == "pubmed":
        or_terms = " OR ".join(f"\"{term}\"[Title/Abstract]" for term in terms[:6])
        simple_terms = " OR ".join(f"\"{term}\"" for term in terms[:5])
        return dedupe_list([or_terms, simple_terms])
    # Semantic Scholar / Google Scholar plain query
    return dedupe_list([" ".join(terms[:8]), " ".join(terms[:5])])


def generate_rescue_queries_with_llm(config: AppConfig) -> Tuple[List[str], List[str], List[str], List[str]]:
    if not (config.enable_llm_agent and has_llm_provider(config) and config.research_projects):
        return [], [], [], []

    projects_payload = [
        {"name": project.name, "context": project.context}
        for project in config.research_projects
    ]
    project_json = json.dumps(projects_payload, ensure_ascii=False)
    prompt = (
        "You are recovering from zero search results in a medical AI paper alert pipeline.\n"
        "Generate broader but still relevant fallback queries.\n"
        "Return ONLY JSON with keys: arxiv_queries, pubmed_queries, semantic_scholar_queries, google_scholar_queries.\n"
        "Each key must be a list of 1..2 strings.\n"
        "Rules:\n"
        "- arxiv_queries: use all: syntax, broad OR style, avoid over-constrained boolean nesting\n"
        "- pubmed_queries: use simple boolean with quoted terms, avoid over-constrained MeSH-only query\n"
        "- semantic_scholar_queries and google_scholar_queries: concise plain text\n"
        "- no markdown, no comments\n"
        f"Projects JSON:\n{project_json}"
    )

    llm_response = call_llm_json(config, prompt, temperature=0.25)
    if not isinstance(llm_response, dict):
        return [], [], [], []

    def normalize(values: Any) -> List[str]:
        if not isinstance(values, list):
            return []
        items = [clean_text(str(item)) for item in values if clean_text(str(item))]
        return dedupe_list(items)[:2]

    return (
        normalize(llm_response.get("arxiv_queries", [])),
        normalize(llm_response.get("pubmed_queries", [])),
        normalize(llm_response.get("semantic_scholar_queries", [])),
        normalize(llm_response.get("google_scholar_queries", [])),
    )


def load_topic_configuration(
    topics_file: str,
) -> Tuple[List[TopicProfile], List[ResearchProject], List[str], List[str], List[str], List[str]]:
    path = Path(topics_file)
    if not path.exists():
        logging.warning("Topic config not found at %s. Starting with empty projects/topics/queries.", path)
        return [], [], [], [], [], []

    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    topics = payload.get("topics", [])
    projects_payload = payload.get("projects", [])
    if not isinstance(topics, list):
        topics = []
    if not isinstance(projects_payload, list):
        projects_payload = []

    profiles: List[TopicProfile] = []
    projects: List[ResearchProject] = []
    arxiv_queries: List[str] = []
    pubmed_queries: List[str] = []
    semantic_queries: List[str] = []
    google_scholar_queries: List[str] = []

    for topic in topics:
        if not isinstance(topic, dict):
            continue
        arxiv_query = clean_text(str(topic.get("arxiv_query", "")))
        pubmed_query = clean_text(str(topic.get("pubmed_query", "")))
        semantic_query = clean_text(str(topic.get("semantic_scholar_query", "")))
        google_scholar_query = clean_text(str(topic.get("google_scholar_query", "")))
        if arxiv_query:
            arxiv_queries.append(arxiv_query)
        if pubmed_query:
            pubmed_queries.append(pubmed_query)
        if semantic_query:
            semantic_queries.append(semantic_query)
        if google_scholar_query:
            google_scholar_queries.append(google_scholar_query)

        name = clean_text(str(topic.get("name", "")))
        keyword_weights = coerce_keyword_weights(topic.get("keywords"))
        relevance_mode = normalize_relevance_mode(topic.get("relevance_mode", LLM_RELEVANCE_MODE_DEFAULT))
        if not name or not keyword_weights:
            continue

        profiles.append(
            TopicProfile(
                name=name,
                keywords=keyword_weights,
                relevance_mode=relevance_mode,
            )
        )

    for project in projects_payload:
        if not isinstance(project, dict):
            continue
        name = clean_text(str(project.get("name", "")))
        context = clean_text(str(project.get("context", "")))
        project_send_frequency, project_interval_days = normalize_send_frequency(
            str(project.get("send_frequency", "daily"))
        )
        goals = normalize_string_list(project.get("goals"))
        methods = normalize_string_list(project.get("methods"))
        stack = normalize_string_list(project.get("stack"))
        merged = " | ".join(part for part in [context, "; ".join(goals), "; ".join(methods), "; ".join(stack)] if part)
        if name and merged:
            projects.append(
                ResearchProject(
                    name=name,
                    context=merged,
                    send_frequency=project_send_frequency,
                    send_interval_days=project_interval_days,
                )
            )

    if not projects and profiles:
        for profile in profiles:
            projects.append(
                ResearchProject(
                    name=profile.name,
                    context=f"Keywords: {', '.join(profile.keywords.keys())}",
                    send_frequency="daily",
                    send_interval_days=1,
                )
            )

    if (
        not profiles
        and not projects
        and not arxiv_queries
        and not pubmed_queries
        and not semantic_queries
        and not google_scholar_queries
    ):
        logging.warning(
            (
                "Topic config is empty at %s. Configure projects, then generate/save queries in Topic Editor "
                "before running local search."
            ),
            path,
        )

    return (
        profiles,
        projects,
        dedupe_list(arxiv_queries),
        dedupe_list(pubmed_queries),
        dedupe_list(semantic_queries),
        dedupe_list(google_scholar_queries),
    )


def sanitize_generated_topics(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_topics = payload.get("topics", []) if isinstance(payload, dict) else []
    if not isinstance(raw_topics, list):
        return []

    result: List[Dict[str, Any]] = []
    for item in raw_topics:
        if not isinstance(item, dict):
            continue
        name = clean_text(str(item.get("name", "")))
        keywords_raw = item.get("keywords", [])
        if isinstance(keywords_raw, str):
            keywords = [part.strip() for part in keywords_raw.split(",") if part.strip()]
        elif isinstance(keywords_raw, list):
            keywords = [clean_text(str(part)) for part in keywords_raw if clean_text(str(part))]
        else:
            keywords = []
        keywords = dedupe_list(keywords)[:12]
        if not name or not keywords:
            continue
        result.append(
            {
                "name": name,
                "keywords": keywords,
                "relevance_mode": normalize_relevance_mode(item.get("relevance_mode", LLM_RELEVANCE_MODE_DEFAULT)),
                "arxiv_query": clean_text(str(item.get("arxiv_query", ""))),
                "pubmed_query": clean_text(str(item.get("pubmed_query", ""))),
                "semantic_scholar_query": clean_text(str(item.get("semantic_scholar_query", ""))),
                "google_scholar_query": clean_text(str(item.get("google_scholar_query", ""))),
            }
        )
    return result


def generate_topics_from_projects(config: AppConfig, projects: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    project_json = json.dumps(projects, ensure_ascii=False)
    prompt = (
        "You are helping configure a research-context paper search tool.\n"
        "For each project, generate one precise topic row with: name, keywords, arxiv_query, pubmed_query, "
        "semantic_scholar_query, google_scholar_query, relevance_mode.\n"
        "Return ONLY JSON object with schema:\n"
        "{\n"
        '  "topics": [\n'
        "    {\n"
        '      "name": "...",\n'
        '      "keywords": ["..."],\n'
        '      "relevance_mode": "balanced",\n'
        '      "arxiv_query": "...",\n'
        '      "pubmed_query": "...",\n'
        '      "semantic_scholar_query": "...",\n'
        '      "google_scholar_query": "..."\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- create exactly one topic per project\n"
        "- keyword list length: 5..10\n"
        "- arXiv query must use all: terms and remain moderately broad\n"
        "- PubMed query should use boolean and quoted phrases where useful\n"
        "- Semantic Scholar query should be concise plain text\n"
        "- Google Scholar query should be concise plain text\n"
        "- default relevance_mode to balanced unless the project is clearly narrow or clearly exploratory\n"
        "- keep response machine-parseable JSON only\n\n"
        f"Projects JSON:\n{project_json}"
    )
    llm_response = call_llm_json(config, prompt, temperature=0.2)
    if not isinstance(llm_response, dict):
        raise ValueError("Topic generation returned invalid response format.")
    topics = sanitize_generated_topics(llm_response)
    if not topics:
        raise ValueError("Topic generation returned no usable topic rows.")
    return topics


def score_paper(
    title: str,
    abstract: str,
    topic_profiles: List[TopicProfile],
) -> Tuple[float, str, List[str], str]:
    combined = f"{title} {abstract}".lower()
    best_topic = ""
    best_score = 0.0
    best_keywords: List[str] = []
    best_mode = LLM_RELEVANCE_MODE_DEFAULT
    for profile in topic_profiles:
        score = 0.0
        matched: List[str] = []
        for keyword, weight in profile.keywords.items():
            if keyword in combined:
                score += weight
                matched.append(keyword)
        if score > best_score:
            best_score = score
            best_topic = profile.name
            best_keywords = matched
            best_mode = normalize_relevance_mode(profile.relevance_mode)
    return best_score, best_topic, best_keywords, best_mode


def apply_topic_metadata_to_paper(paper: Paper, config: AppConfig) -> None:
    score, topic, matched, relevance_mode = score_paper(
        paper.title,
        paper.abstract,
        config.topic_profiles,
    )
    paper.score = score
    paper.topic = topic
    paper.matched_keywords = matched
    paper.relevance_mode = normalize_relevance_mode(relevance_mode)
    paper.relevance_threshold = relevance_mode_threshold(
        paper.relevance_mode,
        config.llm_relevance_threshold,
    )
    project_lookup = {
        clean_text(project.name).lower(): project.name
        for project in config.research_projects
        if clean_text(project.name)
    }
    paper.project_name = project_lookup.get(clean_text(topic).lower(), "")


def build_relevance_policy_summary(
    papers: List[Paper],
    fallback_threshold: float,
) -> List[str]:
    counts: Dict[str, int] = {}
    for paper in papers:
        mode = normalize_relevance_mode(getattr(paper, "relevance_mode", LLM_RELEVANCE_MODE_DEFAULT))
        counts[mode] = counts.get(mode, 0) + 1
    if not counts:
        return []
    ordered_modes = ["strict", "balanced", "discovery"]
    lines: List[str] = []
    for mode in ordered_modes:
        count = counts.get(mode, 0)
        if count <= 0:
            continue
        threshold = relevance_mode_threshold(mode, fallback_threshold)
        lines.append(
            f"{relevance_mode_label(mode)} topic mode: pass >= {threshold:.1f} ({count} candidate{'s' if count != 1 else ''})"
        )
    return lines

def parse_json_loose(text: str) -> Any:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("LLM response is empty.")
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    def try_parse(candidate: str) -> Any:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            # Repair malformed escape sequences inside JSON strings from LLM output.
            repaired = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", candidate)
            if repaired != candidate:
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass
            # Some models return unescaped control chars/newlines inside strings.
            try:
                return json.loads(candidate, strict=False)
            except json.JSONDecodeError:
                pass
            if repaired != candidate:
                try:
                    return json.loads(repaired, strict=False)
                except json.JSONDecodeError:
                    pass
            raise exc

    try:
        return try_parse(raw)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        raise ValueError("Could not find JSON object in LLM response.")
    return try_parse(match.group(0))


def emit_progress(
    progress_callback: Callable[[str, int], None] | None,
    message: str,
    percent: int,
) -> None:
    if not progress_callback:
        return
    try:
        progress_callback(message, max(0, min(100, int(percent))))
    except Exception:
        pass


def build_project_context_text(projects: List[ResearchProject]) -> str:
    lines = []
    for idx, project in enumerate(projects, start=1):
        lines.append(f"{idx}. {project.name}: {project.context}")
    return "\n".join(lines)


def resolve_search_request(
    config: AppConfig,
    search_intent: str | None = None,
    time_horizon_key: str | None = None,
) -> SearchRequest:
    intent = normalize_search_intent(search_intent or config.search_intent_default)
    horizon_key = normalize_time_horizon_key(time_horizon_key or config.search_time_horizon_default, intent)
    return SearchRequest(
        intent=intent,
        time_horizon_key=horizon_key,
        time_horizon_hours=time_horizon_hours(horizon_key, intent),
        intent_label=search_intent_label(intent),
        time_horizon_label=time_horizon_label(horizon_key, intent),
    )


def build_search_query_plans(config: AppConfig) -> List[Dict[str, List[str] | str]]:
    project_terms: List[str] = []
    for project in config.research_projects:
        project_terms.extend(extract_query_terms(f"{project.name} {project.context}"))
    project_terms = dedupe_list(project_terms)

    saved_plan = {
        "label": "saved topic queries",
        "arxiv_queries": dedupe_list(list(config.arxiv_queries))[: config.max_search_queries_per_source],
        "pubmed_queries": dedupe_list(list(config.pubmed_queries))[: config.max_search_queries_per_source],
        "semantic_queries": dedupe_list(list(config.semantic_scholar_queries))[: config.max_search_queries_per_source],
        "google_queries": dedupe_list(list(config.google_scholar_queries))[: config.max_search_queries_per_source],
    }
    plans: List[Dict[str, List[str] | str]] = [saved_plan]

    relaxed_plan = {
        "label": "broader fallback queries",
        "arxiv_queries": build_relaxed_queries_for_source(saved_plan["arxiv_queries"], "arxiv", project_terms)
        if saved_plan["arxiv_queries"]
        else [],
        "pubmed_queries": build_relaxed_queries_for_source(saved_plan["pubmed_queries"], "pubmed", project_terms)
        if saved_plan["pubmed_queries"]
        else [],
        "semantic_queries": build_relaxed_queries_for_source(saved_plan["semantic_queries"], "semantic", project_terms)
        if saved_plan["semantic_queries"]
        else [],
        "google_queries": build_relaxed_queries_for_source(saved_plan["google_queries"], "google", project_terms)
        if saved_plan["google_queries"]
        else [],
    }
    if any(relaxed_plan[key] for key in ("arxiv_queries", "pubmed_queries", "semantic_queries", "google_queries")):
        differs = False
        for key in ("arxiv_queries", "pubmed_queries", "semantic_queries", "google_queries"):
            if list(relaxed_plan[key]) != list(saved_plan[key]):
                differs = True
                break
        if differs:
            plans.append(relaxed_plan)
    return plans


def build_search_candidate_terms(config: AppConfig) -> List[str]:
    terms: List[str] = []
    for profile in config.topic_profiles:
        terms.extend(profile.keywords.keys())
    for project in config.research_projects:
        terms.extend(extract_query_terms(f"{project.name} {project.context}"))
    return dedupe_list([clean_text(term).lower() for term in terms if clean_text(term)])[:12]


def count_term_hits(text: str, terms: List[str]) -> int:
    normalized = clean_text(text).lower()
    score = 0
    for term in terms:
        if term and term in normalized:
            score += 2 if " " in term else 1
    return score


def recency_signal(paper: Paper, now_utc: datetime) -> float:
    age_days = max(0.0, (now_utc - paper.published_at_utc).total_seconds() / 86400.0)
    return 1.0 / (1.0 + age_days / 45.0)


def candidate_priority(
    intent: str,
    paper: Paper,
    terms: List[str],
    now_utc: datetime,
) -> float:
    title_hits = count_term_hits(paper.title, terms)
    abstract_hits = count_term_hits(paper.abstract, terms)
    keyword_score = title_hits * 3 + abstract_hits
    freshness = recency_signal(paper, now_utc)
    if normalize_search_intent(intent) == "whats_new":
        return freshness * 10.0 + keyword_score * 1.4
    if normalize_search_intent(intent) == "discovery":
        return keyword_score * 2.1 + freshness * 1.1
    return keyword_score * 2.7 + freshness * 1.4


def prioritize_candidates_for_search(
    papers: List[Paper],
    config: AppConfig,
    search_request: SearchRequest,
    now_utc: datetime,
) -> List[Paper]:
    if not papers:
        return []
    terms = build_search_candidate_terms(config)
    for paper in papers:
        apply_topic_metadata_to_paper(paper, config)
    return sorted(
        papers,
        key=lambda item: (
            candidate_priority(search_request.intent, item, terms, now_utc),
            item.score,
            item.published_at_utc,
        ),
        reverse=True,
    )


def filter_papers_by_horizon(papers: List[Paper], now_utc: datetime, horizon_hours: int) -> List[Paper]:
    since_utc = now_utc - timedelta(hours=max(1, horizon_hours))
    return [paper for paper in papers if since_utc <= paper.published_at_utc <= now_utc]


def dedupe_papers_by_title(papers: List[Paper]) -> List[Paper]:
    by_key: Dict[str, Paper] = {}
    for paper in sorted(papers, key=lambda item: item.published_at_utc, reverse=True):
        key = clean_text(paper.title).lower()
        if not key:
            key = clean_text(paper.paper_id).lower()
        if not key:
            continue
        if key not in by_key:
            by_key[key] = paper
    return list(by_key.values())


def build_search_retrieval_settings(search_request: SearchRequest) -> Dict[str, Any]:
    policy = get_search_intent_policy(search_request.intent)
    hours = search_request.time_horizon_hours
    if hours >= TIME_HORIZON_OPTIONS["5y"]["hours"]:
        horizon_boost = 1.35
    elif hours >= TIME_HORIZON_OPTIONS["3y"]["hours"]:
        horizon_boost = 1.2
    elif hours >= TIME_HORIZON_OPTIONS["1y"]["hours"]:
        horizon_boost = 1.1
    else:
        horizon_boost = 1.0
    return {
        "arxiv_sort": str(policy.get("arxiv_sort", "submittedDate")),
        "pubmed_sort": str(policy.get("pubmed_sort", "pub date")),
        "arxiv_max_results": min(140, round(float(policy.get("arxiv_max_results", 60)) * horizon_boost)),
        "pubmed_max_results": min(180, round(float(policy.get("pubmed_max_results", 80)) * horizon_boost)),
        "semantic_max_results": min(100, round(float(policy.get("semantic_max_results", 40)) * horizon_boost)),
        "google_scholar_max_results": min(
            GOOGLE_SCHOLAR_MAX_RESULTS_HARD_LIMIT,
            round(float(policy.get("google_scholar_max_results", 20)) * horizon_boost),
        ),
    }


def build_whats_new_horizon_steps(search_request: SearchRequest) -> List[Tuple[str, int]]:
    max_hours = search_request.time_horizon_hours
    steps: List[Tuple[str, int]] = []
    for key in WHATS_NEW_ADAPTIVE_STEPS:
        hours = time_horizon_hours(key, search_request.intent)
        if hours <= max_hours:
            steps.append((key, hours))
    if not steps or steps[-1][1] != max_hours:
        steps.append((search_request.time_horizon_key, max_hours))
    return steps


def build_search_intent_prompt_lines(search_request: SearchRequest) -> List[str]:
    if search_request.intent == "whats_new":
        return [
            "Search intent is What's New.",
            "Prioritize recent papers that are still directly useful to the user's work.",
            "Freshness matters, but do not reward recency alone if relevance is weak.",
            "If two papers are similarly relevant, prefer the newer one.",
        ]
    if search_request.intent == "discovery":
        return [
            "Search intent is Discovery.",
            "Allow adjacent methods, datasets, or evaluation designs when transfer value is concrete.",
            "Direct matches can rank highest, but high-upside adjacent work may also score well.",
        ]
    return [
        "Search intent is Best Match.",
        "Optimize for strongest practical fit to the user's project, even if papers are not extremely recent.",
        "Clearly reusable methods papers may also score well when the reuse path is concrete.",
    ]


def call_gemini_json(config: AppConfig, prompt: str, temperature: float = 0.2) -> Any:
    if not config.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is missing.")

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }

    def model_candidates(primary: str) -> List[str]:
        base = clean_text(primary) or "gemini-3.1-flash"
        ordered = [base]
        if "pro" in base:
            ordered.extend(["gemini-3.1-flash", "gemini-2.5-flash"])
        elif "flash" in base:
            ordered.extend(["gemini-2.5-flash"])
        else:
            ordered.extend(["gemini-3.1-flash", "gemini-2.5-flash"])
        deduped: List[str] = []
        seen = set()
        for item in ordered:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    errors: List[str] = []
    candidates_to_try = model_candidates(config.gemini_model)
    for idx, model in enumerate(candidates_to_try):
        url = GEMINI_API_URL_TEMPLATE.format(model=model)
        try:
            response = requests.post(
                url,
                headers={"x-goog-api-key": config.gemini_api_key},
                json=payload,
                timeout=GEMINI_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            raise RuntimeError(f"Gemini API request failed: {mask_sensitive_text(str(exc))}") from exc

        if response.status_code >= 400:
            body_text = mask_sensitive_text(response.text or "")
            lowered = body_text.lower()
            model_not_available = response.status_code in {400, 404} and (
                "not found" in lowered or "model" in lowered or "unsupported" in lowered
            )
            if model_not_available and idx < len(candidates_to_try) - 1:
                errors.append(f"{model}: {response.status_code}")
                logging.warning(
                    "Gemini model %s unavailable (%s). Retrying with fallback model.",
                    model,
                    response.status_code,
                )
                continue
            try:
                response.raise_for_status()
            except Exception as exc:
                raise RuntimeError(f"Gemini API request failed: {mask_sensitive_text(str(exc))}") from exc

        response_payload = response.json()
        api_candidates = response_payload.get("candidates", [])
        if not api_candidates:
            errors.append(f"{model}: no candidates")
            if idx < len(candidates_to_try) - 1:
                logging.warning("Gemini model %s returned no candidates. Retrying fallback model.", model)
                continue
            raise ValueError("No candidates returned from Gemini API.")

        parts = api_candidates[0].get("content", {}).get("parts", [])
        llm_text = "\n".join(part.get("text", "") for part in parts if part.get("text"))
        return parse_json_loose(llm_text)

    if errors:
        raise RuntimeError("Gemini model fallback exhausted: " + "; ".join(errors))
    raise RuntimeError("Gemini call failed without usable response.")


def call_cerebras_json(config: AppConfig, prompt: str, temperature: float = 0.2) -> Any:
    if not config.cerebras_api_key:
        raise ValueError("CEREBRAS_API_KEY is missing.")

    base_url = (config.cerebras_api_base or CEREBRAS_API_BASE_DEFAULT).strip().rstrip("/")
    if not base_url:
        base_url = CEREBRAS_API_BASE_DEFAULT
    url = f"{base_url}/chat/completions"

    payload = {
        "model": config.cerebras_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {config.cerebras_api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=CEREBRAS_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    response_payload = response.json()
    choices = response_payload.get("choices", [])
    if not choices:
        raise ValueError("No choices returned from Cerebras API.")

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
        llm_text = "\n".join(parts)
    else:
        llm_text = str(content or "")
    return parse_json_loose(llm_text)


def can_use_openai_compat_provider(config: AppConfig) -> bool:
    return (
        config.enable_openai_compat_fallback
        and bool(clean_text(config.openai_compat_api_base))
        and bool(clean_text(config.openai_compat_model))
    )


def call_openai_compatible_json(config: AppConfig, prompt: str, temperature: float = 0.2) -> Any:
    if not can_use_openai_compat_provider(config):
        raise ValueError("OPENAI-compatible provider is not configured.")

    base_url = (config.openai_compat_api_base or OPENAI_COMPAT_API_BASE_DEFAULT).strip().rstrip("/")
    if not base_url:
        raise ValueError("OPENAI_COMPAT_API_BASE is missing.")
    url = f"{base_url}/chat/completions"

    payload = {
        "model": config.openai_compat_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    headers = {"Content-Type": "application/json"}
    if config.openai_compat_api_key:
        headers["Authorization"] = f"Bearer {config.openai_compat_api_key}"

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=CEREBRAS_TIMEOUT_SECONDS,
    )
    if response.status_code in {400, 404, 422}:
        fallback_payload = dict(payload)
        fallback_payload.pop("response_format", None)
        response = requests.post(
            url,
            headers=headers,
            json=fallback_payload,
            timeout=CEREBRAS_TIMEOUT_SECONDS,
        )
    response.raise_for_status()

    response_payload = response.json()
    choices = response_payload.get("choices", [])
    if not choices:
        raise ValueError("No choices returned from OPENAI-compatible API.")

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
        llm_text = "\n".join(parts)
    else:
        llm_text = str(content or "")
    return parse_json_loose(llm_text)


def can_use_cerebras_fallback(config: AppConfig) -> bool:
    return bool(config.cerebras_api_key) and config.enable_cerebras_fallback


def has_llm_provider(config: AppConfig) -> bool:
    return (
        bool(config.gemini_api_key)
        or can_use_openai_compat_provider(config)
        or can_use_cerebras_fallback(config)
    )


def call_llm_json(config: AppConfig, prompt: str, temperature: float = 0.2) -> Any:
    errors: List[str] = []

    if config.gemini_api_key:
        try:
            return call_gemini_json(config, prompt, temperature=temperature)
        except Exception as exc:
            safe_error = mask_sensitive_text(str(exc))
            errors.append(f"Gemini failed: {safe_error}")
            logging.warning(
                "Gemini call failed. Trying configured fallback providers if enabled: %s",
                safe_error,
            )

    if can_use_openai_compat_provider(config):
        try:
            return call_openai_compatible_json(config, prompt, temperature=temperature)
        except Exception as exc:
            safe_error = mask_sensitive_text(str(exc))
            errors.append(f"OpenAI-compatible failed: {safe_error}")
            logging.warning("OpenAI-compatible call failed: %s", safe_error)

    if can_use_cerebras_fallback(config):
        try:
            return call_cerebras_json(config, prompt, temperature=temperature)
        except Exception as exc:
            safe_error = mask_sensitive_text(str(exc))
            errors.append(f"Cerebras failed: {safe_error}")
            logging.warning("Cerebras call failed: %s", safe_error)

    if errors:
        raise RuntimeError("; ".join(errors))

    raise ValueError(
        "No LLM provider available. Configure GEMINI_API_KEY, an OPENAI-compatible backend, or Cerebras fallback."
    )


def request_arxiv_with_retry(params: Dict[str, Any]) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(ARXIV_MAX_RETRY_ATTEMPTS):
        try:
            response = requests.get(
                ARXIV_API_URL,
                params=params,
                headers=ARXIV_REQUEST_HEADERS,
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            if response.status_code in ARXIV_RETRYABLE_STATUS_CODES:
                retry_after = response.headers.get("Retry-After", "").strip()
                if retry_after.isdigit():
                    sleep_seconds = max(1, min(30, int(retry_after)))
                else:
                    sleep_seconds = min(30, 2 ** attempt)
                if attempt < ARXIV_MAX_RETRY_ATTEMPTS - 1:
                    logging.warning(
                        "arXiv temporary error %s, retrying in %ss (attempt %d/%d)",
                        response.status_code,
                        sleep_seconds,
                        attempt + 1,
                        ARXIV_MAX_RETRY_ATTEMPTS,
                    )
                    time.sleep(sleep_seconds)
                    continue
                response.raise_for_status()
            if response.status_code >= 400:
                # Non-retryable HTTP errors should fail fast.
                response.raise_for_status()
            return response
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            if attempt < ARXIV_MAX_RETRY_ATTEMPTS - 1:
                sleep_seconds = min(30, 2 ** attempt)
                logging.warning(
                    "arXiv request failed, retrying in %ss (attempt %d/%d): %s",
                    sleep_seconds,
                    attempt + 1,
                    ARXIV_MAX_RETRY_ATTEMPTS,
                    exc,
                )
                time.sleep(sleep_seconds)
                continue
            break
        except requests.HTTPError as exc:
            # HTTP errors here are non-retryable (retryable statuses are handled above).
            raise RuntimeError(f"arXiv HTTP error: {exc}") from exc
    raise RuntimeError(f"arXiv request failed after retries: {last_error}")


def fetch_arxiv_papers(
    config: AppConfig,
    since_utc: datetime,
    queries: List[str],
    *,
    sort_by: str = "submittedDate",
    max_results_override: int | None = None,
) -> List[Paper]:
    papers_by_id: Dict[str, Paper] = {}
    max_results = config.arxiv_max_results_per_query if max_results_override is None else int(max_results_override)
    max_results = max(1, min(max_results, ARXIV_MAX_RESULTS_HARD_LIMIT))
    for idx, query in enumerate(queries):
        if idx > 0:
            time.sleep(ARXIV_QUERY_INTERVAL_SECONDS)
        params = {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": sort_by,
            "sortOrder": "descending",
        }
        try:
            response = request_arxiv_with_retry(params)
        except Exception as exc:
            logging.warning("Skipping arXiv query due to repeated failure: %s | query=%s", exc, query)
            continue
        feed = feedparser.parse(response.text)

        for entry in feed.entries:
            published_at = parse_arxiv_datetime(entry.published)
            updated_at = parse_arxiv_datetime(entry.updated)
            effective_time = max(published_at, updated_at)
            if effective_time < since_utc:
                continue
            authors = [author.name for author in entry.get("authors", [])]
            paper = Paper(
                paper_id=entry.id,
                title=clean_text(entry.title),
                abstract=clean_text(entry.summary),
                url=entry.link,
                authors=authors,
                published_at_utc=effective_time,
                source="arXiv",
            )
            papers_by_id[paper.paper_id] = paper
    return list(papers_by_id.values())


def fetch_pubmed_ids(
    query: str,
    config: AppConfig,
    *,
    sort: str = "pub date",
    reldate_days: int | None = None,
    max_results_override: int | None = None,
) -> List[str]:
    normalized_query = re.sub(r"\*{2,}", "", clean_text(query))
    if not normalized_query:
        return []
    retmax = config.pubmed_max_ids_per_query if max_results_override is None else int(max_results_override)
    retmax = max(1, min(retmax, 200))
    reldate = max(1, int(config.lookback_hours / 24) + 1) if reldate_days is None else max(1, int(reldate_days))
    params = {
        "db": "pubmed",
        "term": normalized_query,
        "retmax": retmax,
        "sort": sort,
        "reldate": reldate,
        "datetype": "pdat",
        "retmode": "json",
    }
    if config.ncbi_api_key:
        params["api_key"] = config.ncbi_api_key
    response = request_pubmed_with_retry(PUBMED_ESEARCH_URL, params, config, "esearch")
    payload = response.json()
    return payload.get("esearchresult", {}).get("idlist", [])


def fetch_pubmed_summaries(pubmed_ids: List[str], config: AppConfig) -> Dict[str, dict]:
    if not pubmed_ids:
        return {}
    params = {"db": "pubmed", "id": ",".join(pubmed_ids), "retmode": "json"}
    if config.ncbi_api_key:
        params["api_key"] = config.ncbi_api_key
    response = request_pubmed_with_retry(PUBMED_ESUMMARY_URL, params, config, "esummary")
    payload = response.json()
    result = payload.get("result", {})
    return {pmid: result[pmid] for pmid in result.get("uids", []) if pmid in result}


def fetch_pubmed_abstracts(pubmed_ids: List[str], config: AppConfig) -> Dict[str, str]:
    abstracts: Dict[str, str] = {}
    if not pubmed_ids:
        return abstracts

    batch_size = 100
    for index in range(0, len(pubmed_ids), batch_size):
        batch = pubmed_ids[index : index + batch_size]
        params = {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"}
        if config.ncbi_api_key:
            params["api_key"] = config.ncbi_api_key
        response = request_pubmed_with_retry(PUBMED_EFETCH_URL, params, config, "efetch")
        root = ElementTree.fromstring(response.text)
        for article in root.findall(".//PubmedArticle"):
            pmid = article.findtext(".//PMID")
            if not pmid:
                continue
            abstract_parts = []
            for abstract_node in article.findall(".//Abstract/AbstractText"):
                label = abstract_node.attrib.get("Label")
                content = "".join(abstract_node.itertext()).strip()
                if label:
                    abstract_parts.append(f"{label}: {content}")
                elif content:
                    abstract_parts.append(content)
            abstracts[pmid] = clean_text(" ".join(abstract_parts))
    return abstracts


def fetch_pubmed_papers(
    config: AppConfig,
    since_utc: datetime,
    queries: List[str],
    *,
    sort: str = "pub date",
    reldate_days: int | None = None,
    max_results_override: int | None = None,
) -> List[Paper]:
    all_ids: List[str] = []
    seen_ids = set()
    for idx, query in enumerate(queries):
        if idx > 0:
            interval = (
                PUBMED_QUERY_INTERVAL_WITH_KEY_SECONDS
                if config.ncbi_api_key
                else PUBMED_QUERY_INTERVAL_NO_KEY_SECONDS
            )
            time.sleep(interval)
        try:
            ids = fetch_pubmed_ids(
                query,
                config,
                sort=sort,
                reldate_days=reldate_days,
                max_results_override=max_results_override,
            )
        except Exception as exc:
            logging.warning("Skipping PubMed query due to failure: %s | query=%s", exc, query)
            continue
        for pmid in ids:
            if pmid not in seen_ids:
                all_ids.append(pmid)
                seen_ids.add(pmid)

    if not all_ids:
        return []

    try:
        summaries = fetch_pubmed_summaries(all_ids, config)
    except Exception as exc:
        logging.warning("Failed to fetch PubMed summaries; skipping PubMed source: %s", exc)
        return []

    try:
        abstracts = fetch_pubmed_abstracts(all_ids, config)
    except Exception as exc:
        logging.warning("Failed to fetch PubMed abstracts; continuing without abstracts: %s", exc)
        abstracts = {}

    papers: List[Paper] = []
    for pmid in all_ids:
        summary = summaries.get(pmid)
        if not summary:
            continue
        sort_pub_date = summary.get("sortpubdate") or summary.get("pubdate")
        published_at = parse_pubmed_datetime(sort_pub_date) or datetime.now(timezone.utc)
        if published_at < since_utc:
            continue
        authors = [author.get("name", "") for author in summary.get("authors", []) if author.get("name")]
        papers.append(
            Paper(
                paper_id=f"pubmed:{pmid}",
                title=clean_text(summary.get("title", "")),
                abstract=abstracts.get(pmid, ""),
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                authors=authors,
                published_at_utc=published_at,
                source="PubMed",
            )
        )
    return papers


def parse_retry_after_seconds(value: str) -> float | None:
    raw = clean_text(value)
    if not raw:
        return None
    try:
        seconds = float(raw)
    except ValueError:
        return None
    if seconds < 0:
        return None
    return seconds


def request_pubmed_with_retry(
    url: str,
    params: Dict[str, Any],
    config: AppConfig,
    operation: str,
) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(1, PUBMED_MAX_RETRY_ATTEMPTS + 1):
        try:
            response = requests.get(url, params=params, timeout=HTTP_TIMEOUT_SECONDS)
        except Exception as exc:
            last_error = exc
            if attempt >= PUBMED_MAX_RETRY_ATTEMPTS:
                break
            sleep_seconds = min(
                PUBMED_RETRY_BACKOFF_MAX_SECONDS,
                PUBMED_RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)),
            )
            logging.warning(
                "PubMed %s request exception (attempt %d/%d). Retrying in %.1fs: %s",
                operation,
                attempt,
                PUBMED_MAX_RETRY_ATTEMPTS,
                sleep_seconds,
                mask_sensitive_text(str(exc)),
            )
            time.sleep(sleep_seconds)
            continue

        if response.status_code in PUBMED_RETRYABLE_STATUS_CODES and attempt < PUBMED_MAX_RETRY_ATTEMPTS:
            retry_after = parse_retry_after_seconds(response.headers.get("Retry-After", ""))
            sleep_seconds = retry_after
            if sleep_seconds is None:
                sleep_seconds = min(
                    PUBMED_RETRY_BACKOFF_MAX_SECONDS,
                    PUBMED_RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)),
                )
            logging.warning(
                "PubMed %s returned %s (attempt %d/%d). Retrying in %.1fs. url=%s",
                operation,
                response.status_code,
                attempt,
                PUBMED_MAX_RETRY_ATTEMPTS,
                sleep_seconds,
                mask_sensitive_text(response.url or url),
            )
            time.sleep(sleep_seconds)
            continue

        try:
            response.raise_for_status()
            return response
        except Exception as exc:
            last_error = exc
            break

    if last_error:
        raise RuntimeError(f"PubMed {operation} request failed after retries: {last_error}") from last_error
    raise RuntimeError(f"PubMed {operation} request failed without response.")


def fetch_semantic_scholar_papers(
    config: AppConfig,
    since_utc: datetime,
    queries: List[str],
    *,
    max_results_override: int | None = None,
) -> List[Paper]:
    papers_by_id: Dict[str, Paper] = {}
    configured_max = (
        config.semantic_scholar_max_results_per_query
        if max_results_override is None
        else int(max_results_override)
    )
    max_results = max(1, min(configured_max, SEMANTIC_SCHOLAR_MAX_RESULTS_HARD_LIMIT))
    headers: Dict[str, str] = {}
    if config.semantic_scholar_api_key:
        headers["x-api-key"] = config.semantic_scholar_api_key

    for idx, query in enumerate(queries):
        if idx > 0:
            time.sleep(SEMANTIC_SCHOLAR_QUERY_INTERVAL_SECONDS)
        params = {
            "query": query,
            "limit": max_results,
            "fields": SEMANTIC_SCHOLAR_FIELDS,
        }
        try:
            response = requests.get(
                SEMANTIC_SCHOLAR_API_URL,
                params=params,
                headers=headers or None,
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logging.warning(
                "Skipping Semantic Scholar query due to failure: %s | query=%s",
                exc,
                query,
            )
            continue

        rows = payload.get("data", [])
        if not isinstance(rows, list):
            continue

        for row in rows:
            if not isinstance(row, dict):
                continue
            published_at = parse_semantic_datetime(
                str(row.get("publicationDate", "")),
                row.get("year"),
            )
            if not published_at or published_at < since_utc:
                continue

            external_ids = row.get("externalIds", {})
            if not isinstance(external_ids, dict):
                external_ids = {}
            s2_id = clean_text(str(row.get("paperId", "")))
            doi = clean_text(str(external_ids.get("DOI", ""))).lower()
            paper_url = clean_text(str(row.get("url", "")))

            if s2_id:
                paper_id = f"s2:{s2_id}"
            elif doi:
                paper_id = f"doi:{doi}"
            elif paper_url:
                paper_id = f"url:{paper_url}"
            else:
                continue

            if not paper_url and s2_id:
                paper_url = f"https://www.semanticscholar.org/paper/{s2_id}"

            authors: List[str] = []
            authors_raw = row.get("authors", [])
            if isinstance(authors_raw, list):
                for author in authors_raw:
                    if isinstance(author, dict):
                        name = clean_text(str(author.get("name", "")))
                        if name:
                            authors.append(name)

            title = clean_text(str(row.get("title", "")))
            if not title:
                continue
            abstract = clean_text(str(row.get("abstract", "")))

            papers_by_id[paper_id] = Paper(
                paper_id=paper_id,
                title=title,
                abstract=abstract,
                url=paper_url or "https://www.semanticscholar.org/",
                authors=authors,
                published_at_utc=published_at,
                source="SemanticScholar",
            )
    return list(papers_by_id.values())


def fetch_google_scholar_papers(
    config: AppConfig,
    since_utc: datetime,
    now_utc: datetime,
    queries: List[str],
    *,
    max_results_override: int | None = None,
) -> List[Paper]:
    if not config.google_scholar_api_key:
        logging.warning("Skipping Google Scholar search: GOOGLE_SCHOLAR_API_KEY is not set.")
        return []

    papers_by_id: Dict[str, Paper] = {}
    configured_max = (
        config.google_scholar_max_results_per_query
        if max_results_override is None
        else int(max_results_override)
    )
    max_results = max(1, min(configured_max, GOOGLE_SCHOLAR_MAX_RESULTS_HARD_LIMIT))

    for idx, query in enumerate(queries):
        if idx > 0:
            time.sleep(GOOGLE_SCHOLAR_QUERY_INTERVAL_SECONDS)
        params = {
            "engine": "google_scholar",
            "q": query,
            "num": max_results,
            "api_key": config.google_scholar_api_key,
            "hl": "en",
        }
        try:
            response = requests.get(
                GOOGLE_SCHOLAR_SERPAPI_URL,
                params=params,
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logging.warning(
                "Skipping Google Scholar query due to failure: %s | query=%s",
                mask_sensitive_text(str(exc)),
                query,
            )
            continue

        rows = payload.get("organic_results", [])
        if not isinstance(rows, list):
            continue

        for row in rows:
            if not isinstance(row, dict):
                continue
            title = clean_text(str(row.get("title", "")))
            if not title:
                continue
            url = clean_text(str(row.get("link", "")))
            snippet = clean_text(str(row.get("snippet", "")))
            pub_info = row.get("publication_info", {})
            if not isinstance(pub_info, dict):
                pub_info = {}
            summary_text = clean_text(str(pub_info.get("summary", "")))

            authors: List[str] = []
            author_rows = pub_info.get("authors", [])
            if isinstance(author_rows, list):
                for author in author_rows:
                    if isinstance(author, dict):
                        author_name = clean_text(str(author.get("name", "")))
                    else:
                        author_name = clean_text(str(author))
                    if author_name:
                        authors.append(author_name)

            published_at = (
                parse_google_scholar_datetime(summary_text, now_utc)
                or parse_google_scholar_datetime(snippet, now_utc)
                or now_utc
            )
            if published_at < since_utc:
                continue

            paper_id = ""
            result_id = clean_text(str(row.get("result_id", "")))
            if result_id:
                paper_id = f"gscholar:{result_id}"
            elif url:
                paper_id = f"url:{url.lower()}"
            else:
                paper_id = f"gscholar:title:{title.lower()}"

            papers_by_id[paper_id] = Paper(
                paper_id=paper_id,
                title=title,
                abstract=snippet or summary_text,
                url=url or "https://scholar.google.com/",
                authors=authors,
                published_at_utc=published_at,
                source="GoogleScholar",
            )

    return list(papers_by_id.values())

def prefilter_candidates_for_llm(papers: List[Paper], config: AppConfig) -> List[Paper]:
    if not papers:
        return []

    scored: List[Paper] = []
    for paper in papers:
        apply_topic_metadata_to_paper(paper, config)
        scored.append(paper)

    scored.sort(key=lambda item: (item.score, item.published_at_utc), reverse=True)
    with_keywords = [item for item in scored if item.score > 0]
    candidates = with_keywords or scored
    return candidates[: max(1, config.llm_max_candidates)]


def build_llm_scoring_prompt(
    project_context: str,
    project_names: List[str],
    payload_items: List[Dict[str, Any]],
    output_language: str,
    search_request: SearchRequest,
) -> str:
    policy_blocks: List[str] = []
    for mode in ("strict", "balanced", "discovery"):
        policy = get_relevance_mode_policy(mode)
        threshold = relevance_mode_threshold(mode, 6.0)
        mode_lines = "\n".join(f"  - {line}" for line in policy.get("prompt_lines", []))
        policy_blocks.append(
            f"{relevance_mode_label(mode)} mode (pass >= {threshold:.1f}):\n{mode_lines}"
        )
    policy_lines = "\n".join(policy_blocks)
    intent_lines = "\n".join(f"- {line}" for line in build_search_intent_prompt_lines(search_request))
    return (
        "You are a personalized research assistant.\n"
        "Evaluate how relevant each paper is to the user's research projects.\n"
        "Each paper includes a primary matched topic_name and that topic's relevance_mode.\n"
        "Use the matched topic as the first lens, then map the paper to the best project_name when possible.\n"
        "All candidates are shown together so you can rank them on a consistent shared scale.\n"
        "Project context:\n"
        f"{project_context}\n\n"
        "For each paper, do the following:\n"
        "1) score relevance from 1 to 10\n"
        f"2) write one short relevance reason in {output_language}\n"
        f"3) write core-point summary in {output_language} using 3-4 short lines\n"
        f"4) write usefulness explanation in {output_language} using 3-4 short lines\n"
        "5) provide 1-3 evidence spans (exact short phrases copied from title/abstract)\n\n"
        "Return ONLY JSON object:\n"
        "{\n"
        '  "items": [\n'
        "    {\n"
        '      "id": "...",\n'
        '      "relevance_score": 1,\n'
        '      "project_name": "...",\n'
        '      "relevance_reason": "...",\n'
        '      "core_point": "...",\n'
        '      "usefulness": "...",\n'
        '      "evidence_spans": ["...", "..."]\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Search intent guidance:\n"
        f"{intent_lines}\n"
        "Topic-mode scoring guidance:\n"
        f"{policy_lines}\n"
        "- Apply the scoring policy that matches each paper's topic_mode.\n"
        "- project_name must be one of the provided project names when possible; otherwise use empty string.\n"
        "- score must be integer 1..10\n"
        f"- requested time horizon: {search_request.time_horizon_label}\n"
        "- do not hallucinate beyond title and abstract\n\n"
        f"Allowed project names: {json.dumps(project_names, ensure_ascii=False)}\n\n"
        f"Papers JSON:\n{json.dumps(payload_items, ensure_ascii=False)}"
    )


def annotate_papers_with_llm(
    papers: List[Paper],
    config: AppConfig,
    search_request: SearchRequest,
) -> Tuple[List[Paper], Dict[str, Any]]:
    if not papers:
        return [], {
            "mode": "llm",
            "threshold": config.llm_relevance_threshold,
            "scoring_candidates": 0,
            "scored_count": 0,
            "pass_count": 0,
            "score_buckets": {},
            "relevance_policy_summary": [],
        }

    project_context = build_project_context_text(config.research_projects)
    project_name_lookup = {
        clean_text(project.name).lower(): project.name
        for project in config.research_projects
        if clean_text(project.name)
    }
    project_names = [name for name in project_name_lookup.values()]
    by_id = {paper.paper_id: paper for paper in papers}
    output_language = output_language_display_name(config.output_language)
    for paper in papers:
        paper.score = 0.0
        paper.llm_relevance_text = ""
        paper.llm_core_point_text = ""
        paper.llm_usefulness_text = ""
        paper.llm_evidence_spans = []
        paper.relevance_mode = normalize_relevance_mode(
            getattr(paper, "relevance_mode", LLM_RELEVANCE_MODE_DEFAULT)
        )
        if getattr(paper, "relevance_threshold", 0.0) <= 0:
            paper.relevance_threshold = relevance_mode_threshold(
                paper.relevance_mode,
                config.llm_relevance_threshold,
            )
    payload_items = []
    for paper in papers:
        payload_items.append(
            {
                "id": paper.paper_id,
                "title": paper.title,
                "abstract": clean_text(paper.abstract)[:1500],
                "source": paper.source,
                "published_at_utc": paper.published_at_utc.isoformat(),
                "topic_name": paper.topic,
                "topic_mode": paper.relevance_mode,
                "topic_threshold": paper.relevance_threshold,
                "matched_keywords": (paper.matched_keywords or [])[:8],
            }
        )

    prompt = build_llm_scoring_prompt(
        project_context=project_context,
        project_names=project_names,
        payload_items=payload_items,
        output_language=output_language,
        search_request=search_request,
    )
    llm_json = call_llm_json(config, prompt, temperature=0.15)
    raw_items = llm_json.get("items", []) if isinstance(llm_json, dict) else []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        paper_id = clean_text(str(item.get("id", "")))
        paper = by_id.get(paper_id)
        if not paper:
            continue
        try:
            score = float(item.get("relevance_score", 0))
        except (TypeError, ValueError):
            score = 0.0
        evidence_spans: List[str] = []
        evidence_raw = item.get("evidence_spans", [])
        if isinstance(evidence_raw, list):
            for span in evidence_raw[:3]:
                text = clean_text(str(span))
                if text:
                    evidence_spans.append(text[:220])
        elif isinstance(evidence_raw, str):
            for span in re.split(r"[\n;]+", evidence_raw):
                text = clean_text(span)
                if text:
                    evidence_spans.append(text[:220])
                if len(evidence_spans) >= 3:
                    break
        if score >= 7.0 and not evidence_spans:
            score = 5.5
        paper.score = max(0.0, min(10.0, score))
        paper.llm_relevance_text = clean_text(
            str(item.get("relevance_reason", item.get("relevance_reason_ko", "")))
        )
        paper.llm_core_point_text = clean_text(
            str(item.get("core_point", item.get("core_point_ko", "")))
        )
        paper.llm_usefulness_text = clean_text(
            str(item.get("usefulness", item.get("usefulness_ko", "")))
        )
        paper.llm_evidence_spans = evidence_spans
        project_name = clean_text(str(item.get("project_name", "")))
        if project_name:
            canonical_name = project_name_lookup.get(project_name.lower())
            if canonical_name:
                paper.project_name = canonical_name

    selected = [paper for paper in papers if paper.score >= paper.relevance_threshold]
    selected.sort(key=lambda item: (item.score, item.published_at_utc), reverse=True)
    scored_values = [paper.score for paper in papers]
    metadata = {
        "mode": "llm_listwise",
        "threshold": min((paper.relevance_threshold for paper in papers), default=config.llm_relevance_threshold),
        "scoring_candidates": len(papers),
        "scored_count": len([value for value in scored_values if value > 0]),
        "pass_count": len(selected),
        "score_buckets": build_score_buckets(scored_values),
        "scored_examples": build_scored_examples(papers, limit=40),
        "relevance_policy_summary": build_relevance_policy_summary(
            papers,
            config.llm_relevance_threshold,
        ),
    }
    return selected, metadata


def rank_relevant_papers_keyword(
    papers: List[Paper],
    config: AppConfig,
    search_request: SearchRequest,
    now_utc: datetime,
) -> Tuple[List[Paper], Dict[str, Any]]:
    scored = prioritize_candidates_for_search(papers, config, search_request, now_utc)
    ranked = [paper for paper in scored if paper.score >= config.min_relevance_score]
    scored_values = [paper.score for paper in scored]
    metadata = {
        "mode": "keyword_search",
        "threshold": config.min_relevance_score,
        "scoring_candidates": len(scored),
        "scored_count": len(scored),
        "pass_count": len(ranked),
        "score_buckets": build_score_buckets(scored_values),
        "scored_examples": build_scored_examples(scored, limit=40),
        "relevance_policy_summary": build_relevance_policy_summary(
            scored,
            config.llm_relevance_threshold,
        ),
    }
    return ranked, metadata


def rank_relevant_papers(
    papers: List[Paper],
    config: AppConfig,
    search_request: SearchRequest,
    now_utc: datetime,
) -> Tuple[List[Paper], Dict[str, Any]]:
    if not papers:
        return (
            [],
            {
                "mode": "no_candidates",
                "threshold": config.llm_relevance_threshold
                if (config.enable_llm_agent and has_llm_provider(config))
                else config.min_relevance_score,
                "scoring_candidates": 0,
                "scored_count": 0,
                "pass_count": 0,
                "score_buckets": {},
                "relevance_policy_summary": [],
            },
        )
    if config.enable_llm_agent and has_llm_provider(config):
        try:
            candidates = prioritize_candidates_for_search(papers, config, search_request, now_utc)
            candidates = candidates[: max(1, config.llm_max_candidates)]
            llm_ranked, llm_meta = annotate_papers_with_llm(candidates, config, search_request)
            if llm_ranked:
                return llm_ranked, llm_meta
            logging.warning("LLM ranking returned no papers. Falling back to keyword ranking.")
            keyword_ranked, keyword_meta = rank_relevant_papers_keyword(
                papers,
                config,
                search_request,
                now_utc,
            )
            keyword_meta["llm_fallback_reason"] = "llm_returned_no_pass"
            keyword_meta["llm_threshold"] = config.llm_relevance_threshold
            keyword_meta["llm_score_buckets"] = llm_meta.get("score_buckets", {})
            keyword_meta["llm_scored_examples"] = llm_meta.get("scored_examples", [])
            keyword_meta["llm_scoring_candidates"] = llm_meta.get("scoring_candidates", len(candidates))
            keyword_meta["llm_scored_count"] = llm_meta.get("scored_count", 0)
            keyword_meta["llm_pass_count"] = llm_meta.get("pass_count", 0)
            return keyword_ranked, keyword_meta
        except Exception as exc:
            safe_error = mask_sensitive_text(str(exc))
            logging.warning("LLM ranking failed. Falling back to keyword ranking: %s", safe_error)
            keyword_ranked, keyword_meta = rank_relevant_papers_keyword(
                papers,
                config,
                search_request,
                now_utc,
            )
            keyword_meta["llm_fallback_reason"] = f"llm_error: {safe_error}"
            return keyword_ranked, keyword_meta
    return rank_relevant_papers_keyword(papers, config, search_request, now_utc)

def format_authors(authors: List[str], limit: int = 4) -> str:
    if not authors:
        return "N/A"
    if len(authors) <= limit:
        return ", ".join(authors)
    return ", ".join(authors[:limit]) + f" et al. (+{len(authors) - limit})"


def format_local_time(dt_utc: datetime, timezone_name: str) -> str:
    local_dt = dt_utc.astimezone(ZoneInfo(timezone_name))
    return local_dt.strftime("%Y-%m-%d %H:%M %Z")


def escape_multiline(text: str) -> str:
    return html.escape(text).replace("\n", "<br/>")


def format_score_buckets_text(buckets: Dict[str, int]) -> str:
    if not buckets:
        return "N/A"
    return (
        f"9-10: {buckets.get('9-10', 0)}, "
        f"7-8: {buckets.get('7-8', 0)}, "
        f"5-6: {buckets.get('5-6', 0)}, "
        f"1-4: {buckets.get('1-4', 0)}, "
        f"0: {buckets.get('0', 0)}"
    )


def build_diagnostics_lines(stats: DigestStats) -> List[str]:
    lines = [
        f"Search intent: {stats.search_intent_label}",
        f"Requested horizon: {stats.requested_time_horizon_label}",
        f"Window used: {stats.window_used_label or stats.requested_time_horizon_label}",
        f"Query plan: {stats.query_plan_label or 'N/A'}",
        (
            f"Collected candidates: arXiv {stats.arxiv_candidates}, PubMed {stats.pubmed_candidates}, "
            f"SemanticScholar {stats.semantic_scholar_candidates}, "
            f"GoogleScholar {stats.google_scholar_candidates}, "
            f"total {stats.total_candidates}"
        ),
        f"After time filter: {stats.post_time_filter_candidates}",
        f"Query strategy: {stats.query_strategy}",
        f"Ranking mode: {stats.ranking_mode}",
        f"Send cadence: {stats.send_frequency}",
        f"Lookback window: last {stats.lookback_hours}h",
    ]
    if stats.search_notice:
        lines.append("Search note: " + stats.search_notice)
    if not stats.llm_agent_enabled:
        lines.append("LLM ranking: disabled (ENABLE_LLM_AGENT=false)")
    elif not stats.llm_provider_ready:
        lines.append("LLM ranking: unavailable (no active provider/API key)")
    else:
        lines.append("LLM ranking: enabled")
    if stats.ranking_threshold > 0:
        lines.append(f"Relevance threshold: {stats.ranking_threshold:.1f}")
    if stats.relevance_policy_summary:
        lines.extend("Relevance policy: " + line for line in stats.relevance_policy_summary)
    if stats.scoring_candidates > 0:
        lines.append(f"Scoring candidates: {stats.scoring_candidates}")
    if stats.scored_count > 0:
        lines.append(f"Scored papers: {stats.scored_count}")
    lines.append("Score distribution: " + format_score_buckets_text(stats.score_buckets))
    if stats.scored_examples:
        lines.append("Scored papers (score | title): " + " || ".join(stats.scored_examples[:40]))
    lines.append(f"Passed threshold: {stats.pass_count}")
    if stats.project_cadence_filtered_out > 0:
        lines.append(
            "Project cadence filter removed: "
            f"{stats.project_cadence_filtered_out}"
        )
    if stats.project_cadence_summary:
        lines.extend(stats.project_cadence_summary)
    if stats.llm_fallback_score_buckets:
        lines.append(
            "LLM pre-fallback score distribution: "
            + format_score_buckets_text(stats.llm_fallback_score_buckets)
        )
    if stats.llm_fallback_scored_examples:
        lines.append(
            "LLM pre-fallback papers (score | title): "
            + " || ".join(stats.llm_fallback_scored_examples[:40])
        )
    if stats.llm_fallback_reason:
        lines.append(f"LLM fallback info: {stats.llm_fallback_reason}")
    if stats.zero_candidate_recovery_steps:
        lines.append("Zero-candidate recovery:")
        for step in stats.zero_candidate_recovery_steps:
            lines.append(f" - {step}")
    if stats.duplicates_filtered > 0:
        lines.append(f"Duplicate filtered: {stats.duplicates_filtered}")
    if stats.estimated_llm_calls_upper_bound > 0:
        lines.append(f"Estimated max LLM calls (one run): {stats.estimated_llm_calls_upper_bound}")
    if stats.llm_max_candidates_effective > 0:
        lines.append(
            f"LLM candidate cap: base {stats.llm_max_candidates_base} -> effective {stats.llm_max_candidates_effective}"
        )
    lines.append(f"Final included: {stats.final_selected}")
    return lines


def score_badge_colors(score: float) -> Tuple[str, str, str]:
    if score >= 8.0:
        return "#1a7a3a", "#1a7a3a", "#e6f4eb"
    if score >= 7.0:
        return "#b8860b", "#8a6b09", "#fef8e8"
    return "#9a9a9a", "#6b7280", "#f5f5f5"


def source_badge_style(source: str) -> Tuple[str, str, str]:
    source_key = (source or "").strip().lower()
    if source_key == "arxiv":
        return ("arXiv", "#b31b1b", "#fef2f2")
    if source_key == "pubmed":
        return ("PubMed", "#326599", "#eff5fb")
    if source_key in {"semanticscholar", "semantic scholar"}:
        return ("Semantic Scholar", "#1857b6", "#eff4fc")
    if source_key in {"google scholar", "googlescholar"}:
        return ("Google Scholar", "#4285f4", "#eef3fe")
    return (source or "Source", "#374151", "#f3f4f6")


def render_score_dots(score: float, dot_color: str) -> str:
    filled = max(0, min(10, int(round(score))))
    dots: List[str] = []
    for idx in range(10):
        color = dot_color if idx < filled else "#d1d5db"
        dots.append(
            f'<span style="display:inline-block;width:6px;height:6px;'
            f'border-radius:50%;background:{color};margin-right:2px;line-height:6px;">&nbsp;</span>'
        )
    return "".join(dots)


def compose_email_html(
    papers: List[Paper],
    now_utc: datetime,
    since_utc: datetime,
    timezone_name: str,
    output_language: str = "en",
    stats: DigestStats | None = None,
) -> str:
    ui = email_ui_labels(output_language)
    now_local = format_local_time(now_utc, timezone_name)
    since_local = format_local_time(since_utc, timezone_name)
    search_intent_text = stats.search_intent_label if stats else "Search"
    requested_horizon_text = stats.requested_time_horizon_label if stats else "Custom"
    window_used_text = stats.window_used_label if stats and stats.window_used_label else requested_horizon_text
    query_plan_text = stats.query_plan_label if stats and stats.query_plan_label else "N/A"
    search_notice = stats.search_notice if stats and stats.search_notice else ""

    diagnostics_html = ""
    if stats:
        diagnostics_rows = "".join(
            (
                "<tr>"
                "<td style=\"padding:4px 0;font-size:12px;line-height:1.5;color:#475569;\">"
                f"- {html.escape(line)}"
                "</td>"
                "</tr>"
            )
            for line in build_diagnostics_lines(stats)
        )
        diagnostics_html = f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:16px;border:1px solid #e5e7eb;border-radius:10px;background:#f8fafc;">
          <tr>
            <td style="padding:12px 14px;border-bottom:1px solid #e5e7eb;font-size:14px;font-weight:700;color:#0f172a;">
              Selection diagnostics
            </td>
          </tr>
          <tr>
            <td style="padding:10px 14px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                {diagnostics_rows}
              </table>
            </td>
          </tr>
        </table>
        """

    scanned_count = 0
    if stats:
        scanned_count = stats.post_time_filter_candidates or stats.total_candidates
    if scanned_count <= 0:
        scanned_count = len(papers)
    selected_count = len(papers)
    top_score = max((paper.score for paper in papers), default=0.0)
    source_labels: List[str] = []
    for paper in papers:
        label, _, _ = source_badge_style(paper.source)
        if label not in source_labels:
            source_labels.append(label)
    source_summary = " | ".join(source_labels) if source_labels else "N/A"
    window_text = f"{since_local} ~ {now_local}"
    notice_html = ""
    if search_notice:
        notice_html = f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:14px;border-left:3px solid #6a9fd8;background:#f2f6fb;border-radius:7px;">
          <tr>
            <td style="padding:10px 12px;">
              <div style="font-size:10px;letter-spacing:0.8px;text-transform:uppercase;font-weight:700;color:#4a7fb5;">Search note</div>
              <div style="margin-top:4px;font-size:13px;line-height:1.6;color:#5a5a5a;">{html.escape(search_notice)}</div>
            </td>
          </tr>
        </table>
        """
    header_html = f"""
                <tr>
                  <td style="padding:30px 28px 24px;background:linear-gradient(135deg,#1a2f23 0%,#2d5a3d 60%,#3a7a52 100%);color:#ffffff;">
                    <div style="font-size:24px;font-weight:700;line-height:1.2;">Paper Morning</div>
                    <div style="margin-top:6px;font-size:14px;color:#d7e7dd;">Research-context paper search result</div>
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:14px;">
                      <tr>
                        <td style="font-size:12px;color:#a8c4b4;padding:0 10px 6px 0;white-space:nowrap;">Intent</td>
                        <td style="font-size:12px;color:#f4fbf7;padding:0 0 6px 0;">{html.escape(search_intent_text)}</td>
                      </tr>
                      <tr>
                        <td style="font-size:12px;color:#a8c4b4;padding:0 10px 6px 0;white-space:nowrap;">Requested horizon</td>
                        <td style="font-size:12px;color:#f4fbf7;padding:0 0 6px 0;">{html.escape(requested_horizon_text)}</td>
                      </tr>
                      <tr>
                        <td style="font-size:12px;color:#a8c4b4;padding:0 10px 6px 0;white-space:nowrap;">Window used</td>
                        <td style="font-size:12px;color:#f4fbf7;padding:0 0 6px 0;">{html.escape(window_used_text)}</td>
                      </tr>
                      <tr>
                        <td style="font-size:12px;color:#a8c4b4;padding:0 10px 6px 0;white-space:nowrap;">Query plan</td>
                        <td style="font-size:12px;color:#f4fbf7;padding:0 0 6px 0;">{html.escape(query_plan_text)}</td>
                      </tr>
                      <tr>
                        <td style="font-size:12px;color:#a8c4b4;padding:0 10px 6px 0;white-space:nowrap;">Window</td>
                        <td style="font-size:12px;color:#f4fbf7;padding:0 0 6px 0;">{html.escape(window_text)}</td>
                      </tr>
                      <tr>
                        <td style="font-size:12px;color:#a8c4b4;padding:0 10px 0 0;white-space:nowrap;">Sources</td>
                        <td style="font-size:12px;color:#f4fbf7;padding:0;">{html.escape(source_summary)}</td>
                      </tr>
                    </table>
                  </td>
                </tr>
    """

    if not papers:
        return f"""
        <html>
          <body style="margin:0;padding:0;background:#e8e6e1;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#e8e6e1;padding:24px 0;">
              <tr>
                <td align="center">
                  <table role="presentation" width="680" cellpadding="0" cellspacing="0" style="width:680px;max-width:680px;background:#f6f5f1;border:1px solid #e5e3de;border-radius:12px;overflow:hidden;">
                    {header_html}
                    <tr>
                      <td style="padding:16px 22px 10px;background:#ffffff;border-bottom:1px solid #e5e3de;">
                        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5e3de;border-radius:10px;background:#ffffff;">
                          <tr>
                            <td align="center" style="padding:10px 6px;border-right:1px solid #e5e3de;">
                              <div style="font-size:22px;font-weight:700;color:#2d5a3d;">{scanned_count}</div>
                              <div style="font-size:10px;letter-spacing:1px;color:#8a8a8a;">SCANNED</div>
                            </td>
                            <td align="center" style="padding:10px 6px;border-right:1px solid #e5e3de;">
                              <div style="font-size:22px;font-weight:700;color:#2d5a3d;">{selected_count}</div>
                              <div style="font-size:10px;letter-spacing:1px;color:#8a8a8a;">SELECTED</div>
                            </td>
                            <td align="center" style="padding:10px 6px;">
                              <div style="font-size:22px;font-weight:700;color:#2d5a3d;">{top_score:.1f}</div>
                              <div style="font-size:10px;letter-spacing:1px;color:#8a8a8a;">TOP SCORE</div>
                            </td>
                          </tr>
                        </table>
                        <div style="padding:18px 4px 4px;font-size:14px;color:#5a5a5a;">
                          {html.escape(search_notice or f'No sufficiently relevant papers were found for {search_intent_text.lower()} in {requested_horizon_text.lower()}.')}
                        </div>
                        {notice_html}
                        {diagnostics_html}
                      </td>
                    </tr>
                    <tr>
                      <td style="padding:16px 22px 20px;border-top:1px solid #e5e3de;background:#ffffff;">
                    <div style="font-size:11px;line-height:1.6;color:#8a8a8a;text-align:center;">
                          Generated by Paper Morning | Search-first local result
                    </div>
                  </td>
                </tr>
                  </table>
                </td>
              </tr>
            </table>
          </body>
        </html>
        """

    sections = []
    for idx, paper in enumerate(papers, start=1):
        full_abstract = clean_text(paper.abstract)
        snippet = full_abstract[:520]
        if len(full_abstract) > 520:
            snippet += "..."
        keywords = (paper.matched_keywords or [])[:8]
        keywords_html = "".join(
            f'<span style="display:inline-block;padding:3px 8px;margin:0 6px 6px 0;border-radius:4px;'
            f'background:#f3f4f6;color:#475569;font-size:11px;">{html.escape(keyword)}</span>'
            for keyword in keywords
        )
        if not keywords_html:
            keywords_html = '<span style="font-size:12px;color:#6b7280;">N/A</span>'

        score_dot_color, score_fg, score_bg = score_badge_colors(paper.score)
        score_dots = render_score_dots(paper.score, score_dot_color)
        source_label, source_fg, source_bg = source_badge_style(paper.source)
        authors_text = html.escape(format_authors(paper.authors))
        published_local = html.escape(format_local_time(paper.published_at_utc, timezone_name))
        topic_label = html.escape(paper.topic or "N/A")
        project_label = html.escape(paper.project_name or "N/A")
        mode_text = relevance_mode_label(paper.relevance_mode)
        if paper.relevance_threshold > 0:
            mode_text = f"{mode_text} >= {paper.relevance_threshold:.1f}"
        mode_label = html.escape(mode_text)

        relevance_text = escape_multiline(paper.llm_relevance_text or ui["fallback_relevance"])
        core_text = escape_multiline(paper.llm_core_point_text or ui["fallback_core"])
        useful_text = escape_multiline(paper.llm_usefulness_text or ui["fallback_useful"])

        sections.append(
            f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px;border:1px solid #e5e3de;border-radius:10px;background:#ffffff;">
          <tr>
            <td style="padding:12px 18px;border-bottom:1px solid #e5e3de;background:#fafaf8;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td valign="middle" style="font-size:12px;color:#6b7280;">
                    <span style="font-family:monospace;">#{idx}</span>
                    <span style="display:inline-block;margin-left:8px;padding:4px 10px;border-radius:16px;background:{score_bg};color:{score_fg};font-weight:700;font-size:12px;">
                      {score_dots} {paper.score:.1f}
                    </span>
                  </td>
                  <td align="right" valign="middle">
                    <span style="display:inline-block;padding:4px 8px;border-radius:5px;background:{source_bg};color:{source_fg};font-size:10px;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;">
                      {html.escape(source_label)}
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 18px 18px;">
              <div style="font-size:19px;line-height:1.4;font-weight:700;color:#1a1a1a;">
                <a href="{html.escape(paper.url)}" style="color:#1a1a1a;text-decoration:none;">{html.escape(paper.title)}</a>
              </div>
              <div style="margin-top:8px;font-size:12px;line-height:1.55;color:#8a8a8a;">
                {authors_text}<br/>Published {published_local}
              </div>
              <div style="margin-top:10px;font-size:12px;line-height:1.5;color:#475569;">
                <span style="display:inline-block;margin:0 8px 6px 0;padding:4px 8px;border-radius:999px;background:#eef5ef;color:#2d5a3d;">
                  {html.escape(ui["topic"])}: {topic_label}
                </span>
                <span style="display:inline-block;margin:0 8px 6px 0;padding:4px 8px;border-radius:999px;background:#f3f4f6;color:#475569;">
                  {html.escape(ui["project"])}: {project_label}
                </span>
                <span style="display:inline-block;margin:0 8px 6px 0;padding:4px 8px;border-radius:999px;background:#f8f6f2;color:#8a7d5a;">
                  {html.escape(ui["mode"])}: {mode_label}
                </span>
              </div>
              <div style="margin-top:10px;">{keywords_html}</div>

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:10px;border-left:3px solid #2d5a3d;background:#e8f0eb;border-radius:7px;">
                <tr>
                  <td style="padding:10px 12px;">
                    <div style="font-size:10px;letter-spacing:0.8px;text-transform:uppercase;font-weight:700;color:#1f4d34;">{html.escape(ui["why"])}</div>
                    <div style="margin-top:4px;font-size:13px;line-height:1.6;color:#5a5a5a;">{relevance_text}</div>
                  </td>
                </tr>
              </table>

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:8px;border-left:3px solid #c4b99a;background:#f8f6f2;border-radius:7px;">
                <tr>
                  <td style="padding:10px 12px;">
                    <div style="font-size:10px;letter-spacing:0.8px;text-transform:uppercase;font-weight:700;color:#8a7d5a;">{html.escape(ui["key"])}</div>
                    <div style="margin-top:4px;font-size:13px;line-height:1.6;color:#5a5a5a;">{core_text}</div>
                  </td>
                </tr>
              </table>

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:8px;border-left:3px solid #6a9fd8;background:#f2f6fb;border-radius:7px;">
                <tr>
                  <td style="padding:10px 12px;">
                    <div style="font-size:10px;letter-spacing:0.8px;text-transform:uppercase;font-weight:700;color:#4a7fb5;">{html.escape(ui["how"])}</div>
                    <div style="margin-top:4px;font-size:13px;line-height:1.6;color:#5a5a5a;">{useful_text}</div>
                  </td>
                </tr>
              </table>

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:10px;border-top:1px dashed #e5e3de;">
                <tr>
                  <td style="padding-top:10px;font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.7px;font-weight:700;">
                    {html.escape(ui["abstract"])}
                  </td>
                </tr>
                <tr>
                  <td style="padding-top:4px;font-size:12px;line-height:1.65;color:#8a8a8a;">
                    {html.escape(snippet or ui["fallback_abstract"])}
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
        """
        )

    return f"""
    <html>
      <body style="margin:0;padding:0;background:#e8e6e1;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#e8e6e1;padding:24px 0;">
          <tr>
            <td align="center">
              <table role="presentation" width="680" cellpadding="0" cellspacing="0" style="width:680px;max-width:680px;background:#f6f5f1;border:1px solid #e5e3de;border-radius:12px;overflow:hidden;">
                {header_html}

                <tr>
                  <td style="padding:16px 22px 10px;background:#ffffff;border-bottom:1px solid #e5e3de;">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5e3de;border-radius:10px;background:#ffffff;">
                      <tr>
                        <td align="center" style="padding:10px 6px;border-right:1px solid #e5e3de;">
                          <div style="font-size:22px;font-weight:700;color:#2d5a3d;">{scanned_count}</div>
                          <div style="font-size:10px;letter-spacing:1px;color:#8a8a8a;">SCANNED</div>
                        </td>
                        <td align="center" style="padding:10px 6px;border-right:1px solid #e5e3de;">
                          <div style="font-size:22px;font-weight:700;color:#2d5a3d;">{selected_count}</div>
                          <div style="font-size:10px;letter-spacing:1px;color:#8a8a8a;">SELECTED</div>
                        </td>
                        <td align="center" style="padding:10px 6px;">
                          <div style="font-size:22px;font-weight:700;color:#2d5a3d;">{top_score:.1f}</div>
                          <div style="font-size:10px;letter-spacing:1px;color:#8a8a8a;">TOP SCORE</div>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>

                <tr>
                  <td style="padding:0 22px 6px;">
                    {notice_html}
                    {''.join(sections)}
                    {diagnostics_html}
                  </td>
                </tr>

                <tr>
                  <td style="padding:16px 22px 20px;border-top:1px solid #e5e3de;background:#ffffff;">
                    <div style="font-size:11px;line-height:1.6;color:#8a8a8a;text-align:center;">
                      Generated by Paper Morning | Search-first local result
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """


def compose_email_text(
    papers: List[Paper],
    now_utc: datetime,
    since_utc: datetime,
    timezone_name: str,
    output_language: str = "en",
    stats: DigestStats | None = None,
) -> str:
    ui = email_ui_labels(output_language)
    search_intent_text = stats.search_intent_label if stats else "Search"
    requested_horizon_text = stats.requested_time_horizon_label if stats else "Custom"
    window_used_text = stats.window_used_label if stats and stats.window_used_label else requested_horizon_text
    lines = [
        "Paper Morning Search Result",
        f"Intent: {search_intent_text}",
        f"Requested horizon: {requested_horizon_text}",
        f"Window used: {window_used_text}",
        f"Window: {format_local_time(since_utc, timezone_name)} ~ {format_local_time(now_utc, timezone_name)}",
        f"Total selected: {len(papers)}",
        "",
    ]
    if not papers:
        lines.append(
            stats.search_notice if stats and stats.search_notice else "No sufficiently relevant papers were found."
        )
        if stats:
            lines.append("")
            lines.append("[Selection Diagnostics]")
            lines.extend(build_diagnostics_lines(stats))
        return "\n".join(lines)

    for idx, paper in enumerate(papers, start=1):
        lines.append(f"#{idx} [{paper.source}] {paper.title}")
        lines.append(f"URL: {paper.url}")
        mode_text = relevance_mode_label(paper.relevance_mode)
        if paper.relevance_threshold > 0:
            mode_text = f"{mode_text} (>= {paper.relevance_threshold:.1f})"
        lines.append(
            "Score: "
            f"{paper.score:.1f}/10 | Topic: {paper.topic or 'N/A'} | "
            f"Project: {paper.project_name or 'N/A'} | Mode: {mode_text}"
        )
        lines.append(f"Published: {format_local_time(paper.published_at_utc, timezone_name)}")
        lines.append(f"Authors: {format_authors(paper.authors)}")
        lines.append("Matched keywords: " + (", ".join((paper.matched_keywords or [])[:10]) or "N/A"))
        if paper.llm_relevance_text:
            lines.append(f"{ui['why']}: {paper.llm_relevance_text}")
        if paper.llm_core_point_text:
            lines.append(f"{ui['key']}:")
            lines.append(paper.llm_core_point_text)
        if paper.llm_usefulness_text:
            lines.append(f"{ui['how']}:")
            lines.append(paper.llm_usefulness_text)
        abstract = clean_text(paper.abstract)
        if len(abstract) > 500:
            abstract = abstract[:500] + "..."
        lines.append(f"Abstract: {abstract or ui['fallback_abstract']}")
        lines.append("")
    if stats:
        lines.append("[Selection Diagnostics]")
        lines.extend(build_diagnostics_lines(stats))
        lines.append("")
    return "\n".join(lines)


def send_email(config: AppConfig, subject: str, html_body: str, text_body: str) -> None:
    recipient = config.recipient_email or config.gmail_address
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.gmail_address
    msg["To"] = recipient
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    message_text = msg.as_string()
    delivery_mode = normalize_delivery_mode(config.delivery_mode)
    if delivery_mode == DELIVERY_MODE_LOCAL_INBOX:
        raise RuntimeError("Local inbox mode does not send email.")
    if delivery_mode == DELIVERY_MODE_GMAIL_OAUTH:
        send_email_via_google_oauth(config, message_text)
        return
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(config.gmail_address, config.gmail_app_password)
        smtp.sendmail(config.gmail_address, [recipient], message_text)

def collect_and_rank_papers(
    config: AppConfig,
    now_utc: datetime,
    search_request: SearchRequest,
    progress_callback: Callable[[str, int], None] | None = None,
) -> Tuple[List[Paper], DigestStats]:
    llm_provider_ready = has_llm_provider(config)
    stats = DigestStats(
        ranking_threshold=config.min_relevance_score,
        send_frequency=config.send_frequency,
        lookback_hours=search_request.time_horizon_hours,
        llm_max_candidates_base=config.llm_max_candidates_base,
        llm_max_candidates_effective=config.llm_max_candidates,
        llm_agent_enabled=config.enable_llm_agent,
        llm_provider_ready=llm_provider_ready,
        search_intent=search_request.intent,
        search_intent_label=search_request.intent_label,
        requested_time_horizon_key=search_request.time_horizon_key,
        requested_time_horizon_label=search_request.time_horizon_label,
    )
    if config.enable_llm_agent and llm_provider_ready:
        stats.estimated_llm_calls_upper_bound = 1
        stats.ranking_threshold = config.llm_relevance_threshold

    plans = build_search_query_plans(config)
    has_active_query = any(
        any(plan[key] for key in ("arxiv_queries", "pubmed_queries", "semantic_queries", "google_queries"))
        for plan in plans
    )
    if not has_active_query:
        raise ValueError(
            "Search query is empty. In Topic Editor, run 'Keyword / Query Generation' "
            "or manually fill arXiv/PubMed/Semantic Scholar/Google Scholar queries, then save topics."
        )

    retrieval_settings = build_search_retrieval_settings(search_request)
    reldate_days = max(1, int(search_request.time_horizon_hours / 24) + 1)
    stats.query_strategy = f"{search_request.intent}-saved-topics"
    emit_progress(progress_callback, "Preparing search queries...", 10)

    def fetch_from_plan(plan: Dict[str, List[str] | str]) -> Tuple[List[Paper], int, int, int, int]:
        since_utc = now_utc - timedelta(hours=search_request.time_horizon_hours)
        papers_acc: List[Paper] = []
        arxiv_papers_local: List[Paper] = []
        pubmed_papers_local: List[Paper] = []
        semantic_papers_local: List[Paper] = []
        google_scholar_papers_local: List[Paper] = []
        arxiv_queries = list(plan.get("arxiv_queries", []))
        pubmed_queries = list(plan.get("pubmed_queries", []))
        semantic_queries = list(plan.get("semantic_queries", []))
        google_queries = list(plan.get("google_queries", []))

        if arxiv_queries:
            emit_progress(progress_callback, "Fetching papers from arXiv...", 30)
            arxiv_papers_local = fetch_arxiv_papers(
                config,
                since_utc,
                arxiv_queries,
                sort_by=str(retrieval_settings["arxiv_sort"]),
                max_results_override=int(retrieval_settings["arxiv_max_results"]),
            )
            papers_acc.extend(arxiv_papers_local)
        if pubmed_queries:
            emit_progress(progress_callback, "Fetching papers from PubMed...", 45)
            pubmed_papers_local = fetch_pubmed_papers(
                config,
                since_utc,
                pubmed_queries,
                sort=str(retrieval_settings["pubmed_sort"]),
                reldate_days=reldate_days,
                max_results_override=int(retrieval_settings["pubmed_max_results"]),
            )
            papers_acc.extend(pubmed_papers_local)
        if config.enable_semantic_scholar and semantic_queries:
            emit_progress(progress_callback, "Fetching papers from Semantic Scholar...", 58)
            semantic_papers_local = fetch_semantic_scholar_papers(
                config,
                since_utc,
                semantic_queries,
                max_results_override=int(retrieval_settings["semantic_max_results"]),
            )
            papers_acc.extend(semantic_papers_local)
        if config.enable_google_scholar and google_queries:
            emit_progress(progress_callback, "Fetching papers from Google Scholar...", 66)
            google_scholar_papers_local = fetch_google_scholar_papers(
                config,
                since_utc,
                now_utc,
                google_queries,
                max_results_override=int(retrieval_settings["google_scholar_max_results"]),
            )
            papers_acc.extend(google_scholar_papers_local)
        return (
            dedupe_papers_by_title(papers_acc),
            len(arxiv_papers_local),
            len(pubmed_papers_local),
            len(semantic_papers_local),
            len(google_scholar_papers_local),
        )

    selected_candidates: List[Paper] = []
    selected_plan_label = ""
    recovery_steps: List[str] = []
    last_total_candidates = 0
    for index, plan in enumerate(plans, start=1):
        label = str(plan.get("label", f"plan-{index}"))
        recovery_steps.append(f"Trying {label}.")
        plan_papers, arxiv_count, pubmed_count, semantic_count, google_count = fetch_from_plan(plan)
        stats.arxiv_candidates = arxiv_count
        stats.pubmed_candidates = pubmed_count
        stats.semantic_scholar_candidates = semantic_count
        stats.google_scholar_candidates = google_count
        stats.total_candidates = len(plan_papers)
        last_total_candidates = len(plan_papers)
        if not plan_papers:
            recovery_steps.append(f"{label}: no candidates retrieved.")
            continue

        if search_request.intent == "whats_new":
            for window_key, window_hours in build_whats_new_horizon_steps(search_request):
                filtered = filter_papers_by_horizon(plan_papers, now_utc, window_hours)
                recovery_steps.append(
                    f"{label}: {len(filtered)} candidates inside {time_horizon_label(window_key, search_request.intent)}."
                )
                if filtered:
                    selected_candidates = filtered
                    selected_plan_label = label
                    stats.window_used_hours = window_hours
                    stats.window_used_label = time_horizon_label(window_key, search_request.intent)
                    break
            if selected_candidates:
                break
        else:
            filtered = filter_papers_by_horizon(plan_papers, now_utc, search_request.time_horizon_hours)
            recovery_steps.append(
                f"{label}: {len(filtered)} candidates inside {search_request.time_horizon_label}."
            )
            if filtered:
                selected_candidates = filtered
                selected_plan_label = label
                stats.window_used_hours = search_request.time_horizon_hours
                stats.window_used_label = search_request.time_horizon_label
                break

    stats.zero_candidate_recovery_steps = recovery_steps
    stats.query_plan_label = selected_plan_label or (str(plans[-1].get("label", "")) if plans else "")
    if not stats.window_used_label:
        stats.window_used_hours = search_request.time_horizon_hours
        stats.window_used_label = search_request.time_horizon_label
    if not selected_candidates:
        stats.query_strategy = f"{search_request.intent}-no-results"
        stats.post_time_filter_candidates = 0
        stats.no_results_reason = "outside_horizon" if last_total_candidates > 0 else "none_retrieved"
        if stats.no_results_reason == "outside_horizon":
            stats.search_notice = (
                f"Candidates were retrieved, but none stayed inside {search_request.time_horizon_label}. "
                "Try a broader time horizon or use Discovery mode."
            )
        else:
            stats.search_notice = (
                f"No papers were found within {search_request.time_horizon_label}. "
                "Try a broader time horizon, Discovery mode, or revise your project context."
            )
        return [], stats

    emit_progress(progress_callback, "Ranking relevant papers...", 75)
    selected_candidates = [paper for paper in selected_candidates if paper.published_at_utc <= now_utc]
    stats.post_time_filter_candidates = len(selected_candidates)
    ranked, rank_meta = rank_relevant_papers(selected_candidates, config, search_request, now_utc)
    stats.ranking_mode = str(rank_meta.get("mode", "keyword"))
    stats.ranking_threshold = float(rank_meta.get("threshold", stats.ranking_threshold or 0.0))
    stats.scoring_candidates = int(rank_meta.get("scoring_candidates", 0))
    stats.scored_count = int(rank_meta.get("scored_count", 0))
    stats.pass_count = int(rank_meta.get("pass_count", len(ranked)))
    score_buckets = rank_meta.get("score_buckets", {})
    if isinstance(score_buckets, dict):
        stats.score_buckets = {str(k): int(v) for k, v in score_buckets.items()}
    scored_examples = rank_meta.get("scored_examples", [])
    if isinstance(scored_examples, list):
        stats.scored_examples = [clean_text(str(item)) for item in scored_examples if clean_text(str(item))]
    relevance_policy_summary = rank_meta.get("relevance_policy_summary", [])
    if isinstance(relevance_policy_summary, list):
        stats.relevance_policy_summary = [
            clean_text(str(item)) for item in relevance_policy_summary if clean_text(str(item))
        ]
    stats.llm_fallback_reason = clean_text(str(rank_meta.get("llm_fallback_reason", "")))
    if "llm_score_buckets" in rank_meta and isinstance(rank_meta.get("llm_score_buckets"), dict):
        stats.llm_fallback_score_buckets = {
            str(k): int(v)
            for k, v in rank_meta.get("llm_score_buckets", {}).items()
        }
        llm_examples = rank_meta.get("llm_scored_examples", [])
        if isinstance(llm_examples, list):
            stats.llm_fallback_scored_examples = [
                clean_text(str(item)) for item in llm_examples if clean_text(str(item))
            ]
    stats.query_strategy = f"{search_request.intent}-{selected_plan_label or 'saved-topics'}"
    stats.search_notice = (
        f"{search_request.intent_label} searched {stats.window_used_label or search_request.time_horizon_label} "
        f"using {selected_plan_label or 'saved topic queries'}."
    )
    if not ranked:
        stats.no_results_reason = "below_threshold"
        stats.search_notice = (
            f"Candidates were retrieved in {stats.window_used_label or search_request.time_horizon_label}, "
            "but none passed the relevance threshold."
        )
    logging.info("Relevant papers selected: %d", len(ranked))
    emit_progress(progress_callback, "Paper ranking completed.", 90)
    return ranked, stats


def run_digest(
    config: AppConfig,
    dry_run: bool = False,
    force_send: bool = False,
    print_dry_run_output: bool = True,
    respect_schedule_policy: bool = False,
    search_intent: str | None = None,
    time_horizon_key: str | None = None,
    progress_callback: Callable[[str, int], None] | None = None,
) -> str:
    preview_only_mode = dry_run or not delivery_requires_email(config.delivery_mode)
    emit_progress(progress_callback, "Starting search job...", 5)
    now_utc = datetime.now(timezone.utc)
    search_request = resolve_search_request(
        config,
        search_intent=search_intent,
        time_horizon_key=time_horizon_key,
    )
    local_send_date: date | None = None
    if respect_schedule_policy and not force_send:
        should_send_today, next_due_date = evaluate_send_cadence(config, now_utc)
        if not should_send_today:
            skipped_message = (
                f"Skipping today's send due to SEND_FREQUENCY={config.send_frequency}. "
                f"Next due date: {next_due_date:%Y-%m-%d} ({config.timezone_name})"
            )
            logging.info(skipped_message)
            emit_progress(progress_callback, "Skipped by send frequency policy.", 100)
            return skipped_message
        should_send_window, window_reason, local_send_date = should_send_now(config, now_utc)
        if not should_send_window:
            skipped_message = f"Skipping send: {window_reason}"
            logging.info(skipped_message)
            emit_progress(progress_callback, "Skipped by local send-time window.", 100)
            return skipped_message
    ranked_papers, stats = collect_and_rank_papers(
        config,
        now_utc,
        search_request,
        progress_callback=progress_callback,
    )
    ranked_papers, cadence_summary, cadence_filtered_out = apply_project_cadence_filter(
        ranked_papers,
        config,
        now_utc,
    )
    stats.project_cadence_summary = cadence_summary
    stats.project_cadence_filtered_out = cadence_filtered_out
    papers_after_duplicate_filter, sent_history, duplicates_filtered = filter_already_sent_papers(
        ranked_papers,
        now_utc,
        config.sent_history_days,
    )
    papers = papers_after_duplicate_filter[: max(1, config.max_papers)]
    stats.duplicates_filtered = duplicates_filtered
    stats.final_selected = len(papers)
    since_utc = now_utc - timedelta(hours=max(1, stats.window_used_hours or search_request.time_horizon_hours))
    emit_progress(progress_callback, "Composing email body...", 95)
    subject = (
        f"[Paper Morning] {search_request.intent_label} | "
        f"{len(papers)} papers ({now_utc.astimezone(config.timezone):%Y-%m-%d})"
    )
    html_body = compose_email_html(
        papers,
        now_utc,
        since_utc,
        config.timezone_name,
        output_language=config.output_language,
        stats=stats,
    )
    text_body = compose_email_text(
        papers,
        now_utc,
        since_utc,
        config.timezone_name,
        output_language=config.output_language,
        stats=stats,
    )
    preview_payload = {
        "subject": subject,
        "generated_at_utc": now_utc.isoformat(),
        "timezone": config.timezone_name,
        "delivery_mode": config.delivery_mode,
        "send_frequency": config.send_frequency,
        "output_language": config.output_language,
        "content_kind": "search_result",
        "search_intent": search_request.intent,
        "search_intent_label": search_request.intent_label,
        "requested_time_horizon_key": search_request.time_horizon_key,
        "requested_time_horizon_label": search_request.time_horizon_label,
        "window_used_hours": stats.window_used_hours,
        "window_used_label": stats.window_used_label,
        "query_plan_label": stats.query_plan_label,
        "notice": stats.search_notice,
        "paper_count": len(papers),
        "papers": [
            {
                "paper_id": paper.paper_id,
                "title": paper.title,
                "source": paper.source,
                "score": paper.score,
                "url": paper.url,
                "topic": paper.topic,
                "project_name": paper.project_name,
                "relevance_mode": paper.relevance_mode,
                "relevance_threshold": paper.relevance_threshold,
                "published_at_utc": paper.published_at_utc.isoformat() if paper.published_at_utc else "",
                "authors": paper.authors,
                "summary_relevance": paper.llm_relevance_text,
                "summary_core": paper.llm_core_point_text,
                "summary_usefulness": paper.llm_usefulness_text,
                "summary_evidence_spans": paper.llm_evidence_spans,
            }
            for paper in papers
        ],
        "diagnostics": build_diagnostics_lines(stats),
        "text_preview": text_body,
        "html_preview": html_body,
    }

    if preview_only_mode:
        if dry_run:
            logging.info("Dry run enabled. Skipping email sending.")
        else:
            logging.info(
                "Delivery mode %s uses local inbox preview. Skipping email sending.",
                config.delivery_mode,
            )
        preview_path = save_preview_payload(preview_payload)
        logging.info("Preview payload saved: %s", preview_path)
        if print_dry_run_output:
            output_encoding = sys.stdout.encoding or "utf-8"
            safe_text = text_body.encode(output_encoding, errors="replace").decode(
                output_encoding, errors="replace"
            )
            print(safe_text)
        emit_progress(progress_callback, "Preview saved to local inbox.", 100)
        return text_body

    emit_progress(progress_callback, "Sending email...", 98)
    send_email(config, subject, html_body, text_body)
    for paper in papers:
        sent_history[paper.paper_id] = now_utc.isoformat()
    save_sent_history(get_sent_history_path(), sent_history)
    if not force_send and local_send_date is not None:
        save_scheduled_send_lock(
            get_scheduled_send_lock_path(),
            local_send_date.isoformat(),
            now_utc,
            config.timezone_name,
        )
    logging.info("Email sent to %s", config.recipient_email or config.gmail_address)
    emit_progress(progress_callback, "Email sent.", 100)
    return text_body


def read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logging.warning("Invalid integer for %s=%r. Using default %d.", name, raw, default)
        return default


def read_float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logging.warning("Invalid float for %s=%r. Using default %.2f.", name, raw, default)
        return default


def normalize_relevance_score(raw_score: float, env_name: str, default: float) -> float:
    score = raw_score
    if 0.0 < score <= 1.0:
        converted = score * 10.0
        logging.warning(
            "%s=%.3f looks like a 0-1 scale value. Converting to %.1f (0-10 scale).",
            env_name,
            score,
            converted,
        )
        score = converted
    if score < 0:
        logging.warning("%s=%.3f is below 0. Using default %.1f.", env_name, score, default)
        return default
    if score > 10:
        logging.warning("%s=%.3f is above 10. Capping to 10.0.", env_name, score)
        score = 10.0
    return score


def normalize_send_frequency(raw: str) -> Tuple[str, int]:
    value = clean_text(raw).lower()
    mapping = {
        "daily": ("daily", 1),
        "1": ("daily", 1),
        "1d": ("daily", 1),
        "every_3_days": ("every_3_days", 3),
        "3": ("every_3_days", 3),
        "3d": ("every_3_days", 3),
        "weekly": ("weekly", 7),
        "7": ("weekly", 7),
        "7d": ("weekly", 7),
    }
    if value in mapping:
        return mapping[value]
    if value:
        logging.warning("Invalid SEND_FREQUENCY=%r. Using daily.", raw)
    return "daily", 1


def parse_anchor_date(value: str) -> datetime.date:
    raw = clean_text(value)
    if not raw:
        return datetime(2026, 1, 1).date()
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        logging.warning("Invalid SEND_ANCHOR_DATE=%r. Using 2026-01-01.", value)
        return datetime(2026, 1, 1).date()


def scale_llm_max_candidates(base_candidates: int, send_interval_days: int) -> int:
    safe_base = max(1, min(80, base_candidates))
    if send_interval_days <= 1:
        return safe_base
    scaled = int(round(safe_base * (float(send_interval_days) ** 0.35)))
    return max(safe_base, min(80, scaled))


def normalize_output_language(raw: str) -> str:
    value = clean_text(raw).lower()
    if not value:
        return "en"
    # Allow simple language tags: en, en-us, ko, ja, es, fr, etc.
    if re.fullmatch(r"[a-z]{2,8}(-[a-z0-9]{2,8})*", value):
        return value
    logging.warning("Invalid OUTPUT_LANGUAGE=%r. Using en.", raw)
    return "en"


def output_language_display_name(code: str) -> str:
    names = {
        "en": "English",
        "ko": "Korean",
        "ja": "Japanese",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "zh": "Chinese",
        "zh-cn": "Chinese (Simplified)",
        "zh-tw": "Chinese (Traditional)",
    }
    normalized = normalize_output_language(code)
    return names.get(normalized, normalized)


def email_ui_labels(output_language: str) -> Dict[str, str]:
    language = normalize_output_language(output_language).split("-")[0]
    labels_by_lang: Dict[str, Dict[str, str]] = {
        "en": {
            "why": "Why this matches your work",
            "key": "Key finding",
            "how": "How you can use this",
            "abstract": "Abstract preview",
            "topic": "Topic",
            "project": "Project",
            "mode": "Mode",
            "fallback_relevance": "No LLM relevance reason generated.",
            "fallback_core": "No core-point summary generated.",
            "fallback_useful": "No usefulness summary generated.",
            "fallback_abstract": "No abstract available.",
        },
        "ko": {
            "why": "왜 이 논문이 내 연구와 맞는가",
            "key": "핵심 포인트",
            "how": "활용 방법",
            "abstract": "초록 미리보기",
            "topic": "주제",
            "project": "프로젝트",
            "mode": "모드",
            "fallback_relevance": "LLM 관련성 설명이 생성되지 않았습니다.",
            "fallback_core": "핵심 요약이 생성되지 않았습니다.",
            "fallback_useful": "활용성 설명이 생성되지 않았습니다.",
            "fallback_abstract": "초록 정보가 없습니다.",
        },
        "ja": {
            "why": "研究との関連性",
            "key": "主要な発見",
            "how": "活用方法",
            "abstract": "要旨プレビュー",
            "topic": "トピック",
            "project": "プロジェクト",
            "mode": "モード",
            "fallback_relevance": "LLMによる関連性説明が生成されませんでした。",
            "fallback_core": "コア要約が生成されませんでした。",
            "fallback_useful": "活用性の説明が生成されませんでした。",
            "fallback_abstract": "要旨がありません。",
        },
        "es": {
            "why": "Por qué coincide con tu trabajo",
            "key": "Hallazgo clave",
            "how": "Cómo puedes usarlo",
            "abstract": "Vista previa del resumen",
            "topic": "Tema",
            "project": "Proyecto",
            "mode": "Modo",
            "fallback_relevance": "No se generó la razón de relevancia por LLM.",
            "fallback_core": "No se generó el resumen del punto clave.",
            "fallback_useful": "No se generó la explicación de utilidad.",
            "fallback_abstract": "No hay resumen disponible.",
        },
        "fr": {
            "why": "Pourquoi cela correspond à vos travaux",
            "key": "Résultat clé",
            "how": "Comment l'utiliser",
            "abstract": "Aperçu du résumé",
            "topic": "Sujet",
            "project": "Projet",
            "mode": "Mode",
            "fallback_relevance": "Aucune justification de pertinence LLM générée.",
            "fallback_core": "Aucun résumé du point clé généré.",
            "fallback_useful": "Aucune explication d'utilité générée.",
            "fallback_abstract": "Aucun résumé disponible.",
        },
    }
    return labels_by_lang.get(language, labels_by_lang["en"])


def compute_internal_schedule_time(
    send_hour: int,
    send_minute: int,
    advance_minutes: int = INTERNAL_SCHEDULE_ADVANCE_MINUTES,
) -> Tuple[int, int]:
    """Return internal trigger time by advancing scheduled send time earlier."""
    total_minutes = ((send_hour * 60) + send_minute - max(0, advance_minutes)) % (24 * 60)
    return total_minutes // 60, total_minutes % 60


def evaluate_send_cadence(
    config: AppConfig,
    now_utc: datetime,
) -> Tuple[bool, datetime.date]:
    now_local_date = now_utc.astimezone(config.timezone).date()
    if config.send_interval_days <= 1:
        return True, now_local_date

    anchor_date = parse_anchor_date(config.send_anchor_date)
    delta_days = (now_local_date - anchor_date).days
    if delta_days < 0:
        return False, anchor_date

    remainder = delta_days % config.send_interval_days
    if remainder == 0:
        return True, now_local_date
    next_due = now_local_date + timedelta(days=(config.send_interval_days - remainder))
    return False, next_due


def evaluate_project_cadence(
    project: ResearchProject,
    now_utc: datetime,
    timezone_obj: ZoneInfo,
    anchor_date_value: str,
) -> Tuple[bool, datetime.date]:
    now_local_date = now_utc.astimezone(timezone_obj).date()
    if project.send_interval_days <= 1:
        return True, now_local_date
    anchor_date = parse_anchor_date(anchor_date_value)
    delta_days = (now_local_date - anchor_date).days
    if delta_days < 0:
        return False, anchor_date
    remainder = delta_days % project.send_interval_days
    if remainder == 0:
        return True, now_local_date
    next_due = now_local_date + timedelta(days=(project.send_interval_days - remainder))
    return False, next_due


def apply_project_cadence_filter(
    papers: List[Paper],
    config: AppConfig,
    now_utc: datetime,
) -> Tuple[List[Paper], List[str], int]:
    if not papers or not config.research_projects:
        return papers, [], 0

    due_project_names: Dict[str, str] = {}
    all_project_names: Dict[str, str] = {}
    deferred_labels: List[str] = []
    for project in config.research_projects:
        is_due, next_due = evaluate_project_cadence(
            project,
            now_utc,
            config.timezone,
            config.send_anchor_date,
        )
        key = clean_text(project.name).lower()
        if not key:
            continue
        all_project_names[key] = project.name
        if is_due:
            due_project_names[key] = project.name
        else:
            deferred_labels.append(f"{project.name}({project.send_frequency}->{next_due:%Y-%m-%d})")

    if not due_project_names:
        summary = ["No project cadence is due today."]
        if deferred_labels:
            summary.append("Deferred projects: " + ", ".join(deferred_labels))
        return [], summary, len(papers)

    filtered: List[Paper] = []
    filtered_out = 0
    unmatched_topic_labels = 0
    for paper in papers:
        topic_key = clean_text(paper.project_name or paper.topic).lower()
        if not topic_key:
            filtered.append(paper)
            continue
        if topic_key not in all_project_names:
            # Topic labels may be custom and not 1:1 with project names.
            # Only apply cadence filtering when project mapping is explicit.
            unmatched_topic_labels += 1
            filtered.append(paper)
            continue
        if topic_key in due_project_names:
            filtered.append(paper)
            continue
        filtered_out += 1

    summary = [f"Due projects today: {', '.join(due_project_names.values())}"]
    if deferred_labels:
        summary.append("Deferred projects: " + ", ".join(deferred_labels))
    if unmatched_topic_labels > 0:
        summary.append(
            "Cadence bypassed for papers without explicit project mapping: "
            f"{unmatched_topic_labels}"
        )
    return filtered, summary, filtered_out


def load_config(require_email_credentials: bool) -> AppConfig:
    # Reload .env on each call so web UI saves are applied immediately.
    env_path, _ = bootstrap_runtime_files()
    load_dotenv(dotenv_path=env_path, override=True)

    oauth_bundle = load_google_oauth_bundle_defaults()
    gmail_address = os.getenv("GMAIL_ADDRESS", "").strip()
    gmail_app_password = re.sub(
        r"\s+",
        "",
        resolve_secret_value("GMAIL_APP_PASSWORD", os.getenv("GMAIL_APP_PASSWORD", "")),
    )
    recipient_email = os.getenv("RECIPIENT_EMAIL", "").strip()
    delivery_mode = normalize_delivery_mode(os.getenv("DELIVERY_MODE", DELIVERY_MODE_LOCAL_INBOX))
    auto_open_digest_window = os.getenv("AUTO_OPEN_DIGEST_WINDOW", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    enable_google_oauth = os.getenv("ENABLE_GOOGLE_OAUTH", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    google_oauth_use_for_gmail = os.getenv("GOOGLE_OAUTH_USE_FOR_GMAIL", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    google_oauth_client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip() or oauth_bundle.get("client_id", "")
    google_oauth_client_secret = resolve_secret_value(
        "GOOGLE_OAUTH_CLIENT_SECRET",
        os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
    )
    if not google_oauth_client_secret:
        google_oauth_client_secret = oauth_bundle.get("client_secret", "")
    google_oauth_refresh_token = resolve_secret_value(
        "GOOGLE_OAUTH_REFRESH_TOKEN",
        os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN", ""),
    )
    ncbi_api_key = os.getenv("NCBI_API_KEY", "").strip()
    projects_config_file = os.getenv("PROJECTS_CONFIG_FILE", DEFAULT_PROJECTS_CONFIG_FILE).strip() or DEFAULT_PROJECTS_CONFIG_FILE
    user_topics_file = os.getenv("USER_TOPICS_FILE", "user_topics.json").strip() or "user_topics.json"
    user_topics_path = resolve_topics_file_path(user_topics_file, env_path=env_path)
    projects_config_path = resolve_topics_file_path(projects_config_file, env_path=env_path)
    enable_semantic_scholar = os.getenv("ENABLE_SEMANTIC_SCHOLAR", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    semantic_scholar_api_key = resolve_secret_value(
        "SEMANTIC_SCHOLAR_API_KEY",
        os.getenv("SEMANTIC_SCHOLAR_API_KEY", ""),
    )
    semantic_scholar_max_results_per_query = max(
        1,
        read_int_env("SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY", 20),
    )
    enable_google_scholar = os.getenv("ENABLE_GOOGLE_SCHOLAR", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    google_scholar_api_key = resolve_secret_value(
        "GOOGLE_SCHOLAR_API_KEY",
        os.getenv("GOOGLE_SCHOLAR_API_KEY", ""),
    )
    google_scholar_max_results_per_query = max(
        1,
        min(
            GOOGLE_SCHOLAR_MAX_RESULTS_HARD_LIMIT,
            read_int_env("GOOGLE_SCHOLAR_MAX_RESULTS_PER_QUERY", 10),
        ),
    )

    enable_llm_agent = os.getenv("ENABLE_LLM_AGENT", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    gemini_api_key = resolve_secret_value("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
    enable_gemini_advanced_reasoning = os.getenv(
        "ENABLE_GEMINI_ADVANCED_REASONING",
        "true",
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash").strip() or "gemini-3.1-flash"
    if enable_gemini_advanced_reasoning:
        gemini_model = "gemini-3.1-pro"
    enable_openai_compat_fallback = os.getenv("ENABLE_OPENAI_COMPAT_FALLBACK", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    openai_compat_api_key = resolve_secret_value(
        "OPENAI_COMPAT_API_KEY",
        os.getenv("OPENAI_COMPAT_API_KEY", ""),
    )
    openai_compat_model = os.getenv("OPENAI_COMPAT_MODEL", "").strip()
    openai_compat_api_base = (
        os.getenv("OPENAI_COMPAT_API_BASE", OPENAI_COMPAT_API_BASE_DEFAULT).strip()
        or OPENAI_COMPAT_API_BASE_DEFAULT
    )
    cerebras_api_key = resolve_secret_value("CEREBRAS_API_KEY", os.getenv("CEREBRAS_API_KEY", ""))
    cerebras_model = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b").strip() or "gpt-oss-120b"
    cerebras_api_base = (
        os.getenv("CEREBRAS_API_BASE", CEREBRAS_API_BASE_DEFAULT).strip() or CEREBRAS_API_BASE_DEFAULT
    )
    enable_cerebras_fallback = os.getenv("ENABLE_CEREBRAS_FALLBACK", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    send_frequency, send_interval_days = normalize_send_frequency(os.getenv("SEND_FREQUENCY", "daily"))
    send_anchor_date = os.getenv("SEND_ANCHOR_DATE", "2026-01-01").strip() or "2026-01-01"
    output_language = normalize_output_language(os.getenv("OUTPUT_LANGUAGE", "en"))
    gemini_max_papers = max(1, read_int_env("GEMINI_MAX_PAPERS", 5))
    llm_relevance_threshold = normalize_relevance_score(
        read_float_env("LLM_RELEVANCE_THRESHOLD", 6.0),
        "LLM_RELEVANCE_THRESHOLD",
        6.0,
    )
    llm_max_candidates_base = min(80, max(1, read_int_env("LLM_MAX_CANDIDATES", 30)))
    llm_max_candidates = scale_llm_max_candidates(llm_max_candidates_base, send_interval_days)
    max_search_queries_per_source = max(1, read_int_env("MAX_SEARCH_QUERIES_PER_SOURCE", 4))
    sent_history_days = max(1, read_int_env("SENT_HISTORY_DAYS", 14))

    timezone_name = os.getenv("TIMEZONE", "UTC").strip() or "UTC"
    send_hour = read_int_env("SEND_HOUR", 9)
    send_minute = read_int_env("SEND_MINUTE", 0)
    send_time_window_minutes = max(1, read_int_env("SEND_TIME_WINDOW_MINUTES", 15))
    search_intent_default = normalize_search_intent(
        os.getenv("SEARCH_INTENT_DEFAULT", SEARCH_INTENT_DEFAULT)
    )
    search_time_horizon_default = normalize_time_horizon_key(
        os.getenv("SEARCH_TIME_HORIZON_DEFAULT", SEARCH_TIME_HORIZON_DEFAULT),
        search_intent_default,
    )
    max_papers = max(1, read_int_env("MAX_PAPERS", 5))
    lookback_hours = max(1, read_int_env("LOOKBACK_HOURS", 24))
    min_lookback_hours = send_interval_days * 24
    if lookback_hours < min_lookback_hours:
        logging.info(
            "LOOKBACK_HOURS=%d expanded to %d due to SEND_FREQUENCY=%s",
            lookback_hours,
            min_lookback_hours,
            send_frequency,
        )
        lookback_hours = min_lookback_hours
    min_relevance_score = normalize_relevance_score(
        read_float_env("MIN_RELEVANCE_SCORE", 6.0),
        "MIN_RELEVANCE_SCORE",
        6.0,
    )
    arxiv_max_results_per_query = max(1, read_int_env("ARXIV_MAX_RESULTS_PER_QUERY", 25))
    pubmed_max_ids_per_query = max(1, read_int_env("PUBMED_MAX_IDS_PER_QUERY", 25))

    if not user_topics_path.exists():
        template_path = find_resource_file(
            ["user_topics.template.json", "config/user_topics.template.json"],
            _legacy_search_dirs(),
        )
        if template_path and template_path.exists():
            _copy_if_needed(template_path, user_topics_path)

    (
        topic_profiles,
        research_projects,
        arxiv_queries,
        pubmed_queries,
        semantic_queries,
        google_scholar_queries,
    ) = load_topic_configuration(str(user_topics_path))
    if not research_projects:
        file_projects, project_errors = read_projects_config(projects_config_path)
        if project_errors:
            logging.info("Projects config fallback skipped: %s", "; ".join(project_errors))
        else:
            for project in file_projects:
                name = clean_text(str(project.get("name", "")))
                context = clean_text(str(project.get("context", "")))
                project_send_frequency, project_interval_days = normalize_send_frequency(
                    str(project.get("send_frequency", "daily"))
                )
                keywords_raw = project.get("keywords", [])
                if isinstance(keywords_raw, list):
                    keywords = [clean_text(str(item)) for item in keywords_raw if clean_text(str(item))]
                elif isinstance(keywords_raw, str):
                    keywords = [clean_text(part) for part in keywords_raw.split(",") if clean_text(part)]
                else:
                    keywords = []
                merged_context = (
                    f"{context} | Keywords: {', '.join(keywords)}"
                    if context and keywords
                    else (context or f"Keywords: {', '.join(keywords)}")
                )
                if name and merged_context:
                    research_projects.append(
                        ResearchProject(
                            name=name,
                            context=merged_context,
                            send_frequency=project_send_frequency,
                            send_interval_days=project_interval_days,
                        )
                    )

    try:
        ZoneInfo(timezone_name)
    except Exception as exc:
        raise ValueError(f"Invalid TIMEZONE value: {timezone_name}") from exc

    if require_email_credentials and delivery_requires_email(delivery_mode):
        missing = []
        if not gmail_address:
            missing.append("GMAIL_ADDRESS")
        oauth_ready = (
            enable_google_oauth
            and google_oauth_use_for_gmail
            and bool(google_oauth_client_id)
            and bool(google_oauth_client_secret)
            and bool(google_oauth_refresh_token)
        )
        if delivery_mode == DELIVERY_MODE_GMAIL_OAUTH:
            if not oauth_ready:
                missing.append("GOOGLE_OAUTH refresh setup")
        elif not gmail_app_password:
            missing.append("GMAIL_APP_PASSWORD")
        if missing:
            raise ValueError("Missing required env vars for email: " + ", ".join(missing))

    return AppConfig(
        gmail_address=gmail_address,
        gmail_app_password=gmail_app_password,
        recipient_email=recipient_email or gmail_address,
        delivery_mode=delivery_mode,
        auto_open_digest_window=auto_open_digest_window,
        enable_google_oauth=enable_google_oauth,
        google_oauth_use_for_gmail=google_oauth_use_for_gmail,
        google_oauth_client_id=google_oauth_client_id,
        google_oauth_client_secret=google_oauth_client_secret,
        google_oauth_refresh_token=google_oauth_refresh_token,
        timezone_name=timezone_name,
        send_hour=send_hour,
        send_minute=send_minute,
        send_time_window_minutes=send_time_window_minutes,
        search_intent_default=search_intent_default,
        search_time_horizon_default=search_time_horizon_default,
        max_papers=max_papers,
        lookback_hours=lookback_hours,
        min_relevance_score=min_relevance_score,
        arxiv_max_results_per_query=arxiv_max_results_per_query,
        pubmed_max_ids_per_query=pubmed_max_ids_per_query,
        ncbi_api_key=ncbi_api_key,
        topic_profiles=topic_profiles,
        research_projects=research_projects,
        arxiv_queries=arxiv_queries,
        pubmed_queries=pubmed_queries,
        semantic_scholar_queries=semantic_queries,
        enable_semantic_scholar=enable_semantic_scholar,
        semantic_scholar_api_key=semantic_scholar_api_key,
        semantic_scholar_max_results_per_query=semantic_scholar_max_results_per_query,
        google_scholar_queries=google_scholar_queries,
        enable_google_scholar=enable_google_scholar,
        google_scholar_api_key=google_scholar_api_key,
        google_scholar_max_results_per_query=google_scholar_max_results_per_query,
        enable_llm_agent=enable_llm_agent,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        openai_compat_api_key=openai_compat_api_key,
        openai_compat_model=openai_compat_model,
        openai_compat_api_base=openai_compat_api_base,
        enable_openai_compat_fallback=enable_openai_compat_fallback,
        cerebras_api_key=cerebras_api_key,
        cerebras_model=cerebras_model,
        cerebras_api_base=cerebras_api_base,
        enable_cerebras_fallback=enable_cerebras_fallback,
        gemini_max_papers=gemini_max_papers,
        llm_relevance_threshold=llm_relevance_threshold,
        llm_max_candidates_base=llm_max_candidates_base,
        llm_max_candidates=llm_max_candidates,
        max_search_queries_per_source=max_search_queries_per_source,
        sent_history_days=sent_history_days,
        send_frequency=send_frequency,
        send_interval_days=send_interval_days,
        send_anchor_date=send_anchor_date,
        output_language=output_language,
    )


from agent_search import search_papers_for_agent


def load_agent_request_payload(path: str) -> Dict[str, Any]:
    source = clean_text(path)
    if not source:
        return {}
    if source == "-":
        raw_text = sys.stdin.read()
    else:
        raw_text = Path(source).read_text(encoding="utf-8-sig")
    if not clean_text(raw_text):
        return {}
    payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        raise ValueError("Agent request file must contain a JSON object.")
    return payload


def normalize_agent_keywords(raw: Any) -> List[str]:
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        items = raw.split(",")
    else:
        items = []
    return dedupe_list([clean_text(str(item)) for item in items if clean_text(str(item))])


def build_agent_cli_request(args: argparse.Namespace) -> Dict[str, Any]:
    payload = load_agent_request_payload(args.agent_request_file) if args.agent_request_file else {}
    if args.project_name:
        payload["project_name"] = args.project_name
    if args.research_context:
        payload["research_context"] = args.research_context
    if args.keywords:
        payload["keywords"] = normalize_agent_keywords(args.keywords)
    if args.search_intent:
        payload["search_intent"] = args.search_intent
    if args.time_horizon:
        payload["time_horizon"] = args.time_horizon
    if args.top_k is not None:
        payload["top_k"] = args.top_k
    if args.output_language:
        payload["output_language"] = args.output_language
    if args.model:
        payload["model"] = args.model
    if args.include_diagnostics:
        payload["include_diagnostics"] = True
    if "keywords" in payload:
        payload["keywords"] = normalize_agent_keywords(payload.get("keywords", []))
    return payload


def run_agent_search_cli(config: AppConfig, args: argparse.Namespace) -> int:
    payload = build_agent_cli_request(args)
    research_context = clean_text(str(payload.get("research_context", "")))
    if not research_context:
        raise ValueError("research_context is required. Provide --research-context or --agent-request-file.")

    result = search_papers_for_agent(
        config,
        project_name=clean_text(str(payload.get("project_name", ""))),
        research_context=research_context,
        keywords=normalize_agent_keywords(payload.get("keywords", [])),
        search_intent=normalize_search_intent(payload.get("search_intent", "best_match")),
        time_horizon_key=normalize_time_horizon_key(
            payload.get("time_horizon", "1y"),
            payload.get("search_intent", "best_match"),
        ),
        top_k=max(1, min(50, int(payload.get("top_k", 10) or 10))),
        output_language=clean_text(str(payload.get("output_language", ""))) or None,
        model=clean_text(str(payload.get("model", ""))) or None,
        include_diagnostics=coerce_bool(payload.get("include_diagnostics"), False),
        source_policy=payload.get("source_policy") if isinstance(payload.get("source_policy"), dict) else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty_json else None))
    return 0 if result.get("status") != "error" else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Paper Morning research-context paper search runner."
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run the search job immediately and exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not send email. Print the generated result to console.",
    )
    parser.add_argument(
        "--agent-search",
        action="store_true",
        help="Run agent-oriented JSON search and print the response to stdout.",
    )
    parser.add_argument(
        "--agent-request-file",
        type=str,
        default="",
        help="Path to a JSON request object for --agent-search. Use '-' to read from stdin.",
    )
    parser.add_argument("--project-name", type=str, default="", help="Optional project label for --agent-search.")
    parser.add_argument("--research-context", type=str, default="", help="Required context text for --agent-search.")
    parser.add_argument("--keywords", type=str, default="", help="Comma-separated keywords for --agent-search.")
    parser.add_argument(
        "--search-intent",
        type=str,
        default="",
        choices=["whats_new", "best_match", "discovery"],
        help="Search intent for --agent-search.",
    )
    parser.add_argument(
        "--time-horizon",
        type=str,
        default="",
        choices=list(TIME_HORIZON_OPTIONS.keys()),
        help="Time horizon for --agent-search.",
    )
    parser.add_argument("--top-k", type=int, default=None, help="Maximum papers to return for --agent-search.")
    parser.add_argument("--output-language", type=str, default="", help="Output language for --agent-search.")
    parser.add_argument("--model", type=str, default="", help="Optional model override for --agent-search.")
    parser.add_argument(
        "--include-diagnostics",
        action="store_true",
        help="Include diagnostics in --agent-search JSON output.",
    )
    parser.add_argument(
        "--pretty-json",
        action="store_true",
        help="Pretty-print JSON output for --agent-search.",
    )
    return parser.parse_args()


def start_scheduler(config: AppConfig, dry_run: bool) -> None:
    scheduler = BlockingScheduler(timezone=config.timezone_name)
    internal_hour, internal_minute = compute_internal_schedule_time(
        config.send_hour,
        config.send_minute,
    )
    scheduler.add_job(
        lambda: run_digest(config, dry_run=dry_run, respect_schedule_policy=True),
        "cron",
        hour=internal_hour,
        minute=internal_minute,
        id="daily-paper-digest",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )
    logging.info(
        "Scheduler started. User time %02d:%02d -> internal trigger %02d:%02d (%s), SEND_FREQUENCY=%s.",
        config.send_hour,
        config.send_minute,
        internal_hour,
        internal_minute,
        config.timezone_name,
        config.send_frequency,
    )
    scheduler.start()


def main() -> int:
    setup_logging()
    args = parse_args()
    env_path, topics_path = bootstrap_runtime_files()
    logging.info("Using env file: %s", env_path)
    logging.info("Using topics file: %s", topics_path)

    if args.agent_search and args.run_once:
        logging.error("--agent-search cannot be combined with --run-once.")
        return 2

    require_email_credentials = not args.dry_run and not args.agent_search
    try:
        config = load_config(require_email_credentials=require_email_credentials)
    except Exception as exc:
        logging.error("Configuration error: %s", exc)
        return 1

    try:
        if args.agent_search:
            return run_agent_search_cli(config, args)
        if args.run_once:
            run_digest(config, dry_run=args.dry_run)
        else:
            start_scheduler(config, dry_run=args.dry_run)
    except KeyboardInterrupt:
        logging.info("Stopped by user.")
    except Exception:
        logging.exception("Unexpected error while running digest app.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
