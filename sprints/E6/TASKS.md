# Sprint E6 TASKS

Sprint E6, Hedging. Eight tasks including Task 0, each with a test. A stored
criterion is never reworded and no number in a walkthrough or deliverable is
typed by hand. The champion decision from E5 is consumed, never re-opened.

- [ ] Task 0: ETF prices and the instrument set (P0)
  - Acceptance: `data/raw/etf_prices.parquet` holds adjusted closes for SPY,
    IWM, QQQ and the sector SPDRs, fetched once from yfinance, with the E1
    mapping and missing-data rules; a probe prints coverage per instrument.
  - Files: `efb/hedge.py`, `data/raw/etf_prices.parquet`, `tests/test_hedge.py`

- [ ] Task 1: the hedge engine (P0)
  - Acceptance: `efb/hedge.py` with `beta_hedge`, `partial_hedge`,
    `fmp_hedge`, `min_variance_hedge` and `hedge_cost`, each with labeled
    inputs and outputs and the missing-data semantics from E5. Tests: the beta
    hedge of a portfolio that is 1x SPY returns h = -1; the FMP hedge drives
    every in-model exposure below 1e-6; the min-variance hedge is the OLS
    solution against a known covariance; cost is turnover times the stated
    constants plus borrow on shorts.
  - Files: `efb/hedge.py`, `tests/test_hedge.py`

- [ ] Task 2: hedges on the seed books, both models (P0)
  - Acceptance: `data/hedge/{portfolio}_{method}.parquet` for seed_ew and
    seed_mom_ls under beta, partial, FMP and min-variance methods, each
    computed under the champion Sigma and under the alternative Sigma, with
    the residual variance and the factor variance removed stored.
  - Files: `efb/hedge.py`, `data/hedge/*`, `tests/test_hedge.py`

- [ ] Task 3: realized efficacy and rebalancing decay (P0)
  - Acceptance: realized factor P&L and realized beta to Mkt-RF of the hedged
    and unhedged seed books over 2018 to 2026, and the efficacy curve over
    rebalancing frequencies 5, 21 and 63 sessions, all stored.
  - Files: `efb/hedge.py`, `data/hedge/e6_efficacy.parquet`,
    `data/hedge/e6_decay.parquet`, `tests/test_hedge.py`

- [ ] Task 4: evaluate F6.1 to F6.5 into RESULTS.json (P0)
  - Acceptance: every criterion evaluated with a stored number and written to
    `sprints/E6/RESULTS.json`, earlier sprints re-evaluated with no verdict
    changed.
  - Files: `efb/evaluate.py`, `sprints/E6/RESULTS.json`, `tests/test_e6_results.py`

- [ ] Task 5: the research deliverable (P0)
  - Acceptance: `docs/research/E6_hedge_study.md` with the before and after
    decompositions for both seed books under FMP and ETF hedges, the efficacy
    versus rebalancing frequency curve, the recommended hedge policy, the
    champion-against-alternative difference on every headline number, and a
    section titled "What would falsify this?". Ships with
    `tests/test_e6_memo.py` asserting every headline number rounds to a stored
    value.
  - Files: `docs/research/E6_hedge_study.md`, `tests/test_e6_memo.py`

- [ ] Task 6: dashboard D5 Hedging Lab (P1)
  - Acceptance: `dashboard/tabs/d05_hedging.py` with portfolio and instrument
    selectors, before and after decomposition, hedge weights, exposure bars,
    residual tracking error, the cost estimate and a rebalancing slider. Every
    panel builder raises on an empty read.
  - Files: `dashboard/tabs/d05_hedging.py`, `dashboard/app.py`,
    `tests/test_dashboard_d5.py`

- [ ] Task 7: the walkthrough, the render and the engineering close (P0)
  - Acceptance: `notebooks/E6_walkthrough.ipynb` with the hash cell comparing
    stored against recomputed and typing neither, the by-hand hedge algebra,
    one section per criterion, the D5 panel-to-column map with the non-empty
    guard, the deliverable's evidence in citation order, what E7 inherits and
    the credit port note. Executed in one pass, rendered to HTML, published
    and linked. `make rebuild-e6` added and `make rebuild` extended;
    `VERSION.json` over E1 through E6; ledger and open items updated.
  - Files: `notebooks/E6_walkthrough.ipynb`, `Makefile`, `data/VERSION.json`,
    `docs/hygiene_ledger.md`, `docs/open_items.md`,
    `tests/test_e6_walkthrough_notebook.py`

## Order and stops

Tasks run in numeric order. The champion is provisional: every headline result
is reported under XS-v1 and under XS-v2 with the difference stored (F6.4).
Stop conditions: an earlier stored criterion changes verdict; a build, render
or publish step fails in a way two attempts cannot fix.
