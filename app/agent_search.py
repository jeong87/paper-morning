from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Dict, List

from paper_digest_app import (
    AppConfig,
    DigestStats,
    Paper,
    ResearchProject,
    TopicProfile,
    build_diagnostics_lines,
    can_use_cerebras_fallback,
    can_use_openai_compat_provider,
    clean_text,
    coerce_bool,
    coerce_keyword_weights,
    collect_and_rank_papers,
    dedupe_list,
    generate_topics_from_projects,
    normalize_output_language,
    normalize_relevance_mode,
    resolve_search_request,
    LLM_RELEVANCE_MODE_DEFAULT,
)


def build_agent_projects_input(
    project_name: str,
    research_context: str,
    keywords: List[str],
) -> List[Dict[str, str]]:
    merged_context = clean_text(research_context)
    normalized_keywords = [clean_text(str(item)) for item in keywords if clean_text(str(item))]
    if normalized_keywords:
        merged_context = (
            f"{merged_context} | Keywords: {', '.join(normalized_keywords)}"
            if merged_context
            else f"Keywords: {', '.join(normalized_keywords)}"
        )
    return [{"name": clean_text(project_name) or "Untitled project", "context": merged_context}]


def build_topic_profiles_from_generated_topics(topics: List[Dict[str, Any]]) -> List[TopicProfile]:
    profiles: List[TopicProfile] = []
    for topic in topics:
        if not isinstance(topic, dict):
            continue
        name = clean_text(str(topic.get("name", "")))
        keyword_weights = coerce_keyword_weights(topic.get("keywords", []))
        relevance_mode = normalize_relevance_mode(
            topic.get("relevance_mode", LLM_RELEVANCE_MODE_DEFAULT)
        )
        if not name or not keyword_weights:
            continue
        profiles.append(
            TopicProfile(
                name=name,
                keywords=keyword_weights,
                relevance_mode=relevance_mode,
            )
        )
    return profiles


def clone_config_for_agent_request(
    base_config: AppConfig,
    project_name: str,
    research_context: str,
    keywords: List[str],
    generated_topics: List[Dict[str, Any]],
    top_k: int,
    output_language: str | None = None,
    model: str | None = None,
    source_policy: Dict[str, Any] | None = None,
) -> AppConfig:
    topic_profiles = build_topic_profiles_from_generated_topics(generated_topics)
    arxiv_queries = dedupe_list(
        [
            clean_text(str(topic.get("arxiv_query", "")))
            for topic in generated_topics
            if clean_text(str(topic.get("arxiv_query", "")))
        ]
    )
    pubmed_queries = dedupe_list(
        [
            clean_text(str(topic.get("pubmed_query", "")))
            for topic in generated_topics
            if clean_text(str(topic.get("pubmed_query", "")))
        ]
    )
    semantic_queries = dedupe_list(
        [
            clean_text(str(topic.get("semantic_scholar_query", "")))
            for topic in generated_topics
            if clean_text(str(topic.get("semantic_scholar_query", "")))
        ]
    )
    google_queries = dedupe_list(
        [
            clean_text(str(topic.get("google_scholar_query", "")))
            for topic in generated_topics
            if clean_text(str(topic.get("google_scholar_query", "")))
        ]
    )
    requested_output_language = normalize_output_language(
        output_language or base_config.output_language
    )
    normalized_keywords = [clean_text(str(item)) for item in keywords if clean_text(str(item))]
    source_policy = source_policy or {}
    use_arxiv = coerce_bool(source_policy.get("arxiv"), True)
    use_pubmed = coerce_bool(source_policy.get("pubmed"), True)
    use_semantic_scholar = coerce_bool(
        source_policy.get("semantic_scholar"),
        base_config.enable_semantic_scholar,
    )
    use_google_scholar = coerce_bool(
        source_policy.get("google_scholar"),
        base_config.enable_google_scholar,
    )
    requested_model = clean_text(model)
    return replace(
        base_config,
        research_projects=[
            ResearchProject(
                name=clean_text(project_name) or "Untitled project",
                context=build_agent_projects_input(
                    project_name,
                    research_context,
                    normalized_keywords,
                )[0]["context"],
                send_frequency="daily",
                send_interval_days=1,
            )
        ],
        topic_profiles=topic_profiles,
        arxiv_queries=arxiv_queries if use_arxiv else [],
        pubmed_queries=pubmed_queries if use_pubmed else [],
        semantic_scholar_queries=semantic_queries,
        google_scholar_queries=google_queries,
        enable_semantic_scholar=use_semantic_scholar,
        enable_google_scholar=use_google_scholar,
        max_papers=max(1, min(50, int(top_k))),
        output_language=requested_output_language,
        gemini_model=requested_model or base_config.gemini_model,
        openai_compat_model=requested_model or base_config.openai_compat_model,
        cerebras_model=requested_model or base_config.cerebras_model,
    )


def map_agent_status(stats: DigestStats, papers: List[Paper]) -> str:
    if papers:
        return "ok"
    if stats.no_results_reason == "outside_horizon":
        return "outside_horizon"
    if stats.no_results_reason == "below_threshold":
        return "below_threshold"
    if stats.no_results_reason in {"none_retrieved", "no_candidates"}:
        return "no_candidates"
    return "error"


def describe_agent_llm_backend(config: AppConfig) -> Dict[str, str]:
    if config.gemini_api_key:
        return {"provider": "gemini", "model": config.gemini_model}
    if can_use_openai_compat_provider(config):
        return {"provider": "openai_compatible", "model": config.openai_compat_model}
    if can_use_cerebras_fallback(config):
        return {"provider": "cerebras", "model": config.cerebras_model}
    return {"provider": "none", "model": ""}


def search_papers_for_agent(
    config: AppConfig,
    project_name: str,
    research_context: str,
    keywords: List[str] | None = None,
    search_intent: str = "best_match",
    time_horizon_key: str = "1y",
    top_k: int = 10,
    output_language: str | None = None,
    model: str | None = None,
    include_diagnostics: bool = False,
    source_policy: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    normalized_context = clean_text(research_context)
    if not normalized_context:
        raise ValueError("research_context is required.")

    normalized_keywords = [
        clean_text(str(item)) for item in (keywords or []) if clean_text(str(item))
    ]
    llm_projects = build_agent_projects_input(
        project_name,
        normalized_context,
        normalized_keywords,
    )
    generated_topics = generate_topics_from_projects(config, llm_projects)
    request_config = clone_config_for_agent_request(
        config,
        project_name=project_name,
        research_context=normalized_context,
        keywords=normalized_keywords,
        generated_topics=generated_topics,
        top_k=top_k,
        output_language=output_language,
        model=model,
        source_policy=source_policy,
    )
    search_request = resolve_search_request(
        request_config,
        search_intent=search_intent,
        time_horizon_key=time_horizon_key,
    )
    now_utc = datetime.now(timezone.utc)
    ranked, stats = collect_and_rank_papers(request_config, now_utc, search_request)
    papers = ranked[: request_config.max_papers]
    primary_topic = generated_topics[0] if generated_topics else {}
    backend = describe_agent_llm_backend(request_config)
    return {
        "status": map_agent_status(stats, papers),
        "request": {
            "project_name": clean_text(project_name) or llm_projects[0]["name"],
            "search_intent": search_request.intent,
            "time_horizon": search_request.time_horizon_key,
            "top_k": request_config.max_papers,
            "output_language": request_config.output_language,
        },
        "meta": {
            "intent_label": search_request.intent_label,
            "requested_horizon_label": search_request.time_horizon_label,
            "window_used_label": stats.window_used_label or search_request.time_horizon_label,
            "query_plan_label": stats.query_plan_label or "generated topic queries",
            "used_provider": backend["provider"],
            "used_model": backend["model"],
            "sources_queried": [
                label
                for enabled, label in [
                    (bool(request_config.arxiv_queries), "arXiv"),
                    (bool(request_config.pubmed_queries), "PubMed"),
                    (
                        request_config.enable_semantic_scholar
                        and bool(request_config.semantic_scholar_queries),
                        "Semantic Scholar",
                    ),
                    (
                        request_config.enable_google_scholar
                        and bool(request_config.google_scholar_queries),
                        "Google Scholar",
                    ),
                ]
                if enabled
            ],
            "scanned_count": stats.post_time_filter_candidates or stats.total_candidates,
            "selected_count": len(papers),
            "threshold_used": stats.ranking_threshold,
            "notice": stats.search_notice,
        },
        "topic": {
            "name": clean_text(str(primary_topic.get("name", ""))),
            "keywords": [
                clean_text(str(item))
                for item in primary_topic.get("keywords", [])
                if clean_text(str(item))
            ],
            "relevance_mode": normalize_relevance_mode(
                primary_topic.get("relevance_mode", LLM_RELEVANCE_MODE_DEFAULT)
            ),
            "arxiv_query": clean_text(str(primary_topic.get("arxiv_query", ""))),
            "pubmed_query": clean_text(str(primary_topic.get("pubmed_query", ""))),
            "semantic_scholar_query": clean_text(
                str(primary_topic.get("semantic_scholar_query", ""))
            ),
            "google_scholar_query": clean_text(
                str(primary_topic.get("google_scholar_query", ""))
            ),
        },
        "papers": [
            {
                "rank": index,
                "id": paper.paper_id,
                "title": paper.title,
                "authors": ", ".join(paper.authors),
                "source": paper.source,
                "url": paper.url,
                "published_at": paper.published_at_utc.isoformat(),
                "relevance_score": paper.score,
                "relevance_reason": paper.llm_relevance_text,
                "core_point": paper.llm_core_point_text,
                "usefulness": paper.llm_usefulness_text,
                "evidence_spans": list(paper.llm_evidence_spans or []),
                "topic": paper.topic,
                "project_name": paper.project_name,
                "relevance_mode": paper.relevance_mode,
            }
            for index, paper in enumerate(papers, start=1)
        ],
        "diagnostics": build_diagnostics_lines(stats) if include_diagnostics else [],
    }
