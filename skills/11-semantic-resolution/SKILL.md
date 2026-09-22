---
name: semantic-resolution
description: "Semantic Resolution: pin down what a material term, metric, policy, entity or definition actually means before it drives a decision."
order: 11
inputs: ["objective", "context_map"]
outputs: ["resolved_terms", "unresolved_terms", "definition_choice_question"]
emits_event: true
model_neutral: true
---
# 11. Semantic Resolution

**Job:** Find the terms in the request whose definition would change the answer, and resolve them before doing the work — not after.
**User-visible output:** one clear definition question, with options, when a term is genuinely ambiguous; otherwise nothing (silent, correct default).

## What it covers
Activates only when a request contains a material term, metric, policy or entity with more than one live definition in this workspace — not every undefined term matters. This stem finds only the ones where two reasonable definitions would produce two different deliverables — "expansion revenue" (finance-recognized vs. sales-booked vs. net-of-churn) changes a ranking; "warmer tone" in an email rewrite does not need a formal definition. A term worth resolving gets a **material-term check**: would resolving it differently change the recommendation, the risk, the audience, or the numbers? If not, use a reasonable default and disclose it (same rule as skill 09's proactive-guide question budget) rather than asking.

## Model instruction
```text
Scan the request and the assembled context for terms, metrics, policies or entities with more than one live definition in this workspace.
For each candidate, ask: would resolving it one way vs. another change the deliverable, the risk tier, or a recommendation? If no, do not surface it — use the most standard/workspace-default meaning and say so in the decision record.
If yes, it is a blocking unknown: state it as one question with the concrete definitions as options (never "what do you mean by X" open-ended when the finite set of real options is knowable).
Resolve at most the number of terms that actually gate the deliverable in this pass; do not turn the request into a glossary review.
Once resolved, the definition becomes part of the Task Contract for the rest of this task - do not re-ask it.
```

## Observability
Emit one event: `stem: "semantic-resolution"`, `resolved_terms` (term -> chosen definition -> why), `unresolved_terms` still blocking, and the question asked if any.

## Handoff
Blocks `workspace_investigation`/`capability_retrieval` (06 execution-orchestrator) whenever an unresolved material term would change what gets queried. Feeds `04-evidence-builder`'s vocabulary and `07-quality-safety-review`'s check for "was the resolved definition actually used throughout."
