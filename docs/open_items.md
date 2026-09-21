# Open items

Append-only list of issues that a later sprint must resolve before a
stated milestone. Each item names the owning sprint and the blocker it
removes. No work is scheduled for these in the sprint that records them.

## 2026-09-10: E11 requires an ongoing constituent source before the book runs

Owner: E11. The Wikipedia changes table is pinned to revision 1368675864
and freezes the universe at 2026-08-05 (see the Hygiene Ledger and
sprints/E1/PROBES.md). A paper-traded book cannot run on a frozen
universe; E11 must secure an ongoing constituent source (a vendor feed
or a maintained open source) and re-run the universe reconstruction
before the book goes live. Recorded in Sprint E2, no work in E2.

## 2026-09-10: price vendor history needs security identity, found by F2.6

Owner: E1 follow-up, blocking any use of the pre-2017 panel for names
whose symbols were reused. Four of the 858 tickers in the price universe
(CPWR, EP, MI, POM) have reused symbols: each was a real S&P 500 member
that was acquired or delisted, and the symbol was later taken by an
unrelated listing. The vendor splices both histories into one series with
no split to explain the jump, so adjusted-close ratios above 5x appear
with no corporate action behind them. The real history of the original
issuer, Compuware, El Paso, Marshall & Ilsley and Pepco, is absent from
the panel.

E2 drops these four names from the estimation panel and records the
exclusion in the TS-v1 registry entry, but dropping is a mitigation:
every portfolio that used those names as point-in-time members during
2010 to 2016 (the equal-weight seed book is the visible case, with POM
held for 1,627 member days) loses that exposure instead of regaining the
correct one. The fix is a security-identity source so that prices attach
to an issuer rather than to a symbol: FIGI or CRSP PERMNO via a vendor
with delisting-aware history. Until then, no result in EFB may claim
point-in-time universe coverage for 2010 to 2016 without this caveat.
Recorded in Sprint E2 as the failing criterion F2.6.

## 2026-09-10: the risk model needs conditional exposures first, a residual covariance second

Owner: E3. Found by close-out task C4, reordered by close-out task C8. The
portfolio risk decomposition uses sigma_p^2 = w' B F B' w + w' D w with D
diagonal, and B taken from one full-sample fit. For the equal-weight seed
book that is harmless, because the factor share is 99.2 percent either way
and its bias statistic is 1.0225.

For the sector-neutral momentum long/short seed book the root cause is the
static exposure, not the diagonal: static full-sample betas cannot measure
a dynamically sorted portfolio's exposure, so conditional exposures
(rolling betas now, descriptor exposures in E3) are the primary fix, and
residual co-movement is the secondary one. C8 shows both halves. Measured
against the weights actually held and 252-day name-level betas dated at
each rebalance, the book's MOM exposure averages +0.0698 over 195
rebalances and ranges from -0.3322 to +0.3905, while the static full-sample
aggregate with the last month's weights reports -0.0162, essentially no
exposure at all, on a book whose own return series loads +0.2885 on MOM
with a t statistic of 29.10. The same construction puts the factor share at
0.7390 on average, against 0.0968 for the static decomposition with
last-month weights, and the diagonal model's bias statistic for the book is
1.8544 by year (21-day forward window), between 1.1063 and 2.9259, while
the equal-weight book is at 1.0225.

E3 should price the book from descriptor exposures recomputed at each
rebalance, so the book's factor position is measured when it is held, and
then replace the diagonal D with w' Sigma_resid w from a cross-sectional
residual covariance. Until both are in place, no EFB result may quote a
single idio share for a long/short book without the measurement method
attached, and no long/short risk number may be published from the static
decomposition.

## 2026-09-10: the 32 dropped symbols need identity repair, not exclusion

Owner: E1 follow-up. Close-out C1 dropped 36 reused symbols. Four show the
splice in the prices; the other 32 have a name mismatch and clean prices,
so the member's own history is missing from the vendor data entirely. Nine
of the 32 look like real renames of the same issuer (ATI, CCE, CLF, CNX,
DD, FOX, FOXA, OI, PCG) and were dropped anyway, because a rename and a
hidden reuse cannot be told apart from names and prices alone. Repairing
rather than dropping them needs a security-identity source (FIGI or CRSP
PERMNO). The full list with removed and current names is in
sprints/E2/PROBES.md and the decision is in the Hygiene Ledger.

## 2026-09-17: the XS-v1 cross-section is survivors only, 41.9% of the 2010 index by name

Owner: E4. The sector dummies restrict the cross-sectional model to the 502
names the sector file holds, and that file is a current-member snapshot, so
the historical cross-section is entirely survivors. Measured in the E3 Task 0
probes (sprints/E3/PROBES.md): in 2010 an average of 503.9 point-in-time
members per day, of which 292.6 are in the sector file and 211.3 are not,
which is 41.9% of the index by name and 8.85% by market capitalisation. The
name share decays as the missing names leave (33.8% in 2015, 18.9% in 2020,
4.8% in 2025) and the cap share decays faster (5.5% in 2015, 2.0% in 2020,
0.24% in 2025), so the bias is mostly a breadth problem and a smaller weight
problem.

This is a stronger restriction than the F1.5 survivorship measurement of
365.1 bp per year on the full panel, because F1.5 is estimated from the
members the panel does hold while the sector dummies remove the members it
does not. Two consequences are recorded rather than fixed: the historical
cross-section has no non-survivors in it at all, and the sector exposures
themselves are assigned from a snapshot, so a name's 2010 sector is its
2026 sector.

E3 states both numbers in the research note as a limitation and does not
attempt a repair. A repair needs a point-in-time sector and constituent
source, which is the same dependency as the E11 ongoing constituent item
above, and it should be priced in E4's evaluation of the model rather than
patched inside the risk model.

## 2026-09-17: the equal-weight seed book is only 58 to 98 percent covered by the model (closed for E3, carried into E4)

Owner: E4. Found while writing the E3 risk report. The equal-weight seed book
is equal weighted over the whole panel, while the XS-v1 universe is the 502
sector-mapped names, so the weight of the book's names with no descriptor row
is 0.4172 in 2011, 0.3460 in 2015, 0.1950 in 2020 and 0.0179 in 2026. Up to
42 percent of the book's weight is therefore outside the model in the early
years, and data/eval/xs_risk_decomposition.parquet reports that weight per
date as residual_weight. The bias statistic in
data/eval/xs_bias.parquet reports zero residual weight because it reindexes
the book onto each day's cross-section before decomposing, so its comparison
of predicted against realized volatility is like-for-like on the covered part
of the book and says nothing about the uncovered part.

Closed for E3 by stating the number in docs/research/E3_risk_report.md and
keeping it beside every quoted risk figure. Carried into E4 because the fix is
the same point-in-time sector source the item above needs: until the model can
describe the whole book, the early equal-weight risk numbers are partial rather
than wrong.

## 2026-09-17: the momentum book's bias fails F3.6 in the opposite direction from the E2 prediction (open for E4)

Owner: E4. F3.6 requires a mean monthly bias inside 0.8 to 1.25 for both
books. The stored means are 0.9570097710419492 for the equal-weight book, which
is inside the band, and 0.6663870518805773 for the momentum book, which is
below it: the XS-v1 model over-predicts the momentum book's risk by about 1.5
times on average. The E2 measurement of the same book pointed the other way
(21-day bias 1.8544, every year above 1.0), and the sprints/ E3 PRD therefore
pre-registered a fail in the other direction. Both numbers are stored.

The discrepancy is the model and the window, not an arithmetic error: E2
measured the bias of the book's factor exposure using TS-v1 market factor and
stock betas, while E3 prices a full XS-v1 covariance with a specific variance
term and a point-in-time factor covariance. E4 should decide which construction
is the sizing model and price the other as a sensitivity, which is the
conditional covariance work below.

## 2026-09-20: E4 restates three open items and closes none

Survivor restriction, restated with the Task 4 numbers. The XS-v1 universe is
the 502 sector-mapped names out of an 825-name panel, and the missing 323 are
the small, illiquid end of the cross-section. It is not a caveat: dropping them
correlates the size factor return at 0.577780 between the two universes and
liquidity at 0.625560, against 0.98 and above for market, beta, momentum and
reversal, deepens the size premium from -0.000032 to -0.000173, raises mean
cross-sectional R squared from 0.133530 to 0.142526, and the excluded names ran
0.199281 annualized volatility against 0.166796 and earned 0.020141 a year less
over 2010 to 2016. Still open, and still a data problem: only a point-in-time
sector source closes it, no model version does.

Equal-weight seed book coverage, restated but not closed. Task 0b found no
point-in-time GICS source, and the same coverage gap is what caps the early
equal-weight risk numbers. The restatement above is the measurement of it.

Momentum bias, restated with the Task 3 verdict and the E3 ordering reversed.
E3 ordered a conditional exposure fix first and a residual covariance second.
Task 3 measured both and reverses that order: the momentum book's
realized-to-predicted bias falls from 0.8960 to 0.5841 and 0.5191 across
exposure terciles while its predicted volatility is flat, the realized
covariance between its factor and specific components is negative in the high
tercile where a diagonal asserts independence, the top five residual directions
carry 0.553 to 0.577 of the book's specific variance, and adding three residual
principal components to a frozen XS-v1 is worth 3.9 points of held-out R
squared. The half-life sweep is measured and rejected at 0.003, so the bias is
not a calibration knob and a later reader should not retry it.

New, opened by this sprint: the covariance horse race's rebalance grid. The
stored race has 175 windows and `make rebuild-e4` versions it but does not
rebuild it, because the grid was chosen interactively in Task 2 and is not yet
derived from an artifact. Rebuilding it before that is fixed would produce a
second race rather than reproduce the stored one. F4.3 is scored from the
stored artifact meanwhile.

Process decision, for every sprint from E5 on: a research deliverable carries a
test of the `tests/test_e4_memo.py` kind, asserting that every headline number
in the deliverable matches a stored value. Prose and measurement cannot be
allowed to drift apart, and three of this sprint's defects were found by
exactly that kind of check rather than by reading code.

## 2026-09-20: the E4 covariance race (closed on the grid, open on the row)

The grid is closed. E5 Task 0a derived the 175 rebalance dates from the
descriptor and specific-variance artifacts and reproduced the published
medians for all eight window-only estimators exactly, so the race no longer
depends on an interactive choice.

Still open, and new in E5: the XS-v1 row. The published row was produced by a
live per-date model call and the artifact was not tracked in git, so it cannot
be recovered after this sprint's first rebuild overwrote it. Reconstructing it
from `fmp_weights` and the stored factor returns raises `LinAlgError:
Eigenvalues did not converge` inside `condition_number` on all 175 windows,
which `efb/cov.py` catches and drops, and the cause is the scale of
`fmp_weights` relative to the diagonal rather than the covariance. The next
session should fix the design's scale first, then rebuild
`data/eval/cov_horse_race.parquet` with nine estimators and compare the XS-v1
median against the 0.088007 that F4.3 stores.

## 2026-09-20: E5 close-out

The race-grid item is closed: E5 Task 0a derived the grid from the artifacts
and the eight window-only estimators reproduce the published medians exactly;
the XS-v1 row stays closed under F5.0b and is not re-opened here.

New and carried into E6, all stored:

1. F5.1 fails: no version is inside 0.9 to 1.1 on every family, every
   version overshoots the long-only family, so no model is fully calibrated.
2. The sqrt(21) scaled forecast and the directly estimated 21-day model
   disagree per family (`data/eval/e5_horizon.parquet`), so the horizon
   question is open.
3. The survivor-only universe caveat is inherited by every E5 number.
4. The champion XS-v1 carries a stored stress haircut of 1.8471 until a
   stress model replaces it.

## 2026-09-21: E6 close-out

Closed in E6, stored in `data/hedge/` and `sprints/E6/RESULTS.json`:

1. F6.1 passes: the exact in-model FMP hedge drives the worst absolute
   post-hedge exposure to 5.8e-15 and the idio share after the hedge to
   100.0%, at the cost of trading 461.9 names on average.
2. F6.2 passes: the ETF minimum-variance hedge removes 97.85% of the
   long-only seed book's factor variance; the momentum book keeps 42.81%.
3. F6.3 passes: the hedged momentum long/short book realizes a beta to
   Mkt-RF of -0.0272 over 2018 to 2026 against -0.0495 unhedged.
4. F6.4 stores every headline under XS-v1 and XS-v2; every difference is
   0.0 because the hedges use only the shared factor block. The sensitivity
   to the provisional champion is therefore zero, and that is the finding.

New and carried into E7, all stored:

1. The as-stored quarterly capped FMP weights are not a hedge: their worst
   residual exposure is 0.7552 (reversal, 2024-11-29, momentum book), worse
   than the unhedged 0.7169 on that date, because the design drifts after
   the stamp and the caps break exact spanning. The E6 recommendation is
   never to flatten exposures with the capped FMPs; E7's neutralization
   machinery must use the exact projection or accept the drift explicitly.
2. The long-only seed book's realized return series is valid only from
   2025-10 under daily weights, because its stored rows hold every member on
   every day, including names before their prices exist, and the E5
   missing-data semantics make those days missing. The momentum book's
   series is complete and carries F6.3.
3. The provisional E9 cost constants (5 bps per turnover unit, 2% per year
   borrow) are used by every stored cost number in E6 and are replaced by
   the E9 transaction cost model when it exists.
4. The instrument set grows from 12 to 14 as XLRE and XLC gain history; the
   per-date count is stored, and instruments without estimable history are
   recorded as missing, never filled.

## 2026-09-21: E7 close-out

All six signals are NULL under the RG-Signal checklist; the stored deciding
numbers are in `sprints/E7/RG_SIGNAL.json`. F7.1 passes (the lagged
construction probe with the PIT property pinned by perturbation tests),
F7.2 fails (neutral momentum IC -0.0107, t -1.55), F7.3 passes (111 ledger
rows, below-hurdle signals labeled NULL), F7.4 passes (both models stored).

Carried into E8, all stored:

1. The construction machinery runs on synthetic alpha with a known IC, per
   the roadmap's null-signal fallback.
2. The alpha conversion contract is stored per signal in
   `data/alpha/{signal}/alpha.parquet` with columns date, ticker, alpha,
   alpha_xs_v2, ic, sigma_idio_xs_v1, sigma_idio_xs_v2, z, kappa.
3. The fast-decay finding: post-earnings drift's edge dies within one day
   of its lag probe; its IC is announcement-adjacent information, not a
   leak, and any E8 use must respect the one-session tradability lag.
4. The short interest panel covers only 24 settlement dates from 2018 to
   2026 with gaps; a fuller history needs the FINRA files rather than the
   API endpoint.

## 2026-09-21: E8 Task 0c, short interest is NULL for lack of history

Short interest is NULL in the RG-Signal gate for lack of history, not for
lack of signal: the panel covers only 24 settlement dates from 2018 to
2026, its neutral out-of-sample t is 2.1035 and its break-even cost is
21.02 bp per rebalance. It is the one signal to revisit with a longer
panel (the FINRA files rather than the API endpoint), and it stays carried
into a later sprint rather than re-scored here.

## 2026-09-21: E8 Task 0d, evidence policy: fetched inputs only, large files on LFS

Sizes measured: .git 162 MB, committed evidence 81 MB before the change,
whole tracked tree 89 MB. From this task on the evidence snapshot covers
only the fetched inputs that make rebuild cannot regenerate
(data/raw/*.parquet plus registry and VERSION); the derived artifacts
(eval, hedge, alpha, models, processed) are rebuilt deterministically by
make rebuild and are no longer snapshotted. The previous per-sprint
snapshot directories were removed from the tree; git history retains them.

The new snapshot is 109.54 MB compressed, above the 100 MB line, so it is
committed through Git LFS (pattern evidence/data/raw/*.gz). Cost: about
0.11 GB of the free GitHub LFS quota (1 GB storage, 1 GB per month
bandwidth). The E4 descriptor probe cache (228 MB) stays skipped by the
size cap; it is a cache rebuild regenerates from the snapshotted prices
and factors.
