#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import config  # noqa: E402

PATHS = config.load_paths()
REPO_ROOT = config.REPO_ROOT
CONTRACTS_DIR = PATHS.contracts
RUNNING_DIR = CONTRACTS_DIR / ".running"
GATED_AGENTS = {"implementer", "test-implementer"}
TEST_COMMAND_PREFIX = "Test command:"


def normalize(command: str) -> str:
    return " ".join(command.split())


def marker_path(payload: dict) -> Path:
    key = payload.get("agent_id") or payload.get("agent_type") or ""
    return RUNNING_DIR / re.sub(r"[^A-Za-z0-9._-]", "_", key)


def test_commands() -> set:
    commands = set()
    for contract in CONTRACTS_DIR.glob("*.md"):
        for line in contract.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(TEST_COMMAND_PREFIX):
                command = normalize(line[len(TEST_COMMAND_PREFIX):])
                if command:
                    commands.add(command)
    return commands


def shell_command(tool_input) -> str:
    command = (tool_input or {}).get("command")
    if isinstance(command, list):
        if len(command) >= 3 and command[1] in ("-c", "-lc"):
            return command[-1]
        return " ".join(command)
    return command if isinstance(command, str) else ""


def on_subagent_start(payload: dict) -> int:
    if payload.get("agent_type") not in GATED_AGENTS or not CONTRACTS_DIR.is_dir():
        return 0
    RUNNING_DIR.mkdir(exist_ok=True)
    marker_path(payload).write_text(payload["agent_type"], encoding="utf-8")
    return 0


def on_subagent_stop(payload: dict) -> int:
    if payload.get("agent_type") in GATED_AGENTS:
        marker_path(payload).unlink(missing_ok=True)
    return 0


def on_pre_tool_use(payload: dict) -> int:
    if not RUNNING_DIR.is_dir():
        return 0
    running = sorted(RUNNING_DIR.iterdir())
    # Exact match only: subagents run narrower test invocations that must stay unblocked.
    if not running or normalize(shell_command(payload.get("tool_input"))) not in test_commands():
        return 0
    listing = ", ".join(
        f"{m.read_text(encoding='utf-8')} ({m.relative_to(REPO_ROOT)})" for m in running
    )
    print(
        f"contract-workflow: `Test command` is blocked until these subagents report: {listing}. "
        "If a subagent is no longer running, delete its marker file.",
        file=sys.stderr,
    )
    return 2


HANDLERS = {
    "SubagentStart": on_subagent_start,
    "SubagentStop": on_subagent_stop,
    "PreToolUse": on_pre_tool_use,
}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    handler = HANDLERS.get(payload.get("hook_event_name"))
    return handler(payload) if handler else 0


if __name__ == "__main__":
    sys.exit(main())
