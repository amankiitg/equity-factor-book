SHELL := /bin/bash
PYTHON ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python; fi)
PYTEST ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python -m pytest; else echo pytest; fi)

.PHONY: help test lint format dashboard rebuild-e1 rebuild-e2 rebuild-e3 clean

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "%-15s %s\n", $$1, $$2}'

test: ## Run the test suite (it never shrinks)
	$(PYTEST) tests/ -q

lint: ## Static checks: ruff, mypy, black
	ruff check efb dashboard live tests
	mypy efb
	black --check efb dashboard live tests

format: ## Auto-format with black and ruff
	black efb dashboard live tests
	ruff check --fix efb dashboard live tests

dashboard: ## Run the EFB Console (Streamlit)
	streamlit run dashboard/app.py

rebuild-e1: ## Rebuilds the E1 data layer end to end (Sprint E1)
	$(PYTHON) -m efb.build

rebuild-e2: ## Rebuilds E1 and E2 artifacts end to end (Sprint E2)
	$(PYTHON) -m efb.build --e2

rebuild-e3: ## Rebuilds E3 artifacts; implemented in Sprint E3
	@echo "make rebuild-e3 is implemented in Sprint E3." && exit 1

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache
