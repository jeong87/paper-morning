import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = ROOT_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import web_app
from paper_digest_app import AppConfig, save_scheduled_send_lock, should_send_now


def make_config(timezone_name: str = "America/New_York") -> AppConfig:
    return AppConfig(
        gmail_address="sender@example.com",
        gmail_app_password="app-password",
        recipient_email="receiver@example.com",
        delivery_mode="local_inbox",
        auto_open_digest_window=True,
        enable_google_oauth=False,
        google_oauth_use_for_gmail=False,
        google_oauth_client_id="",
        google_oauth_client_secret="",
        google_oauth_refresh_token="",
        timezone_name=timezone_name,
        send_hour=9,
        send_minute=0,
        send_time_window_minutes=15,
        search_intent_default="best_match",
        search_time_horizon_default="1y",
        max_papers=5,
        lookback_hours=24,
        min_relevance_score=6.0,
        arxiv_max_results_per_query=25,
        pubmed_max_ids_per_query=25,
        ncbi_api_key="",
        topic_profiles=[],
        research_projects=[],
        arxiv_queries=[],
        pubmed_queries=[],
        semantic_scholar_queries=[],
        enable_semantic_scholar=True,
        semantic_scholar_api_key="",
        semantic_scholar_max_results_per_query=20,
        google_scholar_queries=[],
        enable_google_scholar=False,
        google_scholar_api_key="",
        google_scholar_max_results_per_query=10,
        enable_llm_agent=True,
        gemini_api_key="",
        gemini_model="gemini-3.1-pro",
        openai_compat_api_key="",
        openai_compat_model="",
        openai_compat_api_base="",
        enable_openai_compat_fallback=False,
        cerebras_api_key="",
        cerebras_model="gpt-oss-120b",
        cerebras_api_base="https://api.cerebras.ai/v1",
        enable_cerebras_fallback=True,
        gemini_max_papers=5,
        llm_relevance_threshold=6.0,
        llm_max_candidates_base=30,
        llm_max_candidates=30,
        max_search_queries_per_source=4,
        sent_history_days=14,
        send_frequency="daily",
        send_interval_days=1,
        send_anchor_date="2026-01-01",
        output_language="en",
    )


class GlobalizationSmokeTests(unittest.TestCase):
    def test_settings_page_renders_agent_controls(self) -> None:
        app = web_app.app
        app.config["TESTING"] = True
        env_map = dict(web_app.DEFAULT_ENV_VALUES)
        env_map["SETUP_WIZARD_COMPLETED"] = "true"
        env_map["USE_KEYRING"] = "false"
        with patch("web_app.read_env_map", return_value=env_map), patch(
            "web_app.get_web_password", return_value=""
        ):
            with app.test_client() as client:
                response = client.get("/settings")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Agent API Settings", html)
        self.assertIn("OPENAI-Compatible API Base", html)

    def test_should_send_now_once_per_local_date(self) -> None:
        config = make_config("America/New_York")
        local_target = datetime(2026, 3, 10, 9, 0, tzinfo=ZoneInfo("America/New_York"))
        now_utc = local_target.astimezone(timezone.utc)

        with tempfile.TemporaryDirectory() as tmp_dir:
            lock_path = Path(tmp_dir) / "last_scheduled_send_local_date.json"
            with patch("paper_digest_app.get_scheduled_send_lock_path", return_value=lock_path):
                should_send, _, local_date = should_send_now(config, now_utc)
                self.assertTrue(should_send)

                save_scheduled_send_lock(
                    lock_path,
                    local_date.isoformat(),
                    now_utc,
                    config.timezone_name,
                )

                should_send_again, reason, _ = should_send_now(
                    config,
                    now_utc + timedelta(minutes=5),
                )
                self.assertFalse(should_send_again)
                self.assertIn("Already sent for local date", reason)


if __name__ == "__main__":
    unittest.main()
