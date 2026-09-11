# Hygiene Ledger

Append-only, timestamped record of every data policy decision in the EFB.
Each entry has a date, the decision, and the reason. Entries are never
edited or removed; corrections are new entries.

## 2026-09-04: Wikipedia changes table pinned to revision 1368675864

Decision. The S&P 500 constituent changes table is read from Wikipedia
revision 1368675864 (2026-08-10), not from the live page.

Reason. The live page removed the "Selected changes" table on 2026-08-11.
Revision 1368675864 is the last revision that still publishes it and
covers 1976-07-01 to 2026-08-05, enough for the 2010-to-today universe.
If the table returns to the live page, a later sprint re-pins and updates
this entry.

## 2026-09-04: FRED DTB3 cross-check recorded as null

Decision. The risk-free rate is the Kenneth French daily RF column. The
FRED DTB3 cross-check is recorded as a null.

Reason. FRED times out from the build host (three attempts, up to 90 s).
Per F1.1, a failing source is recorded in the ledger and the design
adapts; it is never silently dropped. FF RF is the authoritative daily
risk-free rate for E1.

## 2026-09-04: Share-class tickers mapped to yfinance symbols

Decision. Wikipedia tickers with a dot (BF.B, BRK.B) are requested from
yfinance with a hyphen (BF-B, BRK-B) and mapped back to the Wikipedia
form in every artifact.

Reason. yfinance uses the hyphen convention for share classes. Without
the mapping the two current members returned no data.

## 2026-09-04: yfinance Close is split-adjusted; Adj Close adds dividends

Decision. The price pipeline treats yfinance Close as already
split-adjusted and Adj Close as dividend-adjusted. The adjusted-close
audit compares Adj Close total returns with (close + dividend) / prior
close and never reapplies split factors.

Reason. Verified on the delivered series: the split action column records
split events whose adjustment is already inside Close. Reapplying the
factor doubles the adjustment and manufactures fake returns.

## 2026-09-04: Adj Close is authoritative for returns on corporate-action days

Decision. Returns (simple, log, excess) are computed from Adj Close.
Days where the audit disagrees with the close-plus-dividend series by
more than 1 bp are logged in events.parquet as corporate-action events;
the return is never overwritten.

Reason. On merger and special-dividend days (for example BKR on
2017-07-05, a $17.50 special distribution in the GE Oil and Gas
combination) the close-plus-dividend series and Adj Close disagree by
design, because the special distribution does not belong to the
continuing entity. Adj Close is the consistent continuing-holder series.

## 2026-09-04: Point-in-time flags per field

Decision. Per-field point-in-time status:

- prices (open, high, low, close, adj_close, volume, dividend): treated
  as point-in-time as delivered by the vendor, with the caveat that
  vendors revise historical series; rebuilds re-download and re-hash.
- universe membership: point-in-time by construction, rebuilt from the
  changes table, except that before the earliest covered event
  (1976-07-01) membership is extended backward unchanged.
- gics_sector, gics_sub_industry: NOT point-in-time. Known only for
  current members as of the snapshot date.
- shares outstanding: NOT point-in-time. yfinance returns a history for
  10 of 12 sampled names but it is current-vintage data, not the value
  known at each date. No artifact is built from it in E1.
- risk-free rate: FF RF is the daily series; not subject to look-ahead
  because it is a market-wide rate.

Reason. Free sources give current snapshots, not historical vintages.
Anything dated t that feeds a forecast must be data known at t; fields
flagged not point-in-time must never feed a forecast unmodified.

## 2026-09-04: Missing-data policy for prices

Decision. Missing prices stay NaN in the raw artifact. Returns are NaN
on any day where either leg of the return is missing. Coverage is
measured, never imputed.

Reason. Imputation hides coverage gaps from the dashboard and the
research gates. A later sprint that needs filled prices adds an explicit
imputation step with its own ledger entry.

## 2026-09-04: Delisting handling

Decision. A delisted name keeps its rows through its last traded day and
is NaN afterward. The last non-NaN return is not the delisting return:
no delisting-return source exists in the free stack. Returns after the
last price are documented delisting rows under F1.2.

Reason. CRSP-style delisting returns are not available from free
sources. Recording the policy prevents later sprints from confusing
post-delisting NaN with missing data.

## 2026-09-04: Stale-price detection

Decision. A zero-return run of 5 or more consecutive business days is
flagged stale in returns.parquet (column stale) and the first day of the
run is logged in events.parquet as stale_start. The raw return is never
overwritten.

Reason. Zero-return runs show up later as spurious low volatility and
must be visible before any volatility model reads the file. Measured on
the E1 data: 874 runs across 13 tickers (mostly delisted names with flat
closing prints; AMCR and FERG are current members and are called out in
the research note).

## 2026-09-04: Outlier policy

Decision. Any |r| > 0.50 is flagged (column outlier) and logged in
events.parquet; the raw return is never silently winsorized. 226 such
days exist in the E1 data, concentrated in a few delisted names (CPWR,
EP and others).

Reason. Winsorizing raw data is a modeling choice, not a data choice; a
later sprint that wants winsorized returns adds its own explicit step.
The raw artifact stays faithful to the source.

## 2026-09-04: Warm-up window

Decision. Prices are downloaded from 2009-12-15, eleven business days
before the 2010-01-04 universe start, so the first 2010 return has a
prior price. returns.parquet begins on 2010-01-04. F1.2 evaluates NaNs
after the warm-up window and outside documented delisting tails.

Reason. A return needs two prices; without a warm-up the first day of
the window would be NaN by construction.

## 2026-09-04: Timezone and date alignment

Decision. All artifacts use a business-day DatetimeIndex on the New
York calendar with no timezone attached. Weekend rows are dropped,
duplicates are dropped keeping the last, and returns are aligned to the
French daily files by date only (both are US-close series).

Reason. Mixing calendars or keeping timestamps invites one-day shifts
between the French library and yfinance, which would destroy every later
regression. Alignment was verified by the F1.3 correlation of 0.9557
between the equal-weight universe return and the FF market return.

## 2026-09-10: MODEL_START = 2010 for every E2 regression

Decision. Every E2 regression starts at 2010-01-04, the start of the E1
window. MODEL_START is the first calendar year with at least 300
point-in-time members that have price coverage; the Task 0 probe shows
2010 already has 354 covered members, so the threshold does not shorten
the window.

Reason. E1 measured survivorship bias of 349 bp per year (F1.5) and the
coverage gradient by year: 68.9% of point-in-time members are covered in
2010, rising to 99.2% in 2026. Starting later would improve coverage but
discard more than a third of the sample; 300 names is enough for
cross-sectional statistics and is the pre-registered threshold. The full
table is in sprints/E2/PROBES.md.

## 2026-09-10: Missing deletions bias the loser-side residual tail down

Decision. No correction is applied in E2. The following is recorded as
context for E3 and E5.

Only 44.8% of deleted S&P 500 names have recoverable price history, and
the deletions that are missing are disproportionately failures (mergers
and spin-offs survive in vendor data more often than bankruptcies). The
practical consequence is one-sided: the lower tail of residual returns
is thin, so measured specific risk on the loser side is biased
downward, and any long/short construction that shorts distressed names
will look safer than it is. E2's seed long/short momentum book inherits
this caveat. Fixing it requires a delisting-return source, tracked in
docs/open_items.md.

## 2026-09-10: Flagged rows and reused symbols must not enter the estimator

Decision. Volatility, momentum and portfolio risk code reads returns
through efb.hygiene.clean_returns, which sets stale and outlier rows to
NaN. Tickers whose price history splices two companies leave the
estimation panel entirely. The raw returns, the flags, the raw prices and
the events log are unchanged.

Reason. Ticker MI moves from an adjusted close of 0.196 to 18.90 on
2026-05-18, a 96x jump with no split in the vendor data and an outlier
flag from E1 as the policy requires. The volatility horse race and the
portfolio risk history still read the raw r column at that point, so this
one row pushed the trailing 252d mean QLIKE from -6.61 to -1.82 and turned
the study's headline claim into "adaptive methods beat trailing
volatility by five QLIKE units". After the fix the mean is -6.61 and the
largest per-name QLIKE is -3.77 instead of +2989.39.

Chasing that row found the bigger problem. MI is not a bad return, it is
a reused symbol: the 2026 listing took the ticker of a 2010 to 2011 S&P
500 member. CPWR, EP and POM are the same, and all four were real members
whose genuine issuer histories are missing from the vendor data. Masking a
single day would have left eleven years of another company's returns in
place, so the four names are dropped from the E2 estimation panel and the
drop is recorded in the TS-v1 registry entry. They were not dropped
silently: the successor criterion F2.6 tests for exactly this pattern,
stores the four names and the 20 offending rows, and fails, because
dropping a name is a mitigation and not a repair. The repair needs a
security-identity source and is tracked in docs/open_items.md.

The F2.3 verdict does not change, since it was already a fail, but the
size of the effect and the claim built on it do.

## 2026-09-10: Ticker identity, and 36 reused symbols leave the panel

Decision. Every ticker on the Wikipedia changes table's removed list is
compared with the current holder of that symbol on yfinance, cached to
data/raw/yf_names.parquet so each symbol is asked once, and matched by
name token overlap after stripping legal suffixes, punctuation and share
class letters. A verified mismatch means the symbol was reused, and the
ticker leaves the estimation panel. A symbol with no name today is
recorded as unverified and kept, because a missing name is not evidence
of reuse. Tickers with a gap above 60 business days between two live price
segments are flagged separately; none were found.

Old value: 858 tickers in returns.parquet, 47 GARCH fits, F1.3 0.95575,
F1.5 bias 349.67 bp/yr.
New value: 822 tickers, 47 GARCH fits over the reduced panel, F1.3
0.95655, F1.5 bias 365.81 bp/yr. Table and both data hashes in
sprints/E1/RESULTS.json under revisions.

Reason. Four symbols had a level break no split explained (CPWR, EP, MI,
POM) and 32 more had a name mismatch with clean prices, where the vendor
hides the splice by keeping only one company's history. Names and prices
cannot separate a rename from a hidden reuse, so a mismatch is excluded
and the plausible renames (ATI, CCE, CLF, CNX, DD, FOX, FOXA, OI, PCG) go
with them: keeping a fabricated history is worse than dropping a
legitimate one. The 32 are listed with their removed and current names in
sprints/E2/PROBES.md. F2.6b records this and passes; the security-master
fix that would repair rather than drop them is in docs/open_items.md.

## 2026-09-10: F2.3 stands after the horizon-aligned re-test

Decision. F2.3 keeps its recorded fail. F2.3b, a new criterion with the
same 60 percent bar and forecast and target matched on both sides, also
fails. EWMA(0.97) stays the production estimator.

Old value: F2.3 GARCH win share 46.7 percent of 45 names, EWMA(0.94) 36.4
percent of 514 names, verdict fail.
New value: after the C1 exclusions, GARCH 44.4 percent of 45 names,
EWMA(0.94) 35.4 percent of 483 names, verdict fail. F2.3b: horizon 1,
GARCH 46.7, EWMA(0.94) 35.4; horizon 21, GARCH 55.6, EWMA(0.94) 19.9.

Reason. The fail contradicted the daily-vol literature, so it was treated
as a hypothesis. The diagnostic rules out the obvious explanations: QLIKE
targets the same day's squared return, every estimator is one step ahead,
and the arch fit scales returns by 100 with the variance divided back, 47
of 60 fits converging. Counting name-days instead of names, EWMA(0.94)
wins on 51.6 percent of 242,126 name-days, so the name-level fail comes
from a few names where one day is badly mispriced and QLIKE is unbounded.
The 2020 window the brief asked about is not in the sample, which starts
2024-09-03. GARCH does improve to 55.6 percent once its multi-step
dynamics are used, which is the mechanism the hypothesis predicted, but
that is short of 60 and far short of the 70 that would reopen the choice.

## 2026-09-10: the momentum book's idio share is not 9.4 percent

Decision. The deliverable reports three measurements instead of one. No
criterion is added: the C4 check passes, and the correction is a claim
change rather than a test.

Old value: the momentum long/short seed book is 90.6 percent idiosyncratic
(factor share 0.0939).
New value: factor share 0.8919 with the portfolio regression betas and all
six factors in the covariance, 0.1459 with MOM removed, 0.0939 with
name-level TS betas and last-month weights, and 0.5564 of daily variance
explained by the regression (R squared).

Reason. The required check passes: the book's MOM loading is +0.2897 with
a Newey-West t statistic of 29.09, so it genuinely is a momentum position.
But measuring the factor share three ways shows the 0.0939 is an artifact
of treating the residual covariance as diagonal and using static
name-level betas. With residuals assumed uncorrelated, a book of 192
long/short names looks almost risk-free specifically because its residual
co-movement is thrown away. The book is mostly a momentum factor
exposure. The realized residual covariance that would fix this belongs to
E3, which owns the cross-sectional risk model, and is recorded in
docs/open_items.md.

## 2026-09-10: four current constituents were renames, not reused symbols

Decision. The C6 review restores three of the 36 reused symbols to the
estimation panel with their history truncated, and leaves the rest
dropped. New criterion F2.6c records the outcome and passes. F2.6b keeps
its text, threshold and verdict and is re-measured.

Old value: 36 reused symbols, all 36 dropped by the build, F2.6b
dropped_by_build listing 36 tickers, truncated list empty, no F2.6c.
Current-constituent coverage of returns.parquet 499 of 503 (99.20%).

New value: 36 reused symbols, 33 dropped and 3 kept. FOX kept from
2019-03-13, FOXA from 2019-03-12, PCG from 2022-10-03. F2.6b
dropped_by_build lists 33 tickers and records the three restorations.
F2.6c: 502 of 503 covered (99.80%) against the brief's bar of 501 of 503
(99.602%), one name missing (DD).

Reason. A reused symbol that is a current constituent, or that has an
added row for the same ticker dated after its removal, has a second name
to compare with the yfinance holder. Where the two names match, the symbol
was renamed rather than taken over, so the history belongs to the company
in the index and only its start date needs fixing. FOX and FOXA are the
share classes spun out of 21st Century Fox in March 2019 and PCG is the
utility readmitted in October 2022. DD stays out because "DuPont" against
"DuPont de Nemours, Inc." scores 0.33, below the 0.5 bar; a subset-style
matcher would keep it but would also re-score F2.6b's stored 93 matches
and 244 unverified names without new evidence, so the matcher is
unchanged. The three restorations are why F2.6b's leak check now treats a
name the review kept as expected rather than as a failed exclusion;
without that change F2.6b would fail on the three names F2.6c puts back.

## 2026-09-10: E1 restated a second time, and F2.3b's baseline moves

Decision. E1's criteria are re-measured on the panel with the three
restored names. No criterion text, threshold or verdict changes.

Old value: F1.3 0.95655, F1.5 fraction recovered 0.44789, F1.5 naive minus
point-in-time 365.81 bp/yr, naive minus FF market 377.20 bp/yr,
point-in-time minus FF market 9.36 bp/yr. E2 side: F2.1 0.92389, F2.2
mean pairwise 0.015362, F2.4 mean bias 1.022108, F2.5 Newey-West share
0.963208, F2.3b trailing 63d baseline win share 0.366776 at horizon 1 and
0.307566 at horizon 21.

New value: F1.3 0.95636, F1.5 fraction recovered 0.44789, F1.5 naive minus
point-in-time 365.10 bp/yr, naive minus FF market 375.37 bp/yr,
point-in-time minus FF market 8.24 bp/yr. E2 side: F2.1 0.924361, F2.2
mean pairwise 0.015618, F2.4 mean bias 1.022533 with every year moving in
the fourth decimal, F2.5 Newey-West share 0.963376, F2.3b trailing 63d
baseline win share 0.366612 at horizon 1 and 0.307692 at horizon 21.

Reason. Restoring three names changes the universe return and the
estimation panel, so both sprints' criteria move together. The movements
are small, a few basis points on E1 and under a tenth of a percent on
each E2 number, which is the scale expected from adding 3 names to a
500-name universe. The GARCH and EWMA win shares themselves do not move;
only the trailing baseline they are measured against does, and no verdict
changes anywhere. The E1 revisions history now carries three entries, one
per data hash, including the intermediate build (6d24107521893114) that
was made before the add-row filter in the review was fixed and that
changed nothing. That entry is kept rather than deleted because the chain
of data hashes is the record.
