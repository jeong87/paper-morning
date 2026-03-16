import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import yaml
except Exception:  # pragma: no cover - handled by runtime validation path
    yaml = None


DEFAULT_PROJECTS_CONFIG_FILE = "config/projects.yaml"
ALLOWED_PROJECT_SEND_FREQUENCIES = {"daily", "every_3_days", "weekly"}


def _normalize_keywords(raw: Any) -> List[str]:
    if isinstance(raw, str):
        items = [part.strip() for part in raw.split(",")]
    elif isinstance(raw, list):
        items = [str(part).strip() for part in raw]
    else:
        items = []
    deduped: List[str] = []
    seen = set()
    for item in items:
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _normalize_project_send_frequency(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if value in {"", "1", "1d", "daily"}:
        return "daily"
    if value in {"3", "3d", "every_3_days"}:
        return "every_3_days"
    if value in {"7", "7d", "weekly"}:
        return "weekly"
    return "daily"


def normalize_projects_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        raw_projects = payload.get("projects", [])
    else:
        raw_projects = payload
    if not isinstance(raw_projects, list):
        return []

    projects: List[Dict[str, Any]] = []
    for item in raw_projects:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        context = str(item.get("context", "")).strip()
        keywords = _normalize_keywords(item.get("keywords", []))
        send_frequency = _normalize_project_send_frequency(item.get("send_frequency", "daily"))
        if not (name or context):
            continue
        project_entry: Dict[str, Any] = {
            "name": name,
            "context": context,
            "send_frequency": send_frequency,
        }
        if keywords:
            project_entry["keywords"] = keywords
        projects.append(project_entry)
    return projects


def validate_projects(projects: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    if not projects:
        errors.append("At least one project is required.")
        return errors

    for idx, project in enumerate(projects, start=1):
        name = str(project.get("name", "")).strip()
        context = str(project.get("context", "")).strip()
        keywords = project.get("keywords", [])
        send_frequency = str(project.get("send_frequency", "daily")).strip().lower()
        if not name:
            errors.append(f"Project #{idx}: name is required.")
        if not context:
            errors.append(f"Project #{idx}: context is required.")
        if send_frequency and send_frequency not in ALLOWED_PROJECT_SEND_FREQUENCIES:
            errors.append(
                f"Project #{idx}: send_frequency must be one of "
                f"{sorted(ALLOWED_PROJECT_SEND_FREQUENCIES)}."
            )
        if keywords and not isinstance(keywords, list):
            errors.append(f"Project #{idx}: keywords must be a list.")
            continue
        if isinstance(keywords, list):
            for keyword in keywords:
                if not str(keyword).strip():
                    errors.append(f"Project #{idx}: keywords cannot contain empty values.")
                    break
    return errors


def parse_projects_config_text(text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    errors: List[str] = []
    stripped = str(text or "").strip()
    if not stripped:
        return [], ["Projects config is empty."]

    parsed: Any = None
    if yaml is not None:
        try:
            parsed = yaml.safe_load(stripped)
        except Exception as exc:
            errors.append(f"Invalid YAML format: {exc}")
    else:
        try:
            parsed = json.loads(stripped)
        except Exception as exc:
            errors.append(
                "PyYAML is unavailable and JSON fallback parsing failed. "
                f"Use valid JSON-style syntax or install PyYAML. ({exc})"
            )

    if errors:
        return [], errors

    projects = normalize_projects_payload(parsed)
    validation_errors = validate_projects(projects)
    if validation_errors:
        return [], validation_errors
    return projects, []


def read_projects_config(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    if not path.exists():
        return [], [f"Projects config not found: {path}"]
    try:
        raw_text = path.read_text(encoding="utf-8-sig")
    except Exception as exc:
        return [], [f"Failed to read projects config: {exc}"]
    return parse_projects_config_text(raw_text)


def write_projects_config(path: Path, projects: List[Dict[str, Any]]) -> None:
    cleaned = normalize_projects_payload({"projects": projects})
    errors = validate_projects(cleaned)
    if errors:
        raise ValueError("; ".join(errors))

    payload = {"projects": cleaned}
    path.parent.mkdir(parents=True, exist_ok=True)
    if yaml is not None:
        dumped = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
        path.write_text(dumped, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
