# Key rotation: every credential, where it lives, and the order to change it

**Nothing here has been rotated.** This is the checklist, in the order that keeps a
run working. Variable names only; no value appears in this file or in the repository.

## The rule the order follows

For every credential: **create the new one, put it in every consumer, prove it works,
and only then revoke the old one.** A rotation that revokes first has a window in
which the 22:30 evening or the 15:30 morning cannot start. And never rotate inside
**15:25-15:45 UTC** or **22:25-23:00 UTC** on a weekday: those are the two runs.

The system has four credential families with a live consumer (database, Alpaca,
Resend, R2) and one deploy credential (Cloudflare wrangler). The order below goes
from the one whose failure is loudest-but-safest (a seed read, refused before
anything is priced) to the one whose failure sends mail or orders.

## What exists, and where it is configured

| credential | variables | configured in | used by |
|---|---|---|---|
| **Database** | `EFB_SUPABASE_DB_URL` (the write role's connection string; the password is inside it) | Render (`render.yaml`, `sync: false` → dashboard), local `.env` | every evening and morning step; `live/store.py` |
| Database (provisioning only) | `EFB_SUPABASE_PROJECT_URL`, `EFB_SUPABASE_ACCESS_TOKEN`, `EFB_SUPABASE_SECRET_KEY` | local `.env` only | `scripts/provision_supabase.py --apply`, tests. **Never on Render** (`tests/test_e11_render.py` asserts it) |
| **Alpaca (paper)** | `EFB_ALPACA_PAPER_API_KEY`, `EFB_ALPACA_PAPER_SECRET_KEY`, `EFB_ALPACA_ACCOUNT_ID` | Render, local `.env` | order submission and the account read; `live/alpaca.py`. The account id is checked against the key every run |
| **Resend (email)** | `EFB_RESEND_API_KEY` | Render, local `.env` | the evening and morning messages; `live/notify.py`. `EFB_NOTIFY_EMAIL_FROM` / `EFB_NOTIFY_EMAIL_TO` are addresses, not secrets, but they must move together with it |
| Slack (optional) | `EFB_NOTIFY_SLACK_WEBHOOK_URL` | Render only, when set | `live/notify.py` |
| **R2 seed bucket** | `EFB_SEED_R2_ACCOUNT_ID`, `EFB_SEED_R2_BUCKET`, `EFB_SEED_R2_ACCESS_KEY_ID`, `EFB_SEED_R2_SECRET_ACCESS_KEY` | Render has the **read-only** token; local `.env` has the **write** token | the seed is downloaded at the start of every run (`live/seed.py`); the local one also pushes (`scripts/push_seed.py`) |
| **R2 snapshot bucket** | `EFB_R2_ACCOUNT_ID`, `EFB_R2_BUCKET`, `EFB_R2_ACCESS_KEY_ID`, `EFB_R2_SECRET_ACCESS_KEY` | **Render only** (not in this machine's `.env`) | the page's snapshot upload; `live/snapshot.py` |
| **Cloudflare deploy** | wrangler OAuth token, `~/.wrangler/config/default.toml` (no env var) | this machine | `npx wrangler deploy` in `web/` |
| **Cloudflare Access** | `ACCESS_TEAM_DOMAIN`, `ACCESS_AUD` - **plain vars in `web/wrangler.jsonc`, not secrets** | the repo | the Worker's assertion check |
| GitHub | none | there is no `.github/` directory and no Actions secret | - |

Not credentials, and do not rotate them: `EFB_DB_SCHEMA`, `EFB_DRY_RUN`,
`EFB_STORE`, `EFB_SNAPSHOT`, `EFB_INIT_STORE`, `EFB_SEED_SOURCE`, `EFB_FORCE_HOUR`,
`EFB_HEDGE_MODE`, `EFB_DESIGN_RETURNS`, `EFB_FLOOR_RELEASE`, `EFB_MIN_SUBMIT_INTERVAL_SECS`,
`EFB_SHORTABILITY_PRECHECK`, `EFB_RUN_ROOT`, `EFB_SEED_ROOT`, `EFB_CADENCE`,
`EFB_CADENCE_ANCHOR`.

## The order

Do them **one family at a time**, and do not start a second family until the check
for the first has passed.

### 1. R2 seed, read token (Render)

The evening's first step is a seed download, and a bad token refuses the run before
anything is priced - loud, cheap, and nothing trades.

1. Cloudflare dashboard → R2 → API tokens → create a **read-only** token scoped to
   the seed bucket.
2. Render → `efb-live-daily` → Environment → replace `EFB_SEED_R2_ACCESS_KEY_ID`
   and `EFB_SEED_R2_SECRET_ACCESS_KEY`. (Account id and bucket name do not change.)
3. **Check:** from this machine, with the new pair exported,
   `python -c "from live import seed; print(seed.fetch_manifest())"` returns the
   manifest. The old token still exists at this point, so a mistake costs nothing.
4. Revoke the old read token in Cloudflare.

### 2. R2 seed, write token (this machine)

Only `scripts/push_seed.py` uses it, and it is not on the run path.

1. Create a write token scoped to the seed bucket.
2. Update `EFB_SEED_R2_ACCESS_KEY_ID` / `EFB_SEED_R2_SECRET_ACCESS_KEY` in `.env`.
3. **Check:** `python -c "from live import seed; seed.seed_client().head_bucket(Bucket='efb-seed')"`
   succeeds, and `python scripts/push_seed.py --check` (dry run) reports no drift.
4. Revoke the old token.

### 3. R2 snapshot token (Render)

1. Create a token scoped to `efb-snapshots`.
2. Render → `EFB_R2_ACCESS_KEY_ID` / `EFB_R2_SECRET_ACCESS_KEY`.
3. **Check:** with the new pair exported locally,
   `python -c "from live import snapshot; snapshot.r2_client().head_bucket(Bucket='efb-snapshots')"`
   succeeds. The evening's own check is the snapshot upload, which is visible in the
   next run's `run_status.snapshot` column (`snapshot: on (...)`).
4. Revoke the old token.

### 4. Database password

The riskiest, because a wrong string makes every step fail at once and the store is
where the completion record lives.

1. Supabase → Project → Database → reset the password **for the role the URL names**.
   When the new password is shown, copy the pooler connection string (session pooler,
   port 5432; the code refuses the transaction pooler).
2. Update `EFB_SUPABASE_DB_URL` in **Render first**, then in this machine's `.env`.
3. **Check:** a read-only SELECT through the new URL, from this machine:
   `python -c "from live import store; print(store.select('run_status').tail(3))"`.
   Then confirm the next morning's `efb.cron_runs` row appears (or, before then, that
   the `run_status` table still answers).
4. Nothing to revoke: the old password stops working when the reset lands, which is
   why Render is updated in the same minute.

If the connection string is split across a pooler and a direct endpoint, rotate both.

### 5. Alpaca paper keys

1. Alpaca dashboard → Paper trading → regenerate the API key pair.
2. Render → `EFB_ALPACA_PAPER_API_KEY` / `EFB_ALPACA_PAPER_SECRET_KEY`; then `.env`.
   `EFB_ALPACA_ACCOUNT_ID` must still be the account those keys reach.
3. **Check:** a read-only account call with the new key -
   `python scripts/verify_account.py` (it reads and compares, it does not trade).
4. The old pair stops working when it is regenerated; Alpaca shows one active pair.

### 6. Resend key

1. Resend dashboard → API Keys → create a new key with send permission.
2. Render → `EFB_RESEND_API_KEY`; then `.env`.
3. **Check:** a read-only call, `GET https://api.resend.com/domains` with the new
   key, returns 200. Do **not** verify by sending mail.
4. Revoke the old key.

### 7. Cloudflare wrangler deploy token

1. `cd web && npx wrangler logout && npx wrangler login` (or replace
   `CLOUDFLARE_API_TOKEN` if you have switched to one).
2. **Check:** `npx wrangler whoami` shows the account, and
   `npx wrangler deployments status` answers.
3. This token cannot place an order or write the store; its worst failure is a
   deploy that does not happen.

## One-page order

```
1  seed read token   -> Render, check fetch_manifest,   revoke old
2  seed write token  -> .env,   check head_bucket,      revoke old
3  snapshot token    -> Render, check head_bucket,      revoke old
4  database password -> Render then .env, check SELECT
5  Alpaca keys       -> Render then .env, check verify_account
6  Resend key        -> Render then .env, check GET /domains
7  wrangler login    -> this machine, check whoami
```

Rotate at least 30 minutes before 15:25 UTC or after 23:00 UTC, never between those
windows, and never on a Friday after 22:00 UTC - the next run is Monday and a mistake
would sit unnoticed all weekend.
