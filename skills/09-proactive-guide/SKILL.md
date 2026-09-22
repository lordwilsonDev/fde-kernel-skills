---
name: proactive-guide
description: "Proactive Guide: Ask useful questions before the user realizes they need to answer them, without becoming annoying."
order: 9
inputs: ["deliverable", "evidence_register", "assumptions_register"]
outputs: ["next_questions"]
emits_event: true
model_neutral: true
---
# 9. Proactive Guide

**Job:** Ask useful questions before the user realizes they need to answer them, without becoming annoying.
**User-visible output:** "What should we decide next?"

## What it covers
Ask only if the answer changes goal, scope, audience, risk, authority, evidence, cost, time, format or success criteria; otherwise use a reasonable default and disclose it. Each question: short title, one-sentence reason, 2-5 selectable options, an Other option, optional free text, a recommended default when appropriate. Chain: software -> which code environment; business operations -> which systems may I read vs change; research -> citations, memo or both; draft-only -> do not ask about auto-deploy; routine changes allowed -> which actions count as routine.

## Model instruction
```text
After producing the main deliverable, propose up to three next-best questions or actions.
Each must connect directly to the user's original goal, a meaningful uncertainty, a decision required for safe progress, or a high-value opportunity to improve the result.
Do not ask generic engagement questions. Do not ask for information already known. Do not make the user repeat themselves.
Prefer option-based questions with a free-text escape hatch.
```

## Observability
Emit one event per run to the spine (`skills/_spine/event.schema.json`): `skill: "proactive-guide"`, the inputs actually used, the outputs produced, claims/assumptions/risks, approvals required, timestamp.

## Handoff
Next: skill 10-feedback-learning-loop.
