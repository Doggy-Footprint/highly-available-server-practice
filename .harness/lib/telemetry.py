"""Best-effort workflow event log for workflow-approach hooks."""
import datetime
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

import config

_VERSION_FILE = config._HARNESS_DIR / "VERSION"


def _telemetry_directory() -> Path:
    override = os.environ.get("HARNESS_TELEMETRY_DIR")
    return Path(override) if override else Path.home() / ".harness" / "telemetry"


def _repo_slug() -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(config.REPO_ROOT))


def _repo_identity() -> str:
    """Return a stable discriminator for paths with the same display slug."""
    root = str(config.REPO_ROOT.resolve()).encode("utf-8")
    return hashlib.sha256(root).hexdigest()[:16]


def telemetry_file() -> Path:
    return _telemetry_directory() / f"{_repo_slug()}-{_repo_identity()}.jsonl"


def _workflow_state_file() -> Path:
    return _telemetry_directory() / f"{_repo_slug()}-{_repo_identity()}.workflow.json"


def _harness_version():
    try:
        return _VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _client(payload: dict):
    transcript_path = payload.get("transcript_path") or ""
    if "/.codex/" in transcript_path:
        return "codex"
    if "/.claude/" in transcript_path:
        return "claude"
    return None


def _valid_workflow(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    run_id = value.get("workflow_run_id")
    spec = value.get("spec")
    spec_version = value.get("spec_version")
    if not isinstance(run_id, str) or not run_id:
        return None
    if not isinstance(spec, str) or not spec:
        return None
    if isinstance(spec_version, bool) or not isinstance(spec_version, int) or spec_version < 0:
        return None
    return {
        "workflow_run_id": run_id,
        "spec": spec,
        "spec_version": spec_version,
    }


def active_workflow() -> dict | None:
    try:
        value = json.loads(_workflow_state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return _valid_workflow(value)


def _write_state(value: dict) -> bool:
    path = _workflow_state_file()
    temporary_name = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as temporary:
            temporary_name = temporary.name
            json.dump(value, temporary, ensure_ascii=False)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
        return True
    except (OSError, TypeError, ValueError):
        return False
    finally:
        if temporary_name:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass


def _state_snapshot() -> tuple[bool, bytes | None]:
    try:
        return True, _workflow_state_file().read_bytes()
    except FileNotFoundError:
        return True, None
    except OSError:
        return False, None


def _restore_state(snapshot: bytes | None) -> bool:
    path = _workflow_state_file()
    if snapshot is None:
        try:
            path.unlink(missing_ok=True)
            return True
        except OSError:
            return False
    temporary_name = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(snapshot)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
        return True
    except OSError:
        return False
    finally:
        if temporary_name:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass


def _clear_state() -> bool:
    try:
        _workflow_state_file().unlink()
        return True
    except OSError:
        return False


def _event_fields(fields: dict) -> dict:
    enriched = dict(fields)
    if "workflow_run_id" in enriched:
        return enriched
    workflow = active_workflow()
    if workflow is None:
        enriched["workflow_run_id"] = None
        enriched["spec"] = None
    else:
        enriched["workflow_run_id"] = workflow["workflow_run_id"]
        enriched["spec"] = workflow["spec"]
    return enriched


def _emit(payload: dict, event: str, **fields) -> bool:
    try:
        line = {
            "v": 1,
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "harness_version": _harness_version(),
            "repo": str(config.REPO_ROOT),
            "client": _client(payload),
            "session_id": payload.get("session_id"),
            "agent_id": payload.get("agent_id"),
            "agent_type": payload.get("agent_type") or None,
            "tool_use_id": payload.get("tool_use_id"),
            "event": event,
            **_event_fields(fields),
        }
        path = telemetry_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def emit(payload: dict, event: str, **fields) -> None:
    _emit(payload, event, **fields)


def workflow_start(run_id: str, spec: str, spec_version: int) -> bool:
    workflow = _valid_workflow(
        {
            "workflow_run_id": run_id,
            "spec": spec,
            "spec_version": spec_version,
        }
    )
    if workflow is None:
        return False
    readable, previous = _state_snapshot()
    if not readable:
        return False
    if not _write_state(workflow):
        return False
    if _emit({}, "workflow_start", **workflow):
        return True
    _restore_state(previous)
    return False


def workflow_phase(run_id: str, phase: str) -> bool:
    workflow = active_workflow()
    if workflow is None or workflow["workflow_run_id"] != run_id:
        return False
    return _emit({}, "workflow_phase", phase=phase, **workflow)


def verifier_result(
    run_id: str, round_number: int, result: str, findings: int, seeds_run: int, seeds_detected: int
) -> bool:
    workflow = active_workflow()
    if workflow is None or workflow["workflow_run_id"] != run_id:
        return False
    return _emit(
        {},
        "verifier_result",
        round=round_number,
        result=result,
        findings=findings,
        seeds_run=seeds_run,
        seeds_detected=seeds_detected,
        **workflow,
    )


def workflow_end(run_id: str, status: str) -> bool:
    workflow = active_workflow()
    if workflow is None or workflow["workflow_run_id"] != run_id:
        return False
    readable, previous = _state_snapshot()
    if not readable:
        return False
    if not _clear_state():
        return False
    if _emit({}, "workflow_end", status=status, **workflow):
        return True
    _restore_state(previous)
    return False
