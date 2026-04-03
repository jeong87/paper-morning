import unittest
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = ROOT_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from scoring_policy import (
    LLM_RELEVANCE_MODE_DEFAULT,
    normalize_relevance_mode,
    relevance_mode_threshold,
)


class ScoringPolicyTests(unittest.TestCase):
    def test_relevance_mode_aliases_normalize(self) -> None:
        self.assertEqual(normalize_relevance_mode("precision"), "strict")
        self.assertEqual(normalize_relevance_mode("explore"), "discovery")
        self.assertEqual(normalize_relevance_mode(""), LLM_RELEVANCE_MODE_DEFAULT)

    def test_relevance_mode_thresholds_are_stable(self) -> None:
        self.assertEqual(relevance_mode_threshold("strict", 0.0), 7.5)
        self.assertEqual(relevance_mode_threshold("balanced", 0.0), 6.0)
        self.assertEqual(relevance_mode_threshold("discovery", 0.0), 5.0)


if __name__ == "__main__":
    unittest.main()
