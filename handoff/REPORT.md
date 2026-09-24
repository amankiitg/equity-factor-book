# Sprint E11: the prefix enforced book, and the stop it fires

**Owner question, at the top, because the task ends blocked on it.**

Part 1 implemented the rule TASK.md pre-registered: the largest valid prefix,
ordered by `|w_i| / floor_i` on the full-book weights, checked on the final
weights. It fires the stop that same pre-registration wrote: it keeps fewer
names than the drop-only enforcement on **all six** floor rows, 16 against 119
on the share-only row. The rule's own premise fails, for a reason measured
below: the floor is a relative condition on a book renormalized to gross 1.0,
and the re-size on the kept subset moves the names the ordering predicted.

Two consequences the owner has to weigh.

1. **The corrected book is not identified.** The pre-registered prefix is
   degenerate, not merely small: on the min $3,000 and min $5,000 rows it is a
   three-name book whose net dollar exposure is 1.0 of gross, so the exact FMP
   hedge does not neutralise it. Installing it as the table's book breaks a
   standing invariant (`net_dollar_share_of_gross` within 0.01 on every row),
   so the table keeps the last valid enforced book and reports the prefix
   beside it. The rule needs re-specifying, and that is the reviewer's call.
2. **The numbers the share-only choice was made on are not attainable.** The
   owner chose share-only at 188 names, n_eff 85.69, total error 1.25% and p90
   3.44%, all values from the pre-resize fixed point. No enforced book reaches
   188 names: 24 of those 188 names are below 20 shares in the vector that
   actually trades. The enforceable share-only book is **119 names, n_eff
   58.82** by the drop-only rule, and **143 names, n_eff 68.52** by the
   admission control reported below. So the basis of the choice changed even
   though the choice itself is untouched, and the re-decide trigger does not
   fire under any of the three readings.

So the questions for the owner are: hold share-only pending the reviewer's
re-specified rule, or re-decide now on the enforceable numbers, 119 and 58.82
against 143 and 68.52? And does the fall from 85.69 to 58.82 or 68.52 change
the choice, given that "a fall in n_eff alone does not stop the task" was the
pre-registered rule and the fall is now larger than any enforced book can undo.

Nothing is deployed. `dry_run` stays `true`. No proposal was regenerated and
Guard 1 was not re-derived, as Part 1 requires.

## Part 1: E11-F13, the largest valid prefix checked on the final weights

### The rule, implemented as pre-registered

`live/evening_job.py` gains `floor_thresholds` (the larger of the dollar and
share legs at each name's close) and `enforce_floor_by_prefix`. The rule:
order names by `|w_i| / max(dollar_floor, share_floor * price_i)` on the
full-book weights, then for `k` from 499 downward finalize the prefix-`k` set
with the same `finalize_kept_set` the live path uses (size, hedge, renormalize,
quantize) and check every kept name against its floor in those final weights.
The first `k` that passes is the largest valid prefix. The pass set is not
monotone in `k`, so the scan is linear and is never bisected. The same rule
runs on all six floor rows, each with its own floor and its own ordering.

### The stop fires on every row

Reproduced first, per rule 8, on the committed code:

```
row                               one-pass  fixed-pt  drop-only
min_position_1500                      208       252        194  passes=3 converged=True below=0
min_position_2000                      155       208        145  passes=3 converged=True below=0
min_position_3000                       82       156         72  passes=3 converged=True below=0
min_position_5000                       27        99         23  passes=3 converged=True below=0
two_part_floor_1500_20shares            92       172         87  passes=3 converged=True below=0
share_only_20shares                    118       188        119  passes=3 converged=True below=0
```

The enforced count sits at or one above the one-pass count on every row and 58
to 117 names below the pre-resize fixed point, which is the reviewer's finding.

The prefix rule then gives:

```
row                               one-pass  fixed-pt  drop-only  prefix_k
min_position_1500                      208       252        194       131
min_position_2000                      155       208        145       131
min_position_3000                       82       156         72         3
min_position_5000                       27        99         23         3
two_part_floor_1500_20shares            92       172         87        66
share_only_20shares                    118       188        119        16
```

Prefix below drop-only on all six rows: share-only by 103 names, min $3,000 by
69, min $1,500 by 63, two-part by 21, min $5,000 by 20, min $2,000 by 14. That
is the pre-registered stop ("If the prefix result keeps fewer names than
drop-only on any row, stop and report. That would mean a bug, not a finding"),
so Part 1 stops here and the prefix book is not installed.

### The corrected table

`live/construction_table.parquet`, one row per construction. The enforced
columns are identical to the committed table (checked: 47 shared numeric
columns, none moved); the `_prefix` columns are the measured prefix rule.

| construction | one-pass | pre-resize fixed point | enforced book | prefix k | enforced n_eff | prefix n_eff | enforced error | prefix error | enforced p90 | prefix p90 | prefix max weight | prefix net |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| min $1,500 | 208 | 252 | 194 | 131 | 98.736507 | 75.201881 | 2.5015% | 1.8019% | 8.8188% | 5.7309% | 4.9354% | 0 |
| min $2,000 | 155 | 208 | 145 | 131 | 81.681243 | 75.201881 | 1.9150% | 1.8019% | 5.9304% | 5.7309% | 4.9354% | 0 |
| min $3,000 | 82 | 156 | 72 | 3 | 44.476474 | 2.240310 | 0.9147% | 0.0925% | 2.9323% | 0.5012% | 58.8235% | 1.0 |
| min $5,000 | 27 | 99 | 23 | 3 | 14.104803 | 2.240310 | 0.4757% | 0.0925% | 1.6769% | 0.5012% | 58.8235% | 1.0 |
| two-part, $1,500 + 20sh | 92 | 172 | 87 | 66 | 51.190506 | 40.477586 | 0.5560% | 0.3651% | 1.4008% | 0.8907% | 7.1704% | 0 |
| share-only, 20 shares | 118 | 188 | 119 | 16 | 58.822271 | 7.369653 | 0.6426% | 0.0246% | 2.0385% | 0.4322% | 20.6853% | -0.089543 |

"error" is `total_gross_error_share_of_nav`, "p90" is
`quant_error_p90_pct_of_target`, "net" is `net_dollar_share_of_gross_prefix`.
The prefix scan walked 369, 369, 497, 497, 434 and 484 finalizations on the six
rows, in `floor_prefix_scans`, so the linear scan is doing what it says.

**Every enforced row still holds its floor**: `n_below_floor_final` is 0 on all
six, and the pre-resize fixed point still does not (31, 19, 21, 19, 26 and 24
names below floor on the six rows, in the stored
`n_below_floor_final_pre_enforcement`).

**Share-only's n_eff, against the 85.69 the owner chose on:** the enforced book
is **58.822271**, and the pre-registered prefix is 7.369653. As a plain number,
85.69 against 58.82.

### Why the prefix collapses, with the numbers

Reproduced on the share-only row. Four measurements, in the order that
establishes the mechanism.

1. **The floor is relative, so extending the set shrinks every position.** With
   the kept set renormalized to gross 1.0, the average position is NAV / k. The
   below-floor count on the final weights, as a function of the prefix length:

   ```
   k    = 499  450  400  350  300  250  220  200  188  175  160  150  140  131  120  110  100   90   80   60   40   30   20   17   16   15
   below= 374  321  267  210  141   84   49   30   24   15   14   15   14    9    7   10    8    5    5    2    3    1    4    4    0    1
   ```

   It never reaches zero for any `k` between 17 and 499. The first zero is
   `k = 16`, where the prefix has thrown away 103 of the 119 names the drop-only
   rule keeps and gross 1.0 is shared among 16 names, so the floor is satisfied
   for the wrong reason: the max final weight is 20.6853% of gross against
   5.9617% on the enforced book.
2. **Rounding is not the cause.** At every tested `k`, `floor(|w| * NAV /
   price) < 20` and `|w| * NAV / price < 20` give the same count, so the
   failures are not names rounding 19.9 down to 19.
3. **The ordering does not survive the re-size.** On the full set the re-sized
   weights are the full-book weights times one scalar, 1.03248436090019, to
   machine precision (`|w_finalize(499)| / |w_full|` runs from 1.03248436090019
   to 1.0324843609001904, so the largest relative deviation is 2.2e-16), and the
   correlation prints as 1.0. So the ordering is meaningful for the whole book.
   It is not meaningful for a subset. At `k = 188` the 24
   below-floor names are not only the tail: ranked by `|w|` in the re-sized
   book they are positions 0 to 14 (the smallest), and then 17, 30, 31, 42, 47,
   80, 110, 121, 168 and 182 of 188. Rank 182 is the sixth largest position in
   the book and still below its floor, because a high-priced name needs a large
   weight to hold 20 shares at all.
4. **In the regime that passes, the hedge is rank-deficient.** The design has 17
   factors. `cond(design_k' design_k)` is about 2e3 for `k` at or above 100
   (1.7e3 at 499, 2.0e3 at 188, 2.6e3 at 120) and 1.7e19 at `k = 30`, 4.4e18
   at 20, 1.3e20 at 17, 9.0e18 at 16. Names are annihilated to `|w|` of order
   1e-18 (1 name at `k = 60`, 2 at 40, 1 at 30, 3 at 20, 4 at 17). The
   three-name prefix books on the min $3,000 and min $5,000 rows have a net
   dollar exposure of 1.0 of gross: with three names against 17 factors the
   exact FMP hedge cannot neutralise the book at all, so those "books" are all
   long.

Point 4 is what makes the result unusable rather than merely surprising. The
standalone guard `test_the_table_has_all_nine_rows_and_renormalizes` asserts
`|net_dollar_share_of_gross| < 0.01` on every row. Installing the prefix as the
book fails that guard on three of six rows (min $3,000 and min $5,000 at 1.0,
share-only at -0.089543). I did not relax the guard: a guard relaxed to fit a
construction is the rule broken quietly. The enforced book stays the book, the
prefix is measured beside it, and the rule goes back for re-specification.

### The re-decide trigger, on every reading

The trigger as pre-registered in E11-F12: compare share-only against min $2,000
on the same basis, and stop if (a) share-only no longer has both lower total
error and lower p90 than min $2,000, or (b) any enforced row is better or equal
on both n_eff and total error than share-only.

| reading | share-only: n_eff, error, p90 | min $2,000: n_eff, error, p90 | (a) fires | (b) fires |
| --- | --- | --- | --- | --- |
| enforced book (drop-only) | 58.822271, 0.6426%, 2.0385% | 81.681243, 1.9150%, 5.9304% | no | no |
| pre-registered prefix | 7.369653, 0.0246%, 0.4322% | 75.201881, 1.8019%, 5.7309% | no | no |
| admission control | 68.521819, 0.7767%, 1.8515% | 93.898480, 2.0804%, 6.0769% | no | no |

Branch (a) does not fire on any reading: share-only has both the lower total
error and the lower p90 than min $2,000. Branch (b) does not fire either: on
the enforced book the only rows with higher n_eff (min $1,500 at 98.74, min
$2,000 at 81.68) carry higher error (2.5015%, 1.9150%); on the prefix numbers
the rows with higher n_eff (75.201881) carry error 1.8019% against 0.0246%;
on the admission control the rows with higher n_eff (106.89, 93.90) carry
2.7690% and 2.0804% against 0.7767%.

So the trigger does not fire, but that answer is worth less than it looks. On
the pre-registered prefix it is vacuous, because a 16-name book with 20.69%
max weight and a broken hedge is not a book. On the enforced book it is the
reading the reviewer told the owner not to re-decide on. The one reading that
is both valid and larger than the drop-only result is the admission control,
which is a diagnostic I ran, not the pre-registered rule.

### The admission control (diagnostic, not the pre-registered rule)

The reviewer's premise is that the drop-only loop loses breadth the E11-F6
iteration buys back (working lesson: "a fixed-point spec must name admission as
well as dropping"). The prefix direction is the wrong generator for that:
dropping the tail of an ordering is still dropping, and it admits nothing. So I
ran the reverse direction as a control, starting from the drop-only book and
admitting names in descending `|w_i| / floor_i` order, keeping a name only when
the final weights of the enlarged set still clear every kept name's floor.
Nothing is stored; the script is pasted at the end of the report.

| construction | admitted | drop-only | n_eff | naive breadth | governing breadth | error | p90 | max weight | net | long/short | raw beta | worst post-hedge exposure | idio share | below floor |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| min $1,500 | 222 | 194 | 106.892541 | 1.439469 | 1.213196 | 2.7690% | 8.8453% | 4.1241% | 0 | 101/121 | 0.108933 | 1.94e-15 | 1.0 | 0 |
| min $2,000 | 185 | 145 | 93.898480 | 1.576860 | 1.294420 | 2.0804% | 6.0769% | 4.4164% | 0 | 87/98 | 0.111136 | 1.48e-15 | 1.0 | 0 |
| min $3,000 | 88 | 72 | 51.036174 | 2.286323 | 1.755762 | 1.2375% | 4.2501% | 6.3937% | 0 | 26/62 | 0.111653 | 2.52e-15 | 1.0 | 0 |
| min $5,000 | 32 | 23 | 18.742922 | 3.791438 | 2.897250 | 0.5365% | 1.5316% | 12.0395% | 0 | 13/19 | 0.015809 | 1.43e-15 | 1.0 | 0 |
| two-part, $1,500 + 20sh | 124 | 87 | 64.683243 | 1.926052 | 1.559584 | 0.8444% | 2.2523% | 5.5239% | 0 | 55/69 | 0.137104 | 1.14e-15 | 1.0 | 0 |
| share-only, 20 shares | 143 | 119 | 68.521819 | 1.793539 | 1.515270 | 0.7767% | 1.8515% | 5.4408% | 0 | 68/75 | 0.132141 | 9.85e-16 | 1.0 | 0 |

Read this as a bound and not as the answer. Every row is self-consistent: the
floor holds on the final weights (0 below), the hedge is exact (worst post-hedge
exposure 1e-15, idio share 1.0, net 0), and the books are larger than the
drop-only ones on every row, by 9 to 37 names. Share-only goes from 119 to 143
names and from n_eff 58.82 to 68.52. But greedy admission is order-dependent:
it is one self-consistent set, not a proven maximum, and a different admission
order can land elsewhere. It is here to show that the breadth the reviewer
expects is real and reachable, and to give the owner the numbers asked for, not
to pre-empt the reviewer's rule.

### What this does to the basis of the owner's choice

The choice was made on the pre-resize fixed point: 188 names, n_eff 85.69,
governing breadth 1.355, total error 1.25% and p90 3.44%. Enforcement is not
compatible with that book: 24 of its 188 names hold fewer than 20 shares in the
vector that actually trades, which is `n_below_floor_final_pre_enforcement` 24
on the share-only row. No rule that enforces the floor can return 188 names on
this data, so n_eff 85.69 is not attainable and the choice was made on a number
no enforceable book has. The two enforceable share-only books measured here are
119 names at n_eff 58.82 and 143 names at n_eff 68.52, a fall of 31.4% or 20.0%
from 85.69. The reviewer's note on the drop-only book said the fall was 31% and
to "report the fall plainly, not call it close"; I am reporting that the same
fall is now the whole distance from the choice's basis.

The owner's reasoning is untouched and the trigger does not fire, so this is
not a re-decide by itself. It is the fact the reviewer needs before
re-specifying, and the fact the owner needs before the flip, because the
breadth the choice traded IR for is smaller than the table the choice was made
from.

## Parts 2 to 4 and the rest: not started

The owner's instruction for this cycle is that the task stops after Part 1, so
Part 2 (E11-F15, the model inputs into Postgres), Part 3 (the staleness hard
stop), Part 3b (the notification), Part 4 (the corrected deploy steps) and Part
5 onward are not started. Part 1's checkpoint also forbids regenerating
proposals or re-deriving Guard 1 before the owner confirms, and both are
untouched. `dry_run` is still `true` and was not flipped. `live/proposals/` is
unchanged.

`live/construction_table.parquet` and `live/construction_weights.parquet` were
regenerated: the enforced columns are identical to the committed ones and eight
`_prefix` columns were added. The prefix book's names are not the book, so they
are not written into `live/construction_weights.parquet`; that file's rows are
unchanged.

## What changed

- `live/evening_job.py`: `floor_thresholds` and `enforce_floor_by_prefix` added;
  `enforce_floor_on_final_weights` docstring now records the E11-F13 behaviour
  that it only drops. No behaviour change on the live path, which still runs the
  drop-only loop.
- `live/construction_table.py`: every floor row measures the prefix rule beside
  the enforced book and stores eight `_prefix` columns; `_no_floor_row` stamps
  them vacuously.
- `tests/test_construction_table.py`: the enforcement test now pins the prefix
  measurement, the stop, and the net-zero invariant the prefix breaks.
- `tests/test_e11_evening.py`: three unit tests, for `floor_thresholds`, for the
  linear scan on a non-monotone pass set (a bisection would miss it), and for
  the loud failure when no prefix clears.

## Verification

### Commands run and their last lines

Per-step selection while the code changed (rule 21), pasted with the command:

```text
$ .venv/bin/python -m pytest tests/test_construction_table.py tests/test_e11_evening.py -q
...........................                                              [100%]
27 passed in 129.04s (0:02:09)
```

`make lint`, exit 0:

```text
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
pyproject.toml: note: unused section(s): module = ['alpaca', 'alpaca.trading.*']
Success: no issues found in 33 source files
.venv/bin/black --check efb dashboard live tests
All done! ✨ 🍰 ✨
163 files would be left unchanged.
```

`make test`, the full suite, exit 0:

```text
727 passed, 1 skipped, 3 warnings in 759.79s (0:12:39)
```

`make verify-evidence`, exit 0:

```text
.venv/bin/python -c "from efb import evidence; p = evidence.verify(); print('evidence OK' if not p else chr(10).join(p)); raise SystemExit(1 if p else 0)"
evidence OK
```

**The split, rule 21.** `make test-fast` is the default path (`-m "not slow"`):

```text
700 passed, 1 skipped, 27 deselected, 3 warnings in 27.03s
```

So 700 of the 727 pass on the fast path in 27.03s, and the 27 slow tests take
the remaining 732.76s of the full run, because six of them each rebuild the
whole construction table. The full-run count is 727 against the 724 recorded in
`handoff/LOG.md` at `938da6c`, and the three added tests are
`floor_thresholds`, the prefix scan on a non-monotone pass set, and the loud
failure when no prefix clears. No test was removed and none was newly marked
slow, so the full run only grew.

### Headline numbers, file and key

All from `live/construction_table.parquet`, one row per `construction`, in the
order the file stores them (min $1,500, min $2,000, min $3,000, min $5,000,
top_n_150, top_n_200, two_part, share_only, full_book):

| number | file and key |
| --- | --- |
| enforced 194/145/72/23/87/119 | `n_kept` |
| one-pass 208/155/82/27/92/118 | `n_kept_pre_iteration` |
| pre-resize fixed point 252/208/156/99/172/188 | `n_kept_post_iteration` |
| prefix 131/131/3/3/66/16 | `n_kept_prefix` and `floor_prefix_k` |
| scans 369/369/497/497/434/484 | `floor_prefix_scans` |
| enforced n_eff 98.736507/81.681243/44.476474/14.104803/51.190506/58.822271 | `n_eff_kept` |
| prefix n_eff 75.201881/75.201881/2.240310/2.240310/40.477586/7.369653 | `n_eff_kept_prefix` |
| enforced error 0.025015/0.019150/0.009147/0.004757/0.005560/0.006426 | `total_gross_error_share_of_nav` |
| prefix error 0.018019/0.018019/0.000925/0.000925/0.003651/0.000246 | `total_error_share_of_nav_prefix` |
| enforced p90 0.088188/0.059304/0.029323/0.016769/0.014008/0.020385 | `quant_error_p90_pct_of_target` |
| prefix p90 0.057309/0.057309/0.005012/0.005012/0.008907/0.004322 | `quant_error_p90_pct_of_target_prefix` |
| prefix max weight 0.049354/0.049354/0.588235/0.588235/0.071704/0.206853 | `max_weight_share_of_gross_prefix` |
| prefix net 0/0/1.0/1.0/0/-0.089543 | `net_dollar_share_of_gross_prefix` |
| pre-resize below floor 31/19/21/19/26/24 | `n_below_floor_final_pre_enforcement` |
| enforced below floor 0 on all six | `n_below_floor_final` |
| the drop-only loop's passes and convergence | `floor_enforcement_passes` 3, `floor_enforcement_converged` True |
| enforced max weight 0.042984/0.047402/0.067339/0.145208/0.064005/0.059617 | `max_weight_share_of_gross` |

The admission control numbers are not stored. They come from the script pasted
under `Diagnostic scripts`; the rows it prints are the six floor rows in the
same order, with `n_kept` the admitted count and `n_kept_drop_only` the enforced
book.

### git diff --stat from `base_commit` (938da6c)

```text
 handoff/LOG.md                   |  161 ++++++
 handoff/PROJECT_CONTEXT.md       |   66 ++-
 handoff/REPORT.md                | 1037 +++++++++++++++++---------------------
 handoff/TASK.md                  |  303 ++++++++++-
 live/construction_table.parquet  |  Bin 37356 -> 43229 bytes
 live/construction_table.py       |   78 ++-
 live/evening_job.py              |   69 +++
 tests/test_construction_table.py |   17 +-
 tests/test_e11_evening.py        |   80 ++-
 9 files changed, 1215 insertions(+), 596 deletions(-)
```

This is the diff at the Part 1 commit, measured here, so it counts this
section. None of these numbers can be re-taken without moving them, since
whatever paragraph replaces this one changes the totals by its own size.

`handoff/LOG.md`, `handoff/PROJECT_CONTEXT.md` and `handoff/TASK.md` are the
reviewer's and owner's commits `dceda3c`, `8e01e8c` and `adf2fd0`, which land
between `938da6c` and here; the TASK.md number also carries my status flip to
`in_progress` and then `blocked`. Everything else is this task.
`live/construction_weights.parquet` is absent from the diff because the
regenerated file is byte-identical to the committed one: the enforced book's
names did not change, and the prefix book's names were never written to it.

### Yes or no, each with evidence

1. **Any two rows or two estimators identical.** Yes. The min $1,500 and
   min $2,000 prefix books are the same set: their orderings are identical
   (both order by `|w_i| / dollar_floor` on the same full-book weights), and the
   first passing `k` is 131 for both, so every prefix column is identical
   between the two rows (`n_kept_prefix` 131, `n_eff_kept_prefix` 75.201881,
   `total_error_share_of_nav_prefix` 0.018019 on both). The enforced columns
   differ (194 against 145), so the duplicate is confined to the prefix
   measurement. It is also part of the degeneracy: the scan stops where it
   stops, and the floor it was checking barely enters.
2. **Any exception caught and skipped, or fallback taken, with counts.** Yes,
   the pseudoinverse fallback in `live/sizing.hedge_exact_robust`. It fires 148
   times across one full `build_table(store=False)` out of 2536
   `np.linalg.solve` calls, counted by wrapping `np.linalg.solve` and counting
   raises (`efb/hedge.py`'s `fmp_hedge_exact` does not catch `LinAlgError`, so
   a raise there would abort the build and every counted raise is the fallback).
   Attribution, measured by rebuilding with `enforce_floor_by_prefix` stubbed
   out to a single finalize per row: 36 solves and 4 raises without the prefix
   scan, so **144 of the 148 are inside the prefix scan**, where the subsets
   fall below the 17-factor design (the scan walks through 3, 4, 16 and 17 name
   sets). The other 4 sit in the normal build path; 3 of them are in the six
   enforced-book loops, which run 15 solve calls in total and still converge to
   books whose post-hedge exposure is 1e-15. No exception is swallowed: the
   fallback returns the best achievable hedge and the caller reports the
   achieved exposure.
3. **Any criterion reworded or replaced by a different test.** No. No
   `sprints/E*/RESULTS.json` criterion was touched, no threshold or criterion
   string was edited, and no criterion ID was added. The only edits are in
   `tests/` and in the two `live/` modules named above.
4. **Any criterion that passes by construction.** Yes, and it is why the prefix
   book's validity carries no information: the scan returns the first set whose
   every name clears its floor in the final weights, so "no kept name is below
   floor" is true of its output by construction. I did not store a below-floor
   column for the prefix book, because it would be a zero that meant nothing.
   The enforced book's `n_below_floor_final` of 0 is not by construction: the
   drop-only loop checks after the fact, and the pre-resize fixed point fails
   the same check with 31/19/21/19/26/24 names.
5. **Any number that moved by a factor of 10 or more from its previous stored
   value.** No. The 47 numeric columns shared with the committed table are
   identical, the largest absolute difference being 0.0. Eight columns were
   added and none removed.
6. **Any stored number typed into a notebook.** No. No notebook was opened,
   edited or executed.
7. **Any earlier verdict changed.** No. Every verdict in `sprints/E*/RESULTS.json`
   and the registry is untouched, and the construction table carries no verdict.

### Anything decided that the reviewer might disagree with

**I did not install the prefix as the book, which reverses the pre-registration
line "The prefix result is the book. The drop-only result is reported beside
it."** The reviewer's own stop fired, and the prefix book also fails a standing
invariant on three of six rows (net dollar 1.0 of gross on the two three-name
rows, -0.089543 on share-only), so installing it would have left the suite red
against a guard I would then have had to relax. I kept the last valid enforced
book as the book, measured the prefix beside it, and left the rule for the
reviewer to re-specify. If the reviewer wants the prefix installed as the book
regardless, it is one line, but the net-zero guard then has to be dealt with
explicitly rather than quietly.

**The admission control is my diagnostic, not a rule.** It is in the report
because the reviewer's premise (that the drop-only book understates the
possible breadth) is right and needs a number, and because the owner asked
where the trigger lands. It is order-dependent, it is not pre-registered, and I
have wired it nowhere.

**I ran the full suite, which rule 21 requires only before `done`.** The task
ends `blocked`, not `done`, but rule 20 requires `make test` output in this
section, so this is the full run and not a subset.

## Diagnostic scripts

The two diagnostics behind the mechanism, so they can be re-run. Both are
read-only and write nothing. In both, `names, alpha_vec, signal_z, design,
factor_cov, specific` come from `ct._raw_pieces(ROOT, as_of)`, `fw` from
`size.procedure_6_3` plus `ct._scale_to_target`, `close` from
`ct._close_prices`, and `beta_stages` and `n_eff_full` as `build_table` gets
them.

`k sweep`, the below-floor count against the prefix length on the share-only
row, printing for each `k`: the rounded-share count, the target count and the
target-below-19.5 count:

```python
thr = ev.floor_thresholds(close, names, 0.0, 20)
order = np.argsort(-(np.abs(fw) / thr), kind="stable")
for k in (499, 450, 400, 350, 300, 250, 220, 200, 188, 175, 160, 150, 140, 131,
          120, 110, 100, 90, 80, 60, 40, 30, 20, 17, 16, 15):
    keep = np.zeros(len(names), dtype=bool)
    keep[order[:k]] = True
    fin = ev.finalize_kept_set(keep, names, alpha_vec, design, factor_cov,
                               specific, close, ct.PAPER_NAV)
    shares = np.asarray(fin["shares"], dtype=int)
    prices = np.asarray(fin["prices"], dtype=float)
    target = np.abs(np.asarray(fin["w_sub"], dtype=float)) * ct.PAPER_NAV / prices
    print(k, int(ev.below_floor(shares, prices, 0.0, 20).sum()),
          int((np.floor(target) < 20).sum()), int((target < 20).sum()))
```

`admission control`, the dropped-name admission, per floor row, printing the
table in the section above and storing nothing:

```python
for label, dollar_floor, share_floor in ROWS:
    drop_keep, _fin, _p, _c = ev.enforce_floor_on_final_weights(
        np.ones(len(names), dtype=bool), names, alpha_vec, design, factor_cov,
        specific, close, ct.PAPER_NAV, dollar_floor, share_floor)
    thresholds = ev.floor_thresholds(close, names, dollar_floor, share_floor)
    order = np.argsort(-(np.abs(fw) / thresholds), kind="stable")
    admitted = drop_keep.copy()
    for position in order:
        if admitted[position]:
            continue
        trial = admitted.copy()
        trial[position] = True
        fin = ev.finalize_kept_set(trial, names, alpha_vec, design, factor_cov,
                                   specific, close, ct.PAPER_NAV)
        if not ev.below_floor(np.asarray(fin["shares"], dtype=int),
                              np.asarray(fin["prices"], dtype=float),
                              dollar_floor, share_floor).any():
            admitted = trial
    row, _names = ct._compute_row(names, alpha_vec, design, factor_cov, specific,
                                  fw, close, beta_stages, ct.PAPER_NAV, n_eff_full,
                                  admitted, fw, signal_z, label, False,
                                  dollar_floor=dollar_floor, share_floor=share_floor)
    print(label, int(admitted.sum()), int(drop_keep.sum()), row["n_eff_kept"],
          row["total_gross_error_share_of_nav"],
          row["quant_error_p90_pct_of_target"])
```
