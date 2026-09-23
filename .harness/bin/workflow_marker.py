#!/usr/bin/env python3
"""Record workflow-approach telemetry without affecting the workflow."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import telemetry  # noqa: E402


class _QuietParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)

    def exit(self, status=0, message=None):
        raise ValueError(message or str(status))


def _non_negative(value: str) -> int:
    number = int(value)
    if number < 0:
        raise ValueError(value)
    return number


def _parser() -> argparse.ArgumentParser:
    parser = _QuietParser(add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)

    start = commands.add_parser("start", add_help=False)
    start.add_argument("--run-id", required=True)
    start.add_argument("--spec", required=True)
    start.add_argument("--spec-version", required=True, type=_non_negative)

    phase = commands.add_parser("phase", add_help=False)
    phase.add_argument("--run-id", required=True)
    phase.add_argument("--phase", required=True, choices=("implement_test", "verify", "amend"))

    verifier = commands.add_parser("verifier", add_help=False)
    verifier.add_argument("--run-id", required=True)
    verifier.add_argument("--round", required=True, type=_non_negative)
    verifier.add_argument("--result", required=True, choices=("pass", "retry", "limit"))
    verifier.add_argument("--findings", required=True, type=_non_negative)
    verifier.add_argument("--seeds-run", required=True, type=_non_negative)
    verifier.add_argument("--seeds-detected", required=True, type=_non_negative)

    end = commands.add_parser("end", add_help=False)
    end.add_argument("--run-id", required=True)
    end.add_argument("--status", required=True, choices=("complete", "limit", "handoff", "aborted"))
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if not args.run_id:
            return 0
        if args.command == "start":
            telemetry.workflow_start(args.run_id, args.spec, args.spec_version)
        elif args.command == "phase":
            telemetry.workflow_phase(args.run_id, args.phase)
        elif args.command == "verifier":
            telemetry.verifier_result(
                args.run_id,
                args.round,
                args.result,
                args.findings,
                args.seeds_run,
                args.seeds_detected,
            )
        elif args.command == "end":
            telemetry.workflow_end(args.run_id, args.status)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
