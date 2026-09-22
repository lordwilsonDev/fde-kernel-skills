---
name: intent-capture
description: "Intent Capture: Understand what the user is trying to accomplish without a form."
order: 1
inputs: ["user_request", "saved_preferences"]
outputs: ["objective", "deliverable", "audience", "constraints", "definition_of_done", "blocking_questions"]
emits_event: true
model_neutral: true
---
# 1. Intent Capture

**Job:** Understand what the user is trying to accomplish without a form.
**User-visible output:** "Here is what I understand you want"

## What it covers
Goal: what outcome? Deliverable: what should exist at the end? Audience. Constraints (time, budget, style, risk, tools, permissions, format). Definition of done: what makes the user say "yes, that is right".

## Model instruction
```text
Read the user's request and infer the intended outcome.
Do not ask a question if the answer is low-impact or can be safely assumed.
State your interpretation in one short sentence.
Identify only the unknowns that would materially change the recommendation, the work performed, the risk, the cost, the audience, or the final format.
If essential information is missing, ask no more than three concise, answerable questions with options.
```

## Observability
Emit one event per run to the spine (`skills/_spine/event.schema.json`): `skill: "intent-capture"`, the inputs actually used, the outputs produced, claims/assumptions/risks, approvals required, timestamp.

## Handoff
Next: skill 02-context-mapper.
