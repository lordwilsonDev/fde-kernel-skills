---
name: skill-lifecycle
description: "Skill Lifecycle: promote a repeatable, validated workflow pattern into a reusable skill — deliberately, not automatically."
order: 13
inputs: ["memory_consolidation_output", "recurrence_evidence"]
outputs: ["skill_promotion_proposal", "skill_promoted", "skill_deprecated"]
emits_event: true
model_neutral: true
---
# 13. Skill Lifecycle

**Job:** Notice when the same workflow pattern has proven itself across multiple tasks, and turn it into a named, reusable skill — with the user's approval, not silently.
**User-visible output:** "This looks like a pattern you use often. Want me to save it as a reusable skill?" — never a skill that appears without that question having been asked and answered yes.

## What it covers
Activates only when: a workflow pattern (a specific stem sequence, a specific set of default answers, a specific decision rule) has recurred across multiple tasks; each recurrence had a positive, validated outcome (per `07-quality-safety-review`); and the pattern is stable enough to name (not "sometimes I do X, sometimes Y"). One success is a data point, not a pattern — this stem requires recurrence, not a single good run.

## Model instruction
```text
Detect candidates only from the memory consolidation record (10-feedback-learning-loop), never from a single task's outcome.
A candidate needs: the same objective shape recurring, the same stem sequence or decision rule producing it, and a positive validated outcome each time (not just "the user didn't complain").
Propose promotion explicitly: name, the stem sequence it wraps, the inputs/outputs it standardizes, and the recurrence evidence (which past tasks). Do not promote without asking, mirroring 03-scope-governance's rule that saving a durable artifact needs approval.
A promoted skill is versioned and can be deprecated the same explicit way if it stops matching how the user actually works - do not let a stale promoted skill silently keep routing tasks into an outdated pattern.
```

## Observability
Emit one event on proposal, promotion, and deprecation: `stem: "skill-lifecycle"`, `skill_name`, `recurrence_evidence` (task ids/dates), `approval_status`.

## Handoff
Reads from `10-feedback-learning-loop`'s approved-decision and lesson records. A promoted skill becomes an available stem that `00-preflight` can select in future Stem Activation Plans, alongside the original ten and the three added here.
