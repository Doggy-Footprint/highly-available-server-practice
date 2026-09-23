import json
from pathlib import Path

_HARNESS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = _HARNESS_DIR.parent


def load_config() -> dict:
    config = json.loads((_HARNESS_DIR / "config.default.json").read_text(encoding="utf-8"))
    override_path = _HARNESS_DIR / "config.json"
    if override_path.is_file():
        override = json.loads(override_path.read_text(encoding="utf-8"))
        config.update(override)
    return config


class Paths:
    def __init__(self, config: dict):
        self.docs_root = REPO_ROOT / config["docs_root"]
        self.exclude_dirs = set(config["exclude_dirs"])
        self.adr = self.docs_root / "adr"
        self.rejections = self.docs_root / "rejections"
        self.handoff = self.docs_root / "handoff"
        self.synced_comments = self.docs_root / "synced-comments"
        self.specs = self.docs_root / "specs"
        self.spec_logs = self.docs_root / "spec-logs"


def load_paths() -> Paths:
    return Paths(load_config())
