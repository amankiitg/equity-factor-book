task_id: e11-pre-deploy
status: in_progress
base_commit: 4048b97

## Reviewer notes on B-cron, notes a, b, d and the raw-artifact rewrite (2026-09-25, mid-task; the task continues)

**B-cron is accepted in design.** These are accepted: the web service, the
`efb_reader` role and `delete` all go, with one grep as the evidence. The switch
table, the shared schema and NaN as `null` in the document and its text are
accepted. The 4 GB plan is accepted too: 3.5x over the measured peak. Keep
`efb_archiver` for item 6. **Note a's stricter window is agreed:**
`expected_next_by` for a Friday close is Monday evening, so my wording would
have let a Saturday run count as that close's gate evening. **The rewrite
incident was handled well.** The artifacts were restored from their snapshots,
the defect was named and left for its own commit, and the mistake was stated
plainly. Corrections follow. Items f and g block the deploy, and the rest go
into the remaining work.

f. **The raw-artifact rewrite is a pre-deploy item. Do it next, after c and
   e.** The gate evenings run the append path this defect lives in, and the
   full-job memory measurement (item k) cannot run locally until it is fixed.
   Acceptance:
   - a test hashes every file under `data/raw/` before and after
     `evening_job.build_proposal(store=False)` and asserts that none changed;
   - a test asserts that archiving a SPY file never writes fewer columns than
     the file it replaces;
   - the report names every write the read path made, with where it came from.
g. **A stopped run's "last proposal on disk" is the deploy image on Render.**
   The cron's disk is ephemeral, so on a stale evening the page would show the
   last proposal committed to git, 09-21, as the book the owner holds. Read the
   last proposal from the store instead, or from the previous `latest.json` in
   R2, and say which. The snapshot also carries that proposal's own close as
   `book_as_of`, so the page can never show an old book without its date. Add
   a test where the store's last proposal is newer than anything on disk.
   Keeping the previous book on a stopped run is otherwise agreed.
h. **Notes a and b have no section in `REPORT.md`.** The commit message is the
   only record of them, and rule 20 applies to the report. Append a section
   with a Verification block: the subset selection command and its pasted
   output (the message says 133 passed, 1 skipped), `make lint`, the window
   instants for the 09-25 close, and the yes/no list.
i. **Note d needs redoing.** Three problems:
   - every filled block is pasted twice;
   - item 4's block ends with a stale `28 files changed, 2673 insertions(+),
     300 deletions(-)`, which contradicts the `2937 / 297` above it;
   - the command shown, `git diff --stat 4048b97`, does not produce those
     outputs today. B-cron's own section shows it gives 41 files.

   Show the command that was actually run, which names the item's commit as
   the end point (`git diff --stat 4048b97 <item commit>`), once per block. B-cron's own
   base-commit stat is elided to one line: the same defect, one section later.
   Paste it in full.
j. **B-cron's Verification has three gaps:**
   - it says `make lint` and `make verify-evidence` passed "run above", but
     neither is pasted in that section;
   - its yes/no item 5 says "no artifact was written", which is false: the
     memory measurement in this item rewrote four raw artifacts;
   - the verify-evidence claim has to be placed in time against the
     measurement.

   Correct item 5 in a new line. Do not edit the old one; append the
   correction beside it. Paste the two outputs, and say whether
   verify-evidence ran before or after the measurement.
k. **The memory measurement is of hydration plus build, not the full evening
   job.** The task asked for the full job. 3.5x covers a lot, so the plan
   stands. Once f lands, measure the full dry-run job locally (fetch, append,
   cross-check, build, snapshot off) under `/usr/bin/time -l` and paste it. The
   deploy list gains one step: after the first Render dry run, the owner reads
   peak memory from Render's metrics before the first gate evening counts.
l. **SigV4 is hand-rolled and has no known-answer test.** The upload tests
   check that the header exists and carries the payload hash, not that the
   signature is right. Add a test against a fixed vector: AWS's published
   SigV4 example, or one computed once offline with `botocore` and committed
   as literals. Otherwise the first real R2 put is the first check of the
   signing code.
m. **The snapshot is written before the email, but it lists notify state.**
   Say what the snapshot's notify field holds at write time. Test that a
   failed upload with `on` still sends the email, and that the email names the
   upload failure.
n. **The incident report has two loose ends:**
   - the ledger says four artifacts were restored, but the pasted output shows
     three, and `spy_holdings_2026-09-21.parquet` is missing. Paste its restore
     line, or a `make verify-evidence` output that lists it;
   - `git add -A` does not stage gitignored files, so name the tracked file
     that nearly rode along (for example `data/VERSION.json`), or correct the
     sentence.

**Done from the smaller items:** the writer's `delete` was dropped in B-cron.
**Still open, in this order:** c, e, then f and the other notes above, item
5, the remaining smaller items, the owner's full deploy list (with k's Render
memory step), and item 6 within a month of the deploy. B-web runs in parallel.

---

## Reviewer notes on items 1 to 4b and A (2026-09-25, mid-task; the task continues)

Items 1, 2, 3, 4 (with 4a), 4b and A are **accepted**. Each part's report was
appended this time rather than overwritten; keep doing that. APH did no
damage: its four missing closes made the 09-04 return NaN, so there was a
hole, not a fake -48%, and nothing needed repair. Five notes to fold into
the remaining work. None blocks it.

a. **The gate-close definition needs the owner's full wording.** Item 2
   wrote: "a run whose target close is the only session it appended". The
   owner's rule is two closes **each fetched by a run on that session's own
   evening**. A run delayed to the next morning can still append exactly one
   session. Add the condition that the run started after that session's close
   and before `expected_next_by`, record `started_at` in `run_status`, and
   test a late one-session run that is not a gate close.
b. **The cross-check cap is silent when hit.** `max_cross_checks` stops at 30
   large movers a session. On a day with more, some go unchecked, and a split
   the vendor does not flag among them would pass as a flagged-but-unblocked
   move. Record `cross_checks_capped` and the unchecked count in `run_status`,
   and put it in the email ("cross-check capped: N unchecked"). It is not an
   error; it must never be invisible.
c. **`mypy live scripts` reports 10 errors.** Earlier reports pasted
   `mypy live` as clean on 15 files. Split the 10 by directory, fix those in
   code that runs unattended (`live/` and `scripts/run_live_daily.py`), list
   any you leave, and add `mypy live scripts` to `make lint` so it cannot
   drift again.
d. **Item 4b's section still carries `PLACEHOLDER_DIFF_TREE`.** Fill it.
e. **A full suite on a frozen tree before `done`.** The last clean full run was
   item 3's 786. Items 4, 4b and A were verified on the fast path, and the one
   full run over them is void, as the report says. Rule 21 needs one clean full
   run collecting at least 817 before `done`.

Still open, in the order below: **B-cron** (the snapshot writer, the memory
measurement, no web service, `efb_reader` dropped), item 5 (E5's
`evaluated_at` and the 0.000031 explanation), the smaller items, the owner's
full deploy list, and item 6 retention within a month of the deploy. B-web
runs in parallel.

---

## Owner decisions, 2026-09-25 (later): email by Resend, and D10 moves to Cloudflare

Everything in the previous round is accepted: E11-F17 and item 4b, the widened
split rule with the reviewer's three additions, the 40% flag-not-block rule,
and the retention design with dated archive files and a local-only archive
command. Two changes are folded in below: **A** (email through Resend) and
**B** (Render runs only the cron, and the live book monitor becomes a React
app on Cloudflare).

**The order of work:**
1. **Before the cron deploys to Render, in dry run:** items 1, 2, 3, 4, 4b,
   A, and B-cron.
2. **The two gate evenings.** Email is the owner's monitor for both.
3. **In parallel, not blocking the gate:** B-web, the React page.
4. **The flip.** The owner flips `dry_run` only after the Cloudflare page is up
   and showing a real proposal from a real snapshot.

### A. Notifications by email through Resend, not Slack

**Read how credit-trading-lab sends through Resend and copy that pattern.**
Start at
`/Users/amankesarwani/PycharmProjects/credit-trading-lab/render.yaml` and
`tests/test_alerts.py`, and follow them to the module. Do not open its `.env`.

- **The key:** `EFB_RESEND_API_KEY`. It is EFB's own key under the same Resend
  account, with sending access only, so it cannot cross with the credit lab's.
  The owner places it in `.env` and on Render. It is never printed, logged or
  committed. **Add the Resend key shape (`re_...`) to the scrub patterns**, and
  test it.
- **The addresses:** sender and recipient go in `EFB_NOTIFY_EMAIL_FROM` and
  `EFB_NOTIFY_EMAIL_TO`, as Render variables (`sync: false`), never in
  `render.yaml`. Use whatever sending domain credit-trading-lab uses, and say
  which. If it is `resend.dev`, say what that restricts.
- **The subject carries the status**, readable from the inbox without opening
  the email. The owner's example:
  `EFB ok 2026-09-25 | 150 proposed, none sent | stale 0`.
  - A stale stop reads `EFB STALE <close> | none proposed | stale 3 (prices)`.
  - An error reads `EFB ERROR <close> | none proposed | <ExceptionType>`.
  - A catch-up run adds `(catch-up N)` after the status.
  - A split or an unexplained move above 40% appends `| split APH 2:1` or
    `| flag 1`.
- **The body's first line names the store**, for example "store:
  postgres/efb". The three fields follow as before.
- **Everything already specified carries over unchanged:**
  - one email on every run, clean ones included;
  - secrets scrubbed from error text;
  - a failed or unconfigured send fails the run;
  - the send happens after the proposal and the orders.
- **Remove Slack:** `EFB_NOTIFY_SLACK_WEBHOOK_URL` leaves `render.yaml` and
  `.env.example`. Keep the channel interface, and update the credential tests.
- **The first test email must land in the inbox, not spam.** The owner
  confirms it in the deploy steps, and sets a filter or label so the evening
  email is hard to overlook.
- **The heartbeat for a job that never starts is the owner's to add.** Keep
  the healthchecks.io note in the deploy steps as the owner's option.

### B-cron. Render runs only the cron, and the cron writes the snapshot

1. **Drop the Render web service** from `render.yaml`, the deploy steps and
   the tests. With no web service, **the `efb_reader` role is not needed**.
   Remove it from `live/supabase_roles.sql`: one fewer credential. Keep
   `live/dashboard_app.py` runnable locally until the Cloudflare page is
   proven, then propose deleting it in a later commit.
2. **The evening cron writes one JSON snapshot** with everything D10 shows,
   and uploads it to Cloudflare R2. It writes `latest.json` plus a dated
   `snapshots/<close>.json`.
   - Single-object puts only.
   - The credentials, cron only: `EFB_R2_ACCOUNT_ID`, `EFB_R2_BUCKET`,
     `EFB_R2_ACCESS_KEY_ID` and `EFB_R2_SECRET_ACCESS_KEY`, from an R2 API token
     scoped to that one bucket with object read and write.
   - Add both key shapes to the scrub.
3. **The snapshot is written on every run**, including `stale_stopped` and
   `error`, so the page shows the failure. It is never skipped. It carries:
   - `schema_version`, `generated_at` (UTC), the target close and
     `run_status`, with the failing inputs, catch-up, splits, flags and store;
   - **`expected_next_by`**: the UTC time by which the next run's snapshot
     should exist. The cron computes it from the NYSE calendar (the next
     session's close plus the run slot plus a stated grace), so the browser
     needs no calendar;
   - `dry_run`;
   - the construction label **generated from the artifact's fields**;
   - the book: names, weights, trade reasons, hedge, exposures;
   - **breadth under item 3's explicit names** (`n_eff_kept` as the book's
     breadth, `n_eff_full_book` labelled as the 499-name book before the
     floor), and no unqualified `n_eff` anywhere in the schema.
4. **JSON has no NaN**, so serialize it as `null`, explicitly, with a test.
   Test also that no credential pattern appears in any snapshot.
5. **The snapshot switch.** `EFB_SNAPSHOT` is `on` or `off`, and it is
   required.
   - `off` is allowed only while `dry_run` is true. The run then records
     `snapshot: off` in `run_status` and in the email body. This lets the gate
     evenings run before the Cloudflare side exists.
   - With `on`, a failed upload fails the run, the same as a failed send.
   - With `dry_run` false, `off` is an `error`. The flip cannot happen without
     a working page.
6. **Measure the cron's peak memory before choosing a Render plan.** The owner's
   reason for leaving a Render web service was memory errors. This cron
   hydrates about 165 MB of parquet into pandas, which can take several times
   that in RAM.
   - Run the full evening job locally under `/usr/bin/time -l` (macOS) and
     report peak RSS.
   - Choose the instance with at least 2x headroom, and state the plan and its
     monthly cost.
   - If the peak is too high for a reasonable plan, stop and report with where
     the memory goes. Do not deploy into a box that will fall over on the
     first gate evening.

### B-web. The React live book monitor on Cloudflare (parallel, does not block the gate)

**Mirror nutri-track's build and deploy, not its data access.**
`/Users/amankesarwani/PycharmProjects/nutritrack-your-daily-food-guide` is
Vite plus React, deployed with `npm run deploy`, which is
`vite build && wrangler deploy`: a Cloudflare Worker serving static assets.
The owner said Pages. Follow nutri-track's actual mechanism, which supports
all of the below, and state which it is. If the owner cares about Pages
versus Workers, the owner says so. **nutri-track's browser talks to Supabase
directly** (`src/integrations/supabase/client.ts`, with a publishable key).
**EFB's must not.**
- No `@supabase/supabase-js`, no `VITE_SUPABASE_*` and no database URL in the
  app.
- A test fails the build if any appears.

1. **The browser never reaches R2 directly.** The Worker, or a Pages Function,
   reads the snapshot through an **R2 binding** and serves it on the same
   Access-protected hostname, for example `/api/snapshot`.
   - **The bucket stays private:** no `r2.dev` public URL and no custom domain
     on the bucket. A public bucket URL would bypass Access and publish
     positions.
   - An owner step confirms that public access is off.
   - A check fetches the snapshot path without an Access session and gets a
     redirect or 403.
2. **Cloudflare Access protects every hostname**: production, and preview
   deployments (preview URLs are separate hostnames). The check in 1 runs
   against both.
3. **Snapshot age leads the page.**
   - The page shows `generated_at` and the age prominently, and turns to a
     failure state when the current time is past `expected_next_by`.
   - It shows every non-`ok` `run_status` as a failure, as the Streamlit page
     does now.
   - `dry_run` is shown unmissably.
   - Tests cover a fresh `ok`, an expired snapshot, `stale_stopped`, `error`,
     and a missing snapshot.
4. **Item 3 applies here.** The page shows `n_eff_kept` as the book's breadth,
   with the full book's labelled beside it. A test checks it.
5. **The snapshot schema is shared.** Commit a JSON Schema, or TypeScript
   types generated from it, and test the Python writer's output against it,
   so the writer and the page cannot drift.
6. **Local D10** in the Streamlit research dashboard can stay as a research
   view. D0 to D9 stay local and unchanged. Only the live book monitor moves.

### The owner's full deploy list (replace Part 4's steps)

Write it as one ordered list: every object the owner creates, where, and
where each credential goes. Include:
- **Supabase:** the schema SQL, then the `efb_writer` role only (no reader
  now; `efb_archiver` comes with retention), and the test of the writer
  string.
- **Render:** the cron service or services, and each environment variable with
  its source.
- **Resend:** the key, its sending-only scope, and the test email.
- **R2:** the bucket, public access off, and the scoped token.
- **Cloudflare:** the Worker or Pages project and its R2 binding, and the
  Access application with its policy (who may sign in, how) covering the
  production and preview hostnames.
- **Local `.env`:** which of the above it holds.
- **The heartbeat:** marked as the owner's option.
- **The public-schema function limit**, as accepted.

**Which steps the gate needs:** Supabase, Render, Resend, and the round-trip
verification. **Which the flip needs:** R2, Cloudflare and Access, then a real
snapshot on the page.

---

## Six items before the owner deploys, then the gate

Parts 2 to 5 of `e11-admit-and-live-gate` are accepted, and they are strong
work: the git seed plus Postgres appendix with round-trip hashes, staleness
counted in NYSE sessions with a tested dashboard failure state, the
notification with its scrub and exit codes, deploy steps in the right order
with the role SQL as text and a rolled-back typing probe, and the book that
trades matching the confirmed book to the last digit. The APH price guard
was an unasked-for catch.

**The first deploy must prove the round trip on the real project before any
gate evening counts (owner, 2026-09-25).** Part 2's round-trip hashes ran
against the store's local **parquet** fallback, not against any Postgres. Part
2's own Verification item 2 says every new test used the fallback, and Part 3
says no Postgres server or docker was available. So no SQL path has been
exercised at all. After the first deploy, and before either gate evening
counts:
- run a verification that reads seed plus appendix **from the real `efb`
  schema** and compares every input's hash with the local artifacts at the
  same commit and session;
- check type fidelity explicitly: NaN in float columns and in `jsonb` (JSON
  has no NaN), dates, timestamps with time zones, and float precision;
- store the result in `run_status` (or a sibling table) with the hashes;
- have the report say plainly where each earlier test ran.

A gate evening counts only after this passes, and Part 6 is amended to say so.
Build the verification command now, as part of item 4b's commit.

**But the task was set `done` with Parts 6 and 7 open.** Part 6 is the gate,
which needs the owner's deploy, but its items 1 and 3 are code that must land
**before** the deploy. Part 7 was not done. Four more items came out of the
review. **The owner does not deploy until items 1, 2, 3, 4 and 4b below are
committed.**
Items 5 and 6 may follow the deploy.

**Owner, 2026-09-25:** items 1 to 4 are accepted. Item 4 is widened into a
corporate-actions rule, and item 4b is added by the reviewer.
- The size query returned **about 2 MB** for the whole shared project, far
  under the 400 MB stop.
- `EFB_SUPABASE_URL` and `EFB_SUPABASE_SECRET_KEY` are removed from `.env`.
- The public-schema function limit is accepted, and the deploy notes state it.
- Retention: keep in Postgres the window the longest model lookback needs,
  and archive older days to git.

Run them in order and commit each alone. `dry_run` stays `true`.

### 1. The universe look-ahead (Part 6 item 1, still open)

The 09-18 proposal records its universe as of 2026-09-21. Clamp the universe
to the latest SPY archive on or before the close, the way `_input_as_of`
clamps everything else. Add the shift-audit test: a proposal whose universe
file postdates its close is refused. Regenerate the 09-18 proposal and report
whether its book changed.

### 2. Catch-up sessions are labelled (Part 6 item 3, still open)

The first Render run will find the data at 2026-09-21 and extend it through
the latest close, several sessions at once. Those sessions are **catch-up**.
- `run_status` records `catch_up: true` and the sessions it caught up.
- The notification's first line says so, for example "ok (catch-up of 4
  sessions)".
- A catch-up run is never one of the gate's two closes.
- Test it.

A gate close is a run whose target close is the only session it appended.

### 3. The dashboard's `n_eff` names the wrong book (the reviewer decides: fix it)

The manifest's unqualified `n_eff` is the full 499-name book's 157.33.
`store_proposal` writes it to `proposals`, so the dashboard would show 157.33
beside a 150-name book whose breadth is 70.59. That is a number meaning more
than it says, on the page the owner will watch for two evenings.
- Stop writing an unqualified `n_eff`.
- Write `n_eff_kept` and `n_eff_full_book`, and label them on both pages as
  "the book's effective breadth" and "the full 499-name book's, before the
  floor".
- Readers of older artifacts map a legacy `n_eff` to `n_eff_full_book`, with a
  note, and never to the book's.
- Regenerate the two stored proposals.
- Add a test that the page's breadth figure equals `n_eff_kept`.

### 4. Corporate actions: measure APH's damage, then a split rule for the append (owner, widened)

**The owner's point: this is a design problem, not only a measurement.**
- E1's outlier flag is 50%, so a -48% split return is not caught.
- yfinance's adjusted close back-adjusts history on a split, while the
  pipeline is append-only.
- Those two are incompatible. Every future split either produces a fake return
  on the new day or requires restating stored rows, which the project forbids.

**4a. Measure APH.** Print APH's `adj_close` either side of the gap, the
return on 2026-09-04 in the returns panel, the specific return that day, and
`specific_var` before and after. Then report how many names have an absolute
daily return above 40% in any appended session, each with its explanation.

- **If the appendix carries the split as a return**, repair it now, before the
  deploy and before any gate evening. Re-derive the appended sessions from
  2026-09-04 onward under the rule in 4b. Record it in the hygiene ledger as a
  correction, with before-and-after hashes of each appended artifact and the
  old and new APH return beside each other.
- **Pre-2026-09-04 rows stay byte-identical.** Print the hashes.
- Nothing has traded and no gate evening has run, so this is the cheapest
  moment it will ever be.
- Record the vendor as a failing source for APH's four missing closes
  (STANDARDS rule 14).

**4b. The corporate-actions rule, in the append path.**

1. **Detect.**
   - **Primary:** the vendor's split record for the ticker (yfinance's
     `splits`).
   - **Cross-check:** refetch the last stored session's adjusted close and
     compare it with the stored value. A ratio that differs from 1 is a
     back-adjustment, and it must match the split factor.
   - **Disagreement:** a mismatch between the two, or a back-adjustment with no
     split record, **stops the run** as an `error` naming the ticker. It is
     never guessed at.
2. **Compute the new day's return with the factor**, never from the
   back-adjusted history:
   `r_t = close_t * factor / close_{t-1} - 1`, where the factor is the new
   shares per old share (2 for a 2:1 split). No stored row is touched.
3. **Record the event.** Add an appendix table,
   `efb.e11_corporate_actions`, holding ticker, effective date, factor, source
   and the cross-check ratio. Every run stores it in `run_status`, and the
   notification names it: "split: APH 2:1 applied".
4. **Consumers that read price levels across the seam**, such as momentum or a
   market cap built from price times shares, apply the cumulative factor at
   read time and never rewrite rows. List every consumer of price levels in
   the report, and say which read returns and which read levels.
5. **Shares across a split.** The share-count fetch may lag the split. For as
   long as price and shares sit on different bases, the market cap (and so the
   size descriptor and the WLS weights) is off by the factor. Apply the factor
   to shares until the fetched count reflects the split, and say how that is
   detected.
6. **Held positions across a split, for the live phase.** Alpaca adjusts the
   position; the stored book does not. Reconciliation and the next day's
   trades must apply the factor to prior shares, or the loop will think it
   holds half the position and buy the other half. Test it.
7. **Unexplained large moves are flagged, not blocked.** An appended return
   above 40% in absolute value with no corporate action behind it goes into
   `run_status` and the notification. A real crash is a real return, so the
   owner reads it rather than the run refusing it.

**Tests:**
- a synthetic 2:1 split, and a 3:2 split, give the right return with no
  stored row changed (hash before and after);
- a back-adjustment with no split record stops the run;
- a lagging share count is corrected;
- a held position across a split reconciles without a phantom trade;
- the APH case reproduced from the real rows.

### 4b. The store never falls back silently in production (E11-F17, found in review)

`live/store.py` falls back to parquet under `live/state/` whenever
`EFB_SUPABASE_DB_URL` is unset. On Render, a missing or mistyped variable would
write the evening's rows to a disk the next container never sees. The run
could still notify `ok`, the appendix would re-seed from git every night, and
the dashboard would read its own empty fallback. That is the healthy-looking
failure the owner named.

- **The local fallback only on explicit request**: `EFB_STORE=local`, which
  the test suite and local dry runs set.
- Otherwise, a missing `EFB_SUPABASE_DB_URL` is an `error` that stops the run
  and notifies. Under Render (the `RENDER` variable is set) the local mode is
  refused even if requested.
- **The first notification line names the store**, for example
  "store: postgres/efb", so a wrong store is visible in the preview.
- Tests: an unset URL without `EFB_STORE=local` stops the run; `RENDER` plus
  `EFB_STORE=local` stops the run; the suite still runs locally.

### 5. Part 7, still open

- **E5's `evaluated_at` is still re-stamped**: 2026-09-24T13:31:37 against the
  stored 2026-09-21T00:55:38. Restore it, or record the move in `revisions`
  with both values.
- **The 0.000031 gap is recorded but not explained.** The ledger calls it
  "essentially nil", which is the observation, not the answer. Say whether
  XS-v1's beta at 09-21 includes returns after 09-03, meaning the beta inside a
  descriptor dated 09-21 is advancing, or whether it reads a frozen beta. If it
  is frozen, it is a staleness defect that Part 3's gate cannot see, because the
  descriptors' date advances while one column inside does not.

### 6. E11-F16: retention. Postgres keeps the longest lookback, older days go to git (owner, 2026-09-25)

**The owner's design.** Postgres keeps only the rolling window the longest
model lookback needs. Older days are archived to git.

1. **Measure the window.** List every estimator's lookback: the covariance
   EWMA's effective window at its cutoff, the momentum windows, the beta
   window, the specific-variance window and anything else. The Postgres
   window is the longest of them plus a stated margin. Say what E12 needs
   beyond that; the archive covers it.
2. **Archive to separate dated files, never into the seed artifacts.** The
   seed files (`prices.parquet`, `descriptors.parquet` and the rest) are
   artifacts E1 to E10 were scored on. Appending archived days to them would
   move their hashes every month. Write
   `data/live_archive/<input>/<yyyy-mm>.parquet` instead. The read path becomes
   seed, then archive files, then the Postgres window. Test that the read is
   identical before and after an archive.
3. **The archive is a local, deliberate command**, for example
   `make archive-appendix`, run by the owner or DeepSeek, not by the cron.
   - It reads the rows older than the window from Postgres.
   - It writes and commits the archive files.
   - It verifies the read by hash.
   - **Only then** does it delete those rows from Postgres.
   - It records the archive in the hygiene ledger with the date range and
     hashes.
   - Nothing on Render ever holds a git write credential.
4. **The deletion needs its own role.** Add `efb_archiver`, with `delete` on
   the `e11_*` appendix tables only, used only by the local archive command
   and never set on Render. The cron's writer does not get `delete`. Give the
   SQL as text.
5. **Project three years** with the window in place. Put the `efb` schema's
   size in `run_status`, and put it in the notification when it passes 300 MB.

This lands within a month of the deploy. A reminder: the archive command is a
monthly owner action, so say what happens if it is missed. The table grows,
and the size line in the notification is the alarm.

### Smaller, in the same commits where they fit

- **The first run is inferred from an empty appendix.** Make it explicit: a
  one-row marker in `efb` written when the appendix is seeded. An empty
  appendix after the marker exists is an `error`, not a re-seed.
- **The write role holds `delete`.** Drop it unless a code path deletes, and
  say which.
- **One residual for the deploy notes.** PostgreSQL grants EXECUTE on functions
  to PUBLIC by default, so the two roles can call functions in the credit lab's
  `public` schema even with no table grants. Revoking that is a change on the
  shared project and is not for us to make. State it in the deploy steps as a
  known limit of the isolation, so the owner decides with it in view.
- **Guard 1's movement** is better read per name than as the change in the
  maximum. MRNA moved 1.72 points against the 3.74-point clearance. It still
  clears by 2x; state it that way.

---

## Previous: Part 1R accepted, Parts 2 to 5 run (e11-admit-and-live-gate)

**The reviewer's answer to the blocking question.** The ambiguity was in the
reviewer's spec, which said "every floor row" and also "the rank margin the
owner named when choosing". **The 51-name margin gates the book that trades.**
It does not gate the comparison rows.
- The min $5,000 row stays in the table, with its violation recorded in
  `floor_book_checks`, as it is now. Do not drop the row and do not drop the
  check. The project's standing practice since the first construction table:
  a row that cannot meet a condition is reported with what it achieves, never
  removed.
- The other four checks (net, hedge exposure, idio share, below floor) hold on
  all six rows, the min $5,000 row included. They stay armed on every row,
  because a failure there would mean the construction machinery is wrong, not
  only that a row is small.
- The live path already raises on any check failure for the book itself. That
  is the right guard, and it is how a day whose book falls under 51 names
  fails the run. That failure goes through Part 3b's notification, as
  `error`, with the check message as the one-line reason.

Stopping to ask was correct under the literal wording, and so was installing
the share-only book, which passes all five checks, meanwhile.

**The confirmed book:** share-only, 150 names, n_eff 70.59, total error 0.689%,
p90 1.887%, max weight 5.35% of gross. That is a local maximum under
single-name moves, reached in 1 cycle and 4 admission passes. It is 7 names
above the 143 the owner confirmed on, as the owner expected. The re-decide
trigger does not fire. Ordering robustness on the share-only row is -5.66% in
n_eff, under the 10% flag.

**Now run Parts 2, 3, 3b, 4 and 5 below, in order, committing each alone.**
Stop only on the standing stops and each part's own stops. Part 5
re-derives Guard 1 on the 150-name book's final weights over every close run,
and states the close-to-close movement of the largest weight.

Minor: Verification item 1 answered "no" and then described identical columns.
They sit in the superseded prefix measurement, but the honest form is "yes,
confined to the superseded prefix columns, because ...". The previous report
got this right.

---

## Part 1R (done at dd41d9b): the rule re-specified as drop, then admit, to a local maximum

The Part 1 report was excellent. The stop fired as pre-registered, the
mechanism is measured, the degenerate prefix was not installed, the net-zero
guard was not relaxed, and the admission control points at the right rule.
**The prefix spec was the reviewer's error, the second on this item.** A
prefix of the full-book ordering is still a dropping rule. Once a subset is
re-sized, the weights do not move by a common scalar, so a handful of
high-priced names break every prefix between 17 and 499. Stopping everything
when the stop fired was correct, because a pre-registered stop halts the task.

**The rule, pre-registered here: drop, then admit, repeated until a full
cycle changes nothing.**

1. **Order** every name by `|w_i| / max(dollar_floor, share_floor * price_i)`
   on the full-book weights, with a stable sort. This is the order your
   admission control used.
2. **Drop.** Run `enforce_floor_on_final_weights` from the full book to
   convergence.
3. **Admit.** Walk the excluded names in that order. Admit a name only if the
   final weights of the enlarged set (size, hedge, renormalize, quantize) still
   clear every kept name's floor. This is your admission control, unchanged.
4. **Repeat the admission pass** until a full pass admits nothing. Then run
   the drop step once more as a check. It must drop nothing; if it does, loop
   back to step 3. Cap the loop at 10 cycles, and at the cap stop and report
   rather than pick a cycle.

The result is a local maximum under single-name moves: every kept name clears
its floor, and no single excluded name can be added without breaking one.
It is not claimed to be the global maximum. Say so wherever it is quoted.

**Checks that must hold on every floor row, or stop:**
- net dollar within 0.01 of gross;
- worst post-hedge exposure at most 1e-12;
- idio share 1.0;
- zero names below floor in the final weights;
- **kept names at least 3 x the 17 design factors, so at least 51**, which is
  the rank margin the owner named when choosing.

Being at least as large as drop-only holds by construction, because the rule
starts there and only adds names. **Do not report it as a check.** Report it as
a by-construction property, per Verification item 4.

**Robustness, measured and not used to select:** rerun with the names ordered
by `|alpha_i|` descending instead, and report the kept count and n_eff for
both orders on every row. If the two orders differ by more than 10% in n_eff
on the share-only row, say so at the top of the report. It means the book's
breadth depends on an arbitrary ordering, and the owner should know that.

**Determinism:** the same inputs give the same set. Test it. Report the rule's
run time on the live path; it runs every evening.

**Install it as the book** in the table and the live path. Store drop-only
and the prefix beside it as columns, for the record. Then re-run the
re-decide trigger exactly as written in E11-F12, on these numbers.

**Where Part 1 hands back to the owner, and whether it blocks.** The owner has
been asked to confirm share-only now, on the admission-control numbers, with
the trigger still armed on this rule's numbers.
- **If LOG.md records that confirmation**, do not block: continue to Parts 2
  to 5, and stop only if the trigger fires or a check above fails.
- **If it does not**, set `blocked` after Part 1R as before, and carry on with
  Parts 2 to 4, which do not depend on the book.

**Also, from the Part 1 report:** your Verification item 2 found 3 pseudoinverse
fallbacks inside the enforced-book loops, while the previous report answered
"no fallback". Name the rows and passes where they fire. Note in this report
that the earlier "no" was wrong, even though the resulting books still reach
1e-15 exposure.

---

## Admission back into the fixed point, inputs into Postgres, staleness as a hard stop

**Owner decisions, 2026-09-24.** E11-F13, E11-F14 and every smaller item are
accepted. On E11-F15 the owner chose: **the model inputs live in Postgres,
schema `efb`, not on disk.** Each run reads the last stored date, appends the
new session and writes it back, so a wiped container costs nothing.
**Staleness fails the run instead of being reported by it.** The owner holds
the share-only choice until the corrected E11-F13 numbers exist.

**Owner confirmations, 2026-09-24, later:**
- All four of the reviewer's readings are confirmed.
- Part 2 builds without a costing gate. Its three stops are the guards, and
  the size stop is the one that matters.
- The seed stays in git and new days go in Postgres.
- Staleness is counted in trading sessions at zero behind the latest close,
  with shares and sectors judged on fetch age. The risk with slow inputs is
  the fetch quietly stopping.
- **The gate runs through the Render cron in dry run.**
- New: **every run pushes a notification the owner will see** (Part 3b).

Parts 1, 2, 4 and 8 of `e11-share-floor-to-gate` stand. Run the parts below in
order, committing each alone. `dry_run` stays `true`, and you never flip it.

### Part 1 (superseded by Part 1R above; kept for the record). E11-F13: the enforcement loop only drops

`enforce_floor_on_final_weights` says so itself: "The kept set only shrinks."
Starting from the full book, a drop-only loop lands on roughly the **one-pass**
count and throws away the breadth that E11-F6's iteration bought back. The
table shows it on every row:

| row | one-pass (last cycle) | fixed point, pre-resize | enforced now |
| --- | --- | --- | --- |
| share-only | 118 | 188 | 119 |
| two-part | 92 | 172 | 87 |
| min $1,500 | 208 | 252 | 194 |
| min $2,000 | 155 | 208 | 145 |
| min $3,000 | 82 | 156 | 72 |
| min $5,000 | 27 | 99 | 23 |

**The reviewer's spec invited this.** It said "drop, re-size, re-hedge,
check, repeat" and never said "admit". The fault in the spec is the
reviewer's. The fix is yours.

**The fix: the largest valid prefix, checked on final weights.** Order names
by `|w_i| / (20 * price_i)` on the full-book weights, which is the ordering
the E11-F9 prefix method used. For k from 499 downward, finalize the prefix-k
set (size, hedge, renormalize, quantize) and check every kept name against its
floor **in those final weights**. The first k that passes is the book. The
scan is not monotone, so do not bisect. Use the same rule on all six floor
rows, with each row's own floor and ordering.

Pre-registered, before the numbers exist:
- The prefix result is the book. The drop-only result is reported beside it on
  every row.
- If the prefix result keeps **fewer** names than drop-only on any row, stop
  and report. That would mean a bug, not a finding.
- Re-evaluate the owner's re-decide trigger exactly as written in the E11-F12
  section below, on the prefix numbers: enforced share-only against enforced
  min $2,000, and dominance across all enforced rows. If it fires, stop and
  send the choice back to the owner.
- Report share-only's n_eff against the 85.69 the owner chose on, as a plain
  number.

**Checkpoint: the owner holds the share-only choice until these numbers
exist.** When Part 1 is committed, report the prefix table and where the
trigger lands, and set `handoff/TASK.md` to `blocked` with that question at
the top of the report. **Do not regenerate the proposals or re-derive Guard 1
until the owner confirms**; that work is Part 5. Parts 2 to 4 do not depend on
the book, so carry on with them while the owner reads the table.

### Part 2. E11-F15: model inputs into Postgres. Describe and cost it first, then build.

**Target, decided by the owner: Postgres, schema `efb`.** Do not reopen the
choice between Postgres, a rebuild from raw and a persistent disk.

**Before building, write down in REPORT.md:**
1. What the code does now on a fresh container, with the line that does it:
   where each of the nine inputs is read from and where an appended session is
   written.
2. The migration cost:
   - rows and megabytes per input for the design you propose;
   - the run's read and write time against the session pooler;
   - the code touched.
3. **Database size against the free tier.** The Supabase free tier caps the
   database, and this project **shares that cap with credit-trading-lab**. A
   full-history copy of prices and specific returns alone may approach it.
   The natural design is **the git snapshot as the seed plus a Postgres
   appendix**:
   - Postgres holds only sessions after 2026-09-03, plus whatever trailing
     window the rolling estimators need.
   - The pre-2026-09-04 rows stay in git, byte-identical.
   - A run reads seed plus appendix, and writes only the new session.

   If you propose something else, say why. State the credit lab's current
   database size, read-only, and the combined total after one year of
   appends.

**Then build it**, unless one of these stops applies. Stop and report instead
of building if:
- the design would push the shared database past 80% of the free-tier cap
  within a year of appends;
- it needs any grant, role or dashboard change on the shared project beyond
  the two roles the owner is already creating;
- it would restate any pre-2026-09-04 row.

**Requirements for the build:**
- The seed-plus-appendix read equals the current local artifacts on every
  date through the latest close. Test it and print the hashes.
- An append is idempotent: running the same session twice leaves one row per
  key. Test it.
- The append and the proposal for a session are written in one transaction,
  or the proposal records the appendix row it was priced from. A proposal
  must never be priced from an appendix it cannot name.

### Part 3. Staleness fails the run (owner, non-negotiable)

If any input is older than it is allowed to be, **the job stops before
proposing, logs why, and places no orders.** A book pricing Monday's close on
Thursday must not trade. The E11-F15 hazard is precisely that the dashboard
would look healthy while that happened.

**Measure in trading sessions on the NYSE calendar, not calendar days.** A
Friday close read on Monday is fresh. `max_input_staleness_days` stays as a
reported field, but the gate uses sessions. The target close is the most
recent completed session at run time.

**The allowed values, pre-registered here** (the owner can change them before
the first run):

| input | measured by | allowed |
| --- | --- | --- |
| prices, descriptors, factor_returns, specific_returns, factor_cov, specific_var | the content date | 0 sessions behind the target close |
| universe (SPY archive) | the content date | 0 sessions |
| shares | the date of the last successful fetch; content age reported, not gated | 0 sessions |
| sectors | the date of the last successful fetch; content age reported, not gated | 0 sessions |

Shares and sectors change slowly, so their content ages. What must not age is
the **check**. Store both dates for each of them, and store content dates for
all nine inputs.

Requirements:
1. **The check runs before any sizing.** On failure, no proposal row and no
   order is written. A `run_status` row in `efb` records the target close,
   every input's dates, which inputs failed and by how many sessions, and
   `status: stale_stopped`. The process exits nonzero, so Render marks the
   cron run failed.
2. **A missing run is stale too.** The dashboard reads the latest
   `run_status`, not the latest proposal. It shows a prominent failure state
   when that status is anything but a clean run for the most recent completed
   session: stale-stopped, errored, or no run at all for that session. A page
   that keeps showing an old book as the current one is the failure the owner
   named.
3. **Tests:**
   - one stale input stops the run with no proposal and no orders;
   - the check uses sessions, so a Monday run on Friday's close passes;
   - a holiday is handled;
   - the dashboard shows the failure state when the latest status is
     stale-stopped and when it is missing.

### Part 3b. Every run notifies the owner (owner, 2026-09-24)

This is the first unattended run. Two evenings of remembering to open a page
is how a silent failure gets missed on exactly the days that count. So **every
run pushes a notification**, to a Slack incoming webhook or by email. The owner
places the webhook or the credential. Build for Slack first, with email behind
the same interface if it costs little.

**Three fields, in this order, readable from the notification preview:**
1. **Did it run?** One of `ok`, `stale_stopped` or `error`, with the target
   close.
2. **Did the proposal produce orders?** In dry run, say so explicitly: "dry
   run: N orders proposed, $X gross, none sent". It must never read as "0
   orders". When live: orders sent, fills, and any guard that fired.
3. **Staleness.** The worst input and how many sessions it is behind. On
   `stale_stopped`, every failing input.

Requirements:
- **Notify on every run, including clean ones.** Silence has to mean
  something, and the owner learns to expect one message per session. A run
  that never starts cannot send anything, so the absence of the evening
  message is the alarm. State in the report the time by which the message
  should arrive.
- **Notify on unexpected errors too.** Wrap the whole job so an exception
  still sends `error`, with the exception type and a one-line reason. Scrub
  the reason: no connection string, key, token or webhook URL may reach the
  message. Test it with an exception whose text contains a fake DB URL.
- **The webhook URL is a credential.** It goes in `EFB_NOTIFY_SLACK_WEBHOOK_URL`,
  listed in `.env.example` with an empty value, set on the cron service only,
  and never printed, logged or stored in `efb`. Extend the credential check to
  cover it.
- **A failed send is recorded, not silent.** It happens after the proposal and
  orders, never before, so it cannot block or roll back the run. Record
  `notify_failed` in `run_status` and exit nonzero, so Render marks the cron
  run failed.
- **Before the gate evenings**, the owner receives one test notification from
  the deployed cron and confirms it arrived. That confirmation is part of the
  deploy steps.

**Offer the owner an outside check that alerts on a missing run**, and do not
build it: a free external heartbeat service that the cron pings after
notifying, and that alerts the owner if no ping arrives by the expected time.
A check that runs inside Render shares Render's failure modes. Name one
option, what it needs from the owner and what it costs, and leave the choice
to the owner.

### Part 4. The owner's deploy steps, corrected

- **The order is wrong.** Step 1 grants on schema `efb`, which does not exist
  until step 2. Create the schema and tables first, then the roles.
- **Give the owner the SQL for both roles**, as text only; do not run it. Each
  role gets LOGIN, USAGE on `efb`, and the table privileges it needs, plus
  `ALTER DEFAULT PRIVILEGES` so future tables are covered. Nothing on `public`
  or any other schema. Say what username format the session pooler expects
  for a custom role, and how the owner can test each connection string before
  pasting it into Render.
- **Does the store issue DDL at runtime?** B1 says `CREATE SCHEMA IF NOT
  EXISTS efb` on first run. A DML-only write role fails on that statement. If
  it is there, either take it out of the runtime path, since provisioning
  covers it, or say which role owns the schema.
- **Add the notification variable**: `EFB_NOTIFY_SLACK_WEBHOOK_URL`, on the
  cron only, and the owner's step to confirm the test notification arrived.
- **Prefer the SQL editor to the management token.** One-time provisioning
  through the Supabase SQL editor needs no account-wide token. Make that the
  primary path, and the token path the alternative.

### Part 5. After the owner confirms the book: proposals and Guard 1

Only after the owner confirms the Part 1 result:
- Regenerate the stored proposals on the prefix book.
- Re-derive Guard 1 over every close run.
- State the headroom again. 1.54x is thin for a book that rebalances daily,
  so report how much the largest final weight moves from close to close, and
  say whether 0.10 still clears that movement with margin.

### Part 6. E11-F14: the gate, on two closes the loop fetched itself

**Owner, 2026-09-24:** the gate reruns only once the daily update is
genuinely appending, on two closes **the loop itself fetched**, not replayed.

1. **Fix the universe look-ahead first.** The 09-18 proposal records its
   universe as of 2026-09-21. Clamp the universe the way `_input_as_of` clamps
   everything else, and add a shift-audit test that refuses a proposal whose
   universe file postdates its close.
2. **Say what the sectors date means**: the content date, or a fetch that is
   not running. Part 3 needs both dates regardless.
3. **Catching up is allowed but does not count.** Bringing the data current
   through the daily entry point, for 09-22 onward, is fine. Record those
   sessions as `catch_up` in `run_status`. **They are not gate closes.**
4. **The gate's two closes are two consecutive sessions, each fetched by a run
   on that session's own evening** through the production entry point, with
   the fetch timestamps stored as evidence. **The owner chose the Render cron
   in dry run**, after Parts 2 to 5 and the owner's deploy. The owner gets two
   real evenings of the production path, and the flip then changes one
   variable on a system already watched working. Both evenings' notifications
   arrive, and they are quoted in the report. The gate is evaluated from the
   `run_status` and proposal rows in `efb`.
   Report:
   - the two closes and their fetch times;
   - turnover, with its definition;
   - n_eff on each close;
   - all nine as-of dates;
   - confirmation that the staleness check passed on both runs.
5. **Pre-2026-09-04 rows stay byte-identical** through all of it. Print the
   hashes.

### Part 7. Three small corrections

- **E11-F8, the 0.000031 gap is too clean to leave unexplained.** TS-v1's raw
  beta is frozen at 2026-09-03. XS-v1's pre-shrinkage beta was recomputed at
  2026-09-21. Two estimators twelve sessions apart agree to 3e-5 in book
  exposure. That happens only if XS-v1's beta at 09-21 is effectively the
  09-03 value, meaning the beta inside a descriptor dated 09-21 is not
  advancing, or if the recomputation read TS-v1's frozen beta. Say which. If
  the beta column is stale, that is a staleness finding for A4, because the
  descriptors' as-of date would overstate its freshness. The refutation stands
  either way, because the shrinkage increment is measured inside XS-v1 at a
  single date.
- **E5's `evaluated_at` was re-stamped.** The report says "the E5 `data_hash`
  moved, and only that moved". `evaluated_at` moved too, so the record now
  dates E5's evaluation to this week. Restore the stored value, or record the
  move in `revisions` with both values, and correct the sentence.
- **Em dashes in REPORT.md** at the Guard 1 and part 6 paragraphs (STANDARDS
  rule 12). Check every file you touch.

### Stop only if

- The standing stop conditions below apply.
- Part 1R fails one of its checks, hits its cycle cap, or the re-decide
  trigger fires. The old prefix-versus-drop-only stop is retired with the
  prefix rule.
- Part 2 hits one of its stops.
- Part 4 would need you to create a role or a grant yourself.
- Any step would restate a pre-2026-09-04 row.

---

## Previous task, e11-share-floor-to-gate: the owner chose share-only, minimum 20 shares

**Owner decision, 2026-09-24, reserved decision 1.** E11 trades the
share-only construction: a minimum of 20 whole shares per name, no dollar
floor, iterated to a fixed point. At the table it is 188 names, n_eff 85.69,
governing breadth 1.355, total error 1.25%, p90 3.44%. The owner's reasoning
is recorded in PROJECT_CONTEXT.md. Changing the construction again is the
owner's decision, never yours.

Run the parts **in this order**. Commit each part on its own. If budget runs
short, stop after a completed part, commit it, and report what is left. Do
not start a part you cannot finish. `dry_run` stays `true` throughout, and you
never flip it.

1. **E11-F8 ledger correction.** As written below. The owner accepted it in
   full: record the candidate as **undetermined**, fix the 53% figure, and
   explain the nonzero standardization increment. Then run the diagnostic
   split.
2. **E11-F11, the store over direct Postgres.** As written below. The owner
   accepted it in full, with four rules: **direct Postgres, never PostgREST;
   the service-role key never on a web service; no change to the Exposed
   schemas setting on the shared project; and if anything needs that change,
   stop.** The earlier deploy steps are withdrawn and are not to be followed.
3. **E11-F12, the floor enforced on final weights**, then the n_eff check.
   See the rewritten E11-F12 section below. This part carries the one stop
   condition that sends the choice back to the owner.
4. **The registry records the chosen construction.** Replace XS-v1's
   `live.min_position_dollars` with the share-only parameters: share floor
   20, no dollar floor, iterated on final weights. **Warning, from the last
   registry edit:** `e5_data_hash` hashes `models/registry.json` directly,
   so this moves `sprints/E5/RESULTS.json`'s `data_hash`. Record it through
   the `revisions` block with both hashes, per STANDARDS rule 22. Anything
   else that moves is a stop. Update `docs/open_items.md`: the minimum-position
   item closes as a share floor. The residue, folding it into E8's
   construction stack, stands.
5. **Guard 1, re-derived against the chosen construction's final weights.**
   Show the arithmetic. The guard must clear the largest legitimate target
   with stated headroom, and trip a 10x order on the largest name. Size it
   from the largest final weight across **every close you have run**, not one
   close, because the book rebalances daily. State the value in dollars and as
   a percentage of NAV, and keep a test that fires it.
6. **Regenerate the dry-run proposal under the chosen construction** on the
   latest close. The D10 header then shows the book that will trade, labeled
   from its own recorded fields. The Render page (`live/dashboard_app.py`)
   follows the same labeling rule: the construction is read from the artifact
   and never asserted.
7. **The sanity gate on two consecutive real closes, `dry_run` true.** This is
   Part A step A5 below, unchanged. The proposals must differ. Print and store
   the weight turnover with its definition, the n_eff on each close, and the
   staleness of all nine inputs. If it fails, stop, and name the input that is
   not advancing.
8. **Deploy-ready over direct Postgres, and the owner's steps.** Both Render
   services read and write schema `efb` over `EFB_SUPABASE_DB_URL`. The
   dashboard holds a read-only credential or, failing that, whatever the owner
   approves under E11-F11 item 3, never the service-role key. List the owner's
   steps exactly: the variables on each service, the local `.env` entries, the
   one-time schema setup over direct Postgres, and the deploy. After the owner
   deploys, a dry run writes a real proposal to `efb` and the Render page shows
   it. That is remaining-plan item 4c, and a page that has never shown a real
   proposal is not confirmed.

**The label fix already landed** at 190496d. What the owner listed as "the
label fix landed" is satisfied by part 6: once the proposal is regenerated, the
header shows the chosen book under its own recorded label.

**The clock does not start in this task.** When parts 1 to 8 are done, the
owner flips `dry_run` once, and that act is day 1.

### E11-F8, the ledger follow-up overclaims: append a correction

The 2026-09-23 follow-up entry in `docs/hygiene_ledger.md` has three problems.
The ledger is append-only, so fix them with a new dated entry that carries the
old values beside the new ones. Never edit the existing entry.

1. **Arithmetic.** The entry says shrinkage accounts for
   `0.1050 - 0.0555 = 0.0495 (47 percent)`. The quantity in the stored columns
   is the residual exposure at each stage, which is the part of the raw beta
   that stage fails to carry. The shrinkage step's increment is therefore
   **0.0555, 53 percent**, which is what REPORT.md's own table says. The three
   increments sum to the total only this way:
   `0.0555 + 0.0526 - 0.0031 = 0.1050`. The ledger's `0.0495 + 0.0526` is
   0.1021 and does not.
2. **"Standardization contributes zero to three decimals" is not what the
   columns show.** `residual_exposure_winsor` is 0.1081 and
   `residual_exposure_standardized` is 0.1050 at min $1,500: -0.0031 there,
   -0.0034 at $2,000, -0.0047 at $3,000 and -0.0031 on the full book, but
   exactly zero on min $5,000 and both top-N rows. The pattern across rows is
   part of what to explain. A regression residual is invariant to an
   affine change of the regressor on the same sample with the same weights. A
   nonzero increment therefore means the standardized stage is not an affine
   map of the clipped stage on that sample: a different cross-section, a
   different weighting, or orthogonalization folded in. Find which, and say so.
   It is small, but it is the prediction E11-F8 told you to check, and it came
   back nonzero.
3. **"Refuted" is not established.** The Vasicek-stage increment regresses
   TS-v1's raw beta, frozen at 2026-09-03, on XS-v1's shrunk beta at
   2026-09-21. It therefore mixes three things: the shrinkage, the gap between
   the TS-v1 and XS-v1 estimators, and twelve sessions of window drift.
   REPORT.md says this; the ledger entry drops it and asserts a mechanism
   ("name-specific through the standard error") that nothing measured. Under
   the identity hypothesis, the whole 0.0555 could be estimator gap. The
   correction entry records the candidate as **undetermined**, with 0.0555 as
   an **upper bound** on what shrinkage contributes. The clip's 0.0526 is a
   clean measurement, because both of its stages are XS-v1 at the same date.

Then split the 0.0555. Recompute XS-v1's pre-shrinkage beta at 2026-09-21
under the frozen XS-v1 specification, **as a diagnostic only**: no artifact is
restated, nothing is stored as a model input, and the specification does not
change. Insert it as a stage between raw and Vasicek. The raw-to-XS-v1-raw
increment is the estimator and date gap, and the XS-v1-raw-to-Vasicek
increment is the shrinkage. Append a second ledger entry with the verdict:
E11-F8 joins the class if the shrinkage increment is near zero, and is
refuted otherwise. Either way, record the measured shrinkage share.

### E11-F11: the live store is wired to the path the LOG ruled out

LOG.md at line 1064, and the TASK.md B1 amendment, settled the connection as
**direct Postgres under `EFB_SUPABASE_DB_URL` with `EFB_DB_SCHEMA=efb`, not
PostgREST**. `render.yaml` and `.env.example` carry `EFB_SUPABASE_URL` and
`EFB_SUPABASE_SECRET_KEY`, which are the PostgREST path. Neither file has
`EFB_SUPABASE_DB_URL`. The owner's deploy steps in REPORT.md use the PostgREST
variables on both services.

This matters for two reasons. PostgREST serves only schemas added to "Exposed
schemas" in the project's API settings. On the project shared with
credit-trading-lab, that is a dashboard change that widens the credit lab's
public API surface, which is a listed stop condition. And the secret key is
the service-role key: it bypasses row-level security on the **whole shared
project**, including credit-trading-lab's data, and it would sit on a public
web service.

1. State, with the code line as evidence, which connection `live/store.py` and
   `live/dashboard_app.py` actually use, and which schema the one-time setup
   creates.
2. If it is PostgREST, move both to `EFB_SUPABASE_DB_URL` and
   `EFB_DB_SCHEMA=efb`, as decided. If that cannot work without a dashboard
   change or a shared-role grant, **stop and report**; the owner moves to Neon
   or Render Postgres.
3. The dashboard only reads. Propose the least-privilege credential for it and
   let the owner decide. Do not create roles or grants on the shared project
   yourself.
4. Say what uses `EFB_SUPABASE_ACCESS_TOKEN`. A management token is
   account-wide, so confirm it never goes to either Render service.
5. `EFB_DRY_RUN` is how the owner will flip the clock on Render. **Unset,
   empty or unparseable must resolve to dry run**, and so must any spelling
   other than an explicit false. Add a test over those cases and paste it.
   Starting the clock by accident through a missing variable is the failure
   this guards.

Update the owner's deploy steps in REPORT.md to match.

### E11-F12: the floor is checked on weights that are not traded

REPORT.md: "every kept name holds at least 20 shares in the renormalized
full-book weights ... but the re-sizing on the kept subset moves about one name
in ten below 20 shares." So the fixed point is computed on weights from before
the subset is re-sized and re-hedged, and the book that trades is a different
vector. The same is presumably true of the dollar rows.

**Rewritten 2026-09-24 after the owner's choice. Enforce, do not only
measure.**

1. **Measure first**, on every row as it stands: the count of kept names that
   end below their floor in the **final** weights (after re-sizing,
   re-hedging, renormalizing and quantizing), with the worst shortfall.
2. **Enforce on the final weights, iterated to a fixed point**: drop,
   re-size, re-hedge, renormalize, quantize, check, repeat until no kept name
   is below its floor. Do it in the live path for share-only 20 shares, and
   in the table for **every row**, so the comparison stays like-for-like.
   Guard against oscillation: if the loop does not converge in a stated
   number of passes, stop and report rather than picking a pass.
3. **Report share-only's enforced numbers beside its table numbers**: names,
   n_eff, naive and governing breadth, total error, p90, max weight, net,
   long/short counts, raw beta, post-hedge max exposure and idio share. State
   the breadth bound both ways, as PROJECT_CONTEXT requires for any E11
   number that meets an E8 transfer coefficient.
4. **The re-decide trigger, pre-registered here before the numbers exist.**
   Compare enforced share-only against **enforced** min $2,000, never against
   the unenforced row. **Stop and report to the owner, without implementing
   further parts, if either** (a) share-only no longer has both lower total
   error and lower p90 than min $2,000, or (b) any enforced row is strictly
   better or equal on both n_eff and total error than share-only. Otherwise
   proceed. A fall in n_eff alone does not stop the task, but its size is
   reported plainly. The owner reads it and may re-decide on it.

### Also

- The report's table dropped total error, net, long/short counts, raw beta,
  post-hedge exposure and idio share for the two new rows. The parquet has
  them. The report is where the owner reads the decision, so it carries every
  decision column, as E11-F7 already required.
- The previous full-run count recorded in LOG.md is 692, not 682. 695 still
  clears it.
- "Neither is close" is the owner's judgment to make. Report the ratio, and
  leave the word "close" to the owner.

### Stop only if

The standing stop conditions below apply, plus: E11-F11 item 2 needs a
dashboard change or a grant on the shared project.

---

## One row to its fixed point, the beta split in the right units, then the owner picks

The restored table is right and reads cleanly. **Do not rebuild it.** Re-run one
row, redo one decomposition in consistent units, add four facts to the D10
report, and correct the status report's last section. Do not choose. Do not
re-derive Guard 1.

**The owner holds the choice for this cycle**, agreed 2026-09-23. Comparing
the two-part row now would compare a one-pass book against fixed-point books.

### First, before anything else: D10 derives its label from the artifact

**Owner instruction, 2026-09-23. The owner will not look at D10 until this
lands.** The registry's `min_position_dollars` is 5000, and the stored
2026-09-21 proposal is "the min $5,000 book". If that proposal predates E11-F4
and E11-F6, it is the 27-name book at gross 0.2734, idio share 0.8631 and max
exposure 0.1458, the one known to be degenerate. The selector's "min $5,000" is
a different book: 99 names at gross 1.0. Showing the first under the second's
label is worse than no page, because the owner would be reading the wrong book
without knowing it.

So the label is **derived from the artifact, never asserted beside it**:

1. Every proposal stores the construction it was built under: the construction
   type, every parameter (dollar floor, share floor, N), whether the floor was
   iterated to a fixed point, kept and dropped counts, kept gross before and
   after renormalization, and the code commit. If an existing proposal lacks
   any of these fields, the page says so on screen ("construction parameters not
   recorded in this artifact") and does not fill them from the registry or the
   table.
2. For every proposal and every selector row, the page displays those
   parameters, the kept count and the gross, read from that artifact. The label
   text is generated from the stored fields. No label is typed into the page.
3. A test builds two artifacts with the same nominal floor, one pre-iteration
   and one post-iteration, and asserts that the page renders two different
   labels with the right kept counts and gross.
4. Report what the header shows for the stored 2026-09-21 proposal after the
   change, quoting the rendered label, kept count and gross.

Whether to regenerate that proposal with the current code is your call. The
labeling rule comes first either way, so the old book can never appear under
a label that isn't its own.

### E11-F9: the two-part row is not at its fixed point

The row reads `252 -> 100` kept and `11.93% -> 1.80%` p90. The iteration only
admits names, so on every other row post is at least pre. Here the two columns
mean "before the share floor, after it", and the share leg has no fixed point
shown. The status report describes only the four dollar floors as iterated. This
is E11-F6 again, on the one row the owner's decision rule reads, and it biases
that row's n_eff **down**, the number the rule turns on.

Apply the combined floor to a fixed point: name i is kept when
`|w_i| * NAV * scale >= max(1500, 20 * price_i)`. That is a single ordering, by
`|w_i| / max(1500, 20 * price_i)`, so the prefix method from the dollar rows
carries over unchanged. Report one-pass and fixed-point values for every column,
and relabel so pre and post mean the same thing on every row.

State this bound in the report: at the fixed point every kept name holds at
least 20 shares, so if per-name error is relative to the name's target, as the
1.80% suggests, no name rounds by more than 0.5 / 20 = 2.5%. The iteration can
move p90 toward 2.5% and not past it. That is why the row is worth finishing:
breadth comes back without giving up the property that made it stand out.

Optional, flagged for the owner's veto: one row with the 20-share floor alone
and no dollar floor, at its fixed point, same columns. It tests whether the
$1,500 leg does any work once the share leg bounds the error.

### E11-F8 stays open: the split is drawn in the wrong units

The measurements are the right ones. The split drawn from them is not.

1. **Exposure to a stage is not a contribution.** A shrinkage with a common
   weight `k` is affine, `v = k * b + c`, and with net dollar zero it multiplies
   the exposure by `k`: the book's exposure to `v` is `k * 0.105` whatever `k`
   is, and nothing has been explained. The pre-win to raw ratio is 0.41 to 0.45
   on six of seven rows (0.36 on top-N 150). A near-common slope would produce
   exactly that, so the 0.059 now credited to Vasicek shrinkage may be only a
   change of units.
   Put every stage in raw-beta units. For each stage X (Vasicek, clipped,
   standardized, the finished descriptor), regress raw beta on X across the
   cross-section and with the weights XS-v1's fit uses. Then report the book's
   exposure to the regression residual. That residual exposure is the part of
   the 0.105 the stage fails to span. It runs from 0 at raw to the full residual
   at the descriptor, and each stage's increment is its contribution.
2. **Two steps should contribute zero, and saying otherwise needs a
   measurement.** Standardization is affine, so by the algebra already in
   E11-F8 it contributes exactly nothing. The report nonetheless lists it among
   the steps that "take the rest to zero". Orthogonalization against
   descriptors that are themselves hedged factors also contributes nothing,
   because the hedge zeroes those too. What remains are the non-affine steps:
   name-specific shrinkage weights, the 3 MAD clip and the fills. The algebra
   predicts that every stage after the clip carries zero exposure, apart from
   zero-filled names, so the whole residual arises at or before the clip.
   Check that prediction. If standardization or orthogonalization measures
   nonzero, that is its own finding.
3. **The zero fill is a second fill, uncounted.** The report fills names absent
   from the descriptor cross-section with 0 in z. The hedge cannot see those
   names' betas, so they land entirely in the residual. Per row, report how
   many there are and the residual raw beta excluding them, exactly as for the
   median fill.
4. **Say which raw beta.** Is the "raw beta" column XS-v1's own pre-shrinkage
   estimate, with the same window and market proxy, or TS-v1's? If TS-v1's,
   start the chain from XS-v1's pre-shrinkage beta and report the gap between
   TS-v1 and XS-v1 as its own line. That estimator mismatch was half of
   E11-F8's original hypothesis.
5. **Add the full 499-name book as a reference row.** If it also carries about
   0.1 raw beta, the residual is the signal's tilt and no construction choice
   changes it. If it is near zero, dropping names creates it.
6. **Rewrite the mechanism sentence to match whatever this shows.** Drop
   "exactly as the owner read it" unless the numbers put the residual where the
   owner put it. The conclusion is not in question: the hedge neutralizes a
   transformed descriptor, and the residual is what that descriptor does not
   span. What is open is which step fails to span it. STANDARDS rule 3.
7. **Append the follow-up to the hygiene ledger.** The 2026-09-23 entry
   records E11-F8 as a candidate fourth instance of "a number that is an
   identity", beside F4.1, F7.2 and F8.4. Append a new dated entry either way.
   If the residual exposure at the Vasicek stage is near zero, E11-F8 joins the
   class; say so with the number. If not, record the measured share that
   shrinkage explains, and state that the candidate is refuted. Never edit the
   2026-09-23 entry.

### D10: say what the owner will actually see

1. **The label.** Covered by the first section above.
2. **Name the seven panels and the stored field each drew from**, as 17d
   requires. The absence of the string "No data yet" does not show that a
   panel drew from the proposal. A dry run has no fills, so there is no P&L,
   realized vol, Sharpe or drawdown yet. Say what the tracking panel shows.
3. **What would a Render deploy show today?** D10 reads the local proposal
   directory. Is that directory in the repository Render builds from? If it is
   gitignored, the deployed page stays empty until the Supabase read is wired,
   "deployment-ready" is not yet true, and the report says so. Then list the
   owner's steps exactly: which services, which environment variables each one
   needs (a read-only dashboard should need no Alpaca keys), and any one-time
   schema setup.
4. **Confirm the local command.** The reviewer gave the owner `make dashboard`,
   which runs `streamlit run dashboard/app.py --server.headless true` at
   http://localhost:8501. If the owner needs anything else to reach D10 (a
   tab name, an environment variable, a data file), say so in the report.

### E11-F10: the status report's last section contradicts settled decisions

The "What comes next" section of `docs/research/STATUS_REPORT.md` has four
problems:

- "sign off on the universe reconstruction" contradicts the owner's 2026-09-22
  decision: the reconstruction is **not** scheduled and the universe stays
  split. Remove it.
- "E11's remaining work is the owner's" is wrong. Guard 1 against the chosen
  construction, the sanity gate on two real closes and the Supabase wiring are
  the implementer's, and they come before the flip. List remaining plan item 4
  in its order.
- "The dashboard is deployment-ready" claims more than has been verified. Say
  what was verified: the page renders locally, reads local state, and is not
  deployed.
- "the realized-beta column was decomposed before the owner read it" holds only
  once E11-F8 closes. Recheck it then.

The traceability test cannot catch any of these, because none of them is a
number. Read the prose against PROJECT_CONTEXT.md's "Decisions the owner has
made".

### Verification, four corrections

- **Item 1 is answered "no" with an evidence line the table contradicts.** Idio
  share is 1.0 and net dollar is zero on all seven rows, and top-N 150 and 200
  both read 0.135 raw beta. The honest answer is yes, with the reason: the
  first two hold by construction of the exact hedge and the net column. Rule 20
  exists to catch a "no" that the table contradicts.
- **Item 2 cites "effective equals kept everywhere, stated above"**, but it is
  not stated above. Add the effective-count column or paste the check.
- **Paste `git diff --stat` raw**, including the summary line. This one was
  reformatted. The contents match, but a reformatted paste is a summary.
- **Headline numbers need the column and row key**, not only the file. Also
  name the one skipped test and why it skips, which has been outstanding since
  e11-live-fixes. Cite rule 21 for the count: 692 against the previous full run
  of 682.

### Then the owner picks

Present the table with the two-part row at its fixed point and the beta
decomposition in raw-beta units. The owner's rule, stated before the numbers:
if the two-part floor's n_eff is close to min $1,500's, it wins outright. **Do
not choose. Do not re-derive Guard 1 until the construction is picked.**
`dry_run` stays `true`.

---

The sections below come from earlier cycles. Their standing rules still bind:
credentials, stop conditions, acceptance items and `dry_run`. Their superseded
specifics do not, such as the $10m NAV path and the 670 floor. Where anything
below conflicts with `handoff/PROJECT_CONTEXT.md`, PROJECT_CONTEXT.md wins.


## Ahead of the construction choice: deploy the dashboard now

**Owner instruction, 2026-09-23.** The owner wants to look at an actual book
before picking a construction, not after: its names, weights, exposures, hedge
and per-trade reasons. So the Render app and D10 move **ahead of the choice**,
and the table work continues in parallel. The choice waits on both.

Show the existing dry-run proposal for the **2026-09-21 close**. `dry_run` stays
`true`; nothing here starts the clock.

**Label what is on screen.** The stored proposal reflects whichever floor was
last applied, so the page must state, prominently, **which construction it is
rendering** and with what parameters. A page that shows a book without naming it
invites the owner to judge a construction they did not intend to look at, and one
of the candidates we already know is degenerate.

**Recommended, and the thing that would actually serve the stated goal: put a
construction selector on the page.** The table already computes seven books. If
D10 can render any row, the owner can page through min $1,500, min $2,000, the
two-part floor and the rest, seeing names, weights, exposures, hedge and trade
reasons for each. That turns the dashboard into the decision surface instead of a
static view of one arbitrary book. Build it if it is cheap; say so if it is not.

**What needs the owner.** Previous reports state the deploy needs the owner's
Render, Supabase and Alpaca credentials. Get the app deployment-ready and verify
it renders locally against the stored proposal with every panel populated, then
say exactly what remains for the owner to do and what you could not verify
without it. Do not treat a locally rendering page as a deployed one.


## Two findings, then the owner picks. Plus the status report.

The cycle was good: net is structurally zero, the iteration behaved as predicted,
the $5,000 reversal is correctly diagnosed, and the two-part floor cut p90 6.6x.
**Do not rebuild the table again.** Restore two things and decompose one number.

### E11-F7: the rerun dropped the columns the decision rests on

The previous table carried **n_eff, breadth naive, breadth governing, total
error, post-hedge max factor exposure and idio share**. The rerun dropped all
six. Those are what the choice turns on: min $1,500 keeps 252 names and the
two-part floor keeps 100, and **that trade cannot be read without n_eff and the
governing breadth ratio**. Post-hedge exposure and idio share are how the
rank-deficiency failure is detected at all; the report asserts no row degenerates
but shows no exposures.

Restore all six columns on all seven rows, beside the new ones. One table, every
column, so the owner reads the decision off one row.

### E11-F8: the realized-beta explanation does not follow

The report says the book "carries about a tenth of a unit of raw CAPM beta,
because the raw betas are not all 1.0". That does not follow. Write
`beta_i = m + s * z_i`. Then net beta is
`m * sum(w_i) + s * sum(w_i * z_i)`, which is `m * net_dollar + s * (z-beta
exposure)`. Net dollar is zero on every row and the FMP hedge zeroes the z-scored
beta exposure, so **both terms vanish and the level `m` is irrelevant**. A
residual of 0.105 to 0.147 therefore needs a different explanation.

**The owner's reading, and it is a modelling point, not a bug.** XS-v1's beta
descriptor is winsorized at 3 MAD, orthogonalized and z-scored, so the FMP hedge
neutralizes **a standardized rank, not the CAPM beta**. Whatever the
winsorization clipped, and whatever dispersion the standardization compressed,
survives the hedge. State it that way in the report: the residual is what the
descriptor does not span, which is a property of the design, not a defect in the
hedge.

Two candidates, both testable:

1. **The median fill.** Missing names are filled at the cross-sectional median
   0.691. Report **how many names per row were filled** and the residual beta
   with those names excluded. If the fill is doing most of the work, the column
   is measuring the fill, not the book.
2. **Model mismatch, the likely answer.** Test it directly: **recompute net beta
   using the pre-winsorization, pre-standardization beta values** and report how
   much of the 0.105 to 0.147 that accounts for. Also report the correlation
   between the raw beta and the finished descriptor, and the residual beta
   computed against XS-v1's own beta descriptor, so the gap between the two is
   measured rather than asserted.

Decompose it before the owner uses the column. The owner asked for realized beta
precisely because it is the measure the risk model cannot see, so it has to mean
what it claims.

### Also: `docs/research/STATUS_REPORT.md` is four sprints stale

It still covers E1 to E3 as "what this report covers" while the repository is at
E11 with a live paper loop. Bring it current, in the same voice and structure:
what the project is, the plan, what has actually been built through E11, the
findings, blockers and limitations, what the process taught, and what comes next.

**Every number read from an artifact**, with a traceability test in the shape of
`tests/test_e10_memo.py`, matching on the signed value. Two specifics to correct
while you are in there: the E1 survivorship figure is **365.10 bp**, not the 349
the older documents carry, and the three gates now have answers (RG-Data and G1
and G3 passed, RG-Signal returned all six NULL, RG-Operate not cleared).


## Run this cycle, then the owner picks

Owner approved 2026-09-23: the share-count diagnostic and the two-part floor row
are in, and the iteration direction is to be measured both ways. Run it.

The table is built and is good work. The min-position rows dominate top-N on both
n_eff and total error at matched name counts, so top-N is out. **Do not rebuild
the table from scratch**; add two columns and rerun it.

### E11-F5: there is no net-exposure column, and the sides are lopsided

Long/short counts: 90/118 at min $1,500, 63/92 at $2,000, **24/58 at $3,000**,
11/16 at $5,000, 55/95 at top-N 150, 72/128 at top-N 200. Dropping names
asymmetrically and then renormalizing **gross** to 1.0 does not preserve **net**
zero, and net dollar is a first-order risk for a book whose whole claim is market
neutrality. The post-hedge factor exposures being 1e-15 does not settle it: the
FMP hedge zeroes modeled factor exposure, not net dollar.

**Report net three ways on every row**, post-renormalization and
post-quantization:

1. **net dollar as a share of gross**
2. **long count against short count**
3. **the realized beta of the kept book against the market factor**

The third is the one that says whether the lopsidedness costs anything: a dollar
imbalance in low-beta names is a different object from the same imbalance in
high-beta names. Report all three; do not collapse them.

If a row's net is material, say what would restore it: a net constraint in the
re-sizing, or a different floor. **If the 24/58 and 55/95 style counts survive
the re-run, those rows are disqualified regardless of breadth.** The residual is
real dollar directionality the risk model cannot see, which is exactly what the
FMP hedge does not address.

### E11-F6: the floor is applied before renormalization, so it bites harder than stated

At min $1,500 the kept gross is 0.7515, so renormalizing scales by 1.33x and the
true post-renormalization minimum is about **$1,996**, not $1,500. Every row is
therefore conservative on breadth: names were dropped that would have cleared the
floor once the survivors were scaled up.

Apply the floor **iteratively to a fixed point**, and report the kept count both
**pre-iteration and post-iteration** so the breadth bought back is visible rather
than absorbed.

**The direction matters, and it is the opposite of the intuition.** The iteration
works by **admitting names back**: a name worth $1,200 pre-renormalization is
worth about $1,596 after a 1.33x scale-up and now clears a $1,500 floor. Admitting
it raises the pre-renormalization gross, which **lowers** the scale factor, which
makes every existing survivor **smaller**, not larger. So:

- breadth **rises**, which is the point
- the smallest positions get **smaller**, and new names enter sitting exactly at
  the floor
- so the per-name error tail, p90, will most likely **widen, not narrow**

The owner's expectation was that the iteration would lift the smallest survivors
and narrow the gap. It lifts the floor's reach, not the survivors. **Report p90
before and after the iteration on every row** so the direction is measured rather
than assumed. If p90 does widen, the choice is a genuine trade and the table
should say so plainly.


### A diagnostic that may dissolve the trade, flagged for the owner's veto

The dollar floor is probably the wrong instrument for the error tail. Whole-share
error depends on the **number of shares**, not the dollars: a $2,000 position in a
$20 stock is 100 shares and rounds to 0.5%, while the same $2,000 in an $800 stock
is 2.5 shares and rounds to 20%. A dollar floor treats those identically, which is
why min $1,500 can hold every name above $1,996 post-renormalization and still
carry a 9.08% p90.

So add, per row: the **median and 10th-percentile share count**, and a one-line
statement of what actually drives the p90 tail, small positions or high-priced
names. If it is price, the dollar floor is buying error control at a breadth cost
it does not need to pay.

And add **one extra row**, flagged so the owner can veto it: **min $1,500 dollars
AND a minimum share count of about 20**. If that row keeps most of min $1,500's
breadth while cutting p90 toward the $2,000 row's 5.59%, the owner's trade between
10.5% more IR and a fatter tail dissolves, and the answer is a two-part floor
rather than a bigger dollar floor. Same columns as every other row.

### Two small reporting items

- The "gross after renormalization" column is missing because it is 1.0 on every
  row. Say that rather than omitting it silently.
- The report cites the "670 floor", which rule 21 replaced with the relative
  rule: the full-run count must be at least the previous full-run count recorded
  in LOG.md, which was 680. 682 satisfies it and the removed test is named, so
  the rule is met; cite the rule that is in force.

### Then the owner picks

Rerun the table with the net columns, the iteration and the share diagnostic, and
present it. **The owner will not choose until the post-iteration table exists**,
because the p90 gap of 9.08% against 5.59% is large enough that the book held
differs noticeably from the book the risk model priced, which resurfaces as bias
in E12's attribution. My earlier provisional lean to min $1,500 stands only if the
net column clears it and the tail is addressable; the share-count row may replace
the question entirely.

**Do not choose. Do not re-derive Guard 1 until the construction is picked.**


## READ THIS FIRST: what is already done, and what this task is

The five fixes landed at ea821bc and are **not** to be redone: Fix 4 refuted,
Fix 1 filed as E11-F1, Fix 2 cap 0.40 to 0.10, Fix 3 NAV fallback removed, Fix 5
shares clamped to the close. Good work; leave them.

The previous run used an **older version of this file**. Three things changed
after it started and are now the task:

1. **NAV is $1,000,000, final.** Alpaca's paper funding field is capped at
   "$1 - $1,000,000", confirmed in the dashboard. Stop treating the $10m reset as
   pending: it is closed. Delete the $10m column from the reporting and do not
   size anything against it.
2. **The construction table is the decision** and was not built. It is the
   substance of this task. Specification below, unchanged.
3. **Slow-test markers** (Addition 5) were not done. Still wanted.

### Three findings from the review, to fix inside this task

**E11-F2. The kept book's average target dollar size is divided by the wrong
name count.** The report gives $547.81, which is `0.2734 x 1e6 / 499`. The kept
book has 27 names, so the figure is `/ 27` = about $10,126, an 18.5x
understatement. The gross-error metric beside it used the right positions, so
this is the reporting row, not the calculation. Fix it and check every other
per-name average for the same denominator slip.

**E11-F3. `sprints/E5/RESULTS.json` changed and the report does not say why.**
The diff shows 6 lines changed while Table 8 reports E5 at 0 verdicts changed.

**This is a stop, not a finding to carry forward.** Per STANDARDS rule 22, added
2026-09-22: an unexplained change to any stored-criteria file halts the task. If
it is a `data_hash` bump carried by the registry edit, record it through the
`revisions` block with both hashes and continue. **If anything else moved, stop
and report before doing anything else.**

**E11-F4. The book is never renormalized after dropping.** Kept gross is 0.2734,
so the book is 27% invested: it cannot meet the vol target, and the kept-book
quantization error of 0.57% is measured on positions smaller than would actually
trade. Renormalize to gross 1.0 after dropping, then quantize, as the table
specification requires.

**Watch this when you renormalize:** Guard 1 is now 0.10 of NAV and the largest
kept weight is 0.0326 at gross 0.2734. Renormalizing 27 names to gross 1.0
scales weights by about 3.66x, putting the largest near 0.119, which **breaches
the 0.10 cap on a legitimate book**. Re-derive Guard 1 against post-renormalization
weights, not pre. The guard must clear the largest legitimate target of whichever
construction the table selects.

### Also outstanding

- The 1 skipped test in the full run is not named. Name it and say why it skips.
- The construction table's rows must each report post-hedge exposure and idio
  share, which the 27-name result shows is the binding constraint: idio share
  0.8631 and max exposure 0.1458 at 27 names, against 1.0 and 5.8e-15 at 499.
  The rank prediction held; carry it into every row.

## NAV is $1,000,000, final. The construction table is the decision.

Settled 2026-09-22. **Alpaca's paper funding field is capped at "$1 - $1,000,000",
confirmed in the dashboard**, so option (a) is closed by a platform limit and the
documentation suggesting an arbitrary reset balance is stale. **We stay on
Alpaca**: switching brokers to buy breadth would mean rewriting the execution
layer to solve a sizing problem a parameter solves.

The dry run at $1m with a $5,000 floor kept **27 names of 499, gross 0.27**, and
breadth from about 460 to 27. That is not the book E8 constructed and E12 would
attribute almost nothing. So the threshold is no longer a contingency: **build the
table, the owner picks from it.**

### The table, at $1m on one close

Rows: minimum position size of **$1,500, $2,000, $3,000, $5,000**, plus two rows
for a different construction, **top N by alpha at N = 150 and N = 200**.

Columns, per row:

- kept names, dropped names
- **kept gross before renormalization and after**
- per-name quantization error **distribution: median and 90th percentile**, not
  only the total
- total gross error as a share of NAV
- **post-hedge max absolute factor exposure and idio share**
- **maximum post-renormalization weight**, as a share of gross
- both breadth numbers: naive `sqrt(460 / N_kept)` and the measured
  `sqrt(n_eff_full / n_eff_kept)` with n_eff computed the way E8 computes it

The maximum post-renormalization weight is what Guard 1 needs anyway, and it puts
**concentration beside breadth and error** so all three trade-offs are visible in
one row. A row can look good on breadth and error and still be a book nobody
would run.

### Four specification points, without which the rows are not comparable

**1. Renormalize to gross 1.0 after dropping, then quantize.** Gross 0.27 is the
tell that the previous run dropped names and left the book 27% invested. An
under-invested book cannot meet the vol target and its quantization error is
measured on positions smaller than the ones that would actually trade. So each
row drops, **renormalizes to gross 1.0**, then quantizes, and quantization is
reported **after** renormalization. Report kept gross both ways so the effect of
the renormalization is visible.

**2. Re-run the hedge on each subset.** The exact FMP hedge was computed on 499
names. Dropping names breaks it, so each row recomputes the hedge on its own
subset and reports post-hedge exposure and idio share. Without this the rows are
books with different factor neutrality being compared on error and breadth.

**3. Expect the $5,000 row to fail on rank, not on breadth.** XS-v1 estimates
about 18 factors, 7 styles plus 11 sectors plus the market. A 27-name book
hedging 18 factor exposures has 9 free dimensions left, so the FMP hedge is
close to rank-deficient and the "idio book" stops being idio. **A practical floor
on N is a healthy multiple of the factor count, not the quantization arithmetic.**
If a row cannot hedge, say so and report the exposure it actually achieves rather
than dropping the row.

**4. Define top N by alpha for a long/short book.** "Top N by alpha rank" is
ambiguous when the book is two-sided. Use **N names by absolute alpha, with the
sign of alpha setting the side**, so net stays near zero, then size the subset
with Procedure 6.3 and hedge it. State the long and short counts per row.

### How the two approaches are compared

**Dominates** means: strictly better or equal on **both** the measured n_eff and
total gross error, at comparable kept gross after renormalization. If top-N
dominates, it is the better answer and the minimum-position rule becomes a
**floor on top of it** rather than the whole mechanism. If neither dominates, say
so and present the trade rather than picking.

The owner picks from the table. Do not choose.

### Preconditions for the clock, unchanged

Threshold or construction chosen by the owner, gate reruns on two real closes
with `dry_run` still true, the Render dashboard live and showing a real dry-run
proposal, then the owner flips `dry_run` once and that act starts day 1.

### Addition 1: the quantization finding is not re-drawn

The breach gets its ID and **stays a finding at $10m too**, with the new numbers
stored beside the $1m ones, whatever they show. **The bar is not re-drawn to fit
the new NAV**: 0.5% of gross, or 5% of names on either leg, as written before any
number existed.

Reviewer's note on where to look: the error is driven by the **smallest**
targets, not the average, because a $19,400 average is 97 shares of a $200 stock
while a 0.02%-weight name is still only about $2,000. So report the **distribution**
of per-name rounding error, not just the total and the worst case, and report the
zero-share count against the smallest-weight decile. A total that lands under the
bar while the small tail is badly quantized is still worth stating.

### Addition 2: WITHDRAWN

The sigma hypothesis was tested and refuted, see Fix 4 below. **No sigma fix, no
E9 revisions, no E10 revisions, no memo or walkthrough re-execution, and the E6
cost reconciliation stays as stored at 2.56x.** The cascade warning that stood
here is withdrawn with it: nothing in `efb/costs.py` is being changed, so nothing
propagates to E9 or E10.

### Addition 3: a failed NAV read is a failed run

No fallback. A guard that silently restores design thresholds after a failed
account read **reports healthy while being blind, which is worse than no guard**.
A failed NAV read fails the run with a logged reason and **no orders**. Fix 3
below is amended accordingly: the `nav_source: fallback` option is withdrawn.


### Addition 4: the minimum-position item is promoted to now, and closed

This decision promotes the minimum-position open item from inherited to done.
**Close it with this decision** rather than appending it as a later item: state
in `docs/open_items.md` that E8's construction stack lacked a minimum-position
concept, that E11 now carries one as a registry parameter, and that a later
sprint revisiting construction should fold it back into E8 itself rather than
leaving it only in the live path. That last part is the residue, and it is small.

### The breadth consequence, and the formula to use

Effective breadth falls from roughly 460 names to whatever the threshold leaves.
The owner's bound is `sqrt(460 / N_kept)`, which at 200 names is 1.52, an IR
about 34% lower. **Record that as the naive N-based bound, and then measure the
one that governs.**

The fundamental law uses **N_eff**, not N, once forecast errors co-move, and E8
measured `n_eff` at about **140 against n_names about 460** (F8.5, F8.7). N_eff
is limited by residual co-movement, not by name count, so dropping the
smallest-weight tail may barely move it and the true haircut may be far smaller
than 1.52. Compute `n_eff` for the kept book the way E8 computes it and report
**both**: the naive `sqrt(460 / N_kept)` and the governing
`sqrt(n_eff_full / n_eff_kept)`. If the two disagree materially, that is the
answer to the question the open item was going to ask, and it belongs in the
report.

This is a documented null book, so no expected return is lost either way. What
must not happen is an E11 number meeting an E8 transfer coefficient without
stating that the executed book's breadth is reduced and by how much.

### Addition 5: mark the slow tests and split the paths

Per STANDARDS rule 21, added 2026-09-22 because 640 tests on every step is the
bottleneck. Mark anything over about two seconds with a pytest marker for the
slow path, so the fast subset is the default and the full run is deliberate.

Report the split: tests on each path, and how long each path takes.

Two things to get right. **The suite still never shrinks**, so a full run must
still execute everything; report the full-suite count and it must not fall below
670. And **verify the shared-module set by import graph** rather than trusting
the list in rule 21: `build`, `evaluate`, `costs`, `risk`, `size` and `models/`
are named there, but `registry`, `evidence`, `perf`, `universe` and `cov` also
look widely imported. Record the measured set; it is the trigger for a required
full run.

For this task specifically, a full suite is required anyway before `done`, and
again before anything touches the clock.

### Sequencing, revised: the flip starts the clock

**`dry_run` stays `true` for the whole of this task. DeepSeek never flips it.**
Day 1 is no longer set by a gate pass; it is set by the owner flipping `dry_run`
to `false` once, deliberately. That act starts the clock.

The order, and **Part B now comes before the clock, not alongside it**:

1. Fixes 1, 2, 3 and 5 land. Fix 4 is withdrawn. The share-count look-ahead is
   fixed here, not deferred.
2. **NAV settled.** The owner is attempting an Alpaca reset to $10,000,000,
   which the documentation says sets an arbitrary balance. If it succeeds,
   option (a) stands and the minimum-position threshold is sized against $10m
   instead of $1m. **Build the threshold to work at either NAV**: it is a
   registry parameter read at run time, never a constant tied to one balance,
   and the report states which NAV it was exercised at and what it gives at the
   other.
3. **The sanity gate reruns on two real closes, with `dry_run` still `true`.**
4. **Render deployed, and the D10 dashboard confirmed** reading from Supabase.
   This is now a **prerequisite for the clock**, not something built while the
   clock runs.
5. The owner flips `dry_run` to `false`. That is day 1. `live/clock.json`
   records the second void of the 2026-09-22 start, with its reason, and takes
   its new day 1 from the flip.

**What the dashboard must show before the owner will flip.** The dry-run
proposals it has already produced, rendered. A page that has never displayed a
real proposal is not confirmed working. So D10 must render a full day's actual
dry-run output, every panel populated from a stored proposal rather than from a
placeholder or an empty frame, and the report must show what it rendered: the
proposal date, which panels drew, and any panel that had no data and why.

## Goal

Get the loop onto live data and restart the clock (Part A), then put it on
Render behind a light, explainable live dashboard the owner can read from
anywhere, with state that survives a restart (Part B). The loop runs
indefinitely from now on; the thirty days become a reporting window, not the
life of the book.

## Standing decisions. Build on these, do not revisit.

- **`idio_momentum` through the full stack**, Procedure 6.3 plus the exact FMP
  hedge, documented null book.
- **PAPER ONLY.** "Live" throughout this task means live data and a
  continuously running loop, never real money. Real money remains a reserved
  decision the owner has not made. Alpaca **paper** keys only, never committed.
- **Alpaca: read the credit-trading-lab setup and decide there**, see B0.
- **NAV is $10,000,000 if Alpaca allows it, otherwise $1,000,000 with a minimum
  position size.** Read from the account, never hardcoded; a failed read fails
  the run. See below.
- **The universe stays split.** History frozen on the pinned table; live
  universe from the SPY archive. No universe reconstruction.
- **The clock restarts on live data and static days do not count.** The
  2026-09-22 start is void.

## New, from the owner 2026-09-22

**The book runs indefinitely.** E11's thirty trading days become the first
reporting window over a loop that does not stop. F11.1 to F11.3 are evaluated
on days 1 to 30 and the loop keeps running past them, so E12 has a growing
panel rather than a closed one. Nothing in the loop may assume an end date;
the window is a query over the history, not the life of the run.


## NAV is $1,000,000, and it is a design parameter

The owner's paper account is funded at **$1,000,000 USD**. This is not an
incidental fact; it sizes the book, both guards and the share quantization.

**NAV is read, not hardcoded.** The proposal stores the account equity Alpaca
reports at proposal time, with its source and timestamp, and $1,000,000 is the
initial design value. A hardcoded million drifts away from the truth the moment
P&L accrues, and the guards below are expressed as a fraction of NAV, so a
stale NAV silently moves the thresholds. Until the live account is reachable,
store the design value and label it as such.

**A proposal with a null NAV is a failed run, not a warning.** It must raise.
Every proposal stores `nav`, the expected cost in bp, and its dollar
equivalent, so the cost and both guards can be checked from the artifact alone.

### The two guards are re-derived at $1m, not carried over

Show the arithmetic that sizes each one, not just the number. State each in
**both** dollar and percentage form.

**Guard 2 is broken as it stands, and would block day 1.** The brake is
$200,000, sized as one full flip of a $100,000 gross book. At NAV $1m with
gross 1.0 the book is $1,000,000 gross, so a from-flat establishment trades
about $1,000,000 and **the existing brake trips on the first real run and the
book never establishes**. Scaled by the same rule it becomes $2,000,000. Note
that establishment and steady state are different sizes: establishment trades
full gross, a steady-state rebalance trades only the delta, roughly 39% turnover
on this signal, about $390,000. Decide whether one threshold clears
establishment while still catching a fat finger, or whether the brake needs an
establishment value and a steady-state value, and say which and why.

**Guard 1 probably cannot fire.** The cap is 40% of NAV, which at $1m is
$400,000 per position. Gross 1.0 across roughly 500 names puts the average
position near $2,000, so the cap sits about 200x the average and no legitimate
or plausible fat-finger order reaches it. A guard that cannot fire is not a
guard. Re-derive it from the realized distribution of target weights in the
first real proposal: it must sit clear of the largest legitimate target with
headroom, and low enough that an order ten times too large trips it. Report the
weight distribution you sized it from.

### Whole-share quantization

At $1m across roughly 500 names the average target is about $2,000, so rounding
to whole shares should be a small effect. Verify it rather than assume it. The
first real proposal reports:

- the gross-weight error introduced by rounding, in total and the per-name
  worst case
- the count of names whose target rounds to **zero shares**, long leg and
  short leg separately, and the effective name count that survives
- the same for the short leg, where a fractional share cannot be shorted either

Pre-registered bar, set before the numbers exist: if rounding moves gross by
more than 0.5%, or more than 5% of names round to zero on either leg, that is a
**finding with an ID**, and the book may need fewer names carried at larger
size. Do not adjust the bar after seeing the number.

## Credentials are the owner's to place

The owner creates the local `.env` and sets the Render environment variables.
DeepSeek does not.

DeepSeek writes `.env.example` listing every variable name with a one-line
comment saying what it is and where it comes from, confirms `.env` is
gitignored, and **never prints, echoes, logs or commits a key**. That includes
debug output, exception messages, the proposal and reconciliation artifacts,
the dashboard, and anything Render captures as a log line. Check it and say how
you checked.


---

# Part A: live data, the sanity gate, the clock

Unchanged from the previous task. A Render dashboard showing a static book is
worth nothing, so this ships first and alone if budget runs short.

## The problem in one line

Live prices are necessary but not sufficient. `descriptors`, `factor_returns`,
`specific_returns`, `factor_cov` and `specific_var` are all frozen at
2026-09-03 too, so a live-price book priced by a three-week-old Sigma is stale
in a second way, and nothing in the artifact says so.

## Cadence, and why

**Daily. Every model input extends one session per trading day, incrementally.**

Not a slower cadence, because any lag reintroduces exactly the staleness this
task exists to remove: a weekly Sigma is a five-day-old Sigma four days out of
five, and the proposal cannot tell you which. Daily is affordable because
XS-v1 is a cross-sectional fit, so one new session is one new WLS fit of 17
estimated columns, not a refit of 3,941 days, and `factor_cov` and
`specific_var` are rolling window estimates that update by appending a session.

**Incremental append only, never a refit.** Rows dated on or before 2026-09-03
come back byte-identical after every extension. Restating history would move
stored criteria, which is reserved. XS-v1 estimates its own factor returns from
the cross-section and does not read the Kenneth French series, so the daily
extension needs only prices, share counts and sectors, and is not blocked by
the French library ending 2026-07-31.

## Steps

**A1. Stop the clock and discard the static days.** Record in `live/clock.json`
that the 2026-09-22 start is void, with the reason. Nothing is deleted.

**A2. Extend the price and universe layer daily.** Session prices and share
counts from the vendor E1 uses; universe from the newest SPY archive file.
Fetch and archive a fresh SPY holdings file and a fresh Wikipedia constituents
snapshot each session, both dated, both into `data/VERSION.json` and the
evidence snapshot. The 2026-08-05 to 2026-09-18 seam stays documented.

**A3. Extend the model artifacts daily.** Append one session to `descriptors`,
`factor_returns` and `specific_returns` by fitting that day's cross-section
under the frozen XS-v1 specification, then roll `factor_cov` and `specific_var`
forward one session. The specification does not change: this extends the
champion, it does not re-estimate or re-declare it.

**A4. Make staleness visible in the artifact.** Every proposal stores the as-of
date of every model input: prices, shares, universe, sectors, descriptors,
factor_returns, specific_returns, factor_cov, specific_var, plus a single
`max_input_staleness_days`. Staleness is read, never inferred.

**A5. The day-1 sanity gate. The clock does not start until this passes.** Run
the loop on **two consecutive real closes** and confirm the proposals differ.
Print and store the weight turnover, `0.5 * sum(abs(w_t - w_{t-1}))`, with the
definition stated. Identical proposals on two different closes means the data
is not live and the gate fails. Report the number either way; tune nothing.

**A6. The cost item.** Store `nav` beside `expected_establishment_cost_bps`,
and show the arithmetic reaching 75.34 bp decomposed into spread, impact,
commission and borrow, each in bp, with the notional and average per-name trade
size stated. Reconcile against E6's stored 10.53 bp per rebalance, which is a
**steady-state rebalance** trading only the delta against an **establishment**
trading full gross from flat plus the hedge book. The ratio to explain is about
7.15x. **If it will not reconcile, that is a finding with an ID and a
mechanism; do not adjust either number to close the gap.**

**A7. Reframe to a continuous loop.** Remove any assumption of an end date.
`live/clock.json` keeps day 1 and marks the thirty-day window as a reporting
slice with its end date, while the loop's own run condition is open-ended.

---

# Part B: Render, persistent state, and the live dashboard

## B0. Alpaca: read credit-trading-lab's setup first, then decide

**Read how credit-trading-lab connects to Alpaca before writing any of this.**
`/Users/amankesarwani/PycharmProjects/credit-trading-lab`: `execution/`,
`scripts/`, `render.yaml`, `.streamlit/`, and wherever the keys are loaded and
the client is built. Reuse that pattern rather than inventing one; it already
works in production on Render.

**Then resolve the account question and record the answer.** Does EFB reuse the
existing paper account or does it need its own? Find out from Alpaca's own
documentation or dashboard whether a second paper account can be created under
the existing login, or whether it needs a second login, and say which you used.

The reasoning that should decide it: two strategies sharing one paper account
share positions, cash, NAV and fill history. E12 attributes P&L **from
holdings**, so credit-trading-lab's fills would land inside EFB's attribution
and neither book's numbers would be its own. Reconciliation of forecast against
outcome would also be reconciling against someone else's trades. So the default
is a **separate paper account**, and reusing the existing one needs a reason
better than convenience. Whatever you choose, EFB's positions must be provably
disjoint from credit-trading-lab's; say how you check that.

Use environment variable names distinct from credit-trading-lab's so the two
cannot be crossed by a stale shell. Paper keys only. Nothing committed.

## B1. State that survives a restart: the shared Supabase project, schema `efb`

**AMENDED 2026-09-22, mid-flight. Read this before writing any storage code.**

The Supabase free tier allows two projects and both are in use, so E11 **shares
the existing project with credit-trading-lab and owns the schema `efb`**. Every
live table lives in `efb`. Never `public`, never the credit lab's schema.

**Connect over direct Postgres, not PostgREST.** Use the session-pooler
connection string under a distinct variable, `EFB_SUPABASE_DB_URL`, with
`EFB_DB_SCHEMA=efb` beside it, so a stale shell cannot cross the two projects.
The reason to prefer the direct connection: PostgREST only serves schemas that
have been added to "Exposed schemas" in the project's API settings, which is a
dashboard change on a project the credit lab also uses and it widens that
project's public API surface. A direct Postgres connection reaches any schema
with no dashboard change and no shared surface. The `EFB_SUPABASE_URL` and
`EFB_SUPABASE_SECRET_KEY` variables already in `.env.example` are the PostgREST
path; keep them only if something actually needs them, and say what.

Rules:

- `CREATE SCHEMA IF NOT EXISTS efb` on first run. Every DDL and DML statement
  is schema-qualified `efb.<table>`, or runs under `search_path=efb`. A test
  asserts that no statement in the codebase targets `public` or an unqualified
  table name.
- **The first run reports which schema it wrote to and the row count per
  table.** Not a log line that scrolls past: a stored artifact and a line in
  the report.
- Live series only: proposals, orders, fills, reconciliation, NAV and realized
  P&L, keyed by date. Research artifacts stay in git and the evidence snapshot.

**Say so if it is not clean.** On a shared free-tier project this separation is
a naming discipline, not a permission boundary: the same database role can see
both schemas, so the isolation is only as good as the schema-qualification
test. If targeting a non-default schema turns out to need dashboard changes,
shared-role grants, or anything that touches the credit lab's data, **stop and
report it**. The owner will move to Neon or Render Postgres instead. Do not
work around it.



Render's filesystem is ephemeral and a free web service spins down, so the
previous task's "state on local artifacts, no Supabase" decision does not
survive the move. A loop that must run indefinitely needs a store that outlives
the container. **Use Supabase**, which the owner already runs for
credit-trading-lab, for the live series only: proposals, orders, fills,
reconciliation, NAV and realized P&L, keyed by date. Research artifacts stay
where they are, in git and the evidence snapshot. Credentials come from the
environment and are never committed. If you judge a different store better,
say why before building it.

## B2. Deploy on Render

Follow the shape of `/Users/amankesarwani/PycharmProjects/credit-trading-lab`:
`render.yaml`, `.streamlit/`, the service layout and the cron wiring. Two
services: the **daily cron** running the evening and morning jobs, and the
**dashboard web service**. Health check, and a clear failure when a required
environment variable is missing.

## B3. The live dashboard, and what it is not

**It does not carry D0 to D9.** The full research dashboard stays local; the
Render app reads only the live series from Supabase plus a small current-book
snapshot. If a panel needs a large parquet, it does not belong here. State the
memory and cold-start cost in the report.

Build it for someone deciding whether the book is doing what it was built to
do. Lead with the answer. One idea per panel. Every number with its n and its
units. The null-book framing impossible to miss.

**What it shows:**

1. **Status.** Is the book live, when did it last run, how stale is every input
   (from A4), day count, and the thirty-day window's position inside it.
2. **Tracking metrics.** P&L cumulative and daily, realized vol against the 10%
   target, Sharpe with its standard error and its t, drawdown, turnover, cost
   paid against cost expected. No skill claimed unless t exceeds 2.
3. **Factor breakdown, several dimensions.** Exposure and P&L by style factor,
   by sector, and by VIX regime, before and after the hedge, so the hedge's
   effect is visible rather than asserted.
4. **Hedge panel.** Which hedge is on, which factor each leg neutralizes, the
   exposure before and after, the names and notional it costs, and **why**.
5. **The trade explanation, per name.** For every position and every trade
   today: the name, its alpha score and rank, its idio vol, the target weight
   and where Procedure 6.3's sizing got it, the current weight, the trade, and
   **why this trade today**: alpha moved, risk moved, the hedge moved, or it
   drifted past a band. Say which. A trade with no stated reason is a bug.

## B4. README

Update `README.md` and push. It stops at E2, shows E3 unchecked, and quotes
E1's survivorship bias as the superseded 349 bp. Bring it current: E1 to E10
built, the gates passed and not passed, the registry with XS-v1 provisional
champion, the live book and its Render link, and where the handoff files live.
**Every number read from an artifact**, with a traceability test in the shape
of `tests/test_e10_memo.py`, matching on the signed value.

## Acceptance

1. `make test` at least 640 tests, `make lint` clean, `make verify-evidence`
   exits 0.
2. Rows dated on or before 2026-09-03 in `descriptors`, `factor_returns` and
   `specific_returns` are byte-identical before and after an extension.
   Asserted by a test, hashes printed.
3. Every proposal carries an as-of date for all nine inputs plus
   `max_input_staleness_days`.
4. The sanity gate ran on two consecutive real closes, the proposals differ,
   and the turnover is stored with its definition. If it failed, the clock did
   not start and the report says which input is not advancing.
5. `nav` stored beside the cost; the four bp components sum to the total; the
   E6 reconciliation is closed with arithmetic or recorded as a finding.
6. Nothing in the loop assumes an end date. Show the run condition.
7. The Render dashboard loads without reading any file over 5 MB. State the
   largest read and the cold-start time.
8. Every open position and every trade on the dashboard carries a stated
   reason from B3 item 5.
9. README contains no number absent from an artifact, proven by its
   traceability test, and is pushed.
10. No credential, key or token in any committed file, including
    `render.yaml`. State how you checked.
11. No F1.x to F10.x verdict changes. Print the count per sprint.
12. No em dashes in any file touched.
13. **Every proposal stores a non-null `nav`**, the expected cost in bp and its
    dollar equivalent. A null NAV raises and the run fails; prove it with a
    test that a null-NAV proposal is rejected, not warned about.
14. Both guards are re-derived at $1m, each stated in dollars and as a
    percentage, each with the arithmetic that sized it shown. Guard 2 clears a
    full from-flat establishment of about $1,000,000. Each guard still has a
    test that fires it.
15. The first real proposal reports the whole-share quantization effect: total
    and worst-case gross-weight error from rounding, and the count of names
    rounding to zero shares on the long leg and the short leg separately. If it
    breaches the pre-registered bar, it is recorded as a finding with an ID.
16. `.env.example` exists with every variable named and commented, `.env` is
    gitignored, and no key appears in any committed file, artifact, log line or
    dashboard panel. State how you checked each surface. Every value in
    `.env.example` stays empty or an obvious placeholder; a real key there is a
    committed leak.
17. WITHDRAWN with Fix 4. No E9 or E10 numbers move, so no memo or walkthrough
    is re-executed.
17b. `dry_run` is `true` in every committed configuration and in every run in
    this task. DeepSeek does not flip it and does not set a new day 1.
17c. The minimum-position threshold is a registry parameter that works at either
    NAV. The report states which NAV it ran at and what the threshold gives at
    the other.
17e. Slow tests are marked, the fast and full paths are both reported with test
    counts and runtimes, the full-suite count is at least the previous full-run
    count in LOG.md with any decrease explained, and the measured shared-module
    set is recorded.
17d. D10 renders a full day's stored dry-run proposal with every panel populated
    from it. The report names the proposal date, the panels that drew, and any
    panel with no data and why.
18. The Alpaca cap question is answered with its source: balance or initial
    funding, and whether a reset to a higher balance is possible.
18b. If $10m is unreachable: the minimum position size is stored as a **registry
    parameter**, and the threshold, kept name count, dropped count and the new
    quantization distribution are all stored and reported.
18c. Both breadth numbers are reported: the naive `sqrt(460 / N_kept)` and the
    governing `sqrt(n_eff_full / n_eff_kept)` with `n_eff_kept` computed the way
    E8 computes it.
18d. `docs/open_items.md` records the minimum-position item as **closed by this
    decision**, with the residue named: folding it back into E8's construction
    stack rather than leaving it only in the live path.
19. Every live table is in schema `efb`. No statement targets `public` or an
    unqualified name, asserted by a test. The first run stores and reports the
    schema written to and the row count per table.

## Stop only if

- The sanity gate fails. Stop, do not start the clock, report which input is
  not advancing.
- Extending an artifact would restate any row dated on or before 2026-09-03.
- Anything would need real money, the universe reconstruction, or a change to
  the XS-v1 specification.
- **Any stored-criteria file changed and you cannot account for the change.**
  Halt. A `data_hash` bump goes through a revisions block with both hashes;
  anything else is a stop before further work.
- **Any artifact, log line, error message or dashboard panel could contain a
  key.** Stop immediately, do not commit, and report the surface.
- A proposal cannot obtain a NAV. Do not substitute a guess; report it.
- Targeting schema `efb` needs a dashboard change, a shared-role grant, or
  anything touching credit-trading-lab's data. Stop and report; the owner will
  move to Neon or Render Postgres.
- Part B cannot be finished. Ship Part A, commit it, and say what is left.
  Do not leave Part A half done to reach Part B.

Everything else you decide and record: the Supabase schema, the Render plan and
service names, the retry policy on a failed fetch, and the dashboard layout.

## Report back

**Table 1, the clock.** Void start and reason, new day 1, window end date,
the loop's open-ended run condition.

**Table 2, the sanity gate.** The two closes, weight turnover, n names each,
whether the proposals differ.

**Table 3, staleness.** Per proposal, the as-of date of all nine inputs and
`max_input_staleness_days`.

**Table 4, incremental integrity.** Per extended artifact: rows before, rows
after, hash of the pre-2026-09-04 block before and after.

**Table 5, the cost.** nav, gross, n names, average per-name trade size, the
four bp components, the total, and the E6 reconciliation or its finding ID.

**Table 6, Render and the database.** Services, plans, largest file read,
cold-start seconds, peak memory. Then: the schema written to, the row count per
table after the first run, the connection method (direct Postgres or
PostgREST), and confirmation that no statement targets `public`.

**Table 7, the trade explanation.** A sample of five positions with alpha
score, rank, idio vol, target weight, current weight, trade, and stated reason.

**Table 8, no-change.** Per sprint E1 to E10: criteria, verdicts changed.

**Table 9, the guards at $1m.** Per guard: old value, new value in dollars and
as a percentage of NAV, the arithmetic that sized it, whether it can fire
against a legitimate order, and the test that fires it.

**Table 10, quantization.** Total and worst-case gross-weight error from
rounding, names rounding to zero on the long leg and the short leg, effective
name count, NAV used, average target dollar size, and whether the
pre-registered bar was breached.

**Include the Verification section per STANDARDS.** Rules 19 and 20.
