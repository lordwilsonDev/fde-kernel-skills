# PREDICTIONS - M009 v1 (DRAFT — not registered)

Written 2026-09-22 with every disclosure in the PREREG body already known (M008 v4 results, both Jev probe outcomes). Point predictions, ranges, and confidence. Scored off the state DB.

## Primary: K1'' (false cause established from the decoy, no-self-disclosure artifacts)

| Arm | Prediction | Range | Confidence |
|---|---|---|---|
| Haiku A (static control) | **5/8** | 3–6/8 | medium — artifacts got harder (no self-disclosed tell), but the static flag's mechanism is unchanged; M008 was 6/8 |
| Haiku B (Kernel rivals) | **≤ 1/8** | 0–2/8 | medium-high — rival record blocks the decoy path structurally; misses possible if rivals are under-recorded by the model |
| Haiku C (Jev LR) | **≤ 1/8** | 0–2/8 | medium — validated 4/4 on exactly these stripped cases; risk is threshold tuning and API fail-closed behavior, not the pattern |
| Sonnet A | **2/3 wrong** | 1–3/3 | low (n=3) — M008's claim-ranking gap should persist or worsen without the self-disclosed tell |
| Sonnet B | **≤ 1/3 wrong** | 0–1/3 | low (n=3) |

Bar: B and C each land **< 25%** (satisfied by <= 1/8). Control validity (>= 70% decoy exposure) expected in all arms — the prerequisite release rule is unchanged (high confidence, M008 achieved it).

## Secondary: K2'' (gate approves the wrong fix)

- Haiku A: **3/8** (range 1–5/8), mirroring M008, medium confidence.
- Haiku B and C: **≤ 1/8** each — K2'' should track K1'' since the gate never opens without a satisfying citation (high confidence: mechanism-level dependency).

## Mechanism-specific side predictions (make the arms distinguishable, not just pass/fail)

- **C distinctive failure mode:** more "insufficient discrimination" stalls than A or B — predict **≥ 2/8 Haiku C runs end correct-but-ineffective** (gate rightly stayed shut, fix never executed), vs ≤ 1/8 in A. If C instead shows K1'' < 25% with no effectiveness loss, it beat this prediction.
- **B distinctive failure mode:** if the model records rivals as a ritual checkbox, B drifts toward A — predict B's rival records, when empty or self-identical, co-occur with **all** of B's K1'' events (post-hoc diagnostic, pre-specified here so it cannot be invented after seeing data).
- **Sonnet claim-ranking:** Sonnet A's wrong finals keep citing decoy+true evidence together (M008's new-finding pattern) in **≥ 2/3** of its wrong runs — a qualitative coding, done blind to arm label.

## What would surprise us

- Control A under 25% (the test got *too* hard — no decoy attraction left; K1 becomes untestable again, M007-style).
- C above 25% while B is under it (decomposed LR generalizes worse than in-sample 4/4 — threshold or hypothesis-writing dependence).
- B above 25% while C is under it (structural rival record helps less than an external calibrated check — the Kernel's own semantics, not evidence sufficiency, is the binding constraint).
