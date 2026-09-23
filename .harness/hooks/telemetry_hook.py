#!/usr/bin/env python3
"""PostToolUse / PostToolUseFailure telemetry. Always exits 0 with empty
stdout: a non-zero exit or stray output here would block or corrupt the
calling agent's tool loop (U5).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import config  # noqa: E402
import hook_shared  # noqa: E402
import telemetry  # noqa: E402

PATHS = config.load_paths()
REPO_ROOT = config.REPO_ROOT
SEED_SCRIPT = ".harness/bin/seed.py"
# REPO_ROOT is symlink-resolved (config.py resolves __file__); tool_input
# paths from the calling agent usually are not, so resolve() here too or
# every spec/handoff write silently drops on a symlinked worktree (e.g. macOS /tmp).
SPECS_DIR = PATHS.specs.resolve()
HANDOFF_DIR = PATHS.handoff.resolve()


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def parse_spec_version(path: Path):
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("version:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def match_seed(command: str):
    """Return (action, is_seed_invocation)."""
    tokens = command.split()
    for i, tok in enumerate(tokens):
        if tok == SEED_SCRIPT or tok.endswith("/" + SEED_SCRIPT):
            return (tokens[i + 1] if i + 1 < len(tokens) else None), True
    return None, False


def apply_patch_paths(tool_input: dict) -> list:
    text = tool_input.get("input")
    if text is None:
        text = tool_input.get("command")
    if not isinstance(text, str):
        return []
    paths = []
    for line in text.splitlines():
        for prefix in ("*** Add File: ", "*** Update File: "):
            if line.startswith(prefix):
                paths.append(line[len(prefix):].strip())
    return paths


def emit_path_write(payload: dict, path_str) -> None:
    if not path_str:
        return
    path = resolve_path(path_str)
    if path.parent == SPECS_DIR and path.suffix == ".md":
        telemetry.emit(payload, "spec_write", spec=path.stem, version=parse_spec_version(path))
    elif path.parent == HANDOFF_DIR and path.name not in ("index.md", "stale.md"):
        telemetry.emit(payload, "handoff_write", file=path.name)


def bash_exit_code(tool_response):
    if not isinstance(tool_response, dict):
        return None
    value = tool_response.get("exit_code")
    # bool is an int subclass; telemetry requires exit_code strictly int|null.
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def handle_bash(payload: dict, tool_input: dict, tool_response) -> None:
    command = hook_shared.normalize(hook_shared.shell_command(tool_input))
    if not command:
        return
    specs = dict(hook_shared.iter_test_commands(PATHS.specs))
    if command in specs:
        telemetry.emit(payload, "test_command", spec=specs[command], exit_code=bash_exit_code(tool_response))
        return
    action, is_seed = match_seed(command)
    if is_seed:
        telemetry.emit(payload, "seed", action=action, exit_code=bash_exit_code(tool_response))


def handle_post_tool_use(payload: dict) -> None:
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    tool_response = payload.get("tool_response")
    if tool_name == "Bash":
        handle_bash(payload, tool_input, tool_response)
    elif tool_name in ("Write", "Edit"):
        emit_path_write(payload, tool_input.get("file_path"))
    elif tool_name == "apply_patch":
        for path_str in apply_patch_paths(tool_input):
            emit_path_write(payload, path_str)


def handle_post_tool_use_failure(payload: dict) -> None:
    if payload.get("tool_name") != "Bash":
        return
    tool_input = payload.get("tool_input") or {}
    command = hook_shared.normalize(hook_shared.shell_command(tool_input))
    specs = dict(hook_shared.iter_test_commands(PATHS.specs))
    action, is_seed = match_seed(command)
    if command not in specs and not is_seed:
        return
    error_code = payload.get("error_code")
    if error_code is None:
        tool_response = payload.get("tool_response")
        if isinstance(tool_response, dict):
            error_code = tool_response.get("error_code")
    telemetry.emit(
        payload,
        "tool_failure",
        tool_name="Bash",
        error_code=error_code,
        spec=specs.get(command),
        action=action if is_seed else None,
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    hook_event = payload.get("hook_event_name")
    if hook_event == "PostToolUse":
        handle_post_tool_use(payload)
    elif hook_event == "PostToolUseFailure":
        handle_post_tool_use_failure(payload)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
