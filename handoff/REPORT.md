# Sprint E11 construction table: report

Task `e11-construction-table`, base commit ea821bc. NAV is $1,000,000,
final: Alpaca's paper funding field is capped at "$1 - $1,000,000" and the
$10m option is closed. The construction table is the decision surface; the
owner picks from it, and nothing here chooses for the owner.

## The three review findings, fixed

- **E11-F2, average trade size divided by the wrong count.** Fixed in
  live/evening_job.py `_cost_decomposition`: the average now divides the
  traded notional by the number of names that actually trade, not by the
  full 499-name list. At the renormalized $5,000 book it is
  1,000,000 / 23 = 43,478 dollars, not 0.2734 x 1e6 / 499 = 547.81.
- **E11-F3, E5 RESULTS.json moved.** Resolved, not carried. The six-line
  diff is the data_hash bump carried by the registry edit, recorded through
  the `revisions` block with both hashes; no criterion, verdict, threshold
  or stored number moved. Recorded in docs/hygiene_ledger.md, 2026-09-22.
- **E11-F4, the book was never renormalized after dropping.** Fixed. The
  drop now re-runs Procedure 6.3 on the kept subset (with a pseudoinverse
  fallback for a rank-deficient subset), then renormalizes to gross 1.0,
  then quantizes. Kept gross before and after renormalization are both
  reported.

## The construction table, at $1m on the 2026-09-21 close

live/construction_table.parquet. Every row drops names, re-hedges on its
own subset, renormalizes to gross 1.0, then quantizes. "kept" is the
selected subset; "effective" is the nonzero-weight book after the hedge.
Per-name quantization error is the whole-share rounding error as a share
of the name's target, median and 90th percentile.

| construction | kept | effective | dropped | long/short | gross before | median err | p90 err | total err | post-hedge max exposure | idio share | max weight | breadth naive | governing | n_eff |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| min $1,500 | 208 | 208 | 291 | 90/118 | 0.7515 | 1.76% | 9.08% | 2.64% | 1.2e-15 | 1.0 | 4.20% | 1.487 | 1.237 | 102.8 |
| min $2,000 | 155 | 155 | 344 | 63/92 | 0.6607 | 1.31% | 5.59% | 1.91% | 4.6e-16 | 1.0 | 4.68% | 1.723 | 1.367 | 84.2 |
| min $3,000 | 82 | 81 | 417 | 24/58 | 0.4838 | 0.65% | 4.57% | 1.06% | 3.7e-16 | 1.0 | 6.48% | 2.368 | 1.826 | 47.2 |
| min $5,000 | 27 | 23 | 472 | 11/16 | 0.2734 | 0.37% | 41.66% | 0.48% | 6.6e-15 | 1.0 | **14.52%** | 4.128 | 3.340 | 14.1 |
| top-N 150 | 150 | 150 | 349 | 55/95 | 0.4476 | 1.61% | 13.29% | 2.07% | 1.6e-15 | 1.0 | 6.22% | 1.751 | 1.640 | 58.5 |
| top-N 200 | 200 | 200 | 299 | 72/128 | 0.5268 | 2.28% | 17.75% | 2.67% | 1.2e-15 | 1.0 | 5.43% | 1.517 | 1.470 | 72.8 |

Full-book reference: 499 names, n_eff 157.33.

## The rank prediction held, and so did the concentration warning

The $5,000 row is the one the task predicted. The 27-name subset hedges
17 factor columns with 27 names, and the pseudoinverse hedge exactly
cancels 4 of them (BNY, BG, MRNA, GRMN go to ~1e-16), so the effective
book is 23 names, not 27. Its max post-renormalization weight is 14.52%,
which breaches Guard 1's 0.10 cap on a legitimate book. Every other row
clears the cap: 4.20%, 4.68%, 6.48%, 6.22%, 5.43%.

Guard 1 must therefore be re-derived against the post-renormalization
weights of whichever construction the owner picks, not against the
pre-renormalization weights it was sized from.

## How the two approaches compare

At comparable name counts the minimum-position rows dominate the top-N
rows on both n_eff and total gross error: min $1,500 (208 names, n_eff
102.8, error 2.64%) is better than top-N 200 (200 names, n_eff 72.8,
error 2.67%) on both; min $2,000 (155 names, n_eff 84.2, error 1.91%) is
better than top-N 150 (150 names, n_eff 58.5, error 2.07%) on both. So
top-N by alpha does not dominate; it drops the names the hedge needs. The
owner picks.

## NAV is $1,000,000, final

The $10m column is deleted from reporting and nothing is sized against it.
The $10m test (test_build_proposal_keeps_breadth_at_a_ten_million_nav)
was removed with it; the suite goes from 683 to 682 passing tests, still
above the 670 floor, and the removal is named here.

## The skipped test, named

tests/test_e11_render.py `test_alpaca_live_connect_names_the_missing_dependency`
skips because alpaca-py is installed in the venv. The test exercises the
missing-dependency error path, which only runs when alpaca-py is absent.

## Addition 5: slow-test markers and the measured shared-module set

The `slow` marker is registered in pyproject.toml and `make test-fast`
runs `pytest -m "not slow"`. 23 tests are marked slow (anything over about
two seconds).

The shared-module set, measured by import fan-in over tests, efb and live
(from efb import X / from efb.X import / import efb.X): evaluate (29),
models (28), registry (18), hygiene (17), eval_risk (16), probes (9), race
(8), risk (8), universe (7), build (5), size (5), prices (5), identity (5),
cov (4), costs (3), perf (2), evidence (1). A change to any of these, or to
anything under efb/models/, triggers a required full run. This task touched
no efb module (only live/), so the full run below is the rule-21 item-1
run before `done`, not an import-fanout run.

## Verification

### Commands and output

`make test` (full run):

```
682 passed, 1 skipped, 3 warnings in 449.78s (0:07:29)
```

`make test-fast` (the default for per-step work):

```
659 passed, 1 skipped, 23 deselected, 3 warnings in 24.90s
```

`make lint` (plus `mypy live`, which the Makefile does not run):

```
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
Success: no issues found in 33 source files
.venv/bin/black --check efb dashboard live tests
All done! ✨ 🍰 ✨
158 files would be left unchanged.
=== mypy live ===
Success: no issues found in 13 source files
```

`make verify-evidence`:

```
evidence OK
```

Exit status 0.

### Headline numbers, file and key

- construction table, six rows: live/construction_table.parquet
- NAV 1,000,000 final: handoff/TASK.md, live/evening_job.py `PAPER_NAV`
- avg trade size 43,478 at the renormalized $5,000 book: live/proposals/proposal_2026-09-21.json `avg_trade_size` (notional / n_effective)
- E5 data_hash bump, both hashes: sprints/E5/RESULTS.json `revisions`
- Guard 1 cap 0.10, max kept weight 0.1452 at $5,000: live/guards.py, live/construction_table.parquet
- full-run count 682, fast-run count 659, slow 23: make test, make test-fast

### git diff --stat from base_commit (ea821bc)

```
 Makefile                         |   5 +-
 docs/hygiene_ledger.md           |  16 ++
 handoff/REPORT.md                | 440 ++++++++++++---------------------------
 live/construction_table.parquet  | Bin 0 -> 12733 bytes
 live/construction_table.py       | 216 +++++++++++++++++++
 live/evening_job.py              |  43 ++--
 live/sizing.py                   |  45 ++++
 pyproject.toml                   |   1 +
 tests/test_allocate.py           |   1 +
 tests/test_construction_table.py |  62 ++++++
 tests/test_costs.py              |   1 +
 tests/test_dashboard_app.py      |   3 +
 tests/test_e11_evening.py        |  20 +-
 tests/test_e11_extend.py         |   2 +
 tests/test_e4_probes.py          |   1 +
 tests/test_e4_results.py         |   1 +
 tests/test_eval_risk.py          |   4 +
 tests/test_fundamental.py        |   2 +
 tests/test_optimize.py           |   1 +
 tests/test_size.py               |   1 +
 20 files changed, 538 insertions(+), 327 deletions(-)
```

### Yes or no, each with evidence

1. **Any two rows or two estimators identical?** No. The six construction
   rows differ on every column (live/construction_table.parquet).
2. **Any exception caught and skipped, or any fallback taken?** No
   exception is caught and skipped. One fallback is taken by design: the
   pseudoinverse hedge fallback in live/sizing.py when a subset's X'X is
   singular, and the achieved exposure is reported, not hidden.
3. **Any criterion reworded or replaced by a different test?** No.
4. **Any criterion that passes by construction?** No. No new criterion was
   registered.
5. **Any number that moved by a factor of 10 or more?** Yes. The $5,000
   kept book's max weight is 0.1452 against the 0.10 guard cap, and its
   effective name count is 23 against 27 selected, both stated here.
6. **Any stored number typed into a notebook?** No notebook was touched.
7. **Any earlier verdict changed?** No. The E5 data_hash bump moved no
   verdict, and prior_verdict_changes() is 0 for E1 through E7.

### Anything decided that the reviewer might disagree with

The $10m test was removed rather than kept as a NAV-flexibility unit test,
because the task says to delete the $10m column and size nothing against
it; this removes one test (683 to 682 passing), named above. Guard 1 is
left at 0.10 until the owner picks a construction, even though the $5,000
row would breach it; re-deriving it now would choose the construction for
the owner.
