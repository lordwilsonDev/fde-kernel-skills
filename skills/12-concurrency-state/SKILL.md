---
name: concurrency-state
description: "Concurrency & State Control: govern shared mutable state, multiple workers, long-running tasks and review workflows so parallel work doesn't corrupt or duplicate."
order: 12
inputs: ["plan", "execution_orchestrator_assignments"]
outputs: ["lock_or_lease_state", "worker_registry", "conflict_report"]
emits_event: true
model_neutral: true
---
# 12. Concurrency & State Control

**Job:** Prevent two workers (agent+agent, agent+human) from clobbering the same task state, and give a long-running task a durable place to resume from.
**User-visible output:** none directly — a silent guarantee, surfaced only as "another editor is working on this" or "resuming where this left off."

## What it covers
Activates only when preflight detects: more than one worker assigned to the same Task Contract; a task expected to span multiple sessions/turns; mutable shared state (a document, a record, a queue) more than one actor can write; or a human-review step that can race the agent's next action. For a single agent, single turn, single draft, this stem stays NOT_NEEDED — most tasks never need it, and running it by default just adds ceremony (the FDE Kernel's own M008 experiment learned this the hard way: an unlocked, non-atomic state store is where a concurrent-write bug actually showed up).

## Model instruction
```text
Before more than one worker touches the same Task Contract, or before an action would mutate shared state, acquire an explicit lease/lock on the piece of state being changed and re-read the current state under that lease - never act on state read before the lease was held.
State changes commit atomically: a failed action changes nothing, not a half-write. On any failure after the lease is taken, restore from a pre-action snapshot and report a structured failure - never leave partial state as if it were the previous or the new state.
Record which worker holds what, so a second worker (agent or human) sees "in progress by X" rather than silently overwriting it.
For a long-running task, checkpoint state at each merged stem output so the task can resume from the last good state, not from the start, after an interruption.
```

## Observability
Emit one event per lease acquired/released: `stem: "concurrency-state"`, `resource`, `worker_id`, `action` (acquired|released|conflict_detected), and on a conflict, what the other holder was doing.

## Handoff
Gates `06-execution-orchestrator` whenever it's about to write shared state with another worker active. Feeds `10-feedback-learning-loop`'s memory writes, which must also be lease-protected if more than one session can write preferences concurrently.
