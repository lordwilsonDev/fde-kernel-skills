---
name: feedback-learning-loop
description: "Feedback & Learning Loop: Let the user say what they dislike, revise quickly, and improve future work without uncontrolled memory."
order: 10
inputs: ["deliverable", "user_feedback", "workspace_policy"]
outputs: ["revised_deliverable", "change_note", "memory_write_request"]
emits_event: true
model_neutral: true
---
# 10. Feedback & Learning Loop

**Job:** Let the user say what they dislike, revise quickly, and improve future work without uncontrolled memory.
**User-visible output:** "Updated result and what changed"

## What it covers
Controls: Revise this / Too long / Too short / Wrong direction / More practical / More technical / Show alternatives / Change assumptions / Something else, then only the needed follow-up. Memory levels: session context (temporary), reusable preference (save with notice or user setting), approved decision (save as governed workspace policy), lesson (save only after review/approval).

## Model instruction
```text
Treat user feedback as a revision request first.
After revising, show: what changed, what did not change, and any assumption that remains.
Do not save a preference, policy, or lesson permanently unless the user explicitly asks, workspace policy permits automatic preference memory, or it is an approved organizational rule.
Never silently convert one-off criticism into permanent user memory.
```

## Observability
Emit one event per run to the spine (`skills/_spine/event.schema.json`): `skill: "feedback-learning-loop"`, the inputs actually used, the outputs produced, claims/assumptions/risks, approvals required, timestamp.

## Handoff
Next: back to skill 01 with approved preferences and decisions only.
