# Why a monthly rebalance trades 87% of NAV, and what cuts it

Research only: no trading change, no merge, no deploy, no Render change, nothing
triggered. The apparatus is `scripts/churn_study.py`; every number below is in
`churn_study.json` beside this note.

## What was simulated

Monthly cadence (k = 21) through **2024-06-03 to 2026-10-02: 586 sessions, 2.33 years, 28
rebalances**. On each rebalance day the target is built by the live construction itself,
`live.evening_job.build_proposal(store=False)`, with the **currently held book passed as
`previous`** - the floor's release band and the impact term both read it, so the path is
simulated sequentially, one build per rebalance day. Between rebalances the book is held
and drifts with the tree's own returns. Costs are the cadence study's: the size-decile
half-spread and commission on **traded** notional, square-root impact
`k·σ·sqrt(dollar/adv)`, and borrow on the short gross every held day at
`efb.costs.BORROW_RATE`.

**The universe is frozen at the 2026-09-18 SPY archive, dated for every session** (today's
membership applied to the past), for the same reason as the cadence study: the live path
refuses a close before its newest archive. So **P&L levels are indicative** - 2.33 years at
4.4% vol is about 280 bp/yr of standard error per cell - and the cross-variant comparison,
which uses one universe and one cost model throughout, is the result.

**B0 reproduces the cadence study's V0 k=21 row exactly**, which is the check that the
sequential `previous` path and the reused cost model agree with the earlier study:
turnover 87.02% against 0.8702, trading cost **69.1 vs 69.1 bp/yr**, net **48.4 vs 48.4**,
gross 218.9 vs 218.9, borrow 101.4 vs 101.4.

## The variant table

Turnover split is per rebalance, in % of NAV. `alpha` is the expected-alpha-retained metric:
the held book's `Σ w·alpha_vec` over all 586 days as a percentage of B0's the same day
(more on the >100% figures below). Exposure and variance share are of the **held** book;
`expo max` is the worst day of the whole hold and `expo @reb` the worst day right after
trading.

| variant | NAV | release | tov/reb | tov/yr | gross | cost | borrow | net | vol | Sharpe | names | alpha | expo avg | expo max | expo @reb | var share max | var share @reb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **B0** | 1M | off | **87.02%** | 10.48 | 218.9 | 69.1 | 101.4 | 48.4 | 4.41% | 0.11 | 199.7 | 100.0% | 1.19% | 23.0% | 0.159% | 47.1% | 25.5% |
| B1 | 1M | off | 83.46% | 10.05 | 211.6 | 66.3 | 100.6 | 44.8 | 4.42% | 0.10 | 199.7 | 98.7% | 1.49% | 24.1% | 1.929% | 46.5% | 29.4% |
| F75 | 1M | 0.75 | 80.78% | 9.73 | 274.1 | 64.7 | 101.3 | 108.1 | 4.61% | 0.23 | 192.0 | 108.1% | 1.22% | 24.3% | 0.080% | 47.7% | 26.4% |
| **F50** | 1M | 0.50 | **72.23%** | 8.70 | 221.4 | 58.3 | 101.5 | 61.7 | 4.94% | 0.12 | 193.1 | 125.9% | 1.22% | 29.3% | 0.120% | 48.5% | 25.1% |
| N2 | 2M | off | 78.62% | 9.47 | 228.7 | 62.2 | 101.3 | 65.1 | 4.44% | 0.15 | 284.7 | 125.7% | 1.11% | 30.0% | 0.071% | 40.5% | 22.5% |
| N5 | 5M | off | 74.92% | 9.02 | 187.6 | 60.1 | 101.3 | 26.2 | 4.02% | 0.07 | 379.6 | 129.0% | 1.01% | 27.9% | 0.029% | 37.6% | 20.6% |
| F75+B1 | 1M | 0.75 | 77.34% | 9.31 | 268.1 | 62.0 | 100.7 | 105.4 | 4.60% | 0.23 | 192.0 | 107.4% | 1.57% | 23.9% | 1.674% | 46.8% | 26.5% |
| N5+B1 | 5M | off | 71.37% | 8.59 | 161.7 | 57.4 | 100.3 | 3.9 | 3.99% | 0.01 | 379.6 | 125.8% | 1.21% | 27.8% | 1.579% | 38.2% | 20.5% |
| F50+N2+B1 | 2M | 0.50 | **69.27%** | 8.34 | 132.4 | 55.2 | 100.7 | −23.4 | 4.33% | −0.05 | 294.6 | 127.5% | 1.30% | 29.6% | 1.269% | 40.7% | 20.8% |
| NOFLOOR *(reference)* | 1M | off | 71.54% | 8.61 | 222.6 | 53.9 | 101.1 | 67.6 | 3.77% | 0.18 | 494.6 | 133.8% | 0.96% | 24.9% | 0.196% | 36.2% | 19.9% |

Turnover split, % of NAV per rebalance:

| variant | entries | exits | resizes |
|---|---|---|---|
| B0 | 12.01 | 11.18 | 14.23 |
| B1 | 12.01 | 11.10 | 12.78 |
| F75 | 10.72 | 9.37 | 14.65 |
| F50 | 8.47 | 6.37 | 16.22 |
| N2 | 9.18 | 7.95 | 16.68 |
| N5 | 6.28 | 4.80 | 21.14 |
| NOFLOOR | 1.67 | 0.00 | 29.09 |

Three readings of that table are load-bearing.

**1. The floor is a fifth of the problem, not the problem.** Take the floor away entirely
(NOFLOOR, reference only) and the monthly rebalance still trades **71.5% of NAV**. So of
the 51.4 points between the live 87.0% and the design book's 35.6%, the floor explains
**15.5 points (30%)** and about **36 points are in the pre-floor target book itself**. Every
variant that keeps entry contingent on the full floor (all of them except NOFLOOR) removes
only the exits and resizes that the floor forces, which is exactly the 6-15 point range in
the table.

**2. `alpha retained` above 100% is a finding, not a bug.** Every variant holds *more* of
the day's alpha than the fresh target does, up to 133.8% with the floor removed. The floor
drops names for their **size** - a 20-share minimum in the renormalized book - not for
their alpha, so the names it discards carry above-average alpha. That is confirmation that
the floor costs expected return as well as turnover, and it is also the reason the
`alpha ≥ 90%` test cannot separate the variants: they all pass it, so the decision has to be
made on turnover and on the risk columns.

**3. NAV and the floor push the same marginal names.** Raising NAV to 5M cuts turnover by
12.1 points and dropping the release band to 0.50 cuts it by 14.8; together (F50+N2) they
cut it by 17.8, not 27 - they overlap, because both work by keeping names that clear a
20-share minimum in a bigger book. The mechanism is visible in the split: at 5M the exits
fall from 11.2% to 4.8% of NAV per rebalance while resizes rise from 14.2% to 21.1%. Fewer
names leave; the ones that stay are bigger and move more.

## Where the other 36 points come from, and why no floor rule reaches them

The design book's 35.6% is not a measured property of the live signal. `docs/research/
nov11_turnover.md` records it as the **synthetic-alpha** book at `rho = 0.02, phi = 0.95`,
and `efb/size.py:791` gives the relation the repo itself uses:
`predicted turnover = sqrt(2·(1 − phi))`. At phi = 0.95 that is **31.6%**, against a
realized 35.6% - a good match, and it says the design book's turnover is a property of the
**alpha's assumed persistence**, not of the construction.

Run the same relation backwards on what this study measured. The live signal's rank
autocorrelation is 0.892 at 21 sessions (`docs/research/ic_decay.md`), which predicts
`sqrt(2 × 0.108) = 46%` per rebalance - still well below the 71.5% the floor-free book
actually trades. The 71.5% implies an effective persistence of `phi ≈ 1 − 0.715²/2 = 0.744`,
and the 87.0% implies `phi ≈ 0.62`. So the gap between the signal's persistence and the
book's is the **sizing's sensitivity**: `w ∝ alpha/σ²` renormalized to gross 1 moves a name's
weight by far more than its alpha rank moves, and the hedge is re-solved every rebalance, so
a small move in the signal becomes a large move in the book.

That is the part no floor rule, no release band and no NAV touches, and it is where the
next experiment belongs: a **weight-level partial adjustment** (`w_traded = φ·w_held +
(1−φ)·w_target`, or the equivalent per-name band on trades of 25-50% of the change), which
is the mechanism the design book has through `phi` and the live construction does not have
at all. It is not built or tested here - the brief's variants are floor, NAV and trade-band
variants, and a partial adjustment is a different kind of change, because it trades away
the hedge's exactness on purpose.

## A live defect this study found: `EFB_FLOOR_RELEASE` cannot run

Setting the release band on makes `build_proposal` **raise** on the first rebalance where
the band binds:

```
ValueError: the enforced floor book fails its checks and must not trade:
            3 kept names are below their floor
```

`live/evening_job.py::floor_book_violations` (`:1200-1247`) ends with
`below_floor(shares, prices, dollar_floor, share_floor)` against the **full** floor, and
`build_proposal` (`:1888-1901`) raises when that list is non-empty. But the band exists to
keep a held name that is *below* its floor and above `release × floor`, so the check
contradicts the flag by construction. The band's own tests
(`tests/test_nov11_floor_band.py`) exercise `_releasable` and the fixed point directly, and
the one test that builds a whole proposal builds it with **the flag off**
(`floor_release=1.0`), which is why this has not been seen. Measured here: it fires on
**every** rebalance of F75 (12 suppressed violations over 28) and F50 (27 over 28), and on
F50+N2+B1 (27).

For this study only, the below-floor violation is dropped when the band is on (the other
four checks - dollar neutrality, the exact hedge, the idio share and the rank margin - are
kept), and the suppressed count is recorded per variant. **Nothing in `live/` or `efb/` was
edited**: the patch lives in the research script.

## The decision rule, and what it returns

**As written, no candidate qualifies - because B0 itself fails two of the three tests.**
The first ceiling (worst residual factor exposure ≤ 5% of NAV) is breached by *every*
variant including B0, with 23-30% on the worst day: that is the hedge decaying between
rebalances, a property of the 21-session cadence that all ten variants share. The second
(worst single-name variance share ≤ 15%) is also breached by B0 at **25.5%**, because the
10% variance-share cap is applied to the *sized* book before the floor drops names and
renormalizes onto a subset, and is never re-applied afterwards - the build's own manifest
says so (`variance_share_cap_binds: true`, `max_variance_share` 19% on 2025-06-02). A rule
no candidate can pass cannot pick one. **This also corrects the cadence study's exposure
column**, which sampled exposure only every fifth rebalance and so reported 0.16% as the
monthly book's worst: measured every day, the held book's worst day is 23%, and the drift
is the difference.

So it is reported three ways, all in the JSON:

- **as written** (ceilings on the worst day of the whole hold): eligible = none.
- **at rebalance** (ceilings on the worst day right after trading): eligible = none; every
  variant still fails the variance-share ceiling, B0 included.
- **no worse than B0** on both risk measures, with `alpha ≥ 90%`: eligible = **B0, F50, N2,
  N5**; rejected are B1, F75, F75+B1 (variance share), N5+B1 and F50+N2+B1 (rebalance
  exposure), and B1 alone is worse on both.

Under that last reading the rule's own tie-break - **lowest turnover per rebalance** -
picks **F50**:

| | turnover/reb | cost bp/yr | saving vs B0 | monthly net at the design anchor |
|---|---|---|---|---|
| B0 | 87.02% | 69.1 | - | 169 − 69.1 − 100 = **−0.1** |
| **F50** | **72.23%** | **58.3** | **10.8 bp/yr** | 169 − 58.3 − 100 = **+10.7** |

## Is NAV the lever, or the floor rule?

**Neither is *the* lever, and they are not additive - but NAV is the cheaper of the two to
adopt, and the floor rule is the buggy one.**

- Floor rule alone: release 0.75 → −6.2 points of turnover and −4.4 bp/yr; release 0.50 →
  **−14.8 points and −10.8 bp/yr**.
- NAV alone: 2M → −8.4 points and −6.9 bp/yr; 5M → **−12.1 points and −9.0 bp/yr**.
- Both (F50+N2): −17.8 points and −13.9 bp/yr. Confirming the overlap: the two are not
  independent levers on the same names.

**NAV is the owner's question, and it is the cleaner one.** Raising the paper account to
5M needs no code change at all, removes 12.1 points of turnover, and *improves* every risk
column (variance share 47.1% → 37.6% on the worst day, 25.5% → 20.6% at rebalance, realized
vol 4.41% → 4.02%). The release band needs the live defect above fixed first, and at 0.50 it
is the boundary of what `resolve_floor_release` accepts (`FLOOR_RELEASE_MIN`).

The 36 points that neither touches are the real prize, and they are in the target book's own
movement - which is why the next experiment should be a partial adjustment, not another
floor setting.

## What adopting F50 would need in live code

1. **Fix `floor_book_violations`** to be band-aware: the below-floor test must be evaluated
   against `release × floor` for names the book already holds (`sticky`), which means
   passing `sticky` and `release` into `floor_book_violations` (`live/evening_job.py:1200`)
   from its caller at `:1888`. Without this, setting `EFB_FLOOR_RELEASE` fails the evening.
2. **Re-apply the variance-share cap after the floor**, or accept and document that the
   final book can hold 25% of the specific variance in one name. This is a separate defect
   this study found: the cap binds on the sized book and not on the book that trades.
3. **Add a test that builds a whole proposal with the flag on** - the unit tests of the mask
   do not catch either of the above.
4. Then set `EFB_FLOOR_RELEASE=0.5` in Render (owner-only, off by default today).

None of that is done here. The recommendation, if the owner wants one action now, is the
NAV question: at 5M the same construction trades 12 points less, with better risk numbers,
and nothing in the code changes.

## Reproducing it

```
cp -R <repo>/data /tmp/churn/data     # plus one dated SPY archive copy per session, as
                                     # the cadence study did (frozen universe)
PYTHONPATH=. .venv/bin/python scripts/churn_study.py run \
  --root /tmp/churn/data --out docs/research/churn_study.json
```

About 25 minutes: 10 variants × 28 builds of roughly five seconds, plus a daily
alpha/exposure/variance pass. Each variant is written to `churn_rows.partial.json` as it
finishes, so an interruption costs the variant in flight and not the ones already measured.
