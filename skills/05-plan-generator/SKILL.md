---
name: plan-generator
description: "Plan Generator: Turn evidence and intent into a plan the user can inspect, alter, or approve."
order: 5
inputs: ["objective", "evidence_register", "authority_decision"]
outputs: ["plan"]
emits_event: true
model_neutral: true
---
# 5. Plan Generator

**Job:** Turn evidence and intent into a plan the user can inspect, alter, or approve.
**User-visible output:** "Recommended plan"

## What it covers
Outcome, steps, dependencies, decision points (where approval matters), risks, fallback.

## Model instruction
```text
Generate the smallest plan that can safely produce the requested outcome.
Prefer reversible steps before irreversible steps.
Separate: immediate next action, decisions requiring the user, background work, deferred improvements.
For complex work, present the plan before acting. For simple work, act and provide a concise summary.
```

## Observability
Emit one event per run to the spine (`skills/_spine/event.schema.json`): `skill: "plan-generator"`, the inputs actually used, the outputs produced, claims/assumptions/risks, approvals required, timestamp.

## Handoff
Next: skill 06-execution-orchestrator.
