---
name: bs-figure-out
description: Use when the user says "help me figure this out", "I don't know where to start", "something is not working", "my process is broken" or "I need to make a decision" and the problem is not yet well defined. Maps the problem, separates known from unknown, finds the cheapest discriminating checks, and ends with a next-step plan. Not for executing changes (bs-build) or reading a specific doc (bs-understand).
---

# Figure it out (map, discriminate, decide the next step)

Product rule: look and draft only. The output is a map and one recommended next step, not an action.

## Pre-flight
Restate the goal in the user's words, say you will map what is known/unknown and propose a next step, and ask at most two questions: what "solved" looks like, and what they have already tried. Do not ask for a mode.

## Work
1. **Map**: goal, constraints, stakeholders/systems, what has been tried.
2. **Claims table**: each fact as `established` / `reported` / `inferred` / `unknown`, with its source. Second-hand or proxy evidence (complaints, counts) never establishes a cause.
3. **Hypotheses**: 2-4 candidate explanations or options. For each, what evidence would separate it from the others.
4. **Discriminating checks**: rank by cost and by how much they separate the hypotheses. A check that every hypothesis predicts the same result for is not a check, drop it. Warn if the tempting "obvious" check would not discriminate.
5. **Decide**: recommend one next step (usually the cheapest discriminating check) and what result would change the plan. For decisions between options, state the trade-off and the reversible/irreversible split.

## Output
- Problem in one line; claims table; hypotheses; ranked checks; **one recommended next step**; open questions.
- Hand off: if the next step is a change, say "run bs-build"; if it is a reading task, "run bs-understand".

## Save
The map and the chosen next step go to the vault project note; reusable lessons to `40_Memory/`.

Engine: fde-kernel's unknowns/contradiction/discriminating-evidence model. Known blind spot inherited: the model may mislabel a check as discriminating; state your reason each time so the user can challenge it.
