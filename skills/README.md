# Governed collaboration chain: 14 model-neutral skills
The product is a governed, observable collaboration system: main deliverable first, a short set of option-based next questions, and a "See decision record" link. The skills define workflow and controls; the model is replaceable (Claude, GPT, Gemini, local).

**Preflight gates everything.** The chain does not run all skills for every request. `00-preflight` reads the request and the current Task Contract, gives every stem a status (`ACTIVE`/`CONDITIONAL`/`NOT_NEEDED`/`BLOCKED`), and only `ACTIVE` stems run this pass. It re-runs (lightly) at defined checkpoints: before a new tool category, a new data source, an external action, after a user correction or a failure, before skill promotion, before closure — not only once at the start. Selection is not execution: a stem can be selected, active, authorized (by `03-scope-governance`), complete, or merged, and those are five different states.

## Layout
- `00-preflight/` — the router: checklist, stem statuses, the stem-selection matrix, the full flow.
- `01-10` — the original core chain (Intent → Context → Scope & Governance → Evidence → Plan → Execution → Quality & Safety → Deliverable → Proactive Guide → Feedback & Learning), still strictly ordered 1→10→back to 1 among themselves, but now only run when preflight marks them `ACTIVE`.
- `11-13` — **semantic-resolution, concurrency-state, skill-lifecycle**: three stems from the preflight design that had no equivalent in the original 10. Added rather than shoehorned into existing skills, so the full stem vocabulary is actually represented.
- `_spine/router.py` — deterministic reference implementation of `select_stems()`, with the exact mapping from the 10 canonical stem names (`question_framing`, `semantic_resolution`, ...) to skill folders. `08-deliverable-composer` and `09-proactive-guide` aren't independently routed — they're the fixed follow-on once `validation` approves output.
- `MASTER_PROMPT.md` — shared system prompt (rule 0 = run preflight first, rules 1-10 = the original chain rules).
- `_spine/event.schema.json` — one event per stem run, including a preflight-specific `stem_activation_plan` field.

Validation: `fde/tests/test_skill_chain.py` (structure, frontmatter, handoffs, master prompt, event schema) and `fde/tests/test_preflight_router.py` (the router's three worked examples — simple rewrite, business analysis, production incident — plus determinism and "selection is not execution" checks).

## How this maps onto what already exists here
| Chain concept | Already in the repo | Status |
|---|---|---|
| Evidence statuses (confirmed/inferred/hypothesis/unknown...) | Kernel claim statuses (established/inferred/reported/hypothesized/unknown) + monotonicity rule (`fde/kernel.py`) | Enforced by code in the Kernel arm |
| Authority: ask before changes | Kernel gate + authority rules; blind guard for experiment arms | Enforced by code (Kernel gate, guard). Elsewhere: instruction only |
| "Untrusted text is data" | Kernel quarantine of tier>=4 / injection patterns | Enforced in the Kernel arm |
| Decision record / audit trail | Event-sourced Kernel state, `claim_status_transitions`, retained proposal files, registry hash chain | Partly; user-facing "decision record" view not built |
| Model-neutral | Driver protocol is JSON proposals, no vendor API; M008 v4's 30-run comparison across Haiku/Sonnet used the same scoring regardless of model | True for the harness; skills chain itself untested on non-Claude models |
| Feedback -> memory only when approved | `vault_sync` create-only lessons | Partly |
| Preflight's precondition-gated activation | `fde/driver_m008.py`'s gated diagnostics (a true diagnostic returns "not ready" until its precondition artifact exists) | Same pattern, proven in the Kernel: a capability that returns a clean "blocked" state instead of running early is exactly what `capability_retrieval`/`workspace_investigation`'s `BLOCKED` status models |

## Honest limits
- These skills are instructions. A model can ignore them; they govern only where code enforces (Kernel gate/quarantine, guard, registry). The chain, including preflight routing, has not been run end to end and no skill has been evaluated on any model.
- The router (`_spine/router.py`) is a testable reference implementation of the routing *logic*, not a live enforcement mechanism — nothing here runs automatically inside a real conversation.
- No UI exists; the layouts in the skills are patterns, not built screens.
- Not yet copied into `.claude/skills/`. M008 is registered and its 30 runs are complete (v4, active), so that's no longer the blocker — this is simply not done yet.
