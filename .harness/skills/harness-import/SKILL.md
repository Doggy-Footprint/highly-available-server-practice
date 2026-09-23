---
name: harness-import
description: Read how an installed copy of this harness was modified locally, judge which edits generalize, and propose them as changes to the harness payload. Use when carrying a downstream project's local harness edits back upstream.
---

# Run

1. Work from the harness development repository, not the installed project.
2. `python3 installer/harness.py import <target> --json` produces the drift. Do not hand-roll a `git diff` for this — the CLI owns the deterministic part.
3. The diff baseline is the *current* harness source, so a hunk may mix the user's edit with an upstream change made since that target was installed. The report prints both versions; use them to tell the two apart before attributing intent.

# Branch

Before any edit, create `harness-import/<target-name>` in the harness repo. Never work on the default branch.

# Interpret

For each hunk, and for each `added` path:

1. What changed — fact.
2. Why it was likely changed — mark this as a hypothesis, never as fact.
3. Project-specific, or general to the harness.

Rules:
- Not every drift is an improvement. When an edit only makes sense for that project, report it as project-specific and propose nothing.
- An edit you cannot explain is reported as unexplained, not guessed into a rationale.
- A `missing` path means the user deleted a harness file. Treat the deletion itself as the signal.

# Propose

Turn only the generalizable edits into concrete edits to `harness/`. Show them to the user. Do not touch `harness/` before confirmation.

# Apply

For each approved item:

1. Edit `harness/`, never `.harness/` or the generated files.
2. `python3 installer/harness.py upgrade .`
3. `python3 -m unittest tests/test_installer.py`

# Report

Adopted, classified project-specific, unexplained, deferred — each listed by path. Name the branch.
