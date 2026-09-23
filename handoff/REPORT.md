# Sprint E11: net columns, the iterative floor and the share diagnostic

Task `e11-net-column-then-pick`, base commit d9f65e7. NAV is $1,000,000,
final. This task adds the net-exposure columns, applies the dollar floor
iteratively to a fixed point, adds the share-count diagnostic and the flagged
two-part floor row, then reruns the table. Nothing here chooses a construction
and nothing re-derives Guard 1; the owner picks.

## What changed

- **E11-F5, net three ways.** Every row now reports net dollar as a share of
  gross post-renormalization and post-quantization, the long and short counts,
  and the realized CAPM beta of the kept book against the market factor.
- **E11-F6, the floor to a fixed point.** The dollar floor is applied
  iteratively: a name worth x pre-renormalization is worth x / kept_gross
  after the survivors are scaled to gross 1.0, so it clears the floor when
  x >= floor x kept_gross. The kept count and the p90 are reported before and
  after the iteration. The naive repeat-until-no-change loop oscillates (the
  map reverses set inclusion), so the fixed point is solved directly as the
  longest prefix of the dollar-sorted book whose last name still clears.
- **Share diagnostic.** Every row reports the median and 10th-percentile
  share count and a one-line statement of what drives the p90 rounding-error
  tail.
- **The flagged two-part floor.** One extra row, flagged for veto: min $1,500
  dollars (iterative) and min 20 shares, computed on the full-book notional
  before re-sizing, then re-sized, renormalized and quantized like every
  other row.

The realized beta is the raw CAPM beta from
`data/models/TS-v1/beta_history.parquet` at the latest date (2026-09-03),
with missing names filled at the cross-sectional median (0.691). The design
matrix's market column is a constant 1.0, so the FMP hedge zeroes net dollar
(sum of weights), not this beta; the two are different objects and both are
reported.

## The table, at $1m on the 2026-09-21 close

`live/construction_table.parquet`. Every row drops names, re-hedges on its
own subset, renormalizes to gross 1.0, then quantizes. "kept" is the selected
subset; "effective" is the nonzero-weight book after the hedge. Gross before
renormalization is the kept subset's gross before the scale-up; gross after
renormalization is 1.0 on every row, stated rather than omitted. Net dollar
is the net as a share of gross; the post-quantization column is the net after
whole-share rounding. p90 is the 90th percentile of per-name whole-share
rounding error as a share of the name's target.

| construction | kept (pre -> post) | effective | long/short | gross before | net $ renorm | net $ quant | realized beta | median / p10 shares | p90 (pre -> post) | max weight |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| min $1,500 | 208 -> 252 | 252 | 113/139 | 0.8124 | 0 | 0.28% | 0.105 | 19.5 / 4 | 9.08% -> 11.93% | 3.95% |
| min $2,000 | 155 -> 208 | 208 | 90/118 | 0.7515 | 0 | 0.75% | 0.107 | 23 / 5 | 5.59% -> 9.08% | 4.20% |
| min $3,000 | 82 -> 156 | 156 | 64/92 | 0.6626 | 0 | 0.39% | 0.114 | 33 / 8 | 4.57% -> 5.34% | 4.66% |
| min $5,000 | 27 -> 99 | 99 | 32/67 | 0.5315 | 0 | 0.63% | 0.130 | 47 / 8.6 | 41.66% -> 7.30% | 5.84% |
| top-N 150 | 150 -> 150 | 150 | 55/95 | 0.4476 | 0 | 0.10% | 0.135 | 26 / 3 | 13.29% -> 13.29% | 6.22% |
| top-N 200 | 200 -> 200 | 200 | 72/128 | 0.5268 | 0 | -0.05% | 0.135 | 18.5 / 2 | 17.75% -> 17.75% | 5.43% |
| two-part 1500+20sh | 252 -> 100 | 100 | 48/52 | 0.4437 | 0 | -0.11% | 0.147 | 90 / 25.9 | 11.93% -> 1.80% | 6.21% |

Full-book reference: 499 names, n_eff 157.33. The p90 tail driver per row:
min $1,500 high-priced names (26 names, median 3 shares at $457); min $2,000
high-priced (21 names, 4 shares, $536); min $3,000 high-priced (16 names, 8
shares, $561); min $5,000 high-priced (10 names, 2 shares, $428); top-N 150
high-priced (15 names, 1 share, $295); top-N 200 high-priced (20 names, 0
shares, $268); two-part floor small positions (10 names, median 28 shares).

## E11-F5: net dollar is zero, but the realized beta is not

The net dollar column is zero on every row post-renormalization. That is not
a coincidence to be checked off: the FMP hedge's market column is a constant
1.0, so zeroing the modeled market exposure is zeroing net dollar, and the
hedge is re-run on each kept subset inside this table. Post-quantization the
net is at most 0.75% of gross (min $2,000), from whole-share rounding only.
So no row's net dollar is material, and no net constraint or different floor
is needed for dollar directionality.

The realized beta column is the part the risk model cannot see, and it is
small but uniform: 0.105 to 0.147 across all seven rows. The book is
dollar-neutral but carries about a tenth of a unit of raw CAPM beta, because
the raw betas are not all 1.0. No row is meaningfully worse on this measure.

The long/short counts are lopsided in count but balanced in dollars. The
24/58 count at min $3,000 does not survive the iteration: it is 64/92 now,
because the fixed-point floor admits names back on both sides. The 55/95 at
top-N 150 and the 72/128 at top-N 200 do survive, because top-N has no floor
to iterate; those rows stay disqualified as the task directs, which is
consistent with top-N already being out on n_eff and total error.

## E11-F6: breadth rises as predicted; p90's direction depends on the row

The iteration buys breadth back on every dollar floor: 208 -> 252, 155 ->
208, 82 -> 156, 27 -> 99. The prediction that p90 widens holds for $1,500,
$2,000 and $3,000 (9.08% -> 11.93%, 5.59% -> 9.08%, 4.57% -> 5.34%), and
the reason is the one the task gives: the admitted names sit at the floor,
not above it.

At $5,000 the direction reverses, 41.66% -> 7.30%, and the reason matters:
the pre-iteration 27-name book was degenerate. Its pseudoinverse hedge
zeroed 4 names, so the effective book was 23 names with a 14.52% maximum
weight, which breaches Guard 1's 0.10 cap. The iteration admits 72 names
back, the hedge no longer degenerates, effective equals kept (99), the
maximum weight falls to 5.84% below the cap, and p90 narrows. So the $5,000
row's pre-iteration p90 of 41.66% measures the broken 27-name book, not the
floor; the post-iteration 7.30% is the number the floor actually produces.

No row triggers the pseudoinverse fallback after the iteration: effective
equals kept on every row.

## The share diagnostic and the flagged two-part floor

The tail driver is high-priced names on every dollar-floor row and both
top-N rows: a few shares at a several-hundred-dollar price. The dollar floor
buys error control it does not need to pay for, exactly as the task
hypothesized.

The flagged row, min $1,500 dollars plus min 20 shares, keeps 100 names
(48 long, 52 short) with median 90 shares and p10 25.9. It cuts p90 to
1.80%, below the $2,000 row's 5.59%, and its tail driver flips to small
positions (median 28 shares), which is the point. The cost is breadth: it
keeps 100 of min $1,500's 252 names, so this is not a free win but a
two-part floor that trades 152 names for a 6.6x tighter error tail. Its
maximum weight is 6.21%, below Guard 1. The row is flagged for the owner's
veto; the owner picks.

## Two small reporting items, fixed

- The gross-after-renormalization column is 1.0 on every row; it is stated
  above rather than omitted silently.
- The test-count citation now uses rule 21's relative rule: the full-run
  count must be at least the previous full-run count recorded in LOG.md,
  which was 682. The full run below is 684, so the rule is met, and the
  removed $10m test is named in the previous report.

## Verification

### Commands and output

`make test` (full run):

```
684 passed, 1 skipped, 3 warnings in 556.85s (0:09:16)
```

`make test-fast`:

```
659 passed, 1 skipped, 25 deselected, 3 warnings in 24.55s
```

`make lint` plus `mypy live`:

```
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
Success: no issues found in 33 source files
.venv/bin/black --check efb dashboard live tests
All done!
161 files would be left unchanged.
=== mypy live ===
Success: no issues found in 15 source files
```

`make verify-evidence`:

```
evidence OK
```

### Headline numbers, file and key

- construction table, seven rows with net, iteration and share columns:
  live/construction_table.parquet
- min $1,500 iterative floor: 208 -> 252 names, p90 9.08% -> 11.93%
- min $5,000 iterative floor: 27 -> 99 names, max weight 14.52% -> 5.84%,
  Guard 1 breach cleared
- two-part floor: 100 names, p90 1.80%, flagged for veto
- realized beta range 0.105 to 0.147: live/construction_table.parquet

### git diff --stat from base_commit (d9f65e7)

```
 handoff/REPORT.md                | 451 +++++++++++++--------------------------
 live/construction_table.parquet  | Bin 12733 -> 20918 bytes
 live/construction_table.py       | 270 ++++++++++++++++++-----
 tests/test_construction_table.py |  56 ++++-
 4 files changed, 416 insertions(+), 361 deletions(-)
```

### Yes or no, each with evidence

1. **Any two rows or two estimators identical?** No. The seven rows differ
   on every column (live/construction_table.parquet).
2. **Any exception caught and skipped, or any fallback taken?** No exception
   is caught and skipped. No row takes the pseudoinverse fallback after the
   iteration (effective equals kept everywhere), which is stated above.
3. **Any criterion reworded or replaced by a different test?** No.
4. **Any criterion that passes by construction?** No. No new criterion was
   registered.
5. **Any number that moved by a factor of 10 or more?** Yes. The min $5,000
   post-iteration p90 is 7.30% against the pre-iteration 41.66%, and its
   kept count is 99 against 27, both stated here.
6. **Any stored number typed into a notebook?** No notebook was touched.
7. **Any earlier verdict changed?** No.

### Anything decided that the reviewer might disagree with

The iterative floor is solved as the longest dollar-sorted prefix rather
than by repeat-until-no-change, because the repeat loop oscillates (the
fixed-point map reverses set inclusion) and would never terminate; the two
compute the same set, and the prefix method is stated in the code. Guard 1
is left at 0.10 and is not re-derived, because the construction has not been
picked.
