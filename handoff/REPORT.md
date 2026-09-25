# Sprint E11, Part 3: staleness fails the run, counted in NYSE sessions

**What this part does.** A run whose latest close is older than the target close
now stops before any sizing. `live/staleness.py` reads the nine model inputs'
dates off the artifacts, counts the NYSE sessions between each and the most
recent completed session, writes a `run_status` row in `efb` with every date and
every failure, and `scripts/run_live_daily.py` returns nonzero without writing a
proposal row or an order. The dashboard reads the latest `run_status`, not the
latest proposal, and shows a failure state for a stale stop, an error, a run for
an older close, or no run at all.

The rule is the one pre-registered in `handoff/TASK.md` Part 3, unaltered. What
follows is where each date comes from, what the gate does on a real close, and
the decisions the spec left open.

## The nine inputs, the date the gate reads, and where it comes from

| input | gated on | allowed | the date, and its source |
| --- | --- | --- | --- |
| prices | content date | 0 sessions | latest index date in `data/raw/prices.parquet` |
| descriptors | content date | 0 sessions | latest `date` in `data/models/XS-v1/descriptors.parquet` |
| factor_returns | content date | 0 sessions | latest `date` in `data/models/XS-v1/factor_returns.parquet` |
| specific_returns | content date | 0 sessions | latest `date` in `data/models/XS-v1/specific_returns.parquet` |
| specific_var | content date | 0 sessions | latest `date` in `data/models/XS-v1/specific_var.parquet` |
| factor_cov | content date | 0 sessions | latest index date in `data/processed/returns.parquet` |
| universe | content date | 0 sessions | the date in the newest `data/raw/spy_holdings/spy_holdings_<date>.parquet` |
| shares | **fetch date**, content reported | 0 sessions | newest `fetched_at` on a `status == ok` row in `data/raw/shares_history.parquet`; content is the newest `date` on those rows |
| sectors | **fetch date**, content reported | 0 sessions | the date in the newest `data/raw/wikipedia_constituents/wikipedia_constituents_<date>.parquet`; content is `as_of` in `data/processed/sectors.parquet` |

`max_input_staleness_days` is stored on every row as well, computed the old way
(max calendar days from the target close to each content date), because the task
keeps it as a reported field. The gate itself never reads it.

## The order in the cron, and what a stop writes

`scripts/run_live_daily.py::main`, in order: hydrate the appendix, extend the
seven inputs by one session, persist the new sessions, snapshot the evidence,
**run the gate**, then propose, execute, reconcile.

The gate sits after the extension because the extension is what makes the inputs
fresh, and before any sizing because that is what the owner's rule protects. On
a stop:

- no `proposals` row and no `orders` row is written, and `build_proposal` and
  `run_morning` are never called (asserted by a test that makes both raise);
- one `run_status` row, keyed by target close and job, carries the target close,
  all nine inputs with their content dates and sessions behind, the two fetch
  dates, the failing inputs with how far behind each is, the worst input, and
  `status: stale_stopped`;
- `cron_runs` records `stale_stopped` with the one-line reason, and the process
  exits 1, so Render marks the cron run failed;
- an exception anywhere in the run (including before the gate) writes a
  `run_status` row with `status: error` and the exception's one-line reason, so
  the dashboard shows an error rather than keeping the last clean book.

## The gate on the real artifacts, run today

Pasted from `.venv/bin/python -c "from live import staleness; ..."`, the real
`data/` tree, the real clock (2026-09-25 05:32 UTC, before Friday's open, so the
target close is Thursday 2026-09-24):

```text
target_close now: 2026-09-24 00:00:00
status: stale_stopped target: 2026-09-24 max days: 13
worst: prices 3
failures: prices is 3 sessions behind; descriptors is 3 sessions behind;
factor_returns is 3 sessions behind; specific_returns is 3 sessions behind;
factor_cov is 3 sessions behind; specific_var is 3 sessions behind; universe is
3 sessions behind; shares is 2 sessions behind; sectors is 2 sessions behind

  prices            gated_by=content content=2026-09-21 behind=3
  descriptors       gated_by=content content=2026-09-21 behind=3
  factor_returns    gated_by=content content=2026-09-21 behind=3
  specific_returns  gated_by=content content=2026-09-21 behind=3
  factor_cov        gated_by=content content=2026-09-21 behind=3
  specific_var      gated_by=content content=2026-09-21 behind=3
  universe          gated_by=content content=2026-09-21 behind=3
  shares            gated_by=fetch   content=2026-09-22 behind=2 fetch=2026-09-22 fbehind=2
  sectors           gated_by=fetch   content=2026-09-11 behind=9 fetch=2026-09-22 fbehind=2
```

That is the intended answer, not a defect: the committed artifacts stop on the
2026-09-21 close and the last share fetch and archive are from 2026-09-22, so a
run on the 2026-09-24 close is stale and must not trade. The same command also
shows the two inputs whose content is meant to age: the sectors snapshot is
2026-09-11, nine sessions back, and it is reported in the row without gating
anything, because the daily constituents archive that feeds it is two sessions
back and that is what the gate reads.

The session arithmetic, from the same module:

```text
sessions behind 2026-09-04 -> 2026-09-08 (Labor Day 2026-09-07 closed): 1
sessions behind 2026-09-18 -> 2026-09-21 (Friday close, read Monday):   1
```

Four calendar days and three calendar days respectively, one session each. The
first zero for a calendar-day rule would have been a wrong gate on both.

The same result written to a store and read back, which is what the dashboard
does with it (17 columns, and the sentence the owner would see):

```text
stored row columns: ['checked_at', 'detail', 'dry_run', 'failures',
'gross_notional', 'inputs', 'job', 'max_input_staleness_days', 'n_inputs',
'n_orders', 'notify_failed', 'notify_status', 'run_date', 'status',
'target_close', 'worst_input', 'worst_sessions_behind']
status: stale_stopped target: 2026-09-24 worst: prices 3
n_inputs: 9 max days: 13
clean: False | label: STALE STOP: the run refused to price a book
message: The run for the 2026-09-24 close refused to price a book: prices is 3
sessions behind; descriptors is 3 sessions behind; ... sectors is 2 sessions
behind. No book exists for 2026-09-24, so anything shown below it is older and
not current.
inputs keys: ['descriptors', 'factor_cov', 'factor_returns', 'prices', 'sectors',
'shares', 'specific_returns', 'specific_var', 'universe']
```

## The dashboard

`live/dashboard_app.py` now leads with the run state, read from the latest
`run_status` row and judged against the session that should have completed:

| state | when | what the page shows |
| --- | --- | --- |
| `clean` | the latest row's target close is the most recent completed session and its status is `ok` | a green "Run status: clean" line |
| `stale_stopped` | same target close, status `stale_stopped` | a red banner naming every failing input and its distance, and saying any book below is older and not current |
| `error` | same target close, status `error` | a red banner with the one-line reason |
| `notify_failed` | clean run, notification could not be sent | a red banner (Part 3b writes that column) |
| `no_run` / `no_run_for_session` | no row at all, or only rows for an older close | a red banner naming the session that has no run |

The book section keeps its caption honest: when the state is not clean it says
the book below is the last one stored, for which close, and that it is history
rather than today's book. A test renders the real page with `input_dates` and
`check` replaced by functions that raise, so "the page reads no research
artifact" is proved at test time rather than by reading the source.

## Decisions the spec left open, and why

**The sectors fetch date is the constituents archive, not the sectors file.**
`data/processed/sectors.parquet` is written only by `efb/build.py` from the
Wikipedia constituents snapshot; the daily loop reads it and never rebuilds it,
so its `as_of` is 2026-09-11 and will keep ageing. The fetch that the loop
actually performs every evening is `universe.archive_constituents`, called from
`extend.extend_archives`, which writes one dated file per fetch and is the
sector source by its own docstring. Gating on that date measures the check, which
is what the task asks ("what must not age is the check"), and the sectors content
date is reported beside it. Gating on the content date instead would stop every
run forever, which cannot be the intent of an allowed value of 0 sessions. If the
reviewer wants the sector snapshot itself refreshed nightly, that is new work and
a different part.

**The factor covariance date is the returns session.** The artifact is a matrix
with no date of its own; `extend_model` rolls it forward and
`appendix._factor_cov_with_session` stamps it with the latest returns session, so
that session is the date its content carries. A failed returns extension
therefore fails both inputs, which is correct: the matrix would then describe an
older covariance than the one the model is fitted on.

**A missing date is stale, not fresh.** An input with no date at all (the file is
missing, or the date column is empty) reports `sessions_behind: None` and stops
the run, and it outranks any count when the worst input is named, because "how
far behind" is unbounded rather than small. The 58 share rows whose fetch came
back empty carry no date and are excluded from the fetch date for that reason:
the date comes from `status == ok` rows only.

**The gate runs after the extension, not before it.** The task says "before any
sizing"; sizing means the construction and the morning execution. Running it
before the extension would measure the state of the container rather than the
state of the data the book is priced from.

**The target close is the last session whose close has passed.** The cron fires
at 22:30 UTC, after the 20:00 UTC close, so on a session day the target is that
day; a run before the open prices yesterday's close. Both directions are pinned
by tests, and the boundary is the close timestamp from the NYSE calendar, not a
fixed hour.

## Tests, 13 in `tests/test_e11_staleness.py`

The gate itself is measured on synthetic artifacts under a temporary root; the
run-level tests drive `scripts/run_live_daily.main()` with every fetching step
replaced and the sizing steps made to raise, so the promise is asserted on the
store.

1. a Monday run before the open on Friday's close passes, and the same artifacts
   read after Monday's close are one session stale (the negative control);
2. Labor Day is not a session, a run on the holiday evening passes on Friday's
   close, and the same artifacts after Tuesday's close are one behind, not four;
3. the target close is the last session that has closed, before the open and at
   the cron's slot;
4. the stored row carries a content date for all nine inputs, both dates for
   shares and sectors, the reported calendar-day number, and no failure while
   the sectors content age of 11 calendar days sits in the row;
5. an old *fetch* fails while the content date is fresh, which is the check the
   task says must not age;
6. an input with no date is stale, is named as the worst, and does not lose to a
   count;
7. a stale input stops the run: exit 1, no `proposals` row, no `orders` row,
   `build_proposal` and `run_morning` never called, the row naming prices and
   one session, and the stored row rendering the same sentence the owner sees;
8. the negative control for 7: a fresh gate reaches sizing, and the later
   failure replaces the clean row with an `error` row;
9 to 13. the dashboard: a stale stop shows the red banner with the failing input;
   a missing run shows the no-run banner; a row for an older close shows the
   no-run-for-session banner naming the session; a clean row shows no failure at
   all; and the page renders with `input_dates` and `check` wired to raise.

## What could not be verified

**The Postgres path, and one concrete risk in it.** No `EFB_SUPABASE_DB_URL`
exists in `.env` or anywhere on this machine, no Postgres server is installed,
and docker is not available, so every new test exercises the store's local
parquet fallback. `run_status` is therefore proved in shape and in content, not
over a socket. That is the same standing gap as the rest of the live series, and
Part 4's connection-string test is where it gets closed.

While checking what the write path sends, one thing did surface.
`psycopg.types.string.StrDumper.oid` is 25, so psycopg 3.3.6 sends a Python
`str` as `text`, and `store.upsert` passes dates, `jsonb` payloads and timestamps
as strings. If Postgres refuses the assignment, the first write fails with
`column "target_close" is of type date but expression is of type text` rather
than silently, and the fix is a cast per column in `store._upsert_sql`. I could
not settle it without a server. It is not specific to this part: `proposals`
(`trade_date`, `input_as_of jsonb`, `manifest jsonb`) and `cron_runs`
(`run_date`, `started_at`) already carry the same shape, so the first live write
of any table answers it, and Part 4's steps will make the owner's connection test
do exactly that.

Nothing else is unverified. The NYSE calendar is a new live dependency
(`pandas_market_calendars>=4.4`, added to `requirements.txt` and to the `live`
extra in `pyproject.toml`), installed here as 5.4.0, and its holiday and session
arithmetic is pinned by tests 1 and 2.

## What is left

- Part 3b: the notification on every run, Slack first, the webhook in
  `EFB_NOTIFY_SLACK_WEBHOOK_URL` on the cron only, the scrub of the error
  reason, `notify_failed` recorded, and the one external heartbeat option
  offered rather than built. The `run_status` table already carries
  `notify_status`, `notify_failed`, `n_orders` and `gross_notional` for it, so
  3b needs no schema change.
- Part 4: the deploy steps, corrected, with the role SQL as text, the session
  pooler username format, the answer on runtime DDL, and the owner's test
  notification.
- Part 5: only after the owner confirms the book.

## Verification

`make lint`, exit 0:

```text
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
Success: no issues found in 33 source files
.venv/bin/black --check efb dashboard live tests
All done! ... 167 files would be left unchanged.
```

`make test`, the full suite, exit 0. The same command at `dee01c8` (Part 2) was
738 passed, 1 skipped, 3 warnings; this part adds 13 tests, all in
`tests/test_e11_staleness.py`, and nothing else moved.

```text
$ make test > /tmp/full3.log 2>&1; echo "EXIT=$?"
$ tail -c 300 /tmp/full3.log

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
751 passed, 1 skipped, 3 warnings in 584.10s (0:09:44)
EXIT=0
```

### The per-step runs, and the fast/slow split

Per step, the selection and its output, pasted so the subset is auditable
(rule 21):

```text
$ .venv/bin/python -m pytest tests/test_e11_staleness.py tests/test_e11_render.py -q --tb=short
..............s.............                                             [100%]
27 passed, 1 skipped in 2.30s
```

That selection is every test touching what changed: the new file, and
`tests/test_e11_render.py`, which reads `live/dashboard_app.py` as text and
imports it. `tests/test_run_live_daily.py` also covers the cron script and was
run in the same batch while the part was built (26 passed over the three files);
its tests are unchanged and pass in the full run.

The split, rule 21:

```text
$ .venv/bin/python -m pytest tests/ -q -m slow --collect-only
29/752 tests collected (723 deselected) in 2.09s

$ make test-fast
722 passed, 1 skipped, 29 deselected, 3 warnings in 25.56s
make test-fast  25.26s user 2.70s system 106% cpu 26.297 total
```

752 tests collected: 29 on the slow path, 723 on the fast one, and one of them
skipped. The fast path is 25.6s, the full path 584.1s. Every test this part adds
is on the fast path: the file of 13 runs in 2.37s and no single test is near the
two-second marker, so none is marked slow.

`make verify-evidence`, exit 0:

```text
evidence OK
```

### Headline numbers, file and key

| number | file and key |
| --- | --- |
| nine inputs, their gating date and its source | `live/staleness.py::INPUTS`, `GATED_ON_FETCH`, `input_dates` |
| 0 sessions allowed, `ALLOWED_SESSIONS_BEHIND` | `live/staleness.py::check`, `allowed_sessions_behind: 0` in every stored row |
| target close 2026-09-24, max 13 calendar days, worst prices at 3 sessions | the pasted run above, `check()` on the real `data/` |
| Labor Day 2026-09-07 closed; 09-04 to 09-08 is 1 session | `live/staleness.py::sessions`, `sessions_behind` |
| 13 tests | `tests/test_e11_staleness.py`, `pytest -q` |
| 751 collected: 722 fast / 29 slow, 25.6s / 584.1s | `make test-fast` and `make test`, both pasted above |
| the run stops with no proposal and no order | `tests/test_e11_staleness.py::test_a_stale_input_stops_the_run_with_no_proposal_and_no_orders`, asserting on `store.select("proposals")` and `store.select("orders")` |
| `run_status` DDL, 17 columns, key (target_close, job) | `live/supabase_schema.sql`, tail |
| the store's `run_status` key | `live/store.py::TABLE_KEYS` |
| `StrDumper.oid` 25 | psycopg 3.3.6, read directly |

### git diff --stat from `base_commit` (dd41d9b)

This part's own files, from Part 2's commit `dee01c8` (Part 2 is committed, so
the part boundary is that commit rather than the revision's base), with
`git add -N live/staleness.py tests/test_e11_staleness.py` first so the new files
appear:

```text
$ git diff --stat dee01c8 -- handoff/REPORT.md live/staleness.py \
    live/dashboard_app.py live/store.py live/supabase_schema.sql \
    scripts/run_live_daily.py tests/test_e11_staleness.py requirements.txt \
    pyproject.toml
 handoff/REPORT.md           | 677 +++++++++++++++++++++++---------------------
 live/dashboard_app.py       |  35 +++
 live/staleness.py           | 542 +++++++++++++++++++++++++++++++++++++
 live/store.py               |   4 +
 live/supabase_schema.sql    |  29 ++
 pyproject.toml              |   1 +
 requirements.txt            |   2 +
 scripts/run_live_daily.py   |  48 +++-
 tests/test_e11_staleness.py | 422 +++++++++++++++++++++++++++++
 9 files changed, 1451 insertions(+), 309 deletions(-)
```

From the revision's `base_commit` (dd41d9b), which also carries Part 2 and the
reviewer's `ef67024`:

```text
$ git diff --stat dd41d9b
 handoff/LOG.md              |  43 +++
 handoff/PROJECT_CONTEXT.md  |  13 +-
 handoff/REPORT.md           | 697 +++++++++++++++++++++++---------------------
 handoff/TASK.md             |  48 +++-
 live/appendix.py            | 420 ++++++++++++++++++++++++++++++++
 live/dashboard_app.py       |  35 +++
 live/evening_job.py         |   6 +-
 live/staleness.py           | 542 +++++++++++++++++++++++++++++++++++++
 live/store.py               |   4 +
 live/supabase_schema.sql    | 109 ++++++++
 pyproject.toml              |   1 +
 requirements.txt            |   2 +
 scripts/run_live_daily.py   |  63 ++++-
 tests/test_e11_appendix.py  | 272 +++++++++++++++++++++
 tests/test_e11_staleness.py | 422 +++++++++++++++++++++++++++++
 15 files changed, 2345 insertions(+), 332 deletions(-)
```

Nothing else in the repository changed: no research artifact, no construction
table, no proposal, no notebook.

### Yes or no, each with evidence

1. **Any two rows or two estimators identical.** No. Each `run_status` row is one
   target close, and the tests write one row per case. No proposal, position or
   order row exists in the tree at all after this part: the stop path writes
   none, and no test writes one.
2. **Any exception caught and skipped, or fallback taken, with counts.** Yes, two,
   both by design and neither silent. (a) The store's local parquet fallback,
   exercised by every new test because `EFB_SUPABASE_DB_URL` is unset; the
   Postgres path is unreachable here and the section above says so. (b) The cron's
   own `except Exception`, which records `cron_runs status=failed`, writes the
   `run_status` error row, logs the traceback and returns 1; the write of the
   error row is itself guarded so that a store failure cannot mask the original
   failure. No other exception is caught anywhere in the new code; the network,
   the calendar and the artifacts are allowed to raise.
3. **Any criterion reworded or replaced by a different test.** No. No
   `RESULTS.json` criterion, threshold or string was touched, and no existing
   test was edited: the diff shows one new test file and one new module.
4. **Any criterion that passes by construction.** Two, declared. (a) The
   dashboard tests assert on the element the page renders, so if the banner and
   the test drifted apart the test would still catch it, but they do share the
   `run_state` function, so the message wording is not independently checked.
   (b) Test 8 (a fresh gate reaches sizing) proves the gate passed by observing
   that sizing was entered, which is the point; it does not prove what the
   proposal would have contained, because the sizing call is replaced.
5. **Any number that moved by a factor of 10 or more from its previous stored
   value.** No. No stored number moved. The construction table, the proposals,
   the registry and every `RESULTS.json` are untouched; the gate is new and
   reports new numbers.
6. **Any stored number typed into a notebook.** No notebook was opened, edited or
   executed. The one scratch script used is `/tmp/...` and its output is pasted
   above.
7. **Any earlier verdict changed.** No. The rank-margin ruling stands as recorded
   at `ce8c897`, and this part touches no check on any floor row.

### Anything decided that the reviewer might disagree with

**The sectors gate reads the constituents archive, not the sector snapshot.** The
reasoning and the alternative are above. If the reviewer reads "the date of the
last successful fetch" as the sector file's own date, the honest consequence is
that a run today stops on sectors at nine sessions behind and keeps stopping
until the build refreshes the snapshot, so the live loop could not run at all.
I took the reading that keeps the owner's rule meaningful, and I am flagging it
rather than burying it.

**The dashboard shows the no-run state between the close and the cron.** A run
that fires at 22:30 UTC after a 20:00 UTC close leaves roughly two and a half
hours in which the most recent completed session has no `run_status` row, so the
page shows the missing-run banner in that window. The task says a missing run is
stale and the failure state must be prominent, so I implemented that literally
rather than adding a grace period that would blunt the alarm; the banner names
both dates so the owner can see the cron is merely not due yet. If the reviewer
prefers a grace window to the close plus a few hours, it is a small change to
`run_state`.
