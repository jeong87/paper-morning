import argparse
import html
import json
import logging
import os
import secrets
import smtplib
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlencode

import markdown as md
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import dotenv_values
from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template_string,
    request,
    send_file,
    session,
    url_for,
)

from paper_digest_app import (
    CEREBRAS_API_BASE_DEFAULT,
    bootstrap_runtime_files,
    compute_internal_schedule_time,
    enforce_private_file_permissions,
    get_default_data_dir,
    get_log_file_path,
    get_runtime_base_dir,
    is_keyring_available,
    load_config,
    parse_json_loose,
    load_google_oauth_bundle_defaults,
    resolve_secret_value,
    resolve_env_path,
    run_digest,
    setup_logging,
    store_secret_value,
    mask_sensitive_text,
)
from projects_config import (
    DEFAULT_PROJECTS_CONFIG_FILE,
    read_projects_config,
    validate_projects,
    write_projects_config,
)


def read_app_version() -> str:
    candidates = [
        (get_runtime_base_dir() / "VERSION").resolve(),
        (get_runtime_base_dir().parent / "VERSION").resolve(),
        Path("VERSION").resolve(),
    ]
    for version_path in candidates:
        if not version_path.exists():
            continue
        value = version_path.read_text(encoding="utf-8-sig").strip()
        if value:
            return value
    return "0.5.2"


APP_VERSION = read_app_version()
APP_TITLE = f"Paper Digest Web Console v{APP_VERSION}"
SCHEDULER_JOB_ID = "daily-paper-digest-web-job"
SESSION_SECRET_ENV_KEY = "WEB_APP_SECRET_KEY"
AUTH_TOKEN_ENV_KEY = "WEB_APP_AUTH_TOKEN"
WEB_AUTH_SESSION_KEY = "pm_auth_ok"
UI_LANGUAGE_SESSION_KEY = "pm_ui_lang"
GEMINI_API_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
GOOGLE_OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_OAUTH_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_OAUTH_STATE_SESSION_KEY = "google_oauth_state"
GOOGLE_OAUTH_REDIRECT_URI_SESSION_KEY = "google_oauth_redirect_uri"
GOOGLE_OAUTH_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.send",
]
OAUTH_UI_ENABLED = False

EXPECTED_ENV_KEYS = [
    "GMAIL_ADDRESS",
    "GMAIL_APP_PASSWORD",
    "RECIPIENT_EMAIL",
    "TIMEZONE",
    "SEND_HOUR",
    "SEND_MINUTE",
    "SEND_TIME_WINDOW_MINUTES",
    "SEND_FREQUENCY",
    "SEND_ANCHOR_DATE",
    "LOOKBACK_HOURS",
    "MAX_PAPERS",
    "MIN_RELEVANCE_SCORE",
    "ARXIV_MAX_RESULTS_PER_QUERY",
    "PUBMED_MAX_IDS_PER_QUERY",
    "ENABLE_SEMANTIC_SCHOLAR",
    "SEMANTIC_SCHOLAR_API_KEY",
    "SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY",
    "ENABLE_GOOGLE_SCHOLAR",
    "GOOGLE_SCHOLAR_API_KEY",
    "GOOGLE_SCHOLAR_MAX_RESULTS_PER_QUERY",
    "MAX_SEARCH_QUERIES_PER_SOURCE",
    "NCBI_API_KEY",
    "PROJECTS_CONFIG_FILE",
    "USER_TOPICS_FILE",
    "ONBOARDING_MODE",
    "WEB_PASSWORD",
    "UI_LANGUAGE",
    "ALLOW_INSECURE_REMOTE_WEB",
    "USE_KEYRING",
    "ENABLE_GOOGLE_OAUTH",
    "GOOGLE_OAUTH_USE_FOR_GMAIL",
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "GOOGLE_OAUTH_REFRESH_TOKEN",
    "GOOGLE_OAUTH_CONNECTED_EMAIL",
    "GOOGLE_OAUTH_REDIRECT_URI",
    "SETUP_WIZARD_COMPLETED",
    "SEND_NOW_COOLDOWN_SECONDS",
    "SENT_HISTORY_DAYS",
    "ENABLE_LLM_AGENT",
    "GEMINI_API_KEY",
    "ENABLE_GEMINI_ADVANCED_REASONING",
    "GEMINI_MODEL",
    "OUTPUT_LANGUAGE",
    "ENABLE_CEREBRAS_FALLBACK",
    "CEREBRAS_API_KEY",
    "CEREBRAS_MODEL",
    "CEREBRAS_API_BASE",
    "GEMINI_MAX_PAPERS",
    "LLM_RELEVANCE_THRESHOLD",
    "LLM_BATCH_SIZE",
    "LLM_MAX_CANDIDATES",
]

DEFAULT_ENV_VALUES = {
    "GMAIL_ADDRESS": "",
    "GMAIL_APP_PASSWORD": "",
    "RECIPIENT_EMAIL": "",
    "TIMEZONE": "UTC",
    "SEND_HOUR": "9",
    "SEND_MINUTE": "0",
    "SEND_TIME_WINDOW_MINUTES": "15",
    "SEND_FREQUENCY": "daily",
    "SEND_ANCHOR_DATE": "2026-01-01",
    "LOOKBACK_HOURS": "24",
    "MAX_PAPERS": "5",
    "MIN_RELEVANCE_SCORE": "6.0",
    "ARXIV_MAX_RESULTS_PER_QUERY": "25",
    "PUBMED_MAX_IDS_PER_QUERY": "25",
    "ENABLE_SEMANTIC_SCHOLAR": "true",
    "SEMANTIC_SCHOLAR_API_KEY": "",
    "SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY": "20",
    "ENABLE_GOOGLE_SCHOLAR": "false",
    "GOOGLE_SCHOLAR_API_KEY": "",
    "GOOGLE_SCHOLAR_MAX_RESULTS_PER_QUERY": "10",
    "MAX_SEARCH_QUERIES_PER_SOURCE": "4",
    "NCBI_API_KEY": "",
    "PROJECTS_CONFIG_FILE": DEFAULT_PROJECTS_CONFIG_FILE,
    "USER_TOPICS_FILE": "user_topics.json",
    "ONBOARDING_MODE": "preview",
    "WEB_PASSWORD": "",
    "UI_LANGUAGE": "en",
    "ALLOW_INSECURE_REMOTE_WEB": "false",
    "USE_KEYRING": "true",
    "ENABLE_GOOGLE_OAUTH": "false",
    "GOOGLE_OAUTH_USE_FOR_GMAIL": "true",
    "GOOGLE_OAUTH_CLIENT_ID": "",
    "GOOGLE_OAUTH_CLIENT_SECRET": "",
    "GOOGLE_OAUTH_REFRESH_TOKEN": "",
    "GOOGLE_OAUTH_CONNECTED_EMAIL": "",
    "GOOGLE_OAUTH_REDIRECT_URI": "",
    "SETUP_WIZARD_COMPLETED": "false",
    "SEND_NOW_COOLDOWN_SECONDS": "300",
    "SENT_HISTORY_DAYS": "14",
    "ENABLE_LLM_AGENT": "true",
    "GEMINI_API_KEY": "",
    "ENABLE_GEMINI_ADVANCED_REASONING": "true",
    "GEMINI_MODEL": "gemini-3.1-flash",
    "OUTPUT_LANGUAGE": "en",
    "ENABLE_CEREBRAS_FALLBACK": "true",
    "CEREBRAS_API_KEY": "",
    "CEREBRAS_MODEL": "gpt-oss-120b",
    "CEREBRAS_API_BASE": CEREBRAS_API_BASE_DEFAULT,
    "GEMINI_MAX_PAPERS": "5",
    "LLM_RELEVANCE_THRESHOLD": "7",
    "LLM_BATCH_SIZE": "5",
    "LLM_MAX_CANDIDATES": "30",
}

SECRET_ENV_KEYS = {
    "GMAIL_APP_PASSWORD",
    "GEMINI_API_KEY",
    "CEREBRAS_API_KEY",
    "SEMANTIC_SCHOLAR_API_KEY",
    "GOOGLE_SCHOLAR_API_KEY",
    "WEB_PASSWORD",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "GOOGLE_OAUTH_REFRESH_TOKEN",
}
OAUTH_BOOL_FORM_KEYS = {"ENABLE_GOOGLE_OAUTH", "GOOGLE_OAUTH_USE_FOR_GMAIL"}
OAUTH_TEXT_FORM_KEYS = {"GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_REDIRECT_URI"}
OAUTH_SECRET_FORM_KEYS = {"GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REFRESH_TOKEN"}
OAUTH_FORM_KEYS = OAUTH_BOOL_FORM_KEYS | OAUTH_TEXT_FORM_KEYS | OAUTH_SECRET_FORM_KEYS
APP_LOGO_FILENAME = "paper-morning-logo.png"

BASE_TEMPLATE = """
<!doctype html>
<html lang="{{ ui_language }}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{ title }}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #f4f5f7;
      --sidebar-bg: #1a1d23;
      --sidebar-text: #a8b3c4;
      --sidebar-active-bg: #2a2f3a;
      --sidebar-active-text: #ffffff;
      --card: #ffffff;
      --card-border: #e5e8ef;
      --text: #111827;
      --text-sub: #6b7280;
      --accent: #4f6ef7;
      --accent-hover: #3b55e0;
      --ok-bg: #ecfdf5;
      --ok-text: #065f46;
      --ok-border: #6ee7b7;
      --danger-bg: #fef2f2;
      --danger-text: #991b1b;
      --danger-border: #fca5a5;
      --radius-sm: 6px;
      --radius-md: 10px;
      --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
      --transition: 0.15s ease;
      --sidebar-width: 220px;
    }

    *, *::before, *::after { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Inter", "Pretendard", "Segoe UI", sans-serif;
      font-size: 14px;
      line-height: 1.6;
      background: var(--bg);
      color: var(--text);
      display: flex;
      min-height: 100vh;
    }

    .sidebar {
      width: var(--sidebar-width);
      min-height: 100vh;
      background: var(--sidebar-bg);
      display: flex;
      flex-direction: column;
      position: fixed;
      top: 0;
      left: 0;
      bottom: 0;
      z-index: 100;
    }
    .sidebar-logo {
      padding: 20px 20px 16px;
      border-bottom: 1px solid rgba(255,255,255,0.07);
    }
    .logo-image-wrap {
      width: 132px;
      height: 132px;
      border-radius: 12px;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.12);
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 0 12px;
      overflow: hidden;
    }
    .logo-image {
      width: 100%;
      height: 100%;
      object-fit: contain;
      display: block;
    }
    .logo-title {
      font-size: 13px;
      font-weight: 600;
      color: #fff;
      letter-spacing: 0.02em;
    }
    .logo-version {
      font-size: 11px;
      color: var(--sidebar-text);
      margin-top: 2px;
    }
    .sidebar-nav {
      padding: 12px 10px;
      flex: 1;
    }
    .sidebar-nav a {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 9px 12px;
      border-radius: var(--radius-sm);
      color: var(--sidebar-text);
      text-decoration: none;
      font-size: 13.5px;
      font-weight: 500;
      transition: background var(--transition), color var(--transition);
      margin-bottom: 2px;
    }
    .sidebar-nav a:hover {
      background: rgba(255,255,255,0.06);
      color: var(--sidebar-active-text);
    }
    .sidebar-nav a.active {
      background: var(--sidebar-active-bg);
      color: var(--sidebar-active-text);
    }
    .nav-icon {
      font-size: 16px;
      flex-shrink: 0;
    }

    .main-content {
      margin-left: var(--sidebar-width);
      flex: 1;
      padding: 32px 36px 48px;
      max-width: calc(100vw - var(--sidebar-width));
    }
    .page-header {
      margin-bottom: 24px;
    }
    .page-header h1 {
      font-size: 20px;
      font-weight: 600;
      margin: 0 0 4px;
    }
    .page-header p {
      font-size: 13px;
      color: var(--text-sub);
      margin: 0;
    }

    .card {
      background: var(--card);
      border: 1px solid var(--card-border);
      border-radius: var(--radius-md);
      padding: 20px 22px;
      margin-bottom: 16px;
      box-shadow: var(--shadow-sm);
    }
    .card-title {
      font-size: 13px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-sub);
      margin: 0 0 14px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--card-border);
    }

    button, .btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: var(--accent);
      color: #fff;
      border: none;
      border-radius: var(--radius-sm);
      padding: 8px 14px;
      font-size: 13.5px;
      font-weight: 500;
      font-family: inherit;
      cursor: pointer;
      transition: background var(--transition), transform var(--transition), box-shadow var(--transition);
      box-shadow: 0 1px 2px rgba(79,110,247,0.25);
    }
    button:hover:not(:disabled) {
      background: var(--accent-hover);
      transform: translateY(-1px);
    }
    button:active:not(:disabled) { transform: translateY(0); }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    .btn-ghost {
      background: transparent;
      color: var(--text-sub);
      border: 1px solid var(--card-border);
      box-shadow: none;
    }
    .btn-ghost:hover:not(:disabled) {
      background: #f9fafb;
      color: var(--text);
      box-shadow: none;
    }
    .btn-danger {
      background: var(--danger-bg);
      color: var(--danger-text);
      border: 1px solid var(--danger-border);
      box-shadow: none;
    }
    .btn-danger:hover:not(:disabled) {
      background: #fee2e2;
      box-shadow: none;
    }
    .btn-success {
      background: #059669;
      box-shadow: 0 1px 2px rgba(5,150,105,0.25);
    }
    .btn-success:hover:not(:disabled) {
      background: #047857;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 8px;
      border-radius: 99px;
      font-size: 12px;
      font-weight: 500;
    }
    .badge-idle { background: #f3f4f6; color: var(--text-sub); }
    .badge-running { background: #dbeafe; color: #1d4ed8; }
    .badge-ok { background: var(--ok-bg); color: var(--ok-text); }
    .badge-danger { background: var(--danger-bg); color: var(--danger-text); }

    input[type="text"],
    input[type="password"],
    input[type="number"],
    input[type="time"],
    input[type="email"],
    select,
    textarea {
      width: 100%;
      box-sizing: border-box;
      padding: 8px 10px;
      border: 1px solid var(--card-border);
      border-radius: var(--radius-sm);
      font-size: 13.5px;
      font-family: inherit;
      color: var(--text);
      background: #fff;
      transition: border-color var(--transition), box-shadow var(--transition);
      outline: none;
    }
    input:focus, select:focus, textarea:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(79,110,247,0.12);
    }
    textarea {
      min-height: 80px;
      font-family: "Consolas", "Menlo", monospace;
      font-size: 12.5px;
      resize: vertical;
    }
    input[type="checkbox"] {
      width: 16px;
      height: 16px;
      accent-color: var(--accent);
      cursor: pointer;
    }

    .settings-grid {
      display: flex;
      flex-direction: column;
      gap: 0;
    }
    .settings-row {
      display: grid;
      grid-template-columns: 240px 1fr;
      gap: 16px;
      align-items: start;
      padding: 12px 0;
      border-bottom: 1px solid var(--card-border);
    }
    .settings-row:last-child { border-bottom: none; }
    .settings-label { padding-top: 6px; }
    .settings-label strong {
      display: block;
      font-size: 13.5px;
      font-weight: 500;
      color: var(--text);
    }
    .settings-label small {
      display: block;
      margin-top: 2px;
      font-size: 12px;
      color: var(--text-sub);
      line-height: 1.4;
    }

    .action-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }
    .action-card {
      background: var(--card);
      border: 1px solid var(--card-border);
      border-radius: var(--radius-md);
      padding: 16px;
      box-shadow: var(--shadow-sm);
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .action-icon { font-size: 20px; }
    .action-label {
      font-size: 14px;
      font-weight: 600;
      color: var(--text);
    }
    .action-desc {
      font-size: 12.5px;
      color: var(--text-sub);
      margin-bottom: 6px;
    }

    .status-panel {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 10px;
    }
    .status-kv {
      border: 1px solid var(--card-border);
      border-radius: var(--radius-sm);
      padding: 8px 10px;
      background: #fafbfd;
    }
    .kv-label {
      font-size: 11px;
      color: var(--text-sub);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .kv-value {
      font-size: 13px;
      font-weight: 500;
      color: var(--text);
      margin-top: 2px;
    }

    .progress-track {
      background: #eef1f6;
      border: 1px solid var(--card-border);
      border-radius: 99px;
      height: 8px;
      overflow: hidden;
      margin: 10px 0;
    }
    .progress-fill {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, var(--accent), #7c3aed);
      border-radius: 99px;
      transition: width 0.4s ease;
    }

    .flash {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      padding: 12px 14px;
      border-radius: var(--radius-sm);
      margin-bottom: 14px;
      font-size: 13.5px;
      animation: fadeIn 0.25s ease;
    }
    .flash.ok {
      background: var(--ok-bg);
      color: var(--ok-text);
      border: 1px solid var(--ok-border);
    }
    .flash.danger {
      background: var(--danger-bg);
      color: var(--danger-text);
      border: 1px solid var(--danger-border);
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(-6px); }
      to { opacity: 1; transform: none; }
    }

    pre {
      background: #0f1117;
      color: #d1d5db;
      border-radius: var(--radius-md);
      padding: 16px;
      font-size: 12.5px;
      font-family: "Consolas", "Menlo", monospace;
      white-space: pre-wrap;
      word-break: break-all;
      max-height: 420px;
      overflow-y: auto;
      margin: 0;
    }

    table { width: 100%; border-collapse: collapse; }
    thead th {
      text-align: left;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--text-sub);
      padding: 8px 10px;
      border-bottom: 2px solid var(--card-border);
    }
    tbody tr:hover { background: #f9fafb; }
    tbody td {
      padding: 8px 10px;
      vertical-align: top;
      border-bottom: 1px solid var(--card-border);
    }

    .md-body h1, .md-body h2, .md-body h3 { margin-top: 1.2em; }
    .md-body code {
      background: #f2f5fb;
      padding: 2px 4px;
      border-radius: 4px;
    }
    .md-body pre code {
      background: transparent;
      padding: 0;
    }

    .small { font-size: 12px; color: var(--text-sub); }
    .text-ok { color: var(--ok-text); }
    .text-danger { color: var(--danger-text); }
    .button-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
    .gap-8 { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

    @media (max-width: 900px) {
      .sidebar { display: none; }
      .main-content {
        margin-left: 0;
        max-width: 100vw;
        padding: 16px;
      }
      .action-grid { grid-template-columns: 1fr; }
      .status-panel { grid-template-columns: 1fr 1fr; }
      .settings-row { grid-template-columns: 1fr; gap: 4px; }
    }
  </style>
</head>
<body>
  <aside class="sidebar">
    <div class="sidebar-logo">
      <div class="logo-image-wrap">
        <img src="{{ url_for('app_logo') }}" alt="Paper Morning Logo" class="logo-image" onerror="this.style.display='none'; this.parentElement.style.display='none';" />
      </div>
      <div class="logo-title">Paper Morning</div>
      <div class="logo-version">v{{ app_version }}</div>
    </div>
    <nav class="sidebar-nav">
      <a href="{{ url_for('home') }}" class="{{ 'active' if active_page == 'home' else '' }}">
        <span class="nav-icon">🏠</span> Home
      </a>
      <a href="{{ url_for('setup') }}" class="{{ 'active' if active_page == 'setup' else '' }}">
        <span class="nav-icon">🧭</span> Setup Wizard
      </a>
      <a href="{{ url_for('settings') }}" class="{{ 'active' if active_page == 'settings' else '' }}">
        <span class="nav-icon">⚙️</span> Settings
      </a>
      <a href="{{ url_for('topics') }}" class="{{ 'active' if active_page == 'topics' else '' }}">
        <span class="nav-icon">📋</span> Topic Editor
      </a>
      <a href="{{ url_for('logs_page') }}" class="{{ 'active' if active_page == 'logs' else '' }}">
        <span class="nav-icon">🪵</span> Logs
      </a>
      <a href="{{ url_for('manual') }}" class="{{ 'active' if active_page == 'manual' else '' }}">
        <span class="nav-icon">📖</span> Manual
      </a>
      <a href="{{ url_for('license_page') }}" class="{{ 'active' if active_page == 'license' else '' }}">
        <span class="nav-icon">⚖️</span> License
      </a>
    </nav>
  </aside>
  <div class="main-content">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="flash {{ category }}">{{ message }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}
    {{ body|safe }}
  </div>
  <script>
    window.APP_TOKEN = "{{ auth_token }}";
  </script>
</body>
</html>
"""


app = Flask(__name__)
app.secret_key = os.getenv(SESSION_SECRET_ENV_KEY, "").strip() or secrets.token_urlsafe(32)
scheduler = BackgroundScheduler()
scheduler_lock = threading.Lock()
APP_AUTH_TOKEN = os.getenv(AUTH_TOKEN_ENV_KEY, "").strip() or secrets.token_urlsafe(32)

job_state_lock = threading.Lock()
job_state: Dict[str, Any] = {
    "running": False,
    "kind": "",
    "status": "Idle",
    "progress": 0,
    "error": "",
    "started_at": "",
    "finished_at": "",
}

last_dry_run_output = ""
last_send_result = ""


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def env_truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def safe_exception_text(exc: Exception) -> str:
    return mask_sensitive_text(str(exc))


def build_gemini_model_candidates(primary_model: str) -> List[str]:
    base_model = str(primary_model or "").strip() or "gemini-3.1-flash"
    lower = base_model.lower()
    candidates = [base_model]
    if "pro" in lower:
        candidates.extend(["gemini-3.1-flash", "gemini-2.5-flash"])
    elif "flash" in lower:
        candidates.append("gemini-2.5-flash")
    else:
        candidates.extend(["gemini-3.1-flash", "gemini-2.5-flash"])

    deduped: List[str] = []
    seen = set()
    for model in candidates:
        key = model.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(model)
    return deduped


def is_gemini_model_unavailable(status_code: int, body_text: str) -> bool:
    if status_code not in {400, 404}:
        return False
    lowered = (body_text or "").lower()
    markers = [
        "not found",
        "not exist",
        "unsupported",
        "unknown model",
        "model",
        "not available",
    ]
    return any(marker in lowered for marker in markers)


def post_gemini_with_model_fallback(
    gemini_api_key: str,
    gemini_model: str,
    payload: Dict[str, Any],
    timeout_seconds: int,
) -> Tuple[Dict[str, Any], str]:
    candidates = build_gemini_model_candidates(gemini_model)
    errors: List[str] = []
    for idx, model in enumerate(candidates):
        try:
            response = requests.post(
                GEMINI_API_URL_TEMPLATE.format(model=model),
                headers={"x-goog-api-key": gemini_api_key},
                json=payload,
                timeout=timeout_seconds,
            )
        except Exception as exc:
            raise RuntimeError(f"Gemini API request failed: {safe_exception_text(exc)}") from exc

        if response.status_code >= 400:
            body_text = response.text or ""
            if is_gemini_model_unavailable(response.status_code, body_text) and idx < len(candidates) - 1:
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
                raise RuntimeError(f"Gemini API request failed: {safe_exception_text(exc)}") from exc

        try:
            return response.json(), model
        except Exception as exc:
            raise RuntimeError(f"Gemini response JSON parse failed: {safe_exception_text(exc)}") from exc

    if errors:
        raise RuntimeError("Gemini model fallback exhausted: " + "; ".join(errors))
    raise RuntimeError("Gemini call failed without usable response.")


def get_effective_gemini_model(env_map: Dict[str, str]) -> str:
    advanced = env_truthy(str(env_map.get("ENABLE_GEMINI_ADVANCED_REASONING", "true")))
    if advanced:
        return "gemini-3.1-pro"
    configured = str(env_map.get("GEMINI_MODEL", "gemini-3.1-flash") or "").strip()
    return configured or "gemini-3.1-flash"


def get_effective_google_oauth_values(env_map: Dict[str, str]) -> Dict[str, Any]:
    bundle = load_google_oauth_bundle_defaults()
    configured_client_id = str(env_map.get("GOOGLE_OAUTH_CLIENT_ID", "") or "").strip()
    configured_client_secret = resolve_secret_value(
        "GOOGLE_OAUTH_CLIENT_SECRET",
        str(env_map.get("GOOGLE_OAUTH_CLIENT_SECRET", "") or ""),
    )
    bundled_client_id = str(bundle.get("client_id", "") or "").strip()
    bundled_client_secret = str(bundle.get("client_secret", "") or "").strip()
    bundled_redirect_uri = str(bundle.get("redirect_uri", "") or "").strip()
    client_id = configured_client_id or bundled_client_id
    client_secret = configured_client_secret or bundled_client_secret
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": bundled_redirect_uri,
        "using_bundled_client_id": (not configured_client_id) and bool(bundled_client_id),
        "using_bundled_client_secret": (not configured_client_secret) and bool(bundled_client_secret),
        "bundle_ready": bool(bundled_client_id and bundled_client_secret),
    }


def get_google_oauth_redirect_uri(env_map: Dict[str, str], prefer_request: bool = False) -> str:
    configured = str(env_map.get("GOOGLE_OAUTH_REDIRECT_URI", "") or "").strip()
    if configured:
        return configured
    oauth_values = get_effective_google_oauth_values(env_map)
    bundled_redirect = str(oauth_values.get("redirect_uri", "") or "").strip()
    if bundled_redirect:
        return bundled_redirect
    if prefer_request:
        try:
            return url_for("google_oauth_callback", _external=True)
        except Exception:
            pass
    return "http://127.0.0.1:5050/oauth/google/callback"


def exchange_google_oauth_code(client_id: str, client_secret: str, code: str, redirect_uri: str) -> Dict[str, Any]:
    response = requests.post(
        GOOGLE_OAUTH_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Invalid OAuth token response format.")
    return payload


def refresh_google_oauth_access_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> str:
    response = requests.post(
        GOOGLE_OAUTH_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    access_token = str(payload.get("access_token", "")).strip() if isinstance(payload, dict) else ""
    if not access_token:
        raise ValueError("OAuth refresh returned no access token.")
    return access_token


def fetch_google_userinfo(access_token: str) -> Dict[str, Any]:
    response = requests.get(
        GOOGLE_OAUTH_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Invalid userinfo response format.")
    return payload


def has_google_oauth_gmail_ready(env_map: Dict[str, str]) -> bool:
    oauth_values = get_effective_google_oauth_values(env_map)
    return (
        env_truthy(str(env_map.get("ENABLE_GOOGLE_OAUTH", "false")))
        and env_truthy(str(env_map.get("GOOGLE_OAUTH_USE_FOR_GMAIL", "true")))
        and bool(str(oauth_values.get("client_id", "")).strip())
        and bool(str(oauth_values.get("client_secret", "")).strip())
        and bool(resolve_secret_value("GOOGLE_OAUTH_REFRESH_TOKEN", str(env_map.get("GOOGLE_OAUTH_REFRESH_TOKEN", ""))))
    )


def is_local_host(host: str) -> bool:
    lowered = str(host or "").strip().lower()
    return lowered in {"127.0.0.1", "localhost", "::1"}


def get_web_password(env_map: Dict[str, str] | None = None) -> str:
    values = env_map or read_env_map()
    return resolve_secret_value("WEB_PASSWORD", str(values.get("WEB_PASSWORD", "") or ""))


def ensure_host_security(host: str, env_map: Dict[str, str] | None = None) -> None:
    values = env_map or read_env_map()
    if is_local_host(host):
        return
    allow_insecure_remote = env_truthy(str(values.get("ALLOW_INSECURE_REMOTE_WEB", "false")))
    if not allow_insecure_remote:
        raise ValueError(
            "Remote host binding (e.g. 0.0.0.0) is blocked by default. "
            "Only enable ALLOW_INSECURE_REMOTE_WEB=true together with WEB_PASSWORD when strictly required."
        )
    if not get_web_password(values):
        raise ValueError(
            "To bind --host to non-local addresses, set WEB_PASSWORD first."
        )
    logging.warning(
        "Running web console on non-local host without TLS. This is for controlled test use only."
    )


def is_setup_completed(env_map: Dict[str, str] | None = None) -> bool:
    values = env_map or read_env_map()
    if env_truthy(values.get("SETUP_WIZARD_COMPLETED", "")):
        return True
    gmail_address = str(values.get("GMAIL_ADDRESS", "")).strip()
    recipient = str(values.get("RECIPIENT_EMAIL", "")).strip()
    if not gmail_address or not recipient:
        return False
    if has_google_oauth_gmail_ready(values):
        return True
    app_password = resolve_secret_value("GMAIL_APP_PASSWORD", str(values.get("GMAIL_APP_PASSWORD", "")))
    return bool(str(app_password).strip())


def should_force_setup(path: str, env_map: Dict[str, str] | None = None) -> bool:
    if is_setup_completed(env_map):
        return False
    allowed = {"/setup", "/manual", "/license", "/login"}
    if path in allowed:
        return False
    if path.startswith("/oauth/google/"):
        return False
    if path.startswith("/static/") or path.startswith("/assets/") or path.startswith("/setup/"):
        return False
    return True


def get_send_state_path() -> Path:
    return (get_default_data_dir() / "send_state.json").resolve()


def read_send_state() -> Dict[str, Any]:
    path = get_send_state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def write_send_state(data: Dict[str, Any]) -> None:
    path = get_send_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    enforce_private_file_permissions(path)


def check_send_cooldown(env_map: Dict[str, str] | None = None) -> Tuple[bool, str]:
    values = env_map or read_env_map()
    cooldown_raw = str(values.get("SEND_NOW_COOLDOWN_SECONDS", "300")).strip()
    try:
        cooldown_seconds = max(0, int(cooldown_raw))
    except ValueError:
        cooldown_seconds = 300
    if cooldown_seconds <= 0:
        return True, ""

    state = read_send_state()
    last_sent = float(state.get("last_send_now_ts", 0.0) or 0.0)
    elapsed = time.time() - last_sent
    if elapsed >= cooldown_seconds:
        return True, ""
    wait = int(max(1, cooldown_seconds - elapsed))
    return False, f"Send-now can be retried after {wait} seconds."


def mark_send_now_executed() -> None:
    state = read_send_state()
    state["last_send_now_ts"] = time.time()
    state["last_send_now_at"] = now_iso()
    write_send_state(state)


def read_env_map() -> Dict[str, str]:
    env_path = resolve_env_path()
    merged = dict(DEFAULT_ENV_VALUES)
    env_example_candidates = [
        (resolve_env_path().parent / ".env.example").resolve(),
        (get_runtime_base_dir() / ".env.example").resolve(),
        (get_runtime_base_dir().parent / "config" / ".env.example").resolve(),
        (Path("config") / ".env.example").resolve(),
        Path(".env.example").resolve(),
    ]
    env_example_path = next((path for path in env_example_candidates if path.exists()), None)
    if env_example_path:
        merged.update({k: v or "" for k, v in dotenv_values(str(env_example_path)).items()})
    if env_path.exists():
        merged.update({k: v or "" for k, v in dotenv_values(str(env_path)).items()})
    for key in EXPECTED_ENV_KEYS:
        merged.setdefault(key, DEFAULT_ENV_VALUES.get(key, ""))
    return merged


def write_env_map(updated_values: Dict[str, str]) -> None:
    env_path = resolve_env_path()
    current = {}
    if env_path.exists():
        current = {k: v or "" for k, v in dotenv_values(str(env_path)).items()}
    merged = dict(current)
    merged.update(updated_values)
    use_keyring = env_truthy(str(merged.get("USE_KEYRING", "true")))
    if use_keyring:
        for secret_key in SECRET_ENV_KEYS:
            raw = str(merged.get(secret_key, "") or "").strip()
            if not raw:
                continue
            merged[secret_key] = store_secret_value(secret_key, raw)

    ordered_keys: List[str] = list(EXPECTED_ENV_KEYS)
    for key in sorted(merged.keys()):
        if key not in ordered_keys:
            ordered_keys.append(key)

    lines = []
    for key in ordered_keys:
        value = str(merged.get(key, "")).replace("\n", " ").strip()
        lines.append(f"{key}={value}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    enforce_private_file_permissions(env_path)


def normalize_ui_language(raw: str) -> str:
    value = str(raw or "").strip().lower()
    if value.startswith("ko"):
        return "ko"
    return "en"


def get_ui_language(env_map: Dict[str, str] | None = None) -> str:
    requested = str(request.args.get("lang", "") or "").strip().lower()
    if requested in {"en", "ko"}:
        session[UI_LANGUAGE_SESSION_KEY] = requested
        return requested
    cached = str(session.get(UI_LANGUAGE_SESSION_KEY, "") or "").strip().lower()
    if cached in {"en", "ko"}:
        return cached
    values = env_map or read_env_map()
    default_lang = normalize_ui_language(str(values.get("UI_LANGUAGE", "en")))
    session[UI_LANGUAGE_SESSION_KEY] = default_lang
    return default_lang


def get_topics_path(env_map: Dict[str, str]) -> Path:
    path = (env_map.get("USER_TOPICS_FILE") or "user_topics.json").strip()
    topic_path = Path(path).expanduser()
    if not topic_path.is_absolute():
        topic_path = resolve_env_path().parent / topic_path
    return topic_path.resolve()


def get_projects_config_path(env_map: Dict[str, str]) -> Path:
    configured = (env_map.get("PROJECTS_CONFIG_FILE") or DEFAULT_PROJECTS_CONFIG_FILE).strip()
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = resolve_env_path().parent / path
    return path.resolve()


def build_projects_for_llm(projects: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    prepared: List[Dict[str, str]] = []
    for item in projects:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        context = str(item.get("context", "")).strip()
        keywords_raw = item.get("keywords", [])
        if isinstance(keywords_raw, str):
            keywords = [part.strip() for part in keywords_raw.split(",") if part.strip()]
        elif isinstance(keywords_raw, list):
            keywords = [str(part).strip() for part in keywords_raw if str(part).strip()]
        else:
            keywords = []
        if keywords:
            context = f"{context} | Keywords: {', '.join(keywords)}" if context else f"Keywords: {', '.join(keywords)}"
        if not (name or context):
            continue
        prepared.append({"name": name or "Untitled project", "context": context})
    return prepared


def maybe_generate_topics_from_projects(
    env_map: Dict[str, str],
    topics_path: Path,
    topics_payload: Dict[str, Any],
) -> Tuple[bool, str, Dict[str, Any]]:
    projects = topics_payload.get("projects", []) if isinstance(topics_payload, dict) else []
    if not isinstance(projects, list):
        projects = []

    if not projects:
        projects_path = get_projects_config_path(env_map)
        loaded_projects, errors = read_projects_config(projects_path)
        if errors:
            return (
                False,
                "No projects found for preview bootstrap. "
                f"Add at least one project in {projects_path}. ({'; '.join(errors)})",
                topics_payload,
            )
        projects = loaded_projects

    llm_projects = build_projects_for_llm(projects)
    if not llm_projects:
        return False, "Project descriptions are empty. Add project name/context first.", topics_payload

    gemini_api_key = resolve_secret_value("GEMINI_API_KEY", env_map.get("GEMINI_API_KEY", "").strip())
    enable_cerebras_fallback = env_truthy(env_map.get("ENABLE_CEREBRAS_FALLBACK", "true"))
    cerebras_api_key = resolve_secret_value("CEREBRAS_API_KEY", env_map.get("CEREBRAS_API_KEY", "").strip())
    if not gemini_api_key and not (enable_cerebras_fallback and cerebras_api_key):
        return (
            False,
            "Preview bootstrap needs an LLM key. Set GEMINI_API_KEY "
            "(or enable Cerebras fallback with CEREBRAS_API_KEY).",
            topics_payload,
        )

    gemini_model = get_effective_gemini_model(env_map)
    cerebras_model = env_map.get("CEREBRAS_MODEL", "gpt-oss-120b").strip() or "gpt-oss-120b"
    cerebras_api_base = (
        env_map.get("CEREBRAS_API_BASE", CEREBRAS_API_BASE_DEFAULT).strip() or CEREBRAS_API_BASE_DEFAULT
    )

    try:
        raw_response = call_llm_for_topic_generation(
            projects=llm_projects,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            cerebras_api_key=cerebras_api_key,
            cerebras_model=cerebras_model,
            cerebras_api_base=cerebras_api_base,
            enable_cerebras_fallback=enable_cerebras_fallback,
        )
    except Exception as exc:
        return False, f"Automatic topic generation failed: {safe_exception_text(exc)}", topics_payload

    generated_topics = sanitize_generated_topics(raw_response)
    if not generated_topics:
        return False, "Automatic topic generation returned no valid query set.", topics_payload

    next_payload = {"projects": projects, "topics": generated_topics}
    topics_path.parent.mkdir(parents=True, exist_ok=True)
    topics_path.write_text(json.dumps(next_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    enforce_private_file_permissions(topics_path)
    return True, f"Generated {len(generated_topics)} topics from project descriptions.", next_payload


def ensure_bootstrap_files() -> None:
    env_path, topics_path = bootstrap_runtime_files()
    logging.info("Using env file: %s", env_path)
    logging.info("Using topics file: %s", topics_path)


def scheduled_digest_job() -> None:
    try:
        config = load_config(require_email_credentials=True)
        run_digest(config, dry_run=False)
    except Exception:
        logging.exception("Scheduled digest job failed.")


def refresh_scheduler() -> str:
    with scheduler_lock:
        config = load_config(require_email_credentials=True)
        internal_hour, internal_minute = compute_internal_schedule_time(
            config.send_hour,
            config.send_minute,
        )
        scheduler.add_job(
            scheduled_digest_job,
            "cron",
            hour=internal_hour,
            minute=internal_minute,
            timezone=config.timezone_name,
            id=SCHEDULER_JOB_ID,
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=3600,
        )
        if not scheduler.running:
            scheduler.start()
        return (
            f"Scheduler active: user {config.send_hour:02d}:{config.send_minute:02d} "
            f"-> internal {internal_hour:02d}:{internal_minute:02d} "
            f"({config.timezone_name}), SEND_FREQUENCY={config.send_frequency}"
        )


def scheduler_status_text() -> str:
    job = scheduler.get_job(SCHEDULER_JOB_ID)
    if not job:
        return "Scheduler is not configured."
    if not job.next_run_time:
        return "Scheduler configured, next run is pending."
    local_next = job.next_run_time.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    return f"Scheduler ready. Next run: {local_next}"


def render_page(title: str, body: str, active_page: str = ""):
    ui_language = get_ui_language()
    return render_template_string(
        BASE_TEMPLATE,
        title=title,
        body=body,
        auth_token=APP_AUTH_TOKEN,
        active_page=active_page,
        app_version=APP_VERSION,
        ui_language=ui_language,
    )


def test_gmail_login(gmail_address: str, gmail_app_password: str) -> Tuple[bool, str]:
    if not gmail_address or not gmail_app_password:
        return False, "GMAIL_ADDRESS/GMAIL_APP_PASSWORD is empty."
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
            smtp.login(gmail_address, "".join(gmail_app_password.split()))
        return True, "Gmail SMTP login success."
    except Exception as exc:
        return False, f"Gmail login failed: {safe_exception_text(exc)}"


def test_google_oauth_gmail(env_map: Dict[str, str]) -> Tuple[bool, str]:
    enabled = env_truthy(str(env_map.get("ENABLE_GOOGLE_OAUTH", "false")))
    use_for_gmail = env_truthy(str(env_map.get("GOOGLE_OAUTH_USE_FOR_GMAIL", "true")))
    if not enabled or not use_for_gmail:
        return False, "Google OAuth for Gmail is disabled."
    oauth_values = get_effective_google_oauth_values(env_map)
    client_id = str(oauth_values.get("client_id", "")).strip()
    client_secret = str(oauth_values.get("client_secret", "")).strip()
    refresh_token = resolve_secret_value(
        "GOOGLE_OAUTH_REFRESH_TOKEN",
        str(env_map.get("GOOGLE_OAUTH_REFRESH_TOKEN", "")),
    )
    if not client_id or not client_secret or not refresh_token:
        return False, "Google OAuth setup/connection is incomplete."
    try:
        access_token = refresh_google_oauth_access_token(client_id, client_secret, refresh_token)
        info = fetch_google_userinfo(access_token)
        email = str(info.get("email", "")).strip()
        if email:
            return True, f"Google OAuth token refresh success ({email})"
        return True, "Google OAuth token refresh success."
    except Exception as exc:
        return False, f"Google OAuth check failed: {safe_exception_text(exc)}"


def test_gemini_key(gemini_api_key: str, gemini_model: str) -> Tuple[bool, str]:
    if not gemini_api_key:
        return False, "GEMINI_API_KEY is empty."
    payload = {
        "contents": [{"role": "user", "parts": [{"text": "Return JSON: {\"ok\": true}"}]}],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
            "maxOutputTokens": 16,
        },
    }
    try:
        _, used_model = post_gemini_with_model_fallback(
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            payload=payload,
            timeout_seconds=30,
        )
        if used_model != gemini_model:
            return True, f"Gemini API call success (fallback model: {used_model})"
        return True, "Gemini API call success."
    except Exception as exc:
        return False, f"Gemini call failed: {safe_exception_text(exc)}"


def test_cerebras_key(
    cerebras_api_key: str,
    cerebras_model: str,
    cerebras_api_base: str,
) -> Tuple[bool, str]:
    if not cerebras_api_key:
        return False, "CEREBRAS_API_KEY is empty."
    base_url = (cerebras_api_base or CEREBRAS_API_BASE_DEFAULT).strip().rstrip("/")
    if not base_url:
        base_url = CEREBRAS_API_BASE_DEFAULT
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {cerebras_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": cerebras_model,
                "messages": [{"role": "user", "content": "Reply with JSON: {\"ok\": true}"}],
                "temperature": 0.0,
                "max_completion_tokens": 16,
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )
        response.raise_for_status()
        return True, "Cerebras API call success."
    except Exception as exc:
        return False, f"Cerebras call failed: {safe_exception_text(exc)}"


def test_semantic_scholar_key(semantic_api_key: str) -> Tuple[bool, str]:
    if not semantic_api_key:
        return False, "SEMANTIC_SCHOLAR_API_KEY is empty."
    try:
        response = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": "retina stroke prediction",
                "limit": 1,
                "fields": "paperId,title",
            },
            headers={"x-api-key": semantic_api_key},
            timeout=30,
        )
        response.raise_for_status()
        return True, "Semantic Scholar API call success."
    except Exception as exc:
        return False, f"Semantic Scholar call failed: {safe_exception_text(exc)}"


def test_google_scholar_key(google_scholar_api_key: str) -> Tuple[bool, str]:
    if not google_scholar_api_key:
        return False, "GOOGLE_SCHOLAR_API_KEY is empty."
    try:
        response = requests.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google_scholar",
                "q": "retina stroke prediction",
                "num": 1,
                "api_key": google_scholar_api_key,
            },
            timeout=30,
        )
        response.raise_for_status()
        return True, "Google Scholar (SerpAPI) call success."
    except Exception as exc:
        return False, f"Google Scholar (SerpAPI) call failed: {safe_exception_text(exc)}"


def build_settings_warnings(env_map: Dict[str, str]) -> List[str]:
    warnings: List[str] = []
    if env_truthy(str(env_map.get("ALLOW_INSECURE_REMOTE_WEB", "false"))):
        warnings.append(
            "ALLOW_INSECURE_REMOTE_WEB=true: remote exposure without TLS can leak keys/passwords."
        )
    if not env_truthy(str(env_map.get("USE_KEYRING", "true"))):
        warnings.append(
            "USE_KEYRING=false: secrets are stored in plaintext in .env."
        )
    elif not is_keyring_available():
        warnings.append(
            "USE_KEYRING=true but keyring backend is unavailable. Falling back to plaintext .env storage."
        )
    if env_truthy(str(env_map.get("ENABLE_GOOGLE_OAUTH", "false"))):
        oauth_values = get_effective_google_oauth_values(env_map)
        if not str(oauth_values.get("client_id", "")).strip():
            warnings.append(
                "ENABLE_GOOGLE_OAUTH=true but GOOGLE_OAUTH_CLIENT_ID is empty (or bundled OAuth client is missing)."
            )
        if not str(oauth_values.get("client_secret", "")).strip():
            warnings.append(
                "ENABLE_GOOGLE_OAUTH=true but GOOGLE_OAUTH_CLIENT_SECRET is empty (or bundled OAuth client is missing)."
            )
        if not resolve_secret_value(
            "GOOGLE_OAUTH_REFRESH_TOKEN",
            str(env_map.get("GOOGLE_OAUTH_REFRESH_TOKEN", "")),
        ):
            warnings.append("Google OAuth is not connected yet.")

    try:
        max_queries = int(str(env_map.get("MAX_SEARCH_QUERIES_PER_SOURCE", "4")).strip())
        if max_queries > 30:
            warnings.append(
                f"MAX_SEARCH_QUERIES_PER_SOURCE={max_queries}: API call volume may be excessive."
            )
    except ValueError:
        pass

    try:
        semantic_max = int(str(env_map.get("SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY", "20")).strip())
        if semantic_max > 50:
            warnings.append(
                f"SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY={semantic_max}: request volume/latency may increase."
            )
    except ValueError:
        pass

    try:
        llm_candidates = int(str(env_map.get("LLM_MAX_CANDIDATES", "30")).strip())
        if llm_candidates > 80:
            warnings.append("LLM_MAX_CANDIDATES above 80 is not recommended. Runtime cap is 80.")
        elif llm_candidates > 55:
            warnings.append(f"LLM_MAX_CANDIDATES={llm_candidates}: LLM cost may increase.")
    except ValueError:
        pass
    if env_truthy(str(env_map.get("ENABLE_GEMINI_ADVANCED_REASONING", "true"))):
        warnings.append("Advanced reasoning (Gemini 3.1 Pro) is enabled. Speed/cost may increase.")

    if not str(env_map.get("NCBI_API_KEY", "")).strip():
        warnings.append("NCBI_API_KEY is not set: PubMed throughput may be rate-limited.")

    if env_truthy(str(env_map.get("ENABLE_GOOGLE_SCHOLAR", "false"))):
        if not resolve_secret_value(
            "GOOGLE_SCHOLAR_API_KEY",
            str(env_map.get("GOOGLE_SCHOLAR_API_KEY", "")),
        ):
            warnings.append("ENABLE_GOOGLE_SCHOLAR=true but GOOGLE_SCHOLAR_API_KEY is empty.")

    return warnings


def register_windows_scheduled_task() -> Tuple[bool, str]:
    if os.name != "nt":
        return False, "Supported on Windows only."

    candidates = [
        get_runtime_base_dir() / "tools" / "register_task.ps1",
        get_runtime_base_dir().parent / "tools" / "register_task.ps1",
        get_runtime_base_dir() / "register_task.ps1",
        Path(__file__).resolve().parent / "register_task.ps1",
        Path("tools/register_task.ps1").resolve(),
    ]
    script_path = next((path for path in candidates if path.exists()), None)
    if not script_path:
        return False, "register_task.ps1 was not found."

    env_map = read_env_map()
    send_hour_raw = str(env_map.get("SEND_HOUR", "9")).strip()
    send_minute_raw = str(env_map.get("SEND_MINUTE", "0")).strip()
    try:
        send_hour = int(send_hour_raw) if send_hour_raw else 9
    except Exception:
        send_hour = 9
    try:
        send_minute = int(send_minute_raw) if send_minute_raw else 0
    except Exception:
        send_minute = 0
    internal_hour, internal_minute = compute_internal_schedule_time(send_hour, send_minute)
    run_at = f"{internal_hour:02d}:{internal_minute:02d}"
    project_dir = script_path.parent
    if project_dir.name.lower() == "tools":
        project_dir = project_dir.parent
    use_exe = (project_dir / "PaperDigest.exe").exists()

    command = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-TaskName",
        "PaperMorningDailyDigest",
        "-RunAt",
        run_at,
        "-ProjectDir",
        str(project_dir),
    ]
    if use_exe:
        command.append("-UseExe")

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except Exception as exc:
        return False, f"Task Scheduler registration failed to execute: {safe_exception_text(exc)}"

    output = (completed.stdout or "").strip()
    error = (completed.stderr or "").strip()
    if completed.returncode != 0:
        message = error or output or "Unknown error"
        return False, f"Registration failed: {message}"
    return (
        True,
        (output or "Windows Task Scheduler registration completed")
        + f" (user {send_hour:02d}:{send_minute:02d} -> internal {internal_hour:02d}:{internal_minute:02d})",
    )


@app.before_request
def verify_local_post_token():
    env_map = read_env_map()

    if should_force_setup(request.path, env_map):
        if request.path != url_for("setup"):
            return redirect(url_for("setup"))

    web_password = get_web_password(env_map)
    if web_password and not session.get(WEB_AUTH_SESSION_KEY):
        if (
            request.path != url_for("login")
            and not request.path.startswith("/static/")
            and not request.path.startswith("/assets/")
            and request.path != url_for("google_oauth_callback")
        ):
            if request.is_json or request.path.startswith("/jobs/"):
                return jsonify({"ok": False, "message": "Authentication required"}), 401
            return redirect(url_for("login", next=request.path))

    if request.method != "POST":
        return None

    if request.path == url_for("login"):
        return None

    token = request.headers.get("X-App-Token", "").strip()
    if not token:
        if request.is_json:
            payload = request.get_json(silent=True) or {}
            token = str(payload.get("app_token", "")).strip()
        else:
            token = request.form.get("app_token", "").strip()

    if token == APP_AUTH_TOKEN:
        return None

    if request.path.startswith("/jobs/") or request.path.startswith("/topics/") or request.is_json:
        return jsonify({"ok": False, "message": "Forbidden"}), 403
    return ("Forbidden", 403)


@app.route("/assets/logo", methods=["GET"])
def app_logo():
    candidates = [
        (get_runtime_base_dir().parent / "assets" / APP_LOGO_FILENAME).resolve(),
        (get_runtime_base_dir() / "assets" / APP_LOGO_FILENAME).resolve(),
        (get_runtime_base_dir() / APP_LOGO_FILENAME).resolve(),
        (Path("..") / "assets" / APP_LOGO_FILENAME).resolve(),
        (Path("assets") / APP_LOGO_FILENAME).resolve(),
        Path(APP_LOGO_FILENAME).resolve(),
    ]
    for logo_path in candidates:
        if logo_path.exists() and logo_path.is_file():
            return send_file(str(logo_path), mimetype="image/png", conditional=True)
    return ("Logo not found.", 404)

def normalize_topics_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    projects = payload.get("projects") if isinstance(payload, dict) else []
    topics = payload.get("topics") if isinstance(payload, dict) else []
    if not isinstance(projects, list):
        projects = []
    if not isinstance(topics, list):
        topics = []

    clean_projects: List[Dict[str, str]] = []
    for item in projects:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        context = str(item.get("context", "")).strip()
        if not name and not context:
            continue
        clean_projects.append({"name": name, "context": context})

    clean_topics: List[Dict[str, Any]] = []
    for item in topics:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        keywords = item.get("keywords", [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        if not isinstance(keywords, list):
            keywords = []
        keywords = [str(k).strip() for k in keywords if str(k).strip()]
        arxiv_query = str(item.get("arxiv_query", "")).strip()
        pubmed_query = str(item.get("pubmed_query", "")).strip()
        semantic_query = str(item.get("semantic_scholar_query", "")).strip()
        google_scholar_query = str(item.get("google_scholar_query", "")).strip()
        if not (name or keywords or arxiv_query or pubmed_query or semantic_query or google_scholar_query):
            continue
        clean_topics.append(
            {
                "name": name,
                "keywords": keywords,
                "arxiv_query": arxiv_query,
                "pubmed_query": pubmed_query,
                "semantic_scholar_query": semantic_query,
                "google_scholar_query": google_scholar_query,
            }
        )

    return {"projects": clean_projects, "topics": clean_topics}


def read_topics_payload(path: Path) -> Dict[str, Any]:
    if path.exists():
        text = path.read_text(encoding="utf-8-sig")
        return normalize_topics_payload(json.loads(text))
    template_candidates = [
        (get_runtime_base_dir() / "user_topics.template.json").resolve(),
        (get_runtime_base_dir() / "config" / "user_topics.template.json").resolve(),
        (get_runtime_base_dir().parent / "config" / "user_topics.template.json").resolve(),
        (Path("config") / "user_topics.template.json").resolve(),
        Path("user_topics.template.json").resolve(),
    ]
    template_path = next((candidate for candidate in template_candidates if candidate.exists()), None)
    if template_path is not None:
        text = template_path.read_text(encoding="utf-8-sig")
        return normalize_topics_payload(json.loads(text))
    return {"projects": [], "topics": []}


def has_configured_topic_queries(
    payload: Dict[str, Any],
    enable_semantic_scholar: bool = True,
    enable_google_scholar: bool = False,
) -> bool:
    topics = payload.get("topics", []) if isinstance(payload, dict) else []
    if not isinstance(topics, list):
        return False
    for item in topics:
        if not isinstance(item, dict):
            continue
        arxiv_query = str(item.get("arxiv_query", "")).strip()
        pubmed_query = str(item.get("pubmed_query", "")).strip()
        semantic_query = str(item.get("semantic_scholar_query", "")).strip()
        google_scholar_query = str(item.get("google_scholar_query", "")).strip()
        if arxiv_query or pubmed_query:
            return True
        if enable_semantic_scholar and semantic_query:
            return True
        if enable_google_scholar and google_scholar_query:
            return True
    return False


def read_log_tail(path: Path, max_lines: int = 400, max_chars: int = 200_000) -> str:
    if not path.exists():
        return "Log file has not been created yet."
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception as exc:
        return f"Failed to read log file: {exc}"
    if len(text) > max_chars:
        text = text[-max_chars:]
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return "\n".join(lines) if lines else "(empty log)"


def read_latest_preview_payload() -> Dict[str, Any]:
    preview_path = (get_default_data_dir() / "digest_preview.json").resolve()
    if not preview_path.exists():
        return {}
    try:
        payload = json.loads(preview_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def get_job_state_snapshot() -> Dict[str, Any]:
    with job_state_lock:
        return dict(job_state)


def update_job_state(**changes: Any) -> None:
    with job_state_lock:
        job_state.update(changes)


def start_background_job(kind: str) -> Tuple[bool, str]:
    if kind in {"dry_run", "send_now"}:
        env_map = read_env_map()
        topics_path = get_topics_path(env_map)
        topics_payload = read_topics_payload(topics_path)
        semantic_enabled = env_truthy(env_map.get("ENABLE_SEMANTIC_SCHOLAR", "true"))
        google_scholar_enabled = env_truthy(env_map.get("ENABLE_GOOGLE_SCHOLAR", "false"))
        has_queries = has_configured_topic_queries(
            topics_payload,
            enable_semantic_scholar=semantic_enabled,
            enable_google_scholar=google_scholar_enabled,
        )
        if not has_queries and kind == "dry_run":
            generated, message, topics_payload = maybe_generate_topics_from_projects(
                env_map=env_map,
                topics_path=topics_path,
                topics_payload=topics_payload,
            )
            if not generated:
                return False, message
            has_queries = has_configured_topic_queries(
                topics_payload,
                enable_semantic_scholar=semantic_enabled,
                enable_google_scholar=google_scholar_enabled,
            )
            if not has_queries:
                return False, "Generated topics do not contain valid search queries. Update Topic Editor and retry."

        if not has_queries:
            return (
                False,
                "No search queries are configured yet. Run Preview once first to auto-generate topics, "
                "or open Topic Editor and generate/save queries manually.",
            )

    if kind == "send_now":
        ok, message = check_send_cooldown()
        if not ok:
            return False, message

    with job_state_lock:
        if job_state.get("running"):
            return False, "Another task is already running."
        job_state.update(
            {
                "running": True,
                "kind": kind,
                "status": "Starting...",
                "progress": 1,
                "error": "",
                "started_at": now_iso(),
                "finished_at": "",
            }
        )

    threading.Thread(target=run_background_job, args=(kind,), daemon=True).start()
    return True, "Task started."


def run_background_job(kind: str) -> None:
    global last_dry_run_output, last_send_result

    def progress_cb(message: str, percent: int) -> None:
        update_job_state(status=message, progress=percent)

    try:
        if kind == "dry_run":
            progress_cb("Loading configuration...", 5)
            config = load_config(require_email_credentials=False)
            output = run_digest(
                config,
                dry_run=True,
                print_dry_run_output=False,
                progress_callback=progress_cb,
            )
            last_dry_run_output = output
            update_job_state(status="Preview generated.", progress=100)
        elif kind == "send_now":
            progress_cb("Loading configuration...", 5)
            config = load_config(require_email_credentials=True)
            output = run_digest(
                config,
                dry_run=False,
                force_send=True,
                print_dry_run_output=False,
                progress_callback=progress_cb,
            )
            last_send_result = output
            mark_send_now_executed()
            update_job_state(status="Send-now completed (advanced mode).", progress=100)
        elif kind == "reload_scheduler":
            progress_cb("Reloading scheduler...", 30)
            msg = refresh_scheduler()
            update_job_state(status=msg, progress=100)
        elif kind == "register_windows_task":
            progress_cb("Registering Windows Task Scheduler...", 30)
            ok, message = register_windows_scheduled_task()
            if not ok:
                raise RuntimeError(message)
            update_job_state(status=message, progress=100)
        else:
            raise ValueError(f"Unknown job kind: {kind}")
    except Exception as exc:
        logging.exception("Background job failed: %s", kind)
        update_job_state(error=safe_exception_text(exc), status="Task failed.")
    finally:
        update_job_state(running=False, finished_at=now_iso())


def call_gemini_for_topic_generation(
    projects: List[Dict[str, str]],
    gemini_api_key: str,
    gemini_model: str,
) -> Dict[str, Any]:
    project_json = json.dumps(projects, ensure_ascii=False)
    prompt = (
        "You are helping configure a medical AI paper alert assistant.\n"
        "For each project, generate one precise topic row with: name, keywords, arxiv_query, pubmed_query, semantic_scholar_query, google_scholar_query.\n"
        "Return ONLY JSON object with schema:\n"
        "{\n"
        '  "topics": [\n'
        "    {\n"
        '      "name": "...",\n'
        '      "keywords": ["..."],\n'
        '      "arxiv_query": "...",\n'
        '      "pubmed_query": "...",\n'
        '      "semantic_scholar_query": "...",\n'
        '      "google_scholar_query": "..."\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- create one topic per project\n"
        "- keyword list length: 6..12\n"
        "- arXiv query must use all: terms\n"
        "- PubMed query should use boolean and quoted phrases where useful\n"
        "- Semantic Scholar query should be concise plain-text research query\n"
        "- Google Scholar query should be concise plain-text research query\n"
        "- prioritize precision over recall\n"
        "- keep response machine-parseable JSON only\n\n"
        f"Projects JSON:\n{project_json}"
    )

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }

    body, used_model = post_gemini_with_model_fallback(
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        payload=payload,
        timeout_seconds=60,
    )
    if used_model != gemini_model:
        logging.info(
            "Topic generation Gemini model fallback applied: requested=%s used=%s",
            gemini_model,
            used_model,
        )
    candidates = body.get("candidates", [])
    if not candidates:
        raise ValueError("Gemini returned no candidates.")
    parts = candidates[0].get("content", {}).get("parts", [])
    llm_text = "\n".join(part.get("text", "") for part in parts if part.get("text"))
    parsed = parse_json_loose(llm_text)
    if not isinstance(parsed, dict):
        raise ValueError("Invalid Gemini response format.")
    return parsed


def call_cerebras_for_topic_generation(
    projects: List[Dict[str, str]],
    cerebras_api_key: str,
    cerebras_model: str,
    cerebras_api_base: str,
) -> Dict[str, Any]:
    project_json = json.dumps(projects, ensure_ascii=False)
    prompt = (
        "You are helping configure a medical AI paper alert assistant.\n"
        "For each project, generate one precise topic row with: name, keywords, arxiv_query, pubmed_query, semantic_scholar_query, google_scholar_query.\n"
        "Return ONLY JSON object with schema:\n"
        "{\n"
        '  "topics": [\n'
        "    {\n"
        '      "name": "...",\n'
        '      "keywords": ["..."],\n'
        '      "arxiv_query": "...",\n'
        '      "pubmed_query": "...",\n'
        '      "semantic_scholar_query": "...",\n'
        '      "google_scholar_query": "..."\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- create one topic per project\n"
        "- keyword list length: 6..12\n"
        "- arXiv query must use all: terms\n"
        "- PubMed query should use boolean and quoted phrases where useful\n"
        "- Semantic Scholar query should be concise plain-text research query\n"
        "- Google Scholar query should be concise plain-text research query\n"
        "- prioritize precision over recall\n"
        "- keep response machine-parseable JSON only\n\n"
        f"Projects JSON:\n{project_json}"
    )

    base_url = (cerebras_api_base or CEREBRAS_API_BASE_DEFAULT).strip().rstrip("/")
    if not base_url:
        base_url = CEREBRAS_API_BASE_DEFAULT
    response = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {cerebras_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": cerebras_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    response.raise_for_status()
    body = response.json()
    choices = body.get("choices", [])
    if not choices:
        raise ValueError("Cerebras returned no choices.")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        llm_text = "\n".join(
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("text")
        )
    else:
        llm_text = str(content or "")
    parsed = parse_json_loose(llm_text)
    if not isinstance(parsed, dict):
        raise ValueError("Invalid Cerebras response format.")
    return parsed


def call_llm_for_topic_generation(
    projects: List[Dict[str, str]],
    gemini_api_key: str,
    gemini_model: str,
    cerebras_api_key: str,
    cerebras_model: str,
    cerebras_api_base: str,
    enable_cerebras_fallback: bool,
) -> Dict[str, Any]:
    errors: List[str] = []

    if gemini_api_key:
        try:
            return call_gemini_for_topic_generation(projects, gemini_api_key, gemini_model)
        except Exception as exc:
            safe_error = safe_exception_text(exc)
            errors.append(f"Gemini failed: {safe_error}")
            logging.warning("Gemini topic generation failed. Trying Cerebras fallback if enabled: %s", safe_error)

    if enable_cerebras_fallback and cerebras_api_key:
        try:
            return call_cerebras_for_topic_generation(
                projects,
                cerebras_api_key,
                cerebras_model,
                cerebras_api_base,
            )
        except Exception as exc:
            safe_error = safe_exception_text(exc)
            errors.append(f"Cerebras failed: {safe_error}")
            logging.warning("Cerebras topic generation failed: %s", safe_error)

    if errors:
        raise RuntimeError("; ".join(errors))
    raise ValueError(
        "No LLM provider configured. Set GEMINI_API_KEY or enable Cerebras fallback with CEREBRAS_API_KEY."
    )


def sanitize_generated_topics(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_topics = payload.get("topics", []) if isinstance(payload, dict) else []
    if not isinstance(raw_topics, list):
        return []

    result: List[Dict[str, Any]] = []
    for item in raw_topics:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        keywords = item.get("keywords", [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        if not isinstance(keywords, list):
            keywords = []
        keywords = [str(k).strip() for k in keywords if str(k).strip()]
        keywords = list(dict.fromkeys(keywords))[:12]
        arxiv_query = str(item.get("arxiv_query", "")).strip()
        pubmed_query = str(item.get("pubmed_query", "")).strip()
        semantic_query = str(item.get("semantic_scholar_query", "")).strip()
        google_scholar_query = str(item.get("google_scholar_query", "")).strip()
        if not name:
            continue
        result.append(
            {
                "name": name,
                "keywords": keywords,
                "arxiv_query": arxiv_query,
                "pubmed_query": pubmed_query,
                "semantic_scholar_query": semantic_query,
                "google_scholar_query": google_scholar_query,
            }
        )
    return result

def build_home_body() -> str:
    env_map = read_env_map()
    oauth_values = get_effective_google_oauth_values(env_map)
    escaped_status = html.escape(scheduler_status_text())
    escaped_output = html.escape(last_dry_run_output) if last_dry_run_output else "No preview generated yet."
    preview_payload = read_latest_preview_payload()
    preview_rows_html = ""
    preview_papers = preview_payload.get("papers", []) if isinstance(preview_payload, dict) else []
    has_preview_html = bool(
        str(preview_payload.get("html_preview", "")).strip()
        if isinstance(preview_payload, dict)
        else ""
    )
    if isinstance(preview_papers, list) and preview_papers:
        rows: List[str] = []
        for idx, paper in enumerate(preview_papers[:5], start=1):
            if not isinstance(paper, dict):
                continue
            title = html.escape(str(paper.get("title", "") or "Untitled"))
            source = html.escape(str(paper.get("source", "") or "unknown"))
            score = html.escape(str(paper.get("score", "")))
            url = html.escape(str(paper.get("url", "") or ""), quote=True)
            if url:
                title_html = f'<a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>'
            else:
                title_html = title
            rows.append(
                "<div style='padding:10px 0; border-bottom:1px solid var(--card-border);'>"
                f"<div style='font-weight:600;'>#{idx} {title_html}</div>"
                f"<div class='small' style='margin-top:4px;'>Source: <b>{source}</b> · Score: <b>{score}</b></div>"
                "</div>"
            )
        preview_rows_html = "".join(rows)
    else:
        preview_rows_html = "<div class='small'>Run <b>Preview Now</b> to generate your first personalized digest.</div>"
    oauth_connected_email = str(env_map.get("GOOGLE_OAUTH_CONNECTED_EMAIL", "") or "").strip()
    oauth_enabled = env_truthy(str(env_map.get("ENABLE_GOOGLE_OAUTH", "false")))
    oauth_use_for_gmail = env_truthy(str(env_map.get("GOOGLE_OAUTH_USE_FOR_GMAIL", "true")))
    oauth_refresh_ready = bool(
        resolve_secret_value(
            "GOOGLE_OAUTH_REFRESH_TOKEN",
            str(env_map.get("GOOGLE_OAUTH_REFRESH_TOKEN", "")),
        )
    )
    oauth_client_ready = bool(
        str(oauth_values.get("client_id", "")).strip() and str(oauth_values.get("client_secret", "")).strip()
    )
    oauth_ready = oauth_enabled and oauth_use_for_gmail and oauth_client_ready and oauth_refresh_ready
    oauth_bundle_ready = bool(oauth_values.get("bundle_ready"))
    oauth_source = "Settings values"
    if oauth_values.get("using_bundled_client_id") or oauth_values.get("using_bundled_client_secret"):
        oauth_source = "Bundled distribution"
    if oauth_ready:
        oauth_badge_html = '<span class="badge badge-running">🟢 Connected</span>'
        oauth_message = "Google OAuth Gmail sending is enabled."
    elif oauth_client_ready:
        oauth_badge_html = '<span class="badge badge-idle">🟡 Sign-in required</span>'
        oauth_message = "OAuth client settings are ready. Complete Google sign-in to connect."
    else:
        oauth_badge_html = '<span class="badge badge-danger">🔴 Not configured</span>'
        oauth_message = "OAuth client information is missing. Provide settings values or a bundled client."
    if OAUTH_UI_ENABLED:
        oauth_controls_html = (
            f'<a class="btn btn-ghost" href="{url_for("google_oauth_start")}">Connect Google sign-in</a>'
            '<button type="button" class="btn-danger" onclick="disconnectGoogleOauth()">Disconnect</button>'
        )
        oauth_disabled_note = ""
    else:
        oauth_controls_html = ""
        oauth_disabled_note = ""
    oauth_card_style = "" if OAUTH_UI_ENABLED else 'style="display:none;"'
    send_frequency = str(env_map.get("SEND_FREQUENCY", "daily") or "daily").strip().lower()
    send_frequency_label = {
        "daily": "Daily",
        "every_3_days": "Every 3 days",
        "weekly": "Weekly (7 days)",
    }.get(send_frequency, send_frequency)

    body = """
    <div class="page-header">
      <h1>Dashboard</h1>
      <p>Preview-first workflow: generate a personalized digest preview first, then enable automation.</p>
    </div>

    <div class="card">
      <p class="card-title">Mode</p>
      <div class="small">
        <strong>Preview mode</strong> (recommended): no email required, generate digest preview now.<br/>
        <strong>Daily automation mode</strong>: enable scheduled delivery after preview quality is confirmed.
      </div>
    </div>

    <div class="card" style="display:flex; align-items:center; gap:10px; padding:14px 18px;">
      <span id="sched-icon" style="font-size:18px;">📅</span>
      <div>
        <span id="sched-text" style="font-size:13.5px; font-weight:500;">__SCHEDULER_STATUS__</span>
        <div class="small" style="margin-top:4px;">Send frequency: <b>__SEND_FREQUENCY__</b></div>
      </div>
    </div>

    <div class="card" __OAUTH_CARD_STYLE__>
      <p class="card-title">Google OAuth Status</p>
      <div class="status-panel">
        <div class="status-kv">
          <div class="kv-label">Connection Status</div>
          <div class="kv-value">__OAUTH_BADGE__</div>
        </div>
        <div class="status-kv">
          <div class="kv-label">Connected Account</div>
          <div class="kv-value">__OAUTH_EMAIL__</div>
        </div>
        <div class="status-kv">
          <div class="kv-label">Client Source</div>
          <div class="kv-value">__OAUTH_SOURCE__</div>
        </div>
      </div>
      <p class="small" style="margin-top:8px;">__OAUTH_MESSAGE__</p>
      <p class="small" style="margin-top:6px; color:var(--text-sub);">Bundled client status: __OAUTH_BUNDLE_READY__</p>
      <p class="small" style="margin-top:6px; color:var(--text-sub);">__OAUTH_DISABLED_NOTE__</p>
      <div class="button-row" style="margin-top:12px;">
        __OAUTH_CONTROLS_HTML__
      </div>
    </div>

    <div class="action-grid">
      <div class="action-card">
        <span class="action-icon">🔍</span>
        <span class="action-label">Preview Digest</span>
        <span class="action-desc">Runs collection/ranking and shows digest output without sending email.</span>
        <button id="btn-dry" class="btn-success" onclick="startJob('dry_run')">Preview Now</button>
      </div>
      <div class="action-card">
        <span class="action-icon">🧾</span>
        <span class="action-label">Open Email Preview</span>
        <span class="action-desc">Open the latest digest preview in a new browser tab.</span>
        <button id="btn-open-preview" class="btn-ghost" onclick="openPreviewTab()" __PREVIEW_BTN_DISABLED__>Open Preview Tab</button>
      </div>
    </div>

    <details class="card" style="margin-top:14px;">
      <summary style="cursor:pointer; font-weight:600;">Advanced automation controls (email/send scheduler)</summary>
      <div class="action-grid" style="margin-top:12px;">
        <div class="action-card">
          <span class="action-icon">📨</span>
          <span class="action-label">Send Now</span>
          <span class="action-desc">Send one real digest email immediately.</span>
          <button id="btn-send" onclick="startJob('send_now')">Send</button>
        </div>
        <div class="action-card">
          <span class="action-icon">🔄</span>
          <span class="action-label">Reload Scheduler</span>
          <span class="action-desc">Reload scheduler with updated send time/settings.</span>
          <button id="btn-reload" class="btn-ghost" onclick="startJob('reload_scheduler')">Reload</button>
        </div>
        <div class="action-card">
          <span class="action-icon">🪟</span>
          <span class="action-label">Windows Task</span>
          <span class="action-desc">Register a daily task in Windows Task Scheduler.</span>
          <button id="btn-task" class="btn-ghost" onclick="startJob('register_windows_task')">Register</button>
        </div>
      </div>
    </details>

    <div class="card">
      <p class="card-title">Task Status</p>
      <div class="status-panel">
        <div class="status-kv">
          <div class="kv-label">Status</div>
          <div class="kv-value" id="status-badge"><span class="badge badge-idle">⬜ Idle</span></div>
        </div>
        <div class="status-kv">
          <div class="kv-label">Started At</div>
          <div class="kv-value" id="status-started">—</div>
        </div>
        <div class="status-kv">
          <div class="kv-label">Finished At</div>
          <div class="kv-value" id="status-finished">—</div>
        </div>
      </div>
      <div class="progress-track">
        <div class="progress-fill" id="job-progress"></div>
      </div>
      <p id="job-message" style="margin:8px 0 0; font-size:13px; color:var(--text-sub);">No running task.</p>
      <p id="job-error" class="text-danger" style="margin:4px 0 0; font-size:13px;"></p>
    </div>

    <div class="card">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
        <p class="card-title" style="margin:0; border:none; padding:0;">Latest Preview Output</p>
        <button class="btn-ghost" onclick="toggleOutput()" id="btn-toggle" style="padding:4px 10px; font-size:12px;">Collapse ▲</button>
      </div>
      <div style="margin-bottom:10px;">__PREVIEW_CARDS__</div>
      <div id="output-wrap">
        <pre id="output-pre">__LAST_DRY_OUTPUT__</pre>
      </div>
    </div>

    <script>
      let outputVisible = true;
      let previewWindow = null;
      function toggleOutput() {
        const wrap = document.getElementById('output-wrap');
        const btn = document.getElementById('btn-toggle');
        outputVisible = !outputVisible;
        wrap.style.display = outputVisible ? '' : 'none';
        btn.textContent = outputVisible ? 'Collapse ▲' : 'Expand ▼';
      }

      function openPreviewTab() {
        window.open('__PREVIEW_URL__', 'paperMorningPreview');
      }

      const JOB_LABEL = { dry_run: 'Preview', send_now: 'Send Now', reload_scheduler: 'Reload Scheduler', register_windows_task: 'Windows Task Register', none: '' };

      async function fetchStatus() {
        try {
          const res = await fetch('__API_STATUS__');
          const data = await res.json();
          renderStatus(data);
        } catch (err) {
          document.getElementById('job-message').textContent = 'Failed to load job status.';
        }
      }

      function setButtonsDisabled(disabled) {
        ['btn-dry', 'btn-send', 'btn-reload', 'btn-task', 'btn-open-preview'].forEach(id => {
          const el = document.getElementById(id);
          if (el) {
            el.disabled = disabled;
          }
        });
      }

      function renderStatus(data) {
        const p = Math.max(0, Math.min(100, Number(data.progress || 0)));
        const running = Boolean(data.running);
        const hasError = Boolean(data.error);
        const kind = data.kind || 'none';
        document.getElementById('job-progress').style.width = p + '%';
        document.getElementById('status-started').textContent = data.started_at || '—';
        document.getElementById('status-finished').textContent = data.finished_at || '—';
        document.getElementById('job-message').textContent = data.status || '';
        document.getElementById('job-error').textContent = data.error || '';

        const badgeEl = document.getElementById('status-badge');
        if (running) {
          badgeEl.innerHTML = `<span class="badge badge-running">🔵 Running — ${JOB_LABEL[kind]}</span>`;
        } else if (hasError) {
          badgeEl.innerHTML = '<span class="badge badge-danger">🔴 Failed</span>';
        } else {
          badgeEl.innerHTML = '<span class="badge badge-idle">⬜ Idle</span>';
        }

        if (!running && !hasError && kind === 'dry_run' && previewWindow && !previewWindow.closed) {
          previewWindow.location.href = '__PREVIEW_URL__';
          previewWindow.focus();
          previewWindow = null;
        }
        setButtonsDisabled(running);
      }

      async function startJob(kind) {
        if (kind === 'dry_run') {
          try {
            previewWindow = window.open('about:blank', 'paperMorningPreview');
            if (previewWindow && previewWindow.document) {
              previewWindow.document.write('<!doctype html><html><head><title>Generating preview...</title></head><body style=\"font-family:sans-serif;padding:20px;\">Generating digest preview...<br/>This tab will update automatically when ready.</body></html>');
              previewWindow.document.close();
            }
          } catch (err) {
            previewWindow = null;
          }
        }
        try {
          const res = await fetch(`__API_START_BASE__/${kind}`, {
            method: 'POST',
            headers: { 'X-App-Token': window.APP_TOKEN || '' },
          });
          const data = await res.json();
          if (!res.ok) {
            alert(data.message || 'Failed to start task');
            return;
          }
          await fetchStatus();
        } catch (err) {
          alert('Failed to start task');
        }
      }

      async function disconnectGoogleOauth() {
        if (!confirm('Disconnect Google OAuth?')) {
          return;
        }
        try {
          const res = await fetch('__OAUTH_DISCONNECT_URL__', {
            method: 'POST',
            headers: { 'X-App-Token': window.APP_TOKEN || '' },
          });
          if (!res.ok) {
            alert('Failed to disconnect OAuth');
            return;
          }
          window.location.reload();
        } catch (err) {
          alert('Failed to disconnect OAuth');
        }
      }

      fetchStatus();
      setInterval(fetchStatus, 1200);
    </script>
    """

    return (
        body.replace("__SCHEDULER_STATUS__", escaped_status)
        .replace("__SEND_FREQUENCY__", html.escape(send_frequency_label))
        .replace("__LAST_DRY_OUTPUT__", escaped_output)
        .replace("__PREVIEW_CARDS__", preview_rows_html)
        .replace("__OAUTH_BADGE__", oauth_badge_html)
        .replace("__OAUTH_EMAIL__", html.escape(oauth_connected_email or "Not connected"))
        .replace("__OAUTH_SOURCE__", html.escape(oauth_source))
        .replace("__OAUTH_MESSAGE__", html.escape(oauth_message))
        .replace("__OAUTH_BUNDLE_READY__", "Available" if oauth_bundle_ready else "Not available")
        .replace("__OAUTH_DISABLED_NOTE__", html.escape(oauth_disabled_note))
        .replace("__OAUTH_CONTROLS_HTML__", oauth_controls_html)
        .replace("__OAUTH_CARD_STYLE__", oauth_card_style)
        .replace("__OAUTH_DISCONNECT_URL__", url_for("google_oauth_disconnect"))
        .replace("__API_STATUS__", url_for("jobs_status"))
        .replace("__PREVIEW_URL__", url_for("preview_latest"))
        .replace("__PREVIEW_BTN_DISABLED__", "" if has_preview_html else "disabled")
        .replace("__API_START_BASE__", "/jobs/start")
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    env_map = read_env_map()
    configured_password = get_web_password(env_map)
    if not configured_password:
        return redirect(url_for("home"))

    next_path = request.args.get("next", "").strip() or request.form.get("next", "").strip()
    if not next_path.startswith("/"):
        next_path = url_for("home")

    if request.method == "POST":
        submitted = request.form.get("password", "")
        if submitted == configured_password:
            session[WEB_AUTH_SESSION_KEY] = True
            return redirect(next_path)
        flash("Incorrect password.", "danger")

    body = f"""
    <div class="page-header">
      <h1>Login</h1>
      <p>WEB_PASSWORD is configured. Enter your password.</p>
    </div>
    <div class="card" style="max-width:420px;">
      <form method="post">
        <input type="hidden" name="next" value="{html.escape(next_path, quote=True)}" />
        <label style="display:block; margin-bottom:8px; font-weight:600;">Web console password</label>
        <input type="password" name="password" autocomplete="current-password" style="width:100%;" />
        <div style="margin-top:12px;">
          <button type="submit">Sign in</button>
        </div>
      </form>
    </div>
    """
    return render_page("Login", body, active_page="")


@app.route("/logout", methods=["GET"])
def logout():
    session.pop(WEB_AUTH_SESSION_KEY, None)
    return redirect(url_for("login"))


@app.route("/oauth/google/start", methods=["GET"])
def google_oauth_start():
    if not OAUTH_UI_ENABLED:
        flash("Google OAuth UI is disabled in this build. Use Gmail app password mode.", "danger")
        return redirect(url_for("settings"))
    env_map = read_env_map()
    oauth_values = get_effective_google_oauth_values(env_map)
    client_id = str(oauth_values.get("client_id", "")).strip()
    client_secret = str(oauth_values.get("client_secret", "")).strip()
    if not client_id or not client_secret:
        flash("Set Google OAuth Client ID/Secret first (or include a bundled OAuth client file).", "danger")
        return redirect(url_for("settings"))

    redirect_uri = get_google_oauth_redirect_uri(env_map, prefer_request=True)
    state = secrets.token_urlsafe(24)
    session[GOOGLE_OAUTH_STATE_SESSION_KEY] = state
    session[GOOGLE_OAUTH_REDIRECT_URI_SESSION_KEY] = redirect_uri

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_OAUTH_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return redirect(f"{GOOGLE_OAUTH_AUTH_URL}?{urlencode(params)}")


@app.route("/oauth/google/callback", methods=["GET"])
def google_oauth_callback():
    if not OAUTH_UI_ENABLED:
        flash("Google OAuth UI is disabled in this build. Use Gmail app password mode.", "danger")
        return redirect(url_for("settings"))
    error = request.args.get("error", "").strip()
    if error:
        flash(f"Google OAuth authentication failed: {error}", "danger")
        return redirect(url_for("settings"))

    returned_state = request.args.get("state", "").strip()
    expected_state = str(session.pop(GOOGLE_OAUTH_STATE_SESSION_KEY, "") or "").strip()
    if not returned_state or not expected_state or returned_state != expected_state:
        flash("Google OAuth state validation failed. Please try again.", "danger")
        return redirect(url_for("settings"))

    code = request.args.get("code", "").strip()
    if not code:
        flash("Google OAuth code is missing.", "danger")
        return redirect(url_for("settings"))

    env_map = read_env_map()
    oauth_values = get_effective_google_oauth_values(env_map)
    client_id = str(oauth_values.get("client_id", "")).strip()
    client_secret = str(oauth_values.get("client_secret", "")).strip()
    redirect_uri = str(
        session.pop(GOOGLE_OAUTH_REDIRECT_URI_SESSION_KEY, "")
        or get_google_oauth_redirect_uri(env_map, prefer_request=True)
    ).strip()
    if not client_id or not client_secret:
        flash("Google OAuth Client ID/Secret is not configured.", "danger")
        return redirect(url_for("settings"))
    try:
        token_payload = exchange_google_oauth_code(client_id, client_secret, code, redirect_uri)
        access_token = str(token_payload.get("access_token", "")).strip()
        new_refresh_token = str(token_payload.get("refresh_token", "")).strip()
        existing_refresh_token = resolve_secret_value(
            "GOOGLE_OAUTH_REFRESH_TOKEN",
            str(env_map.get("GOOGLE_OAUTH_REFRESH_TOKEN", "")),
        )
        refresh_token = new_refresh_token or existing_refresh_token
        if not refresh_token:
            raise ValueError(
                "No refresh_token was returned. Remove app access in your Google account and reconnect."
            )

        connected_email = ""
        if access_token:
            userinfo = fetch_google_userinfo(access_token)
            connected_email = str(userinfo.get("email", "")).strip()

        updated = dict(env_map)
        updated["ENABLE_GOOGLE_OAUTH"] = "true"
        updated["GOOGLE_OAUTH_USE_FOR_GMAIL"] = "true"
        updated["GOOGLE_OAUTH_REFRESH_TOKEN"] = refresh_token
        updated["GOOGLE_OAUTH_CONNECTED_EMAIL"] = connected_email
        if connected_email and not str(updated.get("GMAIL_ADDRESS", "")).strip():
            updated["GMAIL_ADDRESS"] = connected_email
        if connected_email and not str(updated.get("RECIPIENT_EMAIL", "")).strip():
            updated["RECIPIENT_EMAIL"] = connected_email
        write_env_map(updated)
        try:
            refresh_scheduler()
        except Exception as exc:
            logging.warning("Scheduler refresh skipped after Google OAuth connect: %s", safe_exception_text(exc))
        if connected_email:
            flash(f"Google account connected: {connected_email}", "ok")
        else:
            flash("Google account connected.", "ok")
    except Exception as exc:
        flash(f"Google OAuth connection failed: {safe_exception_text(exc)}", "danger")
    return redirect(url_for("settings"))


@app.route("/oauth/google/disconnect", methods=["POST"])
def google_oauth_disconnect():
    if not OAUTH_UI_ENABLED:
        flash("Google OAuth UI is disabled in this build.", "danger")
        return redirect(url_for("settings"))
    env_map = read_env_map()
    updated = dict(env_map)
    updated["ENABLE_GOOGLE_OAUTH"] = "false"
    updated["GOOGLE_OAUTH_USE_FOR_GMAIL"] = "false"
    updated["GOOGLE_OAUTH_REFRESH_TOKEN"] = ""
    updated["GOOGLE_OAUTH_CONNECTED_EMAIL"] = ""
    try:
        write_env_map(updated)
        flash("Google OAuth has been disconnected.", "ok")
    except Exception as exc:
        flash(f"Failed to disconnect Google OAuth: {safe_exception_text(exc)}", "danger")
    return redirect(url_for("settings"))


@app.route("/setup", methods=["GET", "POST"])
def setup():
    env_map = read_env_map()
    env_path = resolve_env_path()

    if request.method == "POST":
        updated = dict(env_map)
        selected_mode = str(request.form.get("ONBOARDING_MODE", "preview") or "preview").strip().lower()
        if selected_mode not in {"preview", "daily"}:
            selected_mode = "preview"
        updated["ONBOARDING_MODE"] = selected_mode
        basic_keys = [
            "ONBOARDING_MODE",
            "GMAIL_ADDRESS",
            "RECIPIENT_EMAIL",
            "TIMEZONE",
            "SEND_HOUR",
            "SEND_MINUTE",
            "SEND_FREQUENCY",
            "SEND_ANCHOR_DATE",
            "MAX_PAPERS",
            "OUTPUT_LANGUAGE",
            "WEB_PASSWORD",
            "ENABLE_LLM_AGENT",
            "ENABLE_GEMINI_ADVANCED_REASONING",
            "ENABLE_CEREBRAS_FALLBACK",
            "ENABLE_SEMANTIC_SCHOLAR",
            "ENABLE_GOOGLE_SCHOLAR",
            "ALLOW_INSECURE_REMOTE_WEB",
            "USE_KEYRING",
            "ENABLE_GOOGLE_OAUTH",
            "GOOGLE_OAUTH_USE_FOR_GMAIL",
            "GOOGLE_OAUTH_CLIENT_ID",
            "GOOGLE_OAUTH_REDIRECT_URI",
            "SEND_NOW_COOLDOWN_SECONDS",
            "SENT_HISTORY_DAYS",
            "NCBI_API_KEY",
            "SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY",
            "GOOGLE_SCHOLAR_MAX_RESULTS_PER_QUERY",
            "GEMINI_MODEL",
            "CEREBRAS_MODEL",
            "CEREBRAS_API_BASE",
            "PROJECTS_CONFIG_FILE",
        ]
        for key in basic_keys:
            if (not OAUTH_UI_ENABLED) and key in OAUTH_FORM_KEYS:
                continue
            if key in {
                "ENABLE_LLM_AGENT",
                "ENABLE_GEMINI_ADVANCED_REASONING",
                "ENABLE_CEREBRAS_FALLBACK",
                "ENABLE_SEMANTIC_SCHOLAR",
                "ENABLE_GOOGLE_SCHOLAR",
                "ALLOW_INSECURE_REMOTE_WEB",
                "USE_KEYRING",
                "ENABLE_GOOGLE_OAUTH",
                "GOOGLE_OAUTH_USE_FOR_GMAIL",
            }:
                updated[key] = "true" if request.form.get(key) == "on" else "false"
            else:
                updated[key] = request.form.get(key, "").strip()

        for secret_key in {
            "GMAIL_APP_PASSWORD",
            "GEMINI_API_KEY",
            "CEREBRAS_API_KEY",
            "SEMANTIC_SCHOLAR_API_KEY",
            "GOOGLE_SCHOLAR_API_KEY",
            "WEB_PASSWORD",
            "GOOGLE_OAUTH_CLIENT_SECRET",
            "GOOGLE_OAUTH_REFRESH_TOKEN",
        }:
            if (not OAUTH_UI_ENABLED) and secret_key in OAUTH_SECRET_FORM_KEYS:
                continue
            submitted = request.form.get(secret_key, "").strip()
            if secret_key == "GMAIL_APP_PASSWORD" and submitted:
                submitted = "".join(submitted.split())
            updated[secret_key] = submitted if submitted else env_map.get(secret_key, "")

        project_name = request.form.get("PRIMARY_PROJECT_NAME", "").strip()
        project_context = request.form.get("PRIMARY_PROJECT_CONTEXT", "").strip()
        project_keywords_raw = request.form.get("PRIMARY_PROJECT_KEYWORDS", "").strip()
        project_keywords = [part.strip() for part in project_keywords_raw.split(",") if part.strip()]
        project_payload = [{"name": project_name, "context": project_context, "keywords": project_keywords}]
        projects_config_path = get_projects_config_path(updated)
        project_form_failed = False

        project_errors = validate_projects(project_payload)
        if project_errors:
            flash(f"Project config validation failed: {'; '.join(project_errors)}", "danger")
            project_form_failed = True
        else:
            try:
                write_projects_config(projects_config_path, project_payload)
            except Exception as exc:
                flash(f"Failed to save projects config: {safe_exception_text(exc)}", "danger")
                project_form_failed = True

        if project_form_failed:
            env_map = updated
            env_map["_FORM_PRIMARY_PROJECT_NAME"] = project_name
            env_map["_FORM_PRIMARY_PROJECT_CONTEXT"] = project_context
            env_map["_FORM_PRIMARY_PROJECT_KEYWORDS"] = project_keywords_raw
            env_map["_FORM_PROJECTS_CONFIG_FILE"] = str(projects_config_path)
        else:
            topics_path = get_topics_path(updated)
            topics_payload = read_topics_payload(topics_path)
            topics_payload["projects"] = project_payload
            topics_path.parent.mkdir(parents=True, exist_ok=True)
            topics_path.write_text(json.dumps(topics_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            enforce_private_file_permissions(topics_path)

            updated["SETUP_WIZARD_COMPLETED"] = "true"
            try:
                write_env_map(updated)
                try:
                    refresh_scheduler()
                except Exception as exc:
                    logging.warning("Setup saved but scheduler reload skipped: %s", safe_exception_text(exc))
                if request.form.get("after_save") == "preview":
                    started, message = start_background_job("dry_run")
                    if started:
                        flash("Setup saved. Generating preview now.", "ok")
                    else:
                        flash(f"Setup saved, but preview did not start: {message}", "danger")
                else:
                    flash("Setup saved successfully.", "ok")
                return redirect(url_for("home"))
            except Exception as exc:
                flash(f"Failed to save setup: {safe_exception_text(exc)}", "danger")
                env_map = updated

    checked_llm = "checked" if env_truthy(env_map.get("ENABLE_LLM_AGENT", "true")) else ""
    checked_gemini_advanced = (
        "checked" if env_truthy(env_map.get("ENABLE_GEMINI_ADVANCED_REASONING", "true")) else ""
    )
    checked_cerebras = "checked" if env_truthy(env_map.get("ENABLE_CEREBRAS_FALLBACK", "true")) else ""
    checked_semantic = "checked" if env_truthy(env_map.get("ENABLE_SEMANTIC_SCHOLAR", "true")) else ""
    checked_google_scholar = "checked" if env_truthy(env_map.get("ENABLE_GOOGLE_SCHOLAR", "false")) else ""
    checked_remote = "checked" if env_truthy(env_map.get("ALLOW_INSECURE_REMOTE_WEB", "false")) else ""
    checked_keyring = "checked" if env_truthy(env_map.get("USE_KEYRING", "true")) else ""
    checked_google_oauth = "checked" if env_truthy(env_map.get("ENABLE_GOOGLE_OAUTH", "false")) else ""
    checked_google_oauth_gmail = (
        "checked" if env_truthy(env_map.get("GOOGLE_OAUTH_USE_FOR_GMAIL", "true")) else ""
    )
    oauth_defaults = get_effective_google_oauth_values(env_map)
    oauth_bundle_ready_text = "Available" if oauth_defaults.get("bundle_ready") else "Not available"
    oauth_source_text = "Settings values"
    if oauth_defaults.get("using_bundled_client_id") or oauth_defaults.get("using_bundled_client_secret"):
        oauth_source_text = "Bundled distribution"
    oauth_disabled_attr = "" if OAUTH_UI_ENABLED else "disabled"
    oauth_section_style = "" if OAUTH_UI_ENABLED else 'style="display:none;"'
    if OAUTH_UI_ENABLED:
        oauth_setup_connect_html = f'<a class="btn btn-ghost" href="{url_for("google_oauth_start")}">Connect Google sign-in</a>'
    else:
        oauth_setup_connect_html = ""
    selected_mode = str(env_map.get("ONBOARDING_MODE", "preview") or "preview").strip().lower()
    if selected_mode not in {"preview", "daily"}:
        selected_mode = "preview"
    projects_config_path = get_projects_config_path(env_map)
    projects_from_file, _ = read_projects_config(projects_config_path)
    primary_project = projects_from_file[0] if projects_from_file else {}
    form_name = str(env_map.get("_FORM_PRIMARY_PROJECT_NAME", "")).strip()
    form_context = str(env_map.get("_FORM_PRIMARY_PROJECT_CONTEXT", "")).strip()
    form_keywords = str(env_map.get("_FORM_PRIMARY_PROJECT_KEYWORDS", "")).strip()
    primary_project_name = form_name or str(primary_project.get("name", "")).strip()
    primary_project_context = form_context or str(primary_project.get("context", "")).strip()
    if form_keywords:
        primary_project_keywords = form_keywords
    else:
        keywords = primary_project.get("keywords", [])
        if isinstance(keywords, list):
            primary_project_keywords = ", ".join(str(item).strip() for item in keywords if str(item).strip())
        else:
            primary_project_keywords = ""
    send_hour_padded = str(env_map.get("SEND_HOUR", "9")).zfill(2)
    send_minute_padded = str(env_map.get("SEND_MINUTE", "0")).zfill(2)

    def esc(key: str) -> str:
        return html.escape(str(env_map.get(key, "")), quote=True)

    body = f"""
    <div class="page-header">
      <h1>Setup Wizard</h1>
      <p>Complete initial setup once. Settings file: <code>{html.escape(str(env_path))}</code></p>
    </div>

    <form method="post">
      <input type="hidden" name="app_token" value="{APP_AUTH_TOKEN}" />
      <input type="hidden" name="PROJECTS_CONFIG_FILE" value="{html.escape(str(projects_config_path), quote=True)}" />

      <div class="card">
        <p class="card-title">1) Mode</p>
        <div class="settings-row">
          <div class="settings-label"><strong>Onboarding mode</strong><small>Preview-first is recommended.</small></div>
          <select name="ONBOARDING_MODE" id="onboarding_mode" style="width:220px;">
            <option value="preview" {"selected" if selected_mode == "preview" else ""}>Preview mode (recommended)</option>
            <option value="daily" {"selected" if selected_mode == "daily" else ""}>Daily automation mode</option>
          </select>
        </div>
      </div>

      <div class="card">
        <p class="card-title">2) Project description (required)</p>
        <p class="small" style="margin:0 0 12px;">This is stored in tracked config <code>{html.escape(str(projects_config_path))}</code> and used to auto-generate search queries.</p>
        <div class="settings-grid">
          <div class="settings-row">
            <div class="settings-label"><strong>What are you working on?</strong><small>Project title</small></div>
            <input type="text" name="PRIMARY_PROJECT_NAME" value="{html.escape(primary_project_name, quote=True)}" placeholder="e.g., Endoscopy foundation model" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Project context</strong><small>Current goal, methods, and constraints</small></div>
            <textarea name="PRIMARY_PROJECT_CONTEXT" rows="4" placeholder="Describe your active research focus in plain English.">{html.escape(primary_project_context)}</textarea>
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Optional keywords</strong><small>Comma separated</small></div>
            <input type="text" name="PRIMARY_PROJECT_KEYWORDS" value="{html.escape(primary_project_keywords, quote=True)}" placeholder="e.g., colonoscopy, weak supervision, transformer" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Papers per digest</strong><small>MAX_PAPERS</small></div>
            <input type="number" min="1" max="50" name="MAX_PAPERS" value="{esc('MAX_PAPERS')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Summary output language</strong><small>OUTPUT_LANGUAGE — e.g., en, ko, ja, es, fr</small></div>
            <input type="text" name="OUTPUT_LANGUAGE" value="{esc('OUTPUT_LANGUAGE')}" style="width:120px;" />
          </div>
        </div>
      </div>

      <details class="card" {"open" if selected_mode == "daily" else ""}>
        <summary style="cursor:pointer; font-weight:600;">3) Automation + email transport (advanced)</summary>
        <p class="small" style="margin:10px 0 12px;">For Gmail authentication, complete either <strong>App Password</strong> or <strong>Google OAuth</strong>.</p>
        <div class="settings-grid">
          <div class="settings-row">
            <div class="settings-label"><strong>Gmail address</strong></div>
            <input type="text" name="GMAIL_ADDRESS" value="{esc('GMAIL_ADDRESS')}" placeholder="example@gmail.com" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Gmail app password</strong><small>16 characters. Optional if using OAuth. <a href="https://myaccount.google.com/apppasswords" target="_blank">🔗 Get app password</a>. Leave blank to keep the current value</small></div>
            <input type="password" name="GMAIL_APP_PASSWORD" value="" placeholder="xxxx xxxx xxxx xxxx" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Recipient email</strong></div>
            <input type="text" name="RECIPIENT_EMAIL" value="{esc('RECIPIENT_EMAIL')}" placeholder="recipient@example.com" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Timezone</strong></div>
            <input type="text" name="TIMEZONE" value="{esc('TIMEZONE')}" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Send time</strong></div>
            <div>
              <input type="time" id="setup_send_time" value="{send_hour_padded}:{send_minute_padded}" onchange="splitSetupTime(this.value)" style="width:140px;" />
              <input type="hidden" name="SEND_HOUR" id="setup_send_hour" value="{esc('SEND_HOUR')}" />
              <input type="hidden" name="SEND_MINUTE" id="setup_send_minute" value="{esc('SEND_MINUTE')}" />
            </div>
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Send frequency</strong><small>SEND_FREQUENCY</small></div>
            <select name="SEND_FREQUENCY" style="width:160px;">
              <option value="daily" {"selected" if env_map.get("SEND_FREQUENCY", "daily") == "daily" else ""}>Daily</option>
              <option value="every_3_days" {"selected" if env_map.get("SEND_FREQUENCY", "daily") == "every_3_days" else ""}>Every 3 days</option>
              <option value="weekly" {"selected" if env_map.get("SEND_FREQUENCY", "daily") == "weekly" else ""}>Weekly (7 days)</option>
            </select>
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Frequency anchor date</strong><small>SEND_ANCHOR_DATE (YYYY-MM-DD)</small></div>
            <input type="text" name="SEND_ANCHOR_DATE" value="{esc('SEND_ANCHOR_DATE')}" placeholder="2026-01-01" style="width:160px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Send Now cooldown (seconds)</strong><small>Recommended: 300</small></div>
            <input type="number" min="0" name="SEND_NOW_COOLDOWN_SECONDS" value="{esc('SEND_NOW_COOLDOWN_SECONDS')}" style="width:140px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Duplicate suppression retention</strong><small>sent_ids.json retention days</small></div>
            <input type="number" min="1" name="SENT_HISTORY_DAYS" value="{esc('SENT_HISTORY_DAYS')}" style="width:140px;" />
          </div>
        </div>
      </details>

      <div class="card">
        <p class="card-title">4) LLM/API (optional)</p>
        <p class="small" style="margin:0 0 12px;">Works in keyword-only fallback mode even without API keys.</p>
        <p class="small" style="margin:0 0 12px;" {oauth_section_style}>Bundled Google OAuth client: <strong>{oauth_bundle_ready_text}</strong> (current source: {html.escape(oauth_source_text)})</p>
        <p class="small" style="margin:0 0 12px;" {oauth_section_style}>OAuth is currently hidden in the default app-password-first path.</p>
        <div class="settings-grid">
          <div class="settings-row">
            <div class="settings-label"><strong>Enable LLM agent</strong></div>
            <input type="checkbox" name="ENABLE_LLM_AGENT" {checked_llm} />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Gemini API Key</strong><small><a href="https://aistudio.google.com/" target="_blank">🔗 How to create key</a></small></div>
            <input type="password" name="GEMINI_API_KEY" value="" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Gemini model</strong></div>
            <input type="text" name="GEMINI_MODEL" value="{esc('GEMINI_MODEL')}" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Enable advanced reasoning</strong><small>ENABLE_GEMINI_ADVANCED_REASONING — force Gemini 3.1 Pro</small></div>
            <input type="checkbox" name="ENABLE_GEMINI_ADVANCED_REASONING" {checked_gemini_advanced} />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Cerebras fallback</strong></div>
            <input type="checkbox" name="ENABLE_CEREBRAS_FALLBACK" {checked_cerebras} />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Cerebras API Key</strong><small><a href="https://cloud.cerebras.ai/" target="_blank">🔗 How to create key</a></small></div>
            <input type="password" name="CEREBRAS_API_KEY" value="" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Cerebras model</strong></div>
            <input type="text" name="CEREBRAS_MODEL" value="{esc('CEREBRAS_MODEL')}" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Cerebras API Base</strong></div>
            <input type="text" name="CEREBRAS_API_BASE" value="{esc('CEREBRAS_API_BASE')}" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Enable Semantic Scholar source</strong></div>
            <input type="checkbox" name="ENABLE_SEMANTIC_SCHOLAR" {checked_semantic} />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Semantic Scholar API Key</strong><small><a href="https://www.semanticscholar.org/product/api" target="_blank">🔗 How to create key</a></small></div>
            <input type="password" name="SEMANTIC_SCHOLAR_API_KEY" value="" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Semantic Scholar max results per query</strong></div>
            <input type="number" min="1" max="100" name="SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY" value="{esc('SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY')}" style="width:140px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Enable Google Scholar source</strong><small>SerpAPI-based</small></div>
            <input type="checkbox" name="ENABLE_GOOGLE_SCHOLAR" {checked_google_scholar} />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Google Scholar API Key</strong><small><a href="https://serpapi.com/" target="_blank">🔗 SerpAPI</a></small></div>
            <input type="password" name="GOOGLE_SCHOLAR_API_KEY" value="" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Google Scholar max results per query</strong><small>Recommended: 10-20</small></div>
            <input type="number" min="1" max="20" name="GOOGLE_SCHOLAR_MAX_RESULTS_PER_QUERY" value="{esc('GOOGLE_SCHOLAR_MAX_RESULTS_PER_QUERY')}" style="width:140px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>NCBI API key</strong><small>Improves PubMed throughput (recommended)</small></div>
            <input type="text" name="NCBI_API_KEY" value="{esc('NCBI_API_KEY')}" />
          </div>
          <div class="settings-row" {oauth_section_style}>
            <div class="settings-label"><strong>Enable Google OAuth</strong><small>Use Google sign-in instead of app password</small></div>
            <input type="checkbox" name="ENABLE_GOOGLE_OAUTH" {checked_google_oauth} {oauth_disabled_attr} />
          </div>
          <div class="settings-row" {oauth_section_style}>
            <div class="settings-label"><strong>Use OAuth for Gmail sending</strong><small>GOOGLE_OAUTH_USE_FOR_GMAIL</small></div>
            <input type="checkbox" name="GOOGLE_OAUTH_USE_FOR_GMAIL" {checked_google_oauth_gmail} {oauth_disabled_attr} />
          </div>
          <div class="settings-row" {oauth_section_style}>
            <div class="settings-label"><strong>Google OAuth Client ID</strong><small>Google Cloud OAuth client ID (can be blank if bundled client exists)</small></div>
            <input type="text" name="GOOGLE_OAUTH_CLIENT_ID" value="{esc('GOOGLE_OAUTH_CLIENT_ID')}" {oauth_disabled_attr} />
          </div>
          <div class="settings-row" {oauth_section_style}>
            <div class="settings-label"><strong>Google OAuth Client Secret</strong><small>Can be blank if bundled client exists. Leave blank to keep current value</small></div>
            <input type="password" name="GOOGLE_OAUTH_CLIENT_SECRET" value="" autocomplete="new-password" {oauth_disabled_attr} />
          </div>
          <div class="settings-row" {oauth_section_style}>
            <div class="settings-label"><strong>Google OAuth redirect URI</strong><small>Leave blank to auto-use current local UI callback URL</small></div>
            <input type="text" name="GOOGLE_OAUTH_REDIRECT_URI" value="{esc('GOOGLE_OAUTH_REDIRECT_URI')}" placeholder="http://127.0.0.1:5050/oauth/google/callback" {oauth_disabled_attr} />
          </div>
          <div class="settings-row" {oauth_section_style}>
            <div class="settings-label"><strong>Connection status</strong><small>{html.escape(str(env_map.get('GOOGLE_OAUTH_CONNECTED_EMAIL', '') or 'Not connected'))}</small></div>
            <div class="button-row">
              {oauth_setup_connect_html}
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <p class="card-title">5) Web security (optional)</p>
        <div class="settings-row">
          <div class="settings-label"><strong>Web console password</strong><small>Required for remote access (0.0.0.0)</small></div>
          <input type="password" name="WEB_PASSWORD" value="" autocomplete="new-password" />
        </div>
        <div class="settings-row">
          <div class="settings-label"><strong>Allow remote host (not recommended)</strong><small>ALLOW_INSECURE_REMOTE_WEB — allows remote access without HTTPS.</small></div>
          <input type="checkbox" name="ALLOW_INSECURE_REMOTE_WEB" {checked_remote} />
        </div>
        <div class="settings-row">
          <div class="settings-label"><strong>Store secrets in OS keyring</strong><small>USE_KEYRING — stores secrets in OS secure storage.</small></div>
          <input type="checkbox" name="USE_KEYRING" {checked_keyring} />
        </div>
      </div>

      <div class="card">
        <p class="card-title">6) Connectivity checks</p>
        <button type="button" class="btn-ghost" onclick="runHealthcheck()">Run connectivity checks</button>
        <pre id="healthcheck-result" style="margin-top:10px; white-space:pre-wrap;">Not run yet</pre>
      </div>

      <div class="gap-8">
        <button type="submit" name="after_save" value="preview">✅ Save and Preview Now</button>
        <button type="submit" name="after_save" value="save" class="btn-ghost">Save only</button>
      </div>
    </form>

    <script>
      function splitSetupTime(val) {{
        const parts = val.split(':');
        document.getElementById('setup_send_hour').value = parseInt(parts[0], 10);
        document.getElementById('setup_send_minute').value = parseInt(parts[1], 10);
      }}

      async function runHealthcheck() {{
        const box = document.getElementById('healthcheck-result');
        box.textContent = 'Running diagnostics...';
        try {{
          const res = await fetch('{url_for("setup_healthcheck")}', {{
            method: 'POST',
            headers: {{
              'Content-Type': 'application/json',
              'X-App-Token': window.APP_TOKEN || '',
            }},
            body: JSON.stringify({{ app_token: window.APP_TOKEN || '' }}),
          }});
          const data = await res.json();
          box.textContent = JSON.stringify(data, null, 2);
        }} catch (err) {{
          box.textContent = 'Diagnostics failed';
        }}
      }}
    </script>
    """
    return render_page("Setup Wizard", body, active_page="setup")


@app.route("/setup/healthcheck", methods=["POST"])
def setup_healthcheck():
    env_map = read_env_map()
    gmail_ok, gmail_msg = test_gmail_login(
        str(env_map.get("GMAIL_ADDRESS", "")).strip(),
        resolve_secret_value("GMAIL_APP_PASSWORD", str(env_map.get("GMAIL_APP_PASSWORD", "")).strip()),
    )
    gemini_ok, gemini_msg = test_gemini_key(
        resolve_secret_value("GEMINI_API_KEY", str(env_map.get("GEMINI_API_KEY", "")).strip()),
        get_effective_gemini_model(env_map),
    )
    cerebras_ok, cerebras_msg = test_cerebras_key(
        resolve_secret_value("CEREBRAS_API_KEY", str(env_map.get("CEREBRAS_API_KEY", "")).strip()),
        str(env_map.get("CEREBRAS_MODEL", "gpt-oss-120b")).strip() or "gpt-oss-120b",
        str(env_map.get("CEREBRAS_API_BASE", CEREBRAS_API_BASE_DEFAULT)).strip()
        or CEREBRAS_API_BASE_DEFAULT,
    )
    semantic_ok, semantic_msg = test_semantic_scholar_key(
        resolve_secret_value(
            "SEMANTIC_SCHOLAR_API_KEY",
            str(env_map.get("SEMANTIC_SCHOLAR_API_KEY", "")).strip(),
        )
    )
    google_scholar_ok, google_scholar_msg = test_google_scholar_key(
        resolve_secret_value(
            "GOOGLE_SCHOLAR_API_KEY",
            str(env_map.get("GOOGLE_SCHOLAR_API_KEY", "")).strip(),
        )
    )
    google_oauth_ok, google_oauth_msg = test_google_oauth_gmail(env_map)
    return jsonify(
        {
            "gmail": {"ok": gmail_ok, "message": gmail_msg},
            "google_oauth_gmail": {"ok": google_oauth_ok, "message": google_oauth_msg},
            "gemini": {"ok": gemini_ok, "message": gemini_msg},
            "cerebras": {"ok": cerebras_ok, "message": cerebras_msg},
            "semantic_scholar": {"ok": semantic_ok, "message": semantic_msg},
            "google_scholar": {"ok": google_scholar_ok, "message": google_scholar_msg},
        }
    )


@app.route("/")
def home():
    return render_page(APP_TITLE, build_home_body(), active_page="home")


@app.route("/preview/latest", methods=["GET"])
def preview_latest():
    payload = read_latest_preview_payload()
    html_preview = ""
    if isinstance(payload, dict):
        html_preview = str(payload.get("html_preview", "") or "").strip()
    if html_preview:
        return Response(html_preview, mimetype="text/html; charset=utf-8")

    fallback = """
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <title>Paper Morning Preview</title>
      </head>
      <body style="font-family:sans-serif;background:#f8fafc;padding:28px;color:#0f172a;">
        <h2 style="margin-top:0;">No preview available yet</h2>
        <p>Run <b>Preview Now</b> first, then open this tab again.</p>
        <p><a href="/">Back to Dashboard</a></p>
      </body>
    </html>
    """
    return Response(fallback, mimetype="text/html; charset=utf-8")


@app.route("/jobs/start/<kind>", methods=["POST"])
def jobs_start(kind: str):
    allowed = {"dry_run", "send_now", "reload_scheduler", "register_windows_task"}
    if kind not in allowed:
        return jsonify({"ok": False, "message": "Unknown job kind."}), 400

    ok, message = start_background_job(kind)
    code = 200 if ok else 409
    return jsonify({"ok": ok, "message": message}) , code


@app.route("/jobs/status", methods=["GET"])
def jobs_status():
    return jsonify(get_job_state_snapshot())


@app.route("/settings", methods=["GET", "POST"])
def settings():
    env_map = read_env_map()
    env_path = resolve_env_path()

    if request.method == "POST":
        updated = dict(env_map)
        for key in EXPECTED_ENV_KEYS:
            if (not OAUTH_UI_ENABLED) and key in OAUTH_FORM_KEYS:
                continue
            if key in {
                "ENABLE_LLM_AGENT",
                "ENABLE_GEMINI_ADVANCED_REASONING",
                "ENABLE_CEREBRAS_FALLBACK",
                "ENABLE_SEMANTIC_SCHOLAR",
                "ENABLE_GOOGLE_SCHOLAR",
                "ALLOW_INSECURE_REMOTE_WEB",
                "USE_KEYRING",
                "ENABLE_GOOGLE_OAUTH",
                "GOOGLE_OAUTH_USE_FOR_GMAIL",
            }:
                updated[key] = "true" if request.form.get(key) == "on" else "false"
            elif key in SECRET_ENV_KEYS:
                # Keep existing secret when left blank in UI.
                if (not OAUTH_UI_ENABLED) and key in OAUTH_SECRET_FORM_KEYS:
                    continue
                submitted = request.form.get(key, "").strip()
                if key == "GMAIL_APP_PASSWORD" and submitted:
                    submitted = "".join(submitted.split())
                updated[key] = submitted if submitted else env_map.get(key, "")
            else:
                updated[key] = (
                    request.form.get(key, "").strip() if key in request.form else env_map.get(key, "")
                )

        try:
            write_env_map(updated)
            message = "Settings saved."
            try:
                message += " " + refresh_scheduler()
            except Exception as exc:
                message += f" Scheduler reload failed: {safe_exception_text(exc)}"
            flash(message, "ok")
        except Exception as exc:
            flash(f"Failed to save settings: {safe_exception_text(exc)}", "danger")
        return redirect(url_for("settings"))

    checked = "checked" if env_truthy(env_map.get("ENABLE_LLM_AGENT", "false")) else ""
    gemini_advanced_checked = (
        "checked" if env_truthy(env_map.get("ENABLE_GEMINI_ADVANCED_REASONING", "true")) else ""
    )
    cerebras_checked = "checked" if env_truthy(env_map.get("ENABLE_CEREBRAS_FALLBACK", "false")) else ""
    semantic_checked = "checked" if env_truthy(env_map.get("ENABLE_SEMANTIC_SCHOLAR", "true")) else ""
    google_scholar_checked = "checked" if env_truthy(env_map.get("ENABLE_GOOGLE_SCHOLAR", "false")) else ""
    remote_checked = "checked" if env_truthy(env_map.get("ALLOW_INSECURE_REMOTE_WEB", "false")) else ""
    keyring_checked = "checked" if env_truthy(env_map.get("USE_KEYRING", "true")) else ""
    google_oauth_checked = "checked" if env_truthy(env_map.get("ENABLE_GOOGLE_OAUTH", "false")) else ""
    google_oauth_gmail_checked = (
        "checked" if env_truthy(env_map.get("GOOGLE_OAUTH_USE_FOR_GMAIL", "true")) else ""
    )
    oauth_defaults = get_effective_google_oauth_values(env_map)
    oauth_bundle_ready_text = "Available" if oauth_defaults.get("bundle_ready") else "Not available"
    oauth_source_text = "Settings values"
    if oauth_defaults.get("using_bundled_client_id") or oauth_defaults.get("using_bundled_client_secret"):
        oauth_source_text = "Bundled distribution"
    oauth_disabled_attr = "" if OAUTH_UI_ENABLED else "disabled"
    oauth_section_style = "" if OAUTH_UI_ENABLED else 'style="display:none;"'
    if OAUTH_UI_ENABLED:
        oauth_settings_controls_html = (
            f'<a class="btn btn-ghost" href="{url_for("google_oauth_start")}">Connect Google sign-in</a>'
            '<button type="button" class="btn-danger" onclick="disconnectGoogleOauth()">Disconnect</button>'
        )
    else:
        oauth_settings_controls_html = ""
    send_hour_padded = str(env_map.get("SEND_HOUR", "9")).zfill(2)
    send_minute_padded = str(env_map.get("SEND_MINUTE", "0")).zfill(2)

    def esc(key: str) -> str:
        return html.escape(env_map.get(key, ""), quote=True)

    warning_items = build_settings_warnings(env_map)
    warnings_html = ""
    if warning_items:
        rows = "".join(f"<li>{html.escape(item)}</li>" for item in warning_items)
        warnings_html = f"""
        <div class="card" style="border-color:#f59e0b;background:#fffbeb;">
          <p class="card-title" style="color:#92400e;">⚠️ Operational Warning</p>
          <ul style="margin:0;padding-left:18px;color:#92400e;line-height:1.7;">{rows}</ul>
        </div>
        """

    body = f"""
    <div class="page-header">
      <h1>Settings</h1>
      <p>Settings file path: <code>{html.escape(str(env_path))}</code></p>
      <p class="small">Remote access (`--host 0.0.0.0`) is blocked by default. Enable only for testing with `ALLOW_INSECURE_REMOTE_WEB=true` and `WEB_PASSWORD`.</p>
    </div>
    {warnings_html}

    <form method="post">
      <input type="hidden" name="app_token" value="{APP_AUTH_TOKEN}" />

      <div class="card">
        <p class="card-title">📧 Email Settings</p>
        <p class="small" style="margin:0 0 12px;" {oauth_section_style}>Bundled Google OAuth client: <strong>{oauth_bundle_ready_text}</strong> (Current source: {html.escape(oauth_source_text)})</p>
        <p class="small" style="margin:0 0 12px;" {oauth_section_style}>OAuth is currently hidden in the default app-password-first path.</p>
        <div class="settings-grid">
          <div class="settings-row">
            <div class="settings-label">
              <strong>Sender Gmail Address</strong>
              <small>GMAIL_ADDRESS</small>
            </div>
            <input type="text" name="GMAIL_ADDRESS" value="{esc('GMAIL_ADDRESS')}" placeholder="example@gmail.com" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Gmail App Password</strong>
              <small>Google app password (16 chars). Optional when OAuth is enabled. <a href="https://myaccount.google.com/apppasswords" target="_blank">🔗 How to create</a>. Leave blank to keep current value.</small>
            </div>
            <input type="password" name="GMAIL_APP_PASSWORD" value="" placeholder="xxxx xxxx xxxx xxxx" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Recipient Email</strong>
              <small>RECIPIENT_EMAIL — destination email for digest reports</small>
            </div>
            <input type="text" name="RECIPIENT_EMAIL" value="{esc('RECIPIENT_EMAIL')}" placeholder="recipient@example.com" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Web Console Password</strong>
              <small>WEB_PASSWORD — required for remote access (0.0.0.0). Leave blank to keep current value</small>
            </div>
            <input type="password" name="WEB_PASSWORD" value="" placeholder="Web console login password" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Allow Remote Host (Not Recommended)</strong>
              <small>ALLOW_INSECURE_REMOTE_WEB — allows remote access without HTTPS.</small>
            </div>
            <input type="checkbox" name="ALLOW_INSECURE_REMOTE_WEB" {remote_checked} />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Store Secrets in OS Keyring</strong>
              <small>USE_KEYRING — stores secrets in OS secure storage</small>
            </div>
            <input type="checkbox" name="USE_KEYRING" {keyring_checked} />
          </div>
          <div class="settings-row" {oauth_section_style}>
            <div class="settings-label">
              <strong>Enable Google OAuth</strong>
              <small>ENABLE_GOOGLE_OAUTH — connect Gmail without app password</small>
            </div>
            <input type="checkbox" name="ENABLE_GOOGLE_OAUTH" {google_oauth_checked} {oauth_disabled_attr} />
          </div>
          <div class="settings-row" {oauth_section_style}>
            <div class="settings-label">
              <strong>Use OAuth for Gmail Sending</strong>
              <small>GOOGLE_OAUTH_USE_FOR_GMAIL</small>
            </div>
            <input type="checkbox" name="GOOGLE_OAUTH_USE_FOR_GMAIL" {google_oauth_gmail_checked} {oauth_disabled_attr} />
          </div>
          <div class="settings-row" {oauth_section_style}>
            <div class="settings-label">
              <strong>Google OAuth Client ID</strong>
              <small>GOOGLE_OAUTH_CLIENT_ID (can be blank if bundled client is present)</small>
            </div>
            <input type="text" name="GOOGLE_OAUTH_CLIENT_ID" value="{esc('GOOGLE_OAUTH_CLIENT_ID')}" {oauth_disabled_attr} />
          </div>
          <div class="settings-row" {oauth_section_style}>
            <div class="settings-label">
              <strong>Google OAuth Client Secret</strong>
              <small>GOOGLE_OAUTH_CLIENT_SECRET — can be blank if bundled client is present. Leave blank to keep current value</small>
            </div>
            <input type="password" name="GOOGLE_OAUTH_CLIENT_SECRET" value="" autocomplete="new-password" {oauth_disabled_attr} />
          </div>
          <div class="settings-row" {oauth_section_style}>
            <div class="settings-label">
              <strong>Google OAuth redirect URI</strong>
              <small>GOOGLE_OAUTH_REDIRECT_URI — leave blank to auto-use current local UI URL</small>
            </div>
            <input type="text" name="GOOGLE_OAUTH_REDIRECT_URI" value="{esc('GOOGLE_OAUTH_REDIRECT_URI')}" placeholder="http://127.0.0.1:5050/oauth/google/callback" {oauth_disabled_attr} />
          </div>
          <div class="settings-row" {oauth_section_style}>
            <div class="settings-label">
              <strong>Connected Google Account</strong>
              <small>{html.escape(str(env_map.get('GOOGLE_OAUTH_CONNECTED_EMAIL', '') or 'Not connected'))}</small>
            </div>
            <div class="button-row">
              {oauth_settings_controls_html}
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <p class="card-title">⏰ Delivery Schedule</p>
        <div class="settings-grid">
          <div class="settings-row">
            <div class="settings-label">
              <strong>Timezone</strong>
              <small>TIMEZONE — example: America/New_York</small>
            </div>
            <input type="text" name="TIMEZONE" value="{esc('TIMEZONE')}" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Send Time</strong>
              <small>Local send time for your daily digest</small>
            </div>
            <div>
              <input type="time" id="send_time_picker" value="{send_hour_padded}:{send_minute_padded}" onchange="splitTime(this.value)" style="width:140px;" />
              <input type="hidden" name="SEND_HOUR" id="send_hour_hidden" value="{esc('SEND_HOUR')}" />
              <input type="hidden" name="SEND_MINUTE" id="send_minute_hidden" value="{esc('SEND_MINUTE')}" />
            </div>
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Send Frequency</strong>
              <small>SEND_FREQUENCY — daily / every_3_days / weekly</small>
            </div>
            <select name="SEND_FREQUENCY" style="width:180px;">
              <option value="daily" {"selected" if env_map.get("SEND_FREQUENCY", "daily") == "daily" else ""}>Daily</option>
              <option value="every_3_days" {"selected" if env_map.get("SEND_FREQUENCY", "daily") == "every_3_days" else ""}>Every 3 days</option>
              <option value="weekly" {"selected" if env_map.get("SEND_FREQUENCY", "daily") == "weekly" else ""}>Weekly (7 days)</option>
            </select>
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Frequency Anchor Date</strong>
              <small>SEND_ANCHOR_DATE — YYYY-MM-DD</small>
            </div>
            <input type="text" name="SEND_ANCHOR_DATE" value="{esc('SEND_ANCHOR_DATE')}" placeholder="2026-01-01" style="width:160px;" />
          </div>
        </div>
      </div>

      <div class="card">
        <p class="card-title">🔍 Search Parameters</p>
        <div class="settings-grid">
          <div class="settings-row">
            <div class="settings-label">
              <strong>Lookback Window (Hours)</strong>
              <small>LOOKBACK_HOURS — collect papers within the last N hours</small>
            </div>
            <input type="number" name="LOOKBACK_HOURS" min="1" value="{esc('LOOKBACK_HOURS')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Max Papers</strong>
              <small>MAX_PAPERS — max papers included in each digest</small>
            </div>
            <input type="number" name="MAX_PAPERS" min="1" value="{esc('MAX_PAPERS')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Minimum Relevance Score</strong>
              <small>MIN_RELEVANCE_SCORE — keyword-score filter when LLM is disabled</small>
            </div>
            <input type="text" name="MIN_RELEVANCE_SCORE" value="{esc('MIN_RELEVANCE_SCORE')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Max Results per arXiv Query</strong>
              <small>ARXIV_MAX_RESULTS_PER_QUERY</small>
            </div>
            <input type="number" name="ARXIV_MAX_RESULTS_PER_QUERY" min="1" value="{esc('ARXIV_MAX_RESULTS_PER_QUERY')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Max Results per PubMed Query</strong>
              <small>PUBMED_MAX_IDS_PER_QUERY</small>
            </div>
            <input type="number" name="PUBMED_MAX_IDS_PER_QUERY" min="1" value="{esc('PUBMED_MAX_IDS_PER_QUERY')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Enable Semantic Scholar Source</strong>
              <small>ENABLE_SEMANTIC_SCHOLAR</small>
            </div>
            <input type="checkbox" name="ENABLE_SEMANTIC_SCHOLAR" {semantic_checked} />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Enable Google Scholar Source</strong>
              <small>ENABLE_GOOGLE_SCHOLAR (SerpAPI based)</small>
            </div>
            <input type="checkbox" name="ENABLE_GOOGLE_SCHOLAR" {google_scholar_checked} />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Max Results per Semantic Scholar Query</strong>
              <small>SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY</small>
            </div>
            <input type="number" name="SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY" min="1" max="100" value="{esc('SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Max Results per Google Scholar Query</strong>
              <small>GOOGLE_SCHOLAR_MAX_RESULTS_PER_QUERY (recommended: 10-20)</small>
            </div>
            <input type="number" name="GOOGLE_SCHOLAR_MAX_RESULTS_PER_QUERY" min="1" max="20" value="{esc('GOOGLE_SCHOLAR_MAX_RESULTS_PER_QUERY')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Max Search Queries per Source</strong>
              <small>MAX_SEARCH_QUERIES_PER_SOURCE</small>
            </div>
            <input type="number" name="MAX_SEARCH_QUERIES_PER_SOURCE" min="1" value="{esc('MAX_SEARCH_QUERIES_PER_SOURCE')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Send Now Cooldown (seconds)</strong>
              <small>SEND_NOW_COOLDOWN_SECONDS — prevents repeated manual sends</small>
            </div>
            <input type="number" name="SEND_NOW_COOLDOWN_SECONDS" min="0" value="{esc('SEND_NOW_COOLDOWN_SECONDS')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Duplicate-Send Retention Days</strong>
              <small>SENT_HISTORY_DAYS — suppress already-sent paper IDs for this many days</small>
            </div>
            <input type="number" name="SENT_HISTORY_DAYS" min="1" value="{esc('SENT_HISTORY_DAYS')}" style="width:120px;" />
          </div>
        </div>
      </div>

      <div class="card">
        <p class="card-title">🤖 LLM / Gemini / Cerebras Settings</p>
        <p class="small" style="margin:0 0 12px;">Runs in keyword-based fallback mode when API keys are missing or LLM calls fail.</p>
        <div class="settings-grid">
          <div class="settings-row">
            <div class="settings-label">
              <strong>Enable LLM Agent</strong>
              <small>ENABLE_LLM_AGENT — automatic relevance scoring via LLM</small>
            </div>
            <input type="checkbox" name="ENABLE_LLM_AGENT" {checked} />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Gemini API Key</strong>
              <small><a href="https://aistudio.google.com/" target="_blank">🔗 How to create</a>. Leave blank to keep current value.</small>
            </div>
            <input type="password" name="GEMINI_API_KEY" value="" placeholder="Key generated from AI Studio" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Gemini Model</strong>
              <small>GEMINI_MODEL — default: gemini-3.1-flash</small>
            </div>
            <input type="text" name="GEMINI_MODEL" value="{esc('GEMINI_MODEL')}" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Summary Output Language</strong>
              <small>OUTPUT_LANGUAGE — e.g., en, ko, ja, es, fr</small>
            </div>
            <input type="text" name="OUTPUT_LANGUAGE" value="{esc('OUTPUT_LANGUAGE')}" style="width:140px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Enable Advanced Reasoning</strong>
              <small>ENABLE_GEMINI_ADVANCED_REASONING — use Gemini 3.1 Pro when enabled</small>
            </div>
            <input type="checkbox" name="ENABLE_GEMINI_ADVANCED_REASONING" {gemini_advanced_checked} />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Enable Cerebras Fallback</strong>
              <small>ENABLE_CEREBRAS_FALLBACK — auto fallback when Gemini fails</small>
            </div>
            <input type="checkbox" name="ENABLE_CEREBRAS_FALLBACK" {cerebras_checked} />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Cerebras API Key</strong>
              <small><a href="https://cloud.cerebras.ai/" target="_blank">🔗 How to create</a>. Leave blank to keep current value.</small>
            </div>
            <input type="password" name="CEREBRAS_API_KEY" value="" placeholder="Cerebras API Key" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Cerebras Model</strong>
              <small>CEREBRAS_MODEL — e.g., gpt-oss-120b</small>
            </div>
            <input type="text" name="CEREBRAS_MODEL" value="{esc('CEREBRAS_MODEL')}" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Cerebras API Base</strong>
              <small>CEREBRAS_API_BASE — keep default unless needed</small>
            </div>
            <input type="text" name="CEREBRAS_API_BASE" value="{esc('CEREBRAS_API_BASE')}" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Semantic Scholar API Key</strong>
              <small><a href="https://www.semanticscholar.org/product/api" target="_blank">🔗 How to create</a>. Leave blank to keep current value.</small>
            </div>
            <input type="password" name="SEMANTIC_SCHOLAR_API_KEY" value="" placeholder="Semantic Scholar API Key" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Google Scholar API Key</strong>
              <small><a href="https://serpapi.com/" target="_blank">🔗 SerpAPI</a>. Leave blank to keep current value.</small>
            </div>
            <input type="password" name="GOOGLE_SCHOLAR_API_KEY" value="" placeholder="SerpAPI Key" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Gemini Max Papers</strong>
              <small>GEMINI_MAX_PAPERS</small>
            </div>
            <input type="number" name="GEMINI_MAX_PAPERS" min="1" value="{esc('GEMINI_MAX_PAPERS')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>LLM Relevance Threshold</strong>
              <small>LLM_RELEVANCE_THRESHOLD — include papers at or above this score</small>
            </div>
            <input type="number" step="0.1" name="LLM_RELEVANCE_THRESHOLD" min="1" max="10" value="{esc('LLM_RELEVANCE_THRESHOLD')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>LLM Batch Size</strong>
              <small>LLM_BATCH_SIZE</small>
            </div>
            <input type="number" name="LLM_BATCH_SIZE" min="1" value="{esc('LLM_BATCH_SIZE')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>LLM Max Candidates</strong>
              <small>LLM_MAX_CANDIDATES — default 30, max 80 (nonlinear expansion for longer frequencies)</small>
            </div>
            <input type="number" name="LLM_MAX_CANDIDATES" min="1" max="80" value="{esc('LLM_MAX_CANDIDATES')}" style="width:120px;" />
          </div>
        </div>
      </div>

      <div class="card">
        <p class="card-title">📁 Misc</p>
        <div class="settings-grid">
          <div class="settings-row">
            <div class="settings-label">
              <strong>NCBI API key</strong>
              <small>NCBI_API_KEY — recommended to stabilize PubMed throughput</small>
            </div>
            <input type="text" name="NCBI_API_KEY" value="{esc('NCBI_API_KEY')}" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Topics File Path</strong>
              <small>USER_TOPICS_FILE</small>
            </div>
            <input type="text" name="USER_TOPICS_FILE" value="{esc('USER_TOPICS_FILE')}" />
          </div>
        </div>
      </div>

      <div class="gap-8" style="padding:4px 0 8px;">
        <button type="submit">💾 Save</button>
        <span class="small">Scheduler auto-reloads after save.</span>
      </div>
    </form>

    <script>
      function splitTime(val) {{
        const parts = val.split(':');
        document.getElementById('send_hour_hidden').value = parseInt(parts[0], 10);
        document.getElementById('send_minute_hidden').value = parseInt(parts[1], 10);
      }}

      async function disconnectGoogleOauth() {{
        if (!confirm('Disconnect Google OAuth?')) return;
        const res = await fetch('{url_for("google_oauth_disconnect")}', {{
          method: 'POST',
          headers: {{ 'X-App-Token': window.APP_TOKEN || '' }},
        }});
        if (!res.ok) {{
          alert('Failed to disconnect');
          return;
        }}
        window.location.reload();
      }}
    </script>
    """
    return render_page("Settings", body, active_page="settings")

@app.route("/topics", methods=["GET"])
def topics():
    env_map = read_env_map()
    topics_path = get_topics_path(env_map)
    payload = read_topics_payload(topics_path)
    initial_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    body = """
    <div class="page-header">
      <h1>Topic Editor</h1>
      <p>Enter project context, click <b>Generate Keyword / Query</b>, then review and save.</p>
      <p class="small" style="margin-top:4px;">Saved queries are reused in daily runs as-is. (No automatic regeneration)</p>
      <p class="small" style="margin-top:4px;">Current file: <code>__TOPICS_PATH__</code></p>
    </div>

    <div class="card">
      <h3>1) Projects</h3>
      <table>
        <thead><tr><th style="width:28%;">Project Name</th><th>Context</th><th style="width:80px;">Action</th></tr></thead>
        <tbody id="projects-body"></tbody>
      </table>
      <div style="margin-top:10px;"><button type="button" onclick="addProjectRow()">+ Add Project</button></div>
    </div>

    <div class="card">
      <h3>2) Topics / Queries</h3>
      <div class="button-row" style="margin-bottom:10px;">
        <button type="button" id="btn-generate" class="btn-success" onclick="generateTopics()">Generate Keyword / Query</button>
        <span id="generate-status" class="small"></span>
      </div>
      <table>
        <thead>
          <tr>
            <th style="width:12%;">Topic Name</th>
            <th style="width:16%;">Keywords (comma separated)</th>
            <th style="width:18%;">arXiv Query</th>
            <th style="width:18%;">PubMed Query</th>
            <th style="width:18%;">Semantic Scholar Query</th>
            <th style="width:18%;">Google Scholar Query</th>
            <th style="width:80px;">Action</th>
          </tr>
        </thead>
        <tbody id="topics-body"></tbody>
      </table>
      <div style="margin-top:10px;"><button type="button" onclick="addTopicRow()">+ Add Topic</button></div>
    </div>

    <div style="position:sticky; bottom:0; background:rgba(244,245,247,0.95);
                backdrop-filter:blur(6px); border-top:1px solid var(--card-border);
                padding:12px 0; display:flex; gap:10px; align-items:center; z-index:50;">
      <button type="button" onclick="if (preparePayloadBeforeSave()) document.getElementById('topics-save-form').submit();">
        💾 Save Topics
      </button>
      <span class="small">Page reloads after save.</span>
    </div>
    <form id="topics-save-form" method="post" action="__TOPICS_SAVE_URL__">
      <input type="hidden" name="app_token" value="__APP_TOKEN__" />
      <input type="hidden" id="payload_json" name="payload_json" />
    </form>

    <script>
      const initialPayload = __INITIAL_PAYLOAD__;
      let projects = Array.isArray(initialPayload.projects) ? initialPayload.projects : [];
      let topics = Array.isArray(initialPayload.topics) ? initialPayload.topics : [];

      function escHtml(value) {
        return String(value || '')
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;')
          .replace(/'/g, '&#39;');
      }

      function renderProjects() {
        const tbody = document.getElementById('projects-body');
        tbody.innerHTML = '';
        projects.forEach((row, idx) => {
          tbody.insertAdjacentHTML('beforeend', `
            <tr>
              <td><input type="text" value="${escHtml(row.name || '')}" oninput="projects[${idx}].name=this.value" /></td>
              <td><input type="text" value="${escHtml(row.context || '')}" oninput="projects[${idx}].context=this.value" /></td>
              <td><button type="button" class="btn-danger" onclick="removeProjectRow(${idx})">Delete</button></td>
            </tr>
          `);
        });
      }

      function addProjectRow() {
        projects.push({ name: '', context: '' });
        renderProjects();
      }

      function removeProjectRow(idx) {
        projects.splice(idx, 1);
        renderProjects();
      }

      function topicKeywordsToText(value) {
        if (Array.isArray(value)) {
          return value.join(', ');
        }
        return String(value || '');
      }

      function renderTopics() {
        const tbody = document.getElementById('topics-body');
        tbody.innerHTML = '';
        topics.forEach((row, idx) => {
          tbody.insertAdjacentHTML('beforeend', `
            <tr>
              <td><input type="text" value="${escHtml(row.name || '')}" oninput="topics[${idx}].name=this.value" /></td>
              <td><textarea style="min-height:70px;" oninput="topics[${idx}].keywords=this.value">${escHtml(topicKeywordsToText(row.keywords))}</textarea></td>
              <td><textarea style="min-height:70px;" oninput="topics[${idx}].arxiv_query=this.value">${escHtml(row.arxiv_query || '')}</textarea></td>
              <td><textarea style="min-height:70px;" oninput="topics[${idx}].pubmed_query=this.value">${escHtml(row.pubmed_query || '')}</textarea></td>
              <td><textarea style="min-height:70px;" oninput="topics[${idx}].semantic_scholar_query=this.value">${escHtml(row.semantic_scholar_query || '')}</textarea></td>
              <td><textarea style="min-height:70px;" oninput="topics[${idx}].google_scholar_query=this.value">${escHtml(row.google_scholar_query || '')}</textarea></td>
              <td><button type="button" class="btn-danger" onclick="removeTopicRow(${idx})">Delete</button></td>
            </tr>
          `);
        });
      }

      function addTopicRow() {
        topics.push({ name: '', keywords: '', arxiv_query: '', pubmed_query: '', semantic_scholar_query: '', google_scholar_query: '' });
        renderTopics();
      }

      function removeTopicRow(idx) {
        topics.splice(idx, 1);
        renderTopics();
      }

      function normalizedProjects() {
        return projects
          .map(p => ({ name: (p.name || '').trim(), context: (p.context || '').trim() }))
          .filter(p => p.name || p.context);
      }

      function normalizedTopics() {
        return topics
          .map(t => {
            const keywordsText = Array.isArray(t.keywords) ? t.keywords.join(',') : (t.keywords || '');
            const keywords = String(keywordsText)
              .split(',')
              .map(x => x.trim())
              .filter(Boolean);
            return {
              name: (t.name || '').trim(),
              keywords,
              arxiv_query: (t.arxiv_query || '').trim(),
              pubmed_query: (t.pubmed_query || '').trim(),
              semantic_scholar_query: (t.semantic_scholar_query || '').trim(),
              google_scholar_query: (t.google_scholar_query || '').trim(),
            };
          })
          .filter(t => t.name || t.keywords.length || t.arxiv_query || t.pubmed_query || t.semantic_scholar_query || t.google_scholar_query);
      }

      async function generateTopics() {
        const projectsPayload = normalizedProjects();
        if (projectsPayload.length === 0) {
          alert('Please add at least one project first.');
          return;
        }

        const btn = document.getElementById('btn-generate');
        const status = document.getElementById('generate-status');
        const originalLabel = btn.textContent;
        btn.disabled = true;
        btn.textContent = '🔄 Generating...';
        status.innerText = 'Generating keyword/query with LLM...';

        try {
          const res = await fetch('__TOPICS_GENERATE_URL__', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-App-Token': window.APP_TOKEN || '',
            },
            body: JSON.stringify({ app_token: window.APP_TOKEN || '', projects: projectsPayload }),
          });
          const data = await res.json();
          if (!res.ok) {
            throw new Error(data.message || 'Generation failed');
          }
          topics = Array.isArray(data.topics) ? data.topics : [];
          renderTopics();
          status.innerText = `Generated: ${topics.length} topics`;
        } catch (err) {
          status.innerText = 'Generation failed';
          alert(err.message || 'Generation failed');
        } finally {
          btn.disabled = false;
          btn.textContent = originalLabel;
        }
      }

      function preparePayloadBeforeSave() {
        const payload = {
          projects: normalizedProjects(),
          topics: normalizedTopics(),
        };
        if (payload.projects.length === 0 && payload.topics.length === 0) {
          alert('At least one of projects or topics is required.');
          return false;
        }
        document.getElementById('payload_json').value = JSON.stringify(payload, null, 2);
        return true;
      }

      if (projects.length === 0) addProjectRow();
      else renderProjects();

      if (topics.length === 0) addTopicRow();
      else renderTopics();
    </script>
    """

    body = (
        body.replace("__TOPICS_PATH__", html.escape(str(topics_path)))
        .replace("__TOPICS_SAVE_URL__", url_for("topics_save"))
        .replace("__TOPICS_GENERATE_URL__", url_for("topics_generate"))
        .replace("__APP_TOKEN__", APP_AUTH_TOKEN)
        .replace("__INITIAL_PAYLOAD__", initial_json)
    )
    return render_page("Topic Editor", body, active_page="topics")


@app.route("/topics/save", methods=["POST"])
def topics_save():
    env_map = read_env_map()
    topics_path = get_topics_path(env_map)

    raw = request.form.get("payload_json", "").strip()
    try:
        payload = normalize_topics_payload(json.loads(raw))
        has_projects = len(payload.get("projects", [])) > 0
        has_topics = len(payload.get("topics", [])) > 0
        if not (has_projects or has_topics):
            raise ValueError("At least one project or topic is required.")
        topics_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        flash(f"Saved: {topics_path}", "ok")
    except Exception as exc:
        flash(f"Failed to save topics: {safe_exception_text(exc)}", "danger")
    return redirect(url_for("topics"))


@app.route("/topics/generate", methods=["POST"])
def topics_generate():
    req = request.get_json(silent=True) or {}
    projects = req.get("projects", [])
    if not isinstance(projects, list):
        return jsonify({"message": "Invalid projects payload."}), 400

    cleaned_projects: List[Dict[str, str]] = []
    for item in projects:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        context = str(item.get("context", "")).strip()
        if not (name or context):
            continue
        cleaned_projects.append({"name": name, "context": context})

    if not cleaned_projects:
        return jsonify({"message": "At least one project is required."}), 400

    env_map = read_env_map()
    gemini_api_key = resolve_secret_value("GEMINI_API_KEY", env_map.get("GEMINI_API_KEY", "").strip())
    gemini_model = get_effective_gemini_model(env_map)
    enable_cerebras_fallback = env_truthy(env_map.get("ENABLE_CEREBRAS_FALLBACK", "true"))
    cerebras_api_key = resolve_secret_value(
        "CEREBRAS_API_KEY",
        env_map.get("CEREBRAS_API_KEY", "").strip(),
    )
    cerebras_model = env_map.get("CEREBRAS_MODEL", "gpt-oss-120b").strip() or "gpt-oss-120b"
    cerebras_api_base = (
        env_map.get("CEREBRAS_API_BASE", CEREBRAS_API_BASE_DEFAULT).strip() or CEREBRAS_API_BASE_DEFAULT
    )
    if not gemini_api_key and not (enable_cerebras_fallback and cerebras_api_key):
        return jsonify(
            {
                "message": (
                    "No LLM key configured. Set GEMINI_API_KEY, or enable Cerebras fallback and set CEREBRAS_API_KEY."
                )
            }
        ), 400

    try:
        raw_response = call_llm_for_topic_generation(
            projects=cleaned_projects,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            cerebras_api_key=cerebras_api_key,
            cerebras_model=cerebras_model,
            cerebras_api_base=cerebras_api_base,
            enable_cerebras_fallback=enable_cerebras_fallback,
        )
        topics = sanitize_generated_topics(raw_response)
        if not topics:
            return jsonify({"message": "LLM returned no valid topics."}), 502
        return jsonify({"topics": topics})
    except Exception as exc:
        logging.exception("Topic generation failed")
        return jsonify({"message": f"Topic generation failed: {safe_exception_text(exc)}"}), 500


@app.route("/manual", methods=["GET"])
def manual():
    ui_language = get_ui_language()
    preferred_manual = "MANUAL_KR.md" if ui_language == "ko" else "MANUAL_EN.md"
    fallback_manual = "MANUAL_EN.md" if preferred_manual == "MANUAL_KR.md" else "MANUAL_KR.md"
    manual_candidates = [
        (get_runtime_base_dir() / "docs" / "manuals" / preferred_manual).resolve(),
        (Path("docs") / "manuals" / preferred_manual).resolve(),
        (get_runtime_base_dir() / preferred_manual).resolve(),
        Path(preferred_manual).resolve(),
        (get_runtime_base_dir() / "docs" / "manuals" / fallback_manual).resolve(),
        (Path("docs") / "manuals" / fallback_manual).resolve(),
        (get_runtime_base_dir() / fallback_manual).resolve(),
        Path(fallback_manual).resolve(),
    ]
    manual_path = next((candidate for candidate in manual_candidates if candidate.exists()), None)
    if manual_path is None:
        return render_page(
            "Manual",
            (
                '<div class="card"><h2>Manual</h2>'
                '<p class="text-danger">Manual file not found. '
                '(docs/manuals/MANUAL_EN.md or docs/manuals/MANUAL_KR.md)</p></div>'
            ),
            active_page="manual",
        )

    markdown_text = manual_path.read_text(encoding="utf-8-sig")
    rendered_html = md.markdown(
        markdown_text,
        extensions=[
            "fenced_code",
            "tables",
            "sane_lists",
            "toc",
        ],
    )
    body = f"""
    <div class="page-header">
      <h1>📖 Manual</h1>
      <p>Paper Morning usage guide</p>
    </div>
    <div class="card md-body">
      {rendered_html}
    </div>
    """
    return render_page("Manual", body, active_page="manual")


@app.route("/license", methods=["GET"])
def license_page():
    candidates = [
        (get_runtime_base_dir() / "LICENSE").resolve(),
        Path("LICENSE").resolve(),
    ]
    license_path = next((path for path in candidates if path.exists()), None)
    if not license_path:
        return render_page(
            "License",
            '<div class="card"><h2>License</h2><p class="text-danger">LICENSE file not found.</p></div>',
            active_page="license",
        )

    license_text = license_path.read_text(encoding="utf-8-sig")
    body = f"""
    <div class="page-header">
      <h1>⚖️ License</h1>
      <p>Current license: GNU AGPLv3</p>
    </div>
    <div class="card">
      <p class="small" style="margin-top:0;">For licensing questions, contact <a href="mailto:nineclas@gmail.com">nineclas@gmail.com</a>.</p>
      <pre style="white-space:pre-wrap; word-break:break-word; margin:0;">{html.escape(license_text)}</pre>
    </div>
    """
    return render_page("License", body, active_page="license")


@app.route("/logs/content", methods=["GET"])
def logs_content():
    lines_raw = request.args.get("lines", "400").strip()
    try:
        lines = max(50, min(2000, int(lines_raw)))
    except ValueError:
        lines = 400
    log_path = get_log_file_path()
    content = read_log_tail(log_path, max_lines=lines)
    return jsonify(
        {
            "path": str(log_path),
            "exists": log_path.exists(),
            "size": log_path.stat().st_size if log_path.exists() else 0,
            "lines": lines,
            "content": content,
        }
    )


@app.route("/logs", methods=["GET"])
def logs_page():
    body = f"""
    <div class="page-header">
      <h1>Logs</h1>
      <p>View runtime logs. File: <code id="log-path">-</code></p>
    </div>

    <div class="card">
      <div class="button-row" style="margin-bottom:10px;">
        <label class="small" style="display:flex; align-items:center; gap:6px;">
          Lines
          <input id="log-lines" type="number" min="50" max="2000" step="50" value="400" style="width:90px;" />
        </label>
        <button type="button" onclick="loadLogs()">Refresh</button>
        <button type="button" class="btn-ghost" id="btn-auto" onclick="toggleAuto()">Auto refresh: OFF</button>
        <span id="log-meta" class="small"></span>
      </div>
      <pre id="log-viewer" style="max-height:600px;">Loading...</pre>
    </div>

    <script>
      let autoTimer = null;

      async function loadLogs() {{
        const lines = document.getElementById('log-lines').value || '400';
        const res = await fetch('{url_for("logs_content")}?lines=' + encodeURIComponent(lines));
        const data = await res.json();
        document.getElementById('log-path').innerText = data.path || '-';
        document.getElementById('log-meta').innerText = `size=${{data.size || 0}} bytes`;
        const box = document.getElementById('log-viewer');
        box.textContent = data.content || '(empty)';
        box.scrollTop = box.scrollHeight;
      }}

      function toggleAuto() {{
        const btn = document.getElementById('btn-auto');
        if (autoTimer) {{
          clearInterval(autoTimer);
          autoTimer = null;
          btn.innerText = 'Auto refresh: OFF';
          return;
        }}
        autoTimer = setInterval(loadLogs, 5000);
        btn.innerText = 'Auto refresh: ON (5s)';
        loadLogs();
      }}

      loadLogs();
    </script>
    """
    return render_page("Logs", body, active_page="logs")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Paper Digest local web console.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    return parser.parse_args()


def main() -> int:
    setup_logging()
    ensure_bootstrap_files()
    args = parse_args()
    try:
        ensure_host_security(args.host, read_env_map())
    except Exception as exc:
        logging.error(safe_exception_text(exc))
        return 1

    try:
        info = refresh_scheduler()
        logging.info(info)
    except Exception as exc:
        logging.warning("Scheduler initialization skipped: %s", safe_exception_text(exc))

    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

