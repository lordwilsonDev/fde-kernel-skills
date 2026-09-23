# FDE Kernel skills (Claude Code)

The FDE Kernel v0.3.2 harness packaged as Claude Code skills (fde-kernel, fde-mission, fde-eval, plus the bs-* skills) plus the scripts behind them. Run Claude Code from this folder and the skills load from `.claude/skills/`.

| Skill | Use it to |
|---|---|
| `fde-kernel` | understand / extend / debug the Kernel (invariants, layout, known blind spot) |
| `fde-mission` | run ONE closed-loop mission as the reasoning layer (`/fde-mission runs/<run>`) |
| `fde-eval` | design, lint, pre-register, run and report an experiment; red-team the Kernel |

## Portable install
```bash
./install.sh ~/anywhere/fde-workspace              # self-contained copy (fde/, .claude/, runs/); nothing outside it is touched
./install.sh ~/anywhere/fde-workspace --symlink    # one source of truth, updates propagate
./install.sh ~/anywhere/fde-workspace --global-skills   # ALSO copy the 3 skills to ~/.claude/skills (the blind-guard hook stays per-workspace)
```
Config by environment: `FDE_VAULT` (default `~/Documents/Vault`), `FDE_RUNS`, `FDE_HOME`. The installed workspace passes the whole test suite on its own.

## Persistence with the vault
`fde/vault_sync.py` keeps lessons, gap records and regression tests as vault notes (`40_Memory/FDE-Lessons/`), rebuilds the SQLite seed from them, and exports run notes / arm tables to `50_Experiments/FDE-Kernel/`. Create-only for human notes; generated notes carry `fde_generated: true`.

## Quick start
```bash
make check                                                     # full gate: 231 tests + lints + prereg verify M007 + registry status M008 + fmt + typecheck
python3 -W ignore -m unittest discover -s fde/tests          # tests only (231)
python3 fde/lint_scenario.py M006                              # scenario leak linter (M006's flaw is HIGH)
python3 fde/prereg.py new M005 --arms "haiku:kernel,rules,raw x3" --predictions predictions.md
fde/run_blind.sh M005 kernel M005_haiku_kernel_a haiku         # init -> guard on -> headless Claude Code -> guard off -> score
python3 fde/report.py M005                                     # arm table
```
Interactive: `python3 fde/driver.py init runs/M005_demo M005 kernel`, then `python3 fde/driver.py blind on`, start `claude` here and run `/fde-mission runs/M005_demo`; afterwards `python3 fde/driver.py blind off` and `python3 fde/driver.py score runs/M005_demo`.

## Enforced blindness
`fde/blind_guard.py` is a `PreToolUse` hook (`.claude/settings.json`). While `.fde_blind` exists it blocks reads of the harness source, ground truth, tests, pre-registrations, other runs and each run's `state.db`/`run.json`; Bash is limited to `driver.py apply|status`; writes are limited to `proposal_r<N>.json`. It is inactive otherwise. It is a guard, not a sandbox: it only covers the tools it matches and only in this project.

## M008 (decoy on the critical path)
`fde/simulator_m008.py` (world: warehouse fulfilment / inventory allocation) + `fde/driver_m008.py` (the frozen M007 driver plus a prerequisite invariant, decoy-exposure scoring and run-scoped blindness) + linter checks L7/L8. The true diagnostics cannot run until they receive the cohort scope produced by the flagged, confounded decoy diagnostic. M007 files are untouched (byte-pinned by `fde/tests/test_m008.py`); `python3 fde/lint_scenario.py M007 --path-checks` shows what L7/L8 would have said about it.
```bash
python3 fde/lint_scenario.py M008                     # L1-L8, exit 1 on HIGH
python3 fde/registry.py status M008                   # M008 v4: ACTIVE, intact (c60df85f7bac)
fde/run_blind_m008.sh kernel M008_haiku_kernel_a haiku   # headless, hook-enforced blindness; needs API credit
python3 fde/manifest.py tree                          # deterministic tree hash (no git needed)
```
**M008 status: DONE (2026-09-22).** 30/30 registered runs complete under registry v4 (Haiku Kernel / rules-only / raw x8 each, Sonnet Kernel / raw x3 each). **K1 and K2 confirmed**: 6/8 Haiku Kernel runs established the false cause from the decoy alone, and 3/8 got the gate to approve the wrong mitigation. Zero harmful or unauthorized actions in any arm. Results: `50_Experiments/FDE-Kernel/M008/M008-v4-results-2026-09-22.md` in the vault. History: v1 superseded before confirmatory data (`runs/_pilot_M008v1_superseded/`), v2→v3 hardening, v4 added then cancelled a Qwen3-8B arm (0 runs, disclosed by addendum). Tests that need a registration (`--scored` init) use a temp registry.

**Blindness caveat for M008:** all 30 runs were driven through Claude Code subagents, and the `PreToolUse` blind guard was verified live **not** to fire on subagent tool calls. So M008 is **prompt-blind only**, not hook-enforced. This is disclosed by addendum. Hook-enforced blindness needs `run_blind_m008.sh` (headless `claude -p`, API credit).

The blind guard is now an allowlist (current round's ctx/proposal only, proposals create-once, four literal driver commands, no search/web/MCP/sub-agents, fail-closed) and, when started with `driver_m008.py blind on <run>`, run-isolated. The orchestrating session is not blinded; only model-arm sessions are.

## Verified vs not verified
- Verified: 231 tests incl. mutation checks (Kernel, loop, scenarios, guard, linter, pre-registration, registry, report); `make check` exit 0 on 2026-09-22.
- Verified (negative): the `PreToolUse` blind guard does **not** fire on Claude Code subagent tool calls (live probe, `runs/_qualprobe/`).
- **Not verified:** the skills loading as `/skills` in a live Claude Code session, the hook firing in a top-level interactive session, and `fde/run_blind.sh` / `run_blind_m008.sh` end-to-end. The attempts stopped at "Credit balance is too low" (`claude -p` uses API credit, not the subscription).
- Navigation cards for agents: `docs/nav/ABSTRACTIONS.md` (5 route cards, re-validated by `nav.py check` from the `navigation-layer` skill).

## What it does not do (yet)
- The Kernel trusts the `discriminating` flag (documented blind spot; see `fde-kernel`).
- No scenario family in `fde/simulator.py` is red-team grade: `lint_scenario.py` reports HIGH findings on M003-M006. M007 (opaque names, decoy diagnostic first-class, precondition) is lint-clean and pre-registered; 6 runs were made and the family was closed as **decoy not reached** (0/6 visited it, so K1/K2 were untestable there; see `50_Experiments/FDE-Kernel/M007/M007-validity-report-decoy-not-reached.md`). M008 put the decoy on the critical path to fix that.
- Open Kernel gap (from M008 Sonnet runs): a superseded wrong `root_cause` claim can still outrank later correct work, because nothing forces an explicit disposition before a new claim on the same investigation.
- Embeddings are a hash stand-in; the human gate is a deterministic simulation; results so far are n=1-5 per arm, mostly Haiku.
- Outcomes were at ceiling in every arm; the measured Kernel value is discipline, gate integrity and audit, not better answers.
