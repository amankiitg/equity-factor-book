# Data Quality and Universe Note

Sprint E1 research deliverable, 2026-09-04. Written for a senior quant or
risk manager who has not seen the code. No em dashes.

## PM question

Can I trust the data underneath every number this book will ever show?
Yes, with three documented caveats. The prices and the risk-free rate are
trustworthy for current S&P 500 members (full coverage, adjusted-close
audit mean of 0.018 bp per day, universe reconciles to the Kenneth French
market at a correlation of 0.9557). The caveats: only 44.8% of deleted
members have recoverable history, which inflates a naive current-members
backtest by about 349 bp per year; 302 interior missing return rows
across 13 tickers exist inside the universe window; and FRED was
unreachable, so the risk-free rate rests on the Kenneth French RF column
alone. None of these caveats silently corrupt a number: each is flagged,
measured and recorded, and every downstream sprint reads the ledger
first.

## Research questions

- Academic question: What is a return, and which definition (simple, log,
  excess) is correct for which operation: aggregation through time,
  aggregation across assets, and risk measurement?
- Practitioner question: Can I trust the prices, the universe and the
  risk-free rate underneath every number this book will ever show?
- Research question: Is a free, survivorship-affected universe good enough
  to support factor-model research, and how large is the bias it
  introduces, in basis points per year?

## Methodology

Sources. Daily prices, adjusted close, dividends and split factors come
from yfinance for 858 tickers: 503 current S&P 500 members plus 355
deleted members recovered from the Wikipedia changes table. The
constituents table is the live Wikipedia page; the changes table was
removed from the live page on 2026-08-11, so E1 pins revision 1368675864
(2026-08-10), the last revision that still publishes it, covering
1976-07-01 to 2026-08-05. Factors come from the Kenneth French library
(FF5 daily, Momentum daily, Short-term reversal daily, 12 industry
portfolios daily), 202607 vintage, ending 2026-07-31. GICS sectors come
from the Wikipedia constituents table. Shares outstanding was probed
(yfinance returns a history for 10 of 12 sampled names) but no artifact
is built from it because free sources are not point-in-time.

Universe. The membership matrix is rebuilt point-in-time by walking the
changes table backward from today's members: at each event date, for all
earlier dates the removed ticker is a member and the added ticker is not.
The matrix has 4,350 business days (2010-01-04 to 2026-09-04) and 858
tickers; the universe size is stable between 500 and 508 members.

Returns. Simple returns r = P/P(-1) - 1 and log returns g = ln(1 + r) are
computed from adjusted close; excess returns subtract the daily FF RF
rate. Log returns add over time, simple returns add across a portfolio.
Missing prices stay NaN; nothing is imputed or winsorized in the raw
artifact.

Checks. Index alignment (business days only, no duplicate dates, no
infs), the adjusted-close audit (total return from adjusted close versus
close plus dividends, 20 randomly sampled names, seed 42), the
equal-weight universe reconciliation against the FF market return, and
the survivorship backtest (naive buy-all-current-members versus
point-in-time membership versus the FF market).

## Stored numbers

Falsification criteria, evaluated from the artifacts and stored in
sprints/E1/RESULTS.json. Criterion text is copied verbatim from the
roadmap.

| ID | Threshold | Stored number | Verdict |
| --- | --- | --- | --- |
| F1.1 | Each probed source returns at least 95% of requested tickers with at least 10 years of daily history | yfinance coverage 77.2% of all requested tickers; 100.0% of current members; 71.3% of 10-year-eligible tickers | fail |
| F1.2 | Zero NaNs in returns.parquet after the warm-up window, except documented delisting rows | 302 interior NaN return days across 13 tickers | fail |
| F1.3 | Equal-weight universe daily return vs the Kenneth French market return (Mkt-RF + RF) correlation above 0.95. Lower means a date-alignment or adjustment bug, not a finding | 0.9557 | pass |
| F1.4 | Adjusted close reproduces the dividend-adjusted series within 1 bp per day on 20 random names | max 221.25 bp on one merger day, mean 0.0178 bp | fail |
| F1.5 | Fraction of historical members with recoverable history stored; below 70% records the bias magnitude | fraction 0.4479; naive minus point-in-time 349.4 bp per year; naive minus FF market 372.4 bp per year; point-in-time minus FF market 21.1 bp per year | fail |

Stylized facts. Kurtosis (normal is 3), autocorrelation of r at lag 1,
and autocorrelation of r squared at lags 1, 5, 21.

| Series | Kurtosis | ACF(r, 1) | ACF(r^2, 1) | ACF(r^2, 5) | ACF(r^2, 21) |
| --- | --- | --- | --- | --- | --- |
| AAPL | 9.07 | -0.032 | 0.213 | 0.137 | 0.031 |
| XOM | 9.57 | -0.020 | 0.204 | 0.253 | 0.154 |
| JPM | 12.66 | -0.089 | 0.376 | 0.225 | 0.082 |
| Equal-weight universe | 17.25 | -0.076 | 0.366 | 0.284 | 0.087 |

Interpretation for risk modeling. Daily returns are far from Gaussian
(kurtosis 9 to 17), so any Gaussian risk number is a floor, not an
estimate. Returns have essentially no own lag-1 autocorrelation, while
squared returns carry strong positive autocorrelation that decays slowly
from lag 1 to 21: volatility clusters, returns do not.

Sharpe with standard error, FF market factor (Mkt-RF), daily 2010 to
2026.

| Quantity | Value |
| --- | --- |
| Sharpe ratio, daily | 0.0479 |
| Sharpe ratio, annualized | 0.76 |
| SE i.i.d., annualized | 0.246 |
| SE Lo (2002), annualized | 0.227 |
| Ratio Lo / iid | 0.922 |

The two standard errors differ by 8%, and the Lo correction is the
smaller one here because the market factor's lag-1 autocorrelation is
negative (-0.103), which makes the mean more precisely estimated, while
the squared-return clustering term is weighted by SR^2 / 2 and barely
moves the number. The direction of the correction always follows the
data's autocorrelation structure; the lesson is that an eyeballed Sharpe
carries a standard error near 0.2 to 0.25 and is a hypothesis, not
evidence.

Survivorship. Of 355 deleted members, 159 (44.8%) have recoverable price
history. A naive backtest that buys all current members over the whole
window earns 372.4 bp per year more than the FF market; the point-in-time
universe earns 21.1 bp per year more. The survivorship bias is therefore
349.4 bp per year.

## Practitioner conclusion

The data layer is usable for factor-model research, with two rules. Rule
one: every long-only backtest in later sprints carries a mandatory
survivorship caveat, because the naive current-members universe inflates
returns by about 350 bp per year and the roadmap's 200 bp line is
crossed; long/short constructions are preferred wherever the question
allows them. Rule two: the equal-weight universe tracks the FF market at
0.9557, so the price and alignment machinery is sound; residual
disagreement comes from the 302 interior gaps and the 13 stale names,
all of which are flagged in returns.parquet and events.parquet rather
than hidden. The risk-free rate is the FF RF column; FRED was
unreachable and is recorded as a null, not silently substituted.

## What would falsify this?

If the equal-weight universe had failed to track the FF market return
(F1.3 below 0.95), the data layer would be wrong before any model
exists, and nothing downstream could be trusted. It passes at 0.9557.
If survivorship bias were above 200 bp per year, every long-only
backtest in later sprints would carry a mandatory caveat and long/short
constructions would be preferred. The measured bias is 349.4 bp per
year, so the caveat and the long/short preference are in force. If a
data source failed its probe, it would be recorded as a null and the
design routed around it. FRED failed and was recorded as a null.

A negative verdict is a complete deliverable: three of five criteria
fail, and each failure is a measured, documented property of the free
data stack, not an accident waiting to corrupt a model.

## Open questions

- Delisting returns: no free source provides them; the delisting policy
  (NaN after the last price) is documented, but later sprints may want a
  CRSP-based supplement before trusting long/short edges.
- The changes table pin: revision 1368675864 is frozen in time. A later
  sprint should re-pin or replace the source and reconcile the two
  universes.
- The French daily files lag the calendar by one month (202607 vintage
  ends 2026-07-31); excess returns inherit that lag by design.
- FRED access: worth retrying from a different host; until then the RF
  cross-check remains null.
- Sectors and shares outstanding are not point-in-time; any factor that
  needs historical sectors or shares must bring its own vintage source.

## Addendum, 2026-09-10: restated on corrected data

Everything above was written before the ticker identity check existed, and
it is left as written. This addendum states what changed and why.

What was wrong. A ticker symbol is not an identity. When an S&P 500 member
is acquired or delisted its symbol can be taken by an unrelated listing,
and the vendor then splices both companies into one price history. Four
names had a level break no split could explain (CPWR, EP, MI, POM) and 32
more had a name mismatch with clean prices, where the vendor hides the
splice by keeping only one company's history. The close-out task C1
compared every removed security name in the Wikipedia changes table with
the current holder of that symbol on yfinance and found 36 reused symbols
out of 373 removed tickers; 244 more have no listing today and could not
be checked either way. The full table is in sprints/E2/PROBES.md.

What the fix does. Those 36 tickers no longer contribute returns:
returns.parquet drops their rows (858 tickers before, 822 now) and their
events go with them. The membership matrix is untouched, because they
really were members; only their prices are unusable. Nothing is silently
overwritten: the flags, the raw prices and the ledger all stay as they
were.

What moved. sprints/E1/RESULTS.json now carries a revisions block with
the old value, the new value, and the data hash of each, so the change is
on the record rather than in a commit message:

| Criterion | Before | After | Verdict | Why |
| --- | --- | --- | --- | --- |
| F1.3 equal-weight vs market return correlation | 0.95575 | 0.95655 | pass | the universe return no longer averages in 36 spliced series |
| F1.5 survivorship bias, naive minus point-in-time | 349.67 bp/yr | 365.81 bp/yr | fail | the same 36 names leave the backtest universe |
| F1.5, point-in-time minus FF market | 20.75 bp/yr | 9.36 bp/yr | fail | the point-in-time book is cleaner, so less of the gap is left to measure |
| F1.1, F1.2, F1.4 | unchanged | unchanged | unchanged | they read the price artifact, which this correction does not touch |

The bias got larger, not smaller, which is the honest direction: some of
the deleted members that were previously counted had fabricated histories,
and removing them leaves fewer recovered names out of the same deleted
set. F1.5 fails on both runs, so no verdict changed.

The prices artifact is byte for byte identical to the previous build,
verified by the content hashes in data/VERSION.json, so every movement
traces to the exclusions and not to a data refresh. The equal-weight
universe return, which F1.3 correlates against the market, is the other
object that changed: it is now an average over the 822 tickers with usable
history. The ten-year coverage fraction in F1.1 did not move, because it
reads first-available price dates rather than returns, and the same is
true of F1.2 and F1.4.

The walkthrough notebook was re-executed against the new artifacts and
re-rendered at notebooks/E1_walkthrough.html.

## Addendum 2: the second C2 re-run, after C6

The close-out task C6 went back to the reused symbols C1 had excluded and
asked, for each one, whether the symbol is a current index constituent or
has an added row for the same ticker dated after its removal. Where the
name on that side matches the yfinance holder, the symbol was renamed
rather than taken over, so the ticker comes back with its history starting
at the later of the re-add date and its first valid price. Three names
return: FOX from 2019-03-13, FOXA from 2019-03-12 and PCG from 2022-10-03.
DuPont (DD) stays out, because "DuPont" against "DuPont de Nemours, Inc."
scores 0.33 against a 0.5 bar. The full review, with every removed and
current name, is in sprints/E2/TICKER_REVIEW.md and the decision table is
reproduced in docs/research/E2_exposure_study.md.

E1 was rebuilt on the result and its criteria were re-measured. This is a
second pass, so sprints/E1/RESULTS.json keeps a revisions history with one
entry per data hash rather than a single old and new pair:

| Criterion | Before C6 | After C6 | Verdict | Why |
| --- | --- | --- | --- | --- |
| F1.3 equal-weight vs market return correlation | 0.95655 | 0.95636 | pass | the universe return averages in three more series |
| F1.5 fraction of deleted members recovered | 0.44789 | 0.44789 | fail | the restored names are current members, not deleted ones |
| F1.5 survivorship bias, naive minus point-in-time | 365.81 bp/yr | 365.10 bp/yr | fail | the naive book gains three names with long histories |
| F1.5, naive minus FF market | 377.20 bp/yr | 375.37 bp/yr | fail | same correction |
| F1.5, point-in-time minus FF market | 9.36 bp/yr | 8.24 bp/yr | fail | same correction |
| F1.1, F1.2, F1.4 | unchanged | unchanged | unchanged | they read the price artifact, which this correction does not touch |

All four E1 verdicts are unchanged, and the movements are a fraction of a
basis point per year. The direction is the expected one: three large
current constituents back in the naive universe pull its return closer to
the market, so the measured survivorship gap shrinks slightly rather than
growing. The prices artifact is byte for byte identical again, verified by
the content hashes in data/VERSION.json, so every movement traces to the
membership of the return panel.

The estimation panel now covers 502 of the 503 current constituents, up
from 499, with DD the only gap. The E1 walkthrough notebook was re-executed
against the new artifacts and re-rendered at notebooks/E1_walkthrough.html.
