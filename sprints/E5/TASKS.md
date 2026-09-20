# Sprint E5 TASKS

Sprint E5, Risk Model Evaluation. Ten tasks including Task 0, each with a test.
A stored criterion is never reworded and no number in a walkthrough or a
deliverable is typed by hand. Stop conditions are marked where they belong.

- [ ] Task 0: three items, before any bias statistic (P0)
  - Acceptance: the covariance race grid is derived from an artifact and
    `data/eval/cov_horse_race.parquet` is rebuilt from it with F4.3's verdict
    confirmed, so `make rebuild` reproduces F4.3 from raw; the champion rule is
    printed verbatim out of `registry.json`; each candidate's eligibility is
    printed with its reason. All three printed in full and recorded in
    `sprints/E5/PROBES.md`.
  - Files: `efb/probes.py`, `efb/cov.py`, `tests/test_e5_probes.py`,
    `sprints/E5/PROBES.md`
  - STOP CONDITION 1: if the derived grid moves F4.3's verdict, store it as F5.0
    and report before continuing.

- [ ] Task 1: build and register XS-v2 (P0)
  - Acceptance: `efb/models/statistical.py` gains a residual-covariance
    estimator and `efb/build.py` gains `build_xs_v2`: XS-v1's factor structure
    with `D` replaced by k leading residual principal components plus the shrunk
    diagonal remainder, k chosen by the Marchenko-Pastur rule and stored.
    Registered with champion false, eligible true, its own parameters, data hash
    and artifacts hash. XS-v1 is not edited. Tests: the residual covariance is
    positive definite, it reproduces the diagonal when k is zero, it captures at
    least as much specific variance as the diagonal on the same window, and the
    stored k matches the MP count.
  - Files: `efb/models/statistical.py`, `efb/build.py`, `data/models/XS-v2/`,
    `tests/test_xs_v2.py`
  - STOP CONDITION 2: if XS-v2 cannot be built as specified, report before
    improvising a variant.

- [ ] Task 2: portfolio families and the daily bias engine (P0)
  - Acceptance: `efb/eval_risk.py` with the four families built from the panel
    with no look-ahead, at least 50 random portfolios each plus the two seed
    books, and a daily bias engine computing z_t = r_t / sigma_hat_{t|t-1} per
    version with B = sqrt(mean z squared), the confidence band, rolling
    12-month bias, coverage against 1.96, the MAD ratio and the Q-Q pair, at
    portfolio and asset level. Tests: families are deterministic under a fixed
    seed, no portfolio uses a weight dated after its own date, B equals one on a
    synthetic series drawn from the model, and coverage equals five percent
    there.
  - Files: `efb/eval_risk.py`, `data/eval/bias_*.parquet`,
    `tests/test_eval_risk.py`

- [ ] Task 3: horizon consistency and the asset-level check (P1)
  - Acceptance: the 1-day model scaled by sqrt(21) against a directly estimated
    21-day model, stored as a table per version; asset-level bias and coverage
    beside the portfolio-level numbers. Tests: the sqrt(21) scaling is applied
    to the daily forecast and not to the realized number, and the asset-level
    table covers every version and family.
  - Files: `efb/eval_risk.py`, `data/eval/e5_horizon.parquet`,
    `data/eval/e5_asset_level.parquet`

- [ ] Task 4: regimes, recovery times and the stress haircut (P0)
  - Acceptance: bias, coverage and recovery time within VIX terciles and within
    the episodes 2020 Q1 and 2022, for every version; the recovery time in
    trading days and a recommended stress haircut for the champion. The VIX
    series is fetched once, stored as an artifact, and named as the regime
    variable. Tests: every version appears in the regime table, the episode
    windows are the stored ones, and the haircut is a number with a stated
    basis.
  - Files: `efb/eval_risk.py`, `data/raw/vix.parquet`,
    `data/eval/e5_regimes.parquet`, `tests/test_e5_regimes.py`

- [ ] Task 5: the champion rule and the registry update (P0)
  - Acceptance: the rule is applied exactly as printed in Task 0b with the
    arithmetic stored, `champion: true` is set on one entry alone, and the
    registry's `champion_rule` is byte-identical to its previous value. Tests:
    the rule text is unchanged, exactly one version is champion, and the
    champion is eligible.
  - Files: `efb/registry.py`, `data/models/registry.json`,
    `tests/test_champion.py`
  - STOP CONDITION 3: if no version lands inside 0.9 to 1.1 across all families,
    print the table and stop before declaring a champion anyway.
  - STOP CONDITION 4: if two versions tie inside the confidence band and the
    tiebreak does not separate them.

- [ ] Task 6: evaluate every criterion into RESULTS.json (P0)
  - Acceptance: F5.0 if earned, F5.1 to F5.5 evaluated with a stored number each
    and written to `sprints/E5/RESULTS.json`, with the revisions block reporting
    any moved number and the data hash. Earlier sprints re-evaluated from
    artifacts with no verdict changed. STOP CONDITION 5 applies to any earlier
    verdict.
  - Files: `efb/evaluate.py`, `sprints/E5/RESULTS.json`,
    `tests/test_e5_results.py`

- [ ] Task 7: the research deliverable (P0)
  - Acceptance: `docs/research/E5_risk_model_diagnostic.md` with the PM answer
    in one paragraph, the champion decision with its rule and deciding number,
    the full heatmap, the regime table with recovery times and the recommended
    stress haircut, the XS-v2 against XS-v1 result, the champion's known
    weaknesses, and a section titled "What would falsify this?". Ships with
    `tests/test_e5_memo.py` asserting every headline number rounds to a stored
    value.
  - Files: `docs/research/E5_risk_model_diagnostic.md`, `tests/test_e5_memo.py`

- [ ] Task 8: dashboard D4 and the version selector (P1)
  - Acceptance: `dashboard/tabs/d04_risk_eval.py` with the bias heatmap by
    version, family and regime, rolling 12-month bias with bands, calibration
    and Q-Q, the horizon table and the champion badge showing the rule and the
    deciding number. Every panel builder raises on an empty read, every earlier
    tab still renders under every version, and the champion badge reads the
    registry rather than a constant.
  - Files: `dashboard/tabs/d04_risk_eval.py`, `dashboard/app.py`,
    `tests/test_dashboard_d4.py`

- [ ] Task 9: the walkthrough, the render and the engineering close (P0)
  - Acceptance: `notebooks/E5_walkthrough.ipynb` with the hash cell comparing
    stored against recomputed and typing neither, the by-hand derivations (the
    standardized returns, the bias statistic and its band, the coverage share,
    and the champion rule's arithmetic on the stored table), one section per
    criterion, the D4 panel-to-column map with the non-empty guard, the
    deliverable's evidence in citation order, what E6 inherits and the credit
    port note. Executed in one pass, rendered to HTML, published and linked.
    `make rebuild-e5` added and `make rebuild` extended to E1 through E5;
    `VERSION.json` and every registry entry sharing one artifacts hash; ledger
    entries with old value, new value, date and reason; `docs/open_items.md`
    updated with the race-grid item closed. Full suite and lint clean, committed
    and pushed.
  - Files: `notebooks/E5_walkthrough.ipynb`, `Makefile`, `data/VERSION.json`,
    `docs/hygiene_ledger.md`, `docs/open_items.md`,
    `tests/test_e5_walkthrough_notebook.py`

## Order and stops

Tasks run in numeric order. Task 0 is the pre-registration: the rule is printed
before any number exists, and the race grid is closed before any bias statistic
is computed. Task 1 builds the one new model the sprint evaluates. Tasks 2 to 4
are the evaluation and they are the bulk of the work. Task 5 is the decision and
it is mechanical once Task 4 exists. Tasks 6 to 9 are the record.

Six stop conditions, listed in the PRD. The one that matters most is the third:
if no version is inside 0.9 to 1.1 across all families, no model is fit for
decisions and declaring a champion anyway would be the failure mode this sprint
exists to prevent.
