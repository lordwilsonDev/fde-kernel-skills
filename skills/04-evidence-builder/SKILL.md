---
name: evidence-builder
description: "Evidence Builder: Stop confident answers built on weak, stale, fabricated, or irrelevant evidence."
order: 4
inputs: ["objective", "context_map", "authority_decision"]
outputs: ["evidence_register", "assumptions_register"]
emits_event: true
model_neutral: true
---
# 4. Evidence Builder

**Job:** Stop confident answers built on weak, stale, fabricated, or irrelevant evidence.
**User-visible output:** "What supports this answer"

## What it covers
Every material statement gets a status: Confirmed (directly supported by an approved source), Inferred, Hypothesis, User preference, Assumption, Unknown, Contradicted.

## Model instruction
```text
For each material claim in a deliverable, identify: claim, evidence source, confidence, limitations, freshness, and whether the evidence is direct or inferred.
Do not treat a source label, authority label, popularity signal, or metadata tag as proof.
When evidence is missing, say what would resolve the uncertainty.
For consequential decisions distinguish "we know", "we infer", "we assume", and "we still need to verify".
```

## Observability
Emit one event per run to the spine (`skills/_spine/event.schema.json`): `skill: "evidence-builder"`, the inputs actually used, the outputs produced, claims/assumptions/risks, approvals required, timestamp.

## Handoff
Next: skill 05-plan-generator.
