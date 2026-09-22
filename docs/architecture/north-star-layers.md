# FDE harness on the North Star loop

Source: vault `10_Projects/BlackSwanLabz/BlackSwanLabz-North-Star-Architecture.md` (find operational truth, prove it with measurement, intervene where it matters, compound). This maps the repo onto its layers. **No file was moved to make this map**: M008 is registered and its freeze hashes code by path, so `fde/` layout is fixed while M008 is open. New structure is additive.

| Layer | Question it answers here | Where it lives |
|---|---|---|
| 1 Intelligence | Is the scenario a valid test? What is actually true in it? | `fde/simulator*.py` (worlds, hidden truth), `fde/lint_scenario.py` (L1-L8), `docs/superpowers/specs/` (designs), `docs/` |
| 2 Decision | Do we run it, and what counts as a result, before we look? | `fde/registry.py` (M008+, hash-chained, versioned; `runs/registrations/`), `fde/prereg.py` (closed families M003-M007), `runs/PREREG_*.md`, `experiments/TEMPLATE/decision.md`; runtime authority: gate in `fde/kernel.py` |
| 3 Intervention + Verification | Run the arm, then measure it the same way every time | `fde/driver*.py`, `fde/scorer_m008.py`/`fde/evaluator_m008.py` (private, orchestrator-side), `fde/run_blind*.sh`, `fde/blind_guard.py`, `runs/<run>/`, `fde/report.py`, `fde/inspect_run.py`, `fde/tests/` |
| 4 Compounding | What did we learn that the next experiment starts from? | `fde/vault_sync.py`, `fde/lessons_seed.db`, `.claude/skills/`, vault `50_Experiments/FDE-Kernel/`, `40_Memory/FDE-Lessons/` |

## Per-experiment loop (baseline -> change -> observation -> comparison -> result)
1. **Baseline**: freeze manifest + prior-family integrity baseline (`python3 fde/manifest.py m007`, `tests/m007_baseline.json`); the previous family's result stays untouched.
2. **Change**: the one thing that differs (a new world, a new decoy rule). Kernel changes need a new family.
3. **Observation**: runs in `runs/<WORLD>_<model>_<arm>_<letter>/`, one at a time, scored deterministically.
4. **Comparison**: `python3 fde/report.py <WORLD>`, arm table, every cell and miss.
5. **Result**: a written report in the vault, with what was NOT verified. Copy `experiments/TEMPLATE/`.

## Commands (`make help`)
`make test | lint | verify | tree | check` (check = tests + lints + both registrations + tree hash).

## Frozen-path rule
While a `PREREG_<W>.md` is open, do not move or edit any file listed under its "Frozen code". `python3 fde/prereg.py verify <W>` is the check. Non-frozen additions (docs, Makefile, experiments/) are allowed and are recorded by addendum.

## Known real-world gaps (as of 2026-09-21)
- **M008 is blocked**: v1 registration superseded; 2 pilot runs archived (`runs/_pilot_M008v1_superseded/`); v2 needs live blind qualification + registration (`fde/registry.py`). See the vault preflight report.
- Not a git repository (provenance = `fde/manifest.py` tree hash).
- Headless `claude -p` needs API credit; M008 currently runs as subagents, prompt-blind (addendum #3). The hook guard is tested but not yet verified live.
- Kernel trusts the `discriminating` flag (documented blind spot; M008 measures it).
