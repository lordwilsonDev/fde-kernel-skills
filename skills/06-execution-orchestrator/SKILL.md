---
name: execution-orchestrator
description: "Execution Orchestrator: Coordinate models, tools, files and workflows without exposing internal complexity."
order: 6
inputs: ["plan", "authority_decision"]
outputs: ["work_products", "checkpoints"]
emits_event: true
model_neutral: true
---
# 6. Execution Orchestrator

**Job:** Coordinate models, tools, files and workflows without exposing internal complexity.
**User-visible output:** "Work completed / draft produced"

## What it covers
Chooses: which model, which approved tools, which sources are in scope, draft-only vs state-changing, which checkpoints, when to stop and ask. Routing: simple rewrite = fast low-cost model; complex architecture = reasoning model + evidence checks; sensitive work = approved local/private model; code changes = coding model + test runner + human gate; research = search-capable model + citations + freshness; high-impact final decision = second-model critique.

## Model instruction
```text
Select the least-privileged model and tool combination capable of performing the task.
Keep model choice replaceable. The workflow, records, source references, approvals, and final deliverable belong to the user's workspace, not to a model vendor.
Create checkpoints after meaningful work: inputs received, plan approved, evidence gathered, draft created, validation completed, user review requested, final outcome accepted.
If a tool fails, report the failure and its effect on the work. Do not silently substitute a different source, permission, or action.
```

## Observability
Emit one event per run to the spine (`skills/_spine/event.schema.json`): `skill: "execution-orchestrator"`, the inputs actually used, the outputs produced, claims/assumptions/risks, approvals required, timestamp.

## Handoff
Next: skill 07-quality-safety-review.
