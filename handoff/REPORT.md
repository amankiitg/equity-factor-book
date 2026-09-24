# Sprint E11: share-only to the gate, over direct Postgres

Task `e11-share-floor-to-gate`, base commit 1957256. NAV is $1,000,000, final.
The owner chose the share-only construction (minimum 20 whole shares per name,
no dollar floor, iterated to a fixed point) at reserved decision 1. This task
takes that choice to the gate in eight parts, in order, each committed on its
own. `dry_run` stays `true` throughout; this task never flips it. This report
covers parts 1 to 5.

## Part 1: E11-F8 ledger correction, then the diagnostic split

Committed as `a41359c`. Two new append-only entries in
`docs/hygiene_ledger.md`; the 2026-09-23 entry is not edited.

**Correction entry (undetermined).** Three fixes to the overclaiming entry:

1. The shrinkage increment is 0.0555 at min $1,500, which is 53 percent of the
   0.1050 raw beta, not 0.0495 (47 percent). The increments sum to the total
   only this way: 0.0555 + 0.0526 - 0.0031 = 0.1050.
2. The nonzero standardization increment is a zero-fill artifact, not
   standardization doing anything. The standardized stage is affine in the
   clipped stage to machine precision (standardized = 1.5475 x clipped -
   1.4978, max residual 8.8e-16), and a regression residual is invariant to an
   affine regressor change. The two names FDXF and HONA (recent listings) are
   present in the descriptor cross-section but carry no descriptor value, so
   they are filled with 0 in every stage, and an affine map does not carry 0
   to 0; those two points break it. The earlier zero-fill count of 0 everywhere
   was a miscount: it is 2 in the full book and 1 in the minimum-position
   subsets that keep one of them.
3. "Refuted" was not established, so the candidate is recorded undetermined,
   with 0.0555 as an upper bound on the shrinkage's contribution (the Vasicek
   increment regresses TS-v1's frozen 2026-09-03 raw beta on XS-v1's
   2026-09-21 shrunk beta, mixing shrinkage, estimator gap and window drift).

The miscount is fixed in the table: `live/construction_table.py`
`_load_beta_stages` now adds a name to the zero-fill set when its descriptor
value is NaN (`if pd.isna(descriptor): zero_filled.add(ticker)`), not only when
the name is absent. `n_beta_zero_filled` is now 1 in the minimum-position
subsets and 2 in the full book.

**Diagnostic split entry (refuted, measured).** Recomputing XS-v1's
pre-shrinkage beta at 2026-09-21 under the frozen specification (diagnostic
only: nothing restated, nothing stored, the specification unchanged) and
inserting it as a stage splits the 0.0555: the raw-to-XS-v1-raw increment is
0.000031 (the TS-v1/XS-v1 estimator gap plus the date gap, 0.03 percent of the
raw beta), and the XS-v1-raw-to-Vasicek increment is 0.054393 (51.8 percent of
the 0.104987 raw beta). The shrinkage increment is not near zero, so E11-F8
does not join the identity class: the shrinkage removes 52 percent of the raw
beta, and the clip removes the rest.

## Part 2: E11-F11, the store over direct Postgres

The connection settled in LOG.md line 1064 and the TASK.md B1 amendment is
direct Postgres under `EFB_SUPABASE_DB_URL` with `EFB_DB_SCHEMA=efb`, never
PostgREST. The four rules are met, and nothing required a stop.

**1. Which connection the store and the dashboard actually use.** Direct
Postgres, schema `efb`, with a local parquet fallback. The evidence is the code
itself:

- `live/store.py` `get_connection()` reads `EFB_SUPABASE_DB_URL` and returns
  `psycopg.connect(url)`; it never touches a Supabase client or PostgREST. The
  `_qualified(table)` helper returns `f'"{_schema()}"."{table}"'`, and every
  statement goes through it: `_upsert_sql` emits
  `INSERT INTO {_qualified(table)} ... ON CONFLICT ...` and `select` emits
  `SELECT * FROM {_qualified(table)} ORDER BY 1`. Nothing targets `public` or
  an unqualified name.
- `live/dashboard_app.py` has no connection of its own: its only data call is
  `return store.select(name)` (line 33), so it inherits the direct-Postgres
  path and only ever reads.
- The one-time setup is `live/supabase_schema.sql`, whose first statement is
  `create schema if not exists efb;` followed by `create table if not exists
  efb.*` for the eight live-series tables.

**2. Moved to direct Postgres; no stop.** `render.yaml` now carries
`EFB_SUPABASE_DB_URL` and `EFB_DB_SCHEMA` on both services, never
`EFB_SUPABASE_URL`/`EFB_SUPABASE_SECRET_KEY`. `.env.example` was rewritten to
match. Because direct Postgres does not depend on the project's "Exposed
schemas" API setting, no dashboard change and no shared-role grant is needed,
so the stop condition does not fire.

**3. The dashboard's least-privilege credential.** The dashboard only reads, so
it should hold a SELECT-only Postgres role's connection string in its own
`EFB_SUPABASE_DB_URL`, with `EFB_DB_SCHEMA=efb`; the cron holds the write
role's string. The owner creates that role and its grants on the shared
project; I did not create any role or grant.

**4. What uses `EFB_SUPABASE_ACCESS_TOKEN`.** Only
`scripts/provision_supabase.py`, for the one-time Supabase Management API call
that applies `live/supabase_schema.sql`. It is account-wide and must never
reach a Render service; it does not appear in `render.yaml` for either service
(a test asserts `"EFB_SUPABASE_ACCESS_TOKEN" not in render`). The script's
project URL variable was renamed to `EFB_SUPABASE_PROJECT_URL` so it cannot be
confused with the withdrawn PostgREST connection names.

**5. `EFB_DRY_RUN` resolution.** `scripts/run_live_daily.py` now holds the rule
in one testable function:

```python
def resolve_dry_run(value: str | None) -> bool:
    """The clock starts only on the literal string "false", any case."""
    return (value or "").strip().lower() != "false"
```

`main()` uses `resolve_dry_run(os.environ.get("EFB_DRY_RUN"))`. Unset, empty,
whitespace, unparseable, and every spelling other than an explicit false all
resolve to dry run. The test over those cases:

```python
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, True), ("", True), ("   ", True), ("true", True), ("TRUE", True),
        ("True", True), ("yes", True), ("1", True), ("0", True),
        ("garbage", True), ("false", False), ("FALSE", False), ("False", False),
    ],
)
def test_dry_run_resolves_to_dry_run_unless_false(value, expected):
    assert run_live_daily.resolve_dry_run(value) is expected
```

A schema-qualification test also pins the decision: it reads `live/store.py`
and `live/supabase_schema.sql` and asserts every SQL statement goes through
`_qualified`, no statement targets `public` or an unqualified name, and the
schema default is `efb`.

**Deploy steps, updated to match.** In order: deploy the two Render services
from `render.yaml`; set the dashboard's environment to `EFB_SUPABASE_DB_URL`
(read-only role) and `EFB_DB_SCHEMA`; set the cron's to those plus
`EFB_ALPACA_PAPER_API_KEY`, `EFB_ALPACA_PAPER_SECRET_KEY` and `EFB_DRY_RUN`;
run the one-time schema over direct Postgres (the provisioning script, or the
SQL itself); then confirm the deployed page reads Postgres. Neither service
gets the service-role key or the management token.

## Part 3: E11-F12, the floor enforced on final weights

The floor is now checked on the vector that actually trades, not the full-book
weights. `live/evening_job.py` gains `finalize_kept_set` (size, hedge,
renormalize, quantize one kept set), `below_floor`, `floor_shortfalls` and
`enforce_floor_on_final_weights` (drop, re-size, re-hedge, renormalize,
quantize, check, repeat until no kept name is below its floor, with a 30-pass
guard). `_compute_row` uses the same `finalize_kept_set`, and every floor row
in the table is enforced from the full book. The live path enforces the
share-only 20-share floor from the full book and records the construction in
the manifest.

**Measure first, as it stands.** On the full-weight fixed point, the bug
E11-F12 names is real: kept names end below their floor in the final weights.

| row | kept (full-weight fixed) | below floor in final weights | worst shortfall |
| --- | --- | --- | --- |
| min $1,500 | 252 | 31 | $1,500.00 |
| min $2,000 | 208 | 19 | $1,737.89 |
| min $3,000 | 156 | 21 | $3,000.00 |
| min $5,000 | 99 | 19 | $5,000.00 |
| two-part 1500+20sh | 172 | 26 | 18 shares / $1,370.02 |
| share-only 20sh | 188 | 24 | 19 shares |

**Enforced on final weights, every floor row.** Starting from the full book
and iterating to the fixed point (3 passes on every floor row, all converged):

| construction | enforced names | n_eff | naive breadth | governing breadth | total error | p90 | max weight | net | long/short | raw beta | post-hedge exposure | idio share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| min $1,500 | 194 | 98.74 | 1.540 | 1.262 | 2.50% | 8.82% | 4.30% | 0 | 86/108 | 0.1086 | ~1e-15 | 1.0 |
| min $2,000 | 145 | 81.68 | 1.781 | 1.388 | 1.92% | 5.93% | 4.74% | 0 | 61/84 | 0.1141 | ~6e-16 | 1.0 |
| min $3,000 | 72 | 44.48 | 2.528 | 1.881 | 0.91% | 2.93% | 6.73% | 0 | 23/49 | 0.1101 | ~8e-16 | 1.0 |
| min $5,000 | 23 | 14.10 | 4.472 | 3.340 | 0.48% | 1.68% | 14.52% | 0 | 9/14 | -0.0118 | ~2e-15 | 1.0 |
| two-part 1500+20sh | 87 | 51.19 | 2.299 | 1.753 | 0.56% | 1.40% | 6.40% | 0 | 39/48 | 0.1388 | ~1e-15 | 1.0 |
| share-only 20sh | 119 | 58.82 | 1.966 | 1.635 | 0.64% | 2.04% | 5.96% | 0 | 56/63 | 0.1337 | ~1e-15 | 1.0 |

The enforced share-only book is 119 names, n_eff 58.82, total error 0.64% and
p90 2.04%. Against the unenforced table numbers (188 names, n_eff 85.69, total
error 1.25%, p90 3.44%) the enforced book is smaller and rounder: enforcement
drops the names that could not hold 20 shares, so the rounding tail shrinks
while n_eff falls from 85.69 to 58.82. The n_eff fall is reported plainly, not
called close: it is a 31 percent fall.

**The breadth bound, both ways.** PROJECT_CONTEXT requires any E11 number that
meets an E8 transfer coefficient to state the bound both ways. The governing
breadth is sqrt(n_eff_full / n_eff_kept): with n_eff_full 157.33 and the
enforced n_eff 58.82, that is sqrt(157.33 / 58.82) = 1.635, so the enforced
book's governing breadth is 1.635x. The naive bound is sqrt(460 / 119) = 1.966.

**The re-decide trigger, pre-registered before the numbers existed.** Compare
the enforced share-only book against the enforced min $2,000 book, never the
unenforced row. (a) Share-only still has both lower total error (0.64% vs
1.92%) and lower p90 (2.04% vs 5.93%) than enforced min $2,000. (b) No
enforced row is strictly better-or-equal on both n_eff and total error than
share-only: min $1,500 and min $2,000 have higher n_eff but higher error;
min $3,000, min $5,000 and the two-part row have lower error but lower n_eff.
Neither branch fires, so the task proceeds. (For the owner's reading: enforced
min $5,000 has lower total error and lower p90 than share-only, at the cost of
n_eff 14.10, which is why branch (b) is defined on n_eff and total error
jointly.)

The live path produces the same book as the table's enforced share-only row:
`build_proposal(store=False)` returns construction `share_only`, share floor
20, `floor_iterated` true, 119 names, n_eff_kept 58.82, governing breadth
1.635.

## Part 4: the registry records the chosen construction

XS-v1's `live` block in `data/models/registry.json` is replaced:
`min_position_dollars` (E11 Addition 4) is withdrawn, and the entry now reads
`construction: share_only`, `share_floor: 20`, `dollar_floor: 0`,
`floor_iterated: true`. `efb/registry.py` gains `live_construction(payload,
version)`, which the live path reads; `build_proposal` now takes its
construction from the registry rather than a constant, and the manifest's
`construction`, `construction_floor_shares`, `construction_floor_dollars` and
`floor_iterated` fields come from that read. `min_position_dollars` stays as
the legacy reader and now returns zero because the key is gone.

**The E5 `data_hash` moved, and only that moved.** `e5_data_hash` hashes
`models/registry.json` directly, so the edit moves `sprints/E5/RESULTS.json`'s
`data_hash` from `a4c40c67…` to `6dca1f8d…`. Per STANDARDS rule 22 it is
recorded through the `revisions` block with both hashes: `n_changed` is 0, the
`history` list gains a third entry carrying `previous_data_hash` a4c40c67… and
`data_hash` 6dca1f8d…, and the criteria and reference_values are byte-identical
(verified with a sorted-JSON comparison). No other sprint's hash moves: E4
reconstructs the registry without the `live` block, E1/E6/E7/E8/E9/E10 folds
do not read `registry.json`, and E2/E3's stored hashes are historical VERSION
readings that are not touched on disk.

**The evidence chain follows.** `data/VERSION.json`'s `registry.json` entry is
updated to the new sha256 `142afe1f…` (its `data_hash` is unchanged, because
`combined_hash` skips `registry.json` as a non-data artifact), and the
evidence snapshot is refreshed for the two moved files (`registry.json.gz`,
`VERSION.json.gz`); the raw snapshots are reverted untouched. `make
verify-evidence` passes, and the E5 walkthrough notebook is re-executed so its
printed hash matches (only the hash and execution timestamps moved; no stored
criterion number changed).

**`docs/open_items.md` close-out.** The minimum-position item closes as a share
floor; the residue (fold the floor back into E8's own construction stack)
stands.

## Part 5: Guard 1 re-derived against the chosen construction's final weights

Guard 1 is re-derived from the chosen share-only book's final (quantized)
weights, sized from the largest final position across every close the loop has
run, not one close. For each close the enforced share-only book is recomputed
and its largest whole-share position read in dollars:

| close | kept | largest final position | % of NAV |
| --- | --- | --- | --- |
| 2026-09-03 | 124 | MU, $62,280 | 6.23% |
| 2026-09-18 | 116 | MRNA, $65,005 | 6.50% |
| 2026-09-21 | 119 | MU, $59,506 | 5.95% |

The largest legitimate target across all of them is $65,005, 6.50% of NAV, so
ten times the largest name is 65.0% of NAV. The cap stays at
`MAX_POSITION_PCT_OF_NAV = 0.10` — $100,000 at the $1,000,000 NAV — which
clears the 6.50% target with 1.54x headroom (0.065 to 0.10) and trips a
ten-times order on the largest name (0.650 > 0.10). The value is NAV-relative,
so it scales with the book. The boundary and the 10x trip are pinned by
`tests/test_e11_guards.py`, whose largest-legitimate constant moved from 0.0326
to 0.065. The arithmetic and the basis change are recorded in a new
`docs/hygiene_ledger.md` entry.

## Verification

Per STANDARDS 21, per-step subsets plus lint ran after each part; the full
suite ran after the Part 3 artifact rebuild and again after the Part 4
`efb/registry.py` change.

Part 1 subset (construction table and traceability):

```text
$ .venv/bin/pytest tests/test_construction_table.py tests/test_readme_traceability.py tests/test_status_report_traceability.py -q
15 passed in 24.90s
```

Part 2 subset (store, render wiring, daily dry-run resolution):

```text
$ .venv/bin/pytest tests/test_e11_store.py tests/test_e11_render.py tests/test_run_live_daily.py -q
30 passed, 1 skipped in 0.91s
```

Part 3 subsets (the floor enforcement, the live path, the dashboard):

```text
$ .venv/bin/pytest tests/test_construction_table.py -q
7 passed in 25.30s

$ .venv/bin/pytest tests/test_e11_evening.py -q
17 passed in 21.87s

$ .venv/bin/pytest tests/test_dashboard_d10.py tests/test_e11_render.py -q
25 passed, 1 skipped in 1.02s
```

Part 4 subsets (registry, E5 hash and notebook, evidence, the live path):

```text
$ .venv/bin/pytest tests/test_registry.py tests/test_e5_walkthrough_notebook.py tests/test_e8_results.py tests/test_e11_evening.py tests/test_build_e2.py tests/test_build_e3.py tests/test_e11_store.py tests/test_e11_render.py -q
89 passed, 1 skipped in 28.37s

$ .venv/bin/pytest tests/test_evidence.py -q
1 passed in 0.54s
```

Part 5 subset (the re-derived Guard 1):

```text
$ .venv/bin/pytest tests/test_e11_guards.py -q
7 passed in 0.02s
```

Full suite (latest, after the Part 4 `efb/registry.py` change):

```text
$ make test
719 passed, 1 skipped, 3 warnings in 447.64s (0:07:27)
```

The previous full-run count in LOG.md is 692; 719 clears it.

```text
$ make verify-evidence
evidence OK
```

Lint:

```text
$ make lint
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
Success: no issues found in 33 source files
.venv/bin/black --check efb dashboard live tests
All done! ✨ 🍰 ✨
163 files would be left unchanged.
```

`mypy live` (the live package is checked separately from `make lint`):

```text
$ .venv/bin/mypy live
Success: no issues found in 15 source files
```

### Headline numbers, file and key

- Shrinkage increment 0.0555 and the corrected sum 0.0555 + 0.0526 - 0.0031 =
  0.1050: `docs/hygiene_ledger.md`, 2026-09-24 correction entry, stated from
  the `residual_exposure_*` columns of `live/construction_table.parquet`,
  `min_position_1500` row.
- Estimator+date gap 0.000031 and shrinkage increment 0.054393 (51.8 percent of
  0.104987 raw beta): `docs/hygiene_ledger.md`, 2026-09-24 diagnostic split
  entry, computed at min $1,500 from the table weights and the frozen XS-v1
  specification in `efb/models/fundamental.py`.
- `n_beta_zero_filled` = 1 (minimum-position subsets) and 2 (full book):
  `live/construction_table.parquet`, `n_beta_zero_filled` column.
- Enforced share-only book: 119 names, n_eff 58.82, total error 0.006426,
  p90 0.020385, governing breadth 1.635, max weight 0.059617, raw beta
  0.133743: `live/construction_table.parquet`, `share_only_20shares` row,
  `n_kept` / `n_eff_kept` / `total_gross_error_share_of_nav` /
  `quant_error_p90_pct_of_target` / `breadth_governing` /
  `max_weight_share_of_gross` / `realized_market_beta` columns.
- Enforced min $2,000 book: 145 names, n_eff 81.68, total error 0.019150,
  p90 0.059304: `live/construction_table.parquet`, `min_position_2000` row.
- The below-floor counts on the unenforced full-weight fixed point (31, 19,
  21, 19, 26, 24) and worst shortfalls: `live/construction_table.parquet`,
  `n_below_floor_final_pre_enforcement` and
  `worst_floor_shortfall_*_pre_enforcement` columns.
- Live path matches the table: `build_proposal` returns `share_only`, share
  floor 20, `floor_iterated` true, 119 names, n_eff_kept 58.82.
- Registry construction: `data/models/registry.json`, XS-v1 `live` block,
  `construction: share_only`, `share_floor: 20`, `dollar_floor: 0`,
  `floor_iterated: true`.
- E5 data_hash moved a4c40c67… -> 6dca1f8d…: `sprints/E5/RESULTS.json`,
  `data_hash` and `revisions` block (`n_changed` 0, three history entries).
- Registry sha256 in the version manifest: `data/VERSION.json`,
  `artifacts.registry.json.sha256` = 142afe1f….
- Guard 1 largest legitimate target: MRNA $65,005 (6.50% of NAV) at the
  2026-09-18 close, with MU $62,280 (6.23%) at 09-03 and MU $59,506 (5.95%)
  at 09-21: recomputed from the enforced share-only final weights at each
  close. The cap stays 0.10 ($100,000), 1.54x headroom over 0.065.

### git diff --stat from base_commit (1957256)

```text
 data/models/registry.json             |   7 +-
 docs/hygiene_ledger.md                |  69 ++++
 docs/open_items.md                    |  12 +
 efb/registry.py                       |  22 ++
 evidence/MANIFEST.json                |  20 +-
 evidence/data/VERSION.json.gz         | Bin 7972 -> 7984 bytes
 evidence/data/models/registry.json.gz | Bin 4389 -> 4383 bytes
 handoff/LOG.md                        |  70 ++++
 handoff/PROJECT_CONTEXT.md            |  78 ++--
 handoff/REPORT.md                     | 667 ++++++++++++++++++++++------------
 handoff/TASK.md                       | 116 ++++--
 live/construction_table.parquet       | Bin 29817 -> 37356 bytes
 live/construction_table.py            | 271 +++++++++++---
 live/construction_weights.parquet     | Bin 39258 -> 33674 bytes
 live/evening_job.py                   | 204 +++++++++--
 live/guards.py                        |  18 +-
 live/store.py                         | 120 ++++--
 live/supabase_schema.sql              |  27 +-
 notebooks/E5_walkthrough.ipynb        |  94 ++---
 pyproject.toml                        |   4 +-
 render.yaml                           |  17 +-
 requirements.txt                      |   6 +-
 scripts/provision_supabase.py         |  13 +-
 scripts/run_live_daily.py             |  12 +-
 sprints/E5/RESULTS.json               | 238 +++++++++++-
 tests/test_construction_table.py      |  31 ++
 tests/test_e11_evening.py             |  54 ++-
 tests/test_e11_guards.py              |   8 +-
 tests/test_e11_render.py              |  26 +-
 tests/test_e11_store.py               |  97 +++++
 tests/test_registry.py                |  30 ++
 33 files changed, 1824 insertions(+), 531 deletions(-)
```

`handoff/LOG.md`, `handoff/PROJECT_CONTEXT.md` and `handoff/TASK.md` are the
owner's commit `921dee7` (the choice), included because they land between
`1957256` and here. The rest is parts 1 to 5.

### Yes or no, each with evidence

1. **Any two rows or two estimators identical?** No. The enforced floor rows
   differ on names, n_eff, total error, p90, max weight and raw beta; top-N
   150 and top-N 200 still both read 0.135 raw beta to three decimals, stated
   as in the prior report.
2. **Any exception caught and skipped, or any fallback taken, with counts?**
   No. The enforcement loop converged in 3 passes on every floor row
   (`floor_enforcement_converged` true, `floor_enforcement_passes` 3); no pass
   cap was hit and no pseudoinverse hedge fallback was taken (n_effective
   equals n_kept on every row).
3. **Any criterion reworded or replaced by a different test?** No. The floor is
   enforced exactly as written: drop, re-size, re-hedge, renormalize, quantize,
   check, repeat.
4. **Any criterion that passes by construction?** No. The enforcement test
   reads the stored table and asserts the below-floor count is zero on the
   enforced rows, which is a real check, not a re-derivation.
5. **Any number that moved by a factor of 10 or more?** No. `n_kept` on the
   floor rows moved by a factor of 2 to 4 (e.g. share-only 188 to 119, min
   $5,000 99 to 23), and total error and p90 moved down by factors under 5,
   stated here.
6. **Any stored number typed into a notebook?** No. The E5 notebook was
   re-executed (its hash cell recomputes `e5_data_hash`), and no stored number
   was edited by hand; only the printed hash and execution timestamps moved.
7. **Any earlier verdict changed?** Yes, the two the task ordered in part 1:
   E11-F8's ledger verdict moved from refuted to undetermined (correction
   entry), then to refuted by the diagnostic split (0.054393 shrinkage
   increment, not near zero). Part 4 changes no criterion verdict: the E5
   data_hash moved (a4c40c67… -> 6dca1f8d…) with `n_changed` 0, and the
   criteria are byte-identical. Part 5 changes no verdict: Guard 1's cap
   value stays 0.10; only its derivation basis moves to the share-only final
   weights.

### Anything decided that the reviewer might disagree with

The `supabase` client dependency was removed from `requirements.txt` and
`pyproject.toml` (nothing imports it after the move to `psycopg`), and
`psycopg[binary]>=3.1` now lives in the `live` extra. The provisioning script's
project URL variable was renamed to `EFB_SUPABASE_PROJECT_URL` so it cannot be
read as the withdrawn PostgREST connection. The enforced rows start from the
full book, not from the old full-weight fixed point, because the floor is the
only selection rule and the comparison must be like-for-like; the old
full-weight fixed point is retained as the "as it stands" measurement.
Enforcement is applied to the six floor rows, not to top-N and the full book,
which carry no position floor and keep a vacuous stamp. The stored proposal is
not regenerated in this part (part 6 does that), so the dashboard still shows
the old book under its own "not recorded" label until part 6.

The E5 RESULTS.json revisions block was written through the project's own
`evaluate.write_results` with the unchanged criteria, so the `changed` map now
shows old equals new for every criterion and a third history entry carries the
hash transition; this is the sanctioned path, not a hand edit. The evidence
snapshot was refreshed only for the two moved files; `evidence.snapshot()`
rewrites every gzip with a fresh mtime, so the untouched raw snapshots were
reverted and their manifest entries restored to keep the diff honest. The
`supabase`-client removal and the legacy `min_position_dollars` manifest field
(set to the registry's dollar floor, 0.0) are kept so the dashboard's
label-from-artifact rule reads the new `share_only` fields.
