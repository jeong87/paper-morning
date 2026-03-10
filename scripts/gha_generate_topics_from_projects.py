import json
import os
import sys
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests
from dotenv import dotenv_values

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.paper_digest_app import CEREBRAS_API_BASE_DEFAULT, mask_sensitive_text, parse_json_loose

GEMINI_API_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


def fail(message: str) -> None:
    raise SystemExit(message)


def env_truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def safe_exception_text(exc: Exception) -> str:
    return mask_sensitive_text(str(exc))


def read_env_map_from_secret() -> Dict[str, str]:
    env_text = os.getenv("PM_ENV_FILE", "")
    if not env_text.strip():
        fail("PM_ENV_FILE secret is empty. Add repository secret PM_ENV_FILE.")

    normalized = env_text.replace("\r\n", "\n").replace("\r", "\n")
    loaded = dotenv_values(stream=StringIO(normalized))
    env_map: Dict[str, str] = {}
    for key, value in loaded.items():
        if key is None:
            continue
        env_map[str(key).strip()] = str(value or "").strip()
    return env_map


def normalize_projects(projects_payload: Any) -> List[Dict[str, str]]:
    if isinstance(projects_payload, dict):
        raw_projects = projects_payload.get("projects", [])
    else:
        raw_projects = projects_payload

    if not isinstance(raw_projects, list):
        return []

    cleaned: List[Dict[str, str]] = []
    for item in raw_projects:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        context = str(item.get("context", "")).strip()
        if not (name and context):
            continue
        cleaned.append({"name": name, "context": context})
    return cleaned


def parse_projects_lines(lines_text: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for raw in lines_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            name, context = line.split("|", 1)
        elif ":" in line:
            name, context = line.split(":", 1)
        else:
            continue
        name = name.strip()
        context = context.strip()
        if name and context:
            rows.append({"name": name, "context": context})
    return rows


def resolve_projects() -> Tuple[List[Dict[str, str]], str]:
    inline_lines = os.getenv("PM_PROJECTS_LINES", "").strip()
    if inline_lines:
        projects = parse_projects_lines(inline_lines)
        if projects:
            return projects, "workflow_dispatch.inputs.projects_lines"

    projects_json_text = os.getenv("PM_PROJECTS_JSON", "").strip()
    if projects_json_text:
        try:
            payload = json.loads(projects_json_text)
        except json.JSONDecodeError as exc:
            fail(f"PM_PROJECTS_JSON is not valid JSON: {exc}")
        projects = normalize_projects(payload)
        if projects:
            return projects, "secret.PM_PROJECTS_JSON"

    topics_json_text = os.getenv("PM_TOPICS_JSON", "").strip()
    if topics_json_text:
        try:
            payload = json.loads(topics_json_text)
        except json.JSONDecodeError as exc:
            fail(f"PM_TOPICS_JSON is not valid JSON: {exc}")
        projects = normalize_projects(payload)
        if projects:
            return projects, "secret.PM_TOPICS_JSON.projects"

    fail(
        "No project input found. Provide one of: "
        "1) workflow input PM_PROJECTS_LINES, "
        "2) secret PM_PROJECTS_JSON, "
        "3) secret PM_TOPICS_JSON with non-empty projects."
    )


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
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }

    body, used_model = post_gemini_with_model_fallback(
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        payload=payload,
        timeout_seconds=60,
    )
    if used_model != gemini_model:
        print(f"Gemini model fallback applied: requested={gemini_model} used={used_model}")

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
            errors.append(f"Gemini failed: {safe_exception_text(exc)}")

    if enable_cerebras_fallback and cerebras_api_key:
        try:
            return call_cerebras_for_topic_generation(
                projects=projects,
                cerebras_api_key=cerebras_api_key,
                cerebras_model=cerebras_model,
                cerebras_api_base=cerebras_api_base,
            )
        except Exception as exc:
            errors.append(f"Cerebras failed: {safe_exception_text(exc)}")

    if errors:
        raise RuntimeError("; ".join(errors))
    raise RuntimeError(
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


def get_effective_gemini_model(env_map: Dict[str, str]) -> str:
    if env_truthy(env_map.get("ENABLE_GEMINI_ADVANCED_REASONING", "true")):
        return "gemini-3.1-pro"
    configured = env_map.get("GEMINI_MODEL", "gemini-3.1-flash")
    configured = str(configured or "").strip()
    return configured or "gemini-3.1-flash"


def write_output_files(payload: Dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    topics_path = output_dir / "generated_user_topics.json"
    topics_path.write_text(json_text, encoding="utf-8")

    secret_value_path = output_dir / "PM_TOPICS_JSON_VALUE.txt"
    secret_value_path.write_text(json_text, encoding="utf-8")

    guide_path = output_dir / "NEXT_STEP_KR.txt"
    guide_path.write_text(
        (
            "1) generated_user_topics.json 내용을 확인하세요.\n"
            "2) GitHub Repository Secret PM_TOPICS_JSON 값을 이 파일 내용으로 교체하세요.\n"
            "3) paper-morning-digest 워크플로우를 dry_run으로 1회 테스트하세요.\n"
        ),
        encoding="utf-8",
    )


def write_step_summary(
    projects_count: int,
    topics_count: int,
    projects_source: str,
    output_dir: Path,
) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY", "").strip()
    if not summary_path:
        return
    lines = [
        "## Paper Morning - 초기 쿼리 생성 결과",
        "",
        f"- 프로젝트 입력 소스: `{projects_source}`",
        f"- 프로젝트 수: `{projects_count}`",
        f"- 생성된 topic 수: `{topics_count}`",
        f"- 산출물 폴더: `{output_dir.as_posix()}`",
        "",
        "다음 단계:",
        "1. Artifact에서 `generated_user_topics.json` 다운로드",
        "2. Repository Secret `PM_TOPICS_JSON` 값으로 붙여넣기",
        "3. `paper-morning-digest`를 `dry_run`으로 실행해 확인",
    ]
    Path(summary_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    env_map = read_env_map_from_secret()
    projects, projects_source = resolve_projects()

    gemini_api_key = str(env_map.get("GEMINI_API_KEY", "")).strip()
    gemini_model = get_effective_gemini_model(env_map)
    cerebras_api_key = str(env_map.get("CEREBRAS_API_KEY", "")).strip()
    cerebras_model = str(env_map.get("CEREBRAS_MODEL", "gpt-oss-120b") or "").strip() or "gpt-oss-120b"
    cerebras_api_base = (
        str(env_map.get("CEREBRAS_API_BASE", CEREBRAS_API_BASE_DEFAULT) or "").strip()
        or CEREBRAS_API_BASE_DEFAULT
    )
    enable_cerebras_fallback = env_truthy(env_map.get("ENABLE_CEREBRAS_FALLBACK", "true"))

    llm_response = call_llm_for_topic_generation(
        projects=projects,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        cerebras_api_key=cerebras_api_key,
        cerebras_model=cerebras_model,
        cerebras_api_base=cerebras_api_base,
        enable_cerebras_fallback=enable_cerebras_fallback,
    )
    topics = sanitize_generated_topics(llm_response)
    if not topics:
        fail("LLM returned no valid topics. Try clearer project context and rerun.")

    payload = {"projects": projects, "topics": topics}
    output_dir = Path(os.getenv("PM_BOOTSTRAP_OUTPUT_DIR", "bootstrap_output")).resolve()
    write_output_files(payload, output_dir)
    write_step_summary(
        projects_count=len(projects),
        topics_count=len(topics),
        projects_source=projects_source,
        output_dir=output_dir,
    )

    print(f"Generated topics: {len(topics)}")
    print(f"Output directory: {output_dir}")
    print(f"- {output_dir / 'generated_user_topics.json'}")
    print(f"- {output_dir / 'PM_TOPICS_JSON_VALUE.txt'}")
    print(f"- {output_dir / 'NEXT_STEP_KR.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
