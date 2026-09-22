---
name: bs-build
description: Use when the user says "help me build this", "fix this", "add a feature", "this is broken" and there is a project or repo to change. Reads the project, plans, drafts changes, tests locally, and asks before editing important files, installing, or committing. Closest of the four to fde-mission (evidence -> proposal -> gate). Not for pure explanation (bs-understand) or unclear problems (bs-figure-out).
---

# Build / fix (evidence, plan, gate, verify)

Product rule: read, plan, draft and test locally by default; ask before it changes anything that matters.

## Pre-flight
Restate the goal and success test in one line ("done when ..."). Name the project folder, what you will read, what you will draft, and what needs approval. If the success test is missing, ask for it; that is the one required question.

## Work
1. **Ground it.** Read the relevant code and reproduce the problem or state the current behavior. A bug's root cause is a claim: it is `established` only if a discriminating check separates it from the alternatives (a test that fails for this cause only). Otherwise say `inferred`.
2. **Plan.** 3-7 steps, smallest change that meets the success test. List files to touch.
3. **Gate (ask first).** Show the plan and get a yes before: editing important/shared files, installing packages, changing config or systems, committing, deleting. Reversible scratch edits and running tests locally are allowed.
4. **Draft + test.** Write the test first when feasible. Run it. Report real output; if it fails, say so.
5. **Verify.** Re-run the success test. Do not claim done without seeing it pass. Note anything not verified.

## Output
What changed (file:line), the test result, what remains unverified, and the exact command the user can run to check.

## Save
Approved decisions and lessons ("what went wrong and the check that now catches it") go to the vault project note / `40_Memory/`. Follow the repo's existing commit conventions; commit only if asked.

Engine: same shape as fde-mission (evidence -> proposal -> authority gate). The Kernel driver is simulator-only today, so gating here is by asking the user.
