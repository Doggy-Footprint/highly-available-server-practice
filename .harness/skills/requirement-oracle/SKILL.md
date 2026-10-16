---
name: requirement-oracle
description: Help a user make unresolved functional or ISO quality decisions for a workflow spec. Use when intent, scope, expected behavior, quality applicability, measures, thresholds, or coverage targets cannot yet be approved.
---

# Spec Decision Support

Help the user make informed decisions; never decide unspecified behavior silently. Present choices in the `workflow-approach` Brief format and audience: Ask, Decided for you, and New concept.

Read the relevant code, tests, configuration, and project documentation to resolve repository-answerable questions first. For remaining choices, state the decision and why it is needed in plain language. Compare 2–3 meaningful options through concrete examples of resulting behavior and trade-offs. Recommend one with relevant codebase or domain evidence, and name any uncertainty and the evidence needed to reduce it. End with the specific choice the user needs to make.

Resolve functional intent, observable failure behavior, boundaries and state transitions together with verification scope. Distinguish observable target surfaces from test layers and define required variant/layer combinations. Express scope as ISO/IEC/IEEE 29119-4 test design techniques, their enumerated coverage items, and a coverage target; a target below 100% names the selected items and rationale. Structure-based targets are measured by main through the Test command. Clarify lifecycle terms such as re-import versus restart. Do not assume a Cartesian product or narrow away an in-scope requirement. Separate a missing requirement from optional evidence strengthening, and explain what evidence will be sufficient for acceptance. Evaluate all nine ISO/IEC 25010:2023 product quality characteristics for applicability. For applicable characteristics, help select a context-specific measure, inputs, unit, threshold and direction, and automated, review, or mutation evidence. Decide whether fuzzing applies (surface, oracle, budget) and the mutation tool's sample cap and survival threshold. ISO/IEC 25023 measure definitions do not determine the project's pass threshold, and 29119-4 coverage measures do not determine its coverage target. State that distinction when presenting a threshold or target choice.

When a choice is easy to fix later and the user has not stated otherwise, recommend a default the user can veto, chosen by `workflow-approach` Identity and lifecycle rule 7. A choice that is not easy to fix later, as defined in `workflow-approach`, stays an Ask item: if the user cannot decide, leave it unresolved and `workflow-approach` pauses. Mark every default's evidence and uncertainty. Optional quality characteristics may be marked not applicable only with a reason.

Return spec-ready decisions with stable provisional ids, chosen behavior or quality target, rejected options and trade-offs, evidence, uncertainty, and whether the user answered, approved, or vetoed it. `workflow-approach` owns paths, signatures, commands, final ids, lifecycle, and the complete spec.
