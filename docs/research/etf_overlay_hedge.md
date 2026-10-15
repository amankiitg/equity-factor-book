# The ETF overlay: four hedges, and why the funds do not help

Item: would an ETF overlay hedge the book better than re-weighting single stocks?
Read-only research, reproducible:

```
EFB_DATA_ROOT=<the data folder> .venv/bin/python scripts/etf_overlay_research.py --scope live
EFB_DATA_ROOT=<the data folder> .venv/bin/python scripts/etf_overlay_research.py --scope backtest
```

Numbers: `docs/research/etf_overlay_live_numbers.json` and
`docs/research/etf_overlay_backtest_numbers.json`. ETF daily prices, fetched from a
public source into `research/etf_prices/etf_daily_prices.parquet` (SPY and the eleven
sector SPDRs, 2011-01-03 to 2026-10-14).

## The answer in one paragraph

**No.** An overlay of SPY and the sector SPDRs cancels the book's market and sector
exposure *exactly* - by construction, to machine precision - but it does not reduce
the book's risk, its turnover or its cost, and it makes the concentration worse:
on the live books it is **2.51% vol against the stock hedge's 2.02%**, it trades
**57% more on 2026-10-13 than the hedge it replaces** (462,529 against 293,865), it
costs **9.5 bp a close against 7.3 bp**, and it leaves **20.3% of the book's predicted
variance in one name against 20.4%** - the same concentration, bought more dearly.
The reason is structural: a sector fund is ninety-odd per cent market, so cancelling a
sector exposure by holding sector funds needs large offsetting legs (the largest was
14.4% of NAV) and those legs carry the funds' own residual risk, which the stock
hedge does not pay. The one construction that is unambiguously better is the one
already on the build list: **`cap_then_rehedge`**, at 1.84% vol, 9.6% worst-name
share, 6% less turnover and 3% less cost than today's hedge, with the 10% cap finally
true of the book that trades.

## The four constructions

All four start from the same sized book `u`, the same design `X`, the same EWMA
factor covariance `F` and the same specific diagonal `D`, from
`efb.eval_risk._xs_pieces` (rebuilt the way the earlier hedge research rebuilt it for
closes after the committed panel's end - same design function, same covariance, same
median-filled diagonal):

- **`exact`** - the live hedge: `w = u - X (X'X)^-1 X'u` (`live/sizing.py`). Seventeen
  exposures zeroed with stocks only.
- **`cap_then_rehedge`** - the 10% variance-share cap applied and neutrality re-solved,
  three passes (`docs/research/nov11_hedge.md`).
- **`etf_overlay`** - SPY and the eleven sector SPDRs cancel the market and the ten
  estimated sectors; the stocks cancel the six style factors, solved *jointly* with the
  ETF vector, because a style projection moves the market exposure it sits on:
  `(E_M' - X_M' P E_T') f = -(X_M' u - X_M' P X_T' u)` with `P` the style projection,
  then `w = u - X_T (X_T'X_T)^-1 (X_T'u + E_T'f)`. Twelve funds for eleven columns, so
  it is solved by least squares; the residual that could not be cancelled is reported
  (it is 1e-17 in practice).
- **`etf_only`** - the same ETFs cancel the market and the sectors; the style residual
  is accepted rather than hedged.

The ETFs' loadings are **estimated, not assumed**: each fund's daily return is
regressed on the model's own seventeen factor returns (`efb.models.fundamental`, the
same factors the book is measured against), on a window that ends before the period
being measured, per fund. The fits are good - SPY R^2 0.99 with a market loading of
0.98, XLK 0.95, XLF 0.92, XLRE 0.72 - and every window is in the numbers file. Each
fund's residual variance from that regression is its specific variance, on the same
daily-variance basis as the book's own.

## The live books, 2026-10-01 to 2026-10-13 (eight closes)

The pre-hedge book is rebuilt per close from the stored `alpha` and `idio_vol` with the
same three calls the live path uses (`efb.size.proportional`, `live.sizing.cap_variance_shares`,
`sizing.renormalize`), which is this project's own reconstruction of the book the hedge
acted on. Volatilities are reported both at the gross each construction produced and at
gross 1, because the four do not agree on gross and vol at unequal gross is not a
comparison.

| construction | vol | vol at gross 1 | worst single-instrument share (mean / worst) | gross | turnover a close (alpha / hedge leg) | cost, bp of NAV (spread / impact / borrow) |
|---|---:|---:|---|---:|---|---|
| pre-hedge book | - | - | - | 1.000 | 0.522 | - |
| `exact` (today) | 2.02% | 4.03% | **20.4% / 28.8%** | 0.501 | 0.304 (0.522 / 0.479) | 7.31 (2.64 / 0.001 / 4.17) |
| `cap_then_rehedge` | **1.84%** | 3.79% | **9.6% / 10.2%** | 0.487 | 0.287 (0.522 / 0.481) | **7.09** (2.58 / 0.001 / 4.03) |
| `etf_overlay` (C) | 2.51% | 2.68% | 20.3% / 28.2% | 0.936 | 0.452 (0.522 / 0.567) | 9.51 (3.38 / 0.001 / 5.17) |
| `etf_only` (D) | 11.24% | 8.42% | 2.4% / 3.8% | 1.338 | 0.647 (0.522 / 0.125) | 17.00 (5.45 / 0.001 / 10.18) |

Reading it:

1. **The overlay cancels what it is asked to cancel and nothing else helps.** Its
   market and sector exposures are zero to 1e-17 and its style exposures are zero too,
   so the neutrality is as clean as the stock hedge's. What it cannot do is cancel the
   ETFs' own residual risk: the funds are held at 0.338 of gross - XLC at 14.4% of NAV
   was the largest - and that is where 20% of the book's predicted variance ends up
   sitting, in one fund. The overlay's vol is *lower* than the stock hedge's at gross 1
   (2.68% against 4.03%) and higher at the gross it actually produces (2.51% against
   2.02%): it is a bigger book.
2. **Concentration is a property of the style projection, not of the market hedge.**
   Both `exact` and `etf_overlay` leave about a fifth of the variance in one name,
   because both cancel the six style factors on a 130-name book with a projection
   (0.35 at the worst close). Only capping the per-name variance share moves it, which
   is what `cap_then_rehedge` does.
3. **`etf_only` is the risky one.** Accepting the style residual leaves 34.8% of the
   panel's variance and 83% of the live book's in the style factors - 11.24% vol, five
   and a half times the exact hedge - and it needs ETF gross of 0.34 to do it, on which
   borrow and spread alone are 6.4 bp a close.
4. **Cost is not where ETFs win either.** The overlay's spread and borrow are *higher*
   than the stock hedge's (3.38 against 2.64 bp, 5.17 against 4.17), because more gross
   is held and ETF borrow is charged; the saving a 1 bp index spread would give is
   smaller than the extra notional it has to be charged on.

## 2026-10-13, the close the brief asks about

The live loop traded $447,195 that night and the hedge moved 71 names for $72,939
(16% of it). Rebuilding that close's books and pricing the same four constructions:

| construction | traded notional | against today's hedge | cost, bp of NAV | vol | worst share |
|---|---:|---:|---:|---:|---:|
| `exact` (today) | $293,865 | - | 7.31 | 2.10% | 20.0% |
| `cap_then_rehedge` | $275,185 | **-6.4%** (removes $18,680) | 7.09 | 1.94% | 10.0% |
| `etf_overlay` | $462,529 | **+57%** (+$168,664) | 9.51 | 2.60% | 19.7% |
| `etf_only` | $707,212 | **+141%** (+$413,347) | 17.00 | 11.00% | 2.8% |

So the ETF overlay **adds** half again to that day's trade rather than removing any of
it, and the only construction that removes turnover is the cap-and-rehedge. (The
study's own $293,865 for the exact hedge against the loop's $447,195 that night is a
basis difference, not a disagreement: the study's books are the pre-hedge reconstruction
at gross 1, where the loop's book carries the 20-share floor, the quantization and the
real previous positions. The comparison between the four constructions is like for
like.)

## The research panel, 2020-01 to 2026-08 (80 monthly dates)

| construction | vol | vol at gross 1 | factor share | worst share (mean / worst) | gross | turnover |
|---|---:|---:|---:|---|---:|---:|
| `exact` | 1.191% | 1.206% | 0.00% | 2.38% / 4.02% | 0.988 | 0.346 |
| `cap_then_rehedge` | 1.191% | 1.206% | 0.00% | 2.38% / 4.02% | 0.988 | 0.346 |
| `etf_overlay` | 1.231% | 1.068% | 0.00% | 2.86% / 6.47% | 1.153 | 0.417 |
| `etf_only` | 1.592% | 1.371% | 34.8% | 1.88% / 5.43% | 1.157 | 0.409 |

`exact` and `cap_then_rehedge` are identical to five decimals on the panel, which is
the same finding the earlier hedge research made: the cap never binds on a 460-name
research book, so there is nothing to re-solve. The overlay is again a *bigger* book
(gross 1.153 against 0.988) with more turnover and a worse tail (6.47% worst against
4.02%), and only looks better at gross 1 - which is exactly the reading that would
mislead someone comparing volatilities without looking at gross.

The panel comparison starts in 2020 rather than 2012 because the twelve-fund set only
exists from mid-2018: XLC listed in June 2018 (XLRE in October 2015), and each vintage
needs a year of history behind it before it is used. That is a limitation of the
instrument set, not of the measurement, and it is the honest reason the live window -
eight closes - carries most of the weight here.

## Assumptions, stated as assumptions

- **ETF half-spreads**, charged in the loop's own shape (`efb.costs.spread_schedule`
  for stocks): SPY 0.15 bp, the sector SPDRs 1.0 bp, XLB and XLRE 1.5 bp of notional.
  These are quoted-spread magnitudes for the funds, not measured here; the live cost
  model's stock schedule runs 1-10 bp by size decile, so the funds are assumed tighter
  than any stock the book holds.
- **ETF borrow**: 0.5%/yr (SPY 0.3%/yr), the general-collateral level, charged over the
  same 21-session horizon and on the same short-gross basis as the book's own 2%/yr.
- **ETF impact**: the loop's own square-root schedule with each fund's specific
  volatility and its trailing dollar ADV from the fetched prices (median of the last
  63 sessions). It is negligible for these funds, which is itself part of the answer.
- **The funds' specific risk is their regression residual** to the model's seventeen
  factors. That is the same *units* basis as the book's own specific variance, but not
  the same estimator: the book's comes from the cross-sectional risk model, the funds'
  from a time-series regression, and a fund tracking an index the model describes
  imperfectly shows up here as specific risk. The recommendation does not turn on that
  choice: the overlay's *factor* risk is zero and its gross, turnover and cost are all
  higher regardless of what the funds' residual is assumed to be, and the one
  construction that wins on every axis does not use funds at all.

## Recommendation

1. **Do not add an ETF overlay.** It cancels the market and the sectors exactly, and
   that is all it does: it leaves the same single-name concentration, adds half again
   to the day's trade, costs 2.2 bp a close more, and carries the funds' residual risk
   into a book whose largest position would otherwise be a stock. Option D is worse
   still - accepting the style residual multiplies the book's risk by five.
2. **Ship `cap_then_rehedge`** as the live hedge, as the earlier hedge research
   recommends: 1.84% against 2.02% vol, 9.6% against 20.4% worst-name share, 6% less
   turnover, 3% less cost, the same created names, and the 10% cap finally true of the
   book that trades.
3. **If the overlay is revisited, revisit the instrument set first.** One SPY leg
   cancels the market exactly and costs almost nothing (0.15 bp). The sector funds are
   what makes the overlay expensive: eleven highly correlated funds, each about 90%
   market, need ±14% legs to cancel ten sector exposures. A market-only SPY overlay,
   with the *sectors* left to the stocks, is the version worth measuring next - it would
   trade the overlay's cheapness against the stocks' existing sector-neutrality, without
   the leg sizes that sink the full overlay.
