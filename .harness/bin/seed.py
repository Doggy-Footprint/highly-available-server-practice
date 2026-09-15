#!/usr/bin/env python3
"""Backs up files before a contract-workflow seed injection and restores them.
manifest.json is written last, so a backup interrupted before it exists is
detected as partial and never restored from.
"""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import config  # noqa: E402

REPO_ROOT = config.REPO_ROOT.resolve()
SEED_DIR = config.load_paths().contracts / ".seed"
MANIFEST = SEED_DIR / "manifest.json"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_files() -> list:
    if not SEED_DIR.is_dir():
        return []
    return sorted(p for p in SEED_DIR.rglob("*") if p.is_file())


def fail(message: str) -> int:
    print(f"seed: {message}", file=sys.stderr)
    return 1


def cmd_backup(args: list) -> int:
    if not args:
        return fail("backup needs at least one file path")
    if seed_files():
        return fail(f"an unrestored seed exists in {SEED_DIR}; run restore first")

    entries = {}
    for arg in args:
        path = Path(arg).resolve()
        try:
            rel = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            return fail(f"{arg} is outside the repository")
        if not path.is_file():
            return fail(f"{arg} is not a regular file")
        entries[rel] = path

    manifest = {}
    for rel, path in entries.items():
        dest = SEED_DIR / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        manifest[rel] = sha256_of(dest)

    tmp = MANIFEST.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, MANIFEST)
    for rel in manifest:
        print(f"backed up {rel}")
    return 0


def cmd_restore(_args: list) -> int:
    if not seed_files():
        print("seed: nothing to restore")
        return 0
    if not MANIFEST.is_file():
        return fail(f"{MANIFEST} is missing; the backup is partial. Restore by hand from {SEED_DIR}")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    for rel, sha in manifest.items():
        backup = SEED_DIR / rel
        if not backup.is_file() or sha256_of(backup) != sha:
            return fail(f"backup of {rel} is missing or does not match its sha256; nothing restored")

    for rel, sha in manifest.items():
        target = REPO_ROOT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SEED_DIR / rel, target)
        if sha256_of(target) != sha:
            return fail(f"restored {rel} does not match its sha256; backup kept in {SEED_DIR}")

    shutil.rmtree(SEED_DIR)
    for rel in manifest:
        print(f"restored {rel}")
    return 0


def cmd_status(_args: list) -> int:
    files = seed_files()
    if not files:
        print("seed: none")
        return 0
    print(f"seed: unrestored files in {SEED_DIR}")
    for path in files:
        print(f"  {path.relative_to(SEED_DIR).as_posix()}")
    return 1


COMMANDS = {"backup": cmd_backup, "restore": cmd_restore, "status": cmd_status}


def main(argv: list) -> int:
    if not argv or argv[0] not in COMMANDS:
        return fail("usage: seed.py backup <path>... | restore | status")
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
