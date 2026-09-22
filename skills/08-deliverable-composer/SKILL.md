---
name: deliverable-composer
description: "Deliverable Composer: Make the main output excellent, usable and easy to consume."
order: 8
inputs: ["work_products", "review_result", "evidence_register"]
outputs: ["deliverable", "decision_record"]
emits_event: true
model_neutral: true
---
# 8. Deliverable Composer

**Job:** Make the main output excellent, usable and easy to consume.
**User-visible output:** "The main answer, document, plan, code, or decision"

## What it covers
Layout: title; direct answer or completed output; recommended next step; key assumptions or limits; controls [See decision record] [Revise this] [Export]. The link is called 'See decision record', never 'chain of thought'.

## Model instruction
```text
Lead with the actual deliverable.
Do not expose private chain-of-thought or raw hidden reasoning. Provide a concise decision record instead: objective, evidence considered, assumptions, alternatives considered, key trade-offs, actions taken, checks performed, uncertainty, approval status.
Make the main output readable without opening the decision record.
```

## Observability
Emit one event per run to the spine (`skills/_spine/event.schema.json`): `skill: "deliverable-composer"`, the inputs actually used, the outputs produced, claims/assumptions/risks, approvals required, timestamp.

## Handoff
Next: skill 09-proactive-guide.
