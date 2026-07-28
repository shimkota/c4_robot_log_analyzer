from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
CONFIG_DIR = BASE_DIR / "config"

DEFAULT_SETTINGS = {
    "motion_map": {
        "motions": {
            "A": {"label": "A", "direction": None},
            "B": {"label": "B", "direction": None},
            "C": {"label": "C", "direction": None},
            "D": {"label": "D", "direction": None},
            "E": {"label": "E", "direction": None},
        }
    },
    "obstacle_directions": {"directions": {index: None for index in range(8)}},
    "phase_groups": {
        "groups": {
            "move": "移動",
            "centering": "位置調整",
            "scan": "スキャン",
            "calc": "計算・選択",
            "take": "ボード取得",
            "install": "取り付け",
            "reverse": "逆再生",
            "place": "置く",
            "abnormal": "異常対応",
            "manual": "手動対応",
            "unclassified": "未分類",
        }
    },
}


def ensure_runtime_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def list_log_files() -> List[Dict[str, object]]:
    ensure_runtime_dirs()
    files = []
    upload_root = UPLOAD_DIR.resolve()
    for path in sorted(LOG_DIR.rglob("*.csv")):
        resolved = path.resolve()
        if _is_relative_to(resolved, upload_root):
            continue
        stat = path.stat()
        files.append(
            {
                "filename": path.relative_to(LOG_DIR).as_posix(),
                "size": stat.st_size,
                "source": "workspace",
            }
        )
    for path in sorted(UPLOAD_DIR.glob("*.csv")):
        stat = path.stat()
        files.append(
            {
                "filename": path.name,
                "size": stat.st_size,
                "source": "upload",
            }
        )
    seen = set()
    unique = []
    for item in files:
        key = (item["source"], item["filename"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def resolve_log_path(filename: str) -> Path:
    requested = Path(filename)
    if requested.is_absolute() or ".." in requested.parts:
        raise FileNotFoundError(f"CSV not found: {filename}")
    upload_candidate = (UPLOAD_DIR / requested.name).resolve()
    workspace_candidate = (LOG_DIR / requested).resolve()
    candidates = [upload_candidate, workspace_candidate]
    for candidate in candidates:
        if not _is_relative_to(candidate, LOG_DIR.resolve()):
            continue
        if candidate.exists() and candidate.is_file() and candidate.suffix.lower() == ".csv":
            return candidate
    raise FileNotFoundError(f"CSV not found: {filename}")


def _import_yaml():
    try:
        import yaml  # type: ignore

        return yaml
    except ImportError:
        return None


def load_yaml_file(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    yaml = _import_yaml()
    if not path.exists():
        return default
    if yaml is None:
        return default
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else default


def save_yaml_file(path: Path, data: Dict[str, Any]) -> None:
    yaml = _import_yaml()
    if yaml is None:
        raise RuntimeError("PyYAML is required to update settings")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False)


def load_settings() -> Dict[str, Any]:
    return {
        "motion_map": load_yaml_file(CONFIG_DIR / "motion_map.yaml", DEFAULT_SETTINGS["motion_map"]),
        "obstacle_directions": load_yaml_file(
            CONFIG_DIR / "obstacle_directions.yaml", DEFAULT_SETTINGS["obstacle_directions"]
        ),
        "phase_groups": load_yaml_file(CONFIG_DIR / "phase_groups.yaml", DEFAULT_SETTINGS["phase_groups"]),
    }


def save_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in settings.items():
        if key not in DEFAULT_SETTINGS:
            continue
        if isinstance(value, dict):
            save_yaml_file(CONFIG_DIR / f"{key}.yaml", value)
    return load_settings()
