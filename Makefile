SHELL := /bin/bash
VENV_BIN := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin; fi)
PYTHON ?= $(if $(VENV_BIN),$(VENV_BIN)/python,python)
PYTEST ?= $(PYTHON) -m pytest
STREAMLIT ?= $(if $(VENV_BIN),$(VENV_BIN)/streamlit,streamlit)
RUFF ?= $(if $(VENV_BIN),$(VENV_BIN)/ruff,ruff)
MYPY ?= $(if $(VENV_BIN),$(VENV_BIN)/mypy,mypy)
BLACK ?= $(if $(VENV_BIN),$(VENV_BIN)/black,black)

.PHONY: help test lint format publish dashboard rebuild-e1 rebuild-e2 rebuild-e3 rebuild-e4 rebuild-e5 rebuild-e6 rebuild evidence verify-evidence clean

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "%-15s %s\n", $$1, $$2}'

test: ## Run the test suite (it never shrinks)
	$(PYTEST) tests/ -q

lint: ## Static checks: ruff, mypy, black
	$(RUFF) check efb dashboard live tests
	$(MYPY) efb
	$(BLACK) --check efb dashboard live tests

format: ## Auto-format with black and ruff
	$(BLACK) efb dashboard live tests
	$(RUFF) check --fix efb dashboard live tests

dashboard: publish ## Run the EFB Console (Streamlit)
	$(STREAMLIT) run dashboard/app.py --server.headless true

publish: ## Copy the linked sprint documents into the dashboard static folder
	$(PYTHON) -m dashboard.publish

rebuild-e1: ## Rebuilds the E1 data layer end to end (Sprint E1)
	$(PYTHON) -m efb.build

rebuild-e2: ## Rebuilds E1 and E2 artifacts end to end (Sprint E2)
	$(PYTHON) -m efb.build --e2

rebuild-e3: ## Rebuilds the XS-v1 artifacts from the E1 and E2 artifacts (Sprint E3)
	$(PYTHON) -m efb.build --e3

rebuild-e4: ## Rebuilds the E4 statistical and covariance artifacts (Sprint E4)
	$(PYTHON) -m efb.build --e4

rebuild-e5: ## Rebuilds the E5 risk evaluation and the champion decision (Sprint E5)
	$(PYTHON) -m efb.build --e5

rebuild-e6: ## Rebuilds the E6 hedging toolkit over the seed books (Sprint E6)
	$(PYTHON) -m efb.build --e6

rebuild: ## Rebuilds E1 through E6 end to end, the gate G1 one-command path
	$(PYTHON) -m efb.build --all

evidence: ## Refresh the tracked evidence snapshot (E5 R1)
	$(PYTHON) -c "from efb import evidence; m = evidence.snapshot(); print(f\"snapshotted {m['n_artifacts']} artifacts, {m['total_snapshot_bytes'] / 1e6:.2f} MB\")"

verify-evidence: ## Verify every evidence snapshot against its hash (E5 R1)
	$(PYTHON) -c "from efb import evidence; p = evidence.verify(); print('evidence OK' if not p else chr(10).join(p)); raise SystemExit(1 if p else 0)"

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache
