# The monthly book's 23% exposure, partial adjustment, and a drift guard

Research only: nothing here trades, sets a flag, writes a store or deploys. The
apparatus is `scripts/churn_followup.py` and `scripts/exposure_diagnostic.py`; every
number below is in `churn_followup.json` beside this note. Window, cadence (k = 21),
universe (frozen at the 2026-09-18 SPY archive) and cost model are the churn
study's, imported rather than copied, so **B0 reproduces that study exactly**:
turnover 87.02%, cost 69.1 bp/yr, net 48.4, borrow 101.4, max exposure 23.03%.

P&L is indicative (2.33 years at 4.4% vol is ~280 bp/yr of standard error per cell).
The cross-variant comparison, which uses one universe and one cost model, is the
result.

## C1. The 23%: real drift, and a broken distribution

### The day and the factor

The churn study's worst day is **2026-06-30**, exposure **23.03%**, and the factor
is **`reversal`** (the 20-day return ending the day before): +23.0% of NAV on that
factor, with `momentum` +4.4%, `size` +3.0% and `market` +2.7% behind it. Seven of
the eight worst days are `reversal` too:

| date | exposure | factor | net / gross |
|---|---|---|---|
| 2026-06-30 | 23.03% | reversal +23.0 | 0.224 |
| 2025-02-28 | 20.23% | reversal +20.2 | 0.234 |
| 2026-07-31 | 19.26% | reversal −19.3 | −0.255 |
| 2024-09-30 | 17.95% | reversal −17.9 | −0.197 |
| 2025-03-31 | 16.59% | momentum +16.6 | 0.161 |
| 2026-02-27 | 16.29% | reversal +16.3 | 0.175 |
| 2025-06-30 | 15.87% | reversal +15.9 | 0.188 |
| 2026-08-31 | 15.79% | reversal −15.8 | −0.201 |

Every one is the **last session before a rebalance** (15-19 sessions since the
previous one), which is the whole point: the hedge is exact when the book trades
and decays afterwards. **The 28 rebalance days' worst exposure is 0.159%** - at
rebalance the book is neutral to machine precision.

### It is drift, not a loading outlier and not a stale price

On 2026-06-30 the exposure is spread over the book, not concentrated in one name:
`net / gross` is **0.224**, i.e. the signed sum is a fifth of the absolute sum. The
largest single contributions are GLW +6.3% (weight 2.60%, loading 2.42) and WDC
+6.3% (2.59%, 2.42), then CAH −3.2%, CIEN −2.8%, INTC +2.5%.

- **Not a loading outlier.** The loadings are **winsorized**: on that day 12 names
  sit at exactly **+2.4217** and 38 at exactly **−1.4682**, and the cross-sectional
  standard deviation is 1.001. GLW and WDC are at the cap, not past it; the
  exposure comes from *large weights on capped loadings*, several of them.
- **Not a stale price.** None of the top five names has a missing or zero return in
  the preceding 21 sessions (0 of 21 each), and their cumulative returns are large
  and real: GLW +39.7%, WDC +23.7%, INTC +23.4%, CAH +19.1%, CIEN −13.8%.
- **It is not the exposure function's scale.** The design's columns are
  cross-sectionally standardized (`std 1.001`), so `X'w` is in the same units the
  live page's `max_abs_exposure_after_fmp` uses; `21.8%` means a portfolio whose
  loading-weighted weight is 0.218.

The mechanism is the one the churn study names: the book is built on
`idio_momentum` (12-1 momentum) and then drifts for 20 sessions, and the names that
ran up are exactly the ones with the most extreme 20-day-reversal loadings. **The
book is long last month's biggest winners for most of every month**, which is a
real, sustained reversal exposure - not a one-day event:

| session (fixed 2026-06-30 design) | reversal exposure |
|---|---|
| 2026-06-18 | 23.62% |
| 2026-06-22 | 23.54% |
| 2026-06-23 | 22.36% |
| 2026-06-24 | 22.44% |
| 2026-06-25 | 23.17% |
| 2026-06-26 | 21.80% |
| 2026-06-29 | 23.04% |
| 2026-06-30 | 23.03% |

Holding the **design** fixed and letting only the weights move, the exposure is
21.8-23.6% across the whole month: the drift accumulated early and stayed.

### The distribution - and the artifact in it

`X'w` needs a design, and the frozen model publishes one **only on month-end
sessions**: `models/XS-v1/descriptors.parquet` has 190 dates over 15 years, median
gap **31 days**, and only **29** fall inside this 586-session window. On every
other session `race._design_from_styles` gets an all-NaN z, `nan_to_num` turns it
into zeros, and every **style** exposure is measured as exactly 0 (the sector
dummies still measure). That is why the previous day, 2026-06-29, reads
`this_factor = 0.0` while 2026-06-30 reads 23%.

So there are two distributions, and only one of them is about the book:

| | unchanged by this note (the study's) | **the book** (design days only) |
|---|---|---|
| days | 586 | **29** |
| median | 0.53% | **9.34%** |
| mean | 1.19% | - |
| p90 | 1.97% | - |
| p95 | 3.09% | **19.84%** |
| p99 | 15.94% | - |
| max | 23.03% | **23.03%** |
| share > 3% | 5.1% | - |

**The study's 0.53% median and 1.19% average are artifacts of the missing design,
not measurements of a usually-neutral book.** On the days the model can see, the
median exposure is **9.3%** and the 95th percentile **19.8%**. That is the honest
size of the monthly cadence's risk cost, and it is larger than the study said.

The practical consequence: **a daily drift guard cannot see what it is guarding
against**, because the design is monthly. That shapes C3 below.

## C2. Partial adjustment

`w_traded = phi * w_held + (1 - phi) * w_target`, then the minimum-norm projection
onto the design's null space (`delta = X (X'X)^+ X'w`, so `X'(w - delta) = 0`), so
the hedge stays exact on the session it trades. `phi` is the **held** share: 1.0 is
no adjustment, 0.5 is halfway to the target.

**The plain blend has a defect the brief's formula does not cover: nothing ever
leaves.** A name the target has dropped keeps `phi * w` and decays by `(1 - phi)` a
month, so the book's name count grows from **200 to 374** over the window and the
tail is names the alpha abandoned long ago. `P50T` is the same 0.5 with the exit
rule the blend needs - a name the target has dropped leaves at once - and it is the
variant to read.

## C3. The drift guard

On a hold day, if the held book's worst factor exposure exceeds **3% of NAV**, project
the held weights onto the neutral space with the minimum-norm change - a hedge-only
refresh, no re-selection, no re-sizing - and trade that. It fired **28 times in 28
month-ends**: with a monthly design, 3% is crossed on the one session a month the
exposure can be measured, so the guard degenerates into **a monthly re-hedge**, which
is exactly what the exposure needs. Its exposure "before" readings are 5.2%, 7.3%,
8.6%, 17.9%, 3.1% - the same 3-18% the book otherwise carries all month.

## C4. Every variant, the same metrics

Per rebalance, % of NAV; exposure is the held book, `p99`/`max` are the daily series
(all variants share the measurement artifact, so the comparison is fair);
`var max` is the worst single-name variance share.

| variant | phi | hedge | tov/reb | tov/yr | cost bp | borrow bp | net bp | alpha | expo p99 | expo max | var max | names |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **B0** | 1.0 | exact | 87.02% | 10.48 | 69.1 | 101.4 | 48.4 | 100.0% | 15.94% | 23.03% | 47.1% | 200 |
| B0H | 1.0 | cap_then_rehedge | 86.56% | 10.42 | 68.8 | 101.4 | 23.8 | 96.6% | 14.96% | 22.40% | 31.8% | 200 |
| P25 | 0.25 | exact | 65.39% | 7.87 | 51.3 | 100.9 | 26.8 | 115.6% | 14.54% | 27.44% | 38.1% | 374 |
| P50 | 0.5 | exact | 45.89% | 5.53 | 35.6 | 98.0 | −6.7 | 110.5% | 12.60% | 29.70% | 36.6% | 374 |
| P75 | 0.75 | exact | 26.50% | 3.19 | 20.5 | 92.4 | −92.2 | 86.9% | 10.72% | 24.19% | 35.8% | 374 |
| P25H | 0.25 | cap_then_rehedge | 65.03% | 7.83 | 51.1 | 100.8 | 13.3 | 113.1% | 13.42% | 26.98% | 31.1% | 371 |
| P50H | 0.5 | cap_then_rehedge | 45.68% | 5.50 | 35.6 | 97.8 | −19.7 | 109.2% | 12.31% | 29.14% | 36.8% | 371 |
| P75H | 0.75 | cap_then_rehedge | 26.39% | 3.18 | 20.5 | 92.3 | −96.1 | 81.7% | 11.32% | 24.17% | 34.8% | 371 |
| **P50T** | 0.5 | exact | 52.72% | 6.35 | 41.1 | 80.7 | 45.7 | 76.5% | 11.00% | 19.25% | 37.6% | 201 |
| **G3** | 1.0 | exact | 86.48% | 11.80 | 77.7 | 101.2 | 93.3 | 97.3% | 2.68% | 2.99% | 47.1% | 200 |
| **P50G3** | 0.5 | exact | 46.20% | 6.44 | 41.4 | 98.1 | 15.9 | 99.8% | 2.03% | 2.99% | 35.1% | 374 |

Turnover split, % of NAV per rebalance:

| variant | entries | exits | resizes |
|---|---|---|---|
| B0 | 12.01 | 11.18 | 14.23 |
| B0H | 11.84 | 11.00 | 14.38 |
| P25 | 2.53 | **0.00** | 25.59 |
| P50 | 2.20 | **0.00** | 17.53 |
| P75 | 1.87 | **0.00** | 9.52 |
| P50T | 6.78 | 8.12 | 7.77 |
| G3 | 11.96 | 10.84 | 14.39 |
| P50G3 | 2.20 | **0.00** | 17.67 |

The zeros are the defect: with the plain blend the book never exits a name, so the
split has no exits and the resizes carry everything. `P50T` restores exits (8.12%)
and drops resize turnover from 17.5% to 7.8%.

Ranked on **turnover and alpha retained** (the two the brief names):

| rank | variant | tov/reb | alpha retained | what it costs |
|---|---|---|---|---|
| 1 | P75H | 26.4% | 81.7% | alpha below the 90% floor; exposure still 24% |
| 2 | P50T | 52.7% | **76.5%** | alpha below the floor; **exposure improves to 19.3%** |
| 3 | P50G3 | 46.2% | **99.8%** | names 374 (blend artifact); exposure 3.0% |
| 4 | G3 | 86.5% | **97.3%** | +1.3 turns/yr and +8.6 bp/yr; **exposure 3.0%** |

`alpha > 100%` is the churn study's finding, not a bug: the floor drops names for
their size, so the names it discards carry above-average alpha. It is why the
metric cannot separate variants that keep the floor; it is only informative when a
variant trades *away* from the target, and then it bites (P50T 76.5%, P75 86.9%).

**`cap_then_rehedge` (`EFB_HEDGE_MODE`)** is worth knowing about because the owner
may turn it on: at monthly cadence it changes almost nothing on turnover
(86.56% vs 87.02%) and cuts the worst single-name variance share from **47.1% to
31.8%**, at a cost of 3.4 points of alpha retained. It does not touch the factor
exposure (22.4% vs 23.0%).

## C5. Borrow

**What the repo uses.** `efb/costs.BORROW_RATE = 0.02` - "2% per year on short
notional, the E6 provisional". It was introduced with the E9 cost model
(`5f2da22`, `feat(e9): the cost model, the capacity curve and the criteria`) and
is documented as an assumption in `docs/research/E9_tcost_capacity.md`: "Borrow:
2% per year on short notional, the E6 provisional." **There is no external source
behind the 2%.**

**What public evidence says.**

- **Alpaca, the broker the paper account runs on** (docs.alpaca.markets, *Margin and
  Short Selling*, updated 2026-09-17): "**$0 locate and borrow fees on all ETB
  shares** for Trading API users", with 5,000+ easy-to-borrow securities. S&P 500
  general-collateral names are the archetype of easy-to-borrow, so on this account
  the borrow line is **$0 for the names this book shorts**, unless a name is
  hard-to-borrow (which the precheck already drops or flags).
- **Typical general-collateral borrow fees for S&P 500 names**: I could **not**
  verify a rate from an authoritative public source. IBKR's stock-borrow pages
  answer 404 or a consent wall to a scripted fetch, and Investopedia's short-selling
  article (fetched) describes the fee without a rate. The industry convention is a
  spread over the overnight rate for GC collateral, but I will not state a number I
  could not read. The honest position is the one above: **the repo's 2% is an
  assumption, the account's own schedule is 0% for ETB names, and any number
  between is unverified.**

**The monthly net at the design anchor (169 bp gross)**, restated at four borrow
rates. Borrow scales linearly, so the table is `169 - cost - 101.4 x (rate / 2%)`:

| borrow rate | B0 | B0H | P50T | G3 | P50G3 |
|---|---|---|---|---|---|
| 0.25% | +87.3 | +87.5 | +117.8 | +78.7 | +115.3 |
| 0.50% | +74.6 | +74.8 | +107.7 | +66.0 | +103.1 |
| 1.00% | +49.2 | +49.5 | +87.5 | +40.7 | +78.6 |
| 2.00% (the repo's) | **−1.5** | −1.2 | +47.1 | −9.9 | +29.5 |

At the repo's 2% the monthly book is roughly flat; at Alpaca's 0% for ETB names it
is about **+100 bp/yr**. The borrow assumption is doing more work in this decision
than any construction variant.

## The recommendation

**Adopt the drift guard, not the partial adjustment, and fix the borrow assumption
before anything else.**

1. **The 23% is real and it is the cost of the cadence** - a sustained 20-24%
   `reversal` tilt for most of every month, measured on the 29 days a design exists.
   The study's 0.53% median was an artifact of the monthly descriptors, not a
   property of the book.
2. **G3 - the 3% drift guard - is the one change that removes it** (max 2.99%, p99
   2.68%) while keeping 97.3% of the alpha and leaving the rebalance turnover
   unchanged (86.5% vs 87.0%). It costs +8.6 bp/yr, and with a monthly design it is
   a monthly hedge refresh, which is precisely the defect it repairs.
3. **Partial adjustment is promising but not specified enough to adopt.** The
   brief's formula never exits a name, growing the book from 200 to 374 names; with
   the exit rule added (`P50T`) it cuts turnover 39% and *improves* the worst-day
   exposure to 19.3%, but it retains only 76.5% of the alpha - below the study's
   own 90% floor. That is a real trade, not a free lunch, and it needs its own
   study with a proper alpha metric before it goes near the live construction.
4. **The 2% borrow is unverified and probably too high for this account.** Alpaca
   charges nothing on easy-to-borrow names. Re-record `BORROW_RATE` from the
   broker's own schedule (or make it a flag) before the monthly net is used to
   decide anything: it moves the conclusion by more than the whole variant table.
