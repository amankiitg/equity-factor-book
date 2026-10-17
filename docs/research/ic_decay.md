# How fast does the live signal decay? The IC term structure

Research only: no trading change, no flag, nothing merged, no deploy. The apparatus is
`scripts/ic_decay.py`, and every number in this note is in `ic_decay.json` beside it.

## What was measured

**The signal is `idio_momentum`, the one the live construction trades.** `live/evening_job.py`
reads it as `alpha_mod.idio_momentum(root)` (`SIGNAL` at `:43`, used at `:1778`), z-scores it
across the day's names and hands it to `alpha_from_contract` to form `alpha_vec`; the
manifest publishes it as `"signal": "idio_momentum"`. `efb/alpha.py:71` defines it as the
**compounded XS-v1 specific return over t-252..t-21** (`MOMENTUM_LOOKBACK` 252,
`MOMENTUM_SKIP` 21), built from `models/XS-v1/specific_returns.parquet`.

**Returns to predict**, two of them because the book is factor-neutral:

| what | file | column |
|---|---|---|
| total return | `processed/returns.parquet` | `r` |
| specific (residual) return | `models/XS-v1/specific_returns.parquet` | `specific_return` |

The **specific** IC is the one that decides the cadence: the hedge drives every factor
exposure to zero, so the book is paid for its residual picks and nothing else. The total IC
is reported beside it as the naive number a reader will expect.

**Universe: point-in-time membership**, `processed/universe_membership.parquet` (a daily
boolean frame, 2010-01-04..2026-10-02, 857 tickers, ~505 members a day). Every cross-section
is restricted to the names that were members on that date, so a name enters the sample only
while it was actually in the index: **no survivorship bias**. The model's own ticker set
(499 names in XS-v1) is the second restriction, because a name with no specific return has
no signal.

**Window: 2011-12-30 to 2026-10-02, 3,710 sessions, 14.72 years.** The model's specific
returns start 2011-01-03 and the momentum window needs 231 sessions before a signal exists,
which is why the studied period starts at the end of 2011. Breadth: **386 names a day on
average** carrying a signal (minimum 291, maximum 495) out of 388 members in the model's
ticker set.

**The measure is the cross-sectional Spearman rank IC per day**, then averaged across days.
A day is measured only if at least 30 names survive the membership and data filters.

## 1. The decay curve: lagged one-day IC, L = 1..21

IC(L) = rank correlation of the signal at t with the **one-day** return on session t+L.
Specific returns first, since that is the book's P&L:

| L | specific IC | t (naive) | t (Newey-West, bw 21) | total IC | t (Newey-West, bw 21) |
|---|---|---|---|---|---|
| 1 | 0.00420 | 2.62 | **2.73** | 0.01151 | **4.89** |
| 2 | 0.00410 | 2.57 | 2.67 | 0.01144 | 4.86 |
| 3 | 0.00378 | 2.37 | 2.46 | 0.01090 | 4.64 |
| 4 | 0.00368 | 2.31 | 2.39 | 0.01082 | 4.61 |
| 5 | 0.00371 | 2.33 | 2.42 | 0.01078 | 4.63 |
| 6 | 0.00382 | 2.40 | 2.51 | 0.01062 | 4.56 |
| 7 | 0.00388 | 2.44 | 2.54 | 0.01072 | 4.60 |
| 8 | 0.00371 | 2.34 | 2.42 | 0.01062 | 4.57 |
| 9 | 0.00369 | 2.32 | 2.41 | 0.01054 | 4.53 |
| 10 | 0.00358 | 2.26 | 2.34 | 0.01025 | 4.41 |
| 11 | 0.00344 | 2.17 | 2.24 | 0.01011 | 4.32 |
| 12 | 0.00346 | 2.18 | 2.26 | 0.01009 | 4.32 |
| 13 | 0.00350 | 2.21 | 2.29 | 0.01020 | 4.39 |
| 14 | 0.00351 | 2.22 | 2.29 | 0.01025 | 4.41 |
| 15 | 0.00360 | 2.28 | 2.35 | 0.01009 | 4.34 |
| 16 | 0.00353 | 2.24 | 2.30 | 0.01004 | 4.33 |
| 17 | 0.00337 | 2.14 | 2.16 | 0.00982 | 4.26 |
| 18 | 0.00339 | 2.15 | 2.20 | 0.00970 | 4.19 |
| 19 | 0.00331 | 2.10 | 2.14 | 0.00938 | 4.04 |
| 20 | 0.00320 | 2.03 | 2.08 | 0.00924 | 3.97 |
| 21 | 0.00314 | 2.00 | 2.05 | 0.00922 | 3.97 |

**Half-life: 63.8 sessions (about three months) on specific returns, 72.4 on total
returns**, from an OLS fit of `log IC(L)` on L over all 21 lags (specific: decay −1.09% a
day, implied IC at L=1 of 0.00400, R² 0.84; total: −0.96% a day, R² 0.93). The curve falls
25% from L=1 to L=21 on specifics and 20% on total returns in 21 sessions, so at this
horizon the decay is **slow and close to linear**: three quarters of the edge is still there
after a month.

The t-stats are honest about *why* they are as large as they are. A lagged one-day IC at a
fixed lag uses one return per day, and the resulting series is close to serially
uncorrelated (autocorrelation 0.04 at lag 1, −0.01 at 21), so its daily t is a real t:
**2.73 on specifics at lag 1**, and it stays above 2.0 out to L=21 with a bandwidth of 21,
and 2.7-3.1 for L=1 at bandwidths of 21, 63, 126 and 252. The total-return IC is stronger
everywhere, t ≈ 4.9 at L=1.

## 2. Cumulative IC: the same edge, overlapping windows

IC of the signal against the **compounded** return over t+1..t+h:

| h | specific IC | t (naive) | t (Newey-West, bw h+21) | total IC | t (Newey-West) |
|---|---|---|---|---|---|
| 1 | 0.00420 | 2.62 | **2.74** | 0.01151 | **4.91** |
| 2 | 0.00464 | 2.90 | 2.25 | 0.01225 | 3.73 |
| 5 | 0.00402 | 2.61 | 1.32 | 0.00943 | 1.84 |
| 10 | 0.00414 | 2.83 | 1.05 | 0.00609 | 0.89 |
| 21 | 0.00217 | 1.57 | **0.45** | 0.00151 | **0.17** |

Read this table with the naive column ignored. **A cumulative h-day IC shares h−1 of its
returns with its neighbour, and on this signal it shares far more than that**: the mean of
IC(1..21) has an autocorrelation of 0.93 at one day, 0.70 at five and 0.45 at ten, because
the signal itself barely moves (section 3). So a month's worth of cumulative ICs is one long
bet, not 3,700 of them: the Newey-West t at h=10 is **1.05** and at h=21 **0.45**. On total
returns the h=21 t is 0.17. The naive t of 2.8 is the number that would be wrong to quote.

Two things follow, and they matter for the cadence question. The point estimates are
**flat from h=1 to h=10** (0.0042, 0.0046, 0.0040, 0.0041) and only fall at h=21 (0.0022),
which says the same thing as the decay curve: a month-old signal still works, and the edge
does not concentrate in the first few days. And the statistics cannot resolve the last few
months of it: the cumulative columns cannot separate h=5 from h=21.

## 3. Signal rank autocorrelation: why the cadence study's turnover happens

Mean cross-sectional rank autocorrelation of the signal with itself at lag L, over members:

| lag (sessions) | 1 | 5 | 10 | 21 |
|---|---|---|---|---|
| rank autocorrelation | **0.994** | 0.973 | 0.947 | **0.892** |

The signal is a **232-session momentum window rolled one day at a time**, so consecutive
signals share 231 of 232 returns: the score for a given name is essentially frozen for a
month, and even at 21 sessions the cross-sectional ranking is 89% the same.

This is exactly what the cadence study's turnover numbers could not explain, and it
explains them: the *signal* is nearly constant, so the nightly 32.6%-of-NAV turnover is not
the target moving. It is the **book** being re-derived every night - the sizing, the
variance-share cap, the hedge and above all the share floor, which drops and admits names on
their dollar size in the renormalized book. A name whose signal has not changed can cross
the floor because the book it is renormalized against changed. That is why a band aimed at
resizes removed only a sixth of the turnover while hysteresis aimed at exits removed more
than half of it: the churn is in the kept set's membership, not in the weights.

## 4. Stability: the shape holds, the level does not

The same curve, computed inside each third of the history and over the last two years
(specific IC, L=1 then every fifth lag, then L=21):

| period | sessions | mean IC(1..21) | IC(1) | IC(5) | IC(10) | IC(15) | IC(21) |
|---|---|---|---|---|---|---|---|
| first third, 2011-01-03..2016-04-01 | 1,320 | 0.00379 | 0.0041 | 0.0036 | 0.0036 | 0.0043 | 0.0035 |
| second third, 2016-04-04..2021-06-29 | 1,320 | **0.00032** | 0.0012 | 0.0008 | 0.0006 | −0.0002 | −0.0004 |
| last third, 2021-06-30..2026-10-02 | 1,321 | **0.00675** | 0.0073 | 0.0067 | 0.0065 | 0.0068 | 0.0064 |
| last two years, 2024-10-02..2026-10-02 | 502 | **0.00904** | 0.0086 | 0.0083 | 0.0090 | 0.0095 | 0.0082 |

**The shape holds wherever there is a level; the level does not hold.** Every period that
has an edge shows a nearly flat curve across 21 sessions - no period shows the fast decay
that would justify daily trading. But the level moves by a factor of twenty: essentially
zero (and negative at the long lags) from 2016 to mid-2021, then the strongest of the whole
sample in the last five years, at 0.0068-0.0090. Anyone reading the full-sample 0.0036 has
to know that it is an average of a dead span and a good one.

## 5. Translating to cadence

Rebalancing every k days means the book trades on a signal that is 1..k days old, so what it
captures is the average of IC(1..k):

```
capture(k) = mean(IC(1..k)) / mean(IC(1..21))
gross(k)   = 169 x capture(k)            (the design backtest's monthly 169 bp/yr)
net(k)     = gross(k) - trading cost(k) - 100
```

Trading cost is the cadence study's own V1 (25% resize band) rows in bp/yr -
`docs/research/cadence_study.json` on `origin/research-cadence`, k = 1/5/10/21 →
434.60 / 174.09 / 117.60 / 66.30 - and borrow is pinned at the brief's 100 bp/yr. The 80%
interval is a 21-day block bootstrap of the IC days, 2,000 resamples, resampling each day's
whole 21-lag vector so the lags' cross-correlation survives the resample.

| variant | k | capture | gross bp/yr | cost bp/yr | borrow | **net bp/yr** | 80% interval | P(net>0) |
|---|---|---|---|---|---|---|---|---|
| V1 | 1 | 1.166 | 197.1 | 434.6 | 100 | **−337.5** | [−420.9, −243.8] | 0.7% |
| V1 | 5 | 1.082 | 182.9 | 174.1 | 100 | **−91.2** | [−156.9, −21.5] | 5.8% |
| V1 | 10 | 1.060 | 179.1 | 117.6 | 100 | **−38.5** | [−86.6, +5.3] | 11.9% |
| V1 | 21 | 1.000 | 169.0 | 66.3 | 100 | **+2.7** | +2.7 (see below) | 100% (vacuous) |

**The capture ratios are the headline.** 1.166 at daily, 1.082 at weekly, 1.060 at
fortnightly: a signal that is up to a month old captures **at least 93% of the edge it has at
one day old**, and roughly 90% at two weeks. Trading every day instead of every month buys
**17% more gross** (197 against 169 bp/yr) and costs **368 bp/yr more** in trading. The
decay cannot pay for the turnover; only the cost matters.

**Monthly's interval is a point, and it is not evidence.** capture(21) = 1 identically,
because 21 is the anchor, so the bootstrap has nothing to resample and the row's "+2.7" is
the arithmetic `169 − 66.3 − 100`. Its uncertainty is entirely the anchor's and the cost
model's, not the IC's. Two checks on that:

- **An honest band for the anchor.** At ±25% on the 169 bp/yr monthly gross, net(21) runs
  from **−39.6 to +44.9 bp/yr**. That is the real uncertainty of the monthly answer.
- **A second anchor.** The cadence study measured its own monthly V0 gross at 218.9 bp/yr
  (frozen-universe) instead of the design backtest's 169. Under that anchor: net(1) −279.4,
  net(5) −37.2, net(10) +14.4, net(21) **+52.6**. Same ranking, every net higher.

## Recommendation, against the stated rule

The rule: highest estimated net; if two intervals overlap by more than half, prefer the less
frequent.

**Chosen cadence: monthly (k = 21).** It has the highest estimated net (+2.7 bp/yr against
fortnightly's −38.5), and no pair of intervals overlaps by half: monthly's point sits 44 bp
above fortnightly's upper edge, and daily's and weekly's intervals are entirely below zero.

**Is any cadence clearly above zero? No.** This is the plain answer the brief asks for.
Daily, weekly and fortnightly are **clearly below zero** - daily's interval is
[−421, −244] and weekly's [−157, −22], neither of which can be rescued by any plausible
anchor. Monthly's point estimate is positive but tiny and untested: its interval is a point
by construction, and its ±25%-anchor band straddles zero (−39.6 to +44.9). So what the data
support is not "monthly makes money" but **"monthly is the only cadence whose cost does not
eat the signal, and it breaks even at the design anchor"**.

Two riders:

1. **Fortnightly is the only cadence whose interval contains zero rather than sitting below
   it** ([−86.6, +5.3], 12% of resamples positive), and it is the best cell in the cadence
   study's own table (+131.9 bp/yr there). If the owner's anchor is the higher one (218.9),
   fortnightly nets +14.4 and monthly +52.6; if the anchor error is ±25%, both move together.
   The IC study cannot separate them, because their capture ratios differ by only 6%
   (1.060 against 1.000) while their costs differ by 51 bp/yr. **The ranking is decided by
   cost, and on cost the ranking is monthly ≥ fortnightly > weekly > daily.**
2. **Nothing here justifies daily.** Even the last two years, where the IC is 2.5x the
   full-sample level, has capture(1) = 0.95 - i.e. **no decay at all** inside a month, so
   daily trading pays 368 bp/yr extra for an edge that has not faded. The cadence study saw
   the same thing from the P&L side.

## 6. Two cross-checks against the repo's own work, and one caveat it exposes

**The 169 bp/yr anchor is the repo's own number, not a placeholder.**
`docs/research/nov11_turnover.md` §1 measures the design book's edge at **169 bp a year at
gross 1.0** over 176 monthly rebalance dates (2012-01-31..2026-08-31, 462 names held on
average), before any cost. So `gross(21) = 169` is that book, and `capture(k)` scales it by
how much of the edge a k-day-old signal keeps.

**The churn is the construction's, and the turnover note says so from the other side.**
`docs/research/nov11_turnover.md` §4 and `nov11_cadence.md` measure the live loop trading
**~42% of gross every session**, about 25x the backtest's turnover per unit of time, and put
monthly-cost at 24 bp/yr for the design book's 35.6%-per-rebalance turnover. This study's
signal autocorrelation (0.994 at one day, 0.892 at 21) is the other half of that fact: the
*ranking* barely moves, so what trades is not the signal. It is the nightly re-derivation -
sizing, variance-share cap, hedge, and above all the share floor dropping and admitting
names on their size in the renormalized book.

**The caveat that follows, and it is a real one: the `cost(k)` column is the live
construction's, not the design book's, and it is worse.** The cadence study's monthly
rebalance still trades **87.0% of NAV** (`turnover_per_rebalance` at k=21 in
`cadence_study.json`), because the target it trades to is the *floor-constrained* book, which
has moved a long way in 21 sessions even though the signal has not. So monthly costs
**66.3 bp/yr** here against the design book's **24 bp/yr** for the same schedule. The
monthly net that the design book implies is therefore `169 − 24 − 100 = +45 bp/yr`, not the
`+2.7` this table prints: the difference is entirely the live construction's own churn, and
fixing that churn - not choosing a cadence - is worth about 42 bp/yr. That is a construction
question, and it is the one the numbers point at most strongly.

## Reproducing it

```
cp -R <repo>/data /tmp/icdecay/data          # a copy; never the repo's own tree
PYTHONPATH=. .venv/bin/python scripts/ic_decay.py run \
  --root /tmp/icdecay/data --out docs/research/ic_decay.json
```

37 seconds on one core: the signal is built by `efb.alpha.idio_momentum` itself, the IC day
loops are pure numpy, and the bootstrap is 2,000 x 21-day block resamples.
