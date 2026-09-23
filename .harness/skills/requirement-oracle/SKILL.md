---
name: requirement-oracle
description: Help a user make unresolved functional or ISO quality decisions for a workflow spec. Use when intent, scope, expected behavior, quality applicability, measures, or thresholds cannot yet be approved.
---

# Spec Decision Support

Help the user make informed decisions; never decide unspecified behavior merely
to unblock the workflow.

Read the relevant code, tests, configuration, and project documentation before
asking questions that the repository can answer. For remaining choices, explain:

- the decision and why the spec needs it;
- codebase and domain context that changes the answer;
- 2–3 meaningful options, their consequences and trade-offs;
- a recommended option and the evidence supporting it;
- what evidence would reduce remaining uncertainty.

Resolve functional intent, observable failure behavior, boundaries and state
transitions together with verification scope. Distinguish observable target surfaces
from test layers; define required variant/layer combinations, exhaustive versus
representative selection and the representatives with their rationale. Clarify
lifecycle terms such as re-import versus restart. Do not assume a Cartesian product
or narrow away an in-scope requirement. Separate a missing requirement from optional
evidence strengthening, and explain what evidence will be sufficient for acceptance. Evaluate all nine ISO/IEC 25010:2023 product quality characteristics
for applicability. For applicable characteristics, help select a context-specific
measure, inputs, unit, threshold and direction, and automated, review, or mutation
evidence. ISO/IEC 25023 measure definitions do not determine the project's pass
threshold. State that distinction when presenting a threshold choice.

If the user cannot decide, leave the item unresolved and `workflow-approach`
pauses. Only after explicit delegation recommend a conservative default that
preserves safety, security, compatibility, data, and existing observable behavior.
Mark its evidence and uncertainty. Optional quality characteristics may be marked
not applicable only with a reason.

Return spec-ready decisions with stable provisional ids, chosen behavior or
quality target, rejected options and trade-offs, evidence, uncertainty, and the
user's approval or explicit delegation. `workflow-approach` owns paths,
signatures, commands, final ids, lifecycle, and the complete spec.
