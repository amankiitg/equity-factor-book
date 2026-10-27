# HON's 2026-06-29 spin-off return, and the guard that stops the next one

Status: **repair on the branch, held.** Nothing here writes to the store or to
`data/`. The corrected cell is not written anywhere.

## The cell

`data/processed/returns.parquet` carries HON's 2026-06-29 return as **+45.51%**. The
store's corporate-action record for that day is a share distribution of HONA from HON
with `source_rate` 1.0 and `new_rate` **0.5**, and the child closed at **$220.19**.

The session itself paid the parent **-6.46%** as traded: 243.53 to 227.80. The
vendor's own `split_factor` on that row is **0.9535**, which is 4.65% of value, and
4.65% is also what the as-traded move says (a spin-off drops the parent by the value
that leaves it).

So the record's ratio says 47.4% of the parent was distributed and every other
source says about 4.7%. A ratio of 0.05, one HONA per 20 HON, reproduces both:

    inputs:  prior close 243.534348, ex-date close 227.800003, child 220.19, ratio 0.05
    output:  (227.800003 + 0.05 x 220.19) / 243.534348 - 1 = -1.94%
    factor route: 227.800003 / (243.534348 x 0.9535) - 1    = -1.90%

The two routes agree to four basis points. The stored cell is off by 47 points.

## The scan: HON is the only row shaped like this

Every `share_distribution` row in `efb.e11_corporate_actions` (25 rows) was read two
ways: the share of value the record's rate implies (`rate x child / prior`), and the
share of value the vendor's own `split_factor` implies (`1 - 1/factor` for a factor
above one, `1 - factor` below).

| event | record says | factor says | difference |
|---|---|---|---|
| HON / HONA, 2026-06-29 | 47.41% | 4.65% | **42.76 points, the outlier** |
| J / AMTM, 2024-09-30 | 20.74% | 16.46% | 4.28 points, the widest of the rest |
| BWA / PHIN, 2023-07-05 | 14.72% | 11.97% | 2.75 points |
| FTV / RAL, 2025-06-30 | 22.57% | 24.64% | 2.07 points |
| EXC / CEG, 2022-02-02 | 30.55% | 28.67% | 1.88 points |
| GE / GEHC, 2023-01-04 | 23.73% | 21.94% | 1.79 points |
| FDX / FDXF, 2026-06-01 | 18.16% | 19.42% | 1.26 points |
| DD / Q, 2025-11-03 | 59.40% | 58.16% | 1.24 points |
| DHR / VLTO, 2023-10-02 | 11.44% | 11.35% | 0.09 points |
| BDX / WAT, 2024-02-10 | 21.34% | 21.38% | 0.04 points |
| HON / SOLS, 2025-10-30 | 5.72% | 5.75% | 0.03 points |

The rest of the 21 checkable rows sit between those: IP/SLVM 0.06, JEF/VTS 0.21,
GE/GEV 0.23, ILMN/GRAL 0.15, BDX/EMBC 0.15, J/AMTM 2025 0.04, CMCSA/VSNT 0.79,
DTE/DTM 1.32, FLEX/NXT 2.04.

The remaining stored rows are a different action type (an unexplained price move, the
CTVA shape) or carry no factor on the row at all, so this cross-check cannot speak to
them: GE/WAB 2019, FTI/THNPF, ADS/LYLT, FBIN/MBC, K/KLG, APTV/VGNT, CTVA/VYLR.

## What the cell does to the book

Measured against the 2026-10-23 book, with the stored cell and with the cell patched
to -1.94% in a copy of the live-path tree:

* HON's weight: **0.05396** both ways.
* HON's specific variance: **0.000228** both ways, a variance share of **0.1448**.
* HON's raw signal: **+1.450992**, the 99.59th percentile, both ways.

A weight-for-weight identity, because the book does not read the live-path return at
all: it reads `models/XS-v1/specific_returns.parquet`, and that artifact's HON row for
2026-06-29 is **+0.441997**, which is the bad print carried forward.

The damage is in the variance, not the weight. Re-estimating HON's specific variance
with the estimator's own settings (`D_HALF_LIFE=42`, `D_SHRINK_K=60`, 3,977 HON
observations) gives:

| date | stored cell | corrected cell | ratio |
|---|---|---|---|
| 2026-06-30 | 0.003393 (5.82% vol) | 0.000264 (1.62% vol) | 12.9x |
| 2026-10-23 | 0.001090 (3.30% vol) | 0.000268 (1.64% vol) | 4.1x |

The artifact's stored specific variance on 06-30 is 0.003349 against a bucket mean of
0.000499, 6.7x too large for a mega-cap. Three and a half months later the bad print
still prices HON's risk at twice what it should be.

## The repair

`live/corporate_actions.py` now cross-checks a share distribution before applying it.
`distribution_disagreement(factor, child_value, previous_close)` reads the share of
the parent's **restated** prior close that the record's own rate implies, and the
share the vendor's own `split_factor` implies, and returns both when they differ by
more than `DISTRIBUTION_TOLERANCE` (ten points). `_apply_spinoff` then nulls the cell
and records the disagreement instead of writing a return, which is the CTVA shape: a
number no run can reproduce is a hole the hygiene layer reports, not a value to write.

`spinoff_flags` labels it with both shares, for example:

    HON/HONA 2026-06-29, the record's ratio and the child's price say 47.4% of the
    parent was distributed and the vendor's own split factor says 4.7%, so the return
    was nulled

Ten points is set from the population above: the widest legitimate disagreement is
4.28 points, where the child is priced at a different close from the one the factor
used, and the HON row is 42.76 points. Run over all 27 stored rows the guard flags
exactly one, HON on 2026-06-29.

## What is not done, and what the owner has to decide

1. The guard stops the next bad application. It does not rewrite the cell that is
   already stored, and re-running the corporate-actions step over the whole history
   would need a backup-and-restore plan of its own, like the one in
   `attribution_fill_gap.md`.
2. `new_rate` 0.5 in the store is wrong and is what the guard is reacting to. Whether
   the right value is 0.05 (one per 20) or the rate should be left to the vendor's
   factor is an owner decision, taken with the public sources, not a code change.
3. The fitted model artifact still carries +0.441997 for HON on 2026-06-29. Fixing
   that means rebuilding `specific_returns.parquet`, which is a research-path run.
