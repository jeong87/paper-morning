from __future__ import annotations

import sys
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.paper_digest_app import DigestStats, Paper, compose_email_html


def build_demo_papers(now_utc: datetime) -> list[Paper]:
    return [
        Paper(
            paper_id="demo-001",
            title="Multi-Scale Vision Transformer for Robust Medical Image Segmentation",
            abstract=(
                "This paper proposes a multi-scale transformer architecture for cross-device "
                "medical image segmentation with strong domain generalization across centers."
            ),
            url="https://example.org/papers/demo-001",
            authors=["A. Kim", "R. Chen", "M. Patel"],
            published_at_utc=now_utc - timedelta(hours=6),
            source="arXiv",
            score=9.2,
            topic="LLM-Relevance",
            matched_keywords=["medical imaging", "segmentation", "transformer"],
            llm_relevance_ko=(
                "High relevance: this directly matches robust segmentation under domain shift."
            ),
            llm_core_point_ko=(
                "1) Multi-scale token mixer for fine boundaries.\n"
                "2) Cross-center training with robust augmentations.\n"
                "3) Consistent gains on external validation cohorts."
            ),
            llm_usefulness_ko=(
                "Useful for improving generalization in real-world hospital data.\n"
                "Can inform your model architecture and validation protocol."
            ),
        ),
        Paper(
            paper_id="demo-002",
            title="Clinical Risk Prediction from EHR Notes with Retrieval-Augmented Modeling",
            abstract=(
                "A retrieval-augmented framework combines structured EHR variables and free-text "
                "clinical notes for early prognosis prediction under label sparsity."
            ),
            url="https://example.org/papers/demo-002",
            authors=["J. Smith", "L. Garcia"],
            published_at_utc=now_utc - timedelta(hours=11),
            source="PubMed",
            score=7.8,
            topic="LLM-Relevance",
            matched_keywords=["clinical notes", "risk prediction", "multimodal"],
            llm_relevance_ko=(
                "Good relevance: aligned with multimodal prognosis from structured + text signals."
            ),
            llm_core_point_ko=(
                "1) Retrieval module improves calibration under sparse labels.\n"
                "2) Better AUROC than note-only and table-only baselines.\n"
                "3) Includes ablation by note quality and missingness."
            ),
            llm_usefulness_ko=(
                "Applicable when combining tabular and note data in clinical prediction pipelines.\n"
                "Provides practical guidance for missing-data handling."
            ),
        ),
        Paper(
            paper_id="demo-003",
            title="Efficient Distillation for Biomedical QA over Large Literature Corpora",
            abstract=(
                "The study introduces a lightweight distillation strategy for retrieval-augmented "
                "biomedical QA, reducing latency while preserving answer quality."
            ),
            url="https://example.org/papers/demo-003",
            authors=["N. Rossi", "P. Nguyen", "D. Allen"],
            published_at_utc=now_utc - timedelta(hours=18),
            source="SemanticScholar",
            score=6.3,
            topic="LLM-Relevance",
            matched_keywords=["RAG", "biomedical QA", "distillation"],
            llm_relevance_ko=(
                "Moderate relevance: useful for deployment efficiency and QA system scaling."
            ),
            llm_core_point_ko=(
                "1) Distilled retriever-reader stack lowers inference cost.\n"
                "2) Maintains strong accuracy on biomedical QA benchmarks.\n"
                "3) Includes latency/quality trade-off analysis."
            ),
            llm_usefulness_ko=(
                "Helpful for productionizing literature QA systems with constrained resources.\n"
                "Can guide deployment optimization decisions."
            ),
        ),
    ]


def build_demo_stats() -> DigestStats:
    return DigestStats(
        arxiv_candidates=52,
        pubmed_candidates=37,
        semantic_scholar_candidates=28,
        google_scholar_candidates=19,
        total_candidates=136,
        post_time_filter_candidates=64,
        ranking_mode="llm",
        ranking_threshold=6.0,
        scoring_candidates=30,
        scored_count=30,
        pass_count=12,
        score_buckets={"9-10": 3, "7-8": 5, "5-6": 4, "1-4": 15, "0": 3},
        estimated_llm_calls_upper_bound=6,
        final_selected=3,
        query_strategy="saved-topics",
        send_frequency="daily",
        lookback_hours=24,
        llm_max_candidates_base=30,
        llm_max_candidates_effective=30,
    )


def render_demo_html() -> str:
    now_utc = datetime.now(timezone.utc)
    since_utc = now_utc - timedelta(hours=24)
    papers = build_demo_papers(now_utc)
    stats = build_demo_stats()
    html_body = compose_email_html(
        papers=papers,
        now_utc=now_utc,
        since_utc=since_utc,
        timezone_name="UTC",
        stats=stats,
    )
    banner = (
        "<div style=\"max-width:980px;margin:10px auto 6px;font-family:Arial,sans-serif;"
        "font-size:13px;color:#334155;\">"
        "<b>Paper Morning Demo</b> - synthetic sample output for preview purposes"
        "</div>"
    )
    return re.sub(r"(<body[^>]*>)", r"\1" + banner, html_body, count=1, flags=re.IGNORECASE)


def main() -> int:
    output_path = Path("docs/demo/index.html").resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_demo_html(), encoding="utf-8")
    print(f"Demo HTML generated: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
