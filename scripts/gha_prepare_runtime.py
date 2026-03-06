import json
import os
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> int:
    env_text = os.getenv("PM_ENV_FILE", "")
    topics_text = os.getenv("PM_TOPICS_JSON", "")

    if not env_text.strip():
        fail("PM_ENV_FILE secret is empty. Add repository secret PM_ENV_FILE.")
    if not topics_text.strip():
        fail("PM_TOPICS_JSON secret is empty. Add repository secret PM_TOPICS_JSON.")

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

    topics_path.write_text(
        json.dumps(topics_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Prepared runtime files in: {runtime_dir}")
    print(f"- env: {env_path}")
    print(f"- topics: {topics_path}")
    print(f"- data: {data_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
