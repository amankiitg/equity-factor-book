# Sprint E11, Part 4: the owner's deploy steps, corrected

**What this part corrects.** The earlier steps were wrong in order (they granted
on schema `efb` before anything created it) and thin in three places (no SQL for
the roles, no answer on runtime DDL, no notification variable). This report
gives the owner a step list that runs in the right order, the SQL for both roles
as text, the answer that the live runtime issues no DDL so a DML-only write role
is enough, and the two additions Part 3b needs. The SQL editor is the primary
provisioning path; the account-wide Management token is the alternative and
needs an explicit `--apply`.

Nothing in this part was executed against the project. No role, no grant, no
value, and no statement of mine touched Supabase, and the SQL below is text for
the owner to run.

## The owner's steps, in order

1. **Create the schema and the tables first.** Open
   `https://supabase.com/dashboard/project/<ref>/sql/new`, paste
   `live/supabase_schema.sql`, run it. That creates schema `efb` and its
   **18 tables** (the 8 live-series tables, the 9 appendix tables and
   `run_status`). No token, no API call. `scripts/provision_supabase.py` now
   prints exactly this instruction and sends nothing unless asked.
2. **Create the two roles and grant them, second.** Paste
   `live/supabase_roles.sql` after replacing both password placeholders. The
   step is second because a grant on a schema that does not exist yet fails,
   which is the error the earlier order produced. Nothing outside schema `efb`
   is touched.
3. **Test both connection strings locally before pasting them into Render.**
   The commands are below, and the write-role test is the one that settles the
   psycopg typing question Part 3 and Part 3b both flagged.
4. **Set the variables on each Render service** (values in the Render dashboard,
   never committed):

   | service | variables |
   | --- | --- |
   | `efb-live-dashboard` (web) | `EFB_SUPABASE_DB_URL` = **the read-only role's** string; `EFB_DB_SCHEMA` = `efb` |
   | `efb-live-daily` (cron) | `EFB_SUPABASE_DB_URL` = **the write role's** string; `EFB_DB_SCHEMA` = `efb`; `EFB_ALPACA_PAPER_API_KEY`; `EFB_ALPACA_PAPER_SECRET_KEY`; `EFB_DRY_RUN` = `true`; `EFB_NOTIFY_SLACK_WEBHOOK_URL` |

   The dashboard gets no Alpaca keys, no write role's string, and no webhook.
   The cron gets no read-only string. Neither service ever gets
   `EFB_SUPABASE_ACCESS_TOKEN` or `EFB_SUPABASE_SECRET_KEY`.
5. **Deploy** both services from `render.yaml`.
6. **Local `.env`** for local runs: `EFB_SUPABASE_DB_URL`,
   `EFB_DB_SCHEMA=efb`, `EFB_ALPACA_PAPER_API_KEY`,
   `EFB_ALPACA_PAPER_SECRET_KEY`, `EFB_DRY_RUN=true`,
   `EFB_NOTIFY_SLACK_WEBHOOK_URL`, plus `EFB_SUPABASE_PROJECT_URL` for the
   provisioning script. `EFB_SUPABASE_ACCESS_TOKEN` is only for the token path.
7. **Place the webhook and confirm the test notification.** Put the Slack
   incoming webhook URL on the cron service only. Then trigger one cron run
   (Render's "Run now" on the cron job) and **confirm the message arrived**.
   It should read `EFB live book <close>: ok, the run completed` with the orders
   and staleness lines under it. Until that has been seen once, the notification
   path is unproved on both sides.
8. **Confirm remaining-plan item 4c.** After the deploy, a dry run writes a real
   proposal to `efb` (`proposals` and `positions` rows) and the Render page shows
   it under the construction label from its own fields. A page that has never
   shown a real proposal is not confirmed, and I have not deployed.

## The SQL for both roles, as text

`live/supabase_roles.sql`, unexecuted:

```sql
create role efb_writer login password 'REPLACE_WITH_A_LONG_RANDOM_PASSWORD';
create role efb_reader login password 'REPLACE_WITH_A_DIFFERENT_LONG_RANDOM_PASSWORD';

-- The cron writes the live series, the appendix and the run status.
grant usage on schema efb to efb_writer;
grant select, insert, update, delete on all tables in schema efb to efb_writer;

-- The dashboard only reads.
grant usage on schema efb to efb_reader;
grant select on all tables in schema efb to efb_reader;

-- Future tables inherit those grants. Run this as the role that creates the
-- tables, which is `postgres` in the SQL editor, because default privileges
-- attach to the creating role and not to the schema.
alter default privileges in schema efb
  grant select, insert, update, delete on tables to efb_writer;
alter default privileges in schema efb
  grant select on tables to efb_reader;
```

Notes the owner should have:

- **No `serial` and no `identity` anywhere in the schema**, so no sequence
  grant is needed; `grep -c "serial\|identity" live/supabase_schema.sql` is 0.
- **`ALTER DEFAULT PRIVILEGES` attaches to the creating role.** The SQL editor
  runs as `postgres`, so running this there covers the tables the editor
  creates. If the owner later creates tables as another role, that role needs
  its own default privileges statement.
- **Nothing is granted on `public`, on the database, or on any other schema**,
  so the credit lab's objects are untouched. A test asserts the file contains no
  `schema public`, no `on database`, no `superuser` and no `bypassrls`.
- To generate a password:
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## Does the store issue DDL at runtime? No.

This is the reviewer's question from B1, and the answer is measured rather than
asserted:

- The only two statements `live/store.py` runs are
  `live/store.py:128` `cursor.executemany(...)` with the `INSERT ... ON CONFLICT`
  built by `_upsert_sql`, and `live/store.py:149`
  `cursor.execute(f"SELECT * FROM {_qualified(table)} ORDER BY 1")`. Both are
  DML.
- `live/supabase_schema.sql` holds every DDL statement in the repository: one
  `create schema if not exists efb` at **line 8** and 18
  `create table if not exists`, and it is applied by the provisioning step, not
  by a run.
- A test scans every module in `live/` and `scripts/` for
  `create table|create schema|create role|alter table|alter default|grant
  <privilege>|revoke|drop table|drop schema|drop role` and asserts the list is
  empty, and a second test asserts the store's own source holds no DDL.

So the runtime never issues the `create schema if not exists efb` that B1
described, and provisioning covers it: **the schema is owned by whoever runs the
provisioning SQL (`postgres`), and the write role needs DML only.** If the
reviewer intended the runtime to create the schema, that intent is not
implemented and should not be: a DML-only role fails on it.

## Testing each connection string before Render

The step matters more than usual here, because two things are still unproved
from this machine: the Postgres write path in general, and the parameter typing
below.

**The username format.** Supabase's pooler takes a custom role as
`<role>.<project-ref>`, so the writer's string is
`postgresql://efb_writer.omnsjnosbaiqkrmnknqw:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`,
and the reader's is the same with `efb_reader`. A direct connection
(`db.<ref>.supabase.co:5432`) uses the plain role name. **Use the session pooler
on port 5432 for both services**: see the transaction pooler warning below.

**The read role, which must read and must not write:**

```bash
source .env
.venv/bin/python - <<'PY'
import os, psycopg
with psycopg.connect(os.environ["EFB_SUPABASE_DB_URL"]) as conn:
    with conn.cursor() as cur:
        cur.execute("select current_user, count(*) from efb.proposals")
        print("read ok:", cur.fetchone())
        try:
            cur.execute("insert into efb.run_status "
                        "(run_date, job, target_close, status) "
                        "values ('2000-01-01', 'probe', '2000-01-01', 'probe')")
            print("PROBLEM: the read role could write")
        except psycopg.errors.InsufficientPrivilege:
            print("write refused, as it should be")
    conn.rollback()
PY
```

**The write role, which must write, and which settles the typing question:**

```bash
source .env
.venv/bin/python - <<'PY'
import os, psycopg
with psycopg.connect(os.environ["EFB_SUPABASE_DB_URL"]) as conn:
    with conn.cursor() as cur:
        cur.execute(
            "insert into efb.run_status (run_date, job, target_close, status, "
            "inputs, notify_failed) values (%s, %s, %s, %s, %s, %s) "
            "returning target_close",
            ("2000-01-01", "probe", "2000-01-01", "probe", '{"probe": true}', False),
        )
        print("write ok:", cur.fetchone())
    conn.rollback()
    print("rolled back: nothing was left in the table")
PY
```

That insert carries a `date`, a `jsonb` and a `boolean` as Python strings,
booleans and dicts, which is exactly what `store.upsert` sends. If Postgres
refuses the text-typed parameters that psycopg 3.3.6 produces
(`StrDumper.oid` is 25, Part 3's report), it fails here with
`column "target_close" is of type date but expression is of type text`, on the
owner's machine, with the table empty and the transaction rolled back. If it
succeeds, the whole live series is proved writable and the flag from Parts 3 and
3b can be closed.

**The transaction pooler is a trap here.** `psycopg.connect` defaults to
`prepare_threshold=5`, so it starts using server-side prepared statements after
five executions of the same statement, which the transaction pooler on port 6543
does not support. And the setting **cannot be given in the connection string**:

```text
$ .venv/bin/python -c "import psycopg; psycopg.conninfo.make_conninfo(
    'postgresql://efb_writer.ref:pw@host:5432/postgres?prepare_threshold=-1')"
psycopg.ProgrammingError: invalid URI query parameter: "prepare_threshold"
```

So if 6543 is ever wanted, `store.get_connection` has to pass
`prepare_threshold=None` in code, and that is a change plus a test, not a
variable. Until then the session pooler on 5432 is the answer, and it is what the
step list says.

## The two additions Part 3b needed

**The notification variable** is already in `render.yaml` on the cron service
only (`sync: false`), and in `.env.example` with an empty value; the credential
check in `tests/test_e11_render.py` covers both files and asserts no hook path is
committed. The owner's confirmation step is step 7 above.

**The confirmation is part of the deploy**, not an afterthought: the task says
the owner receives one test notification from the deployed cron before the gate
evenings, and that until then the path is unproved. I cannot trigger it from
here, and the message's own absence is the alarm, so the last thing the owner
does is prove the alarm works.

## What could not be verified

- **No Postgres was reachable**, so the roles SQL was never executed, and
  neither `create role` nor the grants have been syntax-checked by a server.
  Step 3 is where the owner finds that out, with the negative control for the
  read role and a rolled-back write for the writer.
- **The pooler username format is from Supabase's documentation, not measured
  here.** Step 3 fails loudly on the first connect if it is wrong.
- **The typing question above stays open** until step 3 runs on a machine that
  can reach the database. I would not deploy on that flag being unresolved and
  the report says so; it is one command, and it is the first thing the write-role
  test does.
- The `--apply` path through the Management API is exercised in tests against a
  stand-in `urlopen`, never against Supabase.

## Tests, 8 in `tests/test_e11_deploy.py`

1. the roles file grants on schema `efb` four times and nowhere else, with no
   `public`, no database grant, no `superuser` and no `bypassrls`;
2. the roles file carries placeholders, never a password;
3. the roles step comes after the schema step: the schema file holds DDL, the
   roles file holds none, and its header names the file to run first;
4. no module in `live/` or `scripts/` contains DDL, so the runtime cannot need
   more than DML;
5. the store runs two statements, both DML, and its source holds no DDL;
6. the provisioning script prints the SQL editor path with the schema file
   before the roles file, and sends nothing without `--apply`, token or not;
7. with `--apply` the Management API receives both files in one statement and
   the token never appears in the output; without a token, `--apply` sends
   nothing and returns 1.

## Verification

Per step, the selection is every test touching what changed. The full suite is
not required at this step: no `efb/` module changed, no artifact was rebuilt, the
clock is not touched, and the state that sets the task `done` is Part 5's, whose
run carries this part too.

```text
$ make lint
.venv/bin/ruff check efb dashboard live tests
All checks passed!
.venv/bin/mypy efb
Success: no issues found in 33 source files
.venv/bin/black --check efb dashboard live tests
All done! ... 170 files would be left unchanged.

$ .venv/bin/python -m pytest tests/test_e11_deploy.py tests/test_e11_render.py \
    tests/test_e11_notify.py -q --tb=short
34 passed, 1 skipped in 1.51s

$ make verify-evidence
evidence OK
```

### Headline numbers, file and key

| number | file and key |
| --- | --- |
| 18 tables, one `create schema if not exists efb` at line 8 | `live/supabase_schema.sql`, `grep -c "create table if not exists"` |
| zero sequences | `live/supabase_schema.sql`, `grep -c "serial\|identity"` is 0 |
| four grants on schema `efb`, none elsewhere | `live/supabase_roles.sql`; asserted by `tests/test_e11_deploy.py::test_the_roles_file_grants_only_on_efb` |
| no DDL in any runtime module | `tests/test_e11_deploy.py::test_the_live_runtime_issues_no_ddl` |
| the store's two statements, both DML | `live/store.py:128` and `live/store.py:149` |
| `prepare_threshold` defaults to 5 and cannot ride in the URL | `psycopg.connect` signature and the pasted `ProgrammingError` |
| the SQL editor path prints first and sends nothing | `scripts/provision_supabase.py::main`, asserted in test 6 |
| the webhook on the cron only | `render.yaml`, second service |
| 8 tests | `tests/test_e11_deploy.py` |

### git diff --stat from `base_commit` (dd41d9b)

This part's own files, from Part 3b's commit `9a46ea6`, with
`git add -N live/supabase_roles.sql tests/test_e11_deploy.py` first so the new
files appear:

```text
$ git diff --stat 9a46ea6 -- handoff/REPORT.md live/supabase_roles.sql \
    scripts/provision_supabase.py tests/test_e11_deploy.py
 handoff/REPORT.md             | 566 ++++++++++++++++++++++--------------------
 live/supabase_roles.sql       |  42 ++++
 scripts/provision_supabase.py | 124 +++++----
 tests/test_e11_deploy.py      | 166 +++++++++++++
 4 files changed, 595 insertions(+), 303 deletions(-)
```

From the revision's `base_commit` (dd41d9b), which also carries Parts 2, 3 and 3b
and the reviewer's `ef67024`:

```text
$ git diff --stat dd41d9b
 ...
 23 files changed, 3271 insertions(+), 389 deletions(-)
```

Nothing else in the repository changed: no research artifact, no construction
table, no proposal, no notebook.

### Yes or no, each with evidence

1. **Any two rows or two estimators identical.** No. No row of any table was
   written: the SQL in this part is text for the owner, and the tests write no
   row.
2. **Any exception caught and skipped, or fallback taken, with counts.** Yes,
   one, and it is the designed fallback: `scripts/provision_supabase.py::_apply`
   catches a Management API failure, prints it, tells the owner to use the SQL
   editor steps already printed above it, and returns 1. The token path is the
   alternative, so falling back to the primary path is the correct behaviour
   rather than a swallowed error. The test suite asserts that nothing is sent
   without `--apply`, so this path cannot fire by accident.
3. **Any criterion reworded or replaced by a different test.** No stored
   criterion was touched. No existing test was edited in this part; the new
   file is additive.
4. **Any criterion that passes by construction.** One, declared: test 5 asserts
   the store's two `cursor.execute` calls are DML by reading the source and
   matching text, which cannot prove at run time that no other statement
   executes. Test 4's scan of the runtime modules is the other half of the same
   claim, and both are text-level. What makes the pair worth having is that the
   reviewer's question is exactly a text-level question about the repository,
   and the answer is now falsifiable by a diff rather than by memory.
5. **Any number that moved by a factor of 10 or more from its previous stored
   value.** No. No stored number moved. The table count in the steps is new
   (18, where the earlier list said eight), and it is a different quantity, not
   a moved one.
6. **Any stored number typed into a notebook.** No notebook was opened, edited
   or executed.
7. **Any earlier verdict changed.** No. The direct-Postgres decision, the
   no-PostgREST rule, the read-only dashboard credential and the "no Exposed
   schemas change" finding all stand. The step order's correction is a defect
   fix in documentation, not a changed verdict.

### Anything decided that the reviewer might disagree with

**The provisioning script no longer applies SQL unless asked.** It used to apply
through the Management API whenever a token happened to be in the environment,
and print the SQL when it was not. The reviewer asked for the SQL editor to be
the primary path and the token the alternative, so the editor path prints first
and always, and the API path needs `--apply`. The consequence is that an owner
who has a token and expects the old behaviour gets a printed instruction instead
of an application; that is the correction the review asked for, and the report
says it plainly.

**The session pooler on 5432 is the recommendation, not 6543.** The transaction
pooler would need a code change because psycopg's default prepared statements
are unsupported there and the setting cannot be carried in the URL. I would
rather tell the owner to use 5432 than ship a half-working 6543 path, and if the
reviewer wants 6543 supported, it is one argument in `store.get_connection` plus
a test.

**I did not create the roles.** The reviewer's earlier rule stands: roles and
grants on the shared project are the owner's to place, and this part only writes
the SQL down.
