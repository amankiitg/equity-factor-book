# Credit Port Design Note

Sprint E13, 2026-09-27. Document only: no code, no live data, no new panels.

Written for the risk system lead at a multi-strategy fixed income fund. The
reading assumption is institutional: TRACE prints, an index membership archive
with daily constituent files, a rating and sector reference set, dealer quotes
through a live feed, and a credit risk system of record that already produces
spreads, durations and DTS. The question this note answers is the one your desk
will ask first: which parts of the Equity Factor Book transfer directly to
corporate credit, which need re-specifying, and which break.

Every EFB number below is read from a stored file. The citation form is
`EFB: <path>` and the path is the file the number was read from. Appendix A
lists the sources in one place, and `tests/test_e13_design_note.py` asserts that
every cited path exists in the repository and that every module of the
repository appears in the map in Section 13.

## 1. The premise: the mathematics is agnostic, the data is not

The Book's own summary of this is in the roadmap's E13 founding sentence: "the
linear algebra does not care about the asset class; the data does"
(`EFB: docs/roadmap_v2.md`).

What is agnostic, and why:

- **The cross-sectional weighted least squares fit.** Regressing a return column
  on a design matrix, weighted by the square root of a size measure, is the same
  operation on bonds. EFB fits it with 18 factors: 17 estimated columns (7 styles
  and 10 sector dummies) against a market column
  (`EFB: data/models/registry.json`).
- **The factor mimicking portfolios.** The identity `X (X'WX)^-1 X'W r = r` holds
  regardless of what the columns mean; EFB measures its own error at a maximum
  absolute 1.2426149519073615e-13 over 1,032,745 factor-days
  (`EFB: sprints/E3/RESULTS.json`, F3.2).
- **The risk decomposition.** `Sigma = X F X' + D`, the factor and specific split,
  the marginal contributions, and the identity that the contributions sum to the
  book's volatility to 6.245004513516506e-17
  (`EFB: sprints/E3/RESULTS.json`, F3.5).
- **The hedge algebra.** An exact hedge solves `X'X` for the exposure the book
  carries and subtracts `X (X'X)^-1 X'w`; EFB drives the worst post-hedge
  exposure to 5.8323571666685226e-15 (`EFB: sprints/E6/RESULTS.json`, F6.1). The
  same algebra hedges a spread exposure with CDX legs.
- **The attribution identity.** Holdings-based attribution closes
  return = factor + specific + cost, an identity that does not know the asset
  class.
- **The evaluation discipline.** Pre-registered criteria, a multiple-testing
  ledger (111 runs, 70 NULL labels, `EFB: sprints/E7/RESULTS.json`, F7.3),
  bias bands and a champion rule. None of that is equity-specific, and it is the
  part a credit desk is most likely to be missing.

What is not agnostic:

| Equity assumption | In credit |
| --- | --- |
| A daily price exists for every name in the cross-section | Most bonds do not trade on most days; there is a print or a mark, not a price |
| The price is a transaction | A dealer mark is a quote, and a stale TRACE print is history |
| A ticker identifies the issuer | A CUSIP identifies an issue; issuers have many, and CUSIPs change on exchange |
| The cross-section is the whole market | The tradable universe depends on your inventory, your index mandate or both |
| Return is price plus dividend | Total return needs coupon, accrued interest, and a rates benchmark to be comparable |
| Specific risk is a number per name | Specific risk has two levels, issuer and bond, plus recovery and jump-to-default |
| A missing name is a gap in the matrix | A missing name may be a default, a call, an exchange or a data gap, and only one of those is a return |
| Volatility is the risk | Spread duration times spread change (DTS) is the risk; a rates move is a separate exposure |

The last row is the one that most often gets a credit port wrong, and it is the
reason Section 8 is the longest section in this note.

## 2. The credit X matrix, schematic for three bonds

Rows are bonds, columns are exposures, one date. This is the credit counterpart
of the matrix EFB's `build_cross_section` assembles
(`EFB: efb/models/fundamental.py`), with the same shape: a market column, style
columns, and dummy blocks.

| column | ALT2 3.5% 2031 | DELL 5.3% 2029 | F 4.9% 2030 | units | note |
| --- | --- | --- | --- | --- | --- |
| constant (market) | 1.00 | 1.00 | 1.00 | | unchanged from EFB, a credit market factor replaces the equity one |
| DTS (spread duration x OAS) | 4.62 | 3.85 | 6.10 | years x bp | the core exposure; see Section 8 |
| spread level (OAS) | 128 | 96 | 231 | bp | a level, not a return; signed so wider is positive |
| spread momentum (1m, 6m) | -6, +21 | -3, +9 | +14, -38 | bp change | sign convention is a decision, see Section 8 |
| spread volatility (residual) | 2.1 | 1.7 | 3.4 | bp/day | the residual of a spread AR(1), not a price vol |
| rating dummies (AAA to CCC, 8 columns) | 0,0,0,1,0,0,0,0 | 0,0,0,0,1,0,0,0 | 0,0,0,0,0,1,0,0 | 0/1 | BBB, A and BB here |
| sector dummies (GICS or your own, 10 columns) | 0,0,0,1,0,0,0,0,0,0 | 0,0,0,0,0,1,0,0,0,0 | 0,0,0,0,0,0,0,1,0,0 | 0/1 | Technology, Consumer Discretionary here |
| seniority and structure (3 columns) | 1,0,0 | 1,0,0 | 0,1,0 | 0/1 | senior unsecured, subordinated, secured |
| issue size (log notional outstanding) | 21.4 | 22.1 | 23.6 | log $m | the equity size descriptor, re-based |
| issuer size (log total debt) | 23.9 | 24.2 | 26.0 | log $m | a second size loading; an issuer with many bonds moves the whole block |
| age (years since issue) | 3.1 | 6.4 | 2.2 | years | the on-the-run premium is real and is not in equities |
| liquidity (TRACE volume, trades, days since last trade) | 41.2, 63, 1 | 8.9, 22, 4 | 55.1, 71, 1 | $m, count, days | three columns, not one |
| return column | +0.31 | -0.12 | +0.55 | % excess | excess over the duration-matched Treasury, Section 3 |

Four differences from the equity matrix are visible in that table alone, and
each is a decision rather than a port:

1. **Dummies outnumber styles.** Rating buckets and seniority are exposures, so
   the design has roughly 25 to 30 columns where EFB has 17. A cross-section of
   500 bonds is fine; a sector-rated bucket with four bonds in it is not, which
   is why EFB's minimum of 5 usable names per day
   (`EFB: efb/models/fundamental.py`, `standardize`) has to be raised to
   something like 15 to 25 in credit.
2. **Liquidity is not one column.** EFB's liquidity descriptor is a log mean
   dollar volume over 63 sessions, shifted one day
   (`EFB: efb/models/fundamental.py`, `raw_descriptors`). Bonds need days since
   last trade and trade count as well, because a bond can have a large print
   volume and still be untradeable.
3. **The market column means something different.** In EFB, the constant column
   plus the FMP hedge makes zero market exposure the same thing as zero net
   dollar exposure. In credit, zeroing the credit market column leaves the rates
   exposure untouched. Key-rate durations, or a separate Treasury factor block,
   are needed if "hedged" is to mean anything to a rates-aware risk manager.
4. **The return column is not in the same units as the exposures.** DTS is in
   years times basis points; an excess return is in percent. Section 3 fixes the
   units before anything is estimated.

## 3. The return column, before anything is estimated

EFB's return is `r_t = P_t/P_{t-1} - 1` on the dividend adjusted close, and the
excess series `r - rf` uses the Fama-French daily risk free rate
(`EFB: docs/research/E1_data_note.md`). Two facts about how EFB used it matter
for the port:

- **XS-v1 regresses the total return, not the excess return**, because the
  risk-free series in the vendor file ends 2026-07-31 while the panel runs to
  2026-09-03 (`EFB: sprints/E3/RESULTS.json`, F3.4 note). The equity excess
  return is therefore a diagnostic, not the dependent variable. In credit the
  benchmark is not optional: a bond's excess return over a duration-matched
  Treasury is the only column in which a spread exposure is comparable across
  issuers.
- **Interior gaps are dropped, never imputed.** EFB drops 302 interior NaN
  return days across 13 tickers (`EFB: sprints/E1/RESULTS.json`, F1.2). At
  equity density that is a rounding error. In credit, dropping every day a bond
  did not trade removes most of the panel, so the choice is between a
  last-print carry-forward with an age column (Section 12), or a monthly or
  weekly rebalance. Both are defensible; silently imputing is not, and EFB's
  ledger rule is that a gap is recorded as a gap.

The three candidate return definitions, in increasing order of what they demand
from your data:

| definition | formula | needs | breaks when |
| --- | --- | --- | --- |
| spread return | `OAS_t - OAS_{t-1}` | a clean OAS series | the OAS is a dealer consensus that moves with the mark, not the market |
| excess return over duration-matched Treasury | `r_bond - D_mod * r_Treasury(matched)` | Treasury curve and each bond's modified duration | the matched Treasury is interpolated across a kink |
| DTS-scaled excess return | excess return divided by DTS | as above plus DTS | DTS is near zero (short floaters, very short paper) |

Recommendation: estimate on the excess return, report DTS exposure beside it,
and keep the spread return as a diagnostic the way EFB kept `excess` now that
XS-v1 uses `r`.

## 4. The factor mapping table

This is the roadmap's own Appendix A mapping (`EFB: docs/roadmap_v2.md`), with a
fourth column added: what actually breaks. The roadmap marks 15 of 17 rows
unchanged; the last column is where that claim is tested, and Sections 5 to 12
give the reasons in full.

| EFB element | credit counterpart | formula status | what breaks |
| --- | --- | --- | --- |
| Return: excess over the risk-free rate | excess over a duration-matched Treasury, or spread return, or the DTS-scaled variant | unchanged after re-specifying the return column | the benchmark must be constructed per bond, not read from a file; Section 3 |
| Market factor (constant 1) | credit market factor (IG or HY index excess return), plus a rates factor or key-rate durations | unchanged | zero credit market exposure is not zero rates exposure; the equity meaning of the constant column does not carry; Section 8 |
| Size (log market cap) | issue size and issuer size, both log | unchanged | issuer size is a block loading: a bond's weight in the cross-section and its issuer's outstanding debt are different objects; Section 4 |
| Beta (to the equity market) | spread beta, or DTS | unchanged | a DTS loading is an exposure to spread change, so the covariance matrix must be a spread covariance, not a return covariance; Section 8 |
| Momentum (12-1) | spread momentum, plus issuer equity momentum | unchanged | spread momentum and equity momentum disagree in stress, and the sign convention is a choice; Section 8 |
| Residual volatility | residual spread volatility | unchanged | needs a spread time series per bond, which most illiquid bonds do not have; Section 9 |
| Liquidity (dollar volume) | TRACE volume, trade count, age, size, days since last trade | unchanged | five columns where EFB has one, and the estimator's minimum names per day rises with them; Section 2 |
| Value (book to price) | spread relative to rating and sector peers, the rich or cheap residual | re-specified descriptor | this is the only row the roadmap already marks re-specified, and it is the one where an equity style translates least directly; Section 8 |
| Sector dummies (GICS) | sector dummies plus rating buckets and seniority | unchanged, more columns | the number of columns triples, and two-way rating by sector buckets empty out; Section 2 |
| Cross-sectional WLS, FMPs, Fama-MacBeth premia | same, weighted by size or by inverse spread volatility | unchanged | weights by inverse spread volatility make the cross-section reflect trading capacity, which is not the same as weighting by size; Section 8 |
| Sigma = X F X' + D, decomposition, marginal contribution | same | unchanged | D has issuer and bond structure; a diagonal is the wrong object when one issuer has thirty bonds; Section 9 |
| Risk model evaluation, regimes | same, with regimes on credit spreads (OAS terciles) rather than VIX | unchanged, regime variable swapped | a spread regime is endogenous to the model: the spread is your dependent variable; Section 8 |
| Hedging with index and sector ETFs | CDX IG and HY, Treasury futures, LQD and HYG | unchanged, instrument set swapped | the instruments' betas to your factors are the model's weakest link; Section 10 |
| Sizing and minimum variance optimization | same, with issue-level caps and liquidity constraints | unchanged, constraints extended | issue-level caps are a new class of constraint, and a liquidity constraint needs an ADV per bond; Section 10 |
| Costs: spread and square-root impact on ADV | dealer bid-ask by rating and size, plus mark staleness | re-specified cost model | EFB's spread was an assumption, not a measurement; in credit you can measure it, which changes what you can claim; Section 11 |
| Attribution: holdings based | same, with carry and roll-down as explicit terms | unchanged, two added terms | in credit the two added terms are usually the larger part of the return of a held bond; Section 11 |
| Hygiene ledger | adds stale prints, size filters, dealer-mark rules and index membership files | unchanged structure | the ledger's rules change more than its structure: staleness is the normal state; Section 12 |

## 5. Universe and identity: issuers versus bonds, and what a symbol is not

EFB asked its price vendor for 858 tickers: the 503 current index members and 355
deleted ones (`EFB: docs/research/E1_data_note.md`). It got usable coverage on
0.7715617715617715 of them, and full coverage on the current members by
construction (`EFB: sprints/E1/RESULTS.json`, F1.1). The estimation panel is 825
names, of which 502 carry a sector, and those 502 are the model's universe
(`EFB: sprints/E3/PROBES.md`).

The lesson EFB paid for is that **a symbol is not an identity**. Three separate
defects sit behind that sentence:

- **36 reused symbols** were found in the vendor history. 33 were dropped from
  the panel. 3 were restored with truncated history, FOX from 2019-03-13, FOXA
  from 2019-03-12 and PCG from 2022-10-03 (`EFB: sprints/E2/RESULTS.json`,
  F2.6b). One of them, MI, shows why: its adjusted close went from 0.196 to
  18.90 on 2026-05-18, a 96x jump with no split at all
  (`EFB: docs/hygiene_ledger.md`). A single such row moved the trailing
  mean QLIKE from -6.61 to -1.82 and the largest per-name value to +2989.39
  (`EFB: docs/hygiene_ledger.md`).
- **4 names were vendor series breaks** where two issuers share one symbol
  history, with 20 break rows recorded (`EFB: sprints/E2/RESULTS.json`, F2.6).
- **Identity verification covered 373 rows, 93 matched and 244 unverified**
  (`EFB: sprints/E2/RESULTS.json`, F2.6b), and the coverage criterion itself
  failed on one name: DD scored 0.33 on a 0.5 name-similarity bar against
  "DuPont" versus "DuPont de Nemours, Inc.", leaving 502 of 503 mapped names, or
  0.9980119284294234 (`EFB: sprints/E2/RESULTS.json`, F2.6c). The framework has
  no FIGI or PERMNO mapping, which the repository records as an open item
  (`EFB: docs/open_items.md`).

In credit this becomes a two-level identity problem, and the second level has no
equity analogue:

| level | identifier | what changes |
| --- | --- | --- |
| issuer, or the obligor group | a permanent issuer ID, with a parent map that is itself dated | a merger changes the obligor without changing any bond |
| issue | CUSIP or ISIN, with an exchange map | a 144A to registered exchange changes the CUSIP without changing the bond |
| the vendor's own key | often the issuer's equity ticker | an issuer whose ticker changes loses its bond history, which is the ticker reuse defect at one remove |

Concretely, in credit the three EFB defects reappear as: **a CUSIP change on
exchange** (the same economic obligation, two identifiers, so a naive CUSIP key
breaks the return series in half), **a reopening** (the same CUSIP with more
outstanding, so issue size steps without a new bond), and **an issuer keyed off
the equity ticker** (so the reuse problem arrives through the reference data
rather than the price file). The fourth is new: several bonds to one obligor, so
every per-name statistic in EFB is a per-issuer statistic in the risk system but
a per-bond statistic in the return.

What to build, in order: an issuer identification table with dated parentage, a
CUSIP to issuer map with an exchange and reopening log, and a coverage criterion
of the same shape as EFB's, which is a fraction with a bar rather than a claim.
The DD case is the reminder that the bar has to be a pre-registered number, not
a judgement made once you see which name failed.

## 6. Survivorship: defaults and fallen angels

EFB's survivorship defect is documented and measured. The sector file holds only
the 502 current members, so the historical cross-section contains no
non-survivors: 41.9% of the 2010 index is absent by name and 8.85% by market cap
(`EFB: docs/open_items.md`), decaying to 4.8% by name in 2025. The measured bias
is a naive-minus-point-in-time return spread of 365.10364348332297 bp per year,
against 375.3717302558671 for naive-minus-Fama-French and 8.242312096655665 for
point-in-time-minus-Fama-French (`EFB: sprints/E1/RESULTS.json`, F1.5). Only
0.447887323943662 of the deleted members have recoverable history (159 of 355,
`EFB: sprints/E1/RESULTS.json`, F1.5), and the missing deletions are
disproportionately failures, so the loser-side residual tail is biased down
(`EFB: docs/hygiene_ledger.md`).

EFB also hit the *mechanism* that produces such a gap, not just the gap: the
membership matrix was seeded with today's live constituents and walked backward
through a pinned changes table, so three names added in 2026 (BE, P and RDDT)
were members back to 2010 for about sixteen years
(`EFB: handoff/LOG.md`, E10-F11). The fix pinned history and took the live
universe from the index archive from 2026-09-18 forward, with the seam labelled.
A cross-check found 6 names in disagreement, including ILMN with a 585-day false
membership gap (`EFB: docs/research/RG_OPERATE.md`).

In credit, survivorship is not one bias, it is three, and they have different
signs:

1. **Defaults are the deletion event.** A bond that defaults stops printing, so
   a survivor-only cross-section removes it on the day it matters most. The
   return it should contribute is the recovery-adjusted loss, which is a large
   negative observation and the single most important one in a credit sample. An
   index membership file gives you the exit date; your recovery data gives you
   the loss. Neither is a price.
2. **Fallen angels are a migration, not a deletion.** A bond that leaves the IG
   index for the HY index keeps trading and keeps printing. This is the credit
   version of the E10 membership defect: if you reconstruct history from today's
   index membership, a fallen angel's IG history disappears and its spread
   widening is attributed to a name that was never in IG. Ratings themselves
   must be point-in-time for the same reason.
3. **Calls, tenders and exchanges are early exits.** EFB's analogue is the 50%
   outlier flag that missed a 2:1 split
   (`EFB: handoff/PROJECT_CONTEXT.md`); in credit the event is a bond that
   disappears at par plus a call premium, and a naive series treats the gap as a
   missing price.

What to ask your data vendor for, phrased as EFB's criteria were: point-in-time
index membership with the reason for each exit, point-in-time ratings with
effective dates, and a default and recovery table keyed by issuer. Then
re-measure the equivalence of EFB's F1.5 on credit: the naive-minus-point-in-time
spread is the number a credit desk should see before it trusts any spread
premium.

## 7. Returns: excess over a duration-matched Treasury

EFB's audits are the transferable part, because they are what caught its data
problems. The adjusted-close audit has a mean absolute error of
0.01783192742840595 bp with a single 221.24636679102804 bp day, matched to the
BKR merger on 2017-07-05 (`EFB: sprints/E1/RESULTS.json`, F1.4). The close-out
audit has a mean of 0.017816512107027022 bp with one large day, again matched to
an event (`EFB: sprints/E2/RESULTS.json`, F2.0c). The universe return correlates
0.9563597974375629 with the Fama-French market factor (`EFB:
sprints/E1/RESULTS.json`, F1.3). None of those three numbers proves the data is
right; together they are the reason anyone believed it.

The credit version of the same battery, with the failure each one catches:

| audit | what it computes | what it catches |
| --- | --- | --- |
| cash-flow reconciliation | coupon and accrued interest against a dated cash-flow file per bond | a total-return series that quietly drops a coupon |
| benchmark match | the excess return against a duration-matched Treasury, from a stated curve | an interpolated benchmark that is not the bond's own risk-free rate |
| print versus mark | TRACE prints against the dealer marks in the same window | a mark series that is a consensus rather than a trade |
| index reconciliation | the book's return against the index's, name by name | a membership or weighting error, which is the E10 defect class |

Two facts from EFB shape how this should be done. First, EFB's risk-free series
ended 2026-07-31 while the panel ran to 2026-09-03, so XS-v1 regresses the total
return and treats the excess return as a diagnostic (`EFB:
sprints/E3/RESULTS.json`, F3.4 note). In credit the analogous trap is a curve or
rating file whose vintage differs from the print file: three reference vintages
that must be reconciled before the return column exists, which is the same
discipline the live loop applies per input (Section 12). Second, EFB drops
interior gaps rather than imputing, 302 rows across 13 tickers (`EFB:
sprints/E1/RESULTS.json`, F1.2). At credit density that rule removes most of the
panel, so it has to be restated as an explicit policy: a bond whose last print
is older than the horizon is either carried at its last mark with its age as an
exposure, or is out of the cross-section that day, and the two choices are
recorded as different experiments rather than mixed inside one estimation panel.

## 8. The factor model with DTS as the core exposure

The equity baselines a credit desk should reproduce before it believes a credit
model are all stored. Cross-sectional R squared averages 0.3294501878861149 over
3941 days, ranging from 0.247919 (2013) to 0.414612 (2022) (`EFB:
sprints/E3/RESULTS.json`, F3.1). The decomposition of that fit is the useful
part: market only is minus zero by construction, sectors alone explain 0.192787
and styles alone 0.200683 (`EFB: data/models/registry.json`). Style and sector
risk contribute about equally, which is a structural fact about a diversified
equity cross-section and not a coincidence to expect in credit, where sector and
rating overlap.

Three diagnostics transfer unchanged and are worth building before the model:

- **The shift test.** The design dated t gives a mean R squared of
  0.3640048077079439 while the lagged design gives 0.32946155266042604, a
  difference of 0.03454325504751787 (`EFB: sprints/E3/RESULTS.json`, F3.1). The
  test exists because a design built from previous-close data and a design with
  look-ahead are otherwise indistinguishable, and the number it produced is what
  proved EFB's descriptors carry no look-ahead (`EFB:
  efb/models/fundamental.py`, `raw_descriptors`).
- **Agreement with the other model world.** EFB's cross-sectional momentum
  factor correlates 0.7555482343048963 with the Fama-French momentum factor and
  its market factor 0.9889255744977894 with the market factor plus the risk-free
  rate over 3917 days (`EFB: sprints/E3/RESULTS.json`, F3.4). A credit port
  should correlate its spread factors with the index's own returns the same way.
- **A pricing test with an expected answer of no.** 64 of 72 Fama-MacBeth
  premium rows are unpriced, a share of 0.8888888888888888 (`EFB:
  sprints/E3/RESULTS.json`, F3.7). A credit desk should expect the same, and say
  so before the estimation runs.

DTS is where the port changes the meaning of every number. In EFB the market
column is a constant and the FMP hedge drives its exposure to zero to
5.8323571666685226e-15 (`EFB: sprints/E6/RESULTS.json`, F6.1), which is the
statement that the book is dollar neutral. In credit the comparable statement is
that the book is DTS neutral: the exposure per bond is spread duration times
spread, and the portfolio number to report is a single figure in years times
basis points. Two consequences:

- **A rates exposure is left over.** Zero credit market exposure is not zero
  rates exposure. Report the book's modified duration beside its DTS, or add
  key-rate duration columns to the design and treat them as factors. This is the
  one place where the roadmap's "unchanged" label for the market factor is too
  generous: the algebra is unchanged, the meaning of a zero is not.
- **The covariance matrix must be a spread covariance.** EFB's F is an EWMA over
  factor returns with a 90-session half-life and a Newey-West correction at lag
  2 (`EFB: data/models/registry.json`). The estimator ports; the input does not.
  Estimating F on spread changes rather than on total returns is what makes a
  DTS loading mean anything, and it is also what makes a rating-block structure
  visible.

Two smaller decisions, each with a cost:

| decision | EFB's choice | credit options | what it costs |
| --- | --- | --- | --- |
| cross-sectional weights | square root of market cap (`EFB: data/models/registry.json`) | outstanding notional, or inverse spread volatility | inverse volatility weighting encodes trading capacity, so liquid bonds dominate the factor estimate |
| regime variable | volatility regimes (VIX terciles) over which the champion's stress bias is measured, 2.8470668684488754 in 2020 Q1 against a sample mean of 3.205007104643809 (`EFB: sprints/E5/RESULTS.json`, F5.3) | OAS terciles | a spread regime is a function of the dependent variable, so it is endogenous by construction and has to be defined on a different bond universe or a different tenor to be a test |

One structural gap deserves emphasis because it is easy to miss when reading the
roadmap's mapping table: **XS-v1 has no cross-sectional value descriptor.** Its
six styles are size, beta, momentum, reversal, residual volatility and liquidity
(`EFB: efb/models/fundamental.py`, `STYLE_NAMES`). Value enters EFB only as the
Fama-French HML loading in the time-series model (`EFB: sprints/E2/PRD.md`). So
the credit value column, a bond's spread relative to its rating and sector peers,
is new work rather than a port, and it is the descriptor a credit PM will ask
about first.

## 9. Specific risk at the issuer and at the bond

EFB builds its diagonal as an exponentially weighted specific variance with a
42-session half-life, shrunk toward the mean of a sector and size-tercile bucket
with weight `n/(n+60)`, and stores 189 specific-variance dates (`EFB:
data/models/registry.json`). The decomposition identity closes to
6.245004513516506e-17 across 370 book dates (`EFB: sprints/E3/RESULTS.json`,
F3.5).

The measurement that matters most for credit is that the diagonal is a
simplification even in equities. EFB tested the residual covariance directly: the
largest residual eigenvalue is 22.303134561841865 against a Marchenko-Pastur edge
of 3.9522375163091836, with 10.8 to 11.2 directions above the edge, and the top
five residual directions carry 0.5681373901266118 to 0.5768030936931818 of the
book's specific variance (`EFB: sprints/E4/RESULTS.json`, F4.5). Roughly 57% of
what the model calls specific is structured. A credit desk should assume the same
or worse, because its issuer blocks are larger than any equity residual cluster.

Two further EFB results set expectations for the credit version:

- **The diagonal fails on concentrated books.** The factor share measured against
  the diagonal is 0.9940314593621442 versus 0.9968315206727247 against the
  realized residual covariance for the equal-weight book, but 0.7905666631763667
  versus 0.5890153813347032 for the momentum book (`EFB:
  sprints/E3/RESULTS.json`, F3.8). The diagonal overstates the factor share by
  20 points on the concentrated book. Credit books are concentrated by
  construction, so this is the regime to expect.
- **The bias has a shape.** The realized-to-predicted ratio falls from 0.8960 to
  0.5841 to 0.5191 across exposure terciles while predicted volatility is flat
  (`EFB: docs/open_items.md`). The model does not merely overstate risk on
  average; it does so in proportion to how much risk the book is taking.

The credit re-specification, in the order it should be built:

1. **Two levels, not one.** Issuer-specific and intra-issuer bond-specific
   variance, with the intra-issuer block estimated from the issuer's own bonds
   where there are enough of them. Thirty bonds to one obligor are thirty
   correlated residuals, and a diagonal treats them as thirty independent draws.
2. **Buckets that match the credit cross-section.** EFB's sector by size tercile
   becomes rating by sector by age. Keep the shrinkage form `n/(n+k)` and
   re-derive k, because the bucket occupancy is thinner and the constant controls
   how much of a thin bucket's estimate survives.
3. **A jump-to-default tail, kept separate.** EFB's return distribution has no
   default jump. A credit specific-risk number that excludes one is not wrong;
   one that includes it silently inside an EWMA variance is, because the
   variance then depends on whether a default happened inside the half-life.

One EFB artifact is worth copying wholesale: `efb/race.py::_specific_for` reads
the stored specific variance, counts the names it cannot cover, and reports that
count, and the caller fills the gaps with the cross-sectional median rather than
with zero. In credit almost every bond will be in that missing set at least once,
so the discipline of reporting the count beside the number matters more, not
less.

## 10. Hedging with CDX and Treasury futures

EFB's hedge study is the most directly transferable body of work in the
repository, because it separates what the algebra can do from what instruments
can do, and it measured both.

What the model's own hedge achieves: the exact in-model factor mimicking
portfolio hedge drives the worst post-hedge exposure to 5.8323571666685226e-15
and the idio share of variance to 1.0, trading a mean of 461.89142857142855 names
per rebalance over 175 dates (`EFB: sprints/E6/RESULTS.json`, F6.1).

What instruments achieve, on the same books:

| instrument set | factor variance removed | idio share after the hedge | source |
| --- | --- | --- | --- |
| exact FMP, in model | effectively all | 1.0 | `EFB: sprints/E6/RESULTS.json`, F6.1 |
| 13 ETFs, minimum variance, long-only book | 0.9784935060330155 | 0.02699369982241376 | `EFB: sprints/E6/RESULTS.json`, F6.2 and F6.4b |
| the same 13 instruments, momentum book | 0.4281 | 0.6719561534724836 | `EFB: docs/research/E6_hedge_study.md` |
| the as-stored capped FMP weights | leaves 0.7551610381615511, worse than unhedged | | `EFB: sprints/E6/RESULTS.json`, F6.1 |

Three conclusions transfer, and the third is the one to plan for:

1. **Instrument hedging is a diversification problem, not an algebra problem.**
   With a diversified book the instruments do nearly as well as the model
   (0.9785 of factor variance removed); with a concentrated book they do less
   than half (0.4281). A credit book is concentrated by issuer and by rating, so
   expect the second regime and size the hedge accordingly.
2. **The residuals that instruments leave behind are the factors with no
   instrument.** EFB measured them per factor: size 0.38156980950939573,
   liquidity 0.32224776934658006, reversal 0.11546042019447843, residual
   volatility 0.08622177896140602, momentum 0.05031865352133169, beta
   0.045336246850708264, market 0.013016329414488754, and sectors between
   0.016798858649876913 and 0.13368172161068734 (`EFB:
   sprints/E6/RESULTS.json`, F6.5). In credit the list becomes rating-bucket
   basis, sector basis, issuer basis and the index-versus-cash basis, and it
   should be measured the same way, as a residual per factor.
3. **A hedge decays, and the decay is measurable.** EFB's beta hedge leaves
   0.006492435936105948 at a 5-day rebalance and 0.013878891477231132 at 63 days
   (`EFB: sprints/E6/RESULTS.json`, F6_decay), and the hedge costs 0.1053% of
   notional on the momentum book and 0.1655% on the equal-weight book at
   monthly turnover of 0.7925 and 0.7640 (`EFB: docs/research/E6_hedge_study.md`).
   In credit the roll of a CDX series and of a Treasury future contract adds a
   cost and a basis step that equity instruments do not have, so the same
   measurement should be run on the roll calendar, not on the rebalance calendar.

The instrument set is CDX IG and HY, Treasury futures, and optionally LQD and HYG
as cash instruments with their own spread. Two mismatches are structural rather
than fixable: an index is a fixed list of names with its own rating and sector
composition, and a Treasury future hedges rates rather than spreads. The practical
consequence is that the hedge's job becomes a two-factor target (net DTS and
modified duration), with the residual reported per rating bucket and per sector,
exactly as F6.5 reported it per equity style.

Finally, the hedge vintage lesson is worth carrying over verbatim, because it was
found the hard way. EFB's hedge was built at the close of t against the design row
dated t, while the book earns the session after it, whose exposures are the row
dated with that session. The fix builds that row from data through the close,
using the close's own priced set as the cross-section, and it is exact whenever
that set does not move: measured against the row the model later publishes, the
hedged book is left with 1.2e-15 and 2.9e-14 of exposure on two ordinary
sessions, against 5.5e-03 and 4.5e-03 for the row dated the close, and 1.8e-03
rather than exact on the session before a market holiday, when the priced set
moves (`EFB: tests/test_hedge_vintage.py`). The credit equivalent is hedging with
spread durations from a mark that is three days old against a trade that settles
in two, and the same discipline applies: know which vintage the hedge used, and
record it, because a hedge is only exact against the object it was built on.

## 11. Costs from TRACE, and the one input credit measures that equity could not

This section is the strongest reason to port the framework at all. EFB's spread
cost is an assumption, and the repository says so in its own criterion. The model
uses a size-decile schedule from 10 bp in the smallest decile to 1 bp in the
largest (`EFB: sprints/E9/RESULTS.json`, F9.5), because every attempt to measure
it failed: raw Corwin-Schultz reads 2.5 to 5.2% of price, the overnight-adjusted
version floors at zero for every name, and Abdi-Ranaldo has no size gradient at
all, correlating 0.0031859126253798906 with size rank against the raw
Corwin-Schultz correlation of -0.47129396780020943 (`EFB:
sprints/E9/RESULTS.json`, F9.3 and F9.5). Equity data gave the framework a
plausible number and no way to check it.

TRACE changes that, and the change should be stated precisely because the
temptation is to overstate it. TRACE gives executed prices, sizes and timestamps
for the subset of bonds that trade. That supports an effective-spread estimator
on the traded subset, which is a measurement rather than an assumption. It says
nothing directly about the bonds that did not print, and those are the bonds a
credit book will hold. So the honest credit statement is: **the liquid part of
your cost model can be measured, and the illiquid part inherits the same problem
EFB had everywhere.** The design implication is to estimate the spread for the
traded subset, then model the untraded subset as a function of rating, size, age
and days since last trade, and report the share of the book's notional that sits
in the modelled part.

The rest of EFB's cost stack ports with its parameters visible. Impact is
`k * sigma * sqrt(dollar trade / ADV)` with k of 0.5 and an uncertainty range of
0.25 to 1.0; commission is 1 bp per dollar traded, one side; borrow is 2% per
year on short notional (`EFB: docs/research/RG_OPERATE.md`). The measured
establishment cost on the live book's 2026-09-21 close is 26.935060028070232 bp
in total, split as spread 4.713262872845437, impact 13.182112210073752,
commission 0.9685376726947534 and borrow 8.071147272456288, on gross
0.9685376726947534 across 499 names at a NAV of 1,000,000 with an average trade
size of 1940.9572599093256 (`EFB: live/cost_reconciliation.json`). The expected
cost on the frozen book is 15.036072942803287 bp (`EFB:
web/fixtures/snapshot_ok.json`). Capacity work produced 9 curves with zero
monotonicity violations on net Sharpe and net mean, and a turnover-penalized
optimizer that removes 0.37549626103844624 of turnover for 0.06485377957194484
of ex-ante information ratio, failing its own 50% bar (`EFB:
sprints/E9/RESULTS.json`, F9.1, F9.2 and F9.5).

The cost defect EFB hit is the one a credit port is guaranteed to repeat, so it
is worth quoting with its numbers. The impact term for the establishment book
reads 39.0447 bp, of which SW alone is 37.2460 bp, or 95.4%. The cause is not
SW's liquidity: the ADV map took a median over the whole panel, SW has zero
volume in 2,409 of its 4,208 sessions, so the median came out as zero, and the
guard `np.maximum(adv_map, 1.0)` turned that zero into one dollar of ADV. The
overstatement is about 14,000x, and the honest establishment cost is about 16.5
bp rather than 53.73 (`EFB: handoff/PROJECT_CONTEXT.md`). The lesson is not
"handle a zero"; it is that **a sparse ADV is the normal case in credit**, so the
estimator needs a minimum print count, an explicit bucket fallback by rating,
size and age, and a list of the names whose cost came from the fallback. EFB
already writes such a list into the proposal manifest (`thin_adv`, `EFB:
live/evening_job.py`), which is the pattern to copy.

Attribution needs the two terms the roadmap names, and they are large. EFB's
identity closes return = factor + specific + cost. In credit the same identity
needs carry and roll-down as explicit terms, because for a held bond they are
usually the larger part of the return, and a model that reports them inside
"factor" will lose the argument about whether the book is being paid for risk or
for the passage of time. Both terms are computable from the cash-flow file and
the curve, which makes them a data requirement rather than a modelling choice.

## 12. The live loop, staleness, and pricing an illiquid bond

EFB's live loop is small and its rules are the transferable part. The evening job
works on previous-close data only and writes a dated proposal with the hash of
every input; the morning job submits through two named fail-safe guards and
reconciles fills against intent; and the loop proposes while the rules decide, so
no path executes without a dated decision (`EFB: sprints/E11/PRD.md`).

The staleness design is the piece to copy. EFB allows the universe file one
session behind and the eight other inputs zero, and gates shares and sectors on
their fetch date rather than their content date, with the reason written into the
code: "a constituent list one session old still names the index being priced; a
price, a return or a covariance one session old prices the wrong close" (`EFB:
live/staleness.py`). In credit the same gate is needed per bond, not per file,
and the allowed lag cannot be zero: a bond that has not printed for a month is
not a broken feed, it is a bond.

The three defects the loop was built to catch all reappear in credit, so they are
worth naming with their equity evidence:

- **A clock running on frozen data.** EFB's day 1 was recorded as 2026-09-22
  while the proposal it produced was built on the 2026-09-03 close, the last date
  in the frozen model data, so thirty runs would have produced thirty identical
  proposals (`EFB: sprints/E11/RESULTS.json`, `day_1_proposal.as_of`). In credit
  the same defect looks like a book priced off marks that stopped updating, and
  it is harder to see because the marks are supposed to be stale.
- **A gate that replays history.** EFB's sanity gate ran on 2026-09-24 against
  the 2026-09-18 and 2026-09-21 closes while two sessions had already closed, and
  one proposal recorded its universe as of 2026-09-21 for a 2026-09-18 close,
  which is look-ahead (`EFB: handoff/LOG.md`, E11-F14). The credit version is a
  gate that validates the pipeline on a week of stale marks and calls the result
  a live check.
- **A silent fallback.** EFB's store fell back to local parquet whenever its
  database variable was unset and said nothing, so a mistyped variable on the
  host would still notify success and leave the dashboard reading an empty
  fallback (`EFB: handoff/REPORT.md`, E11-F17). In credit the equivalent is
  substituting a sector spread for a missing bond spread without recording which
  bonds were substituted, which changes the risk number and hides it.

For pricing illiquid bonds, the design that follows from the above is three
regimes, held explicitly rather than merged:

| regime | what the run knows | what to do |
| --- | --- | --- |
| a trade at or near the close | a price | use it, and count it as a print |
| no trade, a dealer mark | a quote | use it, tag the bond as marked, and carry the age |
| neither | nothing new | carry the last mark, report the bond's age as an exposure, and list it |

The two numbers that make this auditable are the share of book notional in each
regime, and the age distribution of the third regime, both stored per run. EFB's
precedent for the reporting side is its per-input staleness record and the
`failing_inputs` list on the run status (`EFB: live/sanity.py`); its precedent
for the discipline is the rule that a derived number is only as good as the
vintage it was read at, which is what the hedge vintage fix above was about.

Two operational facts of credit that the equity loop does not have to handle, and
that the design should not pretend away: trades settle on a lag, so the positions
the risk system sees after the close are not the positions the book will hold;
and marks get revised, so a risk number can move after it was published. EFB's
rule for the second is direct and worth adopting as written: never rebuild an
artifact a stored criterion was scored on without preserving it first
(`EFB: handoff/PROJECT_CONTEXT.md`).

## 13. The module map (F13.1)

Every module in the repository, with a status and one sentence of reason. The
status vocabulary is the one the criterion fixes: **unchanged**, **re-specified**,
**dropped**. `tests/test_e13_design_note.py` enumerates the repository and fails
if any module is missing from this section, so the "nothing unmapped" exit
criterion is a test rather than a claim.

### 13.1 The research library, `efb/`

| module | status | reason |
| --- | --- | --- |
| efb/__init__.py | unchanged | package marker, no domain content |
| efb/allocate.py | re-specified | the drawdown and allocation algebra ports, but the sampler has to draw defaults, not only returns |
| efb/alpha.py | re-specified | the engine that residualizes a signal on the champion design and measures its IC ports; the six equity signals do not |
| efb/build.py | unchanged | the build orchestrator and artifact hashing do not depend on the asset class |
| efb/costs.py | re-specified | the square-root impact form survives, the spread input becomes a measurement rather than an assumption |
| efb/cov.py | unchanged | an EWMA or PCA covariance estimator over a 504-session window is asset-class-agnostic once the input is a spread series |
| efb/eval_risk.py | re-specified | the evaluation engine ports, the piece assembly has to become credit-aware, including which design vintage a backtest hedges with |
| efb/evaluate.py | unchanged | criteria registration and the stored-numbers discipline are evaluation machinery |
| efb/evidence.py | unchanged | the artifact manifest and its hashes matter more, not less, when marks are revised |
| efb/factors.py | re-specified | the Fama-French download has no credit counterpart; the index's own excess return series is the replacement |
| efb/hedge.py | unchanged | the exact factor-mimicking-hedge algebra is the same operation with CDX and Treasury legs |
| efb/hygiene.py | re-specified | the flag and outlier rules change completely, the ledger structure they feed does not |
| efb/identity.py | re-specified | one symbol per issuer becomes two identity levels, issue and obligor, with a dated parent map |
| efb/models/__init__.py | unchanged | package marker for the model implementations |
| efb/models/fundamental.py | re-specified | the central port: the descriptor definitions change, the winsorization, standardization and orthogonalization survive |
| efb/models/statistical.py | unchanged | PCA on a cross-section does not care whether the columns are returns or spread changes |
| efb/models/timeseries.py | re-specified | the regression and the Vasicek shrinkage port; the factor set becomes credit factors and the beta history is rebuilt |
| efb/optimize.py | unchanged | mean-variance optimization with the E8 constraint set ports, with issue-level caps and liquidity constraints added |
| efb/pca_eval.py | unchanged | the Marchenko-Pastur edge test and the held-out comparison are estimator evaluation |
| efb/perf.py | unchanged | return and risk statistics over a P&L series |
| efb/portfolios.py | re-specified | the test families have to be defined by credit tilts, rating, sector, DTS and age, rather than by equity styles |
| efb/prices.py | re-specified | the vendor call becomes TRACE plus your quote feed, with the three pricing regimes of Section 12 |
| efb/probes.py | re-specified | the probe discipline ports directly; the sources it probes are entirely different |
| efb/race.py | unchanged | the covariance race, the artifact readers and the next-session design construction are model plumbing |
| efb/registry.py | unchanged | versions, hashes, the champion rule and the live construction block are model governance |
| efb/returns.py | re-specified | the largest single change: the return column becomes an excess return over a duration-matched Treasury |
| efb/risk.py | unchanged | the decomposition, the marginal contributions and the Monte Carlo are linear algebra |
| efb/size.py | unchanged | Procedure 6.3 and the proportional sizing rule are weighting rules |
| efb/spy.py | re-specified | the archive-as-live-universe mechanism ports to a credit index constituent archive |
| efb/survivor.py | unchanged | the measurement is reused as is; in credit the deletion event it measures is a default |
| efb/tercile.py | unchanged | exposure terciles are how the bias-by-exposure diagnosis is bucketed |
| efb/universe.py | re-specified | point-in-time index membership with a pinned history and a labelled live seam, on a credit index |
| efb/vol.py | unchanged | volatility scaling ports with the target restated in spread units |

### 13.2 The live loop, `live/`

| module | status | reason |
| --- | --- | --- |
| live/__init__.py | unchanged | package marker |
| live/alpaca.py | re-specified | the broker and the order type change; the interface of intent, submit, poll and reconcile does not |
| live/appendix.py | unchanged | mirroring each model input into a queryable store is exactly what a credit desk needs for point-in-time marks |
| live/breadth.py | unchanged | effective breadth is a property of the weight vector |
| live/clock.py | unchanged | the thirty-session clock is an operating discipline, not an equity one |
| live/construction_table.py | unchanged | the construction diagnostics port; the vintage of the design it reports is now recorded |
| live/corporate_actions.py | re-specified | splits become coupons, calls, tenders and 144A exchanges, and the vendor sentinel lesson carries over |
| live/dashboard_app.py | unchanged | the live view |
| live/evening_job.py | re-specified | the same evening shape, with credit inputs, a per-bond staleness gate and the vintage recorded |
| live/extend.py | unchanged | the append-only extension discipline, including the split guard, is the same problem in credit |
| live/guards.py | unchanged | the two fail-safe guards port, and their sizing lesson is on record |
| live/morning_job.py | unchanged | submit, poll and reconcile the intent |
| live/notify.py | unchanged | run notification |
| live/positions.py | unchanged | read the account before sizing and report the mismatch |
| live/reconcile.py | re-specified | the forecast-against-outcome reconciliation ports, and gains carry and roll-down |
| live/runroot.py | unchanged | the per-run tree |
| live/sanity.py | unchanged | the sanity gate, and its replay defect, are asset-class-agnostic |
| live/seed.py | re-specified | the seed sample becomes a credit sample with its own coverage criterion |
| live/sizing.py | unchanged | the hedged sizing step and the variance-share cap are weighting rules |
| live/snapshot.py | unchanged | the published snapshot |
| live/staleness.py | re-specified | the allowance becomes per bond rather than per file, and the calendar becomes the bond market's |
| live/state.py | unchanged | run state |
| live/store.py | unchanged | the DML-only store and its refusal to fall back silently |
| live/trade_reasons.py | re-specified | the reason vocabulary becomes spread moved, rating changed, carry, roll and new issue |

### 13.3 The dashboard, `dashboard/`

| module | status | reason |
| --- | --- | --- |
| dashboard/app.py | unchanged | the tab router and the version selectors |
| dashboard/publish.py | unchanged | copying linked documents into the served directory is a delivery step |
| dashboard/version.py | unchanged | the version stamp |
| dashboard/tabs/d00_data.py | re-specified | the data panel's inputs become credit reference, print and curve files |
| dashboard/tabs/d01_exposures.py | re-specified | exposures become rating, sector, DTS and age rather than equity styles |
| dashboard/tabs/d02_factor_risk.py | unchanged | the factor risk decomposition panel ports |
| dashboard/tabs/d03_covariance.py | unchanged | the covariance and correlation views |
| dashboard/tabs/d04_risk_eval.py | re-specified | the bias bands and coverage statistics are re-estimated on credit data |
| dashboard/tabs/d05_hedging.py | re-specified | the instrument set becomes CDX and Treasury futures, with the residual per rating bucket |
| dashboard/tabs/d06_alpha_lab.py | re-specified | the signal lab is reused for spread momentum and the rich-cheap residual, which are the credit signals |
| dashboard/tabs/d07_sizing.py | re-specified | the sizing view gains issue-level caps and liquidity constraints |
| dashboard/tabs/d08_costs.py | re-specified | the cost panel gains a measured spread and the untraded-notional share |
| dashboard/tabs/d09_risk_allocation.py | unchanged | risk allocation and drawdown views |
| dashboard/tabs/d10_book.py | unchanged | the book review view |
| dashboard/tabs/methodology.py | unchanged | the document index, and where this note is linked from |

### 13.4 Scripts, the web client and the repository outside the modules

| module | status | reason |
| --- | --- | --- |
| scripts/__init__.py | unchanged | package marker |
| scripts/make_web_fixtures.py | unchanged | the fixture writer, once the snapshot it writes is a credit snapshot |
| scripts/provision_supabase.py | unchanged | schema provisioning |
| scripts/push_seed.py | unchanged | seed publication |
| scripts/run_live_daily.py | unchanged | the daily entry point, and the place a credit run would be wired |
| scripts/smoke_order_timing.py | re-specified | the order timing window becomes the credit market's session, which closes at a different hour |
| scripts/verify_account.py | unchanged | account reconciliation |
| scripts/verify_store_roundtrip.py | unchanged | store round-trip verification |
| web/src/App.tsx | unchanged | the page renders a snapshot document and does not know the asset class |
| web/src/main.tsx | unchanged | the mount point |
| web/src/types.ts | re-specified | the snapshot's factor names and labels become credit labels |
| web/src/App.test.tsx | unchanged | the page tests follow the fixtures |
| web/src/bundle.test.ts | unchanged | the bundle check |
| web/src/fixtures.test.ts | unchanged | the fixture contract, which is what keeps a regenerated fixture honest |
| Makefile | unchanged | the build, test and dashboard targets |
| pyproject.toml | unchanged | tooling and test configuration |
| data/VERSION.json | unchanged | the artifact hash manifest, whose role is unchanged and whose contents are all new |
| tests/ | re-specified | the suites follow the modules; the E13 suite in this sprint is the F13.1 check itself |
| notebooks/ | re-specified | the walkthroughs become credit walkthroughs, with the same rule that every number is read from a stored file |
| sprints/ | unchanged | the sprint scaffolding, criteria, results and probes |
| docs/hygiene_ledger.md | unchanged | the ledger's structure, and its purpose, port as they are |
| docs/multiple_testing_ledger.md | unchanged | the deflated-Sharpe discipline is the part of EFB a credit desk most needs |
| docs/roadmap_v2.md | unchanged | the programme record |
| handoff/ | unchanged | the handoff convention, which the credit port should adopt on day one |

Two statuses in that map deserve a warning, because both are places where a
credit port will be tempted to write "unchanged" and be wrong. `efb/race.py` and
`efb/cov.py` are marked unchanged as *algorithms*. Both will need their inputs
re-specified, and a factor covariance estimated on total returns rather than
spread changes will produce a DTS loading that means nothing. The algorithm being
unchanged is not the same as the number being right.

## 14. Open questions for the research team, each tied to an EFB number

These are written as questions to put to the desk and to the data team. Each
carries the EFB result that makes it worth asking, which is the rule the roadmap
sets for this sprint: an open question with no EFB evidence behind it is a
falsifier.

1. **What is the return column?** EFB's risk-free series ended 2026-07-31 while
   the panel ran to 2026-09-03, so the champion model regresses the total return
   and treats the excess return as a diagnostic (`EFB: sprints/E3/RESULTS.json`,
   F3.4 note). Which curve do you want the duration-matched benchmark taken from,
   and does it change the sign of any factor loading?
2. **What cross-sectional fit should we expect?** The equity baseline is
   0.3294501878861149 over 3941 days, from 0.247919 in 2013 to 0.414612 in 2022
   (`EFB: sprints/E3/RESULTS.json`, F3.1). Write the credit band down before the
   first estimate runs, because a band drawn after the number is not a criterion.
3. **How large is the credit survivorship gap?** EFB measured 365.10364348332297
   bp per year from a survivor-only cross-section, with only 0.447887323943662 of
   deleted members recoverable (`EFB: sprints/E1/RESULTS.json`, F1.5). What are
   the two credit numbers, with defaults counted as exits?
4. **How many identifier breaks are in the reference data?** EFB found 36 reused
   symbols and dropped 33 (`EFB: sprints/E2/RESULTS.json`, F2.6b). How many
   CUSIP changes, reopenings and 144A exchanges are in your history, and what
   share of the book changes its issuer if the parent map is wrong?
5. **Is the issuer block the right unit for specific risk?** EFB found the top
   five residual directions carry 0.5681373901266118 to 0.5768030936931818 of the
   book's specific variance against a Marchenko-Pastur edge of 3.9522375163091836
   (`EFB: sprints/E4/RESULTS.json`, F4.5). What is the credit number, and does a
   two-level structure reduce it?
6. **What does the diagonal cost on a real credit book?** EFB's factor share is
   0.7905666631763667 measured against the diagonal and 0.5890153813347032
   against the realized residual covariance on a concentrated book (`EFB:
   sprints/E3/RESULTS.json`, F3.8). Re-measure that pair on a book of about 200
   bonds across 60 issuers.
7. **What do CDX and Treasury futures actually remove?** EFB's ETF hedge removes
   0.9784935060330155 of factor variance on a diversified book and 0.4281 on a
   concentrated one (`EFB: sprints/E6/RESULTS.json`, F6.2 and `EFB:
   docs/research/E6_hedge_study.md`). What is the residual per rating bucket, in
   the form F6.5 reported per style?
8. **How much of the spread is measurable?** EFB assumed it, from 10 bp in the
   smallest size decile to 1 bp in the largest, because raw Corwin-Schultz reads
   2.5 to 5.2% of price and Abdi-Ranaldo has no size gradient
   (`EFB: sprints/E9/RESULTS.json`, F9.3 and F9.5). What share of your notional
   can be measured from TRACE, and what is the measured gradient by rating and
   size?
9. **What is the minimum print count for an ADV?** EFB's impact term reached
   39.0447 bp with SW alone at 37.2460 bp, or 95.4%, because a zero median ADV was
   floored to one dollar (`EFB: handoff/PROJECT_CONTEXT.md`). What threshold makes
   a per-bond ADV trustworthy, and what is the bucket fallback?
10. **What is the age distribution of your marks?** EFB's gate allows the
    universe one session behind and the other eight inputs zero (`EFB:
    live/staleness.py`). What share of your book is unpriced for more than five
    sessions, and what share of its variance sits there?
11. **How much of the return is carry and roll-down?** EFB's attribution has no
    carry term, and the roadmap adds two. For a held bond, are carry and
    roll-down larger than the factor and specific terms combined, and if so does
    that change the factor loadings' interpretation?
12. **How many signals will be tried?** EFB's ledger records 111 runs and 70
    NULL labels (`EFB: sprints/E7/RESULTS.json`, F7.3). Credit has more, not
    fewer, candidate signals. What is the pre-registered deflated bar, and who
    holds the ledger?
13. **What is the credit bias band and its stress episode?** EFB's champion
    carries a family mean bias of 1.0469839503253322 against a 0.9 to 1.1 band it
    does not meet on every family, and a 2020 Q1 stress bias of
    2.8470668684488754 (`EFB: sprints/E5/RESULTS.json`, F5.1 and F5.3). Which
    episode defines the credit stress case, March 2020, the 2011 European
    episode, or the 2022 rates move?

## 15. The defect classes this project hit, and how each would appear in credit

This is the section the design note exists for. Every class below was hit in
EFB, is recorded in a stored file, and has a credit form that is recognisably the
same defect. They are grouped by kind, and the credit column is written as the
symptom a reviewer would see, not as a warning.

### 15.1 Methodology and evaluation design

| the defect, as EFB hit it | the credit form |
| --- | --- |
| A sign mix-up inflated a relative gap by exactly 2.0, from 2.9598 to a stored 4.959825 (`EFB: sprints/E10/RESULTS.json`) | a spread change reported as positive when spreads tightened, or a hedge residual whose sign flips with the quotation convention |
| The comparator was not the same object, three times: a horizon-free drawdown benchmark, 15 raw years against 14 targeted years (0.1220 against 0.1508), and a 10-month figure beside a 16-year one with no n (`EFB: sprints/E10/RESULTS.json`) | a bond's excess return compared to an index's return rather than to its own duration-matched Treasury, or a credit Sharpe from a quiet quarter beside one from a default wave |
| A criterion fitted to the answer: F10.1b's 0.15 to 0.25 band was drawn after the value was known, so it passed; against the pre-registered 10% bar it fails at 0.2963 (`EFB: sprints/E10/RESULTS.json`) | a "reasonable" credit R squared band chosen after the first estimate, which passes by construction |
| A recorded mechanism contradicted by a control: the drawdown was blamed on fat tails and clustering, while a Gaussian control drew down deeper, -0.1539687769091203 against -0.140308 (`EFB: sprints/E10/RESULTS.json`) | spread widening blamed for a drawdown that a control reproduces with no default and no ratings change |
| A sample selected by ticker order: the first 60 alphabetical names, where a seeded draw moved the win share from 46.7% to 61.2% (`EFB: docs/hygiene_ledger.md`) | taking the first 500 CUSIPs, which in credit means taking one issuer, one sector and one maturity band |
| A per-name average of an unbounded loss: one abused row moved the mean QLIKE from -6.61 to -1.82 and the largest value to +2989.39 (`EFB: docs/hygiene_ledger.md`) | a per-bond cost or tracking-error average dominated by one default or one distressed print |
| Two verdict vocabularies for one signal: E7 stores PASS for two signals while its own `RG_SIGNAL.json` stores NULL for all six (`EFB: sprints/E7/RESULTS.json`) | a signal reported as significant on the raw spread while the same signal is NULL after rating and sector neutralization |

### 15.2 Data hygiene and identity

| the defect, as EFB hit it | the credit form |
| --- | --- |
| A symbol is not an identity: 36 reused symbols, 33 dropped, one name jumping 96x with no split, 0.196 to 18.90 (`EFB: sprints/E2/RESULTS.json`, F2.6b) | a CUSIP change on exchange, a reopening, or a vendor key built from the issuer's equity ticker, each of which cuts a bond's history in half |
| A survivor-only cross-section: 41.9% of the 2010 index absent by name, 8.85% by cap, 365.10364348332297 bp per year of bias, only 0.447887323943662 of deletions recoverable (`EFB: sprints/E1/RESULTS.json`, F1.5) | defaults as the deletion event, and fallen angels as a migration that a naive membership reconstruction erases |
| Retroactive membership: three names added in 2026 were members back to 2010, about sixteen years (`EFB: handoff/LOG.md`, E10-F11) | today's index membership walked backward, so a fallen angel's investment grade history disappears and its widening is attributed to a name that was never in the index |
| Corporate actions: a 2:1 split missed by the outlier flag, a rehearsal that exposed it on the first appended session, and a vendor convention where 0.0 means no split and a rule reading not-equal-to 1.0 would have stopped every run (`EFB: handoff/PROJECT_CONTEXT.md`) | coupons, calls, tenders and exchanges, with the same sentinel convention and the same need for a tolerance rather than an equality |
| Sentinels and missing values becoming numbers: a zero median ADV floored to one dollar, 37.2460 of a 39.0447 bp impact term, about 14,000x overstated; a NaN price silently becoming a share count; a bare NaN refusing to load into jsonb (`EFB: handoff/PROJECT_CONTEXT.md`, `EFB: handoff/REPORT.md`) | a zero price, a "not traded" sentinel or an absent spread entered as a number, which is the defect class a credit panel is most likely to produce |
| A "read-only" run that rewrote raw artifacts: prices rewritten at 61,233,059 bytes and three columns lost from an archive, restored byte for byte and caught by the evidence manifest (`EFB: handoff/REPORT.md`, `EFB: evidence/MANIFEST.json`) | a mark study or a liquidity study writing over a point-in-time file that a stored criterion was scored on |

### 15.3 Live and operational

| the defect, as EFB hit it | the credit form |
| --- | --- |
| A clock running on a frozen close: day 1 recorded as 2026-09-22 while the proposal was built on the 2026-09-03 close (`EFB: sprints/E11/RESULTS.json`) | a book priced off marks that stopped updating, which is harder to see precisely because stale marks are normal |
| A gate that replays history, and a proposal whose universe postdated its close (`EFB: handoff/LOG.md`, E11-F14) | a sanity check run on a week of stale marks and reported as a live check |
| A silent fallback to a local store, so a mistyped variable would still notify success (`EFB: handoff/REPORT.md`, E11-F17) | a sector spread substituted for a missing bond spread without recording which bonds were substituted |
| Mis-sized guards: a $200,000 brake that would have tripped on a $1,000,000 establishment, and a 40% cap about 200x above an average position near $2,000 (`EFB: handoff/LOG.md`) | a per-issuer cap or a notional brake sized from an equity book, which either never fires or stops the first real trade |
| A fixed-point loop that could only drop names: 118 one-pass, 188 at the fixed point, 119 enforced, with n_eff falling to 58.82 (`EFB: handoff/LOG.md`, E11-F13) | a liquidity or issue-cap enforcement loop that only drops, on a book whose constraints require admission |
| A pinned count in a source-pin test, which failed on a correct change and sat broken until the next full-suite run (`EFB: handoff/PROJECT_CONTEXT.md`) | pinning the number of design columns or the number of instruments, so a correct extension fails the suite |

### 15.4 Presentation and reporting

| the defect, as EFB hit it | the credit form |
| --- | --- |
| One criterion with three values: F1.3 stored as null, quoted 0.9557 and 0.9564 elsewhere, corrected to 0.95655; F1.5 quoted as 349 against a stored 365.10 (`EFB: sprints/E1/RESULTS.json`) | a research note quoting a spread premium or a default rate that the stored file disagrees with |
| An unqualified breadth number naming the wrong book: 157.33 for the full book beside a 150-name book whose own breadth is 70.59 (`EFB: handoff/REPORT.md`) | one breadth or concentration number for a book and its issuer rollup, with no label saying which |
| Dates rendered as timestamps, guarded by two suites (`EFB: live/snapshot.py`) | the same, with settlement dates and with as-of dates on ratings |
| A header row leaked into a stored artifact (`EFB: sprints/E7/RESULTS.json`, the `---` key in `verdict_by_signal`) | a vendor file's footnote or unit row carried into the mark history as a bond |
| An untracked, underived artifact one run from being unrecoverable, as E5 lost a published covariance race row (`EFB: handoff/LOG.md`) | an index membership snapshot or a ratings file with no hash and no copy |

Five rules came out of these, and a credit port should adopt them on day one
rather than rediscover them:

- "Every real defect so far was found by reading an output, not the code"
  (`EFB: handoff/PROJECT_CONTEXT.md`). In credit the equivalent is reading the
  mark history, not the pricing code.
- "Never rebuild an artifact a stored criterion was scored on without preserving
  it first" (`EFB: handoff/PROJECT_CONTEXT.md`). Restated marks make this a daily
  rule, not a review rule.
- "A gate on historical dates is a replay, not a live check" (`EFB:
  handoff/PROJECT_CONTEXT.md`).
- "Check whether a number is an identity before reading it as a result" (`EFB:
  handoff/PROJECT_CONTEXT.md`).
- "An unexplained change to a stored-criteria file is a stop" (`EFB:
  handoff/STANDARDS.md`, rule 22).

## 16. A phased build plan for the first ninety days

Each phase names its exit evidence in the form EFB used, so that progress is a
stored number rather than a status report.

| phase | weeks | what is built | exit evidence |
| --- | --- | --- | --- |
| 0. Data inventory and identity | 1 to 2 | issuer and issue identity tables with dated parentage, the coverage criterion, the three reference vintages reconciled | a coverage fraction with a pre-registered bar, in the shape of E1's 0.7715617715617715 (`EFB: sprints/E1/RESULTS.json`, F1.1) |
| 1. Return column and ledger | 3 to 5 | excess return over a duration-matched Treasury, the four audits of Section 7, the stale-print and dealer-mark rules | audit means of the order of EFB's 0.01783192742840595 bp, and a point-in-time panel reproducible from stored files (`EFB: sprints/E1/RESULTS.json`, F1.4) |
| 2. The first cross-section | 6 to 8 | the credit design with DTS, rating, sector, seniority, size, age and liquidity columns, the minimum-names rule, the shift test | a pre-registered R squared band, the market, sector and style decomposition in the form of 0.192787 and 0.200683, and a shift test of the form 0.32946155266042604 against 0.3640048077079439 (`EFB: data/models/registry.json`, `EFB: sprints/E3/RESULTS.json`, F3.1) |
| 3. Specific risk structure | 6 to 8 | issuer and bond levels, bucket shrinkage by rating, sector and age, the jump-to-default tail kept separate | the diagonal against realized factor-share pair on a concentrated book, of the form 0.7905666631763667 against 0.5890153813347032 (`EFB: sprints/E3/RESULTS.json`, F3.8) |
| 4. Hedging | 9 to 11 | CDX and Treasury futures hedges, the residual per rating bucket and sector, the decay by rebalance frequency, the roll cost | a residual table in the form of F6.5's per-style numbers, a decay curve of the form 0.006492435936105948 at 5 days to 0.013878891477231132 at 63 (`EFB: sprints/E6/RESULTS.json`) |
| 5. Costs and capacity | 9 to 11 | the measured spread on traded bonds, the bucket fallback for the rest, the untraded notional share, capacity curves | a cost reconciliation against realized slippage, in the form of 26.935060028070232 bp against the 10.52718113254709 bp reference, ratio 2.55862036464772, verdict reconciled (`EFB: live/cost_reconciliation.json`) |
| 6. The loop | 12 to 13 | the evening and morning shape with a per-bond staleness gate, the three pricing regimes, guards restated for credit | a dry-run week with every number stored, the pricing regime shares reported, and the design vintage recorded |
| 7. Credibility check | 13 | EFB's diagnostic battery reproduced on credit like for like, and this note's falsification section rewritten for credit | a written comparison whose every number is read from a stored file, including the ones that disagree |

The sequencing follows one EFB lesson that is easy to miss: the hard part is not
the model, it is the ledger. Phases 0 and 1 take five weeks and produce no
factor. That is the correct shape, because every measured bias in EFB's record,
365.10364348332297 bp per year of survivorship and a 14,000x cost overstatement
among them, came from the data layer.

## 17. What would falsify this

- **A module marked unchanged that depends on an equity-only assumption.** This
  is the roadmap's own falsifier, and the three candidates to attack first are
  the factor covariance, which needs a spread input to make DTS meaningful; the
  hedge algebra, whose instrument betas are the weakest link; and the cross
  sectional standardization, which takes its cross-section over the names priced
  on the row's own date. That last one is not a theory: EFB's hedge was one
  session stale for exactly that reason, and the fix is recorded with its
  measurements (`EFB: tests/test_hedge_vintage.py`).
- **An open question with no EFB evidence behind it.** Section 14 is written so
  that each question can be audited against a stored number.
- **The specific-risk plan failing its observable test.** If a two-level
  structure does not improve the realized-to-predicted bias relative to a
  diagonal, in the form of EFB's fall from 0.8960 to 0.5841 to 0.5191 across
  exposure terciles (`EFB: docs/open_items.md`), the plan in Section 9 is wrong.
- **The hedging plan failing its observable test.** If CDX and Treasury futures
  remove materially less of the factor variance than equity instruments removed
  on a comparable book, 0.9784935060330155 diversified and 0.4281 concentrated
  (`EFB: sprints/E6/RESULTS.json`, F6.2 and `EFB:
  docs/research/E6_hedge_study.md`), then the instrument set, not the algebra, is
  the binding constraint and the port is worth less than this note claims.
- **The mapping describing EFB rather than credit.** If the credit cross-section
  cannot reproduce a pre-registered fit band and a bias band on a second dataset,
  a different index family or a different period, then Sections 8 and 9 are
  describing the equity book.

## Appendix A: the stored files every number in this note was read from

| source | what it supplied |
| --- | --- |
| `EFB: sprints/E1/RESULTS.json` | universe coverage, interior gaps, the adjusted-close audit, survivorship bias, recoverable history |
| `EFB: sprints/E2/RESULTS.json` | reused symbols, series breaks, identity coverage, the close-out audit, the time-series factor set |
| `EFB: sprints/E3/RESULTS.json` | cross-sectional fit and its decomposition, the shift test, the FMP identity, agreement with the time-series factors, the decomposition identity, the diagonal against realized covariance |
| `EFB: sprints/E4/RESULTS.json` | the PCA factor count, the held-out fit race, the residual spectrum and its concentration |
| `EFB: sprints/E5/RESULTS.json` | family mean bias, the stress episode, the champion and its haircut |
| `EFB: sprints/E6/RESULTS.json` | hedge efficacy, the residual per factor, the hedge decay, the idio share after an instrument hedge |
| `EFB: sprints/E7/RESULTS.json` | the multiple-testing ledger shares and the signal verdict vocabularies |
| `EFB: sprints/E9/RESULTS.json` | the spread assumption and why it was assumed, capacity, the turnover penalty result |
| `EFB: sprints/E10/RESULTS.json` | the sign mix-up, the comparator defects, the criterion fitted to its answer |
| `EFB: sprints/E11/RESULTS.json` | the clock, the day-1 proposal and its as-of date |
| `EFB: data/models/registry.json` | factor count, estimator settings, the covariance half-lives, the champion rule, the live construction block |
| `EFB: data/VERSION.json` | the artifact hash manifest |
| `EFB: live/cost_reconciliation.json` | the measured establishment cost split and the reconciliation verdict |
| `EFB: live/staleness.py` | the allowed sessions behind per input and the reason |
| `EFB: live/sanity_gate.json` | observed input staleness |
| `EFB: web/fixtures/snapshot_ok.json` | the frozen book's numbers and its expected cost |
| `EFB: docs/hygiene_ledger.md` | the symbol reuse entry, the flag rules, the GARCH sample defect, the per-name loss defect |
| `EFB: docs/open_items.md` | the survivor-only cross-section, the bias-by-exposure profile, the missing identity map |
| `EFB: handoff/PROJECT_CONTEXT.md` | the working lessons, the cost defect, the corporate action defects, the pinned-count test |
| `EFB: handoff/LOG.md` | the E10 and E11 defect records quoted in Section 15 |
| `EFB: handoff/REPORT.md` | the store fallback, the rewritten raw artifacts, the unqualified breadth number |
| `EFB: handoff/STANDARDS.md` | the rules quoted in Section 15.4 |
| `EFB: docs/roadmap_v2.md` | the E13 scope, the falsification criteria and the credit mapping this note starts from |
| `EFB: docs/research/E1_data_note.md` | the return definition, the requested tickers, the stylized facts |
| `EFB: docs/research/E3_factor_model_note.md` | the estimation window and the sector constraint |
| `EFB: docs/research/E6_hedge_study.md` | the instrument hedge results and the hedge cost model |
| `EFB: docs/research/RG_OPERATE.md` | the constituent source, the crosscheck disagreements, the cost and timing parameters |
| `EFB: evidence/MANIFEST.json` | the artifact manifest that caught the rewritten raw files |
| `EFB: tests/test_hedge_vintage.py` | the hedge vintage measurements quoted in Sections 10 and 17 |
| `EFB: efb/models/fundamental.py` | the style set, the descriptor definitions, the standardization rule |
| `EFB: efb/race.py` | the specific-variance fallback and the next-session design construction |
| `EFB: live/evening_job.py` | the thin-adv list and the recorded hedge vintage |

Two limitations of this note, stated plainly. First, it cites no credit data,
because it was written without any: every credit statement here is a design
statement or a prediction, and the numbers are all EFB's. Second, the credit
magnitudes that appear in the tables of Sections 2 and 7 are illustrative
placeholders for shape and units, not measurements, and they are labelled as
such where they appear.





