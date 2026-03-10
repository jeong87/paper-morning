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
            title="Artificial Intelligence for Detecting Fetal Orofacial Clefts and Advancing Medical Education",
            abstract=(
                "Orofacial clefts are among the most common congenital craniofacial abnormalities, "
                "yet accurate prenatal detection remains challenging due to the scarcity of "
                "experienced specialists and the relative rarity of the condition."
            ),
            url="https://example.org/papers/demo-001",
            authors=["Yuanji Zhang", "Yuhao Huang", "Haoran Dou", "et al. (+27)"],
            published_at_utc=now_utc - timedelta(hours=10),
            source="arXiv",
            score=9.0,
            topic="Endoscopy FM",
            matched_keywords=["hospital", "ultrasound", "fetal diagnosis"],
            llm_relevance_ko=(
                "Shares methodological similarities with your endoscopy FM project in medical imaging AI diagnostics and education applications."
            ),
            llm_core_point_ko=(
                "An AI system trained on 45,139 ultrasound images detects fetal orofacial clefts "
                "with over 93% sensitivity and over 95% specificity."
            ),
            llm_usefulness_ko=(
                "Reference for improving diagnostic accuracy in your medical imaging deep learning "
                "models and education-focused deployment."
            ),
        ),
        Paper(
            paper_id="demo-002",
            title="Multimodal Large Language Models as Image Classifiers",
            abstract=(
                "Multimodal Large Language Models (MLLM) classification performance depends "
                "critically on evaluation protocol and ground truth quality."
            ),
            url="https://example.org/papers/demo-002",
            authors=["Nikita Kisel", "Illia Volkov", "Klara Janouskova", "Jiri Matas"],
            published_at_utc=now_utc - timedelta(hours=11, minutes=30),
            source="arXiv",
            score=8.0,
            topic="Endoscopy FM",
            matched_keywords=["large language model", "image classification", "MLLM"],
            llm_relevance_ko=(
                "Provides crucial insights into MLLM image classification performance and data quality improvement."
            ),
            llm_core_point_ko=(
                "MLLM classification performance is highly sensitive to evaluation protocol "
                "and ground truth quality, explaining conflicting benchmark outcomes."
            ),
            llm_usefulness_ko=(
                "Apply to your endoscopy FM evaluation pipeline to strengthen benchmarking methodology."
            ),
        ),
        Paper(
            paper_id="demo-003",
            title="Self-Supervised Pretraining for Endoscopic Video Analysis with Limited Annotations",
            abstract=(
                "Endoscopic video analysis remains challenging due to the high cost of obtaining "
                "expert annotations. This work proposes a temporal self-supervised pretraining framework."
            ),
            url="https://example.org/papers/demo-003",
            authors=["J. Kim", "S. Park", "M. Chen", "et al."],
            published_at_utc=now_utc - timedelta(hours=16),
            source="PubMed",
            score=7.0,
            topic="Endoscopy FM",
            matched_keywords=["endoscopy", "self-supervised", "video"],
            llm_relevance_ko=(
                "Directly addresses self-supervised learning for endoscopic video, overlapping with your FM pretraining research."
            ),
            llm_core_point_ko=(
                "A temporal contrastive learning approach achieves performance comparable to supervised methods while using only 10% labeled data."
            ),
            llm_usefulness_ko=(
                "The pretraining strategy can complement your FM pipeline and reduce annotation costs in endoscopic datasets."
            ),
        ),
    ]


def build_demo_stats() -> DigestStats:
    return DigestStats(
        arxiv_candidates=28,
        pubmed_candidates=19,
        semantic_scholar_candidates=0,
        google_scholar_candidates=0,
        total_candidates=47,
        post_time_filter_candidates=47,
        ranking_mode="llm",
        ranking_threshold=6.0,
        scoring_candidates=47,
        scored_count=47,
        pass_count=3,
        score_buckets={"9-10": 1, "7-8": 2, "5-6": 5, "1-4": 33, "0": 6},
        estimated_llm_calls_upper_bound=10,
        final_selected=3,
        query_strategy="saved-topics",
        send_frequency="daily",
        lookback_hours=24,
        llm_max_candidates_base=50,
        llm_max_candidates_effective=50,
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
