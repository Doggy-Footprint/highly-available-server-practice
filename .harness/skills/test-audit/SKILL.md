---
name: test-audit
description: User-invoked audit of an existing test suite (for example tests written before the harness was installed) that leaves feature-grouped handoffs for follow-up workflow-approach runs. Invoke only when the user asks for a test audit.
disable-model-invocation: true
argument-hint: "[path]"
---

# Scope

The argument is a path to audit; without one, audit the whole repository. Run `python3 .harness/bin/test_scan.py <path>` first. It lists test files and tests in python, javascript/typescript, go, rust, java, kotlin, csharp/C#, swift, php, ruby, and C/C++, suspicious signals (see Flag review), runner candidates, and `predates_harness`. Read only flagged files and files relevant to a feature under review, to save tokens. The scanner is rule-based and approximate for non-Python languages; verify a flag by reading before relying on it.

For each `language` in the scan's `files`, read `languages/<language>.md` next to this file before reviewing those files. It lists what the scanner misses, framework-specific checks, false positives per flag, and how to run one test and collect coverage. Also read it for a language whose test files appear only in `inventory`, since the scanner misses some frameworks. Skip other languages.

# Flag review

| flag | confirm by reading | false positives in any language |
| --- | --- | --- |
| `skip` | the skip is unconditional or still applies; group-level skips cover this test | conditional skips that run in CI; `skip` in a name or string |
| `xfail` | the expected failure is still real and tracked | known-issue wrappers around code that does pass |
| `focused` | `only`/`fit`/`focus` is a leftover that hides sibling tests | intentional focus in a local-only draft |
| `no_assert` | no check at all, not even a helper or implicit one | assertions inside helper functions or fixtures; custom matchers |
| `empty` | the body has no statements | tests whose work is in setup hooks or attributes |
| `sleep` | the sleep waits on real time instead of a condition | sleeps in a string or comment |
| `heavy_mock` | mock setup dominates and the unit itself is barely exercised | many stubs for a legitimately wide collaborator |
| `duplicate_name` | a second test shadows or repeats the first | the same name in different classes or groups of one file |
| `trivial_assert` | the assertion cannot fail | placeholders inside generated code or fixtures |
| `mock_only_assert` | the test checks only that mocks were called, not behavior | verifying a side-effect-only collaborator is the real contract |
| `snapshot_only` | the snapshot is reviewed and meaningful, not auto-accepted | snapshots of small stable values that are real contracts |
| `broad_exception` | the expected error type or message is not pinned | exception base type is the documented contract |
| `swallowed_error` | the caught error is neither asserted nor rethrown | deliberate best-effort cleanup; body boundaries are approximate when braces appear in strings |
| `nondeterministic` | time, randomness, or ids reach an assertion unfixed | guards in shared helper files; value only logged or used for timing |
| `retry` | retries hide a flaky test instead of fixing it | retry attribute on a test of retry logic |
| `incomplete` | the test is a stub, todo, or pending placeholder | `TODO` text in a test of todo-list features |

# Intent

Confirm what the project does at product level before judging any test.

1. Use documentation the user provides.
2. Otherwise draft a feature list from the README and code, and confirm it with the user using question cards. Use `requirement-oracle` for decisions the user cannot yet make.
3. Make no feature judgment (keep, delete, missing) before the user confirms the list.

# Run

1. Use the detected runner from the scan; ask the user when several candidates exist or none does.
2. Run the suite. Record failures, skips, and slow tests.
3. Rerun each failure alone, using the single-test command from the language file, to separate flaky from deterministic failures.
4. Collect coverage if the project already supports it, as described in the language file; do not install tooling.

# Spec check

Read `agent-docs/spec-logs` and confirm that each archived spec's Verification Obligations are still covered by existing tests. Report an uncovered obligation by spec path and obligation id.

# Quality

Review the flagged and feature-relevant tests for:
- weak assertions (no assertion, trivially true, only checks no exception);
- implementation coupling (asserts private details or call order rather than behavior);
- over-mocking (the test verifies mocks, not the unit);
- duplicates;
- tests for features absent from the confirmed list: deletion candidates.

# Effectiveness

Per feature, sample hand mutations (a changed condition, boundary, operator, or return value) and check that a test fails.

1. `python3 .harness/bin/seed.py backup <files>` before mutating, `python3 .harness/bin/seed.py restore` after each mutation round.
2. If restore fails, stop immediately, report the failure, and do not continue.
3. Record each mutation and whether it was killed. A surviving mutation is a missing or weak test.

# Classify

Group every finding by feature, each as one of: delete tests, add tests, fix tests, fix implementation. Split any group that is larger than one workflow-approach run into several groups.

# Handoff

Write one `agent-docs/handoff/<16-hex-id>-test-audit-<feature>.md` per group, following the Handoff Rule structure in `AGENTS.md`:

- `## Spec` is `none — to be created by a follow-up workflow-approach`.
- `## Execution Ledger` holds the scan, run, and mutation evidence for that group.
- Add a matching entry to `agent-docs/handoff/index.md`.

Do not edit code or tests, other than the temporary hand mutations restored through `seed.py`.

# Report

List the groups (feature, finding kinds, handoff path) and the recommended order to run them.
