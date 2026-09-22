# E10 fixes and the ongoing constituent source: report

Task `e10-fixes-and-constituent-source`, base commit 5b77d6f. Part A
corrected the nine E10 defects; Part B stood up the SSGA SPY constituent
source. Every number below is read from an artifact.

## Table 1: verdicts

| id | verdict | criterion | threshold | stored numbers |
| --- | --- | --- | --- | --- |
| F10.1 | fail | Simulated drawdown distribution matches the analytical approximation within 10% at the median for the seed book's SR. | simulated median drawdown within 10% of the analytical value | simulated -0.140308, analytical 0.035433, relative gap 2.959825, Gaussian -0.153969 |
| F10.1b | pass | The expected maximum drawdown at the book's horizon, n_obs * 21 / 252 years, is between 0.15 and 0.25 and within 100% of the simulated median. | expected maximum drawdown between 0.15 and 0.25 and a relative gap below 1.0 | horizon 14.5 y, expected MDD 0.199377, relative gap 0.296266, n_obs 174 |
| F10.2 | pass | Control: on i.i.d. bootstrapped returns the stop-loss does not improve Sharpe. On the real book the result is reported either way. | stop-loss does not improve Sharpe on the i.i.d. control | control mean diff -0.487285, improves false |
| F10.2b | pass | The stop-loss that can re-enter does not improve Sharpe on the i.i.d. control. | re-entering stop does not improve Sharpe on the i.i.d. control | control mean diff -0.071617, improves false, entries 2, exits 3, days flat 9 |
| F10.3 | fail | Vol targeting reduces the dispersion of realized annual vol across years by more than 40%. | dispersion reduction above 40% | raw 0.275355, targeted 0.233840, reduction 0.150769 |
| F10.3b | pass | A daily-return volatility estimate's dispersion reduction stays below 40% at every window. | maximum daily-estimator reduction below 40% | daily 21 0.206317, max 0.206317 |

## Table 2: revisions

| criterion | quantity | old | new | reason |
| --- | --- | --- | --- | --- |
| F10.1 | relative_gap_at_median | 4.959825 | 2.959825 | the simulated median is signed, the analytical value is a magnitude; the difference was taken across the sign |
| F10.3 | dispersion_reduction | 0.122049 | 0.150769 | the two dispersions were measured on different year sets (15 raw, 14 targeted); both now on the aligned 14-year set |

## Table 3: drawdown benchmarks

| quantity | value |
| --- | --- |
| simulated median maximum drawdown (i.i.d. bootstrap) | -0.140308 |
| Gaussian control median maximum drawdown | -0.153969 |
| Magdon-Ismail stationary median (the old benchmark) | 0.035433 |
| Magdon-Ismail expected maximum drawdown at horizon | 0.199377 |
| horizon (years) | 14.5 |
| n_obs | 174 |
| n_bootstrap | 2000 |
| relative gap vs the stationary median | 2.959825 |
| relative gap vs the expected maximum drawdown | 0.296266 |

The Gaussian control draws down deeper than the bootstrap, so the gap is
not fat tails or volatility clustering: it is the mismatch between a
stationary median and a finite-sample maximum drawdown. The bootstrap is
i.i.d. (rng.choice with replacement); every place that called it
block-bootstrapped now says i.i.d.

## Table 4: the stop-loss

| book | n_obs | n_dates_available | first_date | last_date | base Sharpe | old-stop change | re-entering change | entries | exits | days flat | stop_fired |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| design | 174 | 174 | 2012-02-29 | 2026-07-31 | 0.978110 | -0.394374 | -0.077161 | 2 | 3 | 9 | True |
| seed_ew | 207 | 4193 | 2025-10-28 | 2026-08-27 | 2.207336 | 0.000000 | 0.000000 | 0 | 0 | 0 | False |
| seed_mom_ls | 4091 | 4092 | 2010-05-28 | 2026-09-03 | -0.247915 | 0.225966 | 0.225966 | 0 | 1 | 1229 | True |

`_apply_stop_loss` is unchanged, since F10.2 was scored on it. The
re-entering stop is `_apply_stop_loss_reentering`, which tracks the
unstopped equity curve while flat so the -5% re-entry test is reachable.

## Table 5: the vol-target sweep

| estimator | window | n_years both sides | raw CV | targeted CV | reduction |
| --- | --- | --- | --- | --- | --- |
| monthly | 12 | 14 | 0.275355 | 0.233840 | 0.150769 |
| daily | 21 | 15 | 0.266348 | 0.211395 | 0.206317 |
| daily | 42 | 15 | 0.266348 | 0.219307 | 0.176613 |
| daily | 63 | 15 | 0.266348 | 0.237869 | 0.106923 |
| daily | 126 | 15 | 0.266348 | 0.211998 | 0.204057 |
| daily | 252 | 14 | 0.275355 | 0.235467 | 0.144861 |

The maximum reduction across every window is 0.206317, below the 40% bar,
so F10.3's verdict stands.

## Table 6: the constituent source

| quantity | value |
| --- | --- |
| SPY as-of date | 18-Sep-2026 |
| raw holding rows | 505 |
| equity rows after filtering | 503 |
| dropped: US DOLLAR | ticker -, CUSIP 999USDZ92, cash line |
| dropped: TPG INC | ticker 2602335D, CUSIP 436CVR021, contingent-value-right line |
| CUSIP non-null | 503 of 503 |
| SEDOL non-null | 503 of 503 |
| Wikipedia live constituents | 503 |
| SPY vs Wikipedia disagreement | 0 names |
| three-way disagreement stored | data/processed/constituent_crosscheck.parquet, 6 names |

The six disagreements are all against the stored membership, none between
SPY and Wikipedia: BE, ILMN and P are live members the stored membership
does not have (added after the pin), and BLDR, TAP and TTD are in the
stored membership but not live (removed after the pin). The archive holds
data/raw/spy_holdings/spy_holdings_2026-09-18.parquet; a second fetch on
the same as-of date does not overwrite or duplicate it. Sector stays on
Wikipedia, because the SPY file's Sector column is "-" for all rows.

## Table 7: the retroactive-membership defect

| symbol | security | date added | in pinned changes table | history dates wrongly marked a member |
| --- | --- | --- | --- | --- |
| BE | Bloom Energy | 2026-09-21 | no | 4360 |
| P | Everpure | 2026-09-21 | no | 4360 |
| RDDT | Reddit | 2026-08-18 | no | 4336 |
| ILMN | Illumina | 2026-09-21 (re-add) | yes (2015 add, 2024 remove) | 585 (the 2024-06-24 to 2026-09-18 gap) |

P is a reused symbol: it was Pandora Media's ticker before Sirius XM
acquired it, and is Everpure today. The symmetric case drops BLDR, TAP and
TTD from the membership matrix entirely, because they are not live and
have no removal event row.

## Table 8: gates

| gate | result |
| --- | --- |
| make test | 594 passed, exit 0 |
| make lint | clean, exit 0 |
| walkthrough | 23 cells executed, 0 error outputs, 0 null execution counts |
| F1.x to F9.x no-change | E1 0/5, E2 0/13, E3 0/9, E4 0/7, E5 0/5, E6 0/7, E7 0/6 |
| data/processed membership artifacts | unchanged (git status clean for data/processed; hashes 532623d5, d14736b7, 86411430) |

## Decisions under "Stop only if", and why no stop

None of the stop conditions fired. F1.x to F9.x did not change verdict.
F10.3b's maximum is 0.206317, below the 40% bar, and F10.1b landed at
0.199377, inside 0.15 to 0.25. No artifact had to be edited by hand, the
SPY file parsed to 503 equity rows, and Part B never required re-running
the universe reconstruction.

Decisions I made where the task left the choice to me: the bootstrap stays
i.i.d. and every label was corrected, rather than implementing a block
bootstrap, because the Gaussian control already demonstrates the
mechanism. The Qp large-argument form is 0.25 ln x + 0.49088. The daily
21-day window is the F10.3b headline. The xlsx is read through zip and
ElementTree rather than adding openpyxl, recorded in the hygiene ledger.
The archive is one file per as-of date under data/raw/spy_holdings.

## Disagreements and new findings

E10-F17: the F10.3b daily reductions measured here differ slightly from
the reviewer's table (daily 21 is 0.206317 here against 0.2042 there, and
the other windows differ by up to 0.008). The daily vol estimate is
sampled at the rebalance date and shifted one period, the exact analogue
of the monthly rule; the reviewer's exact sampling convention was not
recoverable from the handoff notes. The substantive conclusion is
unchanged: the maximum is below 0.40 and F10.3's verdict stands.

## Commits

- c5426aa: handoff status to in_progress
- 722c2d2: PROBES.md reproduces the nine review defects
- 7b92c0c: Part A, the nine corrections (F10.1/F10.3 stay failing)
- 38aa4d6: the frozen-universe defect reproduced
