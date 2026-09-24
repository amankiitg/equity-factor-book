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

## 2026-09-20: the 0.9 style-correlation stop threshold is withdrawn

Decision. The threshold that halted Task 4 is withdrawn, and it is not a
criterion: it was never registered in the roadmap's criteria table and it enters
no RESULTS.json. It was written by hand during Task 4 as a guard against a
specification difference between the two runs and it was the wrong instrument
for the question the task asks. The sprint keeps STOP CONDITION 3, on F4.2, as
its only numeric stop.

Reason. The measurement it halted is a genuine universe effect, not a code
difference, and the pattern is the signature of one: size at 0.577780 and
liquidity at 0.625560 fall between the universes while market, beta, momentum
and reversal stay above 0.98, and residual volatility sits between the two
groups at 0.893133. The 323 excluded names are the small, illiquid, failed end
of the cross-section, so removing them truncates the dispersion that the size
and liquidity descriptors are built to measure. A style correlation of 0.58 on
size is what a real restriction looks like, which is the opposite of what the
threshold assumed it meant.

What it did catch, and why it was worth writing. The first Task 4 run returned a
correlation of exactly 1.000000 on all seven styles, and the threshold was the
reason anyone looked. The defect underneath it is recorded in the entry above:
`style_only` never received the universe. A guard written to catch one failure
caught a different one, and the guard itself was then retired rather than
reworded, because a threshold that has fired once and been explained away is no
longer a threshold.

Also in this entry. The ledger's first version of the survivor measurement said
the size premium flips sign. It does not: both readings are negative and the
mapped universe makes the discount four times deeper. The test written from the
stored artifact caught the misreading before the commit, which is the check this
project relies on rather than re-reading prose.

## 2026-09-20: research deliverables carry a traceability test from E5 on

Decision. Every research deliverable from E5 onward ships with a test that
asserts each headline number in the document matches a stored value, as
`tests/test_e4_memo.py` does for `docs/research/E4_covariance_memo.md`. The
test parses the stored files, rounds the memo's numbers to the printed
precision and fails when a number cannot be traced to an artifact.

Reason. Prose is the one artifact in this project that no assertion has ever
covered. Three of the four defects this sprint found were caught by a check on
an artifact rather than by reading code, and the memo is the place where a
wrong number would do the most damage because it is the document a reader
quotes. The test also caught a misreading in this sprint's own ledger entry,
where the size premium was described as flipping sign when both readings are
negative: the check ran before the commit, which is the sequence worth keeping.

## 2026-09-20: the E4 covariance race artifact was overwritten and is not tracked

Decision. `data/eval/cov_horse_race.parquet` is now a build input and is named
in `E4_ARTIFACTS`, and every artifact this project treats as evidence must be
reproducible from a derivation rather than from an interactive run. Until the
XS-v1 row can be reconstructed, the derived race is stored beside the published
one as `data/eval/cov_horse_race_derived_grid.parquet` and the comparison is
stored in `data/eval/e5_race_grid.json`.

Old value. The published race: 175 windows, 9 estimators, 1575 rows, XS-v1
median 0.088007 winning 59 of 175 windows, which is the row F4.3 was scored on
and the row the E4 memo's optimizer recommendation rests on.

New value. The derived race: the same 175 dates and the same medians for the
eight estimators that need only the window (clip 0.086042, constant_correlation
0.160254, ewma 0.298494, ledoit_wolf 0.094102, pca_v1 0.086674, pca_v1c
0.087318, sample 0.280404, ts_v1 0.150948, every ratio exactly 1.000000), and
no XS-v1 row, because every reconstructed window fails in `condition_number`
with `Eigenvalues did not converge` and `efb/cov.py` catches that error by
design.

Reason. E5 Task 0a was told to derive the grid from an artifact and rebuild the
race from it. The derivation succeeded and is exact, and the rebuild destroyed
the evidence it was meant to reproduce, because the artifact is gitignored
(`data/**/*.parquet`) and is not reproducible from any derivation yet. Two
lessons, both recorded: an artifact that a stored criterion was scored on is
evidence and needs a derivation before it is rebuilt, and an untracked,
underived artifact is one run away from being unrecoverable. The mitigation
this project already has for the general case is the content hash in
`data/VERSION.json`, which detects the change but cannot restore the file.

## 2026-09-20: evidence artifacts get a tracked snapshot (E5 R1)

Decision. Every artifact a stored criterion was scored on has a tracked,
compressed snapshot under `evidence/`, written by `efb.evidence` and verified
by `make verify-evidence`, which decompresses each snapshot, hashes it, and
compares the hash against both `evidence/MANIFEST.json` and the hash
`data/VERSION.json` records for the same artifact. The snapshot covers every
parquet under `data/eval` and `data/models/<version>/`, plus the registry and
the manifest itself.

Cost. 47 artifacts, 13.81 MB of parquet, 12.17 MB committed as gzip. Five files
are over the 4 MB cap and are listed as skipped rather than committed
(`TS-v1/beta_history`, `TS-v1/residuals`, `XS-v1/descriptors`,
`XS-v1/fmp_weights`, `XS-v1/specific_returns`, 68.7 MB together). Every skipped
file is a build product of `make rebuild-e3`, which is the distinction that
matters: the artifact E5 destroyed was not rebuildable from any derivation, and
these five are.

Reason. `data/**/*.parquet` is gitignored, so every computed artifact had the
same exposure, and E5 Task 0a demonstrated it by overwriting the E4 covariance
race, which carried the XS-v1 row that F4.3 was scored on. A content hash in
`VERSION.json` detects that a file changed and cannot bring it back. The project
has found eight defects by reading outputs; this is the first that destroyed
evidence, and the lesson is that a criterion's inputs have to be as durable as
its stored numbers.

## 2026-09-20: the evaluation engine's missing-data semantics, first draft corrected

Decision. A portfolio return is `W R'` with explicit missing-data semantics,
not IEEE arithmetic: an unpriced name contributes zero because its weight is
zero, and a held name with a stale or outlier day makes that portfolio-day
missing. The first draft multiplied the raw matrices, so `0 x NaN` poisoned
every dot product and 98.6 percent of portfolio-days silently collapsed to
NaN before the bias statistics dropped them.

Reason. The bias statistics silently drop non-finite z, so a poisoned engine
still produced a table. The corrected engine keeps 94 percent of
portfolio-days, and the excluded remainder are exactly the stale-day
exclusions the panel carries.

## 2026-09-20: E4's stored data hash survives the E5 registry append

Decision. `evaluate.e4_data_hash` reconstructs the registry as E4 left it:
the four E4-era entries, the champion flag forced false, and the E5-added
`artifacts_hash` dropped from the PCA entries' parameters.

Reason. `registry.json` is append-only but its entries gain keys in later
sprints, and E4's stored data hash covers the file's bytes as of E4 close.
Without the reconstruction, registering XS-v2 moved E4's hash; with it, the
stored hash reproduces byte-for-byte and no earlier sprint's number moves.

## 2026-09-20: F5.1 fails and the champion is declared under the session's stop list

Decision. F5.1 fails: no version lands inside 0.9 to 1.1 on every family
(every version overshoots long-only, the factor versions at about 1.105).
The failure is recorded with its mechanism and the champion rule's
arithmetic ran to its end: XS-v1, mean |bias-1| 0.0607, no tie, no
stress-regime conflict.

Reason. The PRD's stop condition 3 would halt before declaring, and this
sprint's session instruction named only the stress-regime conflict as a
stop, with every other unfavourable number recorded and the run continued.
This entry records the tension so the next sprint knows the champion was
declared with F5.1 failing, on instruction, and not hidden.

## 2026-09-21: the hedge engine applies the E5 missing-data semantics to both legs

Decision. The instrument and FMP hedge legs go through
`eval_risk._portfolio_returns` like the book leg: an unpriced name or
instrument contributes zero, a held one with a missing return makes the
day missing. The first draft used a raw matmul on the returns panel, so
NaN columns of instruments without history (XLRE before 2015, XLC before
2018) poisoned the hedge return and 57.7 percent of minimum-variance rows
went NaN.

Reason. A hedge position is a portfolio; the same 0-times-NaN defect from
E5 applies to it. The stored efficacy series changed materially after the
fix, which is exactly why the revision history in sprints/E6/RESULTS.json
keeps both measurements.

## 2026-09-21: instruments without estimable history are dropped per date, never filled

Decision. An instrument whose prices do not span the 504-session factor
window gets NaN betas and idio variance; it is excluded from the hedge on
that date, the per-date count is stored in `n_instruments`, and its stored
position is NaN rather than zero.

Reason. Filling it with zero would silently pretend the instrument could
have been traded; the count is the recorded truth that the instrument set
grows from 12 to 14 over the sample.

## 2026-09-21: the beta hedge is fitted point-in-time

Decision. The stored `h_spy_beta` in the metrics is fitted on data strictly
before the rebalance date, like the instrument regressions. The first draft
fitted it on the full sample's trailing window, which put 2025 data into a
2012 rebalance.

Reason. The realized efficacy path was already point-in-time; the metrics
column now agrees with it and the walkthrough recomputes the same number
by hand.

## 2026-09-21: the exact FMP hedge is scored, the capped stored FMPs are the basis risk

Decision. F6.1 is scored on the exact in-model FMP hedge rebuilt on the
rebalance date's own design, which drives exposures to 5.8e-15 by
construction. The as-stored quarterly capped FMP weights are stored beside
it as `exposure_after_fmp_capped` and their worst drift, 0.7552, is the
reported basis risk rather than a failed criterion.

Reason. The roadmap says to understand that the FMP hedge is exact
in-model and unusable in practice; scoring the criterion on the capped
tradeable form would have failed it for cap drift while hiding the
exactness that is the point of the exercise.

## 2026-09-21: the shift audit is the lagged-construction probe, not a pairing trick

Decision. The F7.1 audit rebuilds every signal with all inputs moved one day
back and compares the lagged IC against the original IC against r_t. The
first two drafts paired the stored signal with shifted returns; both flagged
fast-decaying honest signals (reversal, earnings drift) because their edge
genuinely dies within one day, which the pairing cannot tell apart from
same-day leakage.

Reason. The lagged reconstruction simulates data available one day earlier:
a clean signal keeps its IC (the information was already there), a leaked
signal flips or dies (the extra day carried the edge). A flagged signal that
is point-in-time by construction, pinned by the perturbation test in
tests/test_alpha.py, carries a fast-decay finding rather than a leak, and
both the flag and the PIT property are stored per signal.

## 2026-09-21: post-earnings drift is tradable only from the next session

Decision. The earnings surprise is dated at the announcement, so the signal
is shifted one session before any pairing. The first draft paired the
announcement-day surprise with the same-day return and produced an IC of
0.20 with t of 21, which was the announcement reaction, not drift.

Reason. The corrected signal's IC is 0.124 with t of 14.0, and the lag
probe shows the edge dies within the lag window: a fast-decay finding, not
a leak.

## 2026-09-21: every E7 signal is NULL and that is a successful sprint

Decision. All six signals fail the RG-Signal checklist on the stored
out-of-sample numbers; every one is labeled NULL in the ledger and the
gate. The F7.2 momentum criterion also fails: the factor-neutral momentum
IC mean is negative (-0.0107 with t -1.55) against the 0.02 threshold.

Reason. The roadmap says every signal NULL is a successful sprint and the
E8 construction machinery runs on synthetic alpha with a known IC. The
negative results are kept in full: six reports, a 111-row ledger, and the
gate JSON.

## 2026-09-21: E8 Task 0a, F7.1b records leakage in post-earnings drift

The empirical shift audit (each signal rebuilt with every input advanced
one day, paired with the same-day return) finds post-earnings drift's
after-shift IC 0.2015 with t 21.15 against 0.124 with t 14.05 before the
shift. The IC survives and grows, so under the F7.1 criterion text the
signal is leaking: its edge is announcement-day information, which the
one-session tradability lag removes. Recorded as leakage in the signal
report per the E8 Task 0a instruction. The construction probe's fast-decay
finding stands beside it. The same audit flips short-term reversal (t
-184.72, the shifted window contains the same-day return) and kills low
residual volatility and short interest; momentum and idio momentum
survive by persistence, because their windows still skip the same-day
return, and that confound is stored, not rewritten.

## 2026-09-21: E8 Task 0c, F7.2's mechanism recorded beside F4.1's

Decision. F7.2 stays a fail at -0.0107 with t -1.55, and its mechanism is
recorded the way F4.1's was: the threshold was written for a different
neutralization. Neutralizing momentum against a risk model that contains
momentum projects the signal out, so the neutralized IC is the residual
after removing the factor the signal is. The raw out-of-sample t of 3.2148
(momentum), 3.8239 (idio momentum) and 7.2700 (post-earnings drift) fall
to -1.6387, -0.5340 and 1.0344 once neutralized: the signals are the known
factors, not new information. F4.1's entry is the same pattern, a
criterion written against one object scored another, and the fail is the
record of that mismatch, never a workaround.

Reason. The F7.2 threshold (neutral momentum IC mean above 0.02 with t
above 2) is the right test only against a design that does not contain
momentum. Against the champion XS-v1 design it measures what is left after
the signal's own factor is removed, which is near zero by construction of
the signal being tested.

## 2026-09-21: E8 close-out

Construction on synthetic alpha with a known IC (rho 0.02, 0.05, 0.10, five
seeds each), a controlled experiment, never a backtest. F8.1 fails (MV
minus Procedure 6.3 is 0.0085, above 1e-6, because the standardized
specific return is orthogonal to the design only up to the sigma_idio
weighting and D is not scalar); F8.2 passes (idio share after the FMP hedge
is 1.0); F8.3 passes (max constraint violation 3.95e-09, zero solver
fallbacks); F8.4 fails (resampling dispersion 1.416 at every rho, and no
shrinkage reduces the relative dispersion because two IC-consistent draws
share only correlation rho squared); F8.5 passes (the transfer table);
F8.6 passes (the long/short per-family alternative is the champion itself,
difference zero by identity).

The headline finding: the synthetic z is i.i.d. across names, so its
breadth is the name count, and the hedged rules realize IC * sqrt(N) with a
transfer coefficient near one; the participation ratio of the
specific-return correlation matrix (N_eff 128.7 against N 456.6, mean
largest residual eigenvalue 16.5) is the return co-movement E4 measured,
not the signal breadth, and used as breadth it over-corrects.

## 2026-09-21: E9 close-out

Transaction costs and capacity. The Corwin-Schultz half-spread is 2.5 to
5.2% by size decile (smaller names wider), and the capacity curve is
negative at every AUM because the i.i.d. synthetic signal reshuffles the
book about 140% of gross each month, which at a 3% half-spread is roughly
4% of AUM per rebalance in spread cost. F9.1 fails (the net Sharpe ratio is
not monotone in AUM: the impact cost's cross-rebalance variance grows with
AUM and inflates the denominator, while the net mean is monotone with zero
violations); F9.2 fails (the turnover-penalized optimizer cuts 37.5% of
turnover with 6.5% ex-ante IR loss, short of the 50% cut); F9.3 fails (the
spread-size-rank correlation magnitude is 0.349, below 0.5, the
Corwin-Schultz noise the roadmap named); F9.4 passes by storage (the
halving AUM is NaN, undefined, at every rho and k).

The headline finding: turnover, not capacity, is the binding constraint.
A real signal with persistence would have far lower turnover and a defined
capacity; that persistence is what the next signal must demonstrate.

## 2026-09-21: E9 cost magnitude correction, the Corwin-Schultz spreads were volatility

Decision. The spread input is a size-decile schedule from 10 bp (smallest
names) to 1 bp (largest) of half-spread, stated as an assumption with a
half and double sensitivity, replacing the stored Corwin-Schultz
half-spreads of 2.5 to 5.2 percent. New criterion F9.5 stores the schedule
beside the anchor estimators it replaced, and E9 is re-run on the
corrected costs.

Old value. The Corwin-Schultz (2012) estimator, as first implemented, was
missing the overnight (gamma) adjustment from the paper, and its two-day
high-low range is dominated by intraday volatility for S&P 500 names, so
the unadjusted estimate reads about 100 times the quoted spread: 2.5 to
5.2 percent per decile, with a size-rank correlation magnitude of 0.349.
The capacity curve was negative at every AUM and the halving AUM was NaN
everywhere, which produced the headline that turnover, not AUM, is the
binding constraint.

New value. Applying the paper's overnight adjustment floors every two-day
estimate at zero (the true spread is below the estimator's resolution on
daily data), and the Abdi-Ranaldo (2017) close-high-low estimate has no
size gradient either (rank correlation 0.003). The schedule is therefore
an assumption, not a measurement, and is stated as such. On the schedule
the spread cost of a 140% turnover rebalance is about 0.07% of AUM, net
Sharpe is monotone in AUM (the violation count moves from 206 to 0), and
the halving AUM is defined for rho 0.05 (100 million dollars at k 0.5) and
rho 0.1 (464 million dollars), still undefined for rho 0.02 because that
book's IC of 0.019 cannot pay the fixed spread and commission at any size.
Both data hashes are on the record in the revisions block of
sprints/E9/RESULTS.json.

Reason. A cost model built on a spread estimate 100 times the quoted
spread makes the capacity question about the spread, when the question is
the impact cost. The estimator comparison is stored in
data/costs/spread_probe.parquet so a later reader can see the failure mode
rather than trust the schedule.

## 2026-09-21: F8.1b, the APM central identity holds in the D^-1 metric

Decision. New criterion F8.1b neutralizes the synthetic alpha in the
D^-1 metric, alpha_perp = alpha - X (X' D^-1 X)^-1 X' D^-1 alpha, and
stores the max absolute weight difference among unconstrained
mean-variance, the proportional rule and Procedure 6.3. F8.1 keeps its
verdict and its number.

Old value. F8.1 stored 0.0085 as the max absolute weight difference
between unconstrained mean-variance and Procedure 6.3, above the 1e-6 the
identity would require.

New value. With alpha GLS-neutralized in the D^-1 metric the Woodbury
correction vanishes exactly and the three constructions are the same
vector to 3.5e-17 (max over the sample).

Reason. The synthetic z is standardized in the equal-weight (sqrt(mcap)
analog) metric, not the D^-1 metric the identity needs, so the 0.0085 gap
is a metric mismatch, not a violation of the identity. F8.1b is the check
that separates the two.

## 2026-09-21: F8.4's 1.416 is sqrt(2), recorded beside F4.1 and F7.2

Decision. Recorded, not fixed. The resampling dispersion of 1.416 is the
relative distance between two IC-consistent redraws of the alpha.

Reason. Two redraws share only correlation rho squared with the original
(0.0004 to 0.01 at rho 0.02 to 0.10), so they are nearly independent and
their relative distance is sqrt(2 * (1 - rho squared)), which is 1.416 at
rho 0.02 and 1.411 at rho 0.10. Getting the dispersion below the 0.30
threshold needs rho above 0.977. Shrinkage multiplies the alpha by a
scalar, and a scalar cancels in a relative distance, so no ridge lambda on
the grid can reduce the dispersion. The 30% threshold was written for a
signal near rho 0.98, not for the experiment's realistic ICs, the same
category of pre-registered threshold error as F4.1 and F7.2.

## 2026-09-21: F7.1c, post-earnings drift's h1 edge is the after-close announcement reaction

Decision. New criterion F7.1c lags each signal one extra day and
re-measures its IC against the same-day return. The direction is opposite
to F7.1b and is the one that discriminates: F7.1b proves the harness sees
injected leakage, F7.1c asks whether the real signals are clean.

New value. Momentum moves 0.0151 to 0.0152 and idio momentum 0.0121 to
0.0123 under the extra lag, so their edges are persistent; short-term
reversal decays 0.0120 to 0.0077 but keeps significance. Post-earnings
drift collapses from an IC of 0.1240 with t 14.05 to 0.0073 with t 0.77:
its horizon-1 edge is the after-close announcement reaction captured
close-to-close, not a persistent drift.

Reason. F7.1b alone cannot say whether a surviving signal is leaking or
persistent, because the forward shift and the extra lag probe different
things. The collapse under the extra lag is the specific evidence that
the edge lives in the announcement-day return, which the one-session lag
exists to remove.

## 2026-09-21: free daily OHLC data cannot measure spreads for S&P 500 names

Decision. F9.3 is recorded as not evaluable on the corrected run. The
criterion asks whether the spread estimate falls with size, but the cost
input is now an assumed size-decile schedule that makes that ordering true
by construction, so the criterion can neither pass nor fail on a
measurement.

Reason. Both free estimators fail on liquid names. The corrected
overnight-adjusted Corwin-Schultz floors every two-day estimate at zero
(the spread is below the estimator's resolution on daily high-low data),
and the Abdi-Ranaldo close-high-low estimate has no size gradient (rank
correlation 0.003). The raw Corwin-Schultz measures volatility, not the
spread (2.5 to 5.2 percent against a quoted range of single-digit basis
points). The consequence is recorded, not patched: every cost number in
this project is an assumption with a sensitivity band, never a
measurement, until a source that actually observes spreads is available.
That changes for credit, where trade prints make spreads measurable, which
is tracked in the open items.

## 2026-09-21: E10 close-out

Dynamic risk allocation and loss management. The design book is rho 0.02,
phi 0.95, seed 1 on corrected costs, net annualized Sharpe 0.978, the
(rho, phi, seed) closest to 1.0. Kelly: full 9.78 times, half 4.89 times,
growth 0.478 at full and 0.359 at half, growth loss 0.036 when the Sharpe
is overstated by one standard error. F10.1 fails: the simulated median
maximum drawdown is 14.0% against the Magdon-Ismail Brownian median of
3.5%, so the constant-vol Brownian benchmark understates the book's
drawdowns by a factor of five (fat tails and vol clustering). F10.2
passes: the drawdown stop does not improve Sharpe on the i.i.d. control
(mean difference -0.49), and on the real books it helps the momentum seed
book by 0.23 while hurting the design book by 0.39, reported either way.
F10.3 fails: vol targeting reduces the dispersion of realized annual vol
by only 12%, below the 40% threshold, because the trailing 12-window
estimate lags and is noisy at monthly frequency.

The practitioner numbers that carry into E11: the chosen fraction is half
Kelly, the vol-targeting rule is scale_t = 10% / trailing vol clipped at
3 times, and the risk budget is written per VIX regime (the middle tercile
carries the deepest drawdown of 0.1309).


## 2026-09-22: E10 corrections after the review

The 2026-09-21 review found nine defects in E10. The corrections, recorded
here because each one changes what a stored number or a stored sentence
means:

- ln(2) sigma^2 / (2 mu) is the stationary drawdown median of an
  infinite-horizon Brownian motion, not a maximum-drawdown quantity. That
  is why F10.1's benchmark and its simulation were never measuring the
  same thing. The horizon-matched expected maximum drawdown (14.5 years,
  the positive-drift Magdon-Ismail value) is 0.1994, stored as F10.1b.
- The F10.1 sign mix (a signed simulated median differenced against a
  magnitude analytical value) overstated the relative gap as 4.9598; the
  like-with-like value is 2.9598. F10.1 stays a fail, the criterion text
  is unchanged, and both values stay on the record through revisions.
- The bootstrap is i.i.d., not block. The Gaussian control (i.i.d.
  Gaussian paths at the book's own moments) draws down deeper than the
  bootstrap, so the gap is not fat tails or volatility clustering: it is
  the benchmark mismatch above.
- The original drawdown stop freezes wealth and peak while flat, so its
  -5% re-entry test is unreachable. A re-entering stop that tracks the
  unstopped equity curve is stored as F10.2b, and on i.i.d. control paths
  it still does not improve Sharpe.
- The E5 missing-data semantics delete 95% of a 500-name equal-weight
  book's days: seed_ew rests on 207 of 4193 sessions (2025-10-28 to
  2026-08-27), so any statistic computed on it under those semantics is a
  ten-month statistic. seed_mom_ls rests on 4091 of 4092 sessions.
- F10.3's dispersion was computed on 15 raw years against 14 targeted
  years. On the aligned 14-year set the reduction is 0.1508, not 0.1220.
  The verdict is unchanged.
- F10.3's recorded mechanism blamed the estimator. It is not the
  estimator: a daily-return volatility estimate reaches at most 0.2042
  (my implementation measures 0.2063 at the 21-day window), still below
  the 40% bar. The true mechanism is that this book's year-to-year
  realized-volatility dispersion is not forecastable at this horizon, and
  the 40% bar was written for a higher-frequency object than a monthly
  book.

## 2026-09-22: iShares IVV holdings endpoint recorded as a failing source

Decision. The iShares IVV holdings CSV endpoint is recorded as a failing
source and is not built on. The SPY holdings file from SSGA is the
constituent and identity source instead.

Reason. The documented CSV endpoint returns HTTP 200 with about 2.25 MB of
HTML, the product page behind an investor-type disclaimer and bot
protection; the content-type header still says text/csv. Seeding a cookie
jar from the product page does not clear it. `raise_for_status()` passes
on this, which is why the SPY fetcher validates the parsed payload shape,
not the status code, and why a test feeds the stored IVV HTML to the SPY
parser and asserts it raises.

## 2026-09-22: SPY xlsx is read without openpyxl

Decision. The SSGA SPY holdings xlsx is parsed through its zip and sheet
XML with the standard library, not through pandas and openpyxl.

Reason. openpyxl is not a project dependency, and adding it plus its
transitive packages for one flat, shared-string sheet is not warranted.
The file is a single worksheet of eight columns whose text cells are all
shared strings, which the zipfile and ElementTree reader recovers
directly; the parser asserts the header row and the row count so a changed
layout fails loudly rather than parsing silently.

## 2026-09-22: the SPY archive joins the versioned and evidence sets

Decision. Each dated file under data/raw/spy_holdings/ is registered in
data/VERSION.json and snapshotted by efb.evidence under
evidence/data/raw/spy_holdings/, the same mechanism that protects the
other fetched inputs make rebuild cannot regenerate. No .gitignore
negation is added for the directory.

Reason. SSGA serves only the current holdings file, so a dated archive
file that is not kept today is unrecoverable. The raw parquet stays
gitignored by design, because the project's evidence policy protects
non-regenerable inputs through the tracked compressed snapshot, not by
tracking the data parquet itself. The snapshot .gz sits under evidence/,
which is tracked and not gitignored, so no negation is required. Cost:
one file is about 34 KB (24 KB compressed), so a year of daily files grows
the committed snapshot by about 6 MB, well inside the size line the E8
Task 0d open item records.

## 2026-09-22: F10.3b drops years whose two sides carry different counts

Decision. F10.3b's dispersion is now computed only over years where the
raw and the targeted side carry the same number of monthly observations;
the dropped years are stored beside the reduction.

Reason. E10-F6 fixed the year-level version of the defect (different year
sets on the two sides) but left the within-year version: the daily
estimator's warmup consumes part of 2012 on the targeted side only, so an
annual volatility built from four monthly returns was being compared with
one built from eleven. The fix drops 2012 at every window and 2013 at the
252-day window; the daily-21 reduction moves from 0.206317 to 0.286842,
still far below the 40% bar, so F10.3b keeps its pass verdict.


## 2026-09-22: the impact sigma is daily, the annualization hypothesis is refuted

Decision. The impact leg's sigma stays daily. No fix is applied to the cost
model and nothing cascades into E9 or E10: the 13.18 bp impact stands as
written.

Reason. The slip hypothesis was that _trade_cost's sigma is annualized, which
would inflate the impact leg by sqrt(252) and cascade a re-run of the E9 cost
model and the E10 reconciliation. Tested and refuted. _cost_decomposition
takes sigma = sqrt(specific_var), and specific_var is the EWMA of squared
daily specific returns, so it is a daily standard deviation. Worked example:
MU's daily specific_return std is 0.02217 and its sqrt(specific_var) is
0.03020, both daily; MRNA's are 0.05984 and 0.19050. A 32,631 MU trade
against a 852,351,955 ADV at that sigma costs 0.934 bp of the trade. The
book's total impact is 13.18 bp under the daily sigma; annualizing it would
give 13.18 x 15.874 = 209.3 bp, and the full-sample daily std (the E9
convention) would give 15.01 bp, or 238.3 bp annualized. The reported 13.18
bp matches the daily sigma, so the sigma is daily and the cost is correct.


## 2026-09-22: E11-F1: whole-share quantization breaches the establishment bar

Decision. The establishment quantization is recorded as a finding, E11-F1,
continuing the finding sequence from E10-F27. It is a breach, not a mechanical
cost, and it stays recorded as a finding until the minimum-position parameter
closes it.

Reason. Whole-share rounding of the smallest-weight tail breaches both clauses
of the establishment bar as written. The measured gross weight error is 0.0539,
which is 5.39% of NAV and, against a gross of 0.9685, 5.56% of gross notional,
the first clause. On the name-count clause, 23 of 256 long names and 13 of 243
short names round to zero shares, each leg past its share of the bar. The
mechanism is the whole-share quantization step itself: a target whose notional
is below half a share prices to zero shares, so the error concentrates in the
smallest-weight tail instead of spreading across the book.


## 2026-09-22: Guard 1's position cap is re-derived, not rescaled

Decision. Guard 1's NAV-relative position cap moves from 0.40 to 0.10 of NAV,
re-derived from the actual target-weight distribution of the 2026-09-21
proposal. A ten-times order on the largest name now trips it.

Reason. The 0.40 cap was rescaled, not re-derived: the largest target in the
proposal is MU at 0.0326 of NAV, so ten times the largest legitimate position
is 0.326 and still cleared 0.40. The distribution is max |weight| 0.0326, q99
0.0119, q95 0.0053 across 499 names. A cap of 0.10 sits clear of the largest
legitimate target with 3.1x headroom and still trips a 10x fat-finger on the
largest name (0.326 > 0.10). The boundary and the 10x trip are pinned by tests.


## 2026-09-22: E5 RESULTS.json data_hash bump is accounted for

Decision. The six-line change to sprints/E5/RESULTS.json is a data_hash bump
carried by the registry edit (adding XS-v1 live.min_position_dollars), and it
is recorded through the revisions block with both hashes. No criterion,
verdict, threshold or stored number moved, so per STANDARDS rule 22 the task
continues rather than halting.

Reason. e5_data_hash hashes models/registry.json directly, so the registry
edit moved it from 210769d6... to a4c40c67... . The diff is the top-level
data_hash, revisions.previous_data_hash (null -> 210769d6...) and
revisions.data_hash (210769d6... -> a4c40c67...), and nothing else. n_changed
stays 0. The E4 hash is unaffected because _registry_as_of_e4 strips the live
key, and the E5 walkthrough was re-executed so its printed hash matches.

## 2026-09-23: a number that is an identity, and E11-F8 as a candidate fourth instance

Decision. The pattern is recorded as a class. E11-F8 is recorded as a
candidate member, pending measurement. The class is a number that reads as a
result but is fixed by the construction of the object it is computed on, so it
carries no information about the data. There are three recorded instances.
F8.4's 1.416 is sqrt(2), because a scalar cancels in a relative distance.
F7.2's neutralized IC is near zero, because neutralizing a signal against a
design that contains it projects the signal out. F4.1's 0.7970 is the looser
form of the same error: a threshold written for one estimator was scored on
another.

The candidate is E11-F8's pre-winsorization beta column in
live/construction_table.parquet. The report attributes its fall from 0.105
raw beta to 0.046 to Vasicek shrinkage. But a shrinkage with one common
weight k is affine, and with net dollar zero it multiplies the book's exposure
by k without explaining any of it. The ratio of pre-winsorization to raw beta
is 0.41 to 0.45 on six of seven construction rows (0.36 on top-N 150), which
is what a near-common k produces. The algebra is the same as F8.4's: a common
scalar carries no information.

Reason. If E11-F8 confirms, four occurrences make this a class rather than a
coincidence, and a future reader should check for it. Before reading a number
as a result, ask whether it would take the same value for any data, or scale
with a constant fixed upstream. E11-F8 is recorded as a candidate rather than a
member because the project writes down a mechanism only after a measurement
supports it. The measurement is the raw-units decomposition in task
e11-two-part-fixed-point-then-pick, which regresses raw beta on each pipeline
stage and reads the book's exposure to the residual. That task appends a
follow-up entry either way. If confirmed, the residual exposure at the Vasicek
stage is near zero and E11-F8 joins the class. If refuted, the entry records
the measured share that shrinkage explains.


## 2026-09-23: E11-F8 measured, and the candidate identity is refuted

Decision. The raw-units decomposition the candidate entry asked for is now
measured, and it refutes the identity hypothesis. The regression of the raw
beta on the Vasicek stage (cap-weighted, as XS-v1 fits) leaves a residual
exposure of 0.0555 at min $1,500, not near zero: the Vasicek shrinkage is not
a common scalar, because its weight is name-specific through the standard
error, so it removes about half the raw beta rather than rescaling it.

The measured split of the 0.1050 raw beta at min $1,500: the shrinkage step
accounts for 0.1050 - 0.0555 = 0.0495 (47 percent), the 3-MAD clip accounts
for 0.1081 - 0.0555 = 0.0526 (50 percent), and standardization and
orthogonalization contribute zero to three decimals, as the affine algebra
predicted. The finished descriptor leaves the full 0.1050 as residual, because
the hedge zeroes it. The full 499-name book carries 0.0936 raw beta, so most of
the residual is the signal's own tilt, and the drop adds about 0.011.

Reason. E11-F8 does not join F4.1, F7.2 and F8.4. The pre-winsorization column
was not an identity: the shrinkage does real, name-specific work, and the clip
does the rest. The numbers are read from live/construction_table.parquet, the
residual-exposure columns of the min_position_1500 and full_book_499 rows.
