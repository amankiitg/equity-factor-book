# E9 Transaction Cost and Capacity Analysis

The alpha is the E8 synthetic alpha with a known IC, labeled as such: no
real signal passed RG-Signal, so this book's real capacity is undefined.
The headline finding is that turnover, not AUM, is the binding constraint:
the synthetic z is i.i.d. across rebalance dates, so the proportional book
reshuffles about 140% of its gross each month, and at the Corwin-Schultz
half-spread that is roughly 4% of AUM per rebalance in spread cost alone,
which no IC in the experiment covers. The capacity curve is therefore
negative at every AUM and the halving AUM is undefined. The table still
answers the useful question: what turnover persistence a strategy needs
before a capacity number is meaningful.

## The cost model and its uncertainty

- Half-spread: the Corwin-Schultz (2012) high-low estimator, median over
  each name's 63-session windows.
- Impact: k * sigma * sqrt(dollar trade / ADV) with k = 0.5, stated with
  uncertainty [0.25, 1.0]; the sensitivity to k is stored under F9.4.
- Commission: 1 bp per dollar traded, one side.
- Borrow: 2% per year on short notional, the E6 provisional.

Cost parameters that free data cannot pin are stated as uncertainty, never
as a clean point estimate.

## Cost curves by size decile

| size decile | mean half-spread | mean market cap | mean ADV |
| --- | --- | --- | --- |
| 0 | 0.05181 | 2.75e+09 | 7.33e+07 |
| 1 | 0.03810 | 6.57e+09 | 7.8e+07 |
| 2 | 0.03302 | 9.75e+09 | 1.14e+08 |
| 3 | 0.03084 | 1.27e+10 | 9.71e+07 |
| 4 | 0.03029 | 1.69e+10 | 1.44e+08 |
| 5 | 0.02916 | 2.25e+10 | 1.32e+08 |
| 6 | 0.03189 | 3.14e+10 | 2.11e+08 |
| 7 | 0.03061 | 4.37e+10 | 2.75e+08 |
| 8 | 0.02694 | 7.34e+10 | 4.52e+08 |
| 9 | 0.02509 | 2.67e+11 | 8.93e+08 |

The Spearman correlation between the half-spread and the size rank is
-0.349: smaller names are wider, but
the per-name correlation sits below 0.5 because the Corwin-Schultz
estimator is noisy on the small names, the failure mode the roadmap named.

## The turnover versus IR trade-off

| rho | turnover cut | ex-ante IR loss |
| --- | --- | --- |
| 0.02 | 0.375 | 0.065 |
| 0.05 | 0.375 | 0.065 |
| 0.1 | 0.375 | 0.065 |

The penalized optimizer holds the low-alpha half of the book at its
previous weight. It cuts about 37% of turnover with under 7% ex-ante IR
loss, so the IR side holds but the 50% turnover cut does not: the book's
turnover is concentrated in its high-alpha names.

## The capacity table

The halving AUM per rho and impact coefficient:

| rho | k | gross Sharpe | halving AUM |
| --- | --- | --- | --- |
| 0.02 | 0.25 | 1.218 | nan |
| 0.02 | 0.5 | 1.218 | nan |
| 0.02 | 1.0 | 1.218 | nan |
| 0.05 | 0.25 | 2.831 | nan |
| 0.05 | 0.5 | 2.831 | nan |
| 0.05 | 1.0 | 2.831 | nan |
| 0.1 | 0.25 | 5.087 | nan |
| 0.1 | 0.5 | 5.087 | nan |
| 0.1 | 1.0 | 5.087 | nan |

Net Sharpe is not monotone in AUM (206
violations over 9 curves), while the net mean return is
monotone (0 violations): the
impact cost's cross-rebalance variance grows with AUM and inflates the
Sharpe ratio's denominator. Both counts are stored under F9.1.

## Stored criteria

- F9.1 (verdict fail): the net Sharpe ratio is
  not monotone in AUM (the ratio's denominator grows with the impact
  variance), and the halving AUM is undefined because net Sharpe is
  negative at every AUM. The net mean is monotone, stored beside it.
- F9.2 (verdict fail): the turnover-penalized
  optimizer cuts about 37% of turnover with under 7% ex-ante IR loss, so
  the 50% cut is not reached because the turnover is concentrated in the
  high-alpha names.
- F9.3 (verdict fail): the spread-size-rank
  correlation magnitude is below 0.5, with the direction correct, because
  the Corwin-Schultz estimator is noisy at the single-name level.
- F9.4 (verdict pass): the halving AUM is stored
  per rho with its sensitivity to k, and it is NaN everywhere: the book is
  below half its gross Sharpe at zero AUM, so the halving point does not
  exist under these costs.

## Practitioner conclusion

Gross alpha is a research number; net alpha is the business. For the
synthetic i.i.d. book the business answer is that the rebalance cadence and
turnover budget are the binding constraints, not AUM: a book that
reshuffles fully each month cannot survive a 3% half-spread at any size. A
real signal with persistence would have far lower turnover and a defined
capacity; that is the property the next signal must demonstrate.

## What would falsify this?

- Net Sharpe is not monotone in AUM: this happened, and the mechanism is
  the ratio denominator, not the cost model, stored under F9.1.
- The turnover penalty destroys ex-ante IR: the stored trade-off under
  F9.2 shows the IR survives but the turnover cut falls short.
- Realized fills in E11 outside the model's band: parameters are
  recalibrated and the capacity curve reissued.
