# Documentation Guide

"Documentation" refers to standalone docs, inline comments, and docstrings.

## Principles
1. **Code is the Ground Truth**: Document only non-obvious rationale, behaviors, and constraints that cannot be inferred from the code.
2. **Preserve Rejection Reasons**: Rejected design alternatives keep their rejection reason.
3. **Preserve Failed Attempts**: Handoffs keep attempted-but-failed approaches.

### Comment Enforcement

A comment/docstring is allowed only when it records a non-obvious:
- design constraint,
- external-system,
- safety/security invariant, or
- reason a seemingly odd implementation is necessary.

Do not use comments to narrate code, restate names/types/control flow, provide tutorials, or justify ordinary implementation choices.

## Index & Staleness Management
1. Every agent-managed directory (e.g., `agent-docs/adr`, `agent-docs/rejections`, `agent-docs/handoff`) must contain `index.md` and `stale.md`.
2. File Naming: `<16-char-hex-id>-<kebab-case-name>.md` (e.g., `3f8a9c12b0e45d67-auth-flow.md`).
3. `index.md` Format: entries separated by `---`:
   ````
   File: <file-name>
   Summary: <one-line summary>
   Related Files: <comma-separated repo paths>
   Related Symbols: <comma-separated function/class/module names>
   ````
4. `stale.md` Format: append one stale file per line.

## Shared Comment & Docstring Synchronization Rules

Apply when an identical comment or docstring must be maintained across multiple locations:

1. Synced ID: a random 48-bit hex ID (12 hex characters, e.g., a1b2c3d4e5f6).
2. Tracking file: `agent-docs/synced-comments/<synced_id>.md`. `code_hash` hashes the participating files' contents with comments stripped, concatenated in alphanumeric filename order:
   ````
   ---
   version: 1
   count: <number of associated code locations>
   code_hash: <hash of participating files' non-comment content>
   ---

   # Content
   <Write the shared comment or docstring here>

   # Version Log
   ## v1 Log
   - Initial creation.
   ````
3. Code tag: every associated code location includes `synced id: <synced_id>, version: <n>, count: <n>`.
4. Update: when the shared text is edited, or a code change alters the recomputed `code_hash`, increment the version in the frontmatter and every code tag, recompute `code_hash`, and add a `# Version Log` entry.
5. Removal: when removing the shared content entirely,
   - remove it from every referenced code location;
   - increment the version, record the removal reason in the version log, and add `obsolete: true` to the frontmatter.

## Architecture Decision Record Rule

Propose an ADR to the user with the checklist and contents below; never write one on your own decision.
ADRs record past architectural decisions, not immutable principles.

### Checklist for updating ADR

Create an ADR only if all hold:

- [ ] The decision is expensive or risky to reverse.
- [ ] A concrete alternative was seriously considered and rejected.
- [ ] The reason for the decision cannot be reliably recovered from the code alone.

### Contents

- Title / Status
- Context
- Decision
- Alternatives: actually considered but rejected (capped to 1-2)
- Consequences: positive / negative (capped to 1-2 each)

#### DO NOT Include

- Tutorials, concepts.
- Rhetorical expressions.
- Non-deterministic sentences.
- Non-falsifiable sentences.
- Session-dependent sentences.

## Rejection Record Rule

Directory: `agent-docs/rejections/`.

Applies when the user rejects a concretely proposed design alternative and the reason cannot be recovered from code. Show the draft to the user and write only after confirmation. If all ADR checklist items hold, propose an ADR (its Alternatives section) instead of a rejection record.

Required file structure:

- `#` Title
- `## Context`
- `## Rejected Alternative`
- `## Reason`
- `## Revisit Condition`
- `## Chosen Instead` (repo path or ADR file)

The ADR "DO NOT Include" list applies.

When the revisit condition is met and the alternative is adopted, append the file to `stale.md`.

## Handoff Rule

Directory: `agent-docs/handoff/`.

Write when a task stops incomplete: contract-workflow Limit reached, the user pauses or stops mid-task, or the user requests it.

Required file structure:

- `#` Title
- `## Goal` (user's original words)
- `## State` (branch, commit, changed files)
- `## Failed Attempts` (table `| attempt | failure evidence | cause |`, cause marked `verified` or `hypothesis`)
- `## Next Step`
- `## Open Questions`
- `## Contract Snapshot` (contract content at stop, or `none`)

When resuming, never delete or edit existing Failed Attempts rows; only append.

When the task completes, append the file to `stale.md`.

# Task Guide

## User Decision

DO NOT decide unspecified task details yourself. Talk back freely to resolve unspecified or ambiguous ones.
