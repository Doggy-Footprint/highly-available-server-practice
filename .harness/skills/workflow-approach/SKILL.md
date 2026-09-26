---
name: workflow-approach
description: Spec-first implementation and test workflow with implementer, test-implementer, and test-verifier subagents. Use before feature/fix level implementation or debugging. Not for typo fixes, renames, config or doc edits, or local bug fixes.
---

# Spec

A spec is the approved, versioned source of truth for one workflow run. The
main agent alone creates and amends it. Subagents consume the assigned version
and never choose missing behavior.

## Identity and lifecycle

1. Active path: `agent-docs/specs/<16-hex-run-id>-<kebab-name>.md`.
2. Archived path: `agent-docs/spec-logs/<same-file-name>`.
3. `specs/` and `spec-logs/` are excluded from Index & Staleness Management.
4. Frontmatter fields are `version`, `run_id`, `status`, `base_commit`,
   `max_verifier_invocations`, and `handoff`. Status is `draft`, `active`,
   `complete`, `limit`, or `aborted`; use `handoff: none` when absent.
5. Amendment increments `version` and adds a Version Log entry. Never change an
   approved expectation silently. Reconfirm any behavior, quality target, or
   verification policy changed by an amendment.
6. Before dispatch, the user approves the whole spec. If a required decision is
   unresolved, pause. Use `requirement-oracle` when the user lacks enough domain
   or codebase evidence to decide.
7. Only after the user explicitly delegates an unresolved required decision may
   the main agent choose a default. Preserve safety, security, compatibility,
   data, and existing observable behavior in that order; record the choice,
   evidence, uncertainty, and delegation in `# Assumptions and Defaults`.
   Optional quality characteristics may be excluded with a recorded reason.

## Required format

````
---
version: <positive integer>
run_id: <16 lowercase hexadecimal characters>
status: draft|active|complete|limit|aborted
base_commit: <full commit id at workflow start>
max_verifier_invocations: 2
handoff: none|<repo-relative handoff path>
---

# User Intent
| id | stakeholder | intention | observable goal |

# Scope
In scope: <behavior and product boundary>
Out of scope: <explicit exclusions>

# Paths
Implementation: <comma-separated repo paths>
Tests: <comma-separated repo paths>
Test command: <one shell command covering all automated functional and quality checks; fails when a structure-based coverage target is missed>
Review evidence: <named procedure/output, or none — reason>

# Signatures
<signature per line>

# Functional Requirements
| id | requirement | priority | source |

# Errors
<failure condition — observable signal, including non-exception failures — post-failure state>

# Cases
| id | level | input / state | expected result |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| Functional suitability | yes|no | ... |
| Performance efficiency | yes|no | ... |
| Compatibility | yes|no | ... |
| Interaction capability | yes|no | ... |
| Reliability | yes|no | ... |
| Security | yes|no | ... |
| Maintainability | yes|no | ... |
| Flexibility | yes|no | ... |
| Safety | yes|no | ... |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | user approval or explicit delegation |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |

# Workflow Control
| item | value |
| correction batches used | 0 |
| verifier invocations | 0 |
| open finding ids | none |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |

# Version Log
## v<n>
- <what changed and the evidence or decision that forced it>
````

Every intent, requirement, Case, quality requirement, obligation, and assumption
has a stable id. Each applicable quality characteristic has at least one quality
requirement. Each quality requirement defines the measured property and context,
method and input quantities, unit, threshold and pass direction, evidence
procedure, and source. ISO/IEC 25023 supplies measure concepts and ISO/IEC/IEEE
29119-4 supplies test design techniques with their coverage measures; neither
supplies project-specific pass thresholds or coverage targets. The user approves
both.

`level` is `normal`, `boundary`, `error`, or `edge`; include every level or a
`none — <reason>` row. Error rows name both signal and post-failure state.
Implementation and Tests paths are disjoint. The implementer never reads Tests;
test roles never read Implementation.

# Verification model

Define a finite set of independently checkable obligations before dispatch. Each
row identifies the required variant, observable target surface, test layer,
selection policy, and one ISO/IEC/IEEE 29119-4 test design technique with its
coverage items and approved coverage target. Coverage is exercised coverage items
divided by declared coverage items. Distinguish test layer (unit, integration,
end-to-end) from Case `level`. Define lifecycle boundaries such as same-process
re-import versus restart. Resolve ambiguous selection or boundary terms before
approval; never let a test role choose missing policy.

- Specification-based: equivalence partitioning, classification tree, boundary
  value analysis (2- or 3-value), syntax, combinatorial (each choice, base choice,
  pairwise, all combinations), decision table, cause-effect graphing, state
  transition, scenario, random, and metamorphic testing. Enumerate coverage items
  finitely as stable ids or an explicit list; listing targets and variants does not
  imply their Cartesian product. A target below 100% names the selected items and
  the rationale.
- Structure-based: statement, branch, decision, branch-condition, branch-condition
  combination, MC/DC, and data flow testing. The spec names the measuring tool and
  the Implementation scope; main measures coverage through the Test command and
  maps each shortfall to behavior. Unexercised code for undeclared behavior is a
  spec gap or implementation defect; for declared behavior it is a test defect.
  Test roles receive only that behavior and measured values, never Implementation
  locations.
- Experience-based (error guessing): coverage items are the guessed defects; the
  target is `none — experience-based`.

Derive obligations from every in-scope requirement, including errors and quality
requirements. Select the techniques the behavior or approved risk policy requires;
justify excluded techniques and dimensions. A finite map does not excuse a missing
user requirement. Such omissions are spec challenges, not permission to expand
test scope silently.

Evidence is sufficient when it observes the required behavior at the declared
surface and layer, uses an independent expected result, distinguishes the
specified failure from success, and meets the approved coverage target. A test
name or filled map is not proof. Additional
examples alone do not establish a gap: a blocking finding must identify a required
obligation and a concrete violating behavior the current evidence fails to reject,
or cite a precise conflict or omission in the approved requirements.

Prefer automated evidence. Review evidence needs a repeatable procedure, inputs,
observation, expected result and named artifact. Mutation evidence supplements
these checks. Main selects the 2–3 strongest distinct defect classes from the audit,
or all if fewer, including on an initial pass with no findings, and records why
they are strongest. A mutation counts only if it executes and the intended
assertion detects it; setup failures and unrelated failures are inconclusive.

Carry audit state between fresh verifiers. Acceptance is scoped to the spec version,
evidence revision and dependencies, not a permanent exemption. Main marks affected
entries invalidated after changes to requirements, tests, helpers, procedures or
implementation behavior; record the impact and why other entries remain valid.
Changed shared helpers can invalidate several obligations. A verifier checks this
impact assessment and reopens acceptance only with new evidence of a defect,
changed dependency or missed requirement. Never inherit acceptance blindly or
restart scope derivation merely because the verifier is fresh.

# Subagent model

Use the model and effort in each installed agent definition. Override them only
when the user names a model.

# Telemetry

Telemetry commands are best-effort: never inspect their result or let failure
change the workflow.

```sh
python3 .harness/bin/workflow_marker.py start --run-id ID --spec NAME --spec-version N
python3 .harness/bin/workflow_marker.py phase --run-id ID --phase implement_test
python3 .harness/bin/workflow_marker.py phase --run-id ID --phase verify
python3 .harness/bin/workflow_marker.py phase --run-id ID --phase amend
python3 .harness/bin/workflow_marker.py verifier --run-id ID --round N --result pass|retry|limit --findings N --seeds-run N --seeds-detected N
python3 .harness/bin/workflow_marker.py end --run-id ID --status complete|limit|handoff|aborted
```

Emit `start` before the initial dispatch. Emit `implement_test` before the parallel
roles. Emit `verify` before dispatching a verifier.
Emit one `verifier` marker after every verifier result. Emit `amend` before every amendment or correction. Emit
`end complete` after completion, `end limit` when the verifier budget is exhausted,
`end handoff` for a nonterminal handoff, and `end aborted` after an approved
recovery abort. Do not emit markers for ordinary tool activity.

# Workflow

1. **Recover or ground (main).** Before creating a spec, inspect `specs/`. If an
   active spec exists, do not start another workflow. If its handoff is valid,
   resume only when requested. Without a handoff, compare `base_commit` to HEAD,
   summarize progress and drift, and ask the user whether to resume or archive it
   as aborted. Read deciding code yourself; delegate only location discovery. For
   pre-0.10 specs, reconcile obligations and audit state with the verification
   model before dispatch, giving each obligation a technique, coverage items and
   target. Do not infer prior acceptance from a passing suite. Obtain approval
   for changed verification policy and preserve invocation counts and history.
2. **Draft and approve (main).** Derive functional requirements and all nine
   quality applicability decisions. Use `requirement-oracle` for decisions the
   user cannot assess. Define measures, thresholds, 29119-4 techniques, coverage
   items and targets, evidence, and traceability with
   `max_verifier_invocations: 2`. Obtain whole-spec approval, set status
   `active`, then run and check:
   `python3 .harness/bin/spec_lifecycle.py start --spec PATH --run-id ID`.
   Emit telemetry start only after lifecycle start succeeds.
3. **Implement + test (parallel).** Emit `implement_test`; dispatch both roles on
   the same spec version without sharing outputs. Instructions are task-specific
   and complete:
   - implementer: path/version, implementation direction, quality constraints,
     risks, allowed non-Test checks, and excluded approaches;
   - test-implementer: path/version, conventions, risk model, 29119-4 techniques
     and coverage items, independent oracle, automated and review evidence, test
     level, and excluded approaches.
4. **Reconcile (main).** Collect both reports using bounded waits. If a subagent
   stalls, interrupt and diagnose before retrying. Resolve challenges with
   spec/code evidence; amend or reject each with a reason. Reopen prior spec
   decisions only with new evidence, and leave dependent work blocked until the
   user resolves any required decision. When unblocked, run the exact Test command
   with a finite timeout suited to its expected runtime. Classify failures as
   implementation defect, test defect, evidence defect, or spec gap and queue one
   correction batch. A timeout is a failure to investigate, never a pass or a
   reason for an unchanged automatic retry.
5. **Verify (fresh test-verifier).** After a passing Test command, dispatch a fresh
   verifier with the spec path/version, complete coverage/evidence map, audit state,
   change-impact assessment, and finding ledger. Check every obligation has a current disposition; audit pending and
   invalidated evidence and assess any new challenge to retained acceptance.
   Before dispatch, check and persist the incremented `verifier invocations` count
   in Workflow Control. At most two invocations are allowed per run, including the
   initial audit and failed, interrupted, or incomplete audits. Resume and spec
   amendments preserve the count; replacement runs must not evade the limit.
   Use the invocation count for telemetry `--round`. Apply the stop condition if
   the required audit would exceed the budget.
6. **Triage and mutate (main).** Resolve findings with stable ids, spec versions,
   affected obligations/variants, evidence, dispositions, and mutation outcomes.
   Classify each item as an obligation evidence gap, a spec challenge, or advisory.
   A spec challenge cites the conflicting or missing requirement and routes to an
   amendment/user decision; optional strengthening is advisory and does not block
   completion. Do not downgrade an actual requirement gap to advisory. Update audit
   state with evidence-backed dispositions. Exercise the selected strongest defect
   classes, prioritizing blocking findings, one mutation at a time, without exposing
   implementation or injected diffs to test roles:
   1. `python3 .harness/bin/seed.py backup <every edited file>`.
   2. Inject the violating behavior and run Test command with a finite timeout
      suited to its expected runtime.
   3. `python3 .harness/bin/seed.py restore` before continuing or handing off;
      stop if restore fails and record the outstanding backup.

   Green confirms a gap only when the mutation executed; failure rejects a finding
   only when the intended assertion detects the violation. For an inconclusive
   result, retry with a changed probe that distinguishes execution from the
   observed failure, or mark the finding blocked and hand off if none is available.
   Triage every finding before redispatch or closure, including the final audit:
   evidence-backed rejections need no further audit when tests, evidence procedures,
   and approved expectations are unchanged.
7. **Correct as one batch (main).** Ordinary implementation, test, evidence, and
   spec corrections have no count limit. For each retry, record the failure
   signature, cause hypothesis, changed approach or new evidence, and observed
   result in the execution ledger. Continue only with a concrete diagnostic or
   justified correction; never repeat a failed approach without new evidence.
   When a resolved finding recurs or edits oscillate, compare prior attempts and
   re-evaluate the cause before editing again. Apply the stop condition when no
   next step is available or the correction requires an audit beyond the budget.

   Emit `amend` and increment the correction count for history. Redispatch
   complete replacement instructions, continuing existing agents where possible.
   Implementation defects receive ids and observable behavior, never test code.
   Test/evidence defects receive rules, variants, and sanitized evidence, never
   implementation diffs. Correct the cause across all declared obligations sharing
   the defective pattern or helper; report the full affected set, including checked
   siblings needing no change. Do not add undeclared combinations during this sweep.
   Update evidence references and invalidate affected acceptance before redispatch.
   A spec gap increments spec version after required approval and redispatches both
   roles. Reconcile, rerun the restored Test command, repeat confirming mutations,
   then return to Verify for a fresh audit.
8. **Stop condition.** Complete only when every required functional and quality
   obligation passes at its approved coverage target, review artifacts exist, the
   verifier audit is complete with no open blocking finding, every obligation has
   current accepted evidence, and the selected confirming mutations fail for the
   intended assertion. Advisory suggestions may remain; unresolved spec challenges
   may not.
   If further verification is required after two invocations, stop with status
   `limit` before making corrections that require that audit. For ordinary
   corrections blocked on a user decision or external change, finish independent
   work and request what is missing, keeping the spec active for a nonterminal
   handoff. Use the same handoff when no new discriminating check or justified
   correction is available.
9. **Close or hand off (main).** For success, set status `complete`, archive with
   `python3 .harness/bin/spec_lifecycle.py archive --spec PATH --status complete`,
   then emit end complete. For verifier-budget exhaustion, write a handoff, set
   `handoff` and status `limit`, archive with `--status limit`, then emit end limit.
   For a nonterminal stop, write the handoff, store its path in the still-active
   spec, and emit end handoff without archiving. Report spec version/path, evidence
   map, finding dispositions, correction causes and count, verifier count,
   mutations, blocked ids, and handoff if any.
