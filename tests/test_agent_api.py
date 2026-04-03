import unittest
from pathlib import Path
from unittest.mock import patch
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = ROOT_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import web_app


class AgentApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = web_app.app
        self.app.config["TESTING"] = True

    def test_agent_endpoint_rejects_non_local_requests(self) -> None:
        with self.app.test_client() as client:
            response = client.post(
                "/api/agent/search",
                json={"research_context": "find ICU multimodal papers"},
                environ_base={"REMOTE_ADDR": "192.168.0.8"},
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json["status"], "error")

    def test_agent_endpoint_returns_json_when_token_matches(self) -> None:
        expected = {
            "status": "ok",
            "request": {"project_name": "Demo"},
            "meta": {"used_provider": "gemini", "used_model": "gemini-3.1-flash"},
            "topic": {"name": "demo"},
            "papers": [],
            "diagnostics": [],
        }
        with patch("web_app.get_agent_api_token", return_value="token"), patch(
            "web_app.load_config", return_value=object()
        ), patch("web_app.search_papers_for_agent", return_value=expected) as mock_search:
            with self.app.test_client() as client:
                response = client.post(
                    "/api/agent/search",
                    json={
                        "project_name": "Demo",
                        "research_context": "find ICU multimodal papers",
                        "top_k": 3,
                        "source_policy": {"arxiv": False, "pubmed": True},
                    },
                    headers={"X-Agent-Token": "token"},
                    environ_base={"REMOTE_ADDR": "127.0.0.1"},
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "ok")
        mock_search.assert_called_once()


if __name__ == "__main__":
    unittest.main()
