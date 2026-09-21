# E6 Hedge Effectiveness Study

Sprint E6 of the Equity Factor Book. Every number in this memo is stored in
`data/hedge/` or in `sprints/E6/RESULTS.json` and is pinned to those artifacts
by `tests/test_e6_memo.py`. The champion risk model is provisional (F5.1
failed), so every headline result is reported under XS-v1 and under the
alternative XS-v2 with the difference stored.

## The answer, in one paragraph

The full FMP hedge is exact in model: it drives the worst absolute factor
exposure of both seed books to 5.8e-15 and lifts the idio share of variance
to 100.0%, but it trades 461.9 names on average, which is why it is unusable
in practice. The ETF minimum-variance hedge removes 97.85% of the factor
variance of the long-only seed book with 13.0 instruments on average, at a
mean monthly cost of 0.0017 of the hedged notional; it removes only 42.81% of
the momentum book's factor variance because the momentum, size and liquidity
tilts are not spanned by the ETF set. Realized, the hedged momentum
long/short book has a beta to Mkt-RF of -0.0272 over 2018 to 2026 against
-0.0495 unhedged, so the hedge works on the data the criterion is stated on.
The recommended policy is the ETF minimum-variance hedge on a monthly
cadence for the long-only book, the exact FMP hedge replaced by its capped
as-stored form only when name count matters more than residual exposure, and
no beta hedge for the momentum book, whose realized beta is already inside
plus or minus 0.1.

## What was hedged and with what

Two seed books from E5: `seed_ew`, the survivorship-caveated equal-weight
book, and `seed_mom_ls`, the monthly re-sorted momentum long/short book.
Three hedges per rebalance date on the E5 race grid of 175 month ends from
2012-01-31 to 2026-07-31:

- the full FMP hedge, built in two forms: the exact in-model one, which
  subtracts x_k of each factor-mimicking portfolio rebuilt on the rebalance
  date's own design, and the as-stored one, which uses the quarterly capped
  FMP weights and keeps their cap drift;
- the ETF minimum-variance hedge over SPY, IWM, QQQ and the eleven sector
  SPDRs, with each instrument's factor exposure fitted on the trailing 504
  sessions;
- the single-factor beta hedge against SPY.

The provisional cost model is 5 bps per unit of hedge turnover plus 2% per
year on short notional; both constants are E9 provisionals and are replaced
by the E9 transaction cost model when it exists.

## Before and after: the FMP hedge

In model, the exact FMP hedge is zero by construction: the worst absolute
post-hedge exposure across every rebalance date, factor and seed book is
5.8e-15, and the idio share of variance after the hedge is 100.0% under both
models. The stored numbers are in F6.1.

The as-stored quarterly capped FMP weights are a different instrument: their
worst absolute post-hedge exposure is 0.7552 on the reversal factor of the
momentum book, higher than the unhedged 0.7169 on that date, because the
design has drifted since the FMPs were stamped and the caps removed the
exact spanning property. That cap drift is basis risk, reported rather than
hidden, and it is the reason the exact hedge, not the capped one, is the
number F6.1 scores.

Both forms trade the whole cross-section: the mean name count is 461.9.
Mean monthly turnover is 0.7640 for the long-only book and 0.7925 for the
momentum book, with mean monthly cost 0.0017 and 0.0011 of notional. The
hedge is exact in model and unusable in practice, exactly as the roadmap
says to understand before implementing.

## Before and after: the ETF minimum-variance hedge

The ETF hedge removes 97.85% of the factor variance of the long-only seed
book, above the 70% F6.2 threshold, with 13.0 instruments on average (the
instrument set grows from 12 to 14 as XLRE and XLC gain price history; the
per-date count is stored and missing instruments are never filled). Mean
monthly turnover is 0.820 and the mean monthly cost is 0.0017.

For the momentum book the same hedge removes 42.81% of factor variance. The
ETF set cannot span the book's own tilts: the residual per-factor exposure
after the instrument hedge, F6.5, is worst on size at 0.3816, liquidity at
0.3222, reversal at 0.1155 and momentum at 0.0503, while the market beta
residual is 0.0130. The sector residuals run from 0.0168 to 0.1337. These
numbers are the quantified answer to "ETFs cannot span every factor; the
residual is reported."

## Realized efficacy, 2018 to 2026

Realized beta to Mkt-RF, computed on the stored daily series:

- momentum book: -0.0495 unhedged; -0.0272 under the ETF hedge, -0.0025
  under the FMP hedge, 0.0075 under the beta hedge. F6.3 passes on the
  stored -0.0272.
- long-only book: 0.3326 unhedged; -0.2837 under the ETF hedge, 0.0125 under
  the FMP hedge, -0.0552 under the beta hedge.

The long-only book's realized series carries the E5 survivorship caveat: its
stored daily rows hold every member on every day, including names before
their prices exist, so under the E5 missing-data semantics (a held name with
a missing return makes the day missing) its realized return series is valid
only from 2025-10 under daily weights and only 188 usable days for the ETF
hedge. The momentum book's series is complete: 2156 usable days after 2018.
F6.3 is stated on the momentum book, and the momentum book's numbers are the
ones that carry the conclusion.

## Efficacy against rebalancing frequency

For the momentum book's beta hedge, realized beta to Mkt-RF by rebalance
frequency is 0.0065 at 5 days, 0.0075 at 21 days and 0.0139 at 63 days. The
hedge decays slowly; a monthly cadence costs a third of a weekly cadence in
turnover for 0.0064 of additional realized beta. The stored curve is in
F6_decay.

## Champion against alternative

The champion is provisional, so F6.4 stores every headline number under
XS-v1 and under XS-v2 with the difference. The differences are exactly zero:
the FMP idio share is 1.0 under both, the long-only ETF hedge removes
0.9785 under both, and the momentum realized beta is -0.0272 under both.
This is not an accident of storage: the hedges use only the factor block,
which the two models share, and the models differ only in the specific
block, which no hedge in this study touches. The sensitivity the criterion
asked for is therefore zero, and that is the finding: the hedge policy is
robust to the champion decision.

## Recommended hedge policy

- For the long-only book: the ETF minimum-variance hedge, monthly cadence,
  all available instruments. It removes 97.85% of factor variance for
  0.0017 of notional per month.
- For the momentum book: the ETF hedge removes only 42.81% and leaves the
  size, liquidity and reversal tilts; a manager who must flatten those uses
  the exact FMP hedge and pays the 461.9 name count. The capped FMPs are
  not a hedge: their worst residual exposure is 0.7552.
- The beta hedge is unnecessary for the momentum book, whose realized beta
  is 0.0075 hedged and -0.0495 unhedged, both inside plus or minus 0.1.
- Rebalance monthly. The 63-day decay costs 0.0139 of realized beta, and the
  turnover saving beyond monthly is not worth it.

## What would falsify this?

- The hedged momentum book's realized beta outside plus or minus 0.1 would
  mean the model exposures or the hedge ratios are wrong. The stored number
  is -0.0272, so this study stands.
- Hedge cost exceeding the value of the variance removed: the cost is
  stored per method per book and is below 0.0017 per month for every method;
  if the E9 cost model raises the constant, the long-only recommendation is
  the first to revisit.
- Hedge ratio instability: the positions are stored per date; a day-to-day
  ratio check belongs to the operation gate, not this sprint.
- If a future model version changes the factor block, every number here
  recomputes and F6.4's zero difference stops being zero, which is exactly
  what the criterion exists to catch.

## The criteria, as stored

| ID | Criterion | Verdict | Stored number |
|----|-----------|---------|---------------|
| F6.1 | Full FMP hedge drives every factor exposure below 1e-6 in absolute value and lifts the idio share of variance above 95%. | pass | worst 5.8e-15, idio share 100.0% |
| F6.2 | ETF minimum-variance hedge removes more than 70% of the factor variance of the long-only seed book. ETFs cannot span every factor; the residual is reported. | pass | 97.85% removed, residual per factor in F6.5 |
| F6.3 | Realized: the hedged momentum long/short book has a beta to Mkt-RF within plus or minus 0.1 over 2018 to 2026. | pass | -0.0272 |
| F6.4 | New in E6: every headline hedge result stored under the champion model and under the alternative model, with the difference stored. | pass | difference 0.0 on every headline |
| F6.5 | New in E6: the residual factor exposure the instrument set cannot reach, quantified per factor. | pass | size 0.3816, liquidity 0.3222, reversal 0.1155, momentum 0.0503 |
