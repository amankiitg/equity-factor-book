# Sprint E1: Tasks

## Status: In Progress

Rules: Task 0 precedes the ten atomic tasks and must complete before any
data-dependent work. Tasks 1 to 10 are the ten atomic tasks, each with a
test. Task 9 evaluates every F criterion; Task 10 produces the research
deliverable.

- [ ] Task 0: Probe every data source and paste printed rows into PROBES.md (P0)
  - Acceptance: `efb/probes.py` prints row count, first and last date, ticker
    coverage and NaN share for yfinance prices, the Wikipedia constituents and
    changes tables, the four French library files, GICS sectors, shares
    outstanding, and the risk-free rate (FF RF cross-checked against FRED
    DTB3); output pasted into `sprints/E1/PROBES.md`; a source is not
    available until its probe has printed rows.
  - Test: `tests/test_probes.py` (parsing and report functions on fixtures,
    no network).
  - Files: efb/probes.py, sprints/E1/PROBES.md, tests/test_probes.py
  - Completed: 2026-09-04. All six sources probed; printed rows in
    PROBES.md. FRED failed (timeout) and is recorded as null. The changes
    table is pinned to Wikipedia revision 1368675864. yfinance coverage
    662 of 858 requested tickers (current members 503 of 503).

- [ ] Task 1: yfinance price pipeline with adjusted-close audit (P0)
  - Acceptance: `efb/prices.py` downloads daily OHLCV, adjusted close and
    dividends for every requested ticker from 2010 to today, cleans and
    deduplicates, writes `data/raw/prices.parquet`, and runs the
    adjusted-close audit on 20 random names (total return from adjusted
    close vs dividend-adjusted series, max abs daily difference in bp,
    stored for F1.4).
  - Test: `tests/test_prices.py` (cleaning, dedupe, audit on synthetic
    prices).
  - Files: efb/prices.py, tests/test_prices.py, data/raw/prices.parquet
  - Completed: 2026-09-04. prices.parquet: 3,597,594 rows, 858 tickers,
    2010-01-04 to 2026-09-03, 0 weekend rows, 0 duplicate dates, 0 infs.
    F1.4 audit on 20 random names: mean abs diff 0.0178 bp, max 221.25 bp
    on one merger day (BKR 2017-07-05 special distribution), logged in the
    ledger and events; adj_close kept authoritative.

- [ ] Task 2: Universe membership matrix and sectors from Wikipedia (P0)
  - Acceptance: `efb/universe.py` parses the current constituents table and
    the changes table, rebuilds the point-in-time membership matrix from
    2010 to today, counts historical members recovered vs listed (stored for
    F1.5), and writes `data/processed/universe_membership.parquet` and
    `data/processed/sectors.parquet` per the PRD schemas.
  - Test: `tests/test_universe.py` (synthetic changes table produces the
    correct point-in-time matrix).
  - Files: efb/universe.py, tests/test_universe.py,
    data/processed/universe_membership.parquet, data/processed/sectors.parquet
  - Completed: 2026-09-04. Membership matrix 4350 business days x 858
    tickers, universe size 503 to 506 over time, 328 additions and 329
    removals. Survivorship: 355 deleted members, 159 with recoverable
    price history, fraction 0.4479 stored for F1.5.

- [ ] Task 3: Kenneth French factors and risk-free rate cross-check (P0)
  - Acceptance: `efb/factors.py` downloads and parses FF5 daily, Momentum
    daily, Short-term reversal daily and 12 industry portfolios daily,
    converts to decimal units, aligns to business days, writes
    `data/raw/factors_ff.parquet`, and cross-checks the FF RF column against
    FRED DTB3 (correlation and mean difference in bp recorded in the
    ledger); a FRED failure is recorded as a null with the design routed
    around it.
  - Test: `tests/test_factors.py` (parser on synthetic CSV text).
  - Files: efb/factors.py, tests/test_factors.py, data/raw/factors_ff.parquet

- [ ] Task 4: Returns and stylized facts (P0)
  - Acceptance: `efb/returns.py` computes simple, log and excess returns
    from `prices.parquet` and `factors_ff.parquet`, writes
    `data/processed/returns.parquet`, checks index alignment (business days,
    no timezone drift, no duplicate dates, no infs), and produces the
    stylized-facts table (kurtosis, ACF of r at lag 1, ACF of r^2 at lags 1,
    5, 21) for AAPL, XOM, JPM and the equal-weight universe.
  - Test: `tests/test_returns.py` (hand-computed returns on synthetic
    prices match to 1e-10; aggregation rules: log adds over time, simple
    adds across assets).
  - Files: efb/returns.py, tests/test_returns.py, data/processed/returns.parquet

- [ ] Task 5: Performance metrics library efb/perf.py (P0)
  - Acceptance: `efb/perf.py` implements Sharpe with i.i.d. and Lo (2002)
    standard errors, annualization, max drawdown, hit rate and slugging per
    the PRD formulas, all typed and documented; on the FF market factor the
    two Sharpe standard errors differ in the expected direction (Lo >= iid
    when returns are positively autocorrelated).
  - Test: `tests/test_perf.py` (known values on synthetic series; iid SE on
    Gaussian draws vs sqrt((1 + SR^2 / 2) / T); Lo SE reduces to iid SE when
    autocorrelation is zero).
  - Files: efb/perf.py, tests/test_perf.py

- [ ] Task 6: Hygiene Ledger and detection rules (P0)
  - Acceptance: `efb/hygiene.py` detects stale prices (zero-return runs of
    5 or more business days), flags outliers (|r| > 0.50, never winsorized
    in raw), marks delisting rows, and writes `data/processed/events.parquet`
    and the flags into `returns.parquet`;
    `docs/hygiene_ledger.md` records every policy decision with a date and a
    reason: missing-data policy, stale-price detection, outlier policy,
    delisting handling, timezone and date alignment, and a point-in-time
    flag per field.
  - Test: `tests/test_hygiene.py` (synthetic price series produce the
    expected stale, outlier and delisting flags).
  - Files: efb/hygiene.py, tests/test_hygiene.py, docs/hygiene_ledger.md,
    data/processed/events.parquet

- [ ] Task 7: Artifact assembly, versioning and one-command rebuild (P0)
  - Acceptance: `efb/build.py` orchestrates Tasks 1 to 6 end to end, writes
    `data/VERSION.json` with a SHA-256 content hash of every artifact, and
    `make rebuild-e1` rebuilds everything in one command.
  - Test: `tests/test_version.py` (hashes match file content; rebuild writes
    all artifacts and a VERSION entry per artifact).
  - Files: efb/build.py, tests/test_version.py, data/VERSION.json, Makefile

- [ ] Task 8: Dashboard D0 Data Health and global sidebar (P0)
  - Acceptance: `dashboard/app.py` provides the global sidebar with the data
    version hash and a tab router; `dashboard/tabs/d00_data.py` renders the
    six D0 panels from parquet only (coverage heatmap, missing and stale
    counts, universe size with additions and deletions, event log, ledger
    rendered in-app); D0 loads in under 3 seconds; a Methodology tab links
    the research deliverable and the walkthrough.
  - Test: `tests/test_dashboard_d0.py` (panel builders read parquet and
    return the expected structures; app and tabs import without executing a
    server).
  - Files: dashboard/app.py, dashboard/tabs/d00_data.py,
    dashboard/tabs/methodology.py, tests/test_dashboard_d0.py

- [ ] Task 9: Evaluate F1.1 to F1.5 and store numbers in RESULTS.json (P0)
  - Acceptance: `sprints/E1/RESULTS.json` contains every F1.x criterion with
    threshold, stored number, verdict (pass, fail, or pending with reason)
    and a note; the numbers are computed from the artifacts, not retyped.
  - Test: `tests/test_results.py` (RESULTS.json exists, has all five keys,
    numbers are floats, verdicts are valid).
  - Files: sprints/E1/RESULTS.json, tests/test_results.py

- [ ] Task 10: Research deliverable: Data Quality and Universe Note (P0)
  - Acceptance: `docs/research/E1_data_note.md` answers the sprint's PM
    question in one paragraph at the top, contains the methodology, the
    stored numbers, the practitioner conclusion, and a section titled
    "What would falsify this?"; written for a senior quant or risk manager
    who has not seen the code; linked from the Methodology tab; no em
    dashes.
  - Test: `tests/test_data_note.py` (file exists, required sections present
    with the required title, no em dash characters).
  - Files: docs/research/E1_data_note.md, tests/test_data_note.py

## Exit criteria (roadmap)

All F1 criteria evaluated with stored numbers in `sprints/E1/RESULTS.json`;
`make rebuild-e1` runs end to end; D0 loads in under 3 seconds; walkthrough
rendered; research deliverable written and linked from the Methodology tab.
