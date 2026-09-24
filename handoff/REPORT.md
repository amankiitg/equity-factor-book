# Sprint E11: the two-part floor to its fixed point, the beta in raw units

Task `e11-two-part-fixed-point-then-pick`, base commit 685920b. NAV is
$1,000,000, final. This task derives D10's label from the artifact, brings the
two-part floor to its fixed point, redoes the beta decomposition in raw-beta
units, and corrects the status report's closing section. Nothing here chooses a
construction and nothing re-derives Guard 1; the owner picks.

## D10's label is derived from the artifact, and the stored proposal says so

The stored 2026-09-21 proposal predates E11-F4 and E11-F6: it is the 27-name
book at kept gross 0.2734, kept idio share 0.8631 and kept max exposure 0.1458.
The page no longer labels it "min position $5,000", which is the selector's
99-name book. After the change the header reads, verbatim:

> The stored dry-run proposal is the book for the **2026-09-21** close, and its
> construction is **construction parameters not recorded in this artifact**.
> **27** names kept, **472** dropped, kept gross **0.2734**, kept idio share
> **0.8631**, kept max exposure **0.1458**. Run state: **dry run (the clock has
> not started)**.

The label is generated only from the proposal's stored fields, never asserted
beside the artifact, and the page does not fill the missing fields from the
registry or the table. `build_proposal` now stores the construction type, the
dollar and share floors, whether the floor was iterated, the kept gross before
and after renormalization, and the code commit, so a regenerated proposal
carries its own label. A test builds two artifacts with the same nominal floor,
one pre-iteration and one post-iteration, and asserts the page renders two
different labels with the right kept counts and gross.

The stored proposal was not regenerated. Regenerating would run the live path,
which still applies the one-pass floor (the fixed-point floor is a table
property until the construction is chosen), so it would produce the renormalized
27-name book, not a fixed-point book. The honest page shows the old book's own
numbers, and the selector is the decision surface.

## E11-F9: the two-part floor, one pass and at its fixed point

The combined floor is applied to a fixed point: name i is kept when its
post-renormalization notional is at least the dollar floor and at least 20
whole shares, which is the single condition ordered by
`|w_i| / max(1500, 20 * price_i)`. Pre and post now mean the same thing on
every row: one pass versus the fixed point.

| construction | kept (one-pass -> fixed) | n_eff kept | p90 (pre -> post) | max weight | governing breadth |
| --- | --- | --- | --- | --- | --- |
| min $1,500 | 208 -> 252 | 115.46 | 9.08% -> 11.93% | 3.95% | 1.167 |
| min $2,000 | 155 -> 208 | 102.77 | 5.59% -> 9.08% | 4.20% | 1.237 |
| min $3,000 | 82 -> 156 | 84.52 | 4.57% -> 5.34% | 4.66% | 1.364 |
| min $5,000 | 27 -> 99 | 56.49 | 41.66% -> 7.30% | 5.84% | 1.669 |
| top-N 150 | 150 -> 150 | 58.53 | 13.29% | 6.22% | 1.640 |
| top-N 200 | 200 -> 200 | 72.84 | 17.75% | 5.43% | 1.470 |
| two-part 1500+20sh | 92 -> 172 | 83.07 | 1.95% -> 3.22% | 4.75% | 1.376 |
| share-only 20sh | 118 -> 188 | 85.69 | 1.81% -> 3.44% | 4.68% | 1.355 |
| full book 499 | 499 -> 499 | 157.33 | 31.70% | 3.37% | 1.000 |

The owner's rule, stated before the numbers: if the two-part floor's n_eff is
close to min $1,500's, it wins outright. The fixed-point two-part floor's n_eff
is 83.07 against 115.46, which is 72 percent, and the share-only floor's is
85.69, 74 percent. Both are closer than the one-pass 52.82 the previous report
showed, but neither is close.

The 2.5% bound is stated and then corrected by the measurement. At the fixed
point every kept name holds at least 20 shares in the renormalized full-book
weights, so no name rounds by more than 0.5 / 20 = 2.5%. But the re-sizing on
the kept subset moves about one name in ten below 20 shares, so the measured p90
is 3.22% at the two-part floor and 3.44% at the share-only floor, above the
idealized bound and below the one-pass tail it replaced. The iteration moves p90
toward 2.5% and does not reach it.

## E11-F8: the beta split, redone in raw-beta units

For each stage the raw beta is regressed on the stage across the full
cross-section with XS-v1's cap weights, and the book's exposure to the residual
is reported. The book is dollar-neutral, so the intercept cancels and the
exposure is `w' raw - slope * w' stage`. At min $1,500:

| stage | book exposure to the residual | increment |
| --- | --- | --- |
| raw (TS-v1) | 0 | - |
| Vasicek shrunk | 0.0555 | 0.0555 (shrinkage + estimator gap) |
| 3-MAD clipped | 0.1081 | 0.0526 (the clip) |
| standardized | 0.1050 | -0.0031 (~zero) |
| finished descriptor | 0.1050 | 0 (the hedge zeroes it) |

The identity candidate is refuted: the residual at the Vasicek stage is 0.0555,
about half the 0.1050 raw beta, not near zero. The shrinkage is name-specific
through the standard error, so it removes about 47 percent of the raw beta
rather than rescaling it by a common k; the 3-MAD clip removes about 50 percent;
standardization and orthogonalization contribute zero to three decimals, as the
affine algebra predicts. The zero fill is not doing work either: no kept name on
any row is absent from the descriptor cross-section, so the zero-fill count is
0 everywhere. The median fill covers at most one name per row.

The full 499-name book carries 0.0936 raw beta, so most of the residual is the
signal's own tilt and the drop adds about 0.011. The raw beta is TS-v1's
unshrunk CAPM beta, frozen at 2026-09-03; XS-v1's own pre-shrinkage beta is not
stored in the artifact, so the first increment conflates the TS-v1/XS-v1
estimator gap with the Vasicek shrinkage and is labelled as such. The hygiene
ledger follow-up records the measurement and the refutation.

## D10: what the owner will actually see

The seven panels and the stored field each drew from: the label reads the
proposal manifest's construction fields; the selector reads
live/construction_table.parquet and live/construction_weights.parquet; the
answer reads data/alpha/summary.parquet and the proposal's n_names; the book
reads the proposal manifest's as-of, name count, idio share, gross, net, n_eff,
vols, cap and cost; the names panel reads the proposal's dated parquet; forecast
against outcome reads live/state/reconciliation.parquet; guard events reads
live/logs/execution_*.parquet; the clock reads live/clock.json.

A dry run has no fills, so there is no P&L, realized vol, Sharpe or drawdown
yet: the forecast-against-outcome panel shows the forecast vol beside a
not-yet-realized vol, and the guard panel shows dry-run statuses with no filled
notional.

What a Render deploy shows today, and why it is not deployment-ready. The local
page the owner runs with `make dashboard` is `dashboard/app.py` (D0 through D10
tabs), which reads local files and is not what Render builds. Render builds
`live/dashboard_app.py`, a different page that reads the Supabase live series
with a local fallback. The construction label and selector are in the local D10,
not in the Render page. `live/proposals/` is tracked in git, but `live/state/`
and `live/logs/` are gitignored, and the Render page does not read the proposal
directory anyway: it reads Supabase tables that stay empty until the daily cron
is wired and run. So a deployed page would not show a populated book today.

The owner's steps, in order: deploy the two Render services from render.yaml (a
web service and a weekday cron); set the dashboard's environment to
EFB_SUPABASE_URL and EFB_SUPABASE_SECRET_KEY only, and the cron's to those plus
EFB_ALPACA_PAPER_API_KEY, EFB_ALPACA_PAPER_SECRET_KEY and EFB_DRY_RUN; run the
one-time schema (live/supabase_schema.sql, or scripts/provision_supabase.py);
then confirm, per remaining-plan item 4c, that the deployed page reads Supabase
rather than local state. A read-only dashboard needs no Alpaca keys.

`make dashboard` is confirmed: it runs
`streamlit run dashboard/app.py --server.headless true` at
http://localhost:8501. The owner needs nothing else to reach D10: the tab is
named "D10 Book Monitor", the data files are already built locally, and no
environment variable is required.

## E11-F10: the status report's closing section is corrected

Four corrections to docs/research/STATUS_REPORT.md: the universe-reconstruction
sign-off is removed (the reconstruction is not scheduled and the universe stays
split); "E11's remaining work is the owner's" is replaced with remaining-plan
item 4 in order (Guard 1 against the chosen construction, the sanity gate on two
real closes, the Supabase wiring, then the flip); "deployment-ready" is replaced
with what was verified (renders locally, reads local state, not deployed); and
the realized-beta sentence now says the column was decomposed into raw-beta
units. The same correction is applied to the blockers section. The traceability
test still passes, and the table is described as nine rows.

## Verification

### Commands and output

`make test` (full run):

```
695 passed, 1 skipped, 3 warnings in 474.60s (0:07:54)
```

`make test-fast`:

```
669 passed, 1 skipped, 26 deselected, 3 warnings in 25.98s
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
panels with 'No data yet': 0; selector options: 9
```

### Headline numbers, file and key

- two-part fixed point kept 92 -> 172, n_eff 83.07: live/construction_table.parquet
  row `two_part_floor_1500_20shares`
- share-only fixed point kept 118 -> 188, n_eff 85.69: live/construction_table.parquet
  row `share_only_20shares`
- min $1,500 raw beta 0.1050, residual at Vasicek 0.0555, at clip 0.1081:
  live/construction_table.parquet row `min_position_1500`
- full book raw beta 0.0936: live/construction_table.parquet row `full_book_499`
- stored proposal header: kept 27, gross 0.2734, idio share 0.8631, max
  exposure 0.1458: live/proposals/proposal_2026-09-21.json

### git diff --stat from base_commit (685920b)

```
 dashboard/tabs/d10_book.py        |  93 ++++++++--
 docs/hygiene_ledger.md            |  56 ++++++
 docs/research/STATUS_REPORT.md    |   8 +-
 handoff/REPORT.md                 | 357 +++++++++++++++++++++-----------------
 live/construction_table.parquet   | Bin 24585 -> 29817 bytes
 live/construction_table.py        | 289 +++++++++++++++++++++++++++---
 live/construction_weights.parquet | Bin 26048 -> 39258 bytes
 live/evening_job.py               |  30 ++++
 tests/test_construction_table.py  |  65 +++++--
 tests/test_dashboard_d10.py       |  91 +++++++++-
 tests/test_e11_evening.py         |   9 +
 11 files changed, 778 insertions(+), 220 deletions(-)
```

### Yes or no, each with evidence

1. **Any two rows or two estimators identical?** Yes. Idio share is 1.0 and net
   dollar is zero on every row by construction of the exact FMP hedge and the
   net column, and top-N 150 and top-N 200 both read 0.135 raw beta to three
   decimals. The rows differ on n_kept, n_eff, p90, max weight and the residual
   exposures.
2. **Any exception caught and skipped, or any fallback taken, with counts?** No
   exception is caught and skipped. No row takes the pseudoinverse hedge
   fallback: n_effective equals n_kept on every row (252/252, 208/208, 156/156,
   99/99, 150/150, 200/200, 172/172, 188/188, 499/499).
3. **Any criterion reworded or replaced by a different test?** No.
4. **Any criterion that passes by construction?** No. No new criterion was
   registered.
5. **Any number that moved by a factor of 10 or more?** No stored number moved.
   The two-part row's pre/post columns were redefined to one-pass versus
   fixed-point, so its pre count changed from 252 to 92, stated here.
6. **Any stored number typed into a notebook?** No notebook was touched.
7. **Any earlier verdict changed?** No.

The one skipped test is
tests/test_e11_render.py `test_alpaca_live_connect_names_the_missing_dependency`,
which skips because alpaca-py is installed in the venv and the test exercises
the missing-dependency path. Rule 21 is met by the full-run count below: it must
be at least the previous full run of 682 recorded in LOG.md, and it is 695.

### Anything decided that the reviewer might disagree with

The stored proposal was not regenerated, because the live path still applies the
one-pass floor and regenerating would produce the renormalized 27-name book, not
a fixed-point book; the page shows the old book's own numbers under a
"not recorded" label. The beta decomposition fits the raw-on-stage regression
with XS-v1's cap weights at 2026-09-03, while the descriptor stages are read at
2026-09-21, so the first increment is labelled as shrinkage plus the TS-v1/XS-v1
estimator gap. Guard 1 is left at 0.10 and is not re-derived, because the
construction has not been picked.
