from __future__ import annotations

from typing import Any, Dict


LLM_RELEVANCE_MODE_DEFAULT = "balanced"

LLM_RELEVANCE_MODE_POLICIES: Dict[str, Dict[str, Any]] = {
    "strict": {
        "label": "Strict",
        "threshold": 7.5,
        "prompt_lines": [
            "Optimize for precision over breadth.",
            "Prefer papers that directly overlap in task, modality, target population, evaluation setup, or deployment goal.",
            "Adjacent methods papers can still score, but only if the reuse path is concrete and unusually strong.",
            "Broad theme overlap without direct execution value should usually stay in 1-4.",
            "Use this rubric:",
            "  9-10: near-direct project match or clear must-read for the active project.",
            "  7-8: strong fit with only minor mismatch; 8+ should feel directly actionable soon.",
            "  5-6: adjacent but useful method or baseline reference; interesting, but not core.",
            "  3-4: weak fit; broad domain similarity only.",
            "  1-2: little meaningful connection.",
        ],
    },
    "balanced": {
        "label": "Balanced",
        "threshold": 6.0,
        "prompt_lines": [
            "Score for practical usefulness to the user's project, not only exact topic overlap.",
            "Direct project matches should score highest, but clearly transferable methods papers may also score well.",
            "Do not over-penalize a paper just because disease/population is different if the modality, task design, evaluation setup, or modeling approach is clearly reusable.",
            "If overlap is only generic buzzwords (e.g., 'medical AI', 'foundation model') with no concrete methodological or clinical connection, usually keep the score in 3-5.",
            "Use this rubric:",
            "  9-10: near-direct project match or must-read paper for the current project.",
            "  7-8: strong fit; either direct overlap or highly reusable method/evaluation/data setup.",
            "  5-6: partial or adjacent fit; useful for methodology, baselines, framing, or monitoring nearby work.",
            "  3-4: weak fit; only broad theme overlap.",
            "  1-2: little meaningful connection.",
            "Use the full range when justified. Do not force most papers into 3-6 if several are genuinely strong.",
            "Be selective, but allow adjacent high-utility papers to pass when the reuse case is concrete.",
        ],
    },
    "discovery": {
        "label": "Discovery",
        "threshold": 5.0,
        "prompt_lines": [
            "Optimize for high-upside discovery, not only immediate direct overlap.",
            "Reward papers that can expand the user's search space through reusable methods, datasets, evaluation ideas, or problem reframing.",
            "Allow domain, population, or modality mismatch when the methodological transfer path is concrete and credible.",
            "Still keep generic buzzword overlap low; curiosity alone is not enough.",
            "Use this rubric:",
            "  9-10: direct match or exceptionally high-upside adjacent paper that could materially change the project.",
            "  7-8: strong adjacent fit with clear reuse potential in method, benchmark, or data strategy.",
            "  5-6: exploratory but worthwhile; useful for idea expansion, baselines, nearby tasks, or future iteration.",
            "  3-4: weak exploratory signal; interesting but hard to connect concretely.",
            "  1-2: little meaningful value for this project.",
            "Let promising adjacent work pass when the usefulness explanation is concrete.",
        ],
    },
}


def _normalize_token(raw: Any) -> str:
    return " ".join(str(raw or "").strip().lower().split())


def normalize_relevance_mode(raw: Any) -> str:
    value = _normalize_token(raw)
    if value in {"strict", "precision", "precise"}:
        return "strict"
    if value in {"discovery", "discover", "explore", "exploratory"}:
        return "discovery"
    return LLM_RELEVANCE_MODE_DEFAULT


def get_relevance_mode_policy(mode: str) -> Dict[str, Any]:
    return LLM_RELEVANCE_MODE_POLICIES[normalize_relevance_mode(mode)]


def relevance_mode_label(mode: str) -> str:
    return str(get_relevance_mode_policy(mode).get("label", "Balanced"))


def relevance_mode_threshold(mode: str, fallback_threshold: float) -> float:
    policy = get_relevance_mode_policy(mode)
    value = policy.get("threshold")
    if isinstance(value, (int, float)):
        return float(value)
    return fallback_threshold
