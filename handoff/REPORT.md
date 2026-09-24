# Sprint E11: share-only to the gate, over direct Postgres

Task `e11-share-floor-to-gate`, base commit 1957256. NAV is $1,000,000, final.
The owner chose the share-only construction (minimum 20 whole shares per name,
no dollar floor, iterated to a fixed point) at reserved decision 1. This task
takes that choice to the gate in eight parts, in order, each committed on its
own. `dry_run` stays `true` throughout; this task never flips it. This report
covers parts 1 and 2.

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

## Verification

Per STANDARDS 21, this step ran the subsets touching what changed plus lint;
the full suite runs before the task is marked done.

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

### git diff --stat from base_commit (1957256)

```text
 .env.example                    |  20 +++++--
 docs/hygiene_ledger.md          |  53 ++++++++++++++++++
 handoff/LOG.md                  |  70 +++++++++++++++++++++++
 handoff/PROJECT_CONTEXT.md      |  78 +++++++++++++++++---------
 handoff/TASK.md                 | 116 +++++++++++++++++++++++++++++++-------
 live/construction_table.parquet | Bin 29817 -> 29826 bytes
 live/construction_table.py      |   4 ++
 live/store.py                   | 120 ++++++++++++++++++++++++++++------------
 live/supabase_schema.sql        |  27 +++++----
 pyproject.toml                  |   4 +-
 render.yaml                     |  17 +++---
 requirements.txt                |   6 +-
 scripts/provision_supabase.py   |  13 +++--
 scripts/run_live_daily.py       |  12 +++-
 tests/test_e11_render.py        |  26 ++++++---
 15 files changed, 440 insertions(+), 126 deletions(-)
```

`handoff/LOG.md`, `handoff/PROJECT_CONTEXT.md` and `handoff/TASK.md` are the
owner's commit `921dee7` (the choice), included because they land between
`1957256` and here. Parts 1 and 2 are the rest; `tests/test_e11_store.py` is
new and untracked so it does not appear in the stat.

### Yes or no, each with evidence

1. **Any two rows or two estimators identical?** No. The two new ledger entries
   carry different numbers (0.0555 correction vs 0.054393 shrinkage split), and
   no construction-table row was rebuilt in this part.
2. **Any exception caught and skipped, or any fallback taken, with counts?** No.
   The store's local-parquet fallback is a configured path, not an exception
   handler, and it is not triggered in the tests that set a schema.
3. **Any criterion reworded or replaced by a different test?** No. The dry-run
   rule is implemented exactly as written (only an explicit false starts the
   clock).
4. **Any criterion that passes by construction?** No. The schema-qualification
   test reads the source, and the dry-run test drives the function, not a
   re-derivation.
5. **Any number that moved by a factor of 10 or more?** No. `n_beta_zero_filled`
   moved 0 to 1 and 0 to 2 on the rows that were miscounted, stated here.
6. **Any stored number typed into a notebook?** No notebook was touched.
7. **Any earlier verdict changed?** Yes, the two the task ordered: E11-F8's
   ledger verdict moved from refuted to undetermined (correction entry), then
   to refuted by the diagnostic split (0.054393 shrinkage increment, not near
   zero). Both are recorded in the append-only ledger.

### Anything decided that the reviewer might disagree with

The `supabase` client dependency was removed from `requirements.txt` and
`pyproject.toml` (nothing imports it after the move to `psycopg`), and
`psycopg[binary]>=3.1` now lives in the `live` extra. The provisioning script's
project URL variable was renamed to `EFB_SUPABASE_PROJECT_URL` so it cannot be
read as the withdrawn PostgREST connection. The full test suite is deferred to
the point before `done`, per STANDARDS 21.
