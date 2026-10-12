# Turnover and cost: what the backtest trades, what the live loop trades, and what
# each is charged

Item 12 and the first research question of the November 11 list, measured on the
committed artifacts and on the live store, read-only. Every number below is
reproducible:

```
.venv/bin/python scripts/nov11_turnover_research.py      # the backtest
.venv/bin/python scripts/nov11_live_churn_research.py    # the live loop's turnover and churn
.venv/bin/python scripts/nov11_live_cost_research.py     # the live book, priced by the same function
```

Design book: `rho = 0.02`, `phi = 0.95`, `seed = 3` (the registry's own picker,
`efb.allocate.pick_design_config`), 176 monthly rebalance dates 2012-01-31 →
2026-08-31, 462 names held on average, on a panel of 4,213 sessions.

## 1. The headline: the cost the research engine never charged

| cost stack (same book, same trades) | gross ann | net ann | vol | Sharpe gross | Sharpe net | turnover / reb | trading bp / yr | borrow bp / yr | total bp / yr |
|---|---|---|---|---|---|---|---|---|---|
| research engine: spread+commission+impact **on the trade**, no borrow (`efb/costs.py:282-296`) | 1.69% | 1.45% | 1.57% | 1.08 | 0.93 | 35.6% | 24 | **0** | 24 |
| live model, spread on the trade (adds borrow) | 1.69% | 0.46% | 1.57% | 1.08 | 0.30 | 35.6% | 24 | 99 | 123 |
| live model as written (spread+commission **on the held book**) | 1.69% | 0.04% | 1.57% | 1.08 | 0.03 | 35.6% | 66 | 99 | 165 |

The design book's edge, at gross 1.0, is **169 bp a year**. The live cost model
charges it **123 to 165 bp a year** for the privilege, and the difference between
the first row and the others is not a modelling detail:

- **The research cost model has no borrow at all.** `efb/costs.py::_trade_cost`
  sums `(spread + COMMISSION) * |Δw| + impact * |Δw|` and stops. The short leg's
  holding cost is absent from every net Sharpe the E-series ever quoted, including
  the 1.0 that picked this configuration. On the live formula
  (`live/evening_job.py:1132-1195`) borrow is `2% * short_gross * 21/252` = **8.33 bp
  per rebalance**, which is 99 bp a year at the monthly convention - **59% of the
  book's entire gross return** - and it is the single largest term in the split the
  page shows (14.20 bp of expected cost, of which borrow is 8.33).
- **The live model charges spread and commission on the book that is held**, once
  per rebalance, and only the impact on the trade. The research engine charges all
  three on the trade. On the same book and the same trades that is 24 bp a year
  against 66, and it takes the net Sharpe from 0.30 to 0.03.

Neither reading is obviously the intended one, and both cannot be right: a spread
is paid when a name is traded, while `live/evening_job.py:1160-1168` says in its
own docstring that these are "the cost of owning the position for the horizon, not
of establishing it". At a monthly rebalance the two conventions are within a factor
of gross/traded (2.8); **at the live loop's frequency (below) they are within a
factor of 1.**

## 2. The live loop does not trade the backtest's book at the backtest's frequency

`efb.positions`, every stored close, read-only:

| close | turnover of gross | traded notional (NAV ~$995k) | names left | names arrived | held |
|---|---|---|---|---|---|
| 2026-09-25 (establishment) | 100.0% | $995,415 | 49 | 74 | 175 |
| 2026-09-29 | 122.0% | $1,214,654 | 49 | 74 | 175 |
| 2026-09-30 | 42.6% | $423,763 | 32 | 35 | 178 |
| 2026-10-01 | 39.6% | $394,654 | 24 | 34 | 188 |
| 2026-10-02 | 42.8% | $426,235 | 28 | 44 | 204 |
| 2026-10-05 | 43.7% | $435,066 | 42 | 29 | 191 |
| 2026-10-06 | 36.7% | $365,480 | 28 | 32 | 195 |
| 2026-10-08 | 50.7% | $504,761 | 50 | 30 | 175 |
| 2026-10-09 | 38.5% | $383,273 | 35 | 19 | 159 |

The live loop trades **~40-50% of the book's gross every session** (57% including
the establishment), and 24-50 names leave the book every session while 19-44
arrive. The backtest trades 35.6% **once a month**. Per unit of time that is
`252 * 0.42 = 10,600%` of turnover a year against `12 * 0.36 = 428%`: **the live
loop turns the book over about 25 times as fast as the research panel it was
designed on**, which is the single largest difference between the backtest and the
thing that trades.

Priced by the same function (`scripts/nov11_live_cost_research.py`), per session:

| session | turnover of gross | research engine bp | live (spread on the trade) | live (spread on the held book) | borrow |
|---|---|---|---|---|---|
| 2026-09-30 | 42.6% | 2.82 | 11.19 | 6.10 | 8.33 |
| 2026-10-02 | 42.8% | 2.71 | 11.08 | 6.09 | 8.33 |
| 2026-10-08 | 50.7% | 3.03 | 11.39 | 6.07 | 8.33 |
| 2026-10-09 | 38.5% | 2.55 | 10.90 | 6.04 | 8.33 |

Two readings of the same numbers, and the horizon is the thing that decides which
is right:

- **As the model defines it** (one rebalance = one 21-session horizon, so 12 a
  year): the live book costs 145 bp/yr on the trade convention and 175 bp/yr as
  written - the same order as the backtest's 123-165 bp/yr, which is why the model
  looks consistent.
- **As the loop trades it** (a rebalance every session, so 252 a year): the same
  per-session charges annualize to **2,500-2,750 bp a year**, of which **2,100 bp
  is borrow alone**. A 2%-a-year borrow rate on a half-short book is 100 bp a year
  of actual cash, so the model's `HORIZON/TRADING_DAYS` factor is charging the same
  21 sessions of holding cost at every session: **at the live loop's frequency the
  borrow term overstates the annual cost by 21x, and the spread and commission
  terms (charged on the held book rather than the trade) by gross/traded ≈ 2.4x.**

That is not a rounding error and it is not only a reporting problem: the same
number is used to decide whether a night's trades are worth sending. The
empirical anchor agrees with the *trade* convention rather than the model's: the
morning reconciliation's own realized cost history averages **3.25 bp a session**
against the model's 5.86 bp of "trading cost expected for the same one session",
and the engine's convention on the live book's own turnover is 2.5-3.1 bp. The
model is charging roughly twice the trading cost the fills actually pay.

## 3. What a turnover control buys, on the stored books

Persistence, which the artifacts already carry:

| variant | gross ann | net ann | Sharpe gross | Sharpe net | turnover / reb | turnover / yr | trading bp / yr |
|---|---|---|---|---|---|---|---|
| phi = 0.0 | 1.70% | -0.26% | 1.04 | -0.16 | 141.3% | 1695% | 96 |
| phi = 0.8 | 1.58% | 0.15% | 0.94 | 0.09 | 65.2% | 782% | 44 |
| phi = 0.95 (the stored design) | 1.69% | 0.46% | 1.08 | 0.30 | 35.6% | 428% | 24 |

A no-trade band on each name's own change, same books:

| band | gross ann | net ann | Sharpe gross | Sharpe net | turnover / reb | trading bp / yr |
|---|---|---|---|---|---|---|
| 0 bp (the stored book) | 1.69% | 0.46% | 1.08 | 0.30 | 35.6% | 24 |
| 5 bp | 1.55% | 0.36% | 0.97 | 0.22 | 31.6% | 21 |
| 10 bp | 1.34% | 0.19% | 0.87 | 0.12 | 25.5% | 17 |
| 25 bp | 0.77% | -0.31% | 0.49 | -0.20 | 14.2% | 9 |
| 50 bp | 0.56% | -0.52% | 0.31 | -0.28 | 7.1% | 4 |

The live construction's 20-share floor at $1m NAV, with an entry/exit band
(admit at the floor, release only below `release x floor`):

| release | gross ann | net ann | Sharpe gross | Sharpe net | turnover / reb | names held | trading bp / yr |
|---|---|---|---|---|---|---|---|
| 1.00 x floor (today's rule) | 1.32% | 0.04% | 0.67 | 0.02 | 40.8% | 237 | 28 |
| 0.75 x floor | 1.26% | 0.02% | 0.66 | 0.01 | 36.6% | 255 | 25 |
| 0.50 x floor | 1.20% | -0.03% | 0.65 | -0.02 | 34.4% | 277 | 23 |
| 0.33 x floor | 1.19% | -0.03% | 0.66 | -0.02 | 33.9% | 293 | 23 |

Two things to read off that table, and the second is the one that matters:

1. **A band on the monthly signal is expensive**: the trades the band skips are
   the re-strike that carries the alpha. At 10 bp the gross return falls 35 bp a
   year for 7 bp of trading cost saved. On a *monthly* book a no-trade band is not
   a cost control, it is a different strategy.
2. **The floor itself is the expensive step at this NAV**: quantizing to whole
   shares with a 20-share floor renormalizes the book onto ~237 names and takes
   the gross Sharpe from 1.08 to 0.67, i.e. it costs more than any cost term here.
   The band on the floor is cheap and mildly helpful - at 0.5 x floor the book
   holds 40 more names than today, trades 6.4 percentage points less per rebalance
   and pays 5 bp a year less for it - which is the *opposite* sign to the
   signal-level band: releasing later keeps more of the book and cuts the churn.

The floor's churn on the **live** books, which is what item 12 actually asks
(`efb.positions`, nine closes): **147 round trips inside 21 sessions, over 112
distinct names**, mean 1.8 sessions away - **84 of the 147 returned the very next
session** - on a mean $7,582 of notional traded twice, **$1,114,508 of notional
traded twice in eight closes**. At the live trading rate that is **$653, or 6.6 bp
of NAV, over those eight closes** (0.8 bp a session) against a book whose own
gross edge at gross 1.0 is **0.67 bp a session**: the round-trip churn at the
floor costs *more than the entire gross edge of the book*, before any of the
signal-driven trading is counted.

## 4. The frequency question, answered as far as the artifacts allow

The panel's *signal* is monthly: 176 book dates, and every module holds a book
from one date to the next. A 2- or 5-session **signal** therefore cannot be built
from it without refitting the cross-section at those dates, which is a research
run rather than a measurement, so this doc does not claim one. What can be
measured, and is:

- **21 sessions is the monthly book**, and it is the cheapest of the schedules the
  artifacts support: 428% of turnover a year and 24 bp of trading cost on the
  engine's convention.
- **A 1-session schedule** is the live loop, and it trades ~42% of the book a
  session, ~25x the backtest's turnover per unit of time, for 2.5-3.1 bp a session
  on the engine's convention - about 6.5-7.8% of NAV a year, against a gross edge
  of 1.7% at gross 1.0 (10.9% at the 10% vol target). **Trading at 1-session
  frequency, the cost is most of the return; at 21 sessions it is 123 bp against
  169 bp, and it is still most of the difference between the design's gross Sharpe
  (1.08) and its net (0.30).**
- The controls that reduce the live loop's churn without touching the signal are
  the *floor band* (release at 0.5 x floor) and a minimum holding period: with 84
  of 147 round trips returning the next session, a one-session minimum would have
  prevented the majority of them at no cost to the monthly signal.

### Recommendation

**Do two things, in this order, and neither touches the signal.** (1) **Settle the
cost model's horizon**: the live loop trades every session while the model charges
spread, commission and borrow on a 21-session horizon, so the borrow is overstated
21x and the spread/commission by gross/traded; either state the horizon on the
face of every figure or charge per trade and per session. Until that is settled,
every "expected cost" the loop reports, every breakeven and every "is this trade
worth it" answer rests on a 21x error in its largest term. (2) **Add borrow to the
research engine's cost model** (`efb/costs.py::_trade_cost`), because the design
book was selected, and its Sharpe reported as ~1.0, on a cost model that charges
no borrow at all; on the live model the same book's net Sharpe is 0.30 and the
borrow is 99 bp of its 169 bp of gross return. Only after those two should the
frequency itself be changed: a rebalance schedule (or the floor band at 0.5) is
worth 25x of turnover, but the measurement above says the *first* fix is that the
two sides of the loop currently disagree about what a rebalance costs.

### Does the local tree's difference from the production seed matter?

Yes and no, and the distinction matters for how these numbers are quoted. The
repository's `data/` differed from the live seed bundle in 14 of its 19 files on
2026-10-09, so the *levels* here - 1.69% gross, 1.57% vol, 24 bp of trading cost -
are the committed research vintage's and are not the live tree's. Every
*comparison* in this doc is unaffected: the cost stacks, the bands, the floor
variants and the live book are all measured on one tree (or on the live store),
so the differences between rows are the treatment and not the vintage. The
conclusion is also structural rather than empirical - the loop's rebalance
frequency, the model's horizon assumption and the absence of borrow are facts
about the code, not about which day's returns are on file. Before any of these
levels is quoted as a live expectation it should be re-measured on the
regenerated seed, which is step 3 of the merge checklist and is blocked on a seed
push.
