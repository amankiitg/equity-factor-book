# Sprint E11 pre-deploy, item 4b: the store never falls back silently in production (E11-F17)

**What was wrong.** `live/store.py` fell back to parquet under `live/state/`
whenever `EFB_SUPABASE_DB_URL` was unset, and it did so without saying anything.
On Render a missing or mistyped variable would therefore have written the
evening's rows to a disk the next container never sees: the run would still
notify `ok`, the appendix would re-seed from git every night, and the dashboard
would read its own empty fallback. Every part of that is healthy from the
outside, which is why the owner named it.

**The rule now.**

| situation | what happens |
| --- | --- |
| `EFB_STORE=local`, no `RENDER` | the local parquet fallback, deliberately |
| no `EFB_STORE` and no `EFB_SUPABASE_DB_URL` | `StoreNotConfigured`, naming what to set. Reads and writes both refuse, so the run cannot half-work |
| `EFB_STORE=local` with `RENDER` set | refused, with the reason (a local write on Render lands on a disk the next container never sees) |
| both a URL and `EFB_STORE=local` | refused as a contradiction, because the write would otherwise go to whichever was checked first |
| `EFB_STORE` set to anything else | refused as an unknown mode, so a typo cannot silently mean local |
| a URL alone | Postgres/`efb` |

`store.store_mode()` is the one decision, `store.get_connection()` calls it, and
`upsert` and `select` go through it, so no caller can reach the fallback by
accident. `scripts/run_live_daily.py` decides the mode before it reads or writes
anything, at the top of the run, so a misconfiguration is an `error` run with a
notification rather than a book priced into the void. Because a store failure
means there is nowhere to record the failure, `finish_run` now guards its two
store writes, logs what happened, and returns nonzero anyway: the message the
owner already has is the report.

**The first line of the message names the store.** `live/notify.py` leads with
`store: postgres/efb`, or `store: local parquet (live/state/supabase)`, or
`store: ERROR <reason>` when the configuration is unusable, which puts the one
healthy-looking failure in front of the owner before the status is even read.

**A defect found while building the verification, and fixed.** `json.dumps`
writes a bare `NaN`, which is not valid JSON and which Postgres `jsonb` refuses
outright. Every `run_status` json column went through `json.dumps`, so one NaN
anywhere in a run's inputs would have failed the whole row, on the one table the
dashboard reads. Today no NaN reaches those columns (`flag_large_moves` drops
them, the hashes and sessions are strings), so this was an unexercised risk
rather than a live failure. `store.json_text` and `store.json_safe` now convert
NaN and infinity to `null`, recursively, and every json column in
`live/staleness.py` goes through them. The verification below carries the
negative control, so the fix is proven to be doing something.

**The round-trip verification command, `scripts/verify_store_roundtrip.py`.** The
task requires the command now, in this commit, and it is built: it reads every
appendix input back from the real `efb` schema and compares it with the local
artifact at the same commit over the sessions both hold, checking the values
column by column and recording a hash for each input plus the sessions the
appendix holds beyond the artifact. It then checks type fidelity explicitly, in
one `SELECT` that writes nothing: a NaN float, a JSON `null` where a NaN used to
be, a date, a timestamp with a time zone and a 1e-17 float. It records the whole
result in `efb.run_status` under `job = store_roundtrip` with the hashes. It
refuses to run in local mode, because reading the real schema is the entire
point, and its refusals are tested.

**It has not run.** There is no Postgres server in this environment, no docker
and no `EFB_SUPABASE_DB_URL`, which is the same wall the earlier parts hit. What
is built and verified here is the command, its refusals, its comparison basis and
the sanitizer it depends on. The owner runs it after the first deploy, before
either gate evening counts.

**Where every earlier Postgres claim actually ran.** Part 2's round-trip hashes,
Part 3's gate and run-status rows, Part 4's typing proof and every store test in
Part 5 ran against the local parquet fallback under `live/state/`, as those
reports said at the time. Part 4's typing probe was never executed against a
server either; it was printed as text for the owner to run. So no SQL path had
been exercised at all before this item, and none has been exercised by this item
either: what is new is that the failure is now impossible to reach quietly, and
that the command which proves the path exists. `tests/conftest.py` pins the suite
to `EFB_STORE=local` and removes any connection string from the environment,
because a test run must never write a row to the project shared with
credit-trading-lab.

## Tests

`tests/test_e11_store.py`, six new tests: the local fallback needs an explicit
request (and both a read and a write refuse without one), local mode is refused
where `RENDER` is set and the label says `ERROR`, a URL and a local request
together are refused while either alone is fine, an unknown mode is refused, the
label names the store or the error, and `json_text` has no NaN while values,
dates and strings that look like numbers survive. The round-trip command's two
refusals and its comparison basis are tested as well, including that a real value
difference is caught rather than normalised away.

`tests/test_e11_notify.py`'s five first-line assertions moved from `[0]` to `[1]`
and the first test now asserts the store line leads, because that is the change.

## Verification

This item changes the write path for every consumer, so the per-step selection is
wide, and standard 21's full-suite triggers do not apply to it: no `efb/` module
changed and no stored artifact was rebuilt. The full suite is running as this is
written and its result is reported in the next item's Verification; if it fails,
that is a blocker and it is fixed before anything else moves. The previous full
run, at item 3, was 786 passed, 1 skipped, 3 warnings in 599.86s, exit 0.

Per step, the selection is every test touching the store, the notification, the
staleness row and the runner:

```text
$ .venv/bin/python -m pytest tests/test_e11_store.py tests/test_e11_notify.py \
    tests/test_e11_render.py tests/test_run_live_daily.py -q
56 passed, 1 skipped in 51.21s
```

`make lint`, exit 0:

```text
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
Success: no issues found in 33 source files
.venv/bin/black --check efb dashboard live tests
All done! ... 174 files would be left unchanged.
```

`make verify-evidence`, exit 0:

```text
evidence OK
```

The verification command's refusal, run here, exit 2:

```text
$ .venv/bin/python scripts/verify_store_roundtrip.py; echo "EXIT=$?"
ERROR EFB_SUPABASE_DB_URL is not set, so the live series has nowhere to go; set it,
or set EFB_STORE=local for a local run
This command reads the real `efb` schema by design, so it refuses to run against
the local fallback.
EXIT=2
```

### Headline numbers, file and key

| number | file and key |
| --- | --- |
| the one mode decision | `live/store.py::store_mode`, with `LOCAL_MODE_ENV`, `LOCAL_MODE_VALUE`, `RENDER_ENV`, `URL_ENV` |
| the error type | `live/store.py::StoreNotConfigured` |
| the store's name in a message | `live/store.py::store_label`; used by `live/notify.py::compose`, first line |
| the jsonb sanitizer | `live/store.py::json_safe`, `json_text`; five columns in `live/staleness.py::run_status_row` |
| the mode checked before any read or write | `scripts/run_live_daily.py`, top of `main`'s try |
| the guarded record | `scripts/run_live_daily.py::finish_run`, `store_failed` |
| the suite is pinned to local | `tests/conftest.py` |
| the verification command | `scripts/verify_store_roundtrip.py`, `job = store_roundtrip` in `efb.run_status` |
| 6 new tests | `tests/test_e11_store.py` |

### git diff --stat from `base_commit` (4048b97)

This item's own files, from item 4a's commit `9bd1caf`:

```text
$ git diff --stat 9bd1caf -- live/store.py live/notify.py live/staleness.py \
    scripts/run_live_daily.py scripts/verify_store_roundtrip.py tests/conftest.py \
    tests/test_e11_store.py tests/test_e11_notify.py
 8 files changed, 675 insertions(+), 41 deletions(-)
live/notify.py                    |  17 +-
 live/staleness.py                 |  10 +-
 live/store.py                     | 147 ++++++++++++++++--
 scripts/run_live_daily.py         |  60 +++++--
 scripts/verify_store_roundtrip.py | 318 ++++++++++++++++++++++++++++++++++++++
 tests/conftest.py                 |  14 ++
 tests/test_e11_notify.py          |  11 +-
 tests/test_e11_store.py           | 139 +++++++++++++++++
 8 files changed, 675 insertions(+), 41 deletions(-)
```

From the task's `base_commit` (4048b97), which carries items 1, 2, 3, 4 and 4a:

```text
$ git diff --stat 4048b97
PLACEHOLDER_DIFF_TREE
```

### Yes or no, each with evidence

1. **Any two rows or two estimators identical.** Not applicable: no estimator is
   touched, and the only numbers are the probe's.
2. **Any exception caught and skipped, or fallback taken, with counts.** One, and
   it is the item's subject in reverse: `finish_run` catches a store failure so
   that the notification, which has already gone out, is not lost to a traceback.
   It does not swallow it: the failure is logged, the exit code is 1 whatever the
   run's status was, and the message's first line already said `store: ERROR`.
   Nothing else is caught. The fallback is no longer taken at all without a
   request.
3. **Any criterion reworded or replaced by a different test.** No `RESULTS.json`
   criterion. Five notify assertions moved from the first line to the second
   because the first line changed, which is the item's own subject, and
   `tests/test_e11_render.py`'s `is_supabase()` expectation still holds because
   that function answers `False` rather than raising when the store is unusable.
4. **Any criterion that passes by construction.** One, declared: the round-trip
   command's tests cover its refusals and its comparison basis, not a real round
   trip, because there is no server here. That is the gap the command exists to
   close, and it is stated rather than implied.
5. **Any number that moved by a factor of 10 or more from its previous stored
   value.** No stored number moved: no artifact was written, and the store writes
   nothing in this item.
6. **Any stored number typed into a notebook.** No notebook was opened, edited or
   executed.
7. **Any earlier verdict changed.** No. Every earlier part's evidence stands, and
   this item says plainly where each of them ran, which is the same statement
   those reports made.

### Anything decided that the reviewer might disagree with

**A URL plus `EFB_STORE=local` is an error rather than a preference.** The
alternative is to let one win; either choice writes somewhere the operator may
not have meant, and this file's whole subject is a write that went somewhere
unintended. If the reviewer would rather the explicit flag win, it is one branch.

**`is_supabase()` answers `False` instead of raising when the store is unusable.**
It is a question about the configuration, not an operation, and the parts that
print or decide remain readable while the run's own first action,
`store.store_mode()`, is the thing that stops it.

**The verification writes one `run_status` row.** The task asks for the result to
be stored with the hashes, so the command writes that row and nothing else; the
type probe is a `SELECT`, so the shared project receives no probe writes at all.

# Sprint E11 pre-deploy, item 4: the corporate-actions rule in the append path

**What was wrong.** The vendor back-adjusts history on a split. This pipeline only
appends and no stored row may be restated. So on the evening a split first appears,
the appended session's raw close is on the new basis while the session it is
compared against is stored on the old one, and the raw return reads -50%. E1's
outlier flag is 50%, so that number sits right under the flag that is supposed to
catch it: a 2:1 split would have entered the book as a -50% name and no test would
have failed. Item 4 is the rule that stops it, and the measurement that says where
it fires.

**Item 4a, measured, not asserted.** The APH split on 2026-09-03 is the case in
hand, and the first thing the measurement showed is that it did **not** produce a
fake return: the delivered close halves (158.5500 on 2026-08-31 to 82.779999 on
2026-09-04), and the panel's APH return on 2026-09-04 is **NaN, not -48%**,
because APH has no close at all on 2026-08-28, 09-01, 09-02 and 09-03, and
`returns.compute_returns` uses `pct_change(fill_method=None)`, so a NaN run makes
the session NaN. The appendix therefore carried a hole, not a fake return. The rule
is what stops the *next* split from being a fake return, and it also records this
one, which nothing had.

Run against the real artifacts, read only, with the extension's own boundary
(`since` = 2026-08-31) and the vendor's own action rows:

```text
appended sessions: 2026-09-01 ... 2026-09-21
  2026-09-03 flagged: ['APH']
  ... every other session flagged: []
splits: ['split: APH 2:1 applied']
ratios: {'SBNY': 1.0, 'DELL': 1.0, 'FMC': 1.0, 'APH': 0.499226, 'CIEN': 1.0, ... 28 more at 1.0}
cross-checked: 33 tickers
flags: []
rows to store: [{'trade_date': '2026-09-21', 'ticker': 'APH', 'effective_date':
  '2026-09-03', 'factor': 2.0, 'source': 'yfinance.splits',
  'cross_check_ratio': 0.4992257042886195}]
artifact hash unchanged: True
any row moved: False
APH r on 2026-09-04 still: nan
```

Three things there are worth reading twice. **The negative control**: 32 of the 33
cross-checked tickers came back at exactly 1.000000, so the one that did not is the
only ticker the vendor's own action column flagged. **Nothing moved**: the artifact
hash is unchanged, no row differs, and APH's return on 2026-09-04 is still NaN,
because the numerator is the post-split close and the last close with a value is
pre-split, so any number there would be a two-week return wearing a one-session
label. **The ratio is 0.499226, not 0.5**: the vendor's adjusted close carries
dividends as well as splits, and APH is one quarterly dividend away from the factor.

**The other numbers item 4a asks for.** APH's `specific_return` panel has **no row
for the ticker after the gap**: its last row is 2026-08-27 at -0.034983, and
nothing on 2026-09-04 or any session through 2026-09-09, because the factor
regression behind it needs the return history the four missing closes removed. So
the split did not enter the specific-return panel as a value; it entered it as an
absence. `specific_var` is unchanged either side of the gap and carries no
information about the split: 0.000600 on 2026-08-31, 09-03 and 09-04 with
`specific_var_raw` 0.0006 and bucket "Information Technology|NA" (the
no-bucket-yet fallback, whose `bucket_mean` equals it exactly), then 0.000600 on
09-08 with the bucket resolved to "Information Technology|3". The split moved
neither the raw variance nor the shrunk one.

Across every appended session to 2026-09-21, the number of names with an absolute
daily return above 40% is **zero**, so there is nothing to explain and no repair to
make. The conditional branch item 4a reserves for a repaired appendix is therefore
not taken: the appendix carried a hole, not a fake return, and a hole is left as a
hole. Pre-2026-09-04 rows are byte-identical, verified by the artifact hash in the
pasted block above.

**Where it did and did not fire.** It fires on the split the vendor reports, on the
session that split takes effect on. It did not fire anywhere in the appended
returns, because the only affected session had no close to correct. It fired on the
cross-check for APH and for the 32 large-move tickers around it, all of which
agreed with their stored values. It did not fire on any flag: no appended return
above 40% was left unexplained.

**The failing source, recorded.** APH has no close on four sessions, one of them the
session the vendor's own split record is dated on, and that is now a ledger entry
rather than a silent gap (`docs/hygiene_ledger.md`, "yfinance is a recorded failing
source for APH's four missing closes"). Two more entries land with it: the append
seam rule, and the decision that an unexplained large move is reported rather than
blocked. The ledger is append-only, so the 2026-09-04 entry that says "never reapply
split factors" is untouched; the new entry says why that one holds for a history
fetched in one go and what changes at the seam.

**Item 4b, the rule.** `live/corporate_actions.py`:

| piece | what it does |
| --- | --- |
| `split_factor_of` | one place decides what the vendor's column means: `0.0` and `NaN` are no split, `1.0` is no split, a negative or non-finite value is no split, everything else is new shares per old share |
| `split_flag_tickers` | the vendor's own `split_factor` column, already stored on the price row, names the tickers that split. The primary detection costs no request |
| `cross_check_ratio`, `resolve_split` | the refetched adjusted close of the last stored session against the stored one. A ratio away from 1 that no record explains, or a record that disagrees with the vendor's own factor, raises naming the ticker and stops the run |
| `adjusted_return` | `close_t * factor / close_{t-1} - 1`, from raw closes, never from the back-adjusted history |
| `apply_to_append`, `apply_to_artifact` | two passes per appended session: the flagged tickers, then every ticker whose appended move exceeds 10%, capped at 30 requests. The artifact is written back only when a split was actually applied |
| `shares_basis_factor`, `held_notional_across_split`, `held_shares_across_split`, `trade_across_split` | a lagging share count is corrected by date, never by guessing a plausible number; a held position keeps its notional so an unchanged target trades nothing |
| `flag_large_moves`, `rows`, `describe` | the >40% flags, the stored row, and `split: APH 2:1 applied` |

`CROSS_CHECK_TOLERANCE = 0.02` is a measured number, not a taste: the vendor's
adjusted close carries dividends, so APH's factor-matched ratio is 0.499226; two
real split factors are never within 2% of each other (3:2 against 2:1 is 25%
apart), so the band separates a dividend from a factor.

Wired into the run: `scripts/run_live_daily.py` applies it straight after
`extend.extend_returns()` and before anything reads the returns, writes the event
to `efb.e11_corporate_actions`, carries it on the run's `run_status` row
(`splits`, `flags`) and names it in the evening message (`Corporate actions: split:
APH 2:1 applied.`, and `Large moves: ...` when a move is unexplained).
`live/notify.py`, `live/staleness.py` and `live/supabase_schema.sql` carry those
fields.

**Every consumer of a price level, and which side of the seam it is on.**

| consumer | reads | needs a factor |
| --- | --- | --- |
| `efb/build.py` returns, `efb/hygiene.py`, `efb/identity.py`, `efb/evaluate.py`, `efb/hedge.py` | two prices inside one basis | no: returns are computed within a basis |
| `efb/costs.py::_corwin_schultz`, `abdi_ranaldo` | a session's own high, low and close | no: the window is per session and the ratios are within one basis |
| `efb/build.py::market_cap` (`close * shares`), `data/processed/market_cap.parquet` | a level times a count | the two factors cancel, but only when both come from the same date's snapshot, which is how `build.py` reads them |
| `live/morning_job.py::_close_prices`, `live/sizing.py` whole-share quantization | the close of the session being traded | no: same session as the order |
| `live/alpaca.py::submit_market_orders` | the price at execution, revalidated | no: same session |
| `live/evening_job.py::usable_prices`, `live/construction_table.py`, the pages | levels at the proposal close | no: same session |
| `live/staleness.py` | dates, not levels | no |

The one place where both bases meet is market cap, and it is why the rule keeps the
factor on the appended session: a stale close against a restated count would move
the size factor by a factor of two.

## Tests

`tests/test_e11_corporate_actions.py`, 20 tests: a synthetic 2:1 and a synthetic
3:2 giving the right return with the caller's frame and the stored artifact both
unchanged (hash before and after), a back-adjustment with no split record stopping
the run, a vendor-flagged split with no record stopping it, a disagreed factor
stopping it, a ratio of 1 and a dividend-sized drift of 0.985 needing no split, the
ratio agreeing with a factor either way round, a lagging share count corrected and a
current one left alone, a held position reconciling with no phantom trade, the
cumulative factor for a level read across two splits, the record and the message,
the flag list, the APH case from the real rows and the real ratio, the artifact
writer with and without a split, and the notification and `run_status` carrying
both.

## Verification

Per step, the selection is every test touching what changed: the new rule, the
runner, the notification, the staleness row and the store.

```text
$ .venv/bin/python -m pytest tests/test_e11_corporate_actions.py tests/test_run_live_daily.py \
    tests/test_e11_notify.py tests/test_e11_staleness.py tests/test_e11_store.py \
    tests/test_e11_extend.py tests/test_e11_deploy.py tests/test_e11_render.py \
    tests/test_e11_sanity.py -q
99 passed, 1 skipped in 51.70s
```

No artifact was rebuilt in this item and no `efb/` module changed, so the full suite
is not required before this commit; it runs before the task's `done`, per standard
21. The count does not shrink: this item adds 20 tests to the 787 collected at item
3, so the next full run collects 807.

`make lint`, exit 0:

```text
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
Success: no issues found in 33 source files
.venv/bin/black --check efb dashboard live tests
All done! ... 174 files would be left unchanged.
```

`make verify-evidence`, exit 0:

```text
evidence OK
```

Two mypy notes, declared. `mypy live scripts` reports 10 errors, and it reported
10 errors on the parent commit as well, checked by stashing this item's changes:
none of them is this item's. `make lint`'s target is `mypy efb`, which is clean.

### Headline numbers, file and key

| number | file and key |
| --- | --- |
| the vendor's split factor | `data/raw/prices.parquet`, row (2026-09-03, APH), column `split_factor` = 2.0 |
| the delivered halving | the same artifact, `close` = 158.550003 at 2026-08-31 and 82.779999 at 2026-09-04 |
| the panel did not carry it as a return | `data/processed/returns.parquet`, (2026-09-04, APH), column `r` = NaN (still NaN after the rule) |
| the cross-check ratio | 0.499226, stored 158.5500 against a refetched 79.1522, recorded in `efb.e11_corporate_actions.cross_check_ratio` |
| the tolerance and why | `live/corporate_actions.py::CROSS_CHECK_TOLERANCE` = 0.02 |
| the appended session's return under the rule | 82.779999 * 2 / 158.550003 - 1 = 0.044213 |
| the store table and its key | `live/corporate_actions.py::TABLE` = `e11_corporate_actions`, `TABLE_KEY` = `("trade_date", "ticker")` |
| the run's own record | `efb.run_status.splits`, `efb.run_status.flags` |
| the message | `live/notify.py::compose`, `Corporate actions:` and `Large moves:` |
| the ledger entries | `docs/hygiene_ledger.md`, three entries dated 2026-09-25 |
| the prose rule | `README.md`, `## Corporate actions` |
| 20 tests | `tests/test_e11_corporate_actions.py` |

### git diff --stat from `base_commit` (4048b97)

This item's own files, from item 3's commit `f539c30`:

```text
$ git diff --stat f539c30 -- live/corporate_actions.py live/notify.py live/staleness.py \
    scripts/run_live_daily.py live/supabase_schema.sql docs/hygiene_ledger.md README.md \
    tests/test_e11_corporate_actions.py
 README.md                           |  22 ++
 docs/hygiene_ledger.md              |  50 +++
 live/corporate_actions.py           | 670 ++++++++++++++++++++++++++++++++++++
 live/notify.py                      |  26 +-
 live/staleness.py                   |   6 +
 live/supabase_schema.sql            |  18 +
 scripts/run_live_daily.py           |  40 ++-
 tests/test_e11_corporate_actions.py | 527 ++++++++++++++++++++++++++++
 8 files changed, 1357 insertions(+), 2 deletions(-)
```

From the task's `base_commit` (4048b97), which carries items 1, 2 and 3 as well:

```text
$ git diff --stat 4048b97
 ...
 28 files changed, 2673 insertions(+), 300 deletions(-)
```

No stored artifact and no research number is in either list.

### Yes or no, each with evidence

1. **Any two rows or two estimators identical.** No. The 32 control tickers are
   identical to each other by design (all exactly 1.0), which is what makes APH's
   0.499226 evidence rather than noise; the ratios are 33 distinct tickers read
   from 33 stored adjusted closes.
2. **Any exception caught and skipped, or fallback taken, with counts.** One, and it
   is deliberate: `apply_to_append` skips a ticker with no stored previous session,
   because there is no return to correct and no cross-check to make. It skips
   nothing else. A `KeyError` reading a cell is `None`, and the two paths that could
   guess (no record for a back-adjustment, a record disagreeing with the vendor's
   own factor) raise instead. Requests are capped at 30 per session by
   `max_cross_checks`, which is a bound on cost, not a silent drop: the cap is
   applied to the large-move population only, after the vendor-flagged tickers have
   all been checked.
3. **Any criterion reworded or replaced by a different test.** No `RESULTS.json`
   criterion, threshold or stored string was touched, and no notebook was opened.
   Three ledger entries were added; none was edited.
4. **Any criterion that passes by construction.** One, declared. The test that the
   APH line reproduces 0.044213 uses the closes I read out of the artifact, so it
   pins the arithmetic and the wiring, not the vendor's data. The artifact is what
   supplies the closes in production, and the ratio 0.499226 in that test is a
   measured number typed from the run pasted above.
5. **Any number that moved by a factor of 10 or more from its previous stored
   value.** No stored number moved at all: no artifact was written in this item, the
   returns artifact's hash is unchanged, and the split row is an addition to a new
   table.
6. **Any stored number typed into a notebook.** No notebook was opened, edited or
   executed.
7. **Any earlier verdict changed.** No. The 2026-09-04 hygiene decision stands as
   written; the new entry explains the case it does not cover rather than
   superseding it. Part 5's price handling, Guard 1's derivation and the owner's
   confirmed numbers all stand.

### Anything decided that the reviewer might disagree with

**A large move is reported, not blocked.** A 55% fall is a real return often enough
that refusing to price a book on it would be wrong, and the cross-check already
answers the question that matters. What does stop the run is a *restated* session
that no split record explains, because that is a corporate action this pipeline
cannot account for. If the reviewer wants an unexplained large move to stop the run
as well, it is one branch in `apply_to_append` and one test.

**The rule leaves APH's hole a hole.** The corrected return for 2026-09-04 is
reachable (+4.4213%), and applying it would mean writing the return of a period
whose denominator predates four missing sessions. The panel's convention everywhere
else is a one-session return, so the number is recorded in the rule's own tests and
in this report and not written into the panel. If the reviewer wants the appendix to
carry it, the honest form is a two-week return on the session it becomes available,
which is a different field.

**The tolerance is 2%, on a measured reason.** A tighter band rejects APH's own
split because of a dividend, and a looser one could let a fine split through as a
dividend. The number is in the module with the measurement beside it.

**`0.0` in the vendor's column means no split, not a factor of zero.** I found this
by testing the rule against a synthetic frame, where the fixture used 0.0 for a
clean session and the rule stopped the run naming a split factor of 0. The real
artifact uses the same convention, so a rule reading `!= 1.0` as "a split" would
have stopped every run. If the vendor ever means something else by 0.0, the module's
`split_factor_of` is the one place to change.

# Sprint E11 pre-deploy, item 3: the book's breadth, and the full book's, with no unqualified `n_eff`

**What was wrong.** The proposal manifest carried one `n_eff`, and it was the
**full 499-name book's** number before the floor: 157.33 at the 2026-09-21 close,
beside a book whose own breadth is 70.59. `scripts/run_live_daily.py::store_proposal`
copied it into `efb.proposals`, and both pages rendered it as "effective breadth
(n_eff)". On the page the owner watches for two evenings, that number meant more
than it said.

**The stored names are now qualified, and nothing writes the unqualified one.**

| name | what it is |
| --- | --- |
| `n_eff_kept` | the book that trades: after the floor, after the renormalization to gross 1.0 |
| `n_eff_full_book` | the full universe book before the floor, reported beside it |

- `live/evening_job.py`: the manifest's unqualified `n_eff` key is gone, and
  `_decomposition`'s internal key is renamed `effective_breadth` so the
  ambiguity cannot come back through a helper. The governing-breadth ratio reads
  the renamed key.
- `scripts/run_live_daily.py::store_proposal` writes both qualified names, and
  `efb.proposals` gains those two columns in place of `n_eff`.
  `live/reconcile.py`'s row column becomes `n_eff_kept`, because that record is
  the book's own.
- `live/sanity.py` stores `n_eff_kept_before/after` and
  `n_eff_full_book_before/after`.
- A grep for the unqualified name across `live/`, `scripts/`, `dashboard/`,
  `efb/` and `tests/` leaves only `live/breadth.py`'s deliberate legacy reader
  (and E8's own sizing-study field, which is a different object in the research
  stack and is untouched).

## The labels, in one place

`live/breadth.py` owns the two labels and the reader both pages use:

```text
BOOK_LABEL      = "the book's effective breadth"
FULL_BOOK_LABEL = "the full 499-name book's, before the floor"
```

- The Render page builds them with `live/dashboard_app.py::_breadth_columns`.
- The research page uses them in D10's book panel, and its construction summary
  metric is relabelled from "n_eff kept" to the book's label.
- `live/construction_table.py` reads the renamed decomposition key, so the E11-F12
  table still builds; its own stored column names (`n_eff_kept`, `n_eff_full`) are
  left alone, because both are already qualified by which book they describe and
  renaming a stored column would mean rebuilding the comparison artifact and
  moving numbers the reviewer has been reading since Part 1R.

**The legacy mapping**, for artifacts stored before this item:
`breadth.full_book_breadth` reads an old `n_eff` as the full book's, and
`breadth.book_breadth` returns `None` for such an artifact rather than showing the
full book's as the book's. `breadth.LEGACY_NOTE` is available for a page to say
so in words, and `breadth.legacy_artifact(record)` is true exactly when the
artifact has the old name and not the new one.

## The regenerated proposals

```text
2026-09-18: book breadth (n_eff_kept) 69.4578 | full book (n_eff_full_book) 146.3238
            recomputed from the stored weights 69.4578
            keys present: ['n_eff_full_book', 'n_eff_kept', 'n_effective']
            unqualified n_eff present: False
2026-09-21: book breadth (n_eff_kept) 70.5921 | full book (n_eff_full_book) 157.3291
            recomputed from the stored weights 70.5921
            unqualified n_eff present: False
```

Both book figures equal the breadth recomputed from the stored weights, which is
the whole point: the number a page shows under "the book's effective breadth" is
the traded book's. The 09-21 book value is the owner-confirmed 70.59.

The two `proposal_*.parquet` files are **unchanged** (they carry weights, not
breadths) and do not appear in this commit; only the manifests moved.

## Tests

Five new in `tests/test_e11_breadth.py`:

1. the two names return the two books, and neither label contains `n_eff`;
2. a legacy artifact maps to the full book only, `book_breadth` is `None` for it,
   the note is `LEGACY_NOTE`, and an empty record invents nothing;
3. the stored proposals carry both names, no unqualified one, and
   `n_eff_kept` equals the breadth recomputed from the stored weights, at both
   closes;
4. the Render page's two columns are the two labels, and its book figure equals
   the traded book's recomputed breadth while its full-book figure is more than
   one name away from it;
5. the research page's D10 book panel shows the same twice over.

**Four existing test files were edited deliberately**, all of them fixtures whose
stub manifests carried the old key: `tests/test_e11_evening.py` (the internal
decomposition key and the two manifest keys),
`tests/test_e11_sanity.py`, `tests/test_e11_reconcile.py` and
`tests/test_dashboard_d10.py`. No assertion was weakened; each was retargeted at
the renamed field, and the d10 stub gained the full-book number so both labels can
be checked.

## Verification

Per step, the selection is every test touching what changed: the breadth names,
both pages, the runner, the sanity gate and the construction table.

```text
$ .venv/bin/python -m pytest tests/test_e11_breadth.py tests/test_e11_evening.py \
    tests/test_e11_sanity.py tests/test_e11_reconcile.py tests/test_dashboard_d10.py \
    tests/test_e11_render.py tests/test_e11_notify.py tests/test_e11_staleness.py \
    tests/test_run_live_daily.py -q --tb=short
103 passed, 1 skipped in 25.11s

$ .venv/bin/python -m pytest tests/test_construction_table.py tests/test_e11_breadth.py -q
12 passed in 103.98s (0:01:43)
```

The full suite is required here because two stored artifacts were regenerated
(standard 21, point 3).

```text
$ make test > /tmp/full5.log 2>&1; echo "EXIT=$?"
$ tail -c 300 /tmp/full5.log

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
786 passed, 1 skipped, 3 warnings in 599.86s (0:09:59)
EXIT=0
```

The previous full run, at Part 5's commit, was 774 passed, 1 skipped (775
collected). This one collects 787: item 1's 3 universe tests, item 2's 4 catch-up
tests and this item's 5 breadth tests, with nothing lost.

`make lint`, exit 0:

```text
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
Success: no issues found in 33 source files
.venv/bin/black --check efb dashboard live tests
All done! ... 172 files would be left unchanged.
```

`make verify-evidence`, exit 0:

```text
evidence OK
```

### Headline numbers, file and key

| number | file and key |
| --- | --- |
| the two stored names | `live/proposals/proposal_2026-09-21.json`, `n_eff_kept` and `n_eff_full_book` |
| 70.5921 and 157.3291 at 09-21, 69.4578 and 146.3238 at 09-18 | the same files, read directly |
| the book's number equals the recomputed breadth | the pasted block above, from `proposal_*.parquet` |
| no unqualified `n_eff` is written | `live/evening_job.py` (manifest), `scripts/run_live_daily.py:133` (row), `live/reconcile.py:82` |
| the legacy mapping | `live/breadth.py::full_book_breadth`, `book_breadth`, `legacy_artifact` |
| the two labels | `live/breadth.py::BOOK_LABEL`, `FULL_BOOK_LABEL`; used by `live/dashboard_app.py::_breadth_columns` and `dashboard/tabs/d10_book.py` |
| two columns in place of one | `live/supabase_schema.sql`, `efb.proposals`; `efb.reconciliation` carries `n_eff_kept` |
| 5 tests | `tests/test_e11_breadth.py` |

### git diff --stat from `base_commit` (4048b97)

This item's own files, from item 2's commit `6c1bbc2`, with
`git add -N live/breadth.py tests/test_e11_breadth.py` first so the new files
appear:

```text
$ git diff --stat 6c1bbc2 -- handoff/REPORT.md live/breadth.py live/evening_job.py \
    live/reconcile.py live/sanity.py live/construction_table.py \
    live/dashboard_app.py dashboard/tabs/d10_book.py live/supabase_schema.sql \
    scripts/run_live_daily.py live/proposals tests/test_e11_breadth.py \
    tests/test_e11_evening.py tests/test_e11_sanity.py tests/test_e11_reconcile.py \
    tests/test_dashboard_d10.py
 dashboard/tabs/d10_book.py              |  11 +-
 handoff/REPORT.md                       | 308 ++++++++++++++++++------------
 live/breadth.py                         |  65 ++++++++
 live/construction_table.py              |   4 +-
 live/dashboard_app.py                   |  18 ++-
 live/evening_job.py                     |  10 +-
 live/proposals/proposal_2026-09-18.json |   7 +-
 live/proposals/proposal_2026-09-21.json |   7 +-
 live/reconcile.py                       |   4 +-
 live/sanity.py                          |   6 +-
 live/supabase_schema.sql                |   5 +-
 scripts/run_live_daily.py               |   3 +-
 tests/test_dashboard_d10.py             |   3 +-
 tests/test_e11_breadth.py               |  92 +++++++++++
 tests/test_e11_evening.py               |   5 +-
 tests/test_e11_reconcile.py             |   2 +-
 tests/test_e11_sanity.py                |   2 +-
 17 files changed, 411 insertions(+), 141 deletions(-)
```

The two proposal parquets are absent from that list: the books did not move, only
their manifests' field names. From the task's `base_commit` (4048b97), which
carries items 1 and 2 as well:

```text
$ git diff --stat 4048b97
 ...
 24 files changed, 1316 insertions(+), 298 deletions(-)
```

### Yes or no, each with evidence

1. **Any two rows or two estimators identical.** No. The two books differ in both
   numbers at both closes (70.5921 against 157.3291, 69.4578 against 146.3238),
   and test 4 asserts the page's two figures are more than one name apart.
2. **Any exception caught and skipped, or fallback taken, with counts.** Yes, one,
   and it is the item's own subject: the legacy read. `full_book_breadth` falls
   back to the old `n_eff` for an artifact that predates the split, and it can
   only ever produce the full book's number; `book_breadth` refuses the fallback
   and returns `None`. Test 2 asserts both, and the note is exposed rather than
   swallowed.
3. **Any criterion reworded or replaced by a different test.** No `RESULTS.json`
   criterion, threshold or stored string was touched. Four existing test files'
   fixture dictionaries were renamed as listed above, and the d10 stub gained a
   field; no stored score moved. The construction table's own column names are
   deliberately unchanged, and the artifact is byte-identical in this commit.
4. **Any criterion that passes by construction.** One, declared: the regenerated
   manifests' `n_eff_kept` comes from the same `kept_decomposition` whose weights
   are written to the parquet, so the test comparing the manifest's number with
   the recomputed breadth proves the two agree, not that the breadth formula is
   the right one. The formula is E8's, unchanged by this item, and its own
   criterion stands.
5. **Any number that moved by a factor of 10 or more from its previous stored
   value.** No. `n_eff_kept` equals the number the manifest already carried under
   `n_eff_kept`, and `n_eff_full_book` equals the old `n_eff`: 157.33 and 70.59
   are the same numbers, now named for what they are. The 09-18 numbers moved
   only by the universe fields item 1 changed, and those weights did not move.
6. **Any stored number typed into a notebook.** No notebook was opened, edited or
   executed.
7. **Any earlier verdict changed.** No. Part 5's books, Guard 1's derivation and
   the owner's confirmed numbers all stand; this item renames fields so the page
   cannot mislead about the book the owner confirmed.

### Anything decided that the reviewer might disagree with

**The construction table's columns keep their names.** `n_eff_kept` and
`n_eff_full` inside `live/construction_table.parquet` are both qualified by which
book they describe, so the reviewer's complaint (an unqualified `n_eff` read as
the book's) does not apply to them, and renaming a stored column would rebuild the
comparison artifact and touch numbers the reviewer has read since Part 1R. If the
reviewer wants `n_eff_full_book` there too, it is a table rebuild plus two test
edits.

**The research dashboard now imports `live.breadth`.** The alternative was a
second copy of the labels in `dashboard/tabs/d10_book.py`, which is how
`_construction_label` ended up duplicated. One shared, tested reader is the
reason the two pages cannot disagree, and `live/breadth.py` imports nothing but
`__future__` and typing.
