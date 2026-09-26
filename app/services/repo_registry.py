from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

SERVICES_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "services.yaml"


@dataclass
class ServiceConfig:
    name: str
    repo_path: Path  # resolved, absolute — always a real local clone
    branch: str
    language: str
    critical_routes: list[str]
    fix_allowed: bool


@lru_cache
def _load_raw() -> dict:
    return yaml.safe_load(SERVICES_PATH.read_text())["services"]


def get_service(name: str) -> ServiceConfig:
    raw = _load_raw().get(name)
    if raw is None:
        raise KeyError(f"no service '{name}' in config/services.yaml")

    local_path = raw.get("local_path")
    if local_path is None:
        raise ValueError(
            f"service '{name}' has no local_path set in config/services.yaml — "
            f"repository={raw.get('repository')!r} is informational only, not clonable from here"
        )

    repo_path = (SERVICES_PATH.parent.parent / local_path).resolve()
    return ServiceConfig(
        name=name,
        repo_path=repo_path,
        branch=raw["branch"],
        language=raw["language"],
        critical_routes=raw.get("critical_routes", []),
        fix_allowed=raw.get("fix_allowed", False),
    )
