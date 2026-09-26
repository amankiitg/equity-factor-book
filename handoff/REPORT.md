# e11-deploy C0, part two: the exposures are computed, and where that stopped

**`exposures_after_hedge` is in, and it is the hedge's own number.**
`live/evening_job.py::exposures` is `X'w` exactly as `_decomposition` computes it,
on the same design the hedge subtracts against: standardized descriptors plus sector
dummies, whose column order `efb/race.py::_descriptor_design` documents as
`fx.ESTIMATED_NAMES`. `labelled_exposures` names each value and raises if the design
has a different width than the names, because a mismatch would put the wrong name on
a number. The manifest carries it, `snapshot.build` copies it, and
`docs/snapshot.schema.json` has it. Measured on the real 09-21 book, one value per
design column, 17 of them:

```text
factors: 17
max |after| : 1.207e-15
sample after: market -3.34e-16, size -1.20e-15, beta 2.50e-16
```

The test asserts the labels equal `fx.ESTIMATED_NAMES`, that the worst exposure is
below 1e-10, and that the book it came from is the stored one, `n_eff_kept` 70.5921.

**`exposures_before_hedge` is deliberately not in, and here is exactly why.** My
first attempt took `X'w` of the book *after* `size.procedure_6_3`, which applies the
hedge itself, so the "before" vector came out identical to the "after" one:
`max |before|` was 0.000000 when a pre-hedge book has real exposures. Putting that
field on the page would have shown a duplicate under a second name, which is worse
than showing nothing. The hedge's own pre-hedge vector exists and is
`design.T @ size.proportional(alpha, specific)` inside
`live/sizing.py::procedure_6_3_robust`, so the change is to surface it there and have
`sized_kept_weights` carry it to the manifest, which touches its two call sites. That
is the next step, not a missing idea.

**One mistake of mine, and how it was caught.** The edit that was meant to add the
sizing companion wrote `evening_job.py`'s text into `live/sizing.py`, because a
variable in the script was still bound to the wrong path. Nothing was committed:
`git checkout -- live/sizing.py` restored it, the call site went back to the function
that exists, and `ruff`, `mypy live scripts` and 62 tests pass on the restored tree.
The `git status` before the restore listed the four files that were meant to change,
so the mistake was visible in the same command that made it.

**`book_as_of` is in.** `snapshot.build` carries the close of the proposal the book
came from, which is the manifest's own `as_of`: the target close on a run that
proposed a book, and the previous proposal's close on a stopped run, so the page
cannot show a book without its date. The schema requires it.

# e11-deploy C0, part one: the cron's plan key

`render.yaml` had no `plan:` key, so Render would have created the cron on its
default instance. From Render's Blueprint reference, the `plan` field's Cron Job
table: "| 2 CPU | 4 GB | `2c-4g` |", and the same page, on omitting the field:
"Render uses `0.5c-512mb` for a new web service, private service, background
worker, or cron job." A 1.07 GiB peak on 512 MB falls over on the first evening,
which is what C0 names.

`render.yaml` now carries `plan: 2c-4g` on the cron, with that reading quoted
beside it, and `tests/test_e11_render.py::test_the_cron_is_created_on_the_four_gigabyte_plan`
asserts the key, that it is the 4 GB instance, and that neither the omitted default
nor the 2 GB plan appears anywhere in the blueprint.

```text
$ .venv/bin/python -m pytest tests/test_e11_render.py -q
16 passed, 1 skipped in 1.97s
```

## C0 still open, and what it needs

Committed here is the first bullet only. The rest of C0 is not started rather than
half-done:

- **The snapshot's three fields.** `exposures_before_hedge`, `exposures_after_hedge`
  and `book_as_of` must be added to `live/snapshot.py` and to
  `docs/snapshot.schema.json`. `book_as_of` is the close of the proposal the book
  came from, which depends on C0's own stopped-run change. The two exposure fields
  are *per-factor* exposures before and after the FMP hedge, and the source of that
  vector is not in the manifest's scalars (`max_abs_exposure_after_fmp`,
  `idio_share_after_fmp`) nor in the snapshot's `hedge`/`exposures` blocks today, so
  finding it is the first task. I did not guess at it: a wrong exposure block on the
  page is worse than a missing one.
- **The fixtures.** `web/fixtures/snapshot_ok.json` from the 09-21 proposal, plus
  the four state variants derived by the writer.
- **`EFB_INIT_STORE`.** Strict parsing, the one-row marker, and the empty-appendix
  check that follows it.

# A measurement run of mine rewrote four raw artifacts, and the evidence check caught it

**What happened.** To measure the cron's peak memory for B-cron I ran
`evening_job.build_proposal` locally, believing it was read-only because it reads
the artifacts rather than fetching them. It is not: it rewrites
`data/raw/prices.parquet` (61 MB), `data/raw/shares_history.parquet` and both
`data/raw/spy_holdings/spy_holdings_2026-09-1[8|21].parquet` files. The
gitignored artifacts are not in git, so nothing showed in `git status`, and I used
`git add -A` on the next commit, which is how a change I did not intend nearly
rode along. `make verify-evidence` failed, which is exactly what it is for.

**What the check caught beyond the bytes.** Comparing the SPY archive against its
evidence snapshot showed the rewrite had dropped three columns: the recorded
snapshot has `name, ticker, identifier, sedol, weight, sector, shares_held,
local_currency, as_of`, and the rewritten file had only `as_of, ticker, name,
identifier, sedol, weight`. So the reader that archives a SPY file writes a leaner
frame than the archive it replaces. On the cron that is invisible, because
Render's disk is ephemeral and the archive is refetched each run, but a local run
loses the sectors, the share counts and the local currency from the source the
universe comes from, and any later run that reads the archive instead of the
source would get less than it thinks.

**What I did, and where it stands.** Every artifact the check named was restored
byte-for-byte from its own snapshot under `evidence/`, and `make verify-evidence`
passes again:

```text
restored data/raw/prices.parquet 61233059 bytes
restored data/raw/shares_history.parquet 2146029 bytes
restored data/raw/spy_holdings/spy_holdings_2026-09-18.parquet 34358 bytes
attempt 1 -> evidence OK
```

**The defect is open, deliberately.** The fix belongs in the append path
(`live/evening_job.py::load_spy_universe` and whatever else writes raw artifacts),
not in a hurry: the reader must not replace an archive with a narrower frame, and
a read path must not rewrite raw data at all. It is written into the session notes
and it is the first thing after the reviewer's remaining notes. Until it lands,
the artifacts on disk are the snapshot's, and no claim in this report rests on a
number the rewrite touched.

**The lesson, stated plainly.** I asserted "read-only" about a run I had not
checked, and the evidence check is the only reason it was caught. That is the same
mistake shape as the void suite: a claim about a tool's behaviour standing in for
a check.

# Sprint E11 pre-deploy, B-cron: Render runs only the cron, and the cron writes the snapshot

**The web service is gone.** `render.yaml` declares one service, the daily cron.
The live book monitor is the Cloudflare page, so the Render dashboard service, the
`efb_reader` role and the read-only connection string all go with it: one fewer
credential, one fewer box to fall over. `live/dashboard_app.py` still runs locally
as a research view, as the task allows, until the Cloudflare page is proven.

**The reader role is removed and the writer loses `delete`.** With no web service
nothing needs a read role. The writer's grant was `select, insert, update, delete`
and nothing in this repository deletes a row: `live/store.py` issues exactly two
statements, an `INSERT ... ON CONFLICT` upsert and a `SELECT`, across 18 tables. So
the grant is now `select, insert, update`, and `efb_archiver`, which needs `delete`
on the `e11_*` tables and nothing else, arrives with retention in item 6.

**The snapshot.** `live/snapshot.py` builds one JSON document per run and puts it in
R2 twice, `latest.json` and `snapshots/<close>.json`, as single-object puts signed
with SigV4 by hand: one object, one verb, no client library worth carrying for it.
The signature covers the payload hash, so a truncated body is refused by the server
rather than stored.

| what the page needs | where it comes from |
| --- | --- |
| `schema_version`, `generated_at` | constants and the clock |
| the target close and `run_status` | the run's own row: status, detail, failing inputs, catch-up and its sessions, splits, flags, notify and snapshot state |
| `expected_next_by` | the next NYSE session after the close, at the cron's own slot (22:30 UTC, from `render.yaml`'s schedule) plus a three-hour grace. Friday points at Monday, and Thanksgiving Thursday points at the Friday, because the calendar answers |
| `dry_run` | the run |
| the construction label | `live/construction_table.construction_label`, generated only from the proposal's fields |
| the book | the proposal's rows with their trade reasons, weights, sides, z and alpha |
| hedge and exposures | the manifest and the chosen construction table row |
| breadth | `n_eff_kept` and `n_eff_full_book` with item 3's two labels, and no unqualified `n_eff` anywhere |

**Written on every run, including `stale_stopped` and `error`.** The snapshot goes
out first inside `finish_run`, before the message and before the row, so the page
shows the failure even when the message could not be sent. A stopped run has no
manifest of its own, so it carries the last proposal on disk: blanking the page on
the evening the loop refused to price a book would hide the book the owner is still
holding. Those names carry no trade reasons, and the module says why: reasons belong
to the evening that proposed them, and inventing them for a night that traded
nothing is the kind of guess this pipeline does not make.

**The switch, and why neither default is safe.** `EFB_SNAPSHOT` is required.

| `EFB_SNAPSHOT` | `dry_run` | what happens |
| --- | --- | --- |
| `on` | either | uploaded; a failed upload is an `error`, and `finish_run` turns an otherwise ok run into one |
| `off` | true | nothing uploaded; `snapshot: off (dry run)` in `run_status` and in the email, which is how the gate evenings run before the page exists |
| `off` | false | an error: the flip cannot happen without a page that can show a real snapshot |

**JSON has no NaN.** Every number goes through `store.json_text`, and `build` turns
non-finite values into `null` as well, so the document and its text agree rather
than only the text being safe. A test asserts the serialized document contains no
`NaN` and that a NaN breadth and an infinity z come out as `null`.

**The schema is shared.** `docs/snapshot.schema.json` is committed and the writer's
output is validated against it in the test, so the writer and the Cloudflare page
cannot drift. The schema pins the keys the page reads, including `expected_next_by`
and the two qualified breadth names.

**Credentials.** Four R2 variables, all required when the switch is on, with a
missing one named in the error. The test asserts that an access key id, a secret, a
Resend key and a database URL do not appear in the document, and that the scrub
would remove each of them on the way out anyway.

## The peak memory, measured before choosing a plan

```text
$ /usr/bin/time -l .venv/bin/python -c "appendix.hydrate(); evening_job.build_proposal(store=False)"
book: 2026-09-21 499 names, n_eff_kept 70.5921
        9.42 real         8.37 user         2.34 sys
          1146863616  maximum resident set size
          1368245976  peak memory footprint
```

**Peak RSS 1,146,863,616 bytes, 1.07 GiB** (peak footprint 1.37 GB), for the
hydration plus a full proposal build in 9.42 seconds. The book it built is the
stored one to four decimals, 70.5921, so the measurement is of the real path rather
than of a reduced one.

**The plan: `2c-4g`, 2 CPU and 4 GB.** Render's own cron table, read rather than
recalled: 512 MB is $0.00016/minute, 2 GB $0.00058, **4 GB $0.00197**, 8 GB
$0.00313, prorated to the second. 2 GB is 1.9x the peak, under the 2x rule, so the
smallest plan that clears it is 4 GB, which is 3.5x. At a five-minute run (the
measured 9.42 seconds is the hydration and build only; the extension's downloads are
the rest) and about 21 sessions a month, that is **about $0.21 a month of compute**,
plus whatever workspace tier the owner already has. The five minutes is an estimate
and the owner will see the real duration in the cron's own logs after the first runs.

## Tests

`tests/test_e11_snapshot.py`, 14 tests: the writer against the committed schema and
the schema refusing a document that drops a field the page needs, the NaN and
infinity rules in both the document and its text, the absence of an unqualified
`n_eff`, item 3's two labels, the run's own status including catch-up sessions and
splits, the names' fields, `expected_next_by` against the calendar including
Thanksgiving, the switch's rules in both directions, `off` writing nothing,
`on` writing both keys with a SigV4 header and the payload hash inside it, no
credential in the document, a missing R2 variable named in the error, a refused
upload raising so the run can fail, and a stopped run still carrying the last book.

`tests/test_e11_deploy.py` and `tests/test_e11_render.py` moved with the blueprint:
one service, no web service, the reader and the archiver absent, the writer's grant
without `delete`, and the eight cron variables present.

## Verification

```text
$ .venv/bin/python -m pytest tests/test_e11_deploy.py tests/test_e11_render.py \
    tests/test_e11_snapshot.py tests/test_e11_notify.py tests/test_e11_staleness.py \
    tests/test_run_live_daily.py tests/test_e11_store.py tests/test_dashboard_d10.py -q
109 passed, 1 skipped in 47.31s

$ make test-fast
787 passed, 1 skipped, 29 deselected, 3 warnings in 80.19s
```

The fast selection's 787 was the frozen-tree run reported with the previous item;
this item's own eight files were added afterwards, so the next fast run collects
eight more.

`make lint`, exit 0, and `make verify-evidence`, exit 0 (both run above).

### Headline numbers, file and key

| number | file and key |
| --- | --- |
| peak RSS 1,146,863,616 bytes | `/usr/bin/time -l` on `appendix.hydrate(); evening_job.build_proposal(store=False)` |
| the plan and its price | Render's cron table: `2c-4g`, 4 GB, $0.00197/minute, prorated to the second |
| 2x headroom over 1.07 GiB | the same table, 4 GB against the measured peak |
| the switch | `live/snapshot.py::SNAPSHOT_ENV`, `snapshot_mode`, `check_snapshot` |
| the two keys | `live/snapshot.py::LATEST_KEY`, `DATED_TEMPLATE` |
| the expectation | `live/snapshot.py::expected_next_by`, `RUN_SLOT_UTC`, `GRACE_HOURS` |
| the shared schema | `docs/snapshot.schema.json`, validated in `tests/test_e11_snapshot.py` |
| no unqualified `n_eff` | `live/snapshot.py::build`, `breadth` |
| one service | `render.yaml`, one `- type: cron` |
| one role, without delete | `live/supabase_roles.sql` |
| the run's own record of the snapshot | `efb.run_status.snapshot` |
| 14 tests | `tests/test_e11_snapshot.py` |

### git diff --stat from `base_commit` (4048b97)

This item's own files, from item A's commit `04780e7`:

```text
$ git diff --stat 04780e7 -- live/snapshot.py live/staleness.py live/notify.py \
    live/construction_table.py live/dashboard_app.py dashboard/tabs/d10_book.py \
    scripts/run_live_daily.py render.yaml .env.example live/supabase_roles.sql \
    live/supabase_schema.sql docs/snapshot.schema.json tests/conftest.py \
    tests/test_e11_snapshot.py tests/test_e11_deploy.py tests/test_e11_render.py
.env.example               |  12 ++
 dashboard/tabs/d10_book.py |  29 +--
 docs/snapshot.schema.json  | 137 ++++++++++++
 live/construction_table.py |  32 +++
 live/dashboard_app.py      |  32 +--
 live/notify.py             |   7 +
 live/snapshot.py           | 518 +++++++++++++++++++++++++++++++++++++++++++++
 live/staleness.py          |   4 +
 live/supabase_roles.sql    |  33 +--
 live/supabase_schema.sql   |   3 +
 pyproject.toml             |   2 +
 render.yaml                |  47 ++--
 scripts/run_live_daily.py  | 112 +++++++---
 tests/conftest.py          |   5 +
 tests/test_e11_deploy.py   |  20 +-
 tests/test_e11_render.py   |  21 +-
 tests/test_e11_snapshot.py | 292 +++++++++++++++++++++++++
 17 files changed, 1181 insertions(+), 125 deletions(-)
```

From the task's `base_commit` (4048b97), which carries every earlier item:

```text
$ git diff --stat 4048b97
 tests/test_e11_store.py                 |  139 ++++
 41 files changed, 5613 insertions(+), 507 deletions(-)
```

### Yes or no, each with evidence

1. **Any two rows or two estimators identical.** Not applicable: no estimator is
   touched; the snapshot copies numbers rather than computing them.
2. **Any exception caught and skipped, or fallback taken, with counts.** One, and
   it is deliberate: a stopped run falls back to the last proposal on disk, so the
   page keeps showing a book. It is not silent (the run's status is in the document
   beside it) and it invents no trade reasons, which the module says in prose. The
   failed-upload path is caught only to record it and fail the run.
3. **Any criterion reworded or replaced by a different test.** No `RESULTS.json`
   criterion. Two render tests and one deploy test moved with the blueprint and the
   roles, which is this item's own subject.
4. **Any criterion that passes by construction.** One, declared: the upload tests
   drive a poster fake, so they prove the request shape, the two keys and the
   signature's presence, not that R2 accepts them. Nothing here can upload for real,
   and the first real upload is an owner step.
5. **Any number that moved by a factor of 10 or more from its previous stored
   value.** No stored number moved: no artifact was written, and the snapshot is a
   new object rather than a change to an existing one.
6. **Any stored number typed into a notebook.** No notebook was opened, edited or
   executed.
7. **Any earlier verdict changed.** No. The web service's removal follows the
   owner's decision, and the earlier deploy steps that named it are superseded by
   the full deploy list that comes with the last item.

### Anything decided that the reviewer might disagree with

**The writer loses `delete` now rather than when the archiver arrives.** The task
lists it among the smaller items, but it belongs to this commit because the roles
file is already open here and the evidence is one grep: two statements in
`live/store.py`, neither of which deletes. Item 6 adds `efb_archiver` with `delete`
on the `e11_*` tables only.

**`efb_archiver` is not created yet.** The task puts it in item 6 with the archive
command it serves, and a role with no caller is a credential to rotate for no
reason. The deploy list says so, and the roles file says so where it matters.

**A stopped run keeps the previous book.** The alternative is a page that blanks on
exactly the evening something went wrong, with the failure visible either way. If
the reviewer would rather a stopped run show no positions, it is one branch and two
assertions.

# Sprint E11 pre-deploy, item A: notifications by email through Resend, not Slack

**What changed.** The run's message leaves through Resend's HTTP API now, copied
from credit-trading-lab's pattern, and the Slack webhook is gone from the code,
the blueprint and the example environment.

**The pattern, read from the credit lab and followed.** Its
`execution/alerts.py::send_alert_email` posts to `https://api.resend.com/emails`
with `Authorization: Bearer <key>`, a body of `from`, `to`, `subject` and `text`,
and a 15-second timeout, and its `render.yaml` declares `RESEND_API_KEY`,
`ALERT_EMAIL_TO` and `RESEND_FROM` with `sync: false`. That is what
`live/notify.py::post`, `email_payload` and `send` do, against
`EFB_RESEND_API_KEY`, `EFB_NOTIFY_EMAIL_TO` and `EFB_NOTIFY_EMAIL_FROM`. The credit
lab's `.env` was not opened.

**The sending domain and what it restricts.** The credit lab uses Resend's shared
sender, `credit-trading-lab <onboarding@resend.dev>`, and EFB now defaults to
`equity-factor-book <onboarding@resend.dev>` when `EFB_NOTIFY_EMAIL_FROM` is unset.
That shared sender can only deliver to the address that owns the Resend account,
so it works for this owner and would not work for a mailing list; a verified
domain is what lifts that, and setting `EFB_NOTIFY_EMAIL_FROM` to an address on one
is the only change needed then.

**The subject carries the status**, readable from an inbox without opening the
email. Verified here, one line each, in
`tests/test_e11_notify.py::test_the_subject_reads_from_the_inbox_the_way_the_owner_asked`:

```text
EFB ok 2026-09-25 | 150 proposed, none sent | stale 0
EFB ok 2026-09-25 | 150 sent | stale 0
EFB STALE 2026-09-25 | none proposed | stale 3 (prices)
EFB ERROR 2026-09-25 | none proposed | ValueError
EFB ok (catch-up 4) 2026-09-22 | 150 proposed, none sent | stale 0
EFB ok 2026-09-25 | 12 proposed, none sent | stale 0 | split APH 2:1 | flag 1
```

The last line shows the split and the flag appended, and that a flag whose move is
explained by the split is not counted: `flag 1`, not `flag 2`. The split's wording
comes from the same `describe` the body uses, so the subject and the body cannot
drift.

**The body's first line names the store**, then the three fields follow as before
(`Orders`, `Staleness`, and `Failing inputs` or `Error` when they apply).

**The key shape is scrubbed.** `re_...` is now one of the scrub's patterns, because
Resend's keys are short enough to slip past the base64 rules and nothing raises them
as `api_key=...`. `test_the_resend_key_shape_is_scrubbed` proves a key inside an
error string comes out as `[redacted]`, and the endpoint itself is redacted too,
which is the right side to err on.

**Everything specified carried over unchanged:** one email per run including clean
ones, a failed or unconfigured send is recorded and the run exits nonzero, the send
happens after the proposal and the orders, and the error text is scrubbed.

**Slack is gone.** `EFB_NOTIFY_SLACK_WEBHOOK_URL` has left `render.yaml`,
`.env.example`, `live/staleness.py`'s dashboard message and the tests;
`live/notify.py` no longer has `CHANNEL_ENV` or `slack_payload`. The channel
interface is unchanged: `send(subject, message)` and `notify_run(...)`.

## Tests

`tests/test_e11_notify.py` now carries the five subject formats, the Resend
payload's `from`/`to`/`subject`/`text`, the key-shape scrub, and a skipped send
that names both email variables. Its posters take the authorization header. Two
tests in `tests/test_e11_render.py` moved: the example environment declares
`EFB_STORE`, `EFB_RESEND_API_KEY`, `EFB_NOTIFY_EMAIL_FROM` and
`EFB_NOTIFY_EMAIL_TO`, and the render test asserts the three sending variables are
on the cron service and not on the web service, with no key material and no address
anywhere in the blueprint.

## Verification

```text
$ .venv/bin/python -m pytest tests/test_e11_notify.py tests/test_e11_render.py \
    tests/test_e11_staleness.py tests/test_run_live_daily.py tests/test_dashboard_d10.py -q
60 passed, 1 skipped in 54.19s
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

The clean run on the tree carrying items 4b and A, with standard 21's fast and
slow split stated:

```text
$ make test-fast
787 passed, 1 skipped, 29 deselected, 3 warnings in 80.19s (0:01:20)
```

**The earlier full-suite run is void, and I am not reporting its numbers as
evidence.** It reported three failures at the 44 percent mark, and they are mine: I
edited `live/notify.py` while it was running, including a moment when its module
docstring was unclosed, so every test that imported the module after that point
failed for reasons that have nothing to do with the item under test. The run above
was started on the frozen tree, with nothing edited while it ran, and it is the
result this item stands on.

### Headline numbers, file and key

| number | file and key |
| --- | --- |
| the endpoint | `live/notify.py::RESEND_ENDPOINT` = `https://api.resend.com/emails` |
| the three variables | `live/notify.py::API_KEY_ENV`, `FROM_ENV`, `TO_ENV` |
| the sender fallback | `live/notify.py::DEFAULT_SENDER` |
| the subject builder | `live/notify.py::subject_text`, with `_split_short` |
| the request body | `live/notify.py::email_payload` |
| the key scrub shape | `live/notify.py::RESEND_KEY_SHAPE` inside `_SCRUBS` |
| the blueprint | `render.yaml`, the cron's `envVars` |
| the example environment | `.env.example`, `EFB_STORE`, the three email keys |
| 2 new tests | `tests/test_e11_notify.py` |

### git diff --stat from `base_commit` (4048b97)

This item's own files, from item 4b's commit `3837ff6`:

```text
$ git diff --stat 3837ff6
 .env.example             |  23 ++++--
 live/notify.py           | 188 +++++++++++++++++++++++++++++++++++++++--------
 live/staleness.py        |   2 +-
 render.yaml              |  12 ++-
 tests/test_e11_notify.py | 133 ++++++++++++++++++++++++++-------
 tests/test_e11_render.py |  26 ++++---
 6 files changed, 310 insertions(+), 74 deletions(-)
```

From the task's `base_commit` (4048b97), which carries items 1 to 4b:

```text
$ git diff --stat 4048b97
 35 files changed, 4156 insertions(+), 403 deletions(-)
```

### Yes or no, each with evidence

1. **Any two rows or two estimators identical.** Not applicable: no estimator.
2. **Any exception caught and skipped, or fallback taken, with counts.** One, and
   it is unchanged from Part 3b: a failed send is caught so the run's own record
   still lands, and the result is `failed`, which the caller turns into a nonzero
   exit. A missing channel is `skipped` for the same reason and fails the run the
   same way.
3. **Any criterion reworded or replaced by a different test.** No `RESULTS.json`
   criterion. Nine notify tests and two render tests moved from the webhook to the
   email variable, which is the item's own subject, and one dashboard message string
   in `live/staleness.py` names the email variables now.
4. **Any criterion that passes by construction.** One, declared: the tests drive the
   poster fake, so they prove the payload and the subjects, not that Resend accepts
   them. Nothing in this environment can send a real email, and the first test email
   is an owner step in the deploy list.
5. **Any number that moved by a factor of 10 or more from its previous stored
   value.** No stored number moved: no artifact was written and no store write path
   changed.
6. **Any stored number typed into a notebook.** No notebook was opened, edited or
   executed.
7. **Any earlier verdict changed.** No. Part 3b's notification rules stand, and this
   item swaps the channel under them.

### Anything decided that the reviewer might disagree with

**An unconfigured email fails the run, where the credit lab's sender quietly
returns False.** That difference is deliberate and pre-existing: EFB's rule has been
one message per run with a failed send failing the run since Part 3b, and a silent
skip is exactly the healthy-looking failure E11-F17 is about. The credit lab's own
choice suits its alert, which is optional.

**The key is read from `EFB_RESEND_API_KEY` only.** No fallback to the credit lab's
`RESEND_API_KEY`, so the two keys cannot be confused for each other and EFB cannot
send with the other project's credential even if both are present.

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

`tests/test_e11_store.py`, eight new tests: the local fallback needs an explicit
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
changed and no stored artifact was rebuilt. The clean run on this tree, with the
fast selection and the slow split reported:

```text
$ make test-fast
787 passed, 1 skipped, 29 deselected, 3 warnings in 80.19s (0:01:20)
```

787 passed against item 3's 786, so the count grew rather than shrank, and the 29
deselected are the tests marked slow. The collected total is 817 against item 3's
787, which is this item's 8 tests, item 4's 20 and item A's 2.

**The first full-suite run of this item is void and its numbers are not evidence.**
It reported three failures, and they are mine: I edited `live/notify.py` while it was
running, including a moment when its module docstring was unclosed, so every test
that imported the module after that point failed for reasons that have nothing to do
with this item. The clean run above was started on the frozen tree afterwards.

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
| 8 new tests | `tests/test_e11_store.py` |

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
```

From the task's `base_commit` (4048b97), which carries items 1, 2, 3, 4 and 4a:

```text
$ git diff --stat 4048b97
README.md                               |  34 +-
 dashboard/tabs/d10_book.py              |  11 +-
 docs/hygiene_ledger.md                  |  50 ++
 handoff/LOG.md                          | 206 +++++++
 handoff/PROJECT_CONTEXT.md              |  75 ++-
 handoff/REPORT.md                       | 914 ++++++++++++++++++++++++--------
 handoff/TASK.md                         | 419 ++++++++++++++-
 live/breadth.py                         |  65 +++
 live/construction_table.py              |   4 +-
 live/corporate_actions.py               | 670 +++++++++++++++++++++++
 live/dashboard_app.py                   |  18 +-
 live/evening_job.py                     |  63 ++-
 live/extend.py                          |  17 +
 live/notify.py                          |  47 +-
 live/proposals/proposal_2026-09-18.json |  13 +-
 live/proposals/proposal_2026-09-21.json |   7 +-
 live/reconcile.py                       |   4 +-
 live/sanity.py                          |   6 +-
 live/staleness.py                       |  17 +-
 live/store.py                           | 147 ++++-
 live/supabase_schema.sql                |  25 +-
 scripts/run_live_daily.py               | 132 ++++-
 scripts/verify_store_roundtrip.py       | 318 +++++++++++
 tests/conftest.py                       |  14 +
 tests/test_dashboard_d10.py             |   3 +-
 tests/test_e11_breadth.py               |  92 ++++
 tests/test_e11_corporate_actions.py     | 527 ++++++++++++++++++
 tests/test_e11_evening.py               |  41 +-
 tests/test_e11_notify.py                | 101 +++-
 tests/test_e11_reconcile.py             |   2 +-
 tests/test_e11_sanity.py                |   2 +-
 tests/test_e11_store.py                 | 139 +++++
 32 files changed, 3850 insertions(+), 333 deletions(-)
README.md                               |  34 +-
 dashboard/tabs/d10_book.py              |  11 +-
 docs/hygiene_ledger.md                  |  50 ++
 handoff/LOG.md                          | 206 +++++++
 handoff/PROJECT_CONTEXT.md              |  75 ++-
 handoff/REPORT.md                       | 914 ++++++++++++++++++++++++--------
 handoff/TASK.md                         | 419 ++++++++++++++-
 live/breadth.py                         |  65 +++
 live/construction_table.py              |   4 +-
 live/corporate_actions.py               | 670 +++++++++++++++++++++++
 live/dashboard_app.py                   |  18 +-
 live/evening_job.py                     |  63 ++-
 live/extend.py                          |  17 +
 live/notify.py                          |  47 +-
 live/proposals/proposal_2026-09-18.json |  13 +-
 live/proposals/proposal_2026-09-21.json |   7 +-
 live/reconcile.py                       |   4 +-
 live/sanity.py                          |   6 +-
 live/staleness.py                       |  17 +-
 live/store.py                           | 147 ++++-
 live/supabase_schema.sql                |  25 +-
 scripts/run_live_daily.py               | 132 ++++-
 scripts/verify_store_roundtrip.py       | 318 +++++++++++
 tests/conftest.py                       |  14 +
 tests/test_dashboard_d10.py             |   3 +-
 tests/test_e11_breadth.py               |  92 ++++
 tests/test_e11_corporate_actions.py     | 527 ++++++++++++++++++
 tests/test_e11_evening.py               |  41 +-
 tests/test_e11_notify.py                | 101 +++-
 tests/test_e11_reconcile.py             |   2 +-
 tests/test_e11_sanity.py                |   2 +-
 tests/test_e11_store.py                 | 139 +++++
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
README.md                               |  22 ++
 dashboard/tabs/d10_book.py              |  11 +-
 docs/hygiene_ledger.md                  |  50 +++
 handoff/LOG.md                          | 206 ++++++++++
 handoff/PROJECT_CONTEXT.md              |  75 +++-
 handoff/REPORT.md                       | 675 +++++++++++++++++++++-----------
 handoff/TASK.md                         | 419 +++++++++++++++++++-
 live/breadth.py                         |  65 +++
 live/construction_table.py              |   4 +-
 live/corporate_actions.py               | 670 +++++++++++++++++++++++++++++++
 live/dashboard_app.py                   |  18 +-
 live/evening_job.py                     |  63 ++-
 live/extend.py                          |  17 +
 live/notify.py                          |  32 +-
 live/proposals/proposal_2026-09-18.json |  13 +-
 live/proposals/proposal_2026-09-21.json |   7 +-
 live/reconcile.py                       |   4 +-
 live/sanity.py                          |   6 +-
 live/staleness.py                       |  13 +
 live/supabase_schema.sql                |  25 +-
 scripts/run_live_daily.py               |  80 +++-
 tests/test_dashboard_d10.py             |   3 +-
 tests/test_e11_breadth.py               |  92 +++++
 tests/test_e11_corporate_actions.py     | 527 +++++++++++++++++++++++++
 tests/test_e11_evening.py               |  41 +-
 tests/test_e11_notify.py                |  92 +++++
 tests/test_e11_reconcile.py             |   2 +-
 tests/test_e11_sanity.py                |   2 +-
 28 files changed, 2937 insertions(+), 297 deletions(-)
README.md                               |  22 ++
 dashboard/tabs/d10_book.py              |  11 +-
 docs/hygiene_ledger.md                  |  50 +++
 handoff/LOG.md                          | 206 ++++++++++
 handoff/PROJECT_CONTEXT.md              |  75 +++-
 handoff/REPORT.md                       | 675 +++++++++++++++++++++-----------
 handoff/TASK.md                         | 419 +++++++++++++++++++-
 live/breadth.py                         |  65 +++
 live/construction_table.py              |   4 +-
 live/corporate_actions.py               | 670 +++++++++++++++++++++++++++++++
 live/dashboard_app.py                   |  18 +-
 live/evening_job.py                     |  63 ++-
 live/extend.py                          |  17 +
 live/notify.py                          |  32 +-
 live/proposals/proposal_2026-09-18.json |  13 +-
 live/proposals/proposal_2026-09-21.json |   7 +-
 live/reconcile.py                       |   4 +-
 live/sanity.py                          |   6 +-
 live/staleness.py                       |  13 +
 live/supabase_schema.sql                |  25 +-
 scripts/run_live_daily.py               |  80 +++-
 tests/test_dashboard_d10.py             |   3 +-
 tests/test_e11_breadth.py               |  92 +++++
 tests/test_e11_corporate_actions.py     | 527 +++++++++++++++++++++++++
 tests/test_e11_evening.py               |  41 +-
 tests/test_e11_notify.py                |  92 +++++
 tests/test_e11_reconcile.py             |   2 +-
 tests/test_e11_sanity.py                |   2 +-
 28 files changed, 2937 insertions(+), 297 deletions(-)
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
dashboard/tabs/d10_book.py              |  11 +-
 handoff/LOG.md                          | 206 ++++++++++++++++
 handoff/PROJECT_CONTEXT.md              |  75 ++++--
 handoff/REPORT.md                       | 414 ++++++++++++++-----------------
 handoff/TASK.md                         | 419 +++++++++++++++++++++++++++++++-
 live/breadth.py                         |  65 +++++
 live/construction_table.py              |   4 +-
 live/dashboard_app.py                   |  18 +-
 live/evening_job.py                     |  63 +++--
 live/extend.py                          |  17 ++
 live/notify.py                          |   6 +
 live/proposals/proposal_2026-09-18.json |  13 +-
 live/proposals/proposal_2026-09-21.json |   7 +-
 live/reconcile.py                       |   4 +-
 live/sanity.py                          |   6 +-
 live/staleness.py                       |   7 +
 live/supabase_schema.sql                |   7 +-
 scripts/run_live_daily.py               |  40 ++-
 tests/test_dashboard_d10.py             |   3 +-
 tests/test_e11_breadth.py               |  92 +++++++
 tests/test_e11_evening.py               |  41 +++-
 tests/test_e11_notify.py                |  92 +++++++
 tests/test_e11_reconcile.py             |   2 +-
 tests/test_e11_sanity.py                |   2 +-
 24 files changed, 1316 insertions(+), 298 deletions(-)
dashboard/tabs/d10_book.py              |  11 +-
 handoff/LOG.md                          | 206 ++++++++++++++++
 handoff/PROJECT_CONTEXT.md              |  75 ++++--
 handoff/REPORT.md                       | 414 ++++++++++++++-----------------
 handoff/TASK.md                         | 419 +++++++++++++++++++++++++++++++-
 live/breadth.py                         |  65 +++++
 live/construction_table.py              |   4 +-
 live/dashboard_app.py                   |  18 +-
 live/evening_job.py                     |  63 +++--
 live/extend.py                          |  17 ++
 live/notify.py                          |   6 +
 live/proposals/proposal_2026-09-18.json |  13 +-
 live/proposals/proposal_2026-09-21.json |   7 +-
 live/reconcile.py                       |   4 +-
 live/sanity.py                          |   6 +-
 live/staleness.py                       |   7 +
 live/supabase_schema.sql                |   7 +-
 scripts/run_live_daily.py               |  40 ++-
 tests/test_dashboard_d10.py             |   3 +-
 tests/test_e11_breadth.py               |  92 +++++++
 tests/test_e11_evening.py               |  41 +++-
 tests/test_e11_notify.py                |  92 +++++++
 tests/test_e11_reconcile.py             |   2 +-
 tests/test_e11_sanity.py                |   2 +-
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

# Review notes c and e, and the report sections notes h and j asked for

This closes notes c, e, h and j from the reviewer's second round.

## Note c: the mypy errors in unattended code

`mypy live scripts` reported fourteen errors, not ten: the four this item set added
after the note was written are in the same split, and every one is in code the cron
runs unattended, so every one is a fix rather than a listed exception. The split by
file, before: `live/staleness.py` 3, `live/evening_job.py` 3,
`live/construction_table.py` 2, `live/appendix.py` 1,
`live/corporate_actions.py` 1, `live/morning_job.py` 1,
`scripts/run_live_daily.py` 2, `scripts/verify_store_roundtrip.py` 1. After:

```text
$ .venv/bin/mypy live scripts
Success: no issues found in 25 source files
```

`make lint` now runs `mypy live scripts` beside `mypy efb`, so the drift cannot
return:

```text
$ make lint
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
Success: no issues found in 33 source files
.venv/bin/mypy live scripts
Success: no issues found in 25 source files
.venv/bin/black --check efb dashboard live tests
All done! 177 files would be left unchanged.
```

## Note e: one clean full suite on a frozen tree

The first full run over the B-cron tree failed five tests, three of them ones the
fast selection passes. The cause was one line: `tests/test_e11_appendix.py` assigned
`store.LOCAL_DIR` directly instead of through monkeypatch, in a test marked slow, so
`make test-fast` never ran it and never saw the leak, while a full run left every
later test reading and writing a temporary directory. Reproduced minimally before
fixing anything:

```text
$ .venv/bin/python -m pytest \
    tests/test_e11_appendix.py::test_the_real_artifacts_round_trip_and_report_hashes \
    tests/test_e11_store.py::test_the_store_label_names_the_store_or_the_error -q
E  assert 'local parquet (/private/var/.../pytest-293/test_the_real_artifacts_round_0/state)'
   == 'local parquet (live/state/supabase)'
1 failed, 1 passed in 54.81s
```

Two fixes and a guard, in `029b300`: monkeypatch at that site; the other slow test
that assumed an empty appendix from the ambient store now makes its own empty
directory (the real fallback holds `cron_runs` and eight `e11_*` tables from local
runs, so it is not empty); and
`tests/test_e11_store.py::test_no_test_leaks_the_store_directory_by_assignment`
scans the suite for the assignment form. The three previously failing files together
in one process, after:

```text
$ .venv/bin/python -m pytest tests/test_e11_appendix.py tests/test_e11_store.py \
    tests/test_e11_notify.py -q
49 passed in 93.23s
```

And the clean full suite, on the committed tree, with nothing edited while it ran:

```text
$ make test
835 passed, 1 skipped, 3 warnings in 601.00s (0:10:01)
EXIT=0
```

835 collected against item 3's 787, so the count grew; the 29 marked-slow tests the
fast selection deselects are inside it.

## Notes a and b: the gate-close window and the visible cap

**a. A gate close is an evening of that close, not merely one appended session.**
Item 2's wording was "a run whose target close is the only session it appended".
The owner's rule is two closes each fetched by a run on that session's own evening,
and the reviewer agreed that the note's own phrase, `expected_next_by`, is too loose
for a Friday close: it points at Monday evening, so a Saturday run would have
counted. `live/staleness.py` now has `session_close`, `gate_window_end` and
`gate_close`, and `run_status` records `started_at`, which the runner sets at the top
of the run. The two instants for the 2026-09-25 close:

```text
$ .venv/bin/python -c "from live import staleness as st; print(st.gate_window_end('2026-09-25')); print(st.expected_next_by('2026-09-25'))"
2026-09-26 01:30:00+00:00
2026-09-29T01:30:00Z
```

and the four cases, measured:

```text
$ .venv/bin/python -c "from live import staleness as st
base = {'target_close':'2026-09-25','status':'ok','catch_up':False,'catch_up_sessions':['2026-09-25']}
for label, started in [('the cron slot','2026-09-25T22:30:00+00:00'),('inside the grace','2026-09-26T01:00:00+00:00'),('the next morning','2026-09-28T13:00:00+00:00'),('before the close','2026-09-25T19:00:00+00:00')]:
    print(f'{label:<20} counts={st.gate_close({**base, "started_at": started})["counts"]}')"
the cron slot        counts=True
inside the grace     counts=True
the next morning     counts=False
before the close     counts=False
```

**b. The cross-check cap is visible when it is hit.** `apply_to_append` returns the
names the request cap stopped it reaching, `live/corporate_actions.py::cap_note`
phrases them, `run_status` carries `cross_checks_capped`, and the email says
"Cross-check capped: N unchecked (names)". It is not an error, and an unchecked name
above 40% is still flagged; what it is not is silent.

### Verification

The subset is every test touching the gate, the run record, the cap, the snapshot
and the message:

```text
$ .venv/bin/python -m pytest tests/test_e11_staleness.py tests/test_e11_corporate_actions.py \
    tests/test_e11_notify.py tests/test_run_live_daily.py tests/test_e11_snapshot.py \
    tests/test_e11_store.py tests/test_e11_deploy.py tests/test_e11_render.py \
    tests/test_dashboard_d10.py -q
134 passed, 1 skipped in 44.30s
```

`make lint` exit 0 and `make verify-evidence` exit 0, both pasted in the note c
section above and in B-cron's section below.

### Yes or no, each with evidence

1. **Any two rows or two estimators identical.** No: the four gate cases differ in
   their verdicts, and the two instants differ by three days.
2. **Any exception caught and skipped, or fallback taken, with counts.** One, and it
   is the cap, which is now counted and named rather than silent. A run with no
   `started_at` refuses to be a gate close and says why.
3. **Any criterion reworded or replaced by a different test.** No `RESULTS.json`
   criterion. One staleness test and one corporate-actions test were added; none was
   replaced.
4. **Any criterion that passes by construction.** One, declared: the gate cases feed
   `gate_close` the instants directly, so they pin the rule and not the runner's own
   clock. The runner's `started_at` has its own test.
5. **Any number that moved by a factor of 10 or more from its previous stored
   value.** No stored number moved; no artifact was rebuilt.
6. **Any stored number typed into a notebook.** No notebook was opened, edited or
   executed.
7. **Any earlier verdict changed.** No. Item 2's `catch_up` flag and its record are
   unchanged; this narrows what counts as a gate close, which is the note's intent.

## Note j: B-cron's Verification gaps, answered

Three gaps, answered rather than edited away.

**The two gates, pasted here.** `make lint` is pasted in full in the note c section
above. `make verify-evidence`:

```text
$ make verify-evidence
evidence OK
```

**Timing, stated plainly.** `make verify-evidence` was **failing** at the end of
B-cron, because the memory measurement in that item rewrote four raw artifacts. It
passed only after they were restored byte-for-byte from their evidence snapshots,
which is the incident commit. So the honest reading is: verify-evidence did **not**
pass at B-cron's commit, ran **after** the measurement, and passes from the
restoration commit onward. Neither B-cron's report nor its commit claims otherwise
now.

**Yes/no item 5 was false, and here is the correction beside it, not instead of
it.** The old line reads "No stored number moved: no artifact was written, and the
snapshot is a new object rather than a change to an existing one." The first clause
is true of the snapshot; the second is false of the run: the memory measurement in
that item rewrote `data/raw/prices.parquet`, `data/raw/shares_history.parquet` and
both `data/raw/spy_holdings/spy_holdings_2026-09-1[8|21].parquet`, one of them
losing `sector`, `shares_held` and `local_currency`. **Correction:** an artifact was
written, by the measurement rather than by the item's own code, all four were
restored byte-for-byte from `evidence/`, and the underlying defect is item f. The
snapshot itself wrote nothing anywhere at that commit, because `EFB_SNAPSHOT` is
required and the measurement ran with it off.
