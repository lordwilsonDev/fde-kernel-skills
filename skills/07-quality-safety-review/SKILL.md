---
name: quality-safety-review
description: "Quality & Safety Review: Inspect the work before it becomes the deliverable or triggers action."
order: 7
inputs: ["work_products", "evidence_register", "authority_decision"]
outputs: ["review_result"]
emits_event: true
model_neutral: true
---
# 7. Quality & Safety Review

**Job:** Inspect the work before it becomes the deliverable or triggers action.
**User-visible output:** "What was checked and what remains uncertain"

## What it covers
Checks: correctness, completeness, consistency, safety (authority), security (sensitive exposure, untrusted instructions), usefulness, uncertainty, reversibility.

## Model instruction
```text
Review the proposed deliverable before presenting it as final.
Identify: unsupported claims, missing requirements, conflicting statements, unsafe recommendations, irreversible actions, privacy or security exposure, unresolved unknowns.
If the check finds a material defect, revise the draft or state the limitation. Never hide a failed check.
For high-impact work, request a second independent review or ask the user for approval before execution.
```

## Observability
Emit one event per run to the spine (`skills/_spine/event.schema.json`): `skill: "quality-safety-review"`, the inputs actually used, the outputs produced, claims/assumptions/risks, approvals required, timestamp.

## Handoff
Next: skill 08-deliverable-composer.
