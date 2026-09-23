# Sprint E11: restore the decision columns, decompose beta, deploy D10

Task `e11-restore-columns-then-pick`, base commit 0df42f5. NAV is $1,000,000,
final. This task restores the six columns the decision rests on, decomposes the
realized-beta column before the owner uses it, moves the dashboard ahead of the
construction choice, and brings the status report current through E11. Nothing
here chooses a construction and nothing re-derives Guard 1; the owner picks.

## What changed

- **E11-F7, six restored columns.** Every row again carries n_eff kept, the
  naive and governing breadth, total gross error, post-hedge max factor
  exposure and idio share, beside the net, iteration and share columns.
- **E11-F8, the beta decomposed.** Every row now reports how many names were
  filled at the median, the realized beta excluding those fills, the realized
  beta against the pre-winsorization Vasicek value, the realized beta against
  XS-v1's own beta descriptor, and the correlation between the raw beta and
  that descriptor.
- **D10 moves ahead of the choice.** The page now names the construction it is
  rendering, and a selector pages through the seven books the table computed.
  The table writes a per-name weights artifact so D10 can show each book's
  names, weights and trade reasons.
- **The status report is current through E11**, with every number traceable to
  an artifact by a new test.

## The table, at $1m on the 2026-09-21 close

`live/construction_table.parquet`. Every row drops names, re-hedges on its own
subset, renormalizes to gross 1.0, then quantizes. Net dollar is zero on every
row, as before. p90 is the 90th percentile of per-name whole-share rounding
error.

| construction | kept (pre -> post) | n_eff kept | breadth naive | governing | total error | max exposure | idio share | max weight | p90 (pre -> post) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| min $1,500 | 208 -> 252 | 115.46 | 1.351 | 1.167 | 3.30% | 2.2e-15 | 1.0 | 3.95% | 9.08% -> 11.93% |
| min $2,000 | 155 -> 208 | 102.77 | 1.487 | 1.237 | 2.64% | 1.2e-15 | 1.0 | 4.20% | 5.59% -> 9.08% |
| min $3,000 | 82 -> 156 | 84.52 | 1.717 | 1.364 | 1.90% | 5.7e-16 | 1.0 | 4.66% | 4.57% -> 5.34% |
| min $5,000 | 27 -> 99 | 56.49 | 2.156 | 1.669 | 1.71% | 6.9e-16 | 1.0 | 5.84% | 41.66% -> 7.30% |
| top-N 150 | 150 -> 150 | 58.53 | 1.751 | 1.640 | 2.07% | 1.6e-15 | 1.0 | 6.22% | 13.29% -> 13.29% |
| top-N 200 | 200 -> 200 | 72.84 | 1.517 | 1.470 | 2.67% | 1.3e-15 | 1.0 | 5.43% | 17.75% -> 17.75% |
| two-part 1500+20sh | 252 -> 100 | 52.82 | 2.145 | 1.726 | 0.56% | 7.8e-16 | 1.0 | 6.21% | 11.93% -> 1.80% |

Full-book reference: n_eff 157.33 over 499 names.

## E11-F7: the six columns, and what they say

Post-hedge max factor exposure is below 2.3e-15 and idio share is 1.0 on every
row, so no row degenerates after the iteration; the rank-deficiency failure
that hit the pre-iteration $5,000 book is gone, and the table shows the
exposures rather than asserting them.

The trade the owner's decision rule turns on is visible in one row now. The
owner's rule, stated before the numbers: if the two-part floor's n_eff is close
to min $1,500's, it wins outright. The measured numbers are 52.82 against
115.46, which is 46 percent, so the two columns the rule names are restored and
the comparison is read off the table. Governing breadth moves from 1.167 at min
$1,500 to 1.726 at the two-part floor, which is the IR haircut the extra 152
names buy.

## E11-F8: the beta is decomposed, and the fill is not the answer

The realized beta is the raw, unshrunk CAPM beta against the kept weights. The
decomposition shows where the 0.105 to 0.147 comes from.

| construction | raw beta | names filled | beta ex fills | pre-win (Vasicek) | XS-v1 descriptor | corr raw vs descriptor |
| --- | --- | --- | --- | --- | --- | --- |
| min $1,500 | 0.105 | 1 | 0.103 | 0.046 | 1.7e-16 | 0.959 |
| min $2,000 | 0.107 | 1 | 0.105 | 0.046 | 2.7e-16 | 0.958 |
| min $3,000 | 0.114 | 1 | 0.112 | 0.048 | -7.6e-17 | 0.959 |
| min $5,000 | 0.130 | 0 | 0.130 | 0.058 | -2.2e-16 | 0.948 |
| top-N 150 | 0.135 | 0 | 0.135 | 0.048 | -1.8e-16 | 0.956 |
| top-N 200 | 0.135 | 0 | 0.135 | 0.055 | -6.9e-17 | 0.961 |
| two-part 1500+20sh | 0.147 | 0 | 0.147 | 0.064 | -1.4e-16 | 0.962 |

The median fill is not doing the work: at most one name per row is filled, and
excluding the fills leaves the beta unchanged to three decimals. The residual is
model mismatch, and it is now measured rather than asserted. The FMP hedge
zeroes XS-v1's own beta descriptor exactly (the descriptor column is 1e-16), so
the residual against the raw beta is whatever the descriptor pipeline removes.
That removal splits two ways: the Vasicek shrinkage takes the raw 0.105 down to
0.046 at min $1,500, and the winsorization, standardization and
orthogonalization take the rest to zero. The correlation between the raw beta
and the finished descriptor is 0.948 to 0.962, which quantifies the gap the
task asked for: the descriptor is not an affine transform of the raw beta, so
the hedge neutralizes a standardized rank, not the CAPM beta, exactly as the
owner read it. The residual is a property of the design, not a defect in the
hedge.

## D10: the dashboard moves ahead of the choice

The page now opens with what is on screen: the stored dry-run proposal for the
2026-09-21 close, the construction it is sized at, the kept and dropped counts,
the kept gross, and the run state. Below it a selector pages through all seven
books, each rendered with its names, weights and trade reasons plus the full
row: the six restored columns, the beta decomposition, and the error tail.

Verified locally against the stored proposal with Streamlit's test runner: the
app runs with zero exceptions, all seven D10 panels are populated (zero
"no data yet" reads), and the selector lists all seven constructions. The
stored proposal itself is the min $5,000 book, so the page names that
construction rather than showing an unnamed book.

What remains for the owner: the Render, Supabase and Alpaca credentials and the
deploy itself. What I could not verify without them: the deployed page, and
whether it reads Supabase rather than local state. D10 reads the local proposal
directory today; the Supabase read path exists in live/store.py and wiring the
page to it is the remaining-plan item 4c, after the choice. A locally rendering
page is not being treated as a deployed one.

## The status report, current through E11

docs/research/STATUS_REPORT.md now covers E1 through E11 in the same voice and
structure, states the three gates' answers, and corrects the E1 survivorship
figure to 365.10 bp. Every number in it is read from an artifact: a new test,
tests/test_status_report_traceability.py, fails the moment a quoted number and
a stored measurement disagree, matching on the signed value. One wrong rounding
was found and fixed while wiring the test: the ETF hedge removes 0.978494 of
factor variance, not 0.978493.

## Verification

### Commands and output

`make test` (full run):

```
692 passed, 1 skipped, 3 warnings in 469.56s (0:07:49)
```

`make test-fast`:

```
667 passed, 1 skipped, 25 deselected, 3 warnings in 23.51s
```

`make lint` plus `mypy live`:

```
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
Success: no issues found in 33 source files
.venv/bin/black --check efb dashboard live tests
All done!
162 files would be left unchanged.
=== mypy live ===
Success: no issues found in 15 source files
```

`make verify-evidence`:

```
evidence OK
```

The local render check (Streamlit test runner):

```
exceptions: 0; D10 label rendered: True; answer rendered: True;
panels with 'No data yet': 0; selector options: 7
```

### Headline numbers, file and key

- seven-row table with the six restored columns and the beta decomposition:
  live/construction_table.parquet
- per-name weights for the selector: live/construction_weights.parquet
- two-part n_eff 52.82 against min $1,500 n_eff 115.46:
  live/construction_table.parquet
- raw beta 0.105 to 0.147, pre-win 0.046 to 0.064, descriptor 1e-16:
  live/construction_table.parquet
- E1 survivorship 365.10 bp: sprints/E1/RESULTS.json, docs/research/STATUS_REPORT.md

### git diff --stat from base_commit (0df42f5)

```
 dashboard/tabs/d10_book.py             | 186 ++++++++++++++++++++++++
 docs/research/STATUS_REPORT.md         |  80 +++++++----
 handoff/REPORT.md                      | 304 ++++++++++++++++++++-------------------
 live/construction_table.parquet        | Bin 20918 -> 24585 bytes
 live/construction_weights.parquet      | new (per-name weights for D10)
 live/construction_table.py             | 160 +++++++++++++++++----
 tests/test_construction_table.py       |  18 +++
 tests/test_dashboard_d10.py            |  77 +++++++++-
 tests/test_status_report_traceability.py | new (121 lines)
```

### Yes or no, each with evidence

1. **Any two rows or two estimators identical?** No. The seven rows differ on
   every column (live/construction_table.parquet).
2. **Any exception caught and skipped, or any fallback taken?** No exception is
   caught and skipped. No row takes the pseudoinverse fallback (effective equals
   kept everywhere), stated above.
3. **Any criterion reworded or replaced by a different test?** No.
4. **Any criterion that passes by construction?** No. No new criterion was
   registered.
5. **Any number that moved by a factor of 10 or more?** No stored number moved;
   the E1 survivorship figure is corrected from 349 to 365.10 in prose, and the
   ETF variance-removal figure is re-rounded from 0.978493 to 0.978494, both
   stated here.
6. **Any stored number typed into a notebook?** No notebook was touched.
7. **Any earlier verdict changed?** No.

### Anything decided that the reviewer might disagree with

The beta decomposition reads XS-v1's descriptor stages from
data/models/XS-v1/descriptors.parquet at its latest date rather than
re-deriving them, and fills names the descriptor cross-section drops with 0 to
match the design's own nan_to_num; the method is stated in the code. D10 was
left reading local state, because wiring it to Supabase is remaining-plan item
4c after the construction choice, not this task. Guard 1 is left at 0.10 and is
not re-derived, because the construction has not been picked.
