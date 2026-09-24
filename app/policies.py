from functools import lru_cache
from pathlib import Path

import yaml

POLICIES_PATH = Path(__file__).resolve().parent.parent / "config" / "policies.yaml"


@lru_cache
def load_policies() -> dict:
    return yaml.safe_load(POLICIES_PATH.read_text())
