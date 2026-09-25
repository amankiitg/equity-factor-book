# Sprint E11, Part 3b: every run notifies the owner

**What this part does.** `live/notify.py` composes one message per run and
delivers it to a Slack incoming webhook, `scripts/run_live_daily.py` sends it
after the proposal and the orders, and the run's `run_status` row records
whether the message went out. A run whose message was not delivered exits
nonzero, so Render marks it failed, and the dashboard shows the notification
state as a failure of its own. Silence now means something: one message per
session means the absence of the evening message is the alarm.

## The message, and the three fields

Composed from the stored 2026-09-21 proposal and its execution log, so the
numbers are real rather than typed:

```text
EFB live book 2026-09-22: ok, the run completed
Orders: dry run: 27 orders proposed, $273,359 gross, none sent
Staleness: worst input prices, 0 sessions behind.
```

The same composer on the real gate result from Part 3, which stops a run today:

```text
EFB live book 2026-09-24: stale_stopped, the run refused to price a book
Orders: none. The run stopped on staleness before sizing, so no book was priced
and no order was built.
Staleness: worst input prices, 3 sessions behind.
Failing inputs: prices 3 sessions behind; descriptors 3 sessions behind;
factor_returns 3 sessions behind; specific_returns 3 sessions behind;
factor_cov 3 sessions behind; specific_var 3 sessions behind; universe
3 sessions behind; shares 2 sessions behind; sectors 2 sessions behind.
```

| field | what it says | when the run stopped |
| --- | --- | --- |
| 1. Did it run? | `EFB live book <target close>: ok, the run completed` | `stale_stopped, the run refused to price a book` or `error, the run failed` |
| 2. Did the proposal produce orders? | `Orders: dry run: N orders proposed, $X gross, none sent` | `Orders: none.` plus why: stopped before sizing, or failed before sizing |
| 3. Staleness | `Staleness: worst input <name>, N sessions behind.` | the same, followed by `Failing inputs:` with every failing input |

The first line is the status and the target close, which is what a preview
shows. The second line never reads as "0 orders": it names the count it did
propose, says none were sent, and only claims there are no orders when the run
stopped before building any. That distinction is asserted in a test, and it is
why the dry-run wording is generated rather than shortened.

The live (non-dry-run) form is `Orders: N orders sent, $X gross`, and the
guards' rejections are already in the morning summary for the same line when
the clock starts; `dry_run` stays `true` and the owner flips it.

## When the message should arrive

The cron fires at `30 22 * * 1-5` UTC, which is 18:30 EDT / 17:30 EST, after
the 16:00 ET close. The measured parts of the run are the hydration (2.93s on
the full dataset, Part 2) and the persist (0.71s), and the extension in between
is network-bound. **The message should arrive by 22:45 UTC (18:45 EDT) on every
weekday the cron fires, and if it has not arrived by then the owner should treat
the evening as missing.** That estimate is not measured end to end, because the
extension needs the live vendors and no full run has happened; the report says
so rather than quoting a number it cannot show.

**A run that never starts cannot send anything**, which is precisely why the
message cannot be the only alarm. See the heartbeat offer below.

## The channel, and the credential

**Slack first, over `urllib` from the standard library**, so the cron needs no
new package to send: one POST of `{"text": <message>}` with a ten second
timeout, and anything but a 2xx is a failed send. **Email sits behind the same
interface and is not built.** A channel is a function from a message to a side
effect, so adding SMTP later is one function plus one set of owner credentials
(host, port, user, password, recipient) and nothing else changes. I did not
build it because it needs a provider choice and a credential the owner has not
placed, and inventing one would put a secret in a place the owner did not choose.

**The webhook URL is a credential, and it is handled as one:**

- `EFB_NOTIFY_SLACK_WEBHOOK_URL`, empty in `.env.example` with the comment that
  it belongs to the cron;
- set in `render.yaml` on the **cron service only**, `sync: false`, so the value
  lives in the Render dashboard and never in the repository. The dashboard
  service never holds one, because it never sends;
- read from the environment at send time and never printed, logged or stored.
  The `run_status` row carries `notify_status` and `notify_failed` and a
  **scrubbed** detail; a test asserts the URL reaches neither the row nor the
  cron detail;
- **the credential check is extended**: `tests/test_e11_render.py` now lists the
  key in the env-example check, and a new test asserts the key appears on the
  cron and not on the web service, and that no hook path (`hooks.slack.com`,
  `https://hooks`) appears in `render.yaml` at all.

## The scrub

Four rules, applied to everything that leaves the process: any `scheme://...`
URL, `eyJ...` JWTs, long base64 or hex blobs, and `password=`, `secret`,
`token`, `api_key` or `access_key` followed by a value. The reason is not
hypothetical: a failed send raises with the webhook URL inside its message, and
that message is what gets recorded.

```text
$ notify.scrub("post to https://hooks.slack.com/services/T1/B2/abcdefghijklmnopqrstuvwx "
               "with password=hunter2 and db=postgresql://u:pw@host:5432/db")
post to [redacted] with [redacted] and db=[redacted]
```

A test drives the error path with an exception whose text contains a fake
Supabase connection string, and asserts the password, the host and the scheme
are gone from both the message and the stored `detail`, while the exception type
survives:

```text
EFB live book 2026-09-22: error, the run failed
Orders: none. The run failed before sizing, so no book was priced.
Staleness: no input failed the check.
Error: OperationalError: could not connect to [redacted]
```

## The record, the order of operations, and the exit code

- The message goes out **after** the proposal and the orders, never before, so a
  failed send cannot block or roll back a run that priced a book and moved no
  money.
- `notify_status` is `sent`, `failed` or `skipped` (no channel configured), and
  `notify_failed` is true whenever the status is not `sent`. The exit code is
  nonzero in exactly those cases, and for a stale stop or an error regardless.
- A failed send appends its scrubbed reason to the `cron_runs` detail. A
  *skipped* send is logged as a warning and recorded on the row, but does not
  add noise to the cron's own line.
- **The dashboard states the notification failure too.** `run_state` gained
  `notify_failed` and `notify_not_configured` states, so a run that could not
  tell the owner is not shown as a clean run: the banner says the run completed,
  that the owner was not told, and, for the unconfigured case, names
  `EFB_NOTIFY_SLACK_WEBHOOK_URL` as the thing to set.
- **The whole job is wrapped.** An exception anywhere, including before the
  gate, sends `error` with the exception type and a scrubbed one-line reason,
  writes the `error` row, and exits nonzero. The reason is scrubbed once, at the
  point it is captured, so the same clean text goes to the message, the row and
  the log.

## The heartbeat, offered and not built

**Option: healthchecks.io, the free "dead man's switch" service.** The cron
pings one URL after it notifies, and the service alerts the owner if a ping does
not arrive by the time it expects.

- What it needs from the owner: a free account, one check with a period of one
  day and a grace period of about an hour (the cron fires once each weekday, so
  the check must not alert on weekends: either a weekly schedule or a
  documented Friday silence), and the alert channel the owner prefers, which can
  be the same Slack webhook. One more Render variable, a ping URL, on the cron.
- What it costs: nothing at this volume. The free tier is built for exactly one
  check per day and alerts by email or webhook.
- Why not built: the task asks for the offer, and building it would mean adding
  a variable the owner has not placed and a network call whose absence is
  indistinguishable from a Render outage. The point of an outside check is that
  it does not share Render's failure modes, so it belongs outside this process.

## What could not be verified

**No real message was delivered.** There is no Slack webhook on this machine and
none should be committed, so the send path is exercised with the real composer
and the real `send` against stand-in posters: one that records the payload, one
that raises with the URL inside the message, and no poster at all. The HTTP path
itself (`notify.post`) is eleven lines of `urllib.request` and its behaviour
against the live webhook is unproved until the owner's test notification, which
is a deploy step in Part 4 and is the confirmation the task asks for.

**The Postgres write path, again.** `run_status.notify_status` and
`notify_failed` are written through the same store as every other live table, and
that path is still unreachable from here (no `EFB_SUPABASE_DB_URL`, no local
server, no docker). The psycopg text-typing question from Part 3's report stands
and applies to `notify_failed boolean` as much as to anything else.

## Tests, 11 in `tests/test_e11_notify.py`

1. the three fields in order, for a clean dry run, and `"0 orders"` absent;
2. a live run says orders were sent and does not say "dry run";
3. a stale stop names every failing input, including one with no date at all;
4. an error message names the exception type and scrubs the reason;
5. `scrub` removes the webhook, a JWT, a long key and `password=`/`api_key:`;
6. no channel configured is `skipped`, not a crash;
7. a refused send records `failed` with the URL redacted;
8. a clean run through `main()` sends once, stores `sent`, `n_orders` 152 and
   `gross_notional` 2,014,000 from the morning summary, and exits 0;
9. a refused send through `main()` exits 1, records `notify_failed`, keeps the
   cron status as the run's own, and the dashboard shows `notify_failed`;
10. no channel through `main()` exits 1 and the dashboard shows
    `notify_not_configured` with the variable named;
11. an unexpected exception through `main()` sends one `error` message with the
    connection string scrubbed, stores the scrubbed reason, and leaves no
    proposal and no order row.

## Verification

Per step, the selection is every test touching what changed, and the full suite
is not required at this step: no `efb/` module changed, no artifact was rebuilt,
the clock is not touched, and this is not the state that sets the task `done`.

```text
$ make lint
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
Success: no issues found in 33 source files
.venv/bin/black --check efb dashboard live tests
All done! ... 169 files would be left unchanged.

$ .venv/bin/python -m pytest tests/test_e11_notify.py tests/test_e11_staleness.py \
    tests/test_e11_render.py tests/test_run_live_daily.py tests/test_e11_store.py \
    tests/test_e11_execution.py tests/test_e11_guards.py -q --tb=short
75 passed, 1 skipped in 2.85s

$ make verify-evidence
evidence OK
```

The full suite at Part 3's commit was 751 passed, 1 skipped (below, pasted).
Part 5 ends with the run that carries this part, Part 4 and Part 5 together, and
that is the one the `done` state rests on.

### Headline numbers, file and key

| number | file and key |
| --- | --- |
| the three fields, in order | `live/notify.py::compose`, `STATUS_LABELS` |
| the dry-run wording | `live/notify.py::compose`, the `status == "ok"` branch |
| four scrub rules | `live/notify.py::_SCRUBS` |
| `sent` / `failed` / `skipped` | `live/notify.py::send` |
| the cron only holds the webhook | `render.yaml`, the second service's `envVars`; asserted by `tests/test_e11_render.py::test_render_yaml_gives_the_webhook_to_the_cron_only` |
| the empty key in the example | `.env.example`, last line |
| `notify_status`, `notify_failed`, `n_orders`, `gross_notional` columns | `live/supabase_schema.sql`, `efb.run_status` |
| exit nonzero when the message was not delivered | `scripts/run_live_daily.py::finish_run`, the last three lines |
| the two dashboard states | `live/staleness.py::LABELS`, `notify_failed` and `notify_not_configured` |
| 11 tests | `tests/test_e11_notify.py` |
| the full run at Part 3 | `751 passed, 1 skipped, 3 warnings in 584.10s`, Part 3's report |

### git diff --stat from `base_commit` (dd41d9b)

This part's own files, from Part 3's commit `51d1bce`, with
`git add -N live/notify.py tests/test_e11_notify.py` first so the new files
appear:

```text
$ git diff --stat 51d1bce -- handoff/REPORT.md live/notify.py live/staleness.py \
    scripts/run_live_daily.py tests/test_e11_notify.py tests/test_e11_render.py \
    render.yaml .env.example
 .env.example              |   6 +
 handoff/REPORT.md         | 636 +++++++++++++++++++---------------------------
 live/notify.py            | 237 +++++++++++++++++
 live/staleness.py         |  16 +-
 render.yaml               |   7 +-
 scripts/run_live_daily.py | 116 +++++++--
 tests/test_e11_notify.py  | 334 ++++++++++++++++++++++++
 tests/test_e11_render.py  |  13 +
 8 files changed, 971 insertions(+), 394 deletions(-)
```

From the revision's `base_commit` (dd41d9b), which also carries Parts 2 and 3 and
the reviewer's `ef67024`:

```text
$ git diff --stat dd41d9b
 ...
 20 files changed, 2936 insertions(+), 346 deletions(-)
```

Nothing else in the repository changed: no research artifact, no construction
table, no proposal, no notebook.

### Yes or no, each with evidence

1. **Any two rows or two estimators identical.** No. One `run_status` row per
   target close; the new tests write one row each in their own temporary store.
2. **Any exception caught and skipped, or fallback taken, with counts.** Yes,
   three, none of them silent. (a) `send` catches everything around the POST and
   turns it into `failed` with a scrubbed reason, because a failed send must not
   mask the run: it is recorded on the row, in the cron detail and in the exit
   code, and the test that raises inside the poster asserts all three. (b) The
   cron's own `except Exception`, which now sends `error` rather than only
   recording it. (c) The store's local parquet fallback, exercised by every new
   test because `EFB_SUPABASE_DB_URL` is unset. No other exception is caught.
3. **Any criterion reworded or replaced by a different test.** No stored
   criterion was touched. Two existing tests were **edited deliberately**, both
   in `tests/test_e11_render.py`'s credential check, to add the webhook key to
   the env-example list and to assert the cron-only placement. Neither weakens
   what was asserted before; the file's other assertions are unchanged.
4. **Any criterion that passes by construction.** Two, declared. (a) Test 8's
   `n_orders` and `gross_notional` come from a patched morning summary, so the
   test proves the message and the row carry what the morning returned, not that
   `run_morning` returns those numbers. (b) The dashboard states are asserted
   through `run_state`, the same function the page calls, so wording and test
   cannot drift independently; the element the page renders is asserted in
   Part 3's dashboard tests.
5. **Any number that moved by a factor of 10 or more from its previous stored
   value.** No. No stored number moved. The notification adds columns and
   message text; no artifact, proposal or registry entry was rewritten.
6. **Any stored number typed into a notebook.** No notebook was opened, edited
   or executed.
7. **Any earlier verdict changed.** No. Part 3's stop behaviour is unchanged:
   the gate, the row and the exit code are the same, and the message is added
   around them.

### Anything decided that the reviewer might disagree with

**A run that cannot deliver its message exits nonzero, even when the book was
built.** The task says a failed send is recorded and exits nonzero; I applied
that to the case where no channel is configured too, because a cron that looks
green while nothing is sent is the failure the whole part exists to prevent. The
alternative reading is to exit 0 when the channel is simply unset, treating it
as a deployment gap rather than a run failure. I chose the strict one, and the
dashboard's `notify_not_configured` state names the variable so the owner cannot
miss what to fix.

**The skipped case does not append to the cron detail.** A failed send does,
because that is news about this run; an unconfigured channel would repeat the
same line every evening, and the row and the dashboard banner carry it. If the
reviewer wants the cron line to say it every time, it is a two-line change.

**The email channel is offered, not built.** The task allows this ("if it costs
little"), and what it costs is a provider choice and a credential the owner has
not placed. The interface is a function, so it is cheap the day the owner wants
it.
