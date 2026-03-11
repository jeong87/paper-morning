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
from paper_digest_app import (
    AppConfig,
    Paper,
    compose_email_html,
    save_scheduled_send_lock,
    should_send_now,
)


def make_config(timezone_name: str = "America/New_York") -> AppConfig:
    return AppConfig(
        gmail_address="sender@example.com",
        gmail_app_password="app-password",
        recipient_email="receiver@example.com",
        enable_google_oauth=False,
        google_oauth_use_for_gmail=False,
        google_oauth_client_id="",
        google_oauth_client_secret="",
        google_oauth_refresh_token="",
        timezone_name=timezone_name,
        send_hour=9,
        send_minute=0,
        send_time_window_minutes=15,
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
        cerebras_api_key="",
        cerebras_model="gpt-oss-120b",
        cerebras_api_base="https://api.cerebras.ai/v1",
        enable_cerebras_fallback=True,
        gemini_max_papers=5,
        llm_relevance_threshold=7.0,
        llm_batch_size=5,
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
    def test_manual_default_is_english(self) -> None:
        app = web_app.app
        app.config["TESTING"] = True
        with patch("web_app.read_env_map", return_value={"UI_LANGUAGE": "en", "WEB_PASSWORD": ""}), patch(
            "web_app.get_web_password", return_value=""
        ):
            with app.test_client() as client:
                response = client.get("/manual")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Paper Morning Manual (GitHub Actions Operations)", html)
        self.assertNotIn("Paper Morning 매뉴얼", html)

    def test_manual_supports_korean_query_param(self) -> None:
        app = web_app.app
        app.config["TESTING"] = True
        with patch("web_app.read_env_map", return_value={"UI_LANGUAGE": "en", "WEB_PASSWORD": ""}), patch(
            "web_app.get_web_password", return_value=""
        ):
            with app.test_client() as client:
                response = client.get("/manual?lang=ko")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Paper Morning 매뉴얼", html)

    def test_output_language_localizes_email_headers(self) -> None:
        now_utc = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
        since_utc = now_utc - timedelta(hours=24)
        paper = Paper(
            paper_id="p1",
            title="A paper title",
            abstract="An abstract for testing localization.",
            url="https://example.com",
            authors=["A. Author"],
            published_at_utc=now_utc - timedelta(hours=2),
            source="arXiv",
            score=9.0,
            llm_relevance_text="",
            llm_core_point_text="",
            llm_usefulness_text="",
        )
        html = compose_email_html(
            papers=[paper],
            now_utc=now_utc,
            since_utc=since_utc,
            timezone_name="UTC",
            output_language="ja",
            stats=None,
        )
        self.assertIn("研究との関連性", html)
        self.assertIn("主要な発見", html)
        self.assertIn("活用方法", html)

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

                should_send_again, reason, _ = should_send_now(config, now_utc + timedelta(minutes=5))
                self.assertFalse(should_send_again)
                self.assertIn("Already sent for local date", reason)


if __name__ == "__main__":
    unittest.main()
