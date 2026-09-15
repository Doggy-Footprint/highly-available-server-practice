#!/usr/bin/env python3
"""Warns when another harness session is already running against this repo.
Uses os.getppid() as the session key (not payload session_id) since neither
Claude nor Codex hook payloads are known to guarantee that field here.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import config  # noqa: E402

RUNNING_DIR = config.REPO_ROOT / ".harness" / "sessions" / ".running"


def is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def own_marker() -> Path:
    return RUNNING_DIR / str(os.getppid())


def sweep_stale() -> list:
    if not RUNNING_DIR.is_dir():
        return []
    alive = []
    for marker in sorted(RUNNING_DIR.iterdir()):
        try:
            pid = int(marker.name)
        except ValueError:
            marker.unlink(missing_ok=True)
            continue
        if is_alive(pid):
            alive.append(marker)
        else:
            marker.unlink(missing_ok=True)
    return alive


def on_session_start(payload: dict) -> int:
    RUNNING_DIR.mkdir(parents=True, exist_ok=True)
    mine = own_marker()
    others = [m for m in sweep_stale() if m != mine]
    mine.write_text(payload.get("source", ""), encoding="utf-8")
    if others:
        print(
            "harness: "
            + str(len(others))
            + " other agent session(s) already running against this repo (pid: "
            + ", ".join(m.name for m in others)
            + "). Concurrent sessions editing the same files can conflict.",
            file=sys.stderr,
        )
    return 0


def on_session_end(payload: dict) -> int:
    own_marker().unlink(missing_ok=True)
    return 0


HANDLERS = {
    "SessionStart": on_session_start,
    "SessionEnd": on_session_end,
}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        payload = {}
    handler = HANDLERS.get(payload.get("hook_event_name"))
    return handler(payload) if handler else 0


if __name__ == "__main__":
    sys.exit(main())
