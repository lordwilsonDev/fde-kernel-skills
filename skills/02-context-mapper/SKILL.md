---
name: context-mapper
description: "Context Mapper: Map the working environment before making strong claims or acting."
order: 2
inputs: ["objective", "approved_files", "saved_preferences"]
outputs: ["context_map"]
emits_event: true
model_neutral: true
---
# 2. Context Mapper

**Job:** Map the working environment before making strong claims or acting.
**User-visible output:** "What I will use / what is missing"

## What it covers
Available (files, systems, tools, prior decisions). Unavailable (missing sources, permissions, facts, APIs). Sensitive (private data, credentials, production, legal/financial/health, customer info). Conflicted (contradictory files, stale plans, unclear ownership).

## Model instruction
```text
Create a context map before making high-impact recommendations or taking action.
Separate information into: confirmed facts, user-provided preferences, assumptions, missing information, conflicting evidence, restricted information.
Never present an assumption as a confirmed fact.
Ask follow-up questions only when resolving the answer would change the deliverable or make execution safer.
```

## Observability
Emit one event per run to the spine (`skills/_spine/event.schema.json`): `skill: "context-mapper"`, the inputs actually used, the outputs produced, claims/assumptions/risks, approvals required, timestamp.

## Handoff
Next: skill 03-scope-governance.
