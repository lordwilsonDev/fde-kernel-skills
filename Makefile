.PHONY: help test lint verify tree check
PY ?= python3
help:
	@echo "make test | lint | verify | tree | check"
test:
	$(PY) -W ignore -m unittest discover -s fde/tests
lint:
	@for w in M007 M008; do $(PY) fde/lint_scenario.py $$w || exit 1; done
verify:
	@$(PY) fde/prereg.py verify M007 || exit 1
	@$(PY) fde/registry.py status M008
tree:
	@$(PY) fde/manifest.py tree | tail -1
check: test lint verify tree
