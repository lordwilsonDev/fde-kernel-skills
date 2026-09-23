.PHONY: help test lint verify tree fmt-check typecheck check precommit hook
PY ?= python3
help:
	@echo "make test | lint | verify | tree | fmt-check | typecheck | check | precommit | hook"
test:
	$(PY) -W ignore -m unittest discover -s fde/tests
lint:
	@for w in M007 M008; do $(PY) fde/lint_scenario.py $$w || exit 1; done
verify:
	@$(PY) fde/prereg.py verify M007 || exit 1
	@$(PY) fde/registry.py status M008
tree:
	@$(PY) fde/manifest.py tree | tail -1
fmt-check:
	@$(PY) fde/hygiene.py fmt-check
typecheck:
	@$(PY) -m mypy fde
precommit: check
hook:
	@mkdir -p .git/hooks
	@printf '%s\n' '#!/bin/sh' 'exec "$$(git rev-parse --show-toplevel)/hooks/pre-commit"' > .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "installed .git/hooks/pre-commit -> hooks/pre-commit (local file; git config untouched)"
check: test lint verify tree fmt-check typecheck
