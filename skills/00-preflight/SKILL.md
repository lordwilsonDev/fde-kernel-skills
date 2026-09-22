---
name: preflight
description: "Preflight: turn a user request into an initial Task Contract and a Stem Activation Plan. Runs before any other skill."
order: 0
inputs: ["raw_user_request", "user_identity", "workspace_policy", "available_stems", "prior_task_contract"]
outputs: ["task_contract", "stem_activation_plan", "first_blocking_unknown", "first_user_question"]
emits_event: true
model_neutral: true
---
# 0. Preflight

**Job:** Route the request. Select only the stems this task actually needs, at the risk level it actually carries, before any of them run.
**User-visible output:** the one first question (if any) plus the deliverable — never a list of internal stem names.

## The key rule
> Preflight selects systems; the Task Contract authorizes actions; stems execute only when their preconditions are met.

This prevents both failure modes: running every stem for every request (slow, noisy, and a false sense of rigor for a one-line rewrite), and letting the model freely choose tools/memory/workflow on its own (ungoverned). Preflight is the only thing that picks stems; nothing downstream re-decides that for itself.

## What it covers
What kind of task is this. What deliverable is likely wanted. Which terms may need semantic resolution. What actions are allowed by default (from `workspace_policy`). What risk tier applies. Which stems are required now, which may be needed later, and which do not apply. What the one first question is, if any. What must not happen yet.

## The checklist (short, deterministic, run before meaningful work begins)
```text
1. What is the user trying to accomplish?
2. What deliverable would make this useful?
3. What decision, action, or audience does it support?
4. What risk tier applies?
5. Which material terms are undefined or ambiguous?
6. What evidence or source authority is likely required?
7. What actions are allowed by current policy?
8. Is this draft-only, investigative, or action-capable work?
9. Which stems are required now?
10. Which stems are conditional on later state?
11. What is the smallest safe first action?
12. What must be asked, approved, deferred, or blocked before proceeding?
```

## Stem status (every stem gets exactly one)
| Status | Meaning |
|---|---|
| `ACTIVE` | Needed immediately for the current task state |
| `CONDITIONAL` | May activate later when a named precondition becomes true |
| `NOT_NEEDED` | Not relevant to this task |
| `BLOCKED` | Needed, but cannot run until authority, data, or user input exists |

Selection is not execution. Five distinct states, in order: **Selected** (probably needed) → **Active** (may run now) → **Authorized** (has permission for its exact action, from `03-scope-governance`) → **Complete** (produced validated output) → **Merged** (now part of the shared Task Contract).

## The stem-selection matrix (canonical names; mapping to `skills/01-10` is in `_spine/router.py`)
| Stem | Activate in preflight when | Example |
|---|---|---|
| `question_framing` | Any nontrivial request | "Help me decide…" |
| `semantic_resolution` | A material term, metric, policy, entity or definition is ambiguous | "expansion revenue", "active user" |
| `ambiguity_risk` | Scope, authority, impact or reversibility is unclear | "Fix production" |
| `context_assembly` | Approved task scope exists and relevant context is needed | Search docs and contracts |
| `capability_retrieval` | A tool, integration, query, file action or code execution may be needed | Query a warehouse |
| `workspace_investigation` | Work needs documents, files, code, SQL, diagnostics or research | Analyze an incident |
| `memory_consolidation` | The task has completed and contains validated reusable knowledge | Store a lesson candidate |
| `concurrency_state` | More than one worker, a long-running task, mutable shared state, or a review workflow exists | Agent plus human analyst |
| `validation` | A material conclusion, recommendation, calculation or action is being created | A revenue report |
| `skill_lifecycle` | A repeatable workflow has demonstrated value across tasks | A monthly analysis pattern |

## Model instruction
```text
Before meaningful work begins, and again at each of these checkpoints, run the preflight checklist and update the Stem Activation Plan:
- at task start (full classification)
- before using a new tool category
- before adding a new data source
- before proposing an external action
- after a material user correction
- after a major failure or contradiction
- before skill promotion
- before task closure
Later passes are lightweight: "what changed, which stem is now needed, and is the next action still authorized?" — not a full re-classification.

Do not run every stem for every request. Do not let capability, memory or workflow choice happen ungoverned outside this selection. Validate the model's own classification against: task type, risk tier, workspace policy, available permissions, evidence requirements, and current Task Contract state — selection is not a free choice, it is checked against these.

A stem marked CONDITIONAL only activates when ITS OWN named precondition is true, not on a hunch. A stem needed but not yet authorized is BLOCKED, not skipped and not silently run anyway.
```

## Full flow
```text
User request -> Preflight checklist -> Initial Task Contract -> Stem Activation Plan
  -> run only ACTIVE stems -> update Task Contract -> re-run lightweight preflight
  -> activate the next CONDITIONAL stem once its precondition passes -> one action
  -> validation -> merge output -> repeat until delivered
```

## Observability
Emit one event per preflight pass to the spine: `stem: "preflight"`, the full Stem Activation Plan (every stem's status and, for `CONDITIONAL`, its precondition), the risk tier, the first blocking unknown if any, and whether this was an initial or a re-run pass.

## Handoff
Only ACTIVE stems run next, in the order the Stem Activation Plan implies (question_framing/`01-intent-capture` first when active). Everything else stays CONDITIONAL, NOT_NEEDED or BLOCKED until a later preflight pass says otherwise.
