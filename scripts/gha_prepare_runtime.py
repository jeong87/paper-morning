import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.projects_config import DEFAULT_PROJECTS_CONFIG_FILE, normalize_projects_payload, read_projects_config


def fail(message: str) -> None:
    raise SystemExit(message)


def parse_topics_payload(topics_text: str) -> Tuple[Dict[str, Any], str]:
    try:
        topics_payload = json.loads(topics_text)
    except json.JSONDecodeError as exc:
        fail(f"PM_TOPICS_JSON is not valid JSON: {exc}")
    if not isinstance(topics_payload, dict):
        fail("PM_TOPICS_JSON must be a JSON object.")
    projects = topics_payload.get("projects", [])
    topics = topics_payload.get("topics", [])
    if projects is not None and not isinstance(projects, list):
        fail("PM_TOPICS_JSON.projects must be a list.")
    if topics is not None and not isinstance(topics, list):
        fail("PM_TOPICS_JSON.topics must be a list.")
    return topics_payload, "secret.PM_TOPICS_JSON"


def resolve_projects_payload(projects_text: str, projects_file_path: Path) -> Tuple[List[Dict[str, Any]], str]:
    if projects_text.strip():
        try:
            payload = json.loads(projects_text)
        except json.JSONDecodeError as exc:
            fail(f"PM_PROJECTS_JSON is not valid JSON: {exc}")
        projects = normalize_projects_payload(payload)
        if not projects:
            fail("PM_PROJECTS_JSON did not contain valid projects entries.")
        return projects, "secret.PM_PROJECTS_JSON"

    projects, errors = read_projects_config(projects_file_path)
    if errors:
        fail(
            "No PM_TOPICS_JSON provided and projects config could not be loaded. "
            f"Path={projects_file_path}; Errors={'; '.join(errors)}"
        )
    return projects, f"repo:{projects_file_path}"


def main() -> int:
    env_text = os.getenv("PM_ENV_FILE", "")
    topics_text = os.getenv("PM_TOPICS_JSON", "")
    projects_text = os.getenv("PM_PROJECTS_JSON", "")
    projects_file = os.getenv("PM_PROJECTS_FILE", DEFAULT_PROJECTS_CONFIG_FILE).strip() or DEFAULT_PROJECTS_CONFIG_FILE

    if not env_text.strip():
        fail("PM_ENV_FILE secret is empty. Add repository secret PM_ENV_FILE.")

    runtime_dir = Path("ci_runtime").resolve()
    runtime_dir.mkdir(parents=True, exist_ok=True)

    env_path = runtime_dir / ".env"
    topics_path = runtime_dir / "user_topics.json"
    data_dir = runtime_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    normalized_env = env_text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized_env.endswith("\n"):
        normalized_env += "\n"
    env_path.write_text(normalized_env, encoding="utf-8")

    payload_source = ""
    topics_payload: Dict[str, Any]
    if topics_text.strip():
        topics_payload, payload_source = parse_topics_payload(topics_text)
    else:
        projects_path = (ROOT_DIR / projects_file).resolve()
        projects, payload_source = resolve_projects_payload(projects_text, projects_path)
        topics_payload = {"projects": projects, "topics": []}

    topics_path.write_text(
        json.dumps(topics_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Prepared runtime files in: {runtime_dir}")
    print(f"- env: {env_path}")
    print(f"- topics: {topics_path}")
    print(f"- data: {data_dir}")
    print(f"- topic source: {payload_source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

