# The rebalance cadence: the three options, and why the flag is not built

Item 12 and the turnover research both point at the same number: the live loop trades
~42% of the book's gross **every session** (`docs/research/nov11_turnover.md` §4), about
25x the backtest's turnover per unit of time, for 2.5–3.1 bp a session on the engine's
convention — 6.5–7.8% of NAV a year against a gross edge of 1.7% at gross 1.0. The
panel's own signal is monthly (176 book dates), so the *cheapest* schedule the artifacts
support is also the one the model was fitted on: 21 sessions, 428% of turnover a year
and 24 bp of trading cost.

Three schedules are on the table. They are not three settings of one switch, which is
why this is a memo and not a flag.

| | what the loop does | what `efb.positions` means | what the page and the bridge show | cost (engine's convention) |
|---|---|---|---|---|
| **nightly** (today) | prices a new target and trades to it every session | tonight's target = what the account should hold | identities hold; every leg accounted for | 2.5–3.1 bp a session, ~6.5–7.8% of NAV a year |
| **monthly** | prices a new target and trades to it on the month's last session; other sessions do nothing at all | the last target, unchanged | nothing to reconcile or report on 20 of 21 sessions; the page sits still, and a stalled cron looks exactly like a quiet month | 35.6% a month, 24 bp of trading cost a year, plus borrow over the month |
| **run nightly, trade monthly** | prices and publishes a new target every session, sends orders only on the cadence session | **ambiguous**: the target is tonight's model book, the account holds last month's, and the difference is a *decision not to trade* rather than a break | every non-cadence session would report the account against a book it was never asked to hold, so the positions check, the bridge's identities and the page's exception count would all be amber every night without anything being wrong | one month's book of trading, plus the modelling of the target each session |

## Why the third shape is the one that needs a decision rather than a flag

"Run nightly, trade monthly" is the shape that preserves the nightly *reporting* the
loop exists for, and it is the shape the November 11 list's item 20 guard already
assumes: a close whose legs are at the broker is not re-priced. But it splits one word
in two — the **book the loop publishes** and the **book the loop holds** — and today
`efb.positions`, the snapshot's `book`, the bridge's `kept` side and the page's sector
deltas are all one object. Implementing it means deciding, for each of them, whether it
means "the target" or "the target we are allowed to trade to", and then teaching the
bridge and the page the difference (a `not_traded_this_session` term, and a positions
check whose reference is the *held* book on non-cadence sessions).

That is a design change across the store, the bridge and the page, not a switch, and it
changes what every count on the page means. So it is not built here, and the flag is
not half-built either: a cadence switch wired into the submission path alone would
produce exactly the amber-every-night state in the third row of the table, which is a
page that cries wolf on the nights nothing is wrong.

## What is built, and what the numbers say to do first

- **Built**: item 20's guard (a close whose legs are at the broker is not re-priced) and
  item 19's status work (a refused leg is INCOMPLETE, filed, exit 0; an unconfirmed leg
  retries). Both are what a cadence change would need to lean on.
- **Not built**: the cadence switch itself, for the reason above, and item 12's floor
  band is built but **off**, with a measured negative result attached
  (`docs/research/nov11_turnover.md`, "The floor band as built").
- **The two things the measurement says to settle first**, neither of which is the
  cadence: the **cost model's horizon** (the live loop trades every session while the
  model charges spread, commission and borrow on a 21-session horizon, so the borrow is
  overstated 21x) and the **borrow in the research engine** (`efb/costs.py::_trade_cost`
  charges none, and the design book's ~1.0 Sharpe was selected on that model; on the
  live model the same book's net Sharpe is 0.30).
  Until the horizon is settled, "is this trade worth it" cannot be answered, and the
  frequency question is downstream of it: a schedule change is worth 25x of turnover,
  but the loop currently disagrees with itself by more than that about what a rebalance
  costs.

## If the decision is the cadence

The numbers for the shape that needs no new page semantics — **monthly**, where the
non-cadence sessions do nothing at all and the loop's own reporting is simply idle —
are the research engine's: 35.6% of gross a month, 4.28x a year, 24 bp of trading cost a
year against a 169 bp gross return, gross Sharpe 1.08 and net 0.93 on the engine's
convention (0.30 on the live one, because of the borrow). A one-session minimum holding
period is the cheapest way to take the floor's churn (84 of 147 round trips returned the
next session) out of the nightly shape without touching the signal at all, and it is a
smaller change than any of the three.
