# Sprint E1: PRD: Universe, Returns and the Hygiene Ledger

Dates: Tue Sep 1 to Sun Sep 6. Tier 1. Gate: RG-Data (end of E1, before any
model is fit).

## Overview

Build the reproducible daily equity data layer and the Hygiene Ledger that
every later sprint reads from. The sprint ends with parquet artifacts, a
written ledger of every data decision, a performance-metrics library
(`efb/perf.py`), and dashboard tab D0 Data Health. No model is fitted in this
sprint.

## Goals

- Every data source probed and its availability recorded in
  `sprints/E1/PROBES.md` before it is used.
- Parquet artifacts for prices, returns, universe membership, FF factors and
  sectors, each with a documented schema and a content hash in
  `data/VERSION.json`.
- `efb/perf.py` computes Sharpe with standard error (i.i.d. and Lo 2002),
  annualization, max drawdown, hit rate and slugging, with unit tests.
- A Hygiene Ledger (`docs/hygiene_ledger.md`) records every data policy
  decision with a date and a reason, including point-in-time flags per field.
- Pre-registered criteria F1.1 to F1.5 evaluated with stored numbers in
  `sprints/E1/RESULTS.json`.
- Dashboard tab D0 Data Health renders in under 3 seconds reading parquet
  only, and the global sidebar shows the data version hash.
- Research deliverable `docs/research/E1_data_note.md` written and linked
  from the Methodology tab.

## User stories

- As a quant researcher, I want reproducible daily returns with documented
  corporate-action handling, so that every later model is fit on data I trust.
- As a risk manager, I want a Hygiene Ledger that records every policy
  decision with a date and a reason, so that I can audit any number in the
  book.
- As a PM, I want D0 Data Health to show coverage, missing and stale counts,
  universe size over time and an event log, so that I can answer "can I trust
  the data underneath every number this book will ever show?".
- As a later sprint author, I want `make rebuild-e1` to rebuild all E1
  artifacts from raw sources in one command, so that the registry is always
  reproducible.

## Technical architecture

```
Wikipedia (constituents + changes) ──▶ efb/universe.py ──▶ universe_membership.parquet
Wikipedia (GICS columns)          ──▶ efb/universe.py ──▶ sectors.parquet
yfinance (OHLCV, adj close, divs) ──▶ efb/prices.py    ──▶ prices.parquet
Kenneth French library            ──▶ efb/factors.py   ──▶ factors_ff.parquet
FRED DTB3 (cross-check)           ──▶ efb/factors.py   ──▶ probe only
prices + factors                  ──▶ efb/returns.py   ──▶ returns.parquet
returns                           ──▶ efb/hygiene.py   ──▶ stale/outlier flags, events.parquet
all artifacts                     ──▶ efb/build.py     ──▶ data/VERSION.json
parquet only                      ──▶ dashboard/tabs/d00_data.py (D0)
```

`make rebuild-e1` runs `python -m efb.build` which fetches sources, writes
parquet, updates `data/VERSION.json`, and stores F criteria numbers in
`sprints/E1/RESULTS.json`. The dashboard reads parquet and markdown only and
never recomputes.

## Data sources (all probed before use, Task 0)

1. yfinance daily OHLCV and adjusted close, S&P 500 members (current plus
   recoverable deleted names), 2010 to today.
2. Wikipedia S&P 500 constituents table and the "Selected changes" table.
3. Kenneth French library: FF5 daily, Momentum daily, Short-term reversal
   daily, 12 industry portfolios daily.
4. GICS sector per ticker (from the Wikipedia constituents table).
5. Shares outstanding via yfinance: record whether history is returned or
   only the current value (probe only, no artifact this sprint).
6. Risk-free rate: FF RF column, cross-checked against FRED DTB3.

## Formulas (inputs and outputs labeled)

Notation. P_t: adjusted close (INPUT: `prices.parquet` column `adj_close`).
rf_t: daily risk-free rate in decimals (INPUT: `factors_ff.parquet` column
`rf`). T: number of observations.

- Simple return: `r_t = P_t / P_{t-1} - 1` (OUTPUT: `returns.parquet` column
  `r`).
- Log return: `g_t = ln(P_t / P_{t-1})` (OUTPUT: `returns.parquet` column
  `g`).
- Excess return: `x_t = r_t - rf_t` (OUTPUT: `returns.parquet` column
  `excess`).
- Aggregation: sum of g over T days equals `ln(P_T / P_0)`; a portfolio
  return `sum_i w_i r_i` holds for simple returns only.
- Sharpe (daily): `SR = mean(x) / std(x, ddof=1)`. Annualized under i.i.d.:
  `SR_ann = SR * sqrt(252)`.
- Sharpe standard error, i.i.d.: `SE_iid = sqrt((1 + SR^2 / 2) / T)`,
  annualized by `sqrt(252)`.
- Sharpe standard error, Lo (2002) autocorrelation-consistent:
  `SE_lo = sqrt((1 / T) * (A + (SR^2 / 2) * B))` with
  `A = 1 + 2 * sum_{k=1..q} w_k * rho_k` (rho_k = autocorrelation of x),
  `B = 1 + 2 * sum_{k=1..q} w_k * phi_k` (phi_k = autocorrelation of x^2),
  `w_k = 1 - k / (q + 1)`, default `q = 5`. Annualized by `sqrt(252)`.
  Reduces to the i.i.d. formula when all autocorrelations are zero.
- Max drawdown: `D_t = W_t / max_{s <= t} W_s - 1`; `MDD = min_t D_t`
  (reported as a negative number).
- Hit rate: fraction of periods with positive excess return.
- Slugging: mean positive excess return divided by absolute mean negative
  excess return.
- Survivorship bias: annualized difference between a naive buy-all-current-
  members equal-weight daily return and the point-in-time membership
  equal-weight daily return.

## Parquet schemas

`data/raw/prices.parquet` (long format)

| column | dtype | meaning |
| --- | --- | --- |
| date | datetime64[ns] | business day, New York calendar |
| ticker | string | uppercase symbol |
| open, high, low, close | float64 | unadjusted OHLC |
| adj_close | float64 | split and dividend adjusted close |
| volume | int64 | shares |
| dividend | float64 | cash dividend per share on ex-date |

Index: none (RangeIndex). Sorted by (ticker, date). Duplicates dropped.

`data/processed/returns.parquet` (long format)

| column | dtype | meaning |
| --- | --- | --- |
| date | datetime64[ns] | business day |
| ticker | string | uppercase symbol |
| r | float64 | simple return on adjusted close |
| g | float64 | log return on adjusted close |
| excess | float64 | r minus daily rf |
| stale | bool | zero-return run of 5 or more consecutive business days |
| outlier | bool | abs(r) > 0.50 on a non-delisting day |

`data/processed/universe_membership.parquet` (wide format)

- index: date (datetime64[ns], business days).
- columns: one boolean column per ticker that was ever a member.
- True means the ticker was in the S&P 500 on that date, rebuilt
  point-in-time from the changes table.

`data/raw/factors_ff.parquet` (wide format)

- index: date (datetime64[ns], business days).
- columns (decimal units, not percent): mkt_rf, smb, hml, rmw, cma, rf, mom,
  st_rev, ind1 ... ind12 (12 industry portfolio value-weighted returns).

`data/processed/sectors.parquet`

| column | dtype | meaning |
| --- | --- | --- |
| ticker | string | uppercase symbol |
| gics_sector | string | GICS sector from Wikipedia; null if unknown |
| gics_sub_industry | string | GICS sub-industry; null if unknown |
| source | string | wikipedia |
| as_of | datetime64[ns] | snapshot date of the constituents table |

`data/processed/events.parquet` (D0 event log)

| column | dtype | meaning |
| --- | --- | --- |
| date | datetime64[ns] | event date (membership change or return date) |
| ticker | string | affected ticker |
| event_type | string | added, removed, outlier, stale_start, split, dividend_large |
| detail | string | human-readable description |

`data/VERSION.json` maps every artifact path to its SHA-256 content hash and
records the build timestamp.

## Pre-registered falsification criteria (copied verbatim from the roadmap)

Numeric thresholds written before the numbers are seen; each is evaluated
with a stored number in `sprints/E1/RESULTS.json`.

| ID | Criterion |
| --- | --- |
| F1.1 | Each probed source returns at least 95% of requested tickers with at least 10 years of daily history. A failing source is recorded in the ledger and the design adapts; it is never silently dropped. |
| F1.2 | Zero NaNs in returns.parquet after the warm-up window, except documented delisting rows. |
| F1.3 | Equal-weight universe daily return vs the Kenneth French market return (Mkt-RF + RF) correlation above 0.95. Lower means a date-alignment or adjustment bug, not a finding. |
| F1.4 | Total returns computed from adjusted close reproduce the dividend-adjusted series within 1 bp per day on 20 randomly sampled names. |
| F1.5 | Survivorship measured: the fraction of historical members with recoverable history is stored. If below 70%, the ledger records the bias magnitude via a naive buy-all-members backtest against the FF market return. |

## Dashboard tab D0 spec (Data Health)

Reads parquet and `docs/hygiene_ledger.md` only, never recomputes.

1. Coverage heatmap: ticker x month, cell = fraction of business days with a
   non-null close (from `prices.parquet`).
2. Missing and stale counts: current missing tickers and stale-price runs
   (from `returns.parquet` columns `stale`).
3. Universe size over time with additions and deletions (from
   `universe_membership.parquet` and `events.parquet` event_type added /
   removed).
4. Corporate-action and outlier event log (from `events.parquet`).
5. Hygiene Ledger rendered in-app (markdown from `docs/hygiene_ledger.md`).
6. Data version hash in the global sidebar (from `data/VERSION.json`).

D0 must load in under 3 seconds with full history. The global sidebar
(`dashboard/app.py`) is created in this sprint and extended in E4.

## Research framing (copied verbatim from the roadmap)

- Academic question: What is a return, and which definition (simple, log,
  excess) is correct for which operation: aggregation through time,
  aggregation across assets, and risk measurement?
- Practitioner question: Can I trust the prices, the universe and the
  risk-free rate underneath every number this book will ever show?
- Research question: Is a free, survivorship-affected universe good enough
  to support factor-model research, and how large is the bias it introduces,
  in basis points per year?
- Research deliverable: Data Quality and Universe Note, written for a senior
  quant or risk manager; it must contain the methodology, the stored
  numbers, the practitioner conclusion, and a section titled "What would
  falsify this?". A negative verdict is a complete deliverable.
- The TASKS.md must include one task that produces the deliverable and one
  that evaluates every falsification criterion listed below.

## Out of scope

- No model is fitted: no factor exposures, covariance or optimization.
- Shares outstanding is probed but no artifact is built this sprint.
- No delisting returns from CRSP; delisting policy is documented in the
  ledger.
- Book writing (E11) and credit port (E13).

## Dependencies

- Repo skeleton and engineering standards (Roadmap Appendix B), already in
  place.
- Network access to yfinance, Wikipedia, the Kenneth French library and
  FRED at build time.
