SHELL := /bin/bash
VENV_BIN := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin; fi)
PYTHON ?= $(if $(VENV_BIN),$(VENV_BIN)/python,python)
PYTEST ?= $(PYTHON) -m pytest
STREAMLIT ?= $(if $(VENV_BIN),$(VENV_BIN)/streamlit,streamlit)
RUFF ?= $(if $(VENV_BIN),$(VENV_BIN)/ruff,ruff)
MYPY ?= $(if $(VENV_BIN),$(VENV_BIN)/mypy,mypy)
BLACK ?= $(if $(VENV_BIN),$(VENV_BIN)/black,black)

# The panel pin. Every rebuild takes an explicit end date; left unset it is the
# stored panel's own last session, so re-running a rebuild cannot extend the panel
# by re-reading sources. Set END to say you mean to move it:
#   make rebuild-e1 END=2026-11-11
END ?=
PIN = $(if $(END),--end $(END))

.PHONY: help test test-fast test-all test-live-tree test-merge-guard lint format publish dashboard rebuild-e1 rebuild-e2 rebuild-e3 rebuild-e4 rebuild-e5 rebuild-e6 rebuild-e7 rebuild-e8 rebuild-e9 rebuild-e10 rebuild evidence verify-evidence web-install web-test web-build clean

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "%-15s %s\n", $$1, $$2}'

test: ## Run the fast subset: no network, no full evening job, no notebook
	$(PYTEST) tests/ -q -m "not slow and not requires_live_tree and not merge_guard"

test-fast: ## The same as test; kept because the standards name it
	$(PYTEST) tests/ -q -m "not slow and not requires_live_tree and not merge_guard"

test-all: ## Run everything, slow included; the phase-end evidence, in the background
	$(PYTEST) tests/ -q -m "not requires_live_tree and not merge_guard"

# The live-tree tests are deselected, never skipped, so the summary reports them as
# "N deselected". Run them deliberately, against a materialised run root, with:
#   EFB_RUN_ROOT=<run root> $(PYTEST) tests/ -q -m requires_live_tree
# This is required by the 2026-11-11 pre-merge check on the regenerated seed:
# see docs/backport_runbook.md.
test-live-tree: ## Run only the tests that need a live-shaped run root (EFB_RUN_ROOT)
	@test -n "$$EFB_RUN_ROOT" || { echo "EFB_RUN_ROOT must point at a materialised run root"; exit 2; }
	$(PYTEST) tests/ -q -m requires_live_tree

# One test, one merge step: live/extend.py must read returns_clean in the same commit
# that lands this branch. It fails on the branch as pushed, by design.
test-merge-guard: ## Run the merge guard that the merge commit must turn green
	$(PYTEST) tests/ -q -m merge_guard

lint: ## Static checks: ruff, mypy, black
	$(RUFF) check efb dashboard live tests
	$(MYPY) efb
	$(MYPY) live scripts
	$(BLACK) --check efb dashboard live tests

format: ## Auto-format with black and ruff
	$(BLACK) efb dashboard live tests
	$(RUFF) check --fix efb dashboard live tests

web-install: ## Install the Cloudflare page's toolchain from the lockfile
	cd web && npm ci

web-test: ## The page's and the Worker's tests, including the leak check
	cd web && npm run test

web-build: ## Type-check and build the page, then check the bundle for leaks
	cd web && npm run build && npm run test

dashboard: publish ## Run the EFB Console (Streamlit)
	$(STREAMLIT) run dashboard/app.py --server.headless true

publish: ## Copy the linked sprint documents into the dashboard static folder
	$(PYTHON) -m dashboard.publish

rebuild-e1: ## Rebuilds the E1 data layer end to end (Sprint E1)
	$(PYTHON) -m efb.build $(PIN)

rebuild-e2: ## Rebuilds E1 and E2 artifacts end to end (Sprint E2)
	$(PYTHON) -m efb.build --e2 $(PIN)

rebuild-e3: ## Rebuilds the XS-v1 artifacts from the E1 and E2 artifacts (Sprint E3)
	$(PYTHON) -m efb.build --e3 $(PIN)

rebuild-e4: ## Rebuilds the E4 statistical and covariance artifacts (Sprint E4)
	$(PYTHON) -m efb.build --e4 $(PIN)

rebuild-e5: ## Rebuilds the E5 risk evaluation and the champion decision (Sprint E5)
	$(PYTHON) -m efb.build --e5 $(PIN)

rebuild-e6: ## Rebuilds the E6 hedging toolkit over the seed books (Sprint E6)
	$(PYTHON) -m efb.build --e6 $(PIN)

rebuild-e7: ## Rebuilds the E7 alpha lab and the hygiene ledger (Sprint E7)
	$(PYTHON) -m efb.build --e7 $(PIN)

rebuild-e8: ## Rebuilds the E8 construction run on synthetic alpha (Sprint E8)
	$(PYTHON) -m efb.build --e8 $(PIN)

rebuild-e9: ## Rebuilds the E9 cost model and capacity curve (Sprint E9)
	$(PYTHON) -m efb.build --e9 $(PIN)

rebuild-e10: ## Rebuilds the E10 risk allocation and loss management (Sprint E10)
	$(PYTHON) -m efb.build --e10 $(PIN)

rebuild: ## Rebuilds E1 through E10 end to end, the gate G1 one-command path
	$(PYTHON) -m efb.build --all $(PIN)

evidence: ## Refresh the tracked evidence snapshot (E5 R1)
	$(PYTHON) -c "from efb import evidence; m = evidence.snapshot(); print(f\"snapshotted {m['n_artifacts']} artifacts, {m['total_snapshot_bytes'] / 1e6:.2f} MB\")"

verify-evidence: ## Verify every evidence snapshot against its hash (E5 R1)
	$(PYTHON) -c "from efb import evidence; p = evidence.verify(); print('evidence OK' if not p else chr(10).join(p)); raise SystemExit(1 if p else 0)"

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache
