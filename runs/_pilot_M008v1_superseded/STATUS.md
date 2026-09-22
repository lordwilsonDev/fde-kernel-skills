# M008 v1 pilot: superseded before confirmatory data collection
Truthful record (orchestrator, 2026-09-21). NOT "zero runs".
- 2 model-arm runs COMPLETED under the v1 registration and were scored and read by the orchestrator: M008_haiku_kernel_a (Kernel arm, 6 rounds) and M008_haiku_rules_a (rules-only arm, 8 rounds). Mechanism: subagents, PROMPT-BLIND only (addendum #3), NOT hook-enforced; tool-use audits were not performed.
- 2 launch attempts failed on "Credit balance is too low" before any model turn (archived in _interrupted_M008_credit_balance/).
- Outcomes seen by the orchestrator: kernel_a took the correct path (decoy first, then true diagnostic, gate-approved fix + replay, no K1/K2 event); rules_a executed the decoy mitigation (gate approved), later applied the correct correction prematurely (ineffective), and its final root cause was correct.
- Disposition: these runs used a driver, guard and registration now known to be defective (see preflight bug hunt). They are NOT M008 confirmatory data and must not enter any arm table. They are retained, unmodified, as a pilot. Any v2 prediction/threshold is written AFTER these two outcomes were seen and must say so.
