#!/usr/bin/env python3
"""Cleanup hook: deletes only the configured contracts dir. Refuses if the resolved contracts path escapes docs_root or the repo root, since docs_root is user-configurable and a bad config must not become an arbitrary rm -rf.
Keeps the whole dir while .seed/ holds files: those are the only copy of files
a stopped seed injection left defective.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import config  # noqa: E402


def is_strictly_inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return child != parent


def main() -> int:
    try:
        json.load(sys.stdin)
    except json.JSONDecodeError:
        pass

    paths = config.load_paths()
    contracts_dir = paths.contracts.resolve()
    docs_root = paths.docs_root.resolve()
    repo_root = config.REPO_ROOT.resolve()

    if not is_strictly_inside(contracts_dir, docs_root) or not is_strictly_inside(docs_root, repo_root):
        print(
            f"cleanup: refusing to delete {contracts_dir} — it is not strictly inside "
            f"{docs_root} inside {repo_root}",
            file=sys.stderr,
        )
        return 0

    seed_dir = contracts_dir / ".seed"
    if seed_dir.is_dir() and any(p.is_file() for p in seed_dir.rglob("*")):
        print(
            f"cleanup: keeping {contracts_dir} — {seed_dir} holds an unrestored seed backup. "
            "Run `python3 .harness/bin/seed.py restore`.",
            file=sys.stderr,
        )
        return 0

    if contracts_dir.is_dir():
        shutil.rmtree(contracts_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
