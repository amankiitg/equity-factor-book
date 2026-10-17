# Does the book need to trade every day?

Research only: no trading change, no flag, nothing merged, no deploy. The apparatus is
`scripts/cadence_study.py`; the numbers in every table are in `cadence_study.json` beside
this file, and every one of them is reproduced by the two commands at the end.

## What was measured, and on what

The live construction's own target book, one per session, built with
`live.evening_job.build_proposal(store=False)` - every `EFB_*` flag unset, NAV fixed at
1,000,000, the same code the evening run executes. Then holding:

- every **k** sessions, trade to that day's target under the variant below; on the days
  between, hold and let the weights drift with the session's returns;
- daily P&L is the held book times the next session's total return;
- costs are the same for every row, which is what makes the comparison mean anything:
  the size-decile half-spread and the commission from `efb.costs` on **traded** notional,
  square-root impact `k * sigma * sqrt(dollar / adv)` with `efb.costs.IMPACT_K`, and
  borrow accrued on the short gross every held day at `efb.costs.BORROW_RATE / 252`.

**The window is 2024-06-03 to 2026-10-02, 586 sessions, 2.33 years.** The live
construction refuses a close earlier than its newest SPY holdings archive ("no SPY archive
dated on or before ..."), and the local bundle's archives begin 2026-09-18, which would
leave twenty sessions. So the universe is **frozen**: the 2026-09-18 archive, dated for
every session in the window.

**Read that as a caveat on the levels, not on the comparison.** The universe is today's
SPY membership applied to the past, so the absolute gross and net figures are indicative
only - they carry the survivorship bias of a universe that was chosen with hindsight. The
result of this study is the **comparison across cadences and across variants**, which is
measured on one construction, one universe and one cost model throughout. The size of the
substitution is measurable where the real archives exist: on 2026-09-30 the native
universe builds 183 names against the frozen one's 180, with a largest weight difference
of 0.31% of NAV, and on 2026-09-25, 171 against 167 with 0.64%. A one-week-stale universe
moves a handful of names; a two-year-stale one moves more, and that is the caveat above.

## The table: four cadences, three variants

V0 trades fully to the target with today's $250 minimum leg. V1 adds a resize band: a
leg that resizes an existing holding by less than 25% of the name's target weight is
skipped (entries and exits always trade). V2 adds exit hysteresis: a held name absent
from the new target is kept at its current weight while the pre-floor full book still
holds it with the same sign, and closed otherwise.

| variant | k | turnover / rebalance | turnover / year (x NAV) | gross bp/yr | trading cost bp/yr | borrow bp/yr | net bp/yr | realized vol | net Sharpe | names held | residual factor exposure avg | max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V0 | 1 | 32.6% | 82.2 | 380.2 | 519.0 | 100.0 | **-238.8** | 4.25% | -0.56 | 200.6 | 9.3e-04 | 2.6e-02 |
| V0 | 5 | 58.0% | 29.4 | 338.8 | 190.0 | 100.2 | **48.6** | 4.34% | 0.11 | 201.1 | 8.4e-04 | 2.5e-02 |
| V0 | 10 | 75.3% | 19.1 | 356.8 | 124.5 | 100.4 | **131.9** | 4.35% | 0.30 | 201.8 | 5.1e-04 | 1.9e-03 |
| V0 | 21 | 87.0% | 10.5 | 218.9 | 69.1 | 101.4 | **48.4** | 4.41% | 0.11 | 199.6 | 4.6e-04 | 1.6e-03 |
| V1 | 1 | 27.4% | 68.9 | 430.8 | 434.6 | 98.2 | **-102.0** | 4.24% | -0.24 | 200.6 | 1.1e-02 | 3.8e-02 |
| V1 | 5 | 53.1% | 26.9 | 371.2 | 174.1 | 99.0 | **98.1** | 4.34% | 0.23 | 201.1 | 8.9e-03 | 2.7e-02 |
| V1 | 10 | 71.1% | 18.0 | 320.9 | 117.6 | 99.6 | **103.7** | 4.32% | 0.24 | 201.8 | 7.5e-03 | 2.6e-02 |
| V1 | 21 | 83.5% | 10.1 | 211.6 | 66.3 | 100.6 | **44.8** | 4.42% | 0.10 | 199.6 | 7.3e-03 | 1.9e-02 |
| V2 | 1 | 14.3% | 36.2 | 294.9 | 233.5 | 149.2 | **-87.9** | 6.83% | -0.13 | 305.4 | 6.2e-02 | 3.8e-01 |
| V2 | 5 | 37.3% | 18.9 | 149.2 | 123.6 | 148.7 | **-123.1** | 6.92% | -0.18 | 293.1 | 5.4e-02 | 3.1e-01 |
| V2 | 10 | 53.5% | 13.5 | 170.4 | 89.3 | 148.0 | **-67.0** | 6.73% | -0.10 | 286.0 | 5.5e-02 | 1.4e-01 |
| V2 | 21 | 67.3% | 8.5 | -47.2 | 53.7 | 146.6 | **-247.5** | 7.16% | -0.35 | 278.0 | 4.7e-02 | 1.1e-01 |

Three things the table says out loud:

1. **Daily is the expensive cadence, and the band is what fixes it.** V0 at k=1 pays
   519 bp/yr of trading cost to earn 380 bp/yr of gross, which is a net loss. V1's 25%
   band takes turnover from 32.6% to 27.4% of NAV per night and the cost from 519 to 435
   bp, and V2's hysteresis takes turnover to 14.3% and cost to 234.
2. **Exit hysteresis is not free.** V2 holds about a hundred names more than the target
   (305 against 201), which raises borrow (149 against 100 bp/yr), raises realized vol
   (6.8% against 4.3%) and breaks the hedge's neutrality badly: its worst residual factor
   exposure is **37.7%** of NAV at k=1 and 11.3% at k=21, against V0's 2.6% and 0.16%. A
   band on resizes (V1) costs an order of magnitude less neutrality, 3.8% worst.
3. **Longer is not simply cheaper.** Turnover per year falls with k as it must, but gross
   return falls faster: 356.8 bp/yr at k=10 against 218.9 at k=21. The signal is a
   horizon-1 one, and a month of holding spends it.

## The turnover curve T(k), and what it says

V0's turnover per rebalance at k = 1, 2, 3, 5, 10, 21:

| k | 1 | 2 | 3 | 5 | 10 | 21 |
|---|---|---|---|---|---|---|
| turnover per rebalance | 32.6% | 41.1% | 48.2% | 58.0% | 75.3% | 87.0% |
| turnover per year (x NAV) | 82.2 | 51.7 | 40.6 | 29.4 | 19.1 | 10.5 |

**The curve is not flat: it rises with k, from 32.6% to 87.0% of NAV per rebalance.** A
flat curve would have meant the daily target is so unstable that a week's worth of
turnover is one day's, i.e. pure noise at the cutoffs. Rising means each rebalance has
more to do the longer it waits - drift plus a target that has genuinely moved - so the
daily turnover is **not** just names flipping at the selection and floor cutoffs. It is
also not a bargain: the per-year line is what costs money, and it falls from 82.2x NAV at
daily to 10.5x at monthly.

## Where V0's daily turnover comes from

586 daily rebalances, split by leg kind, as a share of the total traded notional:

| entries | exits | resizes |
|---|---|---|
| 29.7% | 29.4% | 40.9% |

So **59% of the nightly turnover is names entering and leaving the book**, and 41% is
resizing the names that stay - which is why a band aimed at resizes alone (V1) removes
only about a sixth of the turnover, while hysteresis aimed at exits (V2) removes more than
half of it and pays for it in neutrality. The brief's hypothesis - that most of the daily
turnover is names flipping at the cutoffs - is **right about where it comes from** and
wrong about it being harmless: those entries and exits are the expensive part, and the
cheap way to trade less of them is not to hold stale names but to trade less often.

## The research engine's monthly backtest, for comparison

With borrow added to its cost model, that backtest was estimated at **net Sharpe about
0.30 against 1.08 gross**; this study's monthly cell (V0, k=21) is net Sharpe 0.11 - the
same direction and a lower level, on a different book (frozen universe, live
construction), and not a contradiction: the research engine's monthly book is a different
construction with its own selection and cost model.

## Recommendation

The rule: prefer weekly if its best variant's net is within 10 bp/yr of monthly's best or
better; otherwise monthly.

- Weekly (k=5), best variant V1: **+98.1 bp/yr** (net Sharpe 0.23).
- Monthly (k=21), best variant V0: **+48.4 bp/yr** (net Sharpe 0.11).
- Weekly is **49.7 bp/yr better**, so the rule says **weekly**, and the margin is not
  close: it is five times the 10 bp threshold.

Two riders the owner should see. **Fortnightly (k=10, V0) is the best cell in the table**
at +131.9 bp/yr and net Sharpe 0.30, 33.8 bp/yr above weekly's best - the rule did not
offer it, but it is where the construction's own numbers point. And **V1 is the variant to
carry**: it is at or near the best in every cadence it competes in, it costs about 3.8%
worst residual factor exposure rather than V2's 37.7%, and its band is a rule about one
name's trade, not about which names the book holds.

## Reproducing it

```
# one pass of target books, on a copy of the tree with a dated SPY archive per session
PYTHONPATH=. .venv/bin/python scripts/cadence_study.py targets \
  --root /tmp/cadence/data --start 2024-06-03 --end 2026-10-02 \
  --out /tmp/cadence/targets/frozen --passes 1 --workers 6
# the tables above
PYTHONPATH=. .venv/bin/python scripts/cadence_study.py simulate \
  --root /tmp/cadence/data --targets /tmp/cadence/targets/frozen0.jsonl \
  --json docs/research/cadence_study.json
```

The pass is ~100 minutes of six workers and writes each session as it finishes, so it can
be resumed after an interruption without rebuilding what is already there.
