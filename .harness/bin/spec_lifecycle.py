#!/usr/bin/env python3
import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import config  # noqa: E402

PATHS = config.load_paths()
REPO_ROOT = config.REPO_ROOT.resolve()
SPECS_DIR = PATHS.specs.resolve()
SPEC_LOGS_DIR = PATHS.spec_logs.resolve()
ACTIVE_MARKER = SPECS_DIR / ".active"
SEED_DIR = SPECS_DIR / ".seed"
RUN_ID_RE = re.compile(r"[0-9a-f]{16}")
COMMIT_RE = re.compile(r"[0-9a-f]{40,64}")
TERMINAL = {"complete", "limit", "aborted"}
QUALITY_CHARACTERISTICS = (
    "functional suitability",
    "performance efficiency",
    "compatibility",
    "interaction capability",
    "reliability",
    "security",
    "maintainability",
    "flexibility",
    "safety",
)
REQUIRED_HEADINGS = (
    "# User Intent",
    "# Scope",
    "# Paths",
    "# Signatures",
    "# Functional Requirements",
    "# Errors",
    "# Cases",
    "# Quality Applicability",
    "# Quality Requirements",
    "# Verification Obligations",
    "# Assumptions and Defaults",
    "# Traceability",
    "# Workflow Control",
    "# Version Log",
)


def fail(message: str) -> int:
    print(f"spec lifecycle: {message}", file=sys.stderr)
    return 1


def frontmatter(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    if not lines or lines[0].strip() != "---":
        return {}
    values = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return values
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    return {}


def seed_files() -> list[Path]:
    if not SEED_DIR.is_dir():
        return []
    return [path for path in SEED_DIR.rglob("*") if path.is_file()]


def validate(path: Path) -> list[str]:
    errors = []
    if path.parent.resolve() != SPECS_DIR or path.suffix != ".md":
        return ["spec must be a direct .md child of agent-docs/specs"]
    values = frontmatter(path)
    try:
        if int(values.get("version", "")) < 1:
            errors.append("version must be a positive integer")
    except ValueError:
        errors.append("version must be a positive integer")
    run_id = values.get("run_id", "")
    if not RUN_ID_RE.fullmatch(run_id):
        errors.append("run_id must be 16 lowercase hexadecimal characters")
    elif not path.name.startswith(run_id + "-"):
        errors.append("filename must start with run_id")
    if values.get("status") not in {"draft", "active", *TERMINAL}:
        errors.append("status must be draft, active, complete, limit, or aborted")
    if not COMMIT_RE.fullmatch(values.get("base_commit", "")):
        errors.append("base_commit must be a 40-64 character hexadecimal commit id")
    if values.get("max_verifier_invocations") != "2":
        errors.append("max_verifier_invocations must be 2")
    if "max_correction_rounds" in values:
        errors.append("max_correction_rounds is obsolete; migrate the spec")
    if "handoff" not in values:
        errors.append("handoff must be present; use none when absent")
    elif values["handoff"] != "none":
        handoff = Path(values["handoff"])
        try:
            (REPO_ROOT / handoff).resolve().relative_to(REPO_ROOT)
        except ValueError:
            errors.append("handoff must be a repo-relative path")
        if handoff.is_absolute():
            errors.append("handoff must be a repo-relative path")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return errors + ["spec cannot be read"]
    headings = set(text.splitlines())
    errors.extend(f"missing heading {heading}" for heading in REQUIRED_HEADINGS if heading not in headings)
    lower = text.lower()
    errors.extend(
        f"Quality Applicability is missing {name}"
        for name in QUALITY_CHARACTERISTICS
        if name not in lower
    )
    return errors


def active_marker_value() -> str | None:
    try:
        return ACTIVE_MARKER.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def cmd_validate(args) -> int:
    path = Path(args.spec).resolve()
    errors = validate(path)
    if errors:
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    return 0


def cmd_start(args) -> int:
    path = Path(args.spec).resolve()
    errors = validate(path)
    if errors:
        return fail("invalid spec: " + "; ".join(errors))
    values = frontmatter(path)
    if values.get("status") != "active":
        return fail("start requires spec status active")
    if values.get("run_id") != args.run_id:
        return fail("--run-id does not match spec frontmatter")
    SPECS_DIR.mkdir(parents=True, exist_ok=True)
    current = active_marker_value()
    if current:
        if args.resume and current == path.name:
            return 0
        return fail(f"another workflow is active: {current}")
    other_active = [
        candidate.name
        for candidate in SPECS_DIR.glob("*.md")
        if candidate != path and frontmatter(candidate).get("status") in {"draft", "active"}
    ]
    if other_active:
        return fail("another workflow is active: " + ", ".join(sorted(other_active)))
    try:
        descriptor = os.open(ACTIVE_MARKER, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return fail(f"another workflow is active: {active_marker_value() or 'unknown'}")
    with os.fdopen(descriptor, "w", encoding="utf-8") as marker:
        marker.write(path.name + "\n")
    return 0


def archive(path: Path, expected_status: str) -> int:
    if seed_files():
        return fail(f"keeping {path}; {SEED_DIR} holds an unrestored seed backup")
    values = frontmatter(path)
    if values.get("status") != expected_status or expected_status not in TERMINAL:
        return fail(f"archive requires matching terminal status, got {values.get('status')!r}")
    if path.parent.resolve() != SPECS_DIR or path.suffix != ".md":
        return fail("refusing to archive a path outside agent-docs/specs")
    destination = SPEC_LOGS_DIR / path.name
    if destination.exists():
        return fail(f"archive destination already exists: {destination}")
    SPEC_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    path.rename(destination)
    if active_marker_value() == path.name:
        ACTIVE_MARKER.unlink(missing_ok=True)
    print(destination.relative_to(REPO_ROOT))
    return 0


def cmd_archive(args) -> int:
    return archive(Path(args.spec).resolve(), args.status)


def cmd_session(_args) -> int:
    if not SPECS_DIR.is_dir():
        return 0
    if seed_files():
        print(
            f"spec lifecycle: keeping active specs; {SEED_DIR} holds an unrestored seed backup. "
            "Run `python3 .harness/bin/seed.py restore`.",
            file=sys.stderr,
        )
        return 0
    marker_value = active_marker_value()
    if marker_value and not (SPECS_DIR / marker_value).is_file():
        ACTIVE_MARKER.unlink(missing_ok=True)
    for path in sorted(SPECS_DIR.glob("*.md")):
        values = frontmatter(path)
        status = values.get("status")
        if status in TERMINAL:
            archive(path, status)
            continue
        handoff = values.get("handoff", "none")
        handoff_path = REPO_ROOT / handoff
        if status in {"draft", "active"} and (handoff == "none" or not handoff_path.is_file()):
            print(
                f"spec lifecycle: {path.relative_to(REPO_ROOT)} is {status} without a handoff; "
                f"review progress from base commit {values.get('base_commit', 'unknown')} before resuming or aborting",
                file=sys.stderr,
            )
    return 0


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    commands = value.add_subparsers(dest="command", required=True)
    validate_command = commands.add_parser("validate")
    validate_command.add_argument("--spec", required=True)
    validate_command.set_defaults(handler=cmd_validate)
    start = commands.add_parser("start")
    start.add_argument("--spec", required=True)
    start.add_argument("--run-id", required=True)
    start.add_argument("--resume", action="store_true")
    start.set_defaults(handler=cmd_start)
    archive_command = commands.add_parser("archive")
    archive_command.add_argument("--spec", required=True)
    archive_command.add_argument("--status", required=True, choices=sorted(TERMINAL))
    archive_command.set_defaults(handler=cmd_archive)
    session = commands.add_parser("session")
    session.set_defaults(handler=cmd_session)
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
