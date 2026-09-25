# Sprint E11, Part 2: the model inputs as a git seed plus a Postgres appendix

**The reviewer's ruling first, because it unblocked this part.** The 51-name
rank margin gates the book that trades, not the comparison table. The min $5,000
row stays with its violation recorded, the other four checks stay armed on every
row, and the live path's raise on a check failure is the guard that fails a day
whose book falls under 51 names. The share-only book at `dd41d9b` is confirmed:
150 names, n_eff 70.59, total error 0.689%, p90 1.887%, max weight 5.35%.

**The minor correction the review asked for.** Part 1R's Verification item 1
answered "no" and then described identical columns, which is the answer form the
reviewer flagged. The honest form is: yes, two pairs of floor rows carry
identical **prefix** columns, confined to the superseded prefix measurement and
explained by it (the min $1,500 and min $2,000 rows share an ordering and a
stopping `k` of 131; the min $3,000 and min $5,000 rows share `k` of 3), and no
two rows' **books** are identical. This report uses that form.

## Part 2, item 1: what the code does now on a fresh container

On a fresh Render container the nine model inputs live only in the deployed git
artifacts. Each is read from disk, extended in place, and the appended session is
written back to the same disk path, which the next container loses.

| input | read from, and by | the appended session is written by |
| --- | --- | --- |
| prices | `data/raw/prices.parquet`, read by `probes.load_panel` and `evening_job._close_prices` | `live/extend.py::extend_prices`, `combined.to_parquet(path)` |
| descriptors | `data/models/XS-v1/descriptors.parquet`, read by `probes.load_panel` and `evening_job._input_as_of` | `live/extend.py::extend_model`, `pd.concat([existing_desc, new_desc], ignore_index=True).to_parquet(descriptors_path, index=False)` |
| factor_returns | `data/models/XS-v1/factor_returns.parquet`, same readers | `live/extend.py::extend_model`, `factor_full.to_parquet(factor_path, index=False)` |
| specific_returns | `data/models/XS-v1/specific_returns.parquet`, same readers | `live/extend.py::extend_model`, `specific_full.to_parquet(specific_path, index=False)` |
| factor_cov | `data/models/XS-v1/factor_cov.parquet`, read by `eval_risk._xs_pieces`; a snapshot with no date | `live/extend.py::extend_model` recomputes `fx.ewma_factor_cov` over the whole factor history and overwrites the file |
| specific_var | `data/models/XS-v1/specific_var.parquet`, read by `eval_risk._xs_pieces` and `trade_reasons` | `live/extend.py::extend_model`, `pd.concat([...]).to_parquet(sv_path, index=False)` |
| shares | `data/raw/shares_history.parquet`, read by `probes.load_panel` | `live/extend.py::extend_shares` calls `probes.fetch_share_history`, which writes `efb/probes.py:490` `cached.to_parquet(path, index=False)` |
| sectors | `data/processed/sectors.parquet`, read by `probes.load_panel` and `evening_job._input_as_of` | `live/extend.py::extend_archives` calls `universe.archive_constituents`, which writes `efb/universe.py:85` `constituents.to_parquet(path, index=False)` |
| universe (SPY) | the newest `data/raw/spy_holdings/spy_holdings_*.parquet`, read by `evening_job.load_spy_universe` | `live/extend.py::extend_archives` calls `spy.archive_snapshot`, which writes a new dated file at `efb/spy.py:234` `payload.to_parquet(path, index=False)` |

The hazard is the two ends of that table. `extend_prices` downloads from the last
stored date, so a container that starts from the deployed artifacts re-extends
from the deploy date every evening; and `evening_job._input_as_of` reads
whatever dates the files hold, so a run that skips the extension prices a book
from stale inputs and reports it as fresh. Nothing in the code tells the two
apart.

## Part 2, item 2: the migration cost

**Rows and megabytes per input.** Measured from the committed artifacts: the
whole artifact, the eleven sessions after the seed cutoff of 2026-09-03, and the
bytes per session that the appendix adds.

| input | artifact MB | rows | rows after the cutoff | sessions | rows per session |
| --- | --- | --- | --- | --- | --- |
| prices | 61.233 | 3,606,680 | 9,086 | 11 | 826 |
| descriptors | 19.259 | 702,800 | 38,654 | 11 | 3,514 |
| factor_returns | 1.429 | 71,136 | 198 | 11 | 18 |
| specific_returns | 16.172 | 1,848,332 | 5,467 | 11 | 497 |
| specific_var | 2.248 | 93,944 | 5,489 | 11 | 499 |
| factor_cov | 0.015 | 18 (a 17x17 snapshot) | 324 values | 11 | 289 values |
| shares | 2.146 | 434,462 | 53 | 10 | 5 |
| sectors | 0.010 | 503 | 503 | 1 | 2 |
| universe | 0.019 per file | 1,006 | 1,006 | 2 | 503 |
| **total** | **164.6 (with returns, which is derived)** | | **60,780 rows** | | **6,164** |

**The run's read and write time.** Measured on a copy of the real artifacts with
the local fallback, which is the same code path with a filesystem instead of the
session pooler: `appendix.hydrate` 2.93s, `persist_new_sessions` 0.71s on the
first pass and 0.58s on the second, byte-identical in content. The appendix held
9,086 prices rows, 38,654 descriptor rows, 5,467 specific-return rows, 5,489
specific-variance rows, 198 factor-return rows, 53 share rows, 503 sector rows
and 1,006 universe rows, and the second persist left every count unchanged. The
network cost of the same calls through the session pooler is unmeasured: it
needs a `postgresql://` connection string, which is not on this machine.

**The code touched.** `live/appendix.py` is new (the specs, `artifact_rows`,
`hydrate`, `persist_new_sessions`, `appendix_manifest`). `live/supabase_schema.sql`
gains nine `e11_*` tables. `live/evening_job.py` takes an optional `appendix`
argument and stores it in the manifest. `scripts/run_live_daily.py` hydrates
before the extensions, persists after them, and passes the appendix identity
into `build_proposal`. `tests/test_e11_appendix.py` is new.

## Part 2, item 3: the database size against the free tier

**What the appendix holds.** Only sessions after 2026-09-03. The rolling
estimators need history before that cutoff, and the seed supplies it, so the
appendix carries nothing the seed already has.

**EFB's own projection, one year of appends (252 sessions).** Row widths are the
Postgres heap cost (24-byte tuple header, 4-byte line pointer, the column widths,
aligned to 8) plus about 30% for the primary-key index.

| table | rows a year | MB a year |
| --- | --- | --- |
| `efb.e11_prices` | 208,152 | 36.8 |
| `efb.e11_descriptors` | 885,528 | 147.4 |
| `efb.e11_specific_var` | 125,748 | 18.3 |
| `efb.e11_specific_returns` | 125,244 | 13.0 |
| `efb.e11_universe` | 126,756 | 30.3 |
| `efb.e11_factor_cov` | 72,828 | 9.8 |
| `efb.e11_factor_returns` | 4,536 | 0.7 |
| `efb.e11_shares` | 1,260 | 0.2 |
| `efb.e11_sectors` | 504 | 0.1 |
| **total** | **1,550,556 rows** | **256.7** |

Plus the live series in `efb` (positions at 150 rows a session, proposals,
reconciliations, NAV, cron runs, run status), about 4.5 MB a year. So EFB's own
share after a year is **about 261 MB, which is 52% of a 500 MB free-tier cap**.
The descriptor table is 57% of it, because the artifact carries four value
columns per descriptor per name per session.

**The credit lab's current size could not be read, and that is a hole in this
item.** The task asks for it read-only. Three routes were tried and none is
available on this machine:

1. `pg_database_size` through the Management API needs
   `EFB_SUPABASE_ACCESS_TOKEN`, which is **empty** in `.env`.
2. A direct `psql` connection needs `EFB_SUPABASE_DB_URL`, which is **not in
   `.env`** at all, and the password is deliberately not on disk.
3. PostgREST cannot run SQL. `EFB_SUPABASE_URL` and `EFB_SUPABASE_SECRET_KEY`
   are now set, and they do reach the shared project read-only, but the REST API
   exposes tables, not `pg_database_size`.

**What the owner should run before provisioning**, in the Supabase SQL editor,
one statement:

```sql
select pg_size_pretty(pg_database_size(current_database())) as db_size,
       pg_size_pretty(sum(pg_total_relation_size(format('%I.%I', schemaname, tablename))))
         filter (where schemaname not in ('pg_catalog', 'information_schema')) as tables_size
from pg_tables;
```

Read the number against the 400 MB line, which is 80% of the 500 MB cap. EFB
projects to 261 MB after a year, so the design crosses that line only if the
credit lab's share is above about 139 MB. **This is the one pre-registered stop
I could not evaluate**, and it is a stop about deploying, not about building:
the schema file is text and applies nothing here.

**One thing the credentials did confirm, read-only.** `GET
{EFB_SUPABASE_URL}/rest/v1/` with the service key returns HTTP 200 and an
OpenAPI document titled "standard public schema" listing **9 paths, seven named
relations**: `cron_runs`, `decisions`, `live_attribution`, `order_rejections`,
`pnl_log`, `positions` and `settings`, with the remaining two being the API
root. No `efb` or `e11_` name appears, so the Exposed schemas setting has
not changed and the direct-Postgres decision holds. It also shows why every EFB
statement is schema-qualified: the credit lab has its own `cron_runs`,
`positions` and `decisions`, and EFB's live series would collide with them in
`public`.

**A warning about those two credentials.** `EFB_SUPABASE_SECRET_KEY` is the
service-role key. It bypasses row-level security across the whole shared
project, credit-trading-lab included, so it must never be set on a Render
service, which is the owner's own rule at E11-F11. The store's runtime path is
`EFB_SUPABASE_DB_URL` plus `EFB_DB_SCHEMA=efb`; the secret key stays local and
is not read by any code path in the store. The probe above is the only thing I
used it for, and it read the API's table list, not a row of the lab's data.

## Part 2: the build

`live/appendix.py` implements the design. `artifact_rows` turns each artifact
into appendix-shaped rows (one row per key with a `trade_date`, a MultiIndex
flattened, the covariance matrix unpivoted), `hydrate` writes each artifact back
as seed plus appendix, and `persist_new_sessions` upserts the post-cutoff
sessions. `register_tables` puts the nine tables and their keys into the store's
registry, so the upsert's `ON CONFLICT` covers them and a re-run leaves one row
per key.

Three things the build had to get right, all of them found by the tests rather
than by reading code:

- **The seed goes back verbatim.** The share-count artifact holds **62,022
  duplicated `(date, ticker)` pairs before the cutoff**, from distinct fetches
  with different share values, so deduplicating the seed would have dropped
  them. The seed rows are not after the cutoff and the appendix rows are after
  it, so the two sets cannot collide and no reconciliation is needed.
- **58 share rows have no date at all** (status `empty`, delisted names such as
  ABK and ANR). A date-keyed appendix cannot hold them and a `<= cutoff` seed
  filter drops them, so the seed filter is `not (date > cutoff)` and they stay
  in git where they belong.
- **`factor_returns` has no ticker and `factor_cov` has no ticker and no date**,
  so the key is per input, not assumed: `(trade_date, factor)` and `(trade_date,
  factor, with_factor)`. The covariance snapshot is stamped with the run's
  latest close.

The first run on a fresh database seeds the appendix from the deployed artifacts
before hydrating, so the committed post-cutoff rows go into Postgres instead of
being truncated by an empty appendix.

**The three requirements, each with its test:**

1. **The read equals the local artifacts.** `test_the_real_artifacts_round_trip_and_report_hashes`
   copies the real artifacts, hydrates, and compares a content hash of every
   input. All eight date-bearing inputs match, printed in the Verification
   section.
2. **The append is idempotent.**
   `test_an_append_is_idempotent` runs `persist_new_sessions` twice and asserts
   the same counts, one row per key on prices and descriptors, and the same
   written-row counts. `test_hydration_reproduces_every_input_it_seeded` runs
   the whole cycle on synthetic fixtures for all nine inputs.
3. **The proposal names the appendix it was priced from.**
   `build_proposal` takes the identity and stores it in the manifest, and
   `test_the_proposal_names_the_appendix_it_was_priced_from` asserts the
   manifest carries per-input rows, latest session and a sha256. The identity
   travels into `efb.proposals.manifest` through `store_proposal`, so a stored
   proposal can always name the appendix behind it. I took this option rather
   than one transaction for the append and the proposal, which the task allows
   as the alternative.

## What is left

Parts 3 (the staleness hard stop), 3b (the notification), 4 (the corrected
deploy steps) and 5 (the regenerated proposals and Guard 1 on the 150-name
book) are not started. Each is its own commit and Part 3 is the one the owner
called non-negotiable, so the next session should begin there.

## Verification

### Commands run and their last lines

Per-step selection while the code changed (rule 21):

```text
$ .venv/bin/python -m pytest tests/test_e11_appendix.py tests/test_e11_store.py tests/test_run_live_daily.py -q
..........................                                               [100%]
26 passed in 55.69s
```

```text
$ .venv/bin/python -m pytest tests/test_e11_appendix.py -q -s
....prices             a5fc51fa204de5044f2cf23cd970674660e77a0ea8b024cdc4aee6f6542de2dc a5fc51fa204de5044f2cf23cd970674660e77a0ea8b024cdc4aee6f6542de2dc
descriptors        229773403887fbeee580012d76a91e0b12b58ff3d479f6c9ab089459fa12b32c 229773403887fbeee580012d76a91e0b12b58ff3d479f6c9ab089459fa12b32c
factor_returns     8d98e667b3ae8ac6701068e2c038c60a18cef3b04a2c21b2d05e78fecda060ef 8d98e667b3ae8ac6701068e2c038c60a18cef3b04a2c21b2d05e78fecda060ef
specific_returns   0b61fb04c83307a308df1fb18c7aa332058ee2a6105bd10ccbf2389e663aa2a6 0b61fb04c83307a308df1fb18c7aa332058ee2a6105bd10ccbf2389e663aa2a6
specific_var       a4924ec465c04cd07ded4283d43224e7b01d09dcbecf8854b17276ca5fe4a232 a4924ec465c04cd07ded4283d43224e7b01d09dcbecf8854b17276ca5fe4a232
shares             0f382013335694222ec48cdfea61b74e74af2abffb0222ee9f03bbf358371707 0f382013335694222ec48cdfea61b74e74af2abffb0222ee9f03bbf358371707
sectors            2149e32bb0ab9b088cedea4c25c640fab7243cdd5565066f0cbbbffaef506227 2149e32bb0ab9b088cedea4c25c640fab7243cdd5565066f0cbbbffaef506227
universe           3ce92e6fbf70e09c7bdc29138d9b042bd2bf67416d2c59e32e709b189efba6a5 3ce92e6fbf70e09c7bdc29138d9b042bd2bf67416d2c59e32e709b189efba6a5
5 passed in 50.67s
```

`make lint`, exit 0:

```text
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
Success: no issues found in 33 source files
.venv/bin/black --check efb dashboard live tests
All done! ... 165 files would be left unchanged.
```

`make test`, the full suite, exit 0. The same command at `dd41d9b` was 732
passed, 1 skipped, 3 warnings in 510.38s; this part adds exactly the six tests
in `tests/test_e11_appendix.py`, and nothing else moved.

```text
$ make test > /tmp/full2.log 2>&1; echo "EXIT=$?"
$ tail -c 700 /tmp/full2.log

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
738 passed, 1 skipped, 3 warnings in 603.62s (0:10:03)
EXIT=0
```

`make verify-evidence`, exit 0:

```text
evidence OK
```

### Headline numbers, file and key

| number | file and key |
| --- | --- |
| the nine inputs and their per-session rows | `live/appendix.py::SPECS`, measured in the table above from each artifact |
| post-cutoff rows 9,086 / 38,654 / 198 / 5,467 / 5,489 / 324 / 53 / 503 / 1,006 | `live/construction_table.parquet` is not involved: measured by `appendix.artifact_rows(spec, DATA_ROOT, cutoff=SEED_CUTOFF)` |
| the round-trip hashes | printed above, and recomputed by the test |
| hydrate 2.93s, persist 0.71s / 0.58s | `/tmp/part2_timing.py`, pasted logic in the report |
| 1,550,556 rows and 256.7 MB after a year | `/tmp/part2_projection.py` |
| 62,022 duplicated share keys, 58 undated share rows | `data/raw/shares_history.parquet`, measured |
| 9 exposed REST paths, seven named relations, none named efb | `GET {EFB_SUPABASE_URL}/rest/v1/`, title "standard public schema" |

### git diff --stat from `base_commit` (dd41d9b)

This part's own files, with `git add -N live/appendix.py
tests/test_e11_appendix.py` first so the new files appear in the diff:

```text
$ git diff --stat dd41d9b -- handoff/REPORT.md live/appendix.py \
    live/evening_job.py live/supabase_schema.sql scripts/run_live_daily.py \
    tests/test_e11_appendix.py
 handoff/REPORT.md          | 614 ++++++++++++++++++++++-----------------------
 live/appendix.py           | 420 +++++++++++++++++++++++++++++++
 live/evening_job.py        |   6 +-
 live/supabase_schema.sql   |  80 ++++++
 scripts/run_live_daily.py  |  29 ++-
 tests/test_e11_appendix.py | 272 +++++++++++++++++++++
 6 files changed, 1102 insertions(+), 319 deletions(-)
```

`git diff --stat dd41d9b` over the whole tree adds three files this part did not
touch, `handoff/LOG.md` (+43), `handoff/PROJECT_CONTEXT.md` (13 changed) and
`handoff/TASK.md` (48 changed, the reviewer's `ef67024`), for 9 files changed,
1198 insertions, 327 deletions. Nothing else in the repository changed: no
research artifact, no construction table, no notebook.

### Yes or no, each with evidence

1. **Any two rows or two estimators identical.** Yes, and confined to the
   superseded prefix columns, as corrected above: the min $1,500 and min $2,000
   floor rows carry identical prefix columns because they share an ordering and
   a stopping `k` of 131, and the min $3,000 and min $5,000 rows carry identical
   prefix columns at `k` of 3. No two rows' books are identical. In this part,
   the new appendix tables have no rows in common with anything else.
2. **Any exception caught and skipped, or fallback taken, with counts.** Yes:
   the store's local parquet fallback, exercised by every new test because
   `EFB_SUPABASE_DB_URL` is unset. That is the fallback working as designed, not
   an exception swallowed, and it is why the timings above are filesystem
   timings. No connection was attempted and no error was suppressed.
3. **Any criterion reworded or replaced by a different test.** No. No
   `RESULTS.json` criterion, threshold or string was touched. The reviewer's
   ruling on the rank margin changed no stored criterion; it settled which rows
   the check gates.
4. **Any criterion that passes by construction.** The round trip's equality is
   by construction in the sense that `hydrate` writes seed plus appendix and the
   test then reads seed plus appendix, so it cannot fail for a reason other than
   the code being wrong. What makes it worth having is that it is driven on the
   real 165 MB of artifacts and hashes every input, and it did catch two real
   defects (the dropped share rows and the missing factor columns). Declared.
5. **Any number that moved by a factor of 10 or more from its previous stored
   value.** No. No stored number moved: the construction table is untouched by
   this part, and the only new data are the appendix tables and their rows.
6. **Any stored number typed into a notebook.** No. No notebook was opened,
   edited or executed. (The path `/tmp/part2_timing.py` is a scratch script, not
   a notebook, and its logic is quoted above.)
7. **Any earlier verdict changed.** No. Every verdict in `sprints/E*/RESULTS.json`
   and the registry is untouched.

### Anything decided that the reviewer might disagree with

**The first run seeds the appendix from the deployed artifacts.** With an empty
appendix, hydrating strictly (seed plus appendix) would truncate the committed
post-cutoff rows. I made `hydrate` seed the appendix from the local artifact
when it finds the appendix empty, so the first run takes those rows into
Postgres instead of dropping them, and after that the appendix is authoritative.
If the reviewer wants a strict first run with an explicit migration step
instead, it is a one-line change plus an owner step.

**The proposal records the appendix identity rather than sharing a
transaction.** The task offers both, and the transaction spans an evening's
extension and its proposal; the identity makes the same guarantee auditable from
the stored proposal alone.

**The shared database size is unmeasured.** I could not read it, three routes
were tried, and the report says so with the one statement the owner can run. I
would not deploy on that number being unknown, and the report says that too.
