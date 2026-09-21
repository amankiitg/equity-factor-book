# Sprint E7 TASKS

Sprint E7, Alpha Lab and Backtest Hygiene. Nine tasks including Task 0, each
with a test. A stored criterion is never reworded and no number in a
walkthrough or deliverable is typed by hand. The champion decision from E5 is
consumed, never re-opened; the FMP machinery from E6 is the only
neutralization mechanism.

- [ ] Task 0: probe the optional data sources (P0)
  - Acceptance: a probe prints rows for FINRA short interest and for
    yfinance earnings dates. A source whose probe prints nothing is recorded
    as unavailable in the multiple-testing ledger and its signal is skipped,
    not scored. Probes live in `efb/probes.py` next to the E6 probes.
  - Files: `efb/probes.py`, `tests/test_probes.py`

- [ ] Task 1: the signal library (P0)
  - Acceptance: `efb/alpha.py` with momentum 12-1, short-term reversal, idio
    momentum on XS-v1 residuals and low residual volatility, each a
    point-in-time function of data available at t-1 only, each returning a
    long frame date/ticker/signal. Every signal value NaN is kept, never
    filled. Tests: the shift audit from F7.1 catches a synthetic leaked
    signal; a known series has the right correlation sign.
  - Files: `efb/alpha.py`, `tests/test_alpha.py`

- [ ] Task 2: the harness (P0)
  - Acceptance: `efb/hygiene.py` computes the Spearman IC series, the decay
    at 1/5/21/63 days, the Newey-West t-statistic, the factor-neutralization
    s_perp = s - X (X'X)^-1 X' s, quintile portfolios on the E5 race grid
    hedged with the E6 FMP machinery, turnover, hit rate, the fundamental-law
    pair IR versus IC x sqrt(N_effective) with N_effective stored, and
    regime-conditional IC within VIX terciles. Artifacts under
    `data/alpha/{signal}/` for every admitted signal.
  - Files: `efb/hygiene.py`, `data/alpha/*`, `tests/test_hygiene.py`

- [ ] Task 3: the multiple-testing ledger (P0)
  - Acceptance: `docs/multiple_testing_ledger.md` is append-only, one row per
    signal run (every variant, including failed ones), with Bonferroni
    t-threshold for M variants, the deflated Sharpe ratio and the HLZ hurdle
    |t| > 3 per row, and a stored row count. Rows are written by the engine,
    never edited by hand.
  - Files: `efb/hygiene.py`, `docs/multiple_testing_ledger.md`,
    `tests/test_ledger.py`

- [ ] Task 4: evaluate F7.1 to F7.4 into RESULTS.json (P0)
  - Acceptance: every criterion evaluated with a stored number and written to
    `sprints/E7/RESULTS.json`, earlier sprints re-evaluated with no verdict
    changed.
  - Files: `efb/evaluate.py`, `sprints/E7/RESULTS.json`, `tests/test_e7_results.py`

- [ ] Task 5: the signal reports and the alpha conversion (P0)
  - Acceptance: `docs/research/E7_signal_{name}.md` per admitted signal with
    hypothesis, economic rationale, construction, IC and decay tables, regime
    and subperiod tables, neutralized results, the verdict PASS or NULL
    against the RG-Signal checklist with the number that decided it, and the
    champion-against-alternative difference. The alpha conversion stores
    alpha_i = IC x sigma_idio,i x z_i shrunk by kappa with the schema columns
    date, ticker, alpha, ic, sigma_idio, z, kappa, the E8 input contract.
    Each report ships a traceability test.
  - Files: `docs/research/E7_signal_*.md`, `data/alpha/{signal}/alpha.parquet`,
    `tests/test_e7_memo.py`

- [ ] Task 6: dashboard D6 Alpha Lab (P1)
  - Acceptance: `dashboard/tabs/d06_alpha_lab.py` with a signal selector, the
    IC time series with t-stat, the decay curve, raw-versus-neutral quantile
    spread charts, turnover, the ledger as a table, and the expected-return
    calculator whose inputs (IC, idio vol, z-score, shrinkage) and outputs
    (alpha in bp per day) are labeled on screen. Every panel builder raises
    on an empty read.
  - Files: `dashboard/tabs/d06_alpha_lab.py`, `dashboard/app.py`,
    `tests/test_dashboard_d6.py`

- [ ] Task 7: the RG-Signal gate (P0)
  - Acceptance: each admitted signal labeled PASS or NULL against the seven
    RG-Signal questions, with the deciding number per question stored in
    `sprints/E7/RG_SIGNAL.json`. Construction in E8 is not started under any
    outcome.
  - Files: `sprints/E7/RG_SIGNAL.json`, `tests/test_e7_results.py`

- [ ] Task 8: the walkthrough, the render and the engineering close (P0)
  - Acceptance: `notebooks/E7_walkthrough.ipynb` with the hash cell comparing
    stored against recomputed and typing neither, the by-hand IC and
    neutralization algebra, the shift audit run live, one section per
    criterion, the D6 panel-to-column map with the non-empty guard, the
    deliverable's evidence in citation order, what E8 inherits and the credit
    port note. Executed in one pass, rendered to HTML, published and linked.
    `make rebuild-e7` added and `make rebuild` extended; `VERSION.json` over
    E1 through E7; ledger and open items updated.
  - Files: `notebooks/E7_walkthrough.ipynb`, `Makefile`, `data/VERSION.json`,
    `docs/hygiene_ledger.md`, `docs/open_items.md`,
    `tests/test_e7_walkthrough_notebook.py`

## Order and stops

Tasks run in numeric order. The champion is provisional: every signal number
is reported under XS-v1 and under XS-v2 with the difference stored (F7.4).
Stop conditions: the shift audit (F7.1) fails; an earlier stored criterion
changes verdict; a build, render or publish step fails in a way two attempts
cannot fix. A signal labeled NULL is a successful sprint outcome, never a
stop.
