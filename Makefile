SHELL := /bin/bash
VENV_BIN := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin; fi)
PYTHON ?= $(if $(VENV_BIN),$(VENV_BIN)/python,python)
PYTEST ?= $(PYTHON) -m pytest
STREAMLIT ?= $(if $(VENV_BIN),$(VENV_BIN)/streamlit,streamlit)
RUFF ?= $(if $(VENV_BIN),$(VENV_BIN)/ruff,ruff)
MYPY ?= $(if $(VENV_BIN),$(VENV_BIN)/mypy,mypy)
BLACK ?= $(if $(VENV_BIN),$(VENV_BIN)/black,black)

.PHONY: help test lint format publish dashboard rebuild-e1 rebuild-e2 rebuild-e3 clean

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

rebuild-e3: ## Rebuilds E3 artifacts; implemented in Sprint E3
	@echo "make rebuild-e3 is implemented in Sprint E3." && exit 1

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache
