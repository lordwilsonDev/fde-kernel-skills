# AGENTS.md — FDE Kernel skills

Agent-facing front door for this repository (same idea as palantir/blueprint's AGENTS.md).
Humans get the full story in README.md.

## Build/Test commands

- `make check` — THE meta-gate: unit tests + scenario lints (L1-L8) + prereg verify (M007) +
  registry status (M008) + tree hash + `fmt-check` + `typecheck`. Read-only: it never writes.
- `make precommit` — alias of `make check`; the pre-commit hook runs exactly this.
- `make fmt-check` (= `python3 fde/hygiene.py fmt-check`) — `black --check` over `fde/**/*.py`
  minus `frozen_format_exemptions.txt`. To fix a free file: `python3 fde/hygiene.py fmt-fix`
  (NEVER bare `black fde` — it would rewrite byte-pinned files and break their pins).
- `make typecheck` — `mypy fde`; type debt inside frozen modules is scoped in `mypy.ini`,
  and every `[mypy-...]` override is asserted to cover ONLY frozen files.
- `make hook` — install the local forwarder `.git/hooks/pre-commit -> hooks/pre-commit`
  (a local file; git config is never altered). Run once per clone.
- Tests only: `python3 -W ignore -m unittest discover -s fde/tests`
- Installed workspace (ships code, not experiment material): run the suite line above plus
  `python3 fde/lint_scenario.py M007`; `make check`'s `verify` stage needs `runs/`.

## Architecture

- `fde/kernel.py` claim-integrity Kernel · `fde/driver.py` the experiment loop ·
  `fde/simulator*.py` worlds · `fde/lint_scenario.py` scenario linter (L1-L8) ·
  `fde/prereg.py` + `fde/registry.py` pre-registration and the hash-chained freeze ·
  `fde/blind_guard.py` PreToolUse allowlist hook (wired in `.claude/settings.json`) ·
  `fde/manifest.py` tree provenance · `fde/vault_sync.py` vault notes · `fde/hygiene.py` format gate.
- Skills live in `.claude/skills/` (fde-kernel, fde-mission, fde-eval, bs-*).
  Route cards for agents: `docs/nav/ABSTRACTIONS.md` (re-validated by `nav check`).

## Rules for agents — Frozen files & check-only gates

- Never edit a byte-pinned file. `python3 fde/hygiene.py frozen` lists them: the latest
  non-superseded `runs/registrations/*/v*/registration.json` plus `fde/tests/m007_baseline.json`.
  `make check` fails loudly (registry status / baseline test) if one changes.
- Gates are CHECK-ONLY: never add a writing step to `check`, `precommit`, or `hooks/pre-commit`.
  The hook is whitelisted line-by-line by `test_repo_hygiene`.
- Exceptions must equal the freeze: `frozen_format_exemptions.txt` (format) and the
  `[mypy-...]` scopes (types) are asserted == / subset-of the frozen set by tests —
  add an entry only when a registration freezes that file; shrink it when M009 re-freezes.
- Amend registrations via addenda only (clarify or report a deviation — never change the freeze).
- Blindness: while `.fde_blind` exists the guard allowlists (current round's ctx/proposal,
  four literal driver commands); the orchestrating session is never blinded.
- Deprecate in place: superseded material keeps its record (registry versions,
  `runs/_*_superseded/` dirs, README addenda). Don't delete history.

## Runtime

- Python per `.python-version` (**3.12**); gate tools pinned in `requirements-dev.txt`
  (black, mypy) and asserted against the installed tools by `test_repo_hygiene`.
