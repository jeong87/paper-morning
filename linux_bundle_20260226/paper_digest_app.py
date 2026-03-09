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
from datetime import datetime, timedelta, timezone
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


@dataclass
class TopicProfile:
    name: str
    keywords: Dict[str, float]


@dataclass
class ResearchProject:
    name: str
    context: str


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
    matched_keywords: List[str] = None
    llm_relevance_ko: str = ""
    llm_core_point_ko: str = ""
    llm_usefulness_ko: str = ""


@dataclass
class AppConfig:
    gmail_address: str
    gmail_app_password: str
    recipient_email: str
    enable_google_oauth: bool
    google_oauth_use_for_gmail: bool
    google_oauth_client_id: str
    google_oauth_client_secret: str
    google_oauth_refresh_token: str
    timezone_name: str
    send_hour: int
    send_minute: int
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
    cerebras_api_key: str
    cerebras_model: str
    cerebras_api_base: str
    enable_cerebras_fallback: bool
    gemini_max_papers: int
    llm_relevance_threshold: float
    llm_batch_size: int
    llm_max_candidates_base: int
    llm_max_candidates: int
    max_search_queries_per_source: int
    sent_history_days: int
    send_frequency: str
    send_interval_days: int
    send_anchor_date: str

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
    estimated_llm_calls_upper_bound: int = 0
    duplicates_filtered: int = 0
    final_selected: int = 0
    query_strategy: str = "saved-topics"
    send_frequency: str = "daily"
    lookback_hours: int = 24
    llm_max_candidates_base: int = 0
    llm_max_candidates_effective: int = 0
    zero_candidate_recovery_steps: List[str] = field(default_factory=list)


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
    candidates = [Path.cwd(), get_runtime_base_dir()]
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


def get_sent_history_path() -> Path:
    return (get_default_data_dir() / "sent_ids.json").resolve()


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
        env_example = _find_legacy_file(".env.example", search_dirs)
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
        template = _find_legacy_file("user_topics.template.json", search_dirs)
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
        if not name or not keyword_weights:
            continue

        profiles.append(TopicProfile(name=name, keywords=keyword_weights))

    for project in projects_payload:
        if not isinstance(project, dict):
            continue
        name = clean_text(str(project.get("name", "")))
        context = clean_text(str(project.get("context", "")))
        goals = normalize_string_list(project.get("goals"))
        methods = normalize_string_list(project.get("methods"))
        stack = normalize_string_list(project.get("stack"))
        merged = " | ".join(part for part in [context, "; ".join(goals), "; ".join(methods), "; ".join(stack)] if part)
        if name and merged:
            projects.append(ResearchProject(name=name, context=merged))

    if not projects and profiles:
        for profile in profiles:
            projects.append(
                ResearchProject(
                    name=profile.name,
                    context=f"Keywords: {', '.join(profile.keywords.keys())}",
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
                "before running digest."
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


def score_paper(
    title: str,
    abstract: str,
    topic_profiles: List[TopicProfile],
) -> Tuple[float, str, List[str]]:
    combined = f"{title} {abstract}".lower()
    best_topic = ""
    best_score = 0.0
    best_keywords: List[str] = []
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
    return best_score, best_topic, best_keywords

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
            # LLM이 JSON 문자열 내부의 역슬래시를 잘못 이스케이프하는 경우를 복구한다.
            repaired = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", candidate)
            if repaired != candidate:
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass
            # 일부 모델 응답은 문자열 내부 개행/제어문자를 탈출하지 않고 반환한다.
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


def chunk_list(items: List[Any], chunk_size: int) -> List[List[Any]]:
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def build_project_context_text(projects: List[ResearchProject]) -> str:
    lines = []
    for idx, project in enumerate(projects, start=1):
        lines.append(f"{idx}. {project.name}: {project.context}")
    return "\n".join(lines)


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


def can_use_cerebras_fallback(config: AppConfig) -> bool:
    return bool(config.cerebras_api_key) and config.enable_cerebras_fallback


def has_llm_provider(config: AppConfig) -> bool:
    return bool(config.gemini_api_key) or can_use_cerebras_fallback(config)


def call_llm_json(config: AppConfig, prompt: str, temperature: float = 0.2) -> Any:
    errors: List[str] = []

    if config.gemini_api_key:
        try:
            return call_gemini_json(config, prompt, temperature=temperature)
        except Exception as exc:
            safe_error = mask_sensitive_text(str(exc))
            errors.append(f"Gemini failed: {safe_error}")
            logging.warning("Gemini call failed. Trying Cerebras fallback if enabled: %s", safe_error)

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
        "No LLM provider available. Configure GEMINI_API_KEY or enable Cerebras fallback with CEREBRAS_API_KEY."
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


def fetch_arxiv_papers(config: AppConfig, since_utc: datetime, queries: List[str]) -> List[Paper]:
    papers_by_id: Dict[str, Paper] = {}
    max_results = max(1, min(config.arxiv_max_results_per_query, ARXIV_MAX_RESULTS_HARD_LIMIT))
    for idx, query in enumerate(queries):
        if idx > 0:
            time.sleep(ARXIV_QUERY_INTERVAL_SECONDS)
        params = {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
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


def fetch_pubmed_ids(query: str, config: AppConfig) -> List[str]:
    normalized_query = re.sub(r"\*{2,}", "", clean_text(query))
    if not normalized_query:
        return []
    params = {
        "db": "pubmed",
        "term": normalized_query,
        "retmax": config.pubmed_max_ids_per_query,
        "sort": "pub date",
        "reldate": max(1, int(config.lookback_hours / 24) + 1),
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


def fetch_pubmed_papers(config: AppConfig, since_utc: datetime, queries: List[str]) -> List[Paper]:
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
            ids = fetch_pubmed_ids(query, config)
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
) -> List[Paper]:
    papers_by_id: Dict[str, Paper] = {}
    max_results = max(
        1,
        min(config.semantic_scholar_max_results_per_query, SEMANTIC_SCHOLAR_MAX_RESULTS_HARD_LIMIT),
    )
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
) -> List[Paper]:
    if not config.google_scholar_api_key:
        logging.warning("Skipping Google Scholar search: GOOGLE_SCHOLAR_API_KEY is not set.")
        return []

    papers_by_id: Dict[str, Paper] = {}
    max_results = max(
        1,
        min(config.google_scholar_max_results_per_query, GOOGLE_SCHOLAR_MAX_RESULTS_HARD_LIMIT),
    )

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
        score, topic, matched = score_paper(paper.title, paper.abstract, config.topic_profiles)
        paper.score = score
        paper.topic = topic
        paper.matched_keywords = matched
        scored.append(paper)

    scored.sort(key=lambda item: (item.score, item.published_at_utc), reverse=True)
    with_keywords = [item for item in scored if item.score > 0]
    candidates = with_keywords or scored
    return candidates[: max(1, config.llm_max_candidates)]


def annotate_papers_with_llm(
    papers: List[Paper], config: AppConfig
) -> Tuple[List[Paper], Dict[str, Any]]:
    if not papers:
        return [], {
            "mode": "llm",
            "threshold": config.llm_relevance_threshold,
            "scoring_candidates": 0,
            "scored_count": 0,
            "pass_count": 0,
            "score_buckets": {},
        }

    project_context = build_project_context_text(config.research_projects)
    by_id = {paper.paper_id: paper for paper in papers}
    min_score = config.llm_relevance_threshold

    for batch in chunk_list(papers, max(1, config.llm_batch_size)):
        payload_items = []
        for paper in batch:
            payload_items.append(
                {
                    "id": paper.paper_id,
                    "title": paper.title,
                    "abstract": clean_text(paper.abstract)[:1500],
                    "source": paper.source,
                    "published_at_utc": paper.published_at_utc.isoformat(),
                }
            )

        prompt = (
            "You are a personalized research assistant for a medical-AI PhD researcher.\n"
            "Project context:\n"
            f"{project_context}\n\n"
            "For each paper, do the following:\n"
            "1) score relevance from 1 to 10\n"
            "2) write one short Korean relevance reason\n"
            "3) write Korean core-point summary in 3-4 short lines\n"
            "4) write Korean usefulness explanation in 3-4 short lines\n\n"
            "Return ONLY JSON object:\n"
            "{\n"
            '  "items": [\n'
            "    {\n"
            '      "id": "...",\n'
            '      "relevance_score": 1,\n'
            '      "relevance_reason_ko": "...",\n'
            '      "core_point_ko": "...",\n'
            '      "usefulness_ko": "..."\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "Rules:\n"
            "- score must be integer 1..10\n"
            f"- score >= {min_score:.1f} means pass\n"
            "- do not hallucinate beyond title and abstract\n"
            "- be strict to reduce noisy papers\n\n"
            f"Papers JSON:\n{json.dumps(payload_items, ensure_ascii=False)}"
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
            paper.score = max(0.0, min(10.0, score))
            paper.llm_relevance_ko = clean_text(str(item.get("relevance_reason_ko", "")))
            paper.llm_core_point_ko = clean_text(str(item.get("core_point_ko", "")))
            paper.llm_usefulness_ko = clean_text(str(item.get("usefulness_ko", "")))
            paper.topic = "LLM-Relevance"

    selected = [paper for paper in papers if paper.score >= min_score]
    selected.sort(key=lambda item: (item.score, item.published_at_utc), reverse=True)
    scored_values = [paper.score for paper in papers]
    metadata = {
        "mode": "llm",
        "threshold": min_score,
        "scoring_candidates": len(papers),
        "scored_count": len([value for value in scored_values if value > 0]),
        "pass_count": len(selected),
        "score_buckets": build_score_buckets(scored_values),
    }
    return selected, metadata


def rank_relevant_papers_keyword(
    papers: List[Paper], config: AppConfig
) -> Tuple[List[Paper], Dict[str, Any]]:
    scored: List[Paper] = []
    ranked: List[Paper] = []
    for paper in papers:
        score, topic, matched = score_paper(paper.title, paper.abstract, config.topic_profiles)
        paper.score = score
        paper.topic = topic
        paper.matched_keywords = matched
        scored.append(paper)
        if score < config.min_relevance_score:
            continue
        ranked.append(paper)
    ranked.sort(key=lambda item: (item.score, item.published_at_utc), reverse=True)
    metadata = {
        "mode": "keyword",
        "threshold": config.min_relevance_score,
        "scoring_candidates": len(scored),
        "scored_count": len(scored),
        "pass_count": len(ranked),
        "score_buckets": {},
    }
    return ranked, metadata


def rank_relevant_papers(papers: List[Paper], config: AppConfig) -> Tuple[List[Paper], Dict[str, Any]]:
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
            },
        )
    if config.enable_llm_agent and has_llm_provider(config):
        try:
            candidates = prefilter_candidates_for_llm(papers, config)
            llm_ranked, llm_meta = annotate_papers_with_llm(candidates, config)
            if llm_ranked:
                return llm_ranked, llm_meta
            logging.warning("LLM ranking returned no papers. Falling back to keyword ranking.")
            keyword_ranked, keyword_meta = rank_relevant_papers_keyword(papers, config)
            keyword_meta["llm_fallback_reason"] = "llm_returned_no_pass"
            keyword_meta["llm_threshold"] = config.llm_relevance_threshold
            keyword_meta["llm_score_buckets"] = llm_meta.get("score_buckets", {})
            keyword_meta["llm_scoring_candidates"] = llm_meta.get("scoring_candidates", len(candidates))
            keyword_meta["llm_scored_count"] = llm_meta.get("scored_count", 0)
            keyword_meta["llm_pass_count"] = llm_meta.get("pass_count", 0)
            return keyword_ranked, keyword_meta
        except Exception as exc:
            safe_error = mask_sensitive_text(str(exc))
            logging.warning("LLM ranking failed. Falling back to keyword ranking: %s", safe_error)
            keyword_ranked, keyword_meta = rank_relevant_papers_keyword(papers, config)
            keyword_meta["llm_fallback_reason"] = f"llm_error: {safe_error}"
            return keyword_ranked, keyword_meta
    return rank_relevant_papers_keyword(papers, config)

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
        f"9-10점 {buckets.get('9-10', 0)}개, "
        f"7-8점 {buckets.get('7-8', 0)}개, "
        f"5-6점 {buckets.get('5-6', 0)}개, "
        f"1-4점 {buckets.get('1-4', 0)}개, "
        f"0점 {buckets.get('0', 0)}개"
    )


def build_diagnostics_lines(stats: DigestStats) -> List[str]:
    lines = [
        (
            f"수집 후보: arXiv {stats.arxiv_candidates}건, PubMed {stats.pubmed_candidates}건, "
            f"SemanticScholar {stats.semantic_scholar_candidates}건, "
            f"GoogleScholar {stats.google_scholar_candidates}건, "
            f"총 {stats.total_candidates}건"
        ),
        f"시간 필터 통과: {stats.post_time_filter_candidates}건",
        f"검색 쿼리 전략: {stats.query_strategy}",
        f"선별 모드: {stats.ranking_mode}",
        f"발송 주기: {stats.send_frequency}",
        f"탐색 기간: 최근 {stats.lookback_hours}시간",
    ]
    if stats.ranking_threshold > 0:
        lines.append(f"관련성 임계값: {stats.ranking_threshold:.1f}")
    if stats.scoring_candidates > 0:
        lines.append(f"점수 평가 대상: {stats.scoring_candidates}건")
    if stats.scored_count > 0:
        lines.append(f"점수 계산 완료: {stats.scored_count}건")
    if stats.score_buckets:
        lines.append("점수 분포: " + format_score_buckets_text(stats.score_buckets))
    lines.append(f"임계값 통과: {stats.pass_count}건")
    if stats.llm_fallback_reason:
        lines.append(f"LLM 폴백 정보: {stats.llm_fallback_reason}")
    if stats.zero_candidate_recovery_steps:
        lines.append("0건 복구 절차:")
        for step in stats.zero_candidate_recovery_steps:
            lines.append(f" - {step}")
    if stats.duplicates_filtered > 0:
        lines.append(f"중복 발송 제외: {stats.duplicates_filtered}건")
    if stats.estimated_llm_calls_upper_bound > 0:
        lines.append(f"예상 최대 LLM 호출(1회 실행): {stats.estimated_llm_calls_upper_bound}회")
    if stats.llm_max_candidates_effective > 0:
        lines.append(
            f"LLM 후보 상한: 기본 {stats.llm_max_candidates_base} -> 적용 {stats.llm_max_candidates_effective}"
        )
    lines.append(f"최종 포함: {stats.final_selected}건")
    return lines


def compose_email_html(
    papers: List[Paper],
    now_utc: datetime,
    since_utc: datetime,
    timezone_name: str,
    stats: DigestStats | None = None,
) -> str:
    now_local = format_local_time(now_utc, timezone_name)
    since_local = format_local_time(since_utc, timezone_name)

    diagnostics_html = ""
    if stats:
        diagnostics_items = "".join(
            f"<li>{html.escape(line)}</li>" for line in build_diagnostics_lines(stats)
        )
        diagnostics_html = f"""
        <div style="margin-top:14px;padding:12px;border:1px solid #e5e7eb;border-radius:8px;background:#fafafa;">
          <div style="font-size:14px;font-weight:600;margin-bottom:6px;">Selection diagnostics</div>
          <ul style="margin:0;padding-left:18px;font-size:13px;color:#374151;line-height:1.6;">
            {diagnostics_items}
          </ul>
        </div>
        """

    if not papers:
        return f"""
        <html>
          <body>
            <h2>Daily Paper Digest</h2>
            <p><b>Window:</b> {html.escape(since_local)} ~ {html.escape(now_local)}</p>
            <p>No highly relevant papers were found in the last {int((now_utc - since_utc).total_seconds() / 3600)} hours.</p>
            {diagnostics_html}
          </body>
        </html>
        """

    sections = []
    for idx, paper in enumerate(papers, start=1):
        snippet = clean_text(paper.abstract)[:700]
        if len(clean_text(paper.abstract)) > 700:
            snippet += "..."
        keywords = ", ".join((paper.matched_keywords or [])[:10]) or "N/A"

        llm_block = ""
        if paper.llm_core_point_ko or paper.llm_usefulness_ko or paper.llm_relevance_ko:
            llm_block = (
                f'<div style="font-size:13px;color:#0b5d1e;margin-top:6px;"><b>LLM relevance reason:</b> {html.escape(paper.llm_relevance_ko or "N/A")}</div>'
                f'<div style="font-size:13px;color:#0b5d1e;margin-top:4px;"><b>Core point (KR):</b><br/>{escape_multiline(paper.llm_core_point_ko or "N/A")}</div>'
                f'<div style="font-size:13px;color:#0b5d1e;margin-top:4px;"><b>Why useful for your work (KR):</b><br/>{escape_multiline(paper.llm_usefulness_ko or "N/A")}</div>'
            )

        sections.append(
            f"""
        <div style="margin-bottom:20px;padding:14px;border:1px solid #d9d9d9;border-radius:8px;">
          <div style="font-size:12px;color:#666;">#{idx} | Score {paper.score:.1f}/10 | {html.escape(paper.source)} | {html.escape(paper.topic or "N/A")}</div>
          <div style="font-size:17px;margin-top:6px;"><a href="{html.escape(paper.url)}">{html.escape(paper.title)}</a></div>
          <div style="font-size:13px;color:#444;margin-top:5px;"><b>Published:</b> {html.escape(format_local_time(paper.published_at_utc, timezone_name))}</div>
          <div style="font-size:13px;color:#444;"><b>Authors:</b> {html.escape(format_authors(paper.authors))}</div>
          <div style="font-size:13px;color:#444;"><b>Matched keywords:</b> {html.escape(keywords)}</div>
          {llm_block}
          <div style="font-size:13px;color:#333;margin-top:8px;"><b>Abstract snippet:</b> {html.escape(snippet or "No abstract available.")}</div>
        </div>
        """
        )

    return f"""
    <html>
      <body style="font-family:Arial,sans-serif;max-width:1000px;margin:0 auto;">
        <h2>Daily Paper Digest</h2>
        <p><b>Window:</b> {html.escape(since_local)} ~ {html.escape(now_local)}</p>
        <p><b>Total sent:</b> {len(papers)}</p>
        {''.join(sections)}
        {diagnostics_html}
      </body>
    </html>
    """


def compose_email_text(
    papers: List[Paper],
    now_utc: datetime,
    since_utc: datetime,
    timezone_name: str,
    stats: DigestStats | None = None,
) -> str:
    lines = [
        "Daily Paper Digest",
        f"Window: {format_local_time(since_utc, timezone_name)} ~ {format_local_time(now_utc, timezone_name)}",
        f"Total sent: {len(papers)}",
        "",
    ]
    if not papers:
        lines.append("No highly relevant papers found in the last lookback window.")
        if stats:
            lines.append("")
            lines.append("[Selection Diagnostics]")
            lines.extend(build_diagnostics_lines(stats))
        return "\n".join(lines)

    for idx, paper in enumerate(papers, start=1):
        lines.append(f"#{idx} [{paper.source}] {paper.title}")
        lines.append(f"URL: {paper.url}")
        lines.append(f"Score: {paper.score:.1f}/10 | Topic: {paper.topic or 'N/A'}")
        lines.append(f"Published: {format_local_time(paper.published_at_utc, timezone_name)}")
        lines.append(f"Authors: {format_authors(paper.authors)}")
        lines.append("Matched keywords: " + (", ".join((paper.matched_keywords or [])[:10]) or "N/A"))
        if paper.llm_relevance_ko:
            lines.append(f"LLM relevance reason: {paper.llm_relevance_ko}")
        if paper.llm_core_point_ko:
            lines.append("Core point (KR):")
            lines.append(paper.llm_core_point_ko)
        if paper.llm_usefulness_ko:
            lines.append("Why useful for your work (KR):")
            lines.append(paper.llm_usefulness_ko)
        abstract = clean_text(paper.abstract)
        if len(abstract) > 500:
            abstract = abstract[:500] + "..."
        lines.append(f"Abstract: {abstract or 'No abstract available.'}")
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
    if can_use_google_oauth_for_gmail(config):
        try:
            send_email_via_google_oauth(config, message_text)
            return
        except Exception as exc:
            logging.warning(
                "Google OAuth Gmail send failed. Falling back to SMTP app password if available: %s",
                mask_sensitive_text(str(exc)),
            )
            if not config.gmail_app_password:
                raise RuntimeError(
                    "Google OAuth Gmail 발송에 실패했고 SMTP 앱 비밀번호도 설정되어 있지 않습니다. "
                    "Google OAuth 연결 상태를 확인하거나 GMAIL_APP_PASSWORD를 설정해 주세요."
                ) from exc
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(config.gmail_address, config.gmail_app_password)
        smtp.sendmail(config.gmail_address, [recipient], message_text)

def collect_and_rank_papers(
    config: AppConfig,
    now_utc: datetime,
    progress_callback: Callable[[str, int], None] | None = None,
) -> Tuple[List[Paper], DigestStats]:
    stats = DigestStats(
        ranking_threshold=config.min_relevance_score,
        send_frequency=config.send_frequency,
        lookback_hours=config.lookback_hours,
        llm_max_candidates_base=config.llm_max_candidates_base,
        llm_max_candidates_effective=config.llm_max_candidates,
    )
    since_utc = now_utc - timedelta(hours=config.lookback_hours)
    configured_arxiv_queries = dedupe_list(list(config.arxiv_queries))[: config.max_search_queries_per_source]
    configured_pubmed_queries = dedupe_list(list(config.pubmed_queries))[: config.max_search_queries_per_source]
    configured_semantic_queries = dedupe_list(list(config.semantic_scholar_queries))[
        : config.max_search_queries_per_source
    ]
    configured_google_scholar_queries = dedupe_list(list(config.google_scholar_queries))[
        : config.max_search_queries_per_source
    ]
    arxiv_queries = list(configured_arxiv_queries)
    pubmed_queries = list(configured_pubmed_queries)
    semantic_queries = list(configured_semantic_queries)
    google_scholar_queries = list(configured_google_scholar_queries)
    stats.query_strategy = "saved-topics"
    if config.enable_llm_agent and has_llm_provider(config):
        stats.estimated_llm_calls_upper_bound = 1 + (
            (max(1, config.llm_max_candidates) - 1) // max(1, config.llm_batch_size)
        )
        stats.ranking_threshold = config.llm_relevance_threshold

    emit_progress(progress_callback, "Preparing search queries...", 10)
    has_active_query = bool(arxiv_queries or pubmed_queries)
    if config.enable_semantic_scholar and semantic_queries:
        has_active_query = True
    if config.enable_google_scholar and google_scholar_queries:
        has_active_query = True
    if not has_active_query:
        raise ValueError(
            "검색 쿼리가 비어 있습니다. Topic Editor에서 'Keyword / Query 생성'을 실행하거나 "
            "Topics / Queries 테이블에 arXiv/PubMed/Semantic Scholar/Google Scholar query를 직접 입력 후 Save Topics를 눌러주세요."
        )

    def fetch_from_sources(
        selected_arxiv_queries: List[str],
        selected_pubmed_queries: List[str],
        selected_semantic_queries: List[str],
        selected_google_scholar_queries: List[str],
    ) -> Tuple[List[Paper], int, int, int, int]:
        papers_acc: List[Paper] = []
        arxiv_papers_local: List[Paper] = []
        pubmed_papers_local: List[Paper] = []
        semantic_papers_local: List[Paper] = []
        google_scholar_papers_local: List[Paper] = []
        if selected_arxiv_queries:
            emit_progress(progress_callback, "Fetching papers from arXiv...", 35)
            logging.info("Fetching papers from arXiv...")
            arxiv_papers_local = fetch_arxiv_papers(config, since_utc, selected_arxiv_queries)
            logging.info("arXiv candidates: %d", len(arxiv_papers_local))
            papers_acc.extend(arxiv_papers_local)
        else:
            logging.info("Skipping arXiv search: no configured arXiv query.")

        if selected_pubmed_queries:
            emit_progress(progress_callback, "Fetching papers from PubMed...", 55)
            logging.info("Fetching papers from PubMed...")
            pubmed_papers_local = fetch_pubmed_papers(config, since_utc, selected_pubmed_queries)
            logging.info("PubMed candidates: %d", len(pubmed_papers_local))
            papers_acc.extend(pubmed_papers_local)
        else:
            logging.info("Skipping PubMed search: no configured PubMed query.")
        if config.enable_semantic_scholar and selected_semantic_queries:
            emit_progress(progress_callback, "Fetching papers from Semantic Scholar...", 65)
            logging.info("Fetching papers from Semantic Scholar...")
            semantic_papers_local = fetch_semantic_scholar_papers(
                config,
                since_utc,
                selected_semantic_queries,
            )
            logging.info("Semantic Scholar candidates: %d", len(semantic_papers_local))
            papers_acc.extend(semantic_papers_local)
        elif not config.enable_semantic_scholar:
            logging.info("Skipping Semantic Scholar search: disabled by ENABLE_SEMANTIC_SCHOLAR.")
        else:
            logging.info("Skipping Semantic Scholar search: no configured query.")
        if config.enable_google_scholar and selected_google_scholar_queries:
            emit_progress(progress_callback, "Fetching papers from Google Scholar...", 70)
            logging.info("Fetching papers from Google Scholar...")
            google_scholar_papers_local = fetch_google_scholar_papers(
                config,
                since_utc,
                now_utc,
                selected_google_scholar_queries,
            )
            logging.info("Google Scholar candidates: %d", len(google_scholar_papers_local))
            papers_acc.extend(google_scholar_papers_local)
        elif not config.enable_google_scholar:
            logging.info("Skipping Google Scholar search: disabled by ENABLE_GOOGLE_SCHOLAR.")
        else:
            logging.info("Skipping Google Scholar search: no configured query.")
        return (
            papers_acc,
            len(arxiv_papers_local),
            len(pubmed_papers_local),
            len(semantic_papers_local),
            len(google_scholar_papers_local),
        )

    def apply_source_counts(
        arxiv_count_value: int,
        pubmed_count_value: int,
        semantic_count_value: int,
        google_scholar_count_value: int,
        total_count: int,
    ) -> None:
        stats.arxiv_candidates = arxiv_count_value
        stats.pubmed_candidates = pubmed_count_value
        stats.semantic_scholar_candidates = semantic_count_value
        stats.google_scholar_candidates = google_scholar_count_value
        stats.total_candidates = total_count

    all_papers, arxiv_count, pubmed_count, semantic_count, google_scholar_count = fetch_from_sources(
        arxiv_queries,
        pubmed_queries,
        semantic_queries,
        google_scholar_queries,
    )
    apply_source_counts(arxiv_count, pubmed_count, semantic_count, google_scholar_count, len(all_papers))

    recovery_steps: List[str] = []
    if not all_papers:
        stats.query_strategy = "saved-topics-zero-hit"
        recovery_steps.append("초기 검색 결과 0건. 자동 복구 절차를 시작합니다.")

        for attempt in range(1, ZERO_RESULT_RETRY_ATTEMPTS + 1):
            sleep_seconds = ZERO_RESULT_RETRY_SLEEP_SECONDS * attempt
            recovery_steps.append(f"동일 쿼리 재시도 {attempt}/{ZERO_RESULT_RETRY_ATTEMPTS} (대기 {sleep_seconds:.0f}초)")
            time.sleep(sleep_seconds)
            retry_papers, ra, rp, rs, rg = fetch_from_sources(
                arxiv_queries,
                pubmed_queries,
                semantic_queries,
                google_scholar_queries,
            )
            if retry_papers:
                all_papers = retry_papers
                apply_source_counts(ra, rp, rs, rg, len(all_papers))
                stats.query_strategy = f"saved-topics-retry-{attempt}"
                recovery_steps.append(f"재시도 성공: 총 {len(all_papers)}건")
                break
            recovery_steps.append("재시도 결과: 0건")

    if not all_papers:
        project_terms: List[str] = []
        for project in config.research_projects:
            project_terms.extend(extract_query_terms(f"{project.name} {project.context}"))
        project_terms = dedupe_list(project_terms)
        relaxed_arxiv = (
            build_relaxed_queries_for_source(arxiv_queries, "arxiv", project_terms)
            if arxiv_queries
            else []
        )
        relaxed_pubmed = (
            build_relaxed_queries_for_source(pubmed_queries, "pubmed", project_terms)
            if pubmed_queries
            else []
        )
        relaxed_semantic = (
            build_relaxed_queries_for_source(semantic_queries, "semantic", project_terms)
            if (config.enable_semantic_scholar and semantic_queries)
            else []
        )
        relaxed_google_scholar = (
            build_relaxed_queries_for_source(google_scholar_queries, "google", project_terms)
            if (config.enable_google_scholar and google_scholar_queries)
            else []
        )
        if relaxed_arxiv or relaxed_pubmed or relaxed_semantic or relaxed_google_scholar:
            recovery_steps.append("쿼리 완화 재검색을 수행합니다.")
            retry_papers, ra, rp, rs, rg = fetch_from_sources(
                relaxed_arxiv,
                relaxed_pubmed,
                relaxed_semantic,
                relaxed_google_scholar,
            )
            if retry_papers:
                all_papers = retry_papers
                apply_source_counts(ra, rp, rs, rg, len(all_papers))
                stats.query_strategy = "relaxed-query-retry"
                recovery_steps.append(f"완화 쿼리 성공: 총 {len(all_papers)}건")
            else:
                recovery_steps.append("완화 쿼리 결과: 0건")

    if not all_papers:
        try:
            rescue_arxiv, rescue_pubmed, rescue_semantic, rescue_google = generate_rescue_queries_with_llm(config)
            if rescue_arxiv or rescue_pubmed or rescue_semantic or rescue_google:
                recovery_steps.append("LLM 구조 요청 재검색을 수행합니다.")
                retry_papers, ra, rp, rs, rg = fetch_from_sources(
                    rescue_arxiv,
                    rescue_pubmed,
                    rescue_semantic,
                    rescue_google,
                )
                if retry_papers:
                    all_papers = retry_papers
                    apply_source_counts(ra, rp, rs, rg, len(all_papers))
                    stats.query_strategy = "llm-rescue-query"
                    recovery_steps.append(f"LLM 구조 요청 성공: 총 {len(all_papers)}건")
                else:
                    recovery_steps.append("LLM 구조 요청 결과: 0건")
            else:
                recovery_steps.append("LLM 구조 요청 쿼리를 생성하지 못했습니다.")
        except Exception as exc:
            recovery_steps.append(f"LLM 구조 요청 실패: {mask_sensitive_text(str(exc))}")

    if not all_papers and recovery_steps:
        stats.query_strategy = "recovery-failed"
    stats.zero_candidate_recovery_steps = recovery_steps

    emit_progress(progress_callback, "Ranking relevant papers...", 75)
    all_papers = [paper for paper in all_papers if paper.published_at_utc <= now_utc]
    stats.post_time_filter_candidates = len(all_papers)
    ranked, rank_meta = rank_relevant_papers(all_papers, config)
    stats.ranking_mode = str(rank_meta.get("mode", "keyword"))
    stats.ranking_threshold = float(rank_meta.get("threshold", stats.ranking_threshold or 0.0))
    stats.scoring_candidates = int(rank_meta.get("scoring_candidates", 0))
    stats.scored_count = int(rank_meta.get("scored_count", 0))
    stats.pass_count = int(rank_meta.get("pass_count", len(ranked)))
    score_buckets = rank_meta.get("score_buckets", {})
    if isinstance(score_buckets, dict):
        stats.score_buckets = {str(k): int(v) for k, v in score_buckets.items()}
    stats.llm_fallback_reason = clean_text(str(rank_meta.get("llm_fallback_reason", "")))
    if (
        stats.ranking_mode == "llm"
        and "llm_score_buckets" in rank_meta
        and isinstance(rank_meta.get("llm_score_buckets"), dict)
    ):
        stats.score_buckets = {
            str(k): int(v)
            for k, v in rank_meta.get("llm_score_buckets", {}).items()
        }
        if rank_meta.get("llm_threshold") is not None:
            try:
                stats.ranking_threshold = float(rank_meta.get("llm_threshold"))
                stats.ranking_mode = "llm"
                stats.scoring_candidates = int(
                    rank_meta.get("llm_scoring_candidates", stats.scoring_candidates)
                )
                stats.scored_count = int(rank_meta.get("llm_scored_count", stats.scored_count))
                stats.pass_count = int(rank_meta.get("llm_pass_count", stats.pass_count))
            except (TypeError, ValueError):
                pass
    logging.info("Relevant papers selected: %d", len(ranked))
    emit_progress(progress_callback, "Paper ranking completed.", 90)
    return ranked, stats


def run_digest(
    config: AppConfig,
    dry_run: bool = False,
    force_send: bool = False,
    print_dry_run_output: bool = True,
    progress_callback: Callable[[str, int], None] | None = None,
) -> str:
    emit_progress(progress_callback, "Starting digest job...", 5)
    now_utc = datetime.now(timezone.utc)
    if not dry_run and not force_send:
        should_send_today, next_due_date = evaluate_send_cadence(config, now_utc)
        if not should_send_today:
            skipped_message = (
                f"SEND_FREQUENCY={config.send_frequency} 정책으로 오늘 발송을 건너뜁니다. "
                f"다음 발송일: {next_due_date:%Y-%m-%d} ({config.timezone_name})"
            )
            logging.info(skipped_message)
            emit_progress(progress_callback, "Skipped by send frequency policy.", 100)
            return skipped_message
    since_utc = now_utc - timedelta(hours=config.lookback_hours)
    ranked_papers, stats = collect_and_rank_papers(
        config,
        now_utc,
        progress_callback=progress_callback,
    )
    papers_after_duplicate_filter, sent_history, duplicates_filtered = filter_already_sent_papers(
        ranked_papers,
        now_utc,
        config.sent_history_days,
    )
    papers = papers_after_duplicate_filter[: max(1, config.max_papers)]
    stats.duplicates_filtered = duplicates_filtered
    stats.final_selected = len(papers)
    emit_progress(progress_callback, "Composing email body...", 95)
    subject = f"[Paper Digest] {len(papers)} relevant papers ({now_utc.astimezone(config.timezone):%Y-%m-%d})"
    html_body = compose_email_html(papers, now_utc, since_utc, config.timezone_name, stats=stats)
    text_body = compose_email_text(papers, now_utc, since_utc, config.timezone_name, stats=stats)

    if dry_run:
        logging.info("Dry run enabled. Skipping email sending.")
        if print_dry_run_output:
            output_encoding = sys.stdout.encoding or "utf-8"
            safe_text = text_body.encode(output_encoding, errors="replace").decode(
                output_encoding, errors="replace"
            )
            print(safe_text)
        emit_progress(progress_callback, "Dry-run completed.", 100)
        return text_body

    emit_progress(progress_callback, "Sending email...", 98)
    send_email(config, subject, html_body, text_body)
    for paper in papers:
        sent_history[paper.paper_id] = now_utc.isoformat()
    save_sent_history(get_sent_history_path(), sent_history)
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
    user_topics_file = os.getenv("USER_TOPICS_FILE", "user_topics.json").strip() or "user_topics.json"
    user_topics_path = resolve_topics_file_path(user_topics_file, env_path=env_path)
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
    gemini_max_papers = max(1, read_int_env("GEMINI_MAX_PAPERS", 5))
    llm_relevance_threshold = read_float_env("LLM_RELEVANCE_THRESHOLD", 7.0)
    llm_batch_size = max(1, read_int_env("LLM_BATCH_SIZE", 5))
    llm_max_candidates_base = min(80, max(1, read_int_env("LLM_MAX_CANDIDATES", 30)))
    llm_max_candidates = scale_llm_max_candidates(llm_max_candidates_base, send_interval_days)
    max_search_queries_per_source = max(1, read_int_env("MAX_SEARCH_QUERIES_PER_SOURCE", 4))
    sent_history_days = max(1, read_int_env("SENT_HISTORY_DAYS", 14))

    timezone_name = os.getenv("TIMEZONE", "Asia/Seoul").strip() or "Asia/Seoul"
    send_hour = read_int_env("SEND_HOUR", 9)
    send_minute = read_int_env("SEND_MINUTE", 0)
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
    min_relevance_score = read_float_env("MIN_RELEVANCE_SCORE", 6.0)
    arxiv_max_results_per_query = max(1, read_int_env("ARXIV_MAX_RESULTS_PER_QUERY", 25))
    pubmed_max_ids_per_query = max(1, read_int_env("PUBMED_MAX_IDS_PER_QUERY", 25))

    if not user_topics_path.exists():
        template_path = get_runtime_base_dir() / "user_topics.template.json"
        if template_path.exists():
            _copy_if_needed(template_path, user_topics_path)

    (
        topic_profiles,
        research_projects,
        arxiv_queries,
        pubmed_queries,
        semantic_queries,
        google_scholar_queries,
    ) = load_topic_configuration(str(user_topics_path))

    try:
        ZoneInfo(timezone_name)
    except Exception as exc:
        raise ValueError(f"Invalid TIMEZONE value: {timezone_name}") from exc

    if require_email_credentials:
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
        if not oauth_ready and not gmail_app_password:
            missing.append("GMAIL_APP_PASSWORD")
        if missing:
            raise ValueError("Missing required env vars for email: " + ", ".join(missing))

    return AppConfig(
        gmail_address=gmail_address,
        gmail_app_password=gmail_app_password,
        recipient_email=recipient_email or gmail_address,
        enable_google_oauth=enable_google_oauth,
        google_oauth_use_for_gmail=google_oauth_use_for_gmail,
        google_oauth_client_id=google_oauth_client_id,
        google_oauth_client_secret=google_oauth_client_secret,
        google_oauth_refresh_token=google_oauth_refresh_token,
        timezone_name=timezone_name,
        send_hour=send_hour,
        send_minute=send_minute,
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
        cerebras_api_key=cerebras_api_key,
        cerebras_model=cerebras_model,
        cerebras_api_base=cerebras_api_base,
        enable_cerebras_fallback=enable_cerebras_fallback,
        gemini_max_papers=gemini_max_papers,
        llm_relevance_threshold=llm_relevance_threshold,
        llm_batch_size=llm_batch_size,
        llm_max_candidates_base=llm_max_candidates_base,
        llm_max_candidates=llm_max_candidates,
        max_search_queries_per_source=max_search_queries_per_source,
        sent_history_days=sent_history_days,
        send_frequency=send_frequency,
        send_interval_days=send_interval_days,
        send_anchor_date=send_anchor_date,
    )

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Daily paper digest sender for medical AI research interests."
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run the digest job immediately and exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not send email. Print digest output to console.",
    )
    return parser.parse_args()


def start_scheduler(config: AppConfig, dry_run: bool) -> None:
    scheduler = BlockingScheduler(timezone=config.timezone_name)
    internal_hour, internal_minute = compute_internal_schedule_time(
        config.send_hour,
        config.send_minute,
    )
    scheduler.add_job(
        lambda: run_digest(config, dry_run=dry_run),
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

    require_email_credentials = not args.dry_run
    try:
        config = load_config(require_email_credentials=require_email_credentials)
    except Exception as exc:
        logging.error("Configuration error: %s", exc)
        return 1

    try:
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
