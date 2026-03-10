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
from flask import Flask, flash, jsonify, redirect, render_template_string, request, send_file, session, url_for

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


def read_app_version() -> str:
    version_path = get_runtime_base_dir() / "VERSION"
    if not version_path.exists():
        version_path = Path("VERSION")
    if version_path.exists():
        value = version_path.read_text(encoding="utf-8-sig").strip()
        if value:
            return value
    return "0.5.1"


APP_VERSION = read_app_version()
APP_TITLE = f"Paper Digest Web Console v{APP_VERSION}"
SCHEDULER_JOB_ID = "daily-paper-digest-web-job"
SESSION_SECRET_ENV_KEY = "WEB_APP_SECRET_KEY"
AUTH_TOKEN_ENV_KEY = "WEB_APP_AUTH_TOKEN"
WEB_AUTH_SESSION_KEY = "pm_auth_ok"
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
    "USER_TOPICS_FILE",
    "WEB_PASSWORD",
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
    "TIMEZONE": "Asia/Seoul",
    "SEND_HOUR": "9",
    "SEND_MINUTE": "0",
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
    "USER_TOPICS_FILE": "user_topics.json",
    "WEB_PASSWORD": "",
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
<html lang="ko">
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
            "원격 host 바인딩(0.0.0.0 등)은 기본 차단됩니다. "
            "정말 필요한 경우에만 ALLOW_INSECURE_REMOTE_WEB=true와 WEB_PASSWORD를 함께 설정하세요."
        )
    if not get_web_password(values):
        raise ValueError(
            "--host를 127.0.0.1 외로 지정하려면 WEB_PASSWORD를 먼저 설정해야 합니다."
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
    return False, f"Send Now 재실행은 {wait}초 후 가능합니다."


def mark_send_now_executed() -> None:
    state = read_send_state()
    state["last_send_now_ts"] = time.time()
    state["last_send_now_at"] = now_iso()
    write_send_state(state)


def read_env_map() -> Dict[str, str]:
    env_path = resolve_env_path()
    env_example_path = get_runtime_base_dir() / ".env.example"
    merged = dict(DEFAULT_ENV_VALUES)
    if env_example_path.exists():
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


def get_topics_path(env_map: Dict[str, str]) -> Path:
    path = (env_map.get("USER_TOPICS_FILE") or "user_topics.json").strip()
    topic_path = Path(path).expanduser()
    if not topic_path.is_absolute():
        topic_path = resolve_env_path().parent / topic_path
    return topic_path.resolve()


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
    return render_template_string(
        BASE_TEMPLATE,
        title=title,
        body=body,
        auth_token=APP_AUTH_TOKEN,
        active_page=active_page,
        app_version=APP_VERSION,
    )


def test_gmail_login(gmail_address: str, gmail_app_password: str) -> Tuple[bool, str]:
    if not gmail_address or not gmail_app_password:
        return False, "GMAIL_ADDRESS/GMAIL_APP_PASSWORD가 비어 있습니다."
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
            smtp.login(gmail_address, "".join(gmail_app_password.split()))
        return True, "Gmail SMTP 로그인 성공"
    except Exception as exc:
        return False, f"Gmail 로그인 실패: {safe_exception_text(exc)}"


def test_google_oauth_gmail(env_map: Dict[str, str]) -> Tuple[bool, str]:
    enabled = env_truthy(str(env_map.get("ENABLE_GOOGLE_OAUTH", "false")))
    use_for_gmail = env_truthy(str(env_map.get("GOOGLE_OAUTH_USE_FOR_GMAIL", "true")))
    if not enabled or not use_for_gmail:
        return False, "Google OAuth Gmail 사용이 꺼져 있습니다."
    oauth_values = get_effective_google_oauth_values(env_map)
    client_id = str(oauth_values.get("client_id", "")).strip()
    client_secret = str(oauth_values.get("client_secret", "")).strip()
    refresh_token = resolve_secret_value(
        "GOOGLE_OAUTH_REFRESH_TOKEN",
        str(env_map.get("GOOGLE_OAUTH_REFRESH_TOKEN", "")),
    )
    if not client_id or not client_secret or not refresh_token:
        return False, "Google OAuth 설정/연결이 완료되지 않았습니다."
    try:
        access_token = refresh_google_oauth_access_token(client_id, client_secret, refresh_token)
        info = fetch_google_userinfo(access_token)
        email = str(info.get("email", "")).strip()
        if email:
            return True, f"Google OAuth 토큰 갱신 성공 ({email})"
        return True, "Google OAuth 토큰 갱신 성공"
    except Exception as exc:
        return False, f"Google OAuth 확인 실패: {safe_exception_text(exc)}"


def test_gemini_key(gemini_api_key: str, gemini_model: str) -> Tuple[bool, str]:
    if not gemini_api_key:
        return False, "GEMINI_API_KEY가 비어 있습니다."
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
            return True, f"Gemini API 호출 성공 (fallback model: {used_model})"
        return True, "Gemini API 호출 성공"
    except Exception as exc:
        return False, f"Gemini 호출 실패: {safe_exception_text(exc)}"


def test_cerebras_key(
    cerebras_api_key: str,
    cerebras_model: str,
    cerebras_api_base: str,
) -> Tuple[bool, str]:
    if not cerebras_api_key:
        return False, "CEREBRAS_API_KEY가 비어 있습니다."
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
        return True, "Cerebras API 호출 성공"
    except Exception as exc:
        return False, f"Cerebras 호출 실패: {safe_exception_text(exc)}"


def test_semantic_scholar_key(semantic_api_key: str) -> Tuple[bool, str]:
    if not semantic_api_key:
        return False, "SEMANTIC_SCHOLAR_API_KEY가 비어 있습니다."
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
        return True, "Semantic Scholar API 호출 성공"
    except Exception as exc:
        return False, f"Semantic Scholar 호출 실패: {safe_exception_text(exc)}"


def test_google_scholar_key(google_scholar_api_key: str) -> Tuple[bool, str]:
    if not google_scholar_api_key:
        return False, "GOOGLE_SCHOLAR_API_KEY가 비어 있습니다."
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
        return True, "Google Scholar(SerpAPI) 호출 성공"
    except Exception as exc:
        return False, f"Google Scholar(SerpAPI) 호출 실패: {safe_exception_text(exc)}"


def build_settings_warnings(env_map: Dict[str, str]) -> List[str]:
    warnings: List[str] = []
    if env_truthy(str(env_map.get("ALLOW_INSECURE_REMOTE_WEB", "false"))):
        warnings.append(
            "ALLOW_INSECURE_REMOTE_WEB=true: TLS 없는 원격 노출은 키/비밀번호 유출 위험이 큽니다."
        )
    if not env_truthy(str(env_map.get("USE_KEYRING", "true"))):
        warnings.append(
            "USE_KEYRING=false: 비밀값이 .env 파일에 평문 저장됩니다."
        )
    elif not is_keyring_available():
        warnings.append(
            "USE_KEYRING=true 이지만 keyring 모듈/백엔드를 찾지 못했습니다. 현재는 평문 .env 저장으로 동작합니다."
        )
    if env_truthy(str(env_map.get("ENABLE_GOOGLE_OAUTH", "false"))):
        oauth_values = get_effective_google_oauth_values(env_map)
        if not str(oauth_values.get("client_id", "")).strip():
            warnings.append("ENABLE_GOOGLE_OAUTH=true 이지만 GOOGLE_OAUTH_CLIENT_ID가 비어 있습니다. (또는 내장 OAuth 번들이 없습니다.)")
        if not str(oauth_values.get("client_secret", "")).strip():
            warnings.append("ENABLE_GOOGLE_OAUTH=true 이지만 GOOGLE_OAUTH_CLIENT_SECRET가 비어 있습니다. (또는 내장 OAuth 번들이 없습니다.)")
        if not resolve_secret_value(
            "GOOGLE_OAUTH_REFRESH_TOKEN",
            str(env_map.get("GOOGLE_OAUTH_REFRESH_TOKEN", "")),
        ):
            warnings.append("Google OAuth가 아직 연결되지 않았습니다. 'Google 로그인 연결' 버튼을 실행하세요.")

    try:
        max_queries = int(str(env_map.get("MAX_SEARCH_QUERIES_PER_SOURCE", "4")).strip())
        if max_queries > 30:
            warnings.append(
                f"MAX_SEARCH_QUERIES_PER_SOURCE={max_queries}: API 호출량이 과도할 수 있습니다."
            )
    except ValueError:
        pass

    try:
        semantic_max = int(str(env_map.get("SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY", "20")).strip())
        if semantic_max > 50:
            warnings.append(
                f"SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY={semantic_max}: 호출량/응답시간이 증가할 수 있습니다."
            )
    except ValueError:
        pass

    try:
        llm_candidates = int(str(env_map.get("LLM_MAX_CANDIDATES", "30")).strip())
        if llm_candidates > 80:
            warnings.append("LLM_MAX_CANDIDATES는 최대 80까지 권장됩니다. 실행 시 80으로 제한 적용됩니다.")
        elif llm_candidates > 55:
            warnings.append(f"LLM_MAX_CANDIDATES={llm_candidates}: LLM 비용이 증가할 수 있습니다.")
    except ValueError:
        pass
    if env_truthy(str(env_map.get("ENABLE_GEMINI_ADVANCED_REASONING", "true"))):
        warnings.append("고급 추론(3.1 Pro)이 활성화되어 있습니다. 속도/비용이 증가할 수 있습니다.")

    if not str(env_map.get("NCBI_API_KEY", "")).strip():
        warnings.append("NCBI_API_KEY 미설정: PubMed 쿼리 처리량 제한에 걸릴 수 있습니다.")

    if env_truthy(str(env_map.get("ENABLE_GOOGLE_SCHOLAR", "false"))):
        if not resolve_secret_value(
            "GOOGLE_SCHOLAR_API_KEY",
            str(env_map.get("GOOGLE_SCHOLAR_API_KEY", "")),
        ):
            warnings.append("ENABLE_GOOGLE_SCHOLAR=true 이지만 GOOGLE_SCHOLAR_API_KEY가 비어 있습니다.")

    return warnings


def register_windows_scheduled_task() -> Tuple[bool, str]:
    if os.name != "nt":
        return False, "Windows에서만 지원됩니다."

    candidates = [
        get_runtime_base_dir() / "register_task.ps1",
        Path(__file__).resolve().parent / "register_task.ps1",
    ]
    script_path = next((path for path in candidates if path.exists()), None)
    if not script_path:
        return False, "register_task.ps1 파일을 찾을 수 없습니다."

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
        return False, f"작업 스케줄러 등록 실행 실패: {safe_exception_text(exc)}"

    output = (completed.stdout or "").strip()
    error = (completed.stderr or "").strip()
    if completed.returncode != 0:
        message = error or output or "알 수 없는 오류"
        return False, f"등록 실패: {message}"
    return (
        True,
        (output or "Windows 작업 스케줄러 등록 완료")
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
        (get_runtime_base_dir() / APP_LOGO_FILENAME).resolve(),
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
    template_path = get_runtime_base_dir() / "user_topics.template.json"
    if template_path.exists():
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
        return "로그 파일이 아직 생성되지 않았습니다."
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception as exc:
        return f"로그 파일 읽기 실패: {exc}"
    if len(text) > max_chars:
        text = text[-max_chars:]
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return "\n".join(lines) if lines else "(empty log)"


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
        if not has_configured_topic_queries(
            topics_payload,
            enable_semantic_scholar=semantic_enabled,
            enable_google_scholar=google_scholar_enabled,
        ):
            return (
                False,
                "검색 쿼리가 없습니다. Topic Editor에서 'Keyword / Query 생성' 또는 arXiv/PubMed/Semantic Scholar/Google Scholar 쿼리를 수동 입력 후 Save Topics를 먼저 실행하세요.",
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
            update_job_state(status="Dry-run completed.", progress=100)
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
            update_job_state(status="Send-now completed.", progress=100)
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
    escaped_output = html.escape(last_dry_run_output) if last_dry_run_output else "No dry-run yet."
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
    oauth_source = "Settings 입력값"
    if oauth_values.get("using_bundled_client_id") or oauth_values.get("using_bundled_client_secret"):
        oauth_source = "배포판 내장 번들"
    if oauth_ready:
        oauth_badge_html = '<span class="badge badge-running">🟢 연결 완료</span>'
        oauth_message = "Google OAuth로 Gmail 발송이 활성화되어 있습니다."
    elif oauth_client_ready:
        oauth_badge_html = '<span class="badge badge-idle">🟡 로그인 필요</span>'
        oauth_message = "클라이언트 설정은 준비됨. Google 로그인 연결을 완료하세요."
    else:
        oauth_badge_html = '<span class="badge badge-danger">🔴 미설정</span>'
        oauth_message = "OAuth 클라이언트 정보가 없습니다. 내장 번들 또는 Settings 입력이 필요합니다."
    if OAUTH_UI_ENABLED:
        oauth_controls_html = (
            f'<a class="btn btn-ghost" href="{url_for("google_oauth_start")}">Google 로그인 연결</a>'
            '<button type="button" class="btn-danger" onclick="disconnectGoogleOauth()">연결 해제</button>'
        )
        oauth_disabled_note = ""
    else:
        oauth_controls_html = (
            '<button type="button" class="btn btn-ghost" disabled>Google 로그인 연결</button>'
            '<button type="button" class="btn-danger" disabled>연결 해제</button>'
        )
        oauth_disabled_note = "현재 배포판에서는 OAuth UI가 비활성화되어 있습니다. Gmail 앱 비밀번호 방식을 사용하세요."
    send_frequency = str(env_map.get("SEND_FREQUENCY", "daily") or "daily").strip().lower()
    send_frequency_label = {
        "daily": "매일",
        "every_3_days": "3일마다",
        "weekly": "매주(7일)",
    }.get(send_frequency, send_frequency)

    body = """
    <div class="page-header">
      <h1>Dashboard</h1>
      <p>논문 수집/발송을 수동으로 실행하거나, 스케줄러 상태를 확인합니다.</p>
    </div>

    <div class="card" style="display:flex; align-items:center; gap:10px; padding:14px 18px;">
      <span id="sched-icon" style="font-size:18px;">📅</span>
      <div>
        <span id="sched-text" style="font-size:13.5px; font-weight:500;">__SCHEDULER_STATUS__</span>
        <div class="small" style="margin-top:4px;">발송 주기: <b>__SEND_FREQUENCY__</b></div>
      </div>
    </div>

    <div class="card">
      <p class="card-title">Google OAuth 상태</p>
      <div class="status-panel">
        <div class="status-kv">
          <div class="kv-label">연결 상태</div>
          <div class="kv-value">__OAUTH_BADGE__</div>
        </div>
        <div class="status-kv">
          <div class="kv-label">연동 계정</div>
          <div class="kv-value">__OAUTH_EMAIL__</div>
        </div>
        <div class="status-kv">
          <div class="kv-label">클라이언트 소스</div>
          <div class="kv-value">__OAUTH_SOURCE__</div>
        </div>
      </div>
      <p class="small" style="margin-top:8px;">__OAUTH_MESSAGE__</p>
      <p class="small" style="margin-top:6px; color:var(--text-sub);">내장 번들 준비 상태: __OAUTH_BUNDLE_READY__</p>
      <p class="small" style="margin-top:6px; color:var(--text-sub);">__OAUTH_DISABLED_NOTE__</p>
      <div class="button-row" style="margin-top:12px;">
        __OAUTH_CONTROLS_HTML__
      </div>
    </div>

    <div class="action-grid">
      <div class="action-card">
        <span class="action-icon">🔍</span>
        <span class="action-label">Dry-Run</span>
        <span class="action-desc">메일 발송 없이 오늘 수집/선별 결과만 확인합니다.</span>
        <button id="btn-dry" onclick="startJob('dry_run')">실행</button>
      </div>
      <div class="action-card">
        <span class="action-icon">📨</span>
        <span class="action-label">Send Now</span>
        <span class="action-desc">지금 즉시 실제 논문 리포트 메일을 1회 발송합니다.</span>
        <button id="btn-send" class="btn-success" onclick="startJob('send_now')">발송</button>
      </div>
      <div class="action-card">
        <span class="action-icon">🔄</span>
        <span class="action-label">Reload Scheduler</span>
        <span class="action-desc">변경된 발송 시간/설정을 스케줄러에 다시 반영합니다.</span>
        <button id="btn-reload" class="btn-ghost" onclick="startJob('reload_scheduler')">리로드</button>
      </div>
      <div class="action-card">
        <span class="action-icon">🪟</span>
        <span class="action-label">Windows Task</span>
        <span class="action-desc">Windows 작업 스케줄러에 매일 자동 실행 작업을 등록합니다.</span>
        <button id="btn-task" class="btn-ghost" onclick="startJob('register_windows_task')">등록</button>
      </div>
    </div>

    <div class="card">
      <p class="card-title">Task Status</p>
      <div class="status-panel">
        <div class="status-kv">
          <div class="kv-label">상태</div>
          <div class="kv-value" id="status-badge"><span class="badge badge-idle">⬜ 대기 중</span></div>
        </div>
        <div class="status-kv">
          <div class="kv-label">시작 시각</div>
          <div class="kv-value" id="status-started">—</div>
        </div>
        <div class="status-kv">
          <div class="kv-label">완료 시각</div>
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
        <p class="card-title" style="margin:0; border:none; padding:0;">Last Dry-Run Output</p>
        <button class="btn-ghost" onclick="toggleOutput()" id="btn-toggle" style="padding:4px 10px; font-size:12px;">접기 ▲</button>
      </div>
      <div id="output-wrap">
        <pre id="output-pre">__LAST_DRY_OUTPUT__</pre>
      </div>
    </div>

    <script>
      let outputVisible = true;
      function toggleOutput() {
        const wrap = document.getElementById('output-wrap');
        const btn = document.getElementById('btn-toggle');
        outputVisible = !outputVisible;
        wrap.style.display = outputVisible ? '' : 'none';
        btn.textContent = outputVisible ? '접기 ▲' : '펼치기 ▼';
      }

      const JOB_LABEL = { dry_run: 'Dry-Run', send_now: 'Send Now', reload_scheduler: 'Reload Scheduler', register_windows_task: 'Windows Task Register', none: '' };

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
        ['btn-dry', 'btn-send', 'btn-reload', 'btn-task'].forEach(id => {
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
          badgeEl.innerHTML = `<span class="badge badge-running">🔵 실행 중 — ${JOB_LABEL[kind]}</span>`;
        } else if (hasError) {
          badgeEl.innerHTML = '<span class="badge badge-danger">🔴 실패</span>';
        } else {
          badgeEl.innerHTML = '<span class="badge badge-idle">⬜ 대기 중</span>';
        }
        setButtonsDisabled(running);
      }

      async function startJob(kind) {
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
        if (!confirm('Google OAuth 연결을 해제할까요?')) {
          return;
        }
        try {
          const res = await fetch('__OAUTH_DISCONNECT_URL__', {
            method: 'POST',
            headers: { 'X-App-Token': window.APP_TOKEN || '' },
          });
          if (!res.ok) {
            alert('OAuth 연결 해제 실패');
            return;
          }
          window.location.reload();
        } catch (err) {
          alert('OAuth 연결 해제 실패');
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
        .replace("__OAUTH_BADGE__", oauth_badge_html)
        .replace("__OAUTH_EMAIL__", html.escape(oauth_connected_email or "미연결"))
        .replace("__OAUTH_SOURCE__", html.escape(oauth_source))
        .replace("__OAUTH_MESSAGE__", html.escape(oauth_message))
        .replace("__OAUTH_BUNDLE_READY__", "있음" if oauth_bundle_ready else "없음")
        .replace("__OAUTH_DISABLED_NOTE__", html.escape(oauth_disabled_note))
        .replace("__OAUTH_CONTROLS_HTML__", oauth_controls_html)
        .replace("__OAUTH_DISCONNECT_URL__", url_for("google_oauth_disconnect"))
        .replace("__API_STATUS__", url_for("jobs_status"))
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
        flash("비밀번호가 올바르지 않습니다.", "danger")

    body = f"""
    <div class="page-header">
      <h1>Login</h1>
      <p>WEB_PASSWORD가 설정된 환경입니다. 비밀번호를 입력하세요.</p>
    </div>
    <div class="card" style="max-width:420px;">
      <form method="post">
        <input type="hidden" name="next" value="{html.escape(next_path, quote=True)}" />
        <label style="display:block; margin-bottom:8px; font-weight:600;">웹 콘솔 비밀번호</label>
        <input type="password" name="password" autocomplete="current-password" style="width:100%;" />
        <div style="margin-top:12px;">
          <button type="submit">로그인</button>
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
        flash("현재 버전에서는 Google OAuth UI가 비활성화되어 있습니다. Gmail 앱 비밀번호를 사용하세요.", "danger")
        return redirect(url_for("settings"))
    env_map = read_env_map()
    oauth_values = get_effective_google_oauth_values(env_map)
    client_id = str(oauth_values.get("client_id", "")).strip()
    client_secret = str(oauth_values.get("client_secret", "")).strip()
    if not client_id or not client_secret:
        flash("Google OAuth Client ID/Secret를 먼저 설정하세요. (또는 배포판 OAuth 번들 파일을 포함하세요.)", "danger")
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
        flash("현재 버전에서는 Google OAuth UI가 비활성화되어 있습니다. Gmail 앱 비밀번호를 사용하세요.", "danger")
        return redirect(url_for("settings"))
    error = request.args.get("error", "").strip()
    if error:
        flash(f"Google OAuth 인증 실패: {error}", "danger")
        return redirect(url_for("settings"))

    returned_state = request.args.get("state", "").strip()
    expected_state = str(session.pop(GOOGLE_OAUTH_STATE_SESSION_KEY, "") or "").strip()
    if not returned_state or not expected_state or returned_state != expected_state:
        flash("Google OAuth state 검증 실패. 다시 시도하세요.", "danger")
        return redirect(url_for("settings"))

    code = request.args.get("code", "").strip()
    if not code:
        flash("Google OAuth code가 없습니다.", "danger")
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
        flash("Google OAuth Client ID/Secret가 설정되어 있지 않습니다.", "danger")
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
                "refresh_token이 반환되지 않았습니다. Google 계정에서 앱 권한을 제거한 뒤 다시 연결해 주세요."
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
            flash(f"Google 계정 연동 완료: {connected_email}", "ok")
        else:
            flash("Google 계정 연동 완료.", "ok")
    except Exception as exc:
        flash(f"Google OAuth 연결 실패: {safe_exception_text(exc)}", "danger")
    return redirect(url_for("settings"))


@app.route("/oauth/google/disconnect", methods=["POST"])
def google_oauth_disconnect():
    if not OAUTH_UI_ENABLED:
        flash("현재 버전에서는 Google OAuth UI가 비활성화되어 있습니다.", "danger")
        return redirect(url_for("settings"))
    env_map = read_env_map()
    updated = dict(env_map)
    updated["ENABLE_GOOGLE_OAUTH"] = "false"
    updated["GOOGLE_OAUTH_USE_FOR_GMAIL"] = "false"
    updated["GOOGLE_OAUTH_REFRESH_TOKEN"] = ""
    updated["GOOGLE_OAUTH_CONNECTED_EMAIL"] = ""
    try:
        write_env_map(updated)
        flash("Google OAuth 연결을 해제했습니다.", "ok")
    except Exception as exc:
        flash(f"Google OAuth 해제 실패: {safe_exception_text(exc)}", "danger")
    return redirect(url_for("settings"))


@app.route("/setup", methods=["GET", "POST"])
def setup():
    env_map = read_env_map()
    env_path = resolve_env_path()

    if request.method == "POST":
        updated = dict(env_map)
        basic_keys = [
            "GMAIL_ADDRESS",
            "RECIPIENT_EMAIL",
            "TIMEZONE",
            "SEND_HOUR",
            "SEND_MINUTE",
            "SEND_FREQUENCY",
            "SEND_ANCHOR_DATE",
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

        updated["SETUP_WIZARD_COMPLETED"] = "true"
        try:
            write_env_map(updated)
            try:
                refresh_scheduler()
            except Exception as exc:
                logging.warning("Setup saved but scheduler reload skipped: %s", safe_exception_text(exc))
            flash("Setup 저장 완료.", "ok")
            return redirect(url_for("home"))
        except Exception as exc:
            flash(f"Setup 저장 실패: {safe_exception_text(exc)}", "danger")
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
    oauth_bundle_ready_text = "있음" if oauth_defaults.get("bundle_ready") else "없음"
    oauth_source_text = "Settings 입력값"
    if oauth_defaults.get("using_bundled_client_id") or oauth_defaults.get("using_bundled_client_secret"):
        oauth_source_text = "배포판 내장 번들"
    oauth_disabled_attr = "" if OAUTH_UI_ENABLED else "disabled"
    if OAUTH_UI_ENABLED:
        oauth_setup_connect_html = f'<a class="btn btn-ghost" href="{url_for("google_oauth_start")}">Google 로그인 연결</a>'
    else:
        oauth_setup_connect_html = '<button type="button" class="btn btn-ghost" disabled>Google 로그인 연결</button>'
    send_hour_padded = str(env_map.get("SEND_HOUR", "9")).zfill(2)
    send_minute_padded = str(env_map.get("SEND_MINUTE", "0")).zfill(2)

    def esc(key: str) -> str:
        return html.escape(str(env_map.get(key, "")), quote=True)

    body = f"""
    <div class="page-header">
      <h1>Setup Wizard</h1>
      <p>처음 1회 기본 설정을 완료하세요. 설정 파일: <code>{html.escape(str(env_path))}</code></p>
    </div>

    <form method="post">
      <input type="hidden" name="app_token" value="{APP_AUTH_TOKEN}" />

      <div class="card">
        <p class="card-title">1) 이메일/스케줄</p>
        <p class="small" style="margin:0 0 12px;">Gmail 발송 인증은 <strong>앱 비밀번호</strong> 또는 <strong>Google OAuth</strong> 중 하나만 완료하면 됩니다.</p>
        <div class="settings-grid">
          <div class="settings-row">
            <div class="settings-label"><strong>Gmail 주소</strong></div>
            <input type="text" name="GMAIL_ADDRESS" value="{esc('GMAIL_ADDRESS')}" placeholder="example@gmail.com" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Gmail 앱 비밀번호</strong><small>16자리, OAuth를 쓸 경우 선택 사항. <a href="https://myaccount.google.com/apppasswords" target="_blank">🔗 발급 바로가기</a>. 빈칸 저장 시 기존값 유지</small></div>
            <input type="password" name="GMAIL_APP_PASSWORD" value="" placeholder="xxxx xxxx xxxx xxxx" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>수신 이메일</strong></div>
            <input type="text" name="RECIPIENT_EMAIL" value="{esc('RECIPIENT_EMAIL')}" placeholder="recipient@example.com" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>타임존</strong></div>
            <input type="text" name="TIMEZONE" value="{esc('TIMEZONE')}" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>발송 시각</strong></div>
            <div>
              <input type="time" id="setup_send_time" value="{send_hour_padded}:{send_minute_padded}" onchange="splitSetupTime(this.value)" style="width:140px;" />
              <input type="hidden" name="SEND_HOUR" id="setup_send_hour" value="{esc('SEND_HOUR')}" />
              <input type="hidden" name="SEND_MINUTE" id="setup_send_minute" value="{esc('SEND_MINUTE')}" />
            </div>
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>발송 주기</strong><small>SEND_FREQUENCY</small></div>
            <select name="SEND_FREQUENCY" style="width:160px;">
              <option value="daily" {"selected" if env_map.get("SEND_FREQUENCY", "daily") == "daily" else ""}>매일</option>
              <option value="every_3_days" {"selected" if env_map.get("SEND_FREQUENCY", "daily") == "every_3_days" else ""}>3일마다</option>
              <option value="weekly" {"selected" if env_map.get("SEND_FREQUENCY", "daily") == "weekly" else ""}>매주(7일)</option>
            </select>
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>주기 기준일</strong><small>SEND_ANCHOR_DATE (YYYY-MM-DD)</small></div>
            <input type="text" name="SEND_ANCHOR_DATE" value="{esc('SEND_ANCHOR_DATE')}" placeholder="2026-01-01" style="width:160px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Send Now 쿨다운(초)</strong><small>권장 300</small></div>
            <input type="number" min="0" name="SEND_NOW_COOLDOWN_SECONDS" value="{esc('SEND_NOW_COOLDOWN_SECONDS')}" style="width:140px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>중복 발송 보관일</strong><small>sent_ids.json 유지 기간</small></div>
            <input type="number" min="1" name="SENT_HISTORY_DAYS" value="{esc('SENT_HISTORY_DAYS')}" style="width:140px;" />
          </div>
        </div>
      </div>

      <div class="card">
        <p class="card-title">2) LLM/API (선택)</p>
        <p class="small" style="margin:0 0 12px;">API 키가 없어도 키워드 기반 폴백 모드로 동작합니다.</p>
        <p class="small" style="margin:0 0 12px;">Google OAuth 내장 번들: <strong>{oauth_bundle_ready_text}</strong> (현재 소스: {html.escape(oauth_source_text)})</p>
        <p class="small" style="margin:0 0 12px;">{'' if OAUTH_UI_ENABLED else '현재 버전에서는 OAuth 설정 UI가 비활성화되어 있습니다. Gmail 앱 비밀번호 방식을 사용하세요.'}</p>
        <div class="settings-grid">
          <div class="settings-row">
            <div class="settings-label"><strong>LLM 에이전트 사용</strong></div>
            <input type="checkbox" name="ENABLE_LLM_AGENT" {checked_llm} />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Gemini API Key</strong><small><a href="https://aistudio.google.com/" target="_blank">🔗 발급 방법</a></small></div>
            <input type="password" name="GEMINI_API_KEY" value="" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Gemini 모델</strong></div>
            <input type="text" name="GEMINI_MODEL" value="{esc('GEMINI_MODEL')}" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>요약 출력 언어</strong><small>OUTPUT_LANGUAGE — 예: en, ko, ja, es, fr</small></div>
            <input type="text" name="OUTPUT_LANGUAGE" value="{esc('OUTPUT_LANGUAGE')}" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>고급 추론 사용</strong><small>ENABLE_GEMINI_ADVANCED_REASONING — 체크 시 Gemini 3.1 Pro 강제 사용</small></div>
            <input type="checkbox" name="ENABLE_GEMINI_ADVANCED_REASONING" {checked_gemini_advanced} />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Cerebras fallback</strong></div>
            <input type="checkbox" name="ENABLE_CEREBRAS_FALLBACK" {checked_cerebras} />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Cerebras API Key</strong><small><a href="https://cloud.cerebras.ai/" target="_blank">🔗 발급 방법</a></small></div>
            <input type="password" name="CEREBRAS_API_KEY" value="" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Cerebras 모델</strong></div>
            <input type="text" name="CEREBRAS_MODEL" value="{esc('CEREBRAS_MODEL')}" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Cerebras API Base</strong></div>
            <input type="text" name="CEREBRAS_API_BASE" value="{esc('CEREBRAS_API_BASE')}" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Semantic Scholar 소스 사용</strong></div>
            <input type="checkbox" name="ENABLE_SEMANTIC_SCHOLAR" {checked_semantic} />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Semantic Scholar API Key</strong><small><a href="https://www.semanticscholar.org/product/api" target="_blank">🔗 발급 방법</a></small></div>
            <input type="password" name="SEMANTIC_SCHOLAR_API_KEY" value="" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Semantic Scholar 쿼리당 최대 결과</strong></div>
            <input type="number" min="1" max="100" name="SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY" value="{esc('SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY')}" style="width:140px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Google Scholar 소스 사용</strong><small>SerpAPI 기반</small></div>
            <input type="checkbox" name="ENABLE_GOOGLE_SCHOLAR" {checked_google_scholar} />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Google Scholar API Key</strong><small><a href="https://serpapi.com/" target="_blank">🔗 SerpAPI</a></small></div>
            <input type="password" name="GOOGLE_SCHOLAR_API_KEY" value="" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Google Scholar 쿼리당 최대 결과</strong><small>권장 10~20</small></div>
            <input type="number" min="1" max="20" name="GOOGLE_SCHOLAR_MAX_RESULTS_PER_QUERY" value="{esc('GOOGLE_SCHOLAR_MAX_RESULTS_PER_QUERY')}" style="width:140px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>NCBI API Key</strong><small>PubMed 처리량 향상(권장)</small></div>
            <input type="text" name="NCBI_API_KEY" value="{esc('NCBI_API_KEY')}" />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Google OAuth 사용</strong><small>앱 비밀번호 대신 Google 로그인 연동</small></div>
            <input type="checkbox" name="ENABLE_GOOGLE_OAUTH" {checked_google_oauth} {oauth_disabled_attr} />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>OAuth를 Gmail 발송에 사용</strong><small>GOOGLE_OAUTH_USE_FOR_GMAIL</small></div>
            <input type="checkbox" name="GOOGLE_OAUTH_USE_FOR_GMAIL" {checked_google_oauth_gmail} {oauth_disabled_attr} />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Google OAuth Client ID</strong><small>Google Cloud OAuth 클라이언트 ID (내장 번들이 있으면 비워도 됨)</small></div>
            <input type="text" name="GOOGLE_OAUTH_CLIENT_ID" value="{esc('GOOGLE_OAUTH_CLIENT_ID')}" {oauth_disabled_attr} />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Google OAuth Client Secret</strong><small>내장 번들이 있으면 비워도 됨. 빈칸 저장 시 기존값 유지</small></div>
            <input type="password" name="GOOGLE_OAUTH_CLIENT_SECRET" value="" autocomplete="new-password" {oauth_disabled_attr} />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>Google OAuth Redirect URI</strong><small>비우면 현재 로컬 UI 주소 자동 사용</small></div>
            <input type="text" name="GOOGLE_OAUTH_REDIRECT_URI" value="{esc('GOOGLE_OAUTH_REDIRECT_URI')}" placeholder="http://127.0.0.1:5050/oauth/google/callback" {oauth_disabled_attr} />
          </div>
          <div class="settings-row">
            <div class="settings-label"><strong>연결 상태</strong><small>{html.escape(str(env_map.get('GOOGLE_OAUTH_CONNECTED_EMAIL', '') or '미연결'))}</small></div>
            <div class="button-row">
              {oauth_setup_connect_html}
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <p class="card-title">3) 웹 보안 (선택)</p>
        <div class="settings-row">
          <div class="settings-label"><strong>웹 콘솔 비밀번호</strong><small>원격 접근(0.0.0.0) 시 필수</small></div>
          <input type="password" name="WEB_PASSWORD" value="" autocomplete="new-password" />
        </div>
        <div class="settings-row">
          <div class="settings-label"><strong>원격 host 허용 (비권장)</strong><small>ALLOW_INSECURE_REMOTE_WEB — HTTPS 미적용 원격 접근을 허용합니다.</small></div>
          <input type="checkbox" name="ALLOW_INSECURE_REMOTE_WEB" {checked_remote} />
        </div>
        <div class="settings-row">
          <div class="settings-label"><strong>OS 키체인 저장</strong><small>USE_KEYRING — 비밀값을 OS 보안 저장소에 저장합니다.</small></div>
          <input type="checkbox" name="USE_KEYRING" {checked_keyring} />
        </div>
      </div>

      <div class="card">
        <p class="card-title">4) 연결 진단</p>
        <button type="button" class="btn-ghost" onclick="runHealthcheck()">연결 진단 실행</button>
        <pre id="healthcheck-result" style="margin-top:10px; white-space:pre-wrap;">아직 실행하지 않음</pre>
      </div>

      <div class="gap-8">
        <button type="submit">✅ Setup 완료하고 저장</button>
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
        box.textContent = '진단 중...';
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
          box.textContent = '진단 실패';
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
    oauth_bundle_ready_text = "있음" if oauth_defaults.get("bundle_ready") else "없음"
    oauth_source_text = "Settings 입력값"
    if oauth_defaults.get("using_bundled_client_id") or oauth_defaults.get("using_bundled_client_secret"):
        oauth_source_text = "배포판 내장 번들"
    oauth_disabled_attr = "" if OAUTH_UI_ENABLED else "disabled"
    if OAUTH_UI_ENABLED:
        oauth_settings_controls_html = (
            f'<a class="btn btn-ghost" href="{url_for("google_oauth_start")}">Google 로그인 연결</a>'
            '<button type="button" class="btn-danger" onclick="disconnectGoogleOauth()">연결 해제</button>'
        )
    else:
        oauth_settings_controls_html = (
            '<button type="button" class="btn btn-ghost" disabled>Google 로그인 연결</button>'
            '<button type="button" class="btn-danger" disabled>연결 해제</button>'
        )
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
          <p class="card-title" style="color:#92400e;">⚠️ 운영 경고</p>
          <ul style="margin:0;padding-left:18px;color:#92400e;line-height:1.7;">{rows}</ul>
        </div>
        """

    body = f"""
    <div class="page-header">
      <h1>Settings</h1>
      <p>설정 파일 위치: <code>{html.escape(str(env_path))}</code></p>
      <p class="small">외부 접근(`--host 0.0.0.0`)은 기본 차단됩니다. 테스트 목적일 때만 `ALLOW_INSECURE_REMOTE_WEB=true` + `WEB_PASSWORD`를 사용하세요.</p>
    </div>
    {warnings_html}

    <form method="post">
      <input type="hidden" name="app_token" value="{APP_AUTH_TOKEN}" />

      <div class="card">
        <p class="card-title">📧 이메일 설정</p>
        <p class="small" style="margin:0 0 12px;">Google OAuth 내장 번들: <strong>{oauth_bundle_ready_text}</strong> (현재 소스: {html.escape(oauth_source_text)})</p>
        <p class="small" style="margin:0 0 12px;">{'' if OAUTH_UI_ENABLED else '현재 버전에서는 OAuth 설정 UI가 비활성화되어 있습니다. Gmail 앱 비밀번호 방식을 사용하세요.'}</p>
        <div class="settings-grid">
          <div class="settings-row">
            <div class="settings-label">
              <strong>발신 Gmail 주소</strong>
              <small>GMAIL_ADDRESS</small>
            </div>
            <input type="text" name="GMAIL_ADDRESS" value="{esc('GMAIL_ADDRESS')}" placeholder="example@gmail.com" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Gmail 앱 비밀번호</strong>
              <small>Google 앱 비밀번호 16자리. OAuth를 쓰면 선택 사항입니다. <a href="https://myaccount.google.com/apppasswords" target="_blank">🔗 발급 방법</a>. 빈칸 저장 시 기존값 유지.</small>
            </div>
            <input type="password" name="GMAIL_APP_PASSWORD" value="" placeholder="xxxx xxxx xxxx xxxx" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>수신 이메일</strong>
              <small>RECIPIENT_EMAIL — 리포트를 받을 주소</small>
            </div>
            <input type="text" name="RECIPIENT_EMAIL" value="{esc('RECIPIENT_EMAIL')}" placeholder="recipient@example.com" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>웹 콘솔 비밀번호</strong>
              <small>WEB_PASSWORD — 외부 접근(0.0.0.0) 시 필수, 빈칸 저장 시 기존값 유지</small>
            </div>
            <input type="password" name="WEB_PASSWORD" value="" placeholder="웹 콘솔 로그인 비밀번호" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>원격 host 허용 (비권장)</strong>
              <small>ALLOW_INSECURE_REMOTE_WEB — HTTPS 없는 원격 접근을 허용합니다.</small>
            </div>
            <input type="checkbox" name="ALLOW_INSECURE_REMOTE_WEB" {remote_checked} />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>OS 키체인 저장</strong>
              <small>USE_KEYRING — 비밀값을 OS 보안 저장소에 저장</small>
            </div>
            <input type="checkbox" name="USE_KEYRING" {keyring_checked} />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Google OAuth 사용</strong>
              <small>ENABLE_GOOGLE_OAUTH — 앱 비밀번호 없이 Gmail 연동</small>
            </div>
            <input type="checkbox" name="ENABLE_GOOGLE_OAUTH" {google_oauth_checked} {oauth_disabled_attr} />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>OAuth를 Gmail 발송에 사용</strong>
              <small>GOOGLE_OAUTH_USE_FOR_GMAIL</small>
            </div>
            <input type="checkbox" name="GOOGLE_OAUTH_USE_FOR_GMAIL" {google_oauth_gmail_checked} {oauth_disabled_attr} />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Google OAuth Client ID</strong>
              <small>GOOGLE_OAUTH_CLIENT_ID (내장 번들이 있으면 비워도 동작)</small>
            </div>
            <input type="text" name="GOOGLE_OAUTH_CLIENT_ID" value="{esc('GOOGLE_OAUTH_CLIENT_ID')}" {oauth_disabled_attr} />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Google OAuth Client Secret</strong>
              <small>GOOGLE_OAUTH_CLIENT_SECRET — 내장 번들이 있으면 비워도 동작. 빈칸 저장 시 기존값 유지</small>
            </div>
            <input type="password" name="GOOGLE_OAUTH_CLIENT_SECRET" value="" autocomplete="new-password" {oauth_disabled_attr} />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Google OAuth Redirect URI</strong>
              <small>GOOGLE_OAUTH_REDIRECT_URI — 비우면 현재 로컬 UI 주소 자동 사용</small>
            </div>
            <input type="text" name="GOOGLE_OAUTH_REDIRECT_URI" value="{esc('GOOGLE_OAUTH_REDIRECT_URI')}" placeholder="http://127.0.0.1:5050/oauth/google/callback" {oauth_disabled_attr} />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Google 연동 계정</strong>
              <small>{html.escape(str(env_map.get('GOOGLE_OAUTH_CONNECTED_EMAIL', '') or '미연결'))}</small>
            </div>
            <div class="button-row">
              {oauth_settings_controls_html}
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <p class="card-title">⏰ 발송 스케줄</p>
        <div class="settings-grid">
          <div class="settings-row">
            <div class="settings-label">
              <strong>타임존</strong>
              <small>TIMEZONE — 예: Asia/Seoul</small>
            </div>
            <input type="text" name="TIMEZONE" value="{esc('TIMEZONE')}" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>발송 시각</strong>
              <small>매일 논문 리포트를 보내는 시각</small>
            </div>
            <div>
              <input type="time" id="send_time_picker" value="{send_hour_padded}:{send_minute_padded}" onchange="splitTime(this.value)" style="width:140px;" />
              <input type="hidden" name="SEND_HOUR" id="send_hour_hidden" value="{esc('SEND_HOUR')}" />
              <input type="hidden" name="SEND_MINUTE" id="send_minute_hidden" value="{esc('SEND_MINUTE')}" />
            </div>
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>발송 주기</strong>
              <small>SEND_FREQUENCY — daily / every_3_days / weekly</small>
            </div>
            <select name="SEND_FREQUENCY" style="width:180px;">
              <option value="daily" {"selected" if env_map.get("SEND_FREQUENCY", "daily") == "daily" else ""}>매일</option>
              <option value="every_3_days" {"selected" if env_map.get("SEND_FREQUENCY", "daily") == "every_3_days" else ""}>3일마다</option>
              <option value="weekly" {"selected" if env_map.get("SEND_FREQUENCY", "daily") == "weekly" else ""}>매주(7일)</option>
            </select>
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>주기 기준일</strong>
              <small>SEND_ANCHOR_DATE — YYYY-MM-DD</small>
            </div>
            <input type="text" name="SEND_ANCHOR_DATE" value="{esc('SEND_ANCHOR_DATE')}" placeholder="2026-01-01" style="width:160px;" />
          </div>
        </div>
      </div>

      <div class="card">
        <p class="card-title">🔍 검색 파라미터</p>
        <div class="settings-grid">
          <div class="settings-row">
            <div class="settings-label">
              <strong>탐색 기간 (시간)</strong>
              <small>LOOKBACK_HOURS — 최근 몇 시간 이내 논문 수집</small>
            </div>
            <input type="number" name="LOOKBACK_HOURS" min="1" value="{esc('LOOKBACK_HOURS')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>최대 논문 수</strong>
              <small>MAX_PAPERS — 리포트에 포함할 최대 논문 수</small>
            </div>
            <input type="number" name="MAX_PAPERS" min="1" value="{esc('MAX_PAPERS')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>최소 관련성 점수</strong>
              <small>MIN_RELEVANCE_SCORE — LLM 미사용 시 키워드 점수 필터</small>
            </div>
            <input type="text" name="MIN_RELEVANCE_SCORE" value="{esc('MIN_RELEVANCE_SCORE')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>arXiv 쿼리당 최대 결과</strong>
              <small>ARXIV_MAX_RESULTS_PER_QUERY</small>
            </div>
            <input type="number" name="ARXIV_MAX_RESULTS_PER_QUERY" min="1" value="{esc('ARXIV_MAX_RESULTS_PER_QUERY')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>PubMed 쿼리당 최대 결과</strong>
              <small>PUBMED_MAX_IDS_PER_QUERY</small>
            </div>
            <input type="number" name="PUBMED_MAX_IDS_PER_QUERY" min="1" value="{esc('PUBMED_MAX_IDS_PER_QUERY')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Semantic Scholar 소스 사용</strong>
              <small>ENABLE_SEMANTIC_SCHOLAR</small>
            </div>
            <input type="checkbox" name="ENABLE_SEMANTIC_SCHOLAR" {semantic_checked} />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Google Scholar 소스 사용</strong>
              <small>ENABLE_GOOGLE_SCHOLAR (SerpAPI 기반)</small>
            </div>
            <input type="checkbox" name="ENABLE_GOOGLE_SCHOLAR" {google_scholar_checked} />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Semantic Scholar 쿼리당 최대 결과</strong>
              <small>SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY</small>
            </div>
            <input type="number" name="SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY" min="1" max="100" value="{esc('SEMANTIC_SCHOLAR_MAX_RESULTS_PER_QUERY')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Google Scholar 쿼리당 최대 결과</strong>
              <small>GOOGLE_SCHOLAR_MAX_RESULTS_PER_QUERY (권장 10~20)</small>
            </div>
            <input type="number" name="GOOGLE_SCHOLAR_MAX_RESULTS_PER_QUERY" min="1" max="20" value="{esc('GOOGLE_SCHOLAR_MAX_RESULTS_PER_QUERY')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>소스당 최대 검색 쿼리 수</strong>
              <small>MAX_SEARCH_QUERIES_PER_SOURCE</small>
            </div>
            <input type="number" name="MAX_SEARCH_QUERIES_PER_SOURCE" min="1" value="{esc('MAX_SEARCH_QUERIES_PER_SOURCE')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Send Now 쿨다운(초)</strong>
              <small>SEND_NOW_COOLDOWN_SECONDS — 수동 발송 연속 호출 방지</small>
            </div>
            <input type="number" name="SEND_NOW_COOLDOWN_SECONDS" min="0" value="{esc('SEND_NOW_COOLDOWN_SECONDS')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>중복 발송 보관일</strong>
              <small>SENT_HISTORY_DAYS — 이미 보낸 논문 ID를 제외하는 기간</small>
            </div>
            <input type="number" name="SENT_HISTORY_DAYS" min="1" value="{esc('SENT_HISTORY_DAYS')}" style="width:120px;" />
          </div>
        </div>
      </div>

      <div class="card">
        <p class="card-title">🤖 LLM / Gemini / Cerebras 설정</p>
        <p class="small" style="margin:0 0 12px;">API 키가 없거나 LLM 실패 시 키워드 기반 폴백 모드로 동작합니다.</p>
        <div class="settings-grid">
          <div class="settings-row">
            <div class="settings-label">
              <strong>LLM 에이전트 사용</strong>
              <small>ENABLE_LLM_AGENT — LLM으로 관련성 자동 평가</small>
            </div>
            <input type="checkbox" name="ENABLE_LLM_AGENT" {checked} />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Gemini API Key</strong>
              <small><a href="https://aistudio.google.com/" target="_blank">🔗 발급 방법</a>. 빈칸 저장 시 기존값 유지</small>
            </div>
            <input type="password" name="GEMINI_API_KEY" value="" placeholder="AI Studio에서 발급받은 키" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Gemini 모델</strong>
              <small>GEMINI_MODEL — 기본값 gemini-3.1-flash</small>
            </div>
            <input type="text" name="GEMINI_MODEL" value="{esc('GEMINI_MODEL')}" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>요약 출력 언어</strong>
              <small>OUTPUT_LANGUAGE — 예: en, ko, ja, es, fr</small>
            </div>
            <input type="text" name="OUTPUT_LANGUAGE" value="{esc('OUTPUT_LANGUAGE')}" style="width:140px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>고급 추론 사용</strong>
              <small>ENABLE_GEMINI_ADVANCED_REASONING — 체크 시 Gemini 3.1 Pro를 사용</small>
            </div>
            <input type="checkbox" name="ENABLE_GEMINI_ADVANCED_REASONING" {gemini_advanced_checked} />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Cerebras fallback 사용</strong>
              <small>ENABLE_CEREBRAS_FALLBACK — Gemini 실패 시 자동 백업 호출</small>
            </div>
            <input type="checkbox" name="ENABLE_CEREBRAS_FALLBACK" {cerebras_checked} />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Cerebras API Key</strong>
              <small><a href="https://cloud.cerebras.ai/" target="_blank">🔗 발급 방법</a>. 빈칸 저장 시 기존값 유지</small>
            </div>
            <input type="password" name="CEREBRAS_API_KEY" value="" placeholder="Cerebras API 키" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Cerebras 모델</strong>
              <small>CEREBRAS_MODEL — 예: gpt-oss-120b</small>
            </div>
            <input type="text" name="CEREBRAS_MODEL" value="{esc('CEREBRAS_MODEL')}" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Cerebras API Base</strong>
              <small>CEREBRAS_API_BASE — 기본값 권장 유지</small>
            </div>
            <input type="text" name="CEREBRAS_API_BASE" value="{esc('CEREBRAS_API_BASE')}" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Semantic Scholar API Key</strong>
              <small><a href="https://www.semanticscholar.org/product/api" target="_blank">🔗 발급 방법</a>. 빈칸 저장 시 기존값 유지</small>
            </div>
            <input type="password" name="SEMANTIC_SCHOLAR_API_KEY" value="" placeholder="Semantic Scholar API 키" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Google Scholar API Key</strong>
              <small><a href="https://serpapi.com/" target="_blank">🔗 SerpAPI 발급</a>. 빈칸 저장 시 기존값 유지</small>
            </div>
            <input type="password" name="GOOGLE_SCHOLAR_API_KEY" value="" placeholder="SerpAPI 키" autocomplete="new-password" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Gemini 최대 논문 수</strong>
              <small>GEMINI_MAX_PAPERS</small>
            </div>
            <input type="number" name="GEMINI_MAX_PAPERS" min="1" value="{esc('GEMINI_MAX_PAPERS')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>LLM 관련성 임계점</strong>
              <small>LLM_RELEVANCE_THRESHOLD — 이 점수 이상만 리포트 포함</small>
            </div>
            <input type="number" step="0.1" name="LLM_RELEVANCE_THRESHOLD" min="1" max="10" value="{esc('LLM_RELEVANCE_THRESHOLD')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>LLM 배치 크기</strong>
              <small>LLM_BATCH_SIZE</small>
            </div>
            <input type="number" name="LLM_BATCH_SIZE" min="1" value="{esc('LLM_BATCH_SIZE')}" style="width:120px;" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>LLM 최대 후보 수</strong>
              <small>LLM_MAX_CANDIDATES — 기본 30, 최대 80 (3일/주간 주기에서는 비선형 확장 적용)</small>
            </div>
            <input type="number" name="LLM_MAX_CANDIDATES" min="1" max="80" value="{esc('LLM_MAX_CANDIDATES')}" style="width:120px;" />
          </div>
        </div>
      </div>

      <div class="card">
        <p class="card-title">📁 기타</p>
        <div class="settings-grid">
          <div class="settings-row">
            <div class="settings-label">
              <strong>NCBI API Key</strong>
              <small>NCBI_API_KEY — PubMed 처리량 안정화에 권장</small>
            </div>
            <input type="text" name="NCBI_API_KEY" value="{esc('NCBI_API_KEY')}" />
          </div>
          <div class="settings-row">
            <div class="settings-label">
              <strong>Topics 파일 경로</strong>
              <small>USER_TOPICS_FILE</small>
            </div>
            <input type="text" name="USER_TOPICS_FILE" value="{esc('USER_TOPICS_FILE')}" />
          </div>
        </div>
      </div>

      <div class="gap-8" style="padding:4px 0 8px;">
        <button type="submit">💾 저장</button>
        <span class="small">저장 후 스케줄러가 자동으로 재시작됩니다.</span>
      </div>
    </form>

    <script>
      function splitTime(val) {{
        const parts = val.split(':');
        document.getElementById('send_hour_hidden').value = parseInt(parts[0], 10);
        document.getElementById('send_minute_hidden').value = parseInt(parts[1], 10);
      }}

      async function disconnectGoogleOauth() {{
        if (!confirm('Google OAuth 연결을 해제할까요?')) return;
        const res = await fetch('{url_for("google_oauth_disconnect")}', {{
          method: 'POST',
          headers: {{ 'X-App-Token': window.APP_TOKEN || '' }},
        }});
        if (!res.ok) {{
          alert('연결 해제 실패');
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
      <p>프로젝트 컨텍스트를 입력한 뒤 <b>Keyword / Query 생성</b> 버튼으로 키워드/쿼리 초안을 만들고, 수동 수정 후 저장하세요.</p>
      <p class="small" style="margin-top:4px;">저장된 쿼리는 매일 실행 시 그대로 사용됩니다. (자동 재생성되지 않음)</p>
      <p class="small" style="margin-top:4px;">현재 파일: <code>__TOPICS_PATH__</code></p>
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
        <button type="button" id="btn-generate" class="btn-success" onclick="generateTopics()">Keyword / Query 생성</button>
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
      <span class="small">저장 후 화면이 새로고침됩니다.</span>
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
          alert('먼저 프로젝트를 입력하세요.');
          return;
        }

        const btn = document.getElementById('btn-generate');
        const status = document.getElementById('generate-status');
        const originalLabel = btn.textContent;
        btn.disabled = true;
        btn.textContent = '🔄 생성 중...';
        status.innerText = 'LLM으로 keyword/query 생성 중...';

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
          status.innerText = `생성 완료: ${topics.length}개 topic`;
        } catch (err) {
          status.innerText = '생성 실패';
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
          alert('projects 또는 topics 중 하나는 입력해야 합니다.');
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
    manual_path = Path("MANUAL_KR.md")
    if not manual_path.exists():
        return render_page(
            "Manual",
            '<div class="card"><h2>Manual</h2><p class="text-danger">MANUAL_KR.md 파일을 찾을 수 없습니다.</p></div>',
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
      <p>Paper Morning 사용 방법 가이드</p>
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
            '<div class="card"><h2>License</h2><p class="text-danger">LICENSE 파일을 찾을 수 없습니다.</p></div>',
            active_page="license",
        )

    license_text = license_path.read_text(encoding="utf-8-sig")
    body = f"""
    <div class="page-header">
      <h1>⚖️ License</h1>
      <p>현재 라이선스: GNU AGPLv3</p>
    </div>
    <div class="card">
      <p class="small" style="margin-top:0;">문의가 필요하면 <a href="mailto:nineclas@gmail.com">nineclas@gmail.com</a> 으로 메일 주세요.</p>
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
      <p>실행 로그를 확인합니다. 파일: <code id="log-path">-</code></p>
    </div>

    <div class="card">
      <div class="button-row" style="margin-bottom:10px;">
        <label class="small" style="display:flex; align-items:center; gap:6px;">
          표시 줄 수
          <input id="log-lines" type="number" min="50" max="2000" step="50" value="400" style="width:90px;" />
        </label>
        <button type="button" onclick="loadLogs()">새로고침</button>
        <button type="button" class="btn-ghost" id="btn-auto" onclick="toggleAuto()">자동 새로고침: OFF</button>
        <span id="log-meta" class="small"></span>
      </div>
      <pre id="log-viewer" style="max-height:600px;">로딩 중...</pre>
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
          btn.innerText = '자동 새로고침: OFF';
          return;
        }}
        autoTimer = setInterval(loadLogs, 5000);
        btn.innerText = '자동 새로고침: ON (5s)';
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
