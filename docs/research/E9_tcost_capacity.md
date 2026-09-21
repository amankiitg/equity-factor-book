# E9 Transaction Cost and Capacity Analysis

The alpha is the E8 synthetic alpha with a known IC, labeled as such: no
real signal passed RG-Signal, so this book's real capacity is undefined.
The spread input is a size-decile schedule from 10 bp half-spread for the
smallest names to 1 bp for the largest, stated as an assumption with a
half and double sensitivity, because the free estimators measure
volatility rather than the spread on daily high-low data for S&P 500
names. On that schedule the spread cost of a 140% turnover rebalance is
about 0.07% of AUM, not the 4% the Corwin-Schultz estimate implied, and
the capacity question is the impact cost, not the spread.

## The cost model and its uncertainty

- Half-spread: the size-decile schedule above, stated as an assumption.
  The estimators it replaced are documented in the addendum and in
  data/costs/spread_probe.parquet.
- Impact: k * sigma * sqrt(dollar trade / ADV) with k = 0.5, stated with
  uncertainty [0.25, 1.0]; the sensitivity to k is stored under F9.4.
- Commission: 1 bp per dollar traded, one side.
- Borrow: 2% per year on short notional, the E6 provisional.

Cost parameters that free data cannot pin are stated as uncertainty, never
as a clean point estimate.

## Cost curves by size decile

| size decile | mean half-spread | mean market cap | mean ADV |
| --- | --- | --- | --- |
| 0 | 0.00100 | 2.72e+09 | 7.23e+07 |
| 1 | 0.00090 | 6.57e+09 | 7.8e+07 |
| 2 | 0.00080 | 9.75e+09 | 1.14e+08 |
| 3 | 0.00070 | 1.27e+10 | 9.71e+07 |
| 4 | 0.00060 | 1.69e+10 | 1.44e+08 |
| 5 | 0.00050 | 2.26e+10 | 1.32e+08 |
| 6 | 0.00040 | 3.15e+10 | 2.11e+08 |
| 7 | 0.00030 | 4.4e+10 | 2.72e+08 |
| 8 | 0.00020 | 7.28e+10 | 4.58e+08 |
| 9 | 0.00010 | 2.65e+11 | 8.83e+08 |

The chosen schedule falls monotonically from the smallest to the largest
decile by construction, which is the size ordering the spread should have.

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
| 0.05 | 0.25 | 2.831 | 4.64e+08 |
| 0.05 | 0.5 | 2.831 | 1e+08 |
| 0.05 | 1.0 | 2.831 | 3.16e+07 |
| 0.1 | 0.25 | 5.087 | 2.15e+09 |
| 0.1 | 0.5 | 5.087 | 4.64e+08 |
| 0.1 | 1.0 | 5.087 | 1e+08 |

Net Sharpe is monotone in AUM (0
violations over 9 curves) and the net mean return is
monotone (0 violations). The
halving AUM is defined for rho 0.05 and 0.1, and undefined for rho 0.02
because that book's weak alpha is already below half its gross Sharpe at
the 1 million dollar grid floor once the fixed spread and commission cost
of a 140% turnover rebalance is paid.

## The spread schedule sensitivity

The halving AUM under the schedule at half and double, per rho, at k = 0.5:

| rho | spread multiplier | halving AUM |
| --- | --- | --- |
| 0.02 | 0.5 | 1.47e+07 |
| 0.02 | 1.0 | nan |
| 0.02 | 2.0 | nan |
| 0.05 | 0.5 | 1.47e+08 |
| 0.05 | 1.0 | 1e+08 |
| 0.05 | 2.0 | 2.15e+07 |
| 0.1 | 0.5 | 6.81e+08 |
| 0.1 | 1.0 | 4.64e+08 |
| 0.1 | 2.0 | 3.16e+08 |

## Stored criteria

- F9.1 (verdict fail): net Sharpe is
  monotone in AUM (0 violations), and the halving AUM is stored per rho
  and k: undefined for rho 0.02, 100 million dollars at rho 0.05 k 0.5
  and 464 million dollars at rho 0.1 k 0.5.
- F9.2 (verdict fail): the turnover-penalized
  optimizer cuts about 37% of turnover with under 7% ex-ante IR loss, so
  the 50% cut is not reached because the turnover is concentrated in the
  high-alpha names.
- F9.3 (verdict fail): the corrected
  overnight-adjusted Corwin-Schultz estimator floors every name at zero,
  so the size-rank correlation is undefined; the raw estimator reads
  -0.471 and the Abdi-Ranaldo estimate
  0.003, neither above 0.5.
- F9.4 (verdict pass): the halving AUM is stored
  per rho with its sensitivity to k, finite for rho 0.05 and 0.1.
- F9.5 (verdict pass): the chosen schedule's
  median half-spread by decile is stored beside the anchor estimators it
  replaced.

## Addendum: the cost magnitude correction

The original headline said turnover, not AUM, is the binding constraint,
with the halving AUM undefined at every rho and k. That conclusion came
from the cost estimate, not from the book: the stored Corwin-Schultz
half-spreads of 2.5 to 5.2 percent are volatility, not spreads. The
estimator's two-day high-low range is dominated by intraday volatility
for liquid names, so the unadjusted estimate reads about 100 times the
quoted spread, and the overnight-adjusted estimate floors at zero
everywhere. The Abdi-Ranaldo close-high-low estimate has no size
gradient either. The estimator comparison per decile, before and after:

| size decile | raw CS median | adj CS median | Abdi-Ranaldo | schedule |
| --- | --- | --- | --- | --- |
| 0 | 0.04180 | 0.00000 | 0.00071 | 0.00100 |
| 1 | 0.03657 | 0.00000 | 0.00111 | 0.00090 |
| 2 | 0.03118 | 0.00000 | 0.00086 | 0.00080 |
| 3 | 0.02952 | 0.00000 | 0.00068 | 0.00070 |
| 4 | 0.02758 | 0.00000 | 0.00092 | 0.00060 |
| 5 | 0.02684 | 0.00000 | 0.00071 | 0.00050 |
| 6 | 0.02734 | 0.00000 | 0.00052 | 0.00040 |
| 7 | 0.02717 | 0.00000 | 0.00084 | 0.00030 |
| 8 | 0.02512 | 0.00000 | 0.00105 | 0.00020 |
| 9 | 0.02368 | 0.00000 | 0.00091 | 0.00010 |

Before: the raw Corwin-Schultz median half-spread was 2.4 to 4.2 percent,
and at 140% monthly turnover that is about 3 to 5 percent of AUM per
rebalance in spread cost alone, which no IC in the experiment covers, so
the capacity curve was negative at every AUM and the halving AUM was
undefined everywhere. After: the schedule is 10 to 1 bp, the spread cost
per rebalance is about 0.07% of AUM, net Sharpe is monotone in AUM (the
violation count moved from 206 to 0), and the halving AUM is defined for
rho 0.05 and 0.1. The rho 0.02 book remains cost-impaired at any size
because its alpha is too weak to pay even the fixed spread and
commission. Both data hashes are on the record in the revisions block of
sprints/E9/RESULTS.json.

## Practitioner conclusion

Gross alpha is a research number; net alpha is the business. With the
corrected spread the capacity question becomes the impact cost, which is
monotone in AUM, and the halving AUM is defined for the stronger books.
The rho 0.02 book is the cautionary case: at 140% turnover even 10 bp of
spread plus commission is enough to halve a book with an IC of 0.019
before the first dollar of impact.

## What would falsify this?

- Net Sharpe is not monotone in AUM: with the corrected costs it is
  monotone, 0 violations stored under F9.1.
- The turnover penalty destroys ex-ante IR: the stored trade-off under
  F9.2 shows the IR survives but the turnover cut falls short.
- Realized fills in E11 outside the model's band: parameters are
  recalibrated and the capacity curve reissued, and the spread schedule
  is replaced by the measured fills.
