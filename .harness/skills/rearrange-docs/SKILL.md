---
name: rearrange-docs
description: User-invoked rewrite of harness-governed documents after instruction changes in recent commits, so each document states the current rule once and in place, instead of stacking patches over stale text or contradicting other documents. Invoke only when the user asks to rearrange docs.
disable-model-invocation: true
---

# Select commits

1. Run `git log -5 --name-status --format='%h %s'`. Show the user each commit's hash, message, and changed paths. Do not read file contents yet.
2. Ask the user with question cards which commits to process. The user may name older commits instead.
3. If `git status --porcelain` shows uncommitted changes to an in-scope document, ask whether to include them. Otherwise leave them alone.

# Intent

Read the diffs of the selected commits. For each instruction change, write one line covering:
- what rule or behavior was added, changed, or removed;
- what earlier statement it replaces, if any;
- whether the commit message states the purpose (fact) or you inferred it (hypothesis);
- for an added rule, whether it applies generally or only to the case that prompted it. This is a fact only if the commit message or the rule itself states when the rule applies; otherwise it is a hypothesis.

Confirm every hypothesis with the user before the Diagnose step. If the diff conflicts with the code, ask which one is intended. The code stays the ground truth until the user decides.

# Scope

In scope are documents governed by the harness rules in `AGENTS.md` (standalone docs, inline comments, and docstrings):
- `AGENTS.md` and `CLAUDE.md`, outside the managed block (`<!-- harness:begin … -->` to `<!-- harness:end -->`);
- README files and other standalone docs about the changed behavior;
- `agent-docs/` records: `adr`, `rejections`, `handoff`, `synced-comments`, and their `index.md`;
- skill and agent definitions the project owns;
- comments and docstrings in the files the selected commits touched.

Never edit these; report a problem found in them instead:
- the managed block, and files listed in `.harness/manifest.json`. These come from the harness, so carry the change upstream instead.
- `agent-docs/specs/` and `agent-docs/spec-logs/`.
- generated files. Edit their source and regenerate them as the project's `AGENTS.md` describes.

Read `AGENTS.md` and `CLAUDE.md` in full on every run. Find the other related documents by searching the scope for the paths, symbols, commands, terms, and versions the diff touched. Also check the `Related Files` and `Related Symbols` fields in `index.md` and the synced-comment tracking files.

## Last processed commit

`agent-docs/sync-state.json` maps each document path to the last commit this skill processed for that document. Check it for the related documents only, not for the whole scope:
- No entry means the document was never processed.
- Skip, for that document, any selected commit that is the recorded commit or one of its ancestors (`git merge-base --is-ancestor <selected> <recorded>`).
- Run `git log --format='%h %s' <recorded>..HEAD -- <document>`. If it lists commits that are not selected, show them and ask whether to add them. Added commits go through the Intent step.

# Diagnose

Classify each finding in each document as one of:
- `stale`: contradicted or superseded by the change;
- `conflict`: two documents state different rules for the same thing;
- `stacked`: the change was appended as a patch (a trailing note, an exception after an exception, or "previously X, now Y" narration) instead of rewriting the rule where it lives;
- `duplicate`: the same rule restated in several documents. Pick one owner; the others link to it.
- `dangling`: refers to a removed path, symbol, command, option, or version;
- `index`: an `index.md` entry whose summary or related files no longer match the document;
- `obsolete`: still correct but no longer needed, such as a workaround for a problem that is fixed or an instruction for a task that is finished;
- `overfit`: a rule added by the selected commits that is written as a general rule, where the user confirmed it applies only to the case that prompted it.

# Propose

For each file, show its findings, the rewritten text (or a section outline when the rewrite is large), and the source each rewrite aligns with: a diff hunk, code, or another document.

Get user confirmation with question cards, one card per file. Put all `dangling` and `index` findings from every file into a single card. Do not edit before confirmation.

- `conflict`: do not choose a side. Ask the user which statement is intended.
- `obsolete`: propose deleting the text.
- `overfit`: ask the user to choose between narrowing the rule to the condition it applies to, deleting it, and keeping it general.

# Rewrite

- Rewrite each affected section as if you were writing it fresh for the current state. Integrate the change into the existing rule instead of appending it. Delete superseded text instead of annotating it.
- Change meaning only where the confirmed intent requires it. Propose any other improvement separately, labeled as outside the selected commits.
- Keep each document's language, voice, and heading structure.
- Records are history; do not rewrite their past content.
  - For an ADR, propose a superseding ADR or marking it stale under the ADR Rule.
  - Keep rejection reasons and Failed Attempts rows.
  - Move an adopted rejection or a completed handoff to `stale/` under the Index & Staleness Management rule.
- Comments follow Comment Enforcement. Edits to synced comments follow the Shared Comment & Docstring Synchronization rules (version, count, `code_hash`, version log).
- The ADR "DO NOT Include" list applies to every rewritten instruction.
- Before editing a document that has uncommitted changes, save a copy of it for the Verify step.

# Verify

1. Search the scope again for each removed or renamed term. Nothing in scope may still refer to the old rule.
2. Launch a sub agent with a fresh context. Give it, for each edited document, the version from before this run (`git show HEAD:<path>`, or the saved copy), the current version, and the confirmed intent lines and findings. Give it nothing else from this session. It reports:
   - every place where the current version does not read as one coherent current document;
   - every rule, constraint, exception, or stated reason that the previous version had, the current version lacks, and no confirmed finding accounts for.

   For each reported loss, restore the text or ask the user.
3. Run `python3 .harness/git/verify_rules.py`. If it fails, report the failure reason and ask the user whether to revert this run's edits or to fix the problem and continue.
4. When verification passes, set the `agent-docs/sync-state.json` entry of every related document, edited or not, to the newest selected commit.

Do not commit.

# Report

List the edited files with their findings, the findings the user declined, the losses the sub agent reported and how each was resolved, and the problems reported in files outside the editable scope.