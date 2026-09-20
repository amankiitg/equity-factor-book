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

Superseded on its root cause by the C8 entry further down: the primary
reason the 0.0939 is wrong is that static full-sample betas cannot measure
a dynamically sorted portfolio's exposure, and the residual co-movement is
the second reason rather than the first. The values below stand as
recorded.

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

## 2026-09-10: the GARCH sample was chosen by ticker order, and it mattered

Decision. The GARCH evaluation moves from the first 60 names of the sorted
universe to a seeded random sample of 100 names with full coverage over the
out-of-sample window. New criterion F2.3c records it and fails. F2.3 and
F2.3b keep their text, thresholds and verdicts and are re-measured.

Old value: F2.3 GARCH win share 44.4 percent of 45 names, EWMA(0.94) 35.4
percent of 483 names, paired sample of 37 names where GARCH 40.5 percent
and EWMA(0.94) 27.0 percent. F2.3b horizon 1 GARCH 46.7 percent, horizon 21
GARCH 55.6 percent, 47 of 60 fits converging and 13 not.

New value: seed 20260910, sample of 100 drawn from the 599 names with full
coverage, 98 fits converging and 2 not (LW, RDDT). F2.3 GARCH 58.2 percent
of 98 names, EWMA(0.94) unchanged at 35.4 percent of 483, paired sample of
80 names where GARCH 53.8 percent and EWMA(0.94) 36.3 percent. F2.3b
horizon 1 GARCH 61.2 percent, horizon 21 GARCH 49.0 percent. F2.3c fails:
GARCH clears 60 percent at horizon 1 but EWMA(0.94) is at 35.4 and 19.9.

Reason. The alphabetical head of a sorted ticker list is the names starting
with A and B, not a sample. GARCH's measured win share moves from 46.7 to
61.2 percent at horizon 1 and from 55.6 to 49.0 percent at horizon 21 on
the same data with a different set of names, which is the size of the
effect the old sample was carrying. EWMA(0.94) is far below the bar on
every sample, so no verdict changes and no production choice changes; the
sample the number came from was simply not defensible, and now it is
recorded with its seed, its eligible universe and its non-converged names.

## 2026-09-10: the trailing-wins volatility result depends on the window

Decision. No new criterion. The window comparison the close-out brief asked
for is stored in data/eval/vol_window_dependence.parquet and stated in the
deliverable, because it changes how F2.3's fail should be read.

Old value: no window comparison existed. F2.3 reported EWMA(0.94) losing to
trailing 252d for 64.6 percent of names on the two-year out-of-sample
window and that was the end of it.

New value: on the same two-year window, name level, EWMA(0.94) beats
trailing for 35.4 percent of 483 names and EWMA(0.97) for 52.0 percent.
Over the full history from MODEL_START, name level, EWMA(0.94) beats
trailing for 74.3 percent of 506 names and EWMA(0.97) for 86.8 percent. By
name-day over the full history, EWMA(0.97) wins 56.9 percent of 1,948,463
observations, 56.7 percent with 2020 removed, and 60.5 percent inside 2020.

Reason. The brief asked whether the trailing-wins result is a property of
the window, and it is. Trailing 252d beats EWMA(0.97) for just under half
the names in the last two years and loses to it for almost seven names in
eight over sixteen years. 2020 is not the driver: excluding it moves the
pooled day-level share by 0.2 points. F2.3 keeps its fail because the
criterion is written on the out-of-sample window, and the deliverable now
states the window dependence explicitly rather than leaving the fail to
read as a statement about the estimator in general.

## 2026-09-10: the momentum exposure has to be measured at the rebalance

Decision. No new criterion. C4's check passes and this replaces the way the
book's exposure and factor share are measured, because the static one
cannot measure a book that re-sorts every month. The root cause of the C4
finding reads: static full-sample betas cannot measure a dynamically sorted
portfolio's exposure; conditional exposures (rolling betas now, descriptor
exposures in E3) are the primary fix, residual co-movement the secondary
one. The C4 entry above is superseded on its root cause by this one, and
docs/open_items.md is rewritten with the same ordering. The values C4
recorded stay on the record above, uncorrected.

Old value: the book's MOM exposure was read off one number, the regression
loading of its return series, +0.2885 with a Newey-West t statistic of
29.10, beside a factor share of 0.0968 from full-sample name-level betas and
last-month weights. No exposure at a rebalance was ever measured, and the
diagonal model's bias statistic was reported only for the equal-weight book
(F2.4, 1.0225 on a 63-day window).

New value: over 195 rebalances from 2010-07-30 to 2026-09-03, the MOM
exposure from weights held and 252-day name-level betas dated at the
rebalance averages +0.0698 and ranges from -0.3322 to +0.3905, positive at
73.9 percent of rebalances. The static full-sample aggregate with the last
month's weights is -0.0162. The factor share from rolling betas averages
0.7390 over the same rebalances, against 0.0968 static. The momentum book's
bias statistic, realized 21-day forward vol over predicted vol by calendar
year, averages 1.8544 over 193 month ends and runs from 1.1063 in 2012 to
2.9259 in 2026, with 2020 at 2.4560; every year exceeds 1.0, against 1.0225
for the equal-weight book. Both series are stored, in
data/eval/momentum_exposure_rolling.parquet and
data/portfolios/seed_mom_ls_risk_21.parquet.

Reason. The static aggregate reports essentially zero momentum exposure for
a book that is long the winners and short the losers by construction and
whose return series loads 0.2885 on MOM at t 29.10. It does that because it
combines this month's weights with a beta fitted across sixteen years of a
book that changes every month, so the two never meet on the same date. The
same fault makes the static factor share 0.0968 where the conditional one
is 0.7390. Separately, the diagonal model's predicted vol for the book is
about half its realized vol in every year of the sample, which says the
diagonal residual assumption and the static exposure together are
understating a long/short book's risk by a factor of two, while the
equal-weight book is calibrated to within 2 percent. The primary fix is
conditional exposure, which rolling betas give now and E3's descriptor
exposures give properly, and the residual covariance is the second fix
rather than the first.

## 2026-09-10: C4's prose numbers moved with the C6 panel

Decision. The C4 paragraph in docs/research/E2_exposure_study.md, its
Sizing bullet, and the open item that quoted them were updated to the
artifact's current values. No criterion is involved and no verdict changed.

Old value: MOM loading 0.2897 with t 29.09; factor shares 0.8919 with the
regression betas and all six factors, 0.1459 with MOM removed, 0.0939 with
name-level betas and last-month weights; regression R squared 0.5564.

New value: MOM loading 0.2885 with t 29.10; factor shares 0.8906, 0.1462 and
0.0968; regression R squared 0.5581. All read from
data/eval/momentum_exposure.parquet.

Reason. C6 restored FOX, FOXA and PCG to the estimation panel, which
re-fitted the loadings and moved every one of these numbers in its fourth
decimal. They are prose numbers in a document, not stored criteria, so
nothing was re-scored; they were simply stale against the artifact, and a
deliverable that quotes an artifact has to quote the artifact. The C4
entry above this one records the values as they stood when it was written,
and they stay there.

## 2026-09-10: a NaN was reading as a changed number

Decision. The change detection in sprints/*/RESULTS.json now compares the
serialized form of a measurement instead of the objects, so a rebuild on
unchanged data reports nothing moved. No criterion, threshold or number
changes.

Old value: F2.3b was flagged as changed in two consecutive E2 rebuilds
whose stored numbers are identical, because its stored per-year block
contains a NaN for a calendar year with no observations and NaN is not
equal to itself.

New value: a rebuild of the same data reports zero changed criteria and
appends no history entry. Verified by rebuilding twice: data hash
51f0faa935cb57e8 both times, five history entries both times, n_changed 0.

Reason. The flag exists so a reader can see which numbers moved, and a flag
that fires on every run for a criterion that did not move makes the whole
record useless. The comparison now treats two NaNs as the same number,
which is what they mean here: the year had no data. The one history entry
already written with the false positive (data hash 51f0faa9) keeps it,
because the history is append only, and the values it records are identical
either way.

## 2026-09-10: final rebuild, hashes, and the criteria list

Decision. The third close-out pass is closed. make rebuild-e2 runs twice with
the same result, every artifact is versioned, and the deliverable ends with
every criterion and its verdict.

Verified values. data/VERSION.json data_hash
51f0faa935cb57e8e9f11bf620e5f551f69ca50b415f12112f880f32b3393692 over 29
artifacts; models/registry.json carries the same artifacts_hash; the E2
results file carries the same data hash. The E1 results file carries its own
E1 only hash, 050f2b4531540bbcc6142f64fef7d1aa7f124a10c4c124dc34747ebd5206e6ad,
because an E1 rebuild hashes the E1 artifacts, and its history holds the
three hashes that pass went through: d64ce6a7, 6d241075 and 050f2b45. The
sprint has 13 criteria, 9 passing and 4 failing: F2.3, F2.3b, F2.3c and
F2.6. 215 tests pass.

Reason. The close-out brief asks for the rebuild, the refreshed hashes, the
full test suite and one line listing every criterion with its verdict, and
this is that record. A second rebuild on the same data produced the same
data hash, appended no history entry and reported zero changed criteria,
which is the proof that the numbers in the deliverable can be re-derived
rather than trusted.

## 2026-09-11: the D1 rolling-beta panel read a shape the build never writes

Decision. dashboard/tabs/d01_exposures.py now pivots beta_history.parquet
from its long form before drawing the rolling beta chart. No data artifact
changes, so no hash moves.

Old value: beta_overlay() looked for (method, ticker) column levels, which
beta_history.parquet does not have: the artifact is written long, one row
per (date, method, ticker). The lookup found no columns, so the D1 panel
drew an empty chart with an empty legend while every other D1 panel
worked.

New value: beta_overlay() returns the three method columns for a ticker
from the long artifact. On JPM it returns 201 rows over raw, vasicek and
blume, asserted in tests/test_dashboard_d1.py, which also keeps the wide
form working for callers that pass it.

Reason. This was found while writing the E2 walkthrough section that maps
every D1 panel to the parquet columns it reads. The map made the mismatch
visible: the artifact has method as a column, the panel treated it as a
column level. The check in the walkthrough now executes every D1 panel
builder against the current artifacts and fails if a read comes back
empty, so the same defect cannot return unnoticed.

## 2026-09-11: the E2 walkthrough is rebuilt against the close-out data

Decision. notebooks/E2_walkthrough.ipynb is regenerated from scratch
against data hash 51f0faa935cb57e8, executed, rendered to
notebooks/E2_walkthrough.html, and linked from the Methodology tab as
before. It replaces the C1 to C4 version.

Old value: the previous walkthrough reproduced C1 to C4 against the
pre-close-out data and cited the numbers as they stood then.

New value: twelve sections covering the three research questions, the
by-hand derivations on AAPL, XOM and JPM, the full volatility arc through
F2.3, F2.3b and F2.3c, the exposure-timing result from C8, the data
integrity trail, all thirteen criteria, the dashboard D1 column map, the
nine tables the deliverable cites, what E3 inherits, and the credit port
note. 135 numeric checks run inside the notebook, every one asserting a
printed value against its artifact, and five more run after execution in
tests/test_e2_walkthrough_notebook.py.

Reason. The brief for this notebook is that no figure is typed by hand.
That is now mechanical rather than a promise: the closing cell collects
every stored value from sprints/E1/RESULTS.json and sprints/E2/RESULTS.json
into a forbidden-literal set (212 entries) and asserts none of them appears
in any code cell, and the post-execution test asserts that the full
precision form of every stored value appears in the printed output. If C6
had moved F1.3 again, the notebook would have failed at the assert rather
than reported a stale figure.

## 2026-09-17: the shares history is as filed, and it starts in late 2015

Decision. E3 reads share counts from the vendor's share history
(get_shares_full), dates each row at its filing date, and uses the last
observation dated at or before t-1, so a count is never used before it was
filed. Market cap is close x shares and carries a per-row look_ahead flag
that is true wherever the count is a backfill of the name's first filing,
because that value was not knowable on the date it is applied to. This
entry corrects the E1 statement about the same source; the E1 text is not
edited.

Old value. The ledger entry of 2026-09-10 recorded: "yfinance returns a
history for 10 of 12 sampled names but it is current-vintage data, not the
value known at each date. No artifact is built from it in E1." That was
generalised from a twelve name sample to a claim about the whole series.

New value. Measured over the panel's names (826 asked, the union of the
sector file and the panel): 773 return a history, 426,062 fetched rows of
which 52 are empty markers for names with no vendor page (DD is one). The
rows are dated at filing dates, not period ends, and the series is not
split adjusted, which is what makes it as filed rather than restated: AAPL
steps from 4,275,630,080 on 2020-08-28 to 17,102,499,840 on 2020-08-31,
exactly 4.000000x, at the 2020 4-for-1 split. 61,002 fetched rows (14.3%)
are duplicate dates with conflicting values and are dropped by keeping the
largest value on a date. 341 split-sized steps are visible across the
panel. Names with a filed count among the 502 sector-mapped names: 1 in
2013-04, 22 by 2015-09, 149 by 2015-10, 396 by 2015-11, 435 by 2015-12,
502 by 2017. 1,245,448 name-days (36% of the panel's 3,459,225) carry a
backfilled count and are flagged look_ahead.

Reason. The direction of the E1 note was wrong for the period the series
covers and right for the period it does not. The series is usable as a
point-in-time count from the date it starts, and unusable, not merely
noisy, before that. E1 is not reopened and its operative finding still
holds: no E1 artifact is built from the series. What changes is that E3
can use it from 2015-10 onward with the flag doing the work, and that the
2010 to 2015 window in Size and in the sqrt(market cap) weights is
recorded as a projection rather than presented as data.

## 2026-09-17: XS-v1 parameters fixed by the Task 0 probes

Decision. XS-v1 estimates from 2011-01-03, the first session on which at
least 300 names carry every descriptor, and its universe is the
sector-mapped panel names with a return and a complete descriptor row. The
descriptor windows, the standardisation, the orthogonalization map, the
weights, the identification constraint and the covariance half-lives are
the ones recorded in the XS-v1 registry entry. The regressand is the total
return r, because the risk-free series ends 2026-07-31.

Old value. The PRD as drafted said XS-v1 estimates from 2010-01-04 with
the first cross-section on 2010-01-05, and the Fama-MacBeth subperiods
started at 2010.

New value. Momentum is the binding warm-up: the 12-1 window needs 231
observations ending at t-21, so no name has momentum on 2010-12-31 and
252 sessions sit below the 300-name floor. The first complete cross-section
is 2011-01-03, and the subperiods become 2011-01-03 to 2015-12-31,
2016-01-01 to 2020-12-31, 2021-01-01 to 2026-09-03. The cross-section then
holds 428 to 497 names and is never below the floor again. Liquidity is the
second tightest window, at 425 of 428 names in 2010 and 499 of 501 in 2026.
The sector file binds the universe: 502 names, of which 41.9% of the 2010
index by name and 8.85% by market cap sit outside the file, falling to
4.8% by name and 0.24% by cap in 2025.

Reason. A stored threshold is set on measured data, as MODEL_START was in
E2. The 300-name floor was met in 2010 on price coverage alone; with the
descriptor set attached, the first qualifying session is a year later, and
recording 2010 would have meant publishing a cross-section of zero rows for
a year or silently shortening a descriptor window.

## 2026-09-17: the XS-v1 design carries 17 estimated columns, not 18

Decision. The published XS-v1 factor set has 18 factors: seven styles and
eleven sector factors. The estimated design has 17 columns: the seven style
columns and ten sector dummies, with Real Estate (code 60) as the reference
sector and no dummy of its own. Its factor return is derived from the
identification constraint, and the cap-weighted mean of the sector block is
moved into the market factor when the factor returns are reported.

Old value. The first build estimated all eleven sector dummies from a design
that also contained the market constant column, and solved the system with a
pseudo-inverse. The factor-mimicking portfolio identity X' w_FMP = e_k then
failed badly: the largest absolute deviation from the unit vector was far
above the criterion's 1e-8 fail band.

New value. With the reference sector dropped, X has full column rank on every
one of the 3941 days, the FMP rows satisfy the identity at 1.2426149519073615e-13,
and the identified factor returns reproduce the same fitted values to 1e-15.
The cap-weighted sector factor returns sum to 7.047314121155779e-18 on the worst
day.

Reason. A constant column plus a full set of mutually exclusive sector dummies
is exactly collinear, so the design is rank deficient by one and no
pseudo-inverse can satisfy X' w = I for every column. The criterion was right
and the parameterization was wrong, so the parameterization changed: this is a
correction to the model, not to the criterion. The reported 18-factor set is
unchanged and no criterion text was edited.

## 2026-09-17: the month-end artifacts ran on quarter ends, and the F3.6 and F3.8 windows were 47 months instead of 141

Decision. The exposure time series, the risk decomposition, the bias
statistics and the realized residual covariance are all month-end artifacts,
evaluated at every month end the model runs.

Old value. The artifact covered 63 month ends: the exposure series had 63
dates, the decomposition 62 book dates, the bias statistics 47 months per book
and the realized residual covariance 47 windows per book.

New value. The artifact covers 189 month ends: the exposure series has 189
dates, the decomposition 185 book dates, the bias statistics 141 months per
book from 2015-01-30 and the realized residual covariance 141 windows per book.
The corrected numbers are in sprints/E3/RESULTS.json with data hash
536c4c71c64e0ad28c9c1009bbb9caa18377173249652baff00256fc84c32204.

Reason. The builder computed one date list at quarter frequency for the
factor-mimicking weight sample and then reused that same list for the exposure,
decomposition, bias and residual covariance artifacts, so the month-end
artifacts silently carried quarter ends. The coverage was not wrong, it was
thin, and thin coverage understated every window count in F3.6 and F3.8. The
fix keeps the quarter-end sample for the FMP weights, where a sampled set of
days is the intent, and gives the month-end artifacts their own list. The
verdicts did not change, but both the numbers and the window counts did, so
they are recorded as a revision rather than as a silent edit.

## 2026-09-17: the market-only R squared is zero by construction, not a diagnostic

Decision. F3.1 stores the by-year, by-sector and block R squared diagnostics
that the sprint's standing instruction B asks for, computed whether or not the
average clears its bar.

Old value. The first diagnostics stored a single "market factor alone" R
squared, and it came back as zero.

New value. The market factor is the constant column, so a model containing only
the market factor predicts the cap-weighted mean return and explains none of the
within-day dispersion: the market-only R squared is zero by construction on
every day. Two informative comparisons replace it: the sector block alone
averages 0.192787 and the style block alone averages 0.200683, against 0.3294501878861149
for the full 18-factor set.

Reason. A statistic that is zero by algebra should not be reported as though it
were a measurement of the descriptors, because a reader would read it as
evidence that the market factor explains nothing rather than as evidence that
the market factor is the intercept. Both substitute statistics are measured on
the same days and the same names as the full model.

## 2026-09-17: XS-v1 regresses the total return, and the market factor is a total-return factor

Decision. The regressand is the panel's total return r. The market factor is
therefore a total-return factor, the premia are total-return premia, and F3.4
compares the model's market factor against Mkt-RF plus RF, the FF total return.

Old value. The PRD draft assumed the academic convention of regressing the
excess return r minus rf.

New value. The stored risk-free series ends 2026-07-31 (factors_ff.parquet,
4169 rows) while the panel's total return runs to 2026-09-03, so an excess
regressand would truncate the model by five weeks and would make the
cross-section of the final month unusable. The stored market correlation goes
from an expected 0.9563597974375629 for the excess counterpart to 0.9889255744977894
for the total-return factor on the 3917-day overlap. The sprint's standing
instruction C prices the choice directly: the Market factor estimated on total
returns and on excess returns is printed side by side in sprints/E3/PROBES.md
with its correlation on the overlap. Because the market factor is the intercept
of a design that contains a constant column, subtracting a common risk-free
rate on a day moves the intercept and leaves every other coefficient untouched,
so the gap between the two series is the risk-free rate itself.

Reason. A five-week truncation of the sample is a bigger error than the
difference between a total-return and an excess factor, and the difference can
be measured rather than assumed. The measurement is stored so an E4 or E5
comparison against an excess-return model has the conversion in hand.

## 2026-09-17: the shift test runs the other way, which is what makes the lag load bearing

Decision. Every XS-v1 descriptor is dated t-1 and is computed from data through
t-1, so the model fits the design dated t-1 against the return r_t. The sprint
prints the shift test both ways: the same returns explained by the design dated
t-1 and by the design dated t, on the same names, so the only difference is the
vintage of the design.

Old value. The PRD's design rule pre-registered the direction: "a shift test
proves that replacing X_{t-1} with X_t reduces the cross-sectional R squared".
That is the opposite of what the artifacts show.

New value. Over 3940 pairs of consecutive cross-sections, the lagged design
explains 0.329462 of the daily cross-sectional dispersion of r_t and the design
dated t explains 0.364005, so the later design explains 3.45 percentage points
more rather than less. Both numbers are printed by
notebooks/E3_walkthrough.ipynb, section 4, and the lagged number reproduces the
stored mean R squared of 0.3294501878861149 to 1e-5, which is the check that
the build really fits the t-1 design.

Reason. Replacing X_{t-1} with X_t cannot lower the R squared, because the
t-dated size descriptor is the log of market cap at t and market cap at t is
the t-1 market cap times one plus r_t, so the dated-t design contains the
variable being explained on both sides of the regression; the dated-t reversal
and momentum windows contain the day being explained for the same reason. The
3.45 points are therefore a measurement of the same-day information that the
t-1 rule removes, and they are the reason the rule exists rather than evidence
against it. The pre-registration is recorded as wrong about the sign, the
decision it was attached to (use the t-1 design) is unchanged, and no criterion
text was edited. The rule was wrong on one detail and the walkthrough now
prints the exact windows: the momentum column is 231 sessions, not 252, and it
ends 21 sessions before the date being explained, so momentum is the one style
whose window never contains the return.

## 2026-09-17: the exposure time series had no book label, so F3.9 quoted a blend

Decision. `data/eval/xs_exposure_timeseries.parquet` carries a `book` column,
and the F3.9 reconciliation quotes the momentum book alone.

Old value. `risk.exposure_series` returned one row per date and factor with no
book label, and the build concatenated the two books into the same frame. The
artifact therefore held 6804 rows of which 3402 were duplicates on (date,
factor): two different exposure vectors under one key. F3.9's stored mean was
computed over both books together, 0.3407061589106543 over 282 rows, and the
dashboard's exposure timing panel took the same pooled series because there was
no label to filter on.

New value. The artifact holds 6804 rows with no duplicate keys, F3.9 quotes the
momentum book over its own 141 rebalances at a mean of 0.7214982201158555 and a
range of 0.23195900889357352 to 1.091340001486862, and the dashboard panel
filters on the book it is asked for. The equal-weight book's own momentum
exposure averages -0.038468 and its market exposure 0.761138, against the
momentum book's 0.719794 and -0.000998, so the two books are not two versions
of one exposure profile and the pooled number described neither.

Reason. The criterion text, quoted from the roadmap, says "the XS-v1 exposure
time series for the momentum book". A frame in which two books are
indistinguishable cannot support that sentence, and the error was found while
splitting the bias by the book's own exposure for the E3 close-out, which is
exactly the kind of question the label is needed for. This is a correction to
an artifact schema and to a stored number, so it is recorded as a revision in
sprints/E3/RESULTS.json, which reports n_changed 1 against the previous run.

## 2026-09-17: the share-history cache was narrowed to the sector file, so the survivor weight share came back zero

Decision. The E3 build fetches the share history for the union of the sector
file and the panel, which is what `python -m efb.probes --e3-shares-all` does
and what the Task 0 probe record describes: 826 names asked, 773 returning a
history.

Old value. The build asked for the 502 names in the sector file only and wrote
the result back to the cache, so the cached history held the sector names
alone. With no share count for a name there is no market capitalisation, and
the survivor-only table's `share_outside_mcap` came back as 0.0 for every year
while `share_outside` stayed correct, because the name count does not need a
market cap and the weight share does.

New value. The cache holds the union again (503 names before the probe run, 826
after it) and
`data/eval/xs_survivor_restriction.parquet` reproduces the Task 0 probe record
exactly: 0.419391 by name and 0.088511 by market cap in 2010, 0.048094 and
0.002385 in 2025, 0.013707 and 0.000444 in the partial 2026.

Reason. The zero was arithmetically correct and factually wrong, which is the
failure mode a stored table is supposed to prevent: nothing raised, the column
was present, and only the probe record caught it. The narrower fetch also
clobbered a cache that the probe had filled with the wider union, so a rebuild
silently narrowed what was known about the past. The union is now what the
build asks for, and the survivor table is stored so that a future regression
shows up as a changed number rather than as a plausible zero.

## 2026-09-20: the Ledoit-Wolf shrinkage intensity was missing its 1/T

Decision. `efb/cov.py` divides the Ledoit-Wolf plug-in intensity by the number
of days in the window, so `delta = (pi - rho) / (gamma * T)`, and a test pins
both the corrected value and the uncorrected ratio it replaced. No stored
criterion moves: the covariance laboratory is new in E4 and this is its first
run.

Old value. `delta = (pi - rho) / gamma`, clipped into [0, 1]. On the 504-day
windows the uncorrected ratio is roughly T times too large, so the intensity
hit the clip at exactly 1.0000 in every one of the 175 rebalances: the
estimator silently became its own target, and the Ledoit-Wolf row of the
horse race was byte for byte the constant-correlation row, mean realized
volatility 0.175822 for both and identical condition numbers.

New value. `delta` averages 0.2738 across the windows, ranging from 0.1482 to
1.0000, and Ledoit-Wolf is a genuine blend: mean realized volatility 0.103960,
between the sample covariance at 0.409593 and the constant-correlation target
at 0.175822, with a median condition number of 2785 against 2.65e6 for the
sample.

Reason. This is the fifth defect this project has found by reading an output
rather than the code that produced it, and the first in a published estimator.
The two identical rows are what exposed it: nothing raised, the table was
well formed, and every number in it was plausible. The horse race exists to
separate estimators that look alike on paper, so an estimator that collapses
onto another one in every window is exactly the failure the comparison is
built to catch. The ledger records it because a reader of the E4 memo has to
know that the Ledoit-Wolf comparisons in the first draft of the table were the
target's numbers wearing the estimator's name.

## 2026-09-20: realized volatility has two definitions and only one is authoritative

Decision. The F3.6 realized volatility, the standard deviation of the book's own
daily return series over the forward horizon times `sqrt(252)`, is the only
realized volatility any EFB table may quote. The covariance form,
`sqrt(w' S w)` on the names with complete forward data, survives as a labelled
diagnostic column and is never presented as the bias statistic's denominator.

Old value. The Task 3 diagnostics computed realized volatility as
`sqrt(252) * sqrt(w' S w)` on the names complete over the forward window and
reported 0.064068 for the momentum book in the high exposure tercile, against
the stored 0.027775 for the same months.

New value. Every measurement that talks about realized volatility reads
`realized_vol_ann` from `data/eval/xs_bias.parquet`, which is the F3.6
definition: 0.027775 in the high tercile, 0.030110 in the middle and 0.049093
in the low. The covariance form is stored beside it as
`book_realized_vol_covariance_form`, and a test asserts the two disagree in
level so a reader cannot silently swap them.

Reason. Both numbers are arithmetically correct and they answer different
questions. The stored one measures the dispersion of the book's return series,
which is what a bias statistic needs and what E2 and E3 have used since F2.4.
The covariance form measures one instant of the book's risk against a
particular covariance estimate. Publishing the second where the first belongs
would have moved the momentum book's high tercile bias from 0.52 to 1.2 and
turned a failing criterion into a passing one, with no error anywhere in the
arithmetic. This is the sixth defect this project has found by reading an output
rather than the code behind it, and the reason line is the same as the
Ledoit-Wolf entry: the table was well formed and every number in it was
plausible.

## 2026-09-20: F4.1 was written for an estimator this sprint did not specify

Decision. F4.1 is recorded as a fail at 0.7970 with its mechanism, the
correlation PCA is not changed to make it pass, and a covariance PCA is
registered separately as PCA-v1c because every other estimator in the lab works
on a covariance. The full-sample number 0.9450 is stored beside the fail.

Old value. The pre-registered criterion reads "First principal component vs the
market factor: correlation above 0.95", written before the standardization
choice existed.

New value. PCA-v1 standardizes each name to unit variance, so its first
principal component is the equal-weight common factor: 0.9891 against the
equal-weight mean return and 0.7970 against the cap-weighted market factor over
the 504-day window, and 0.9450 against the market over the full 4192-day
sample. PCA-v1c, on the covariance of raw returns, puts its PC1 at 0.9306
against the market and 0.9433 against the equal-weight mean, and its factor
count of 16 is above the F4.2 band because it is a different object with a
different edge; F4.2 governs PCA-v1 and its count of 13.

Reason. A threshold that assumes a first principal component tracking the
cap-weighted market is a threshold for a covariance PCA, and this sprint
specified a correlation PCA in its own PRD. Recording the fail is the point of
pre-registering it: the criterion did its job by catching that the specification
and the threshold were written by different people at different times. The
alternative, quietly switching to a covariance PCA and reporting a pass, would
have hidden a real difference between two estimators that the horse race now
separates.

## 2026-09-20: the horse race swallowed an unknown estimator and produced no rows

Decision. `efb/cov.py` catches only `numpy.linalg.LinAlgError` when an
estimator fails on a window, so a configuration error surfaces instead of
silently removing a row, and `parameter_count` knows every name in
`ESTIMATORS`. A test asserts that every name in the dispatch table has a
parameter count.

Old value. `except (np.linalg.LinAlgError, ValueError): continue`. PCA-v1c was
added to the estimator tuple and to the dispatch without a parameter count, so
it raised `ValueError: unknown estimator pca_v1c` on every one of the 175
windows and the horse race printed a well formed eight row table with no
indication that a ninth estimator had been requested.

New value. The nine estimator race prints nine rows: clip 0.086042, pca_v1
0.086674, pca_v1c 0.087318, xs_v1 0.088007, ledoit_wolf 0.094102, ts_v1
0.150948, constant_correlation 0.160254, sample 0.280404, ewma 0.298494, in
medians over 175 windows.

Reason. The table was well formed and every number in it was plausible, which is
the same reason line as the Ledoit-Wolf entry and the same failure mode: a bare
except around a dispatch table means any future estimator added with a typo
produces no rows in silence. The two defects are recorded together because they
are one habit, an output that looks finished being trusted without a check that
every part asked for is present.

## 2026-09-20: the survivor restriction was named but never applied

Decision. `efb/survivor.py`'s `style_only` takes the universe as an argument and
restricts both the cross-sectional standardization and the daily cross-section
to it, and `run` refuses to compare two universes whose mean cross-section size
is identical. The measured summary carries each universe's mean names per date.

Old value. The first run printed a table in which every style correlated exactly
1.000000, both premia agreed to six decimals, both t statistics agreed to six
decimals, and both R squared readings were 0.133530. The mean names per date
were 825 and 502 by construction, and the fit never saw the difference: the
label `mapped_502` was passed to a function that had no universe parameter, so
the 502 name restriction was computed in `restricted_names` and then used
nowhere.

New value. The two universes now differ as they should. Size correlates 0.577780
between them, liquidity 0.625560, residual volatility 0.893133, and the stable
four read market 0.997009, beta 0.988961, momentum 0.982820, reversal 0.980173.
The size premium deepens: -0.000032 on the panel against -0.000173 on the
mapped names, with a t statistic of -0.073681 against -0.577971. Mean
cross-sectional R squared rises from 0.133530 to 0.142526 when the excluded
names are dropped, and mean specific variance falls from 2.9172148211e-04 to
2.2854110873e-04. Mean names per date are 569.2 and 467.9, below the panel's 825
and the mapped 502 because the descriptor history is not complete for every
name.

Reason. The table was well formed and every number in it was plausible, which is
the same reason line as the Ledoit-Wolf and swallowed-exception entries, and the
third instance of the same habit: an output that looks finished is trusted
without a check that the two things it claims to compare are actually two
things. The identical correlations were the only evidence, and they were
identical to a degree no two different universes can produce. Every measurement
in this sprint now stores the sample size it was computed on alongside the
result.
