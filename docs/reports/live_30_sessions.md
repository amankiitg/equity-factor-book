# Live book: first 30-session track record

Window: 2026-09-30 to 2026-11-10 (clock day 1 through the 30th trading day).

## Provenance and units

- Data source: the public snapshot at https://efb-live-book.nutritrack.workers.dev/api/snapshot only, generated_at 2026-11-10T22:49:39Z (measured). Sections used: attribution.live.daily, attribution.live.cumulative, attribution.live.by_factor, attribution.live.cost, attribution.live.risk, run_status.cadence, reconciliation.
- Tagging: "(measured)" is read straight from the snapshot; "(derived)" is computed from snapshot values by the stated formula; "(chosen)" is a constant picked here, with the choice stated.
- Units: P&L and cost are in basis points of NAV, where 1 bp = 0.01%. A daily figure is a one-day fraction. Volatilities are annualized unless a day is stated.
- No identifiers or account details appear. All figures are scale-free (bps, percent, ratios).

## Window

The clock's day 1 is 2026-09-30 and its 30-trading-day window ends 2026-11-10 (measured from live/clock.json, matching the report window). The snapshot's live attribution series runs 2026-10-01 through 2026-11-10, 29 sessions (measured: first_day 2026-10-01, last_day 2026-11-10, n_days 29). The snapshot notes that 3 rehearsal sessions before 2026-10-01 are stored and excluded. The 2026-09-30 flip session is clock day 1 but carries no separate daily P&L row in the snapshot, so every daily figure below is over 29 sessions. That one-session gap is listed under Live verification pending.

## 1. Cumulative P&L and daily statistics

Cumulative over the 29 sessions (measured, attribution.live.cumulative):

| Component | bps | percent |
|---|---|---|
| Total | -209.17 | -2.09% |
| Factor | -0.02 | -0.00% |
| Stock-specific | -60.93 | -0.61% |
| Cost | -147.51 | -1.48% |
| Unexplained residual | -0.70 | -0.01% |

The three components plus the residual add to the total (derived check: -0.02 - 60.93 - 147.51 - 0.70 = -209.17 bps).

Daily P&L statistics over the 29 sessions (derived from attribution.live.daily):

| Statistic | Value | How |
|---|---|---|
| Mean daily P&L | -7.21 bps | mean of pnl_total (derived) |
| Daily volatility | 17.18 bps | standard deviation of pnl_total, ddof=1 (derived) |
| Annualized volatility | 2.73% | 17.18 bps times sqrt(252); the 252 is chosen as the standard factor |
| Worst day | -41.17 bps | 2026-10-09 (measured) |
| Best day | +41.57 bps | 2026-11-04 (measured) |
| Max drawdown | -246.10 bps (-2.46%) | peak-to-trough of cumulative pnl_total, peak 2026-10-01, trough 2026-11-03 (derived) |
| Hit rate | 34.5% | 10 of 29 days positive (derived) |

Reading: the total loss is -2.09%, and the largest single piece is cost (-1.48%), more than twice the stock-specific loss (-0.61%). The factor leg is essentially zero (-0.02 bps), so the hedge held across the window.

## 2. Two regimes side by side

Regime boundary (measured, run_status.cadence): the book rebalanced daily through the 2026-10-23 close (the anchor), then switched to a monthly calendar (k = 21 sessions) with a drift guard from 2026-10-26. The next scheduled rebalance is 2026-11-23 (measured).

| | Daily (through 2026-10-23) | Monthly with drift guard (from 2026-10-26) |
|---|---|---|
| Sessions | 17 (measured) | 12 (measured) |
| Rebalance days in window | 17 (derived, every session) | 0 (derived, all hold days) |
| Cost per day | 7.95 bps (derived) | 1.03 bps (derived) |
| Total P&L in window | -173.27 bps (measured sum) | -35.90 bps (measured sum) |

Cost-per-day worked example, inputs labelled before outputs.

Inputs (measured, attribution.live.cost):

- Expected trading cost = 3.49 bps per rebalance.
- Expected borrow cost = 5.30 bps, the short leg's annual rate over one 21-session hold (the horizon the live cost model prices).
- Expected total per rebalance = 8.79 bps (trading plus borrow).
- Realized cost = 7.31 bps, the mean over the 19 days a realized cost exists.

Outputs (derived from the daily pnl_cost column):

- Daily regime: 17 sessions, summed pnl_cost -135.11 bps, so cost per day = 135.11 / 17 = 7.95 bps.
- Monthly regime: 12 sessions, summed pnl_cost -12.40 bps, so cost per day = 12.40 / 12 = 1.03 bps.

Reading: the daily regime pays the full rebalance cost every session (measured 7.95 bps per day, close to the 8.79 bps expected rebalance cost). The monthly regime pays no trading cost on its 12 hold sessions and only small carry (measured 1.03 bps per day), a roughly 7.7x lower cost drag (derived: 7.95 / 1.03).

Drift guard (measured, run_status.cadence.drift_guard): threshold 5% exposure, current exposure 4.05%, not fired, 0 forced trades and 0 turnover in the window.

Caveat (Live verification pending): the measured monthly carry of 1.03 bps per day sits far below the 5.30 bps forecast borrow, and 2 of the 12 monthly sessions carry zero cost. Whether the forecast borrow overstates the realized accrual, or the accrual is recorded elsewhere, needs the store, so it is left pending.

## 3. The 2026-11-05 market drop

The snapshot's market factor return that day is -5.14% (measured, daily market_return). The brief cited the S&P 500 at -4.4%; the two are not the same series, and -5.14% is the figure the attribution uses.

The book that day (measured, attribution.live.daily for 2026-11-05):

| Line | bps |
|---|---|
| Total P&L | -14.47 |
| Factor P&L | +0.26 |
| Stock-specific P&L | -14.86 |
| Cost | +0.14 |

What it says about the hedge: on a day the market factor fell 5.14%, the book's factor P&L was +0.26 bps (essentially zero), so the hedge neutralized the market and factor exposure. The loss that day was stock-specific (-14.86 bps), which is the risk a factor hedge is not designed to remove. The hedge did its job; the signal's own risk did the damage.

## 4. Realized versus predicted volatility, and the bias statistic

Volatility, annualized (the 252 annualization factor is chosen as standard):

- Predicted (forecast) volatility, mean over the 25 days that carry one: 2.75% (measured mean).
- Realized volatility, full sample: 2.73% (derived, standard deviation of daily P&L times sqrt(252)).
- Latest day, 2026-11-10: forecast 2.71% versus realized 2.74% (measured), ratio 1.01 (derived).

Realized volatility matched predicted volatility over the window (ratio near 1.00).

Bias statistic: not enough data yet (25 of 30). The bias engine needs 30 finite forecast observations before it computes the statistic; 25 of the 29 sessions carry a finite forecast (measured), so the statistic stays null.

## 5. Verdict

Thirty sessions (29 attributed days) cannot distinguish skill from noise, and the honest read is that they do not try to. The stock-specific edge, the only part that is the signal, is -2.10 bps per day (measured) with a daily dispersion of 18.91 bps; the t-statistic against zero is -0.60 (derived), far below the 2.0 bar the project uses, so no skill is claimed and the verdict is luck (measured verdict string from the attribution code's skill test). The annualized information ratio is -1.76, and the annualized Sharpe on total P&L is -6.66, dominated by cost rather than signal. For scale, the project's days-to-detect table (chosen bar t = 2.0) says an information ratio of 1.0 would need about 1,008 days (roughly 4 years) and 0.25 would need about 16,128 days to clear that bar; 29 days is a noise sample for any realistic edge.

What 30 sessions can and cannot tell us:

- They can show the machinery ran end to end, the hedge held (factor P&L near zero through a 5% market drop), realized volatility matched forecast, and cost is the dominant drag.
- They cannot say whether the signal is real. A specific mean of -2.10 bps per day with a standard error of 3.51 bps is consistent with a true edge of zero, and with a small positive or negative edge. Nothing here asserts skill, and nothing here rules it out.

## Live verification pending

Anything that needs the store is listed here rather than asserted:

1. The 2026-09-30 flip session (clock day 1) has no daily P&L row in the snapshot's live series. Only the store's attribution table can show whether it was attributed separately or folded into 2026-10-01.
2. The monthly carry (measured 1.03 bps per day) versus the forecast borrow (5.30 bps per 21-session hold) needs the fill and borrow-accrual detail in the store to reconcile.
3. The 2026-11-05 market return: the snapshot's market factor is -5.14% while the brief cites the S&P 500 at -4.4%. Confirming which market series the attribution uses needs the factor-return artifact, not the snapshot.
