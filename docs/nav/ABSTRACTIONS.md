# Learned routes — fde-kernel-skills

Distilled by `nav.py distill` from real sessions. Every `route:` and `gate:` line is re-validated by `nav.py check`, so this file fails loudly when the system moves under it.

## Prove the fde kernel tree passes its full gate

- date: 2026-09-22
- trigger: prove the fde kernel tree passes its full gate
- system: fde-kernel-skills
- id: prove-the-fde-kernel-tree-passes-its-full-gate
- route: Makefile -> fde/tests/test_kernel.py -> fde/tests/test_m008.py
- gate: make check
- proof: 3 path(s) + 1 gate target(s) validated 2026-09-22 by nav.py distill; re-validated by nav.py check
- findings: none

## Lint a scenario family for leaks before trusting it

- date: 2026-09-22
- trigger: lint a scenario family for leaks before trusting it
- system: fde-kernel-skills
- id: lint-a-scenario-family-for-leaks-before-trusting-it
- route: fde/lint_scenario.py -> fde/simulator.py -> fde/simulator_m008.py
- gate: make lint
- proof: 3 path(s) + 1 gate target(s) validated 2026-09-22 by nav.py distill; re-validated by nav.py check
- findings: none

## Pre-register an experiment tamper-evidently

- date: 2026-09-22
- trigger: pre-register an experiment tamper-evidently
- system: fde-kernel-skills
- id: pre-register-an-experiment-tamper-evidently
- route: fde/prereg.py -> fde/registry.py -> runs/registrations/M008/v4/registration.json
- gate: make verify
- proof: 3 path(s) + 1 gate target(s) validated 2026-09-22 by nav.py distill; re-validated by nav.py check
- findings: none

## Run one closed-loop blind mission interactively

- date: 2026-09-22
- trigger: run one closed-loop blind mission interactively
- system: fde-kernel-skills
- id: run-one-closed-loop-blind-mission-interactively
- route: fde/driver.py -> skills/MASTER_PROMPT.md -> fde/blind_guard.py
- gate: make test
- proof: 3 path(s) + 1 gate target(s) validated 2026-09-22 by nav.py distill; re-validated by nav.py check
- findings: none

## Report the arm table for a finished world

- date: 2026-09-22
- trigger: report the arm table for a finished world
- system: fde-kernel-skills
- id: report-the-arm-table-for-a-finished-world
- route: fde/report.py -> fde/inspect_run.py
- gate: make test
- proof: 2 path(s) + 1 gate target(s) validated 2026-09-22 by nav.py distill; re-validated by nav.py check
- findings: none
