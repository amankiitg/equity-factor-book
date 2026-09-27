# E12 P&L Attribution Report

The attribution is run on **the seed book's own stored days**: rho 0.02, seed 0, out
of `data/portfolios/mv_constrained.parquet`, 3,645 sessions from
2012-02-01 to 2026-07-31. The
live book replaces that input table and nothing else, which is what makes this a
scaffold rather than a placeholder.

Everything below is read from a stored artifact: `data/attribution/daily.parquet`,
`monthly.parquet` and `timeseries.parquet`, written by
`scripts/build_attribution.py`, and `sprints/E12/RESULTS.json` for the criteria.

## 1. Factor against idio, cumulative

| component | cumulative |
| --- | --- |
| total | +7039.6 bp |
| factor | -33.0 bp |
| idio | +7466.7 bp |
| cost | +0.0 bp |

The book is long/short and dollar-neutral, gross 1.0, so the numbers are basis
points of the book and of NAV at once. The split is not asserted: the identity's own
residual is stored per day and its worst day is
+123.3 bp, with a median of
+1.8 bp.

**What that residual is and is not.** It is total minus (factor + idio + cost), where
the three come from three different artifacts: the stored factor returns, the stored
specific returns and the panel's own total returns. On the sessions the current build
produced it closes to 6.9e-18, which is machine precision and the check the sprint
wanted. On this artifact it closes to machine precision on
174 of 3,645 sessions and misses
by a median of +1.8 bp elsewhere, because the
seed's older vintages do not reproduce their own panel from their stored factor and
specific returns. Both numbers are true and they are kept apart.

## 2. Per factor

The rows are ordered by absolute contribution, so the largest exposure the book ran is
first.

| factor | cumulative P&L | share of the factor line |
| --- | --- | --- |
| liquidity | -170.9 | +517.8% |
| reversal | +81.4 | -246.5% |
| momentum | +55.5 | -168.2% |
| size | +16.1 | -48.8% |
| resid_vol | -7.6 | +23.1% |
| beta | -7.5 | +22.6% |
| sector_55 | +0.0 | -0.0% |
| sector_10 | -0.0 | +0.0% |
| sector_40 | +0.0 | -0.0% |
| sector_15 | +0.0 | -0.0% |
| market | -0.0 | +0.0% |
| sector_50 | +0.0 | -0.0% |
| sector_20 | -0.0 | +0.0% |
| sector_25 | -0.0 | +0.0% |
| sector_45 | -0.0 | +0.0% |
| sector_30 | -0.0 | +0.0% |
| sector_60 | -0.0 | +0.0% |
| sector_35 | +0.0 | -0.0% |

## 3. The five largest months

Cumulative answers "did it work"; the by-period table answers "when". The five
largest months by absolute P&L, out of `monthly.parquet`:

| month | sessions | total | factor | idio |
| --- | --- | --- | --- | --- |
| 2025-02 | 19 | -462.0 | -7.7 | -465.1 |
| 2020-03 | 22 | +431.7 | -29.1 | +560.1 |
| 2017-05 | 22 | -424.4 | -9.9 | -385.6 |
| 2018-05 | 22 | +423.5 | +12.3 | +415.6 |
| 2026-05 | 20 | +405.8 | +9.3 | +362.2 |

## 4. Selection, sizing and timing

The three are separated by construction, not by a port:

- **Selection** is the alpha: `idio_momentum`, residualized on the champion design.
  On this book it is the idio line, +7466.7 bp.
- **Sizing** is Procedure 6.3's `alpha / sigma^2`, the 10% variance-share cap and the
  20-share floor, all of which act on the weights before the hedge.
- **Timing** is the *design vintage*. The hedge zeroes the book's exposure as measured
  on the design dated the close the book was built at; the return realizes under the
  design dated the session. The gap between the two is the timing line:
  +141.4 bp over the whole artifact.

not in this report: the regime table, the seven-way selection, sizing and timing decomposition, and the selection-versus-sizing-vs-timing port are in the roadmap's E12 scope and are not among this sprint's nine tasks. They are recorded as open in `sprints/E12/TASKS.md` rather than silently dropped.

### The hedge timing, measured

The two design vintages differ on **174 of 3,645
sessions**, which are the sessions that follow a rebalance date: the seed's descriptor
artifact is a monthly snapshot, so on every other session the design dated the session
and the design dated the book's own close are the same object.

| quantity | value |
| --- | --- |
| mean per-factor exposure gap, on those sessions | 0.01967 |
| largest single gap | 0.6258, of reversal |
| timing P&L | +141.4 bp |
| total P&L on those sessions | +520.7 bp |
| timing as a share of it | 27.2% |

An average taken over all 3,645 sessions would divide that by
twenty and read as nothing, which is why it is quoted this way.

**Is the design dated a session computable at the previous close? Yes, it is what it
is.** Every descriptor on row `t` of `descriptors.parquet` is built from data through
`t-1`: `efb/models/fundamental.py` writes size as `log(market_cap.shift(1))`, and
beta, residual volatility and liquidity each carry `.shift(1)` on their window, with
reversal shifting the return series by one; only momentum reaches further back (through
`t-21`). Measured on the stored artifact, the 2026-09-21 size descriptor equals log
market cap at the 2026-09-18 close exactly, to 0.000e+00 for LITE, MRNA and AAPL, and
misses the same-day cap by 8.4e-03 to 1.2e-01. And the cross-sectional R-squared the
stored fit actually achieved is 0.329586 on average, against the
shift test's **lagged** figure of 0.329462 and its look-ahead variant of
0.364005. It matches the lagged design, not the same-day one, which is
the second independent confirmation that the stored fit is the no-look-ahead pairing.

So there is no look-ahead in the stored model, and the hedge is not stale in the sense
of reading data it should not have. It is one session **behind**: the evening of close
`t` hedges with the design dated `t`, which carries data through `t-1`, while the book
earns its return over `t` to `t+1`, whose exposure is described by the design dated
`t+1`, available in the same evening. Recorded as a post-flip fix in
`docs/open_items.md`; the live hedge is unchanged.

## 5. The two estimators, side by side

The holdings view knows what the book held; the regression view only sees what it
earned. Regressing the book's daily P&L on the factor returns gives betas with
standard errors, and the sprint's second criterion asks whether those betas agree with
the average holdings-based exposures within one standard error.

| term | regression beta | SE | within one SE of the holdings view |
| --- | --- | --- | --- |
| beta | 0.0092 | 0.0176 | yes |
| liquidity | 0.0028 | 0.0351 | yes |
| market | 0.0215 | 0.0077 | no |
| momentum | 0.0250 | 0.0208 | no |
| resid_vol | -0.0888 | 0.0305 | no |
| reversal | 0.0230 | 0.0206 | no |
| sector_10 | -0.0158 | 0.0067 | no |
| sector_15 | -0.0292 | 0.0112 | no |
| sector_20 | 0.0140 | 0.0170 | yes |
| sector_25 | -0.0067 | 0.0129 | yes |
| sector_30 | -0.0225 | 0.0144 | no |
| sector_35 | -0.0155 | 0.0159 | yes |
| sector_40 | -0.0312 | 0.0187 | no |
| sector_45 | -0.0579 | 0.0220 | no |
| sector_50 | -0.0209 | 0.0126 | no |
| sector_55 | -0.0015 | 0.0090 | yes |
| sector_60 | -0.0040 | 0.0096 | yes |
| size | 0.0739 | 0.0337 | no |

**7 of 20 terms agree.** This is
a measurement on a book that rebalances monthly, where the regression's intercept
absorbs a month of drift that the holdings view attributes to factors; the live book
rebalances daily and is the object the criterion is about. Verdict: **pending**.

## 6. Skill against luck

| quantity | value |
| --- | --- |
| days | 3,645 |
| mean idio P&L | +2.0 bp/day |
| standard error of that mean | +0.6 bp |
| t-statistic | 3.43 |
| annualized information ratio | 0.902 |
| annualized Sharpe | 0.849 |
| its Lo (2002) standard error | 0.258 |

The rule the sprint pre-registered is that no skill is claimed unless the t-statistic
exceeds 2.0, and that the reported Sharpe carries its standard
error. Both are applied mechanically: t = 3.43 over 3645 days exceeds 2.0, so the number clears the bar F12.3 sets.

**Read that with its own caveat.** E10 chose the (rho, phi) whose net annualized Sharpe
is closest to 1.0 on this same sample, so a Sharpe of 0.85
measured here is the selection working, not an edge discovered. The live book trades a
different signal, documented as a null book whose factor-neutral IC is -0.0031 at
t -0.51, and the expected verdict for its thirty-day window is **luck**.

The number that decides what a thirty-day window can show:

| annualized information ratio | days needed for t of 2.0 |
| --- | --- |
| 0.25 | 16,128 |
| 0.5 | 4,032 |
| 1.0 | 1,008 |
| 2.0 | 252 |

## 7. The criteria as registered

| ID | criterion | verdict |
| --- | --- | --- |
| F12.1 | Holdings-based factor P&L plus idio P&L plus costs equals total P&L to 1e-10 every day. | partial |
| F12.2 | Time-series attribution betas agree with average holdings-based exposures within one standard error. | pending |
| F12.3 | The reported Sharpe carries its SE and no skill is claimed unless t exceeds 2. The expected verdict is luck; write it down. | pending |

Their stored numbers and the detail behind each verdict are in
`sprints/E12/RESULTS.json`.

## 8. What would falsify this

- **The identity failing on live days.** It failed on the seed's older vintages; if it
  fails on the live ones, the split is describing a different book from the one that
  traded.
- **The two estimators disagreeing beyond one standard error on a daily book.** They
  disagree on this monthly one, where the mismatch is explainable; a daily book has no
  such excuse.
- **The hedge's factor P&L growing.** It is the part that should have been zero. If
  the timing line grows rather than shrinks, the stale design is the cause and the
  post-flip fix is the remedy.
- **A realized cost far from the expected one.** The E9 model is untested by real
  fills until the live days exist.
- **A t above two on thirty days.** It would be the measurement, not the edge: thirty
  days cannot show an information ratio of 0.25, let alone 1.0.

## 9. Coverage

Built and stored: holdings-based attribution per day (factor by factor, idio, cost),
the reconciliation residual, both design vintages and the timing gap, the raw-beta
line, realized against forecast volatility with the bias statistic, the fill counts,
the cost split four ways, the two-estimator comparison, the skill test with its
standard errors, the page's section and the weekly review.

Not in this report, and named as open in `sprints/E12/TASKS.md`: the regime table and
the seven-way carry decomposition.
