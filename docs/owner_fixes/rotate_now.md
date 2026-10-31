# Rotate now: the Sunday-evening runbook

**Nothing was rotated on 2026-10-31.** This file is the do-this-now version of
[`key_rotation.md`](./key_rotation.md), which has the full inventory and the reasoning.
Variable names only: no value of any credential appears in the repository.

Do it **Sunday 2026-11-01 evening, after 23:00 UTC** - the weekend's last run has
finished and Monday's 15:30 morning is 16 hours away, which is the widest window the
week offers. Never inside 15:25-15:45 UTC or 22:25-23:00 UTC.

## The order, and one check per family

One family at a time. Do not start the next until the check for the current one has
passed. Every check reads; none of them sends mail or an order.

| # | credential | variables | set in | check (read-only) |
| --- | --- | --- | --- | --- |
| 1 | R2 seed, read token | `EFB_SEED_R2_ACCESS_KEY_ID`, `EFB_SEED_R2_SECRET_ACCESS_KEY` | Render only | `python -c "from live import seed; print(seed.fetch_manifest())"` |
| 2 | R2 seed, write token | the same two names | this machine's `.env` | `python scripts/push_seed.py --check` (dry run: no drift) |
| 3 | R2 snapshot token | `EFB_R2_ACCESS_KEY_ID`, `EFB_R2_SECRET_ACCESS_KEY` | Render only | `python -c "import os; from live import snapshot; snapshot.r2_client().head_bucket(Bucket=os.environ['EFB_R2_BUCKET'])"` |
| 4 | database password | `EFB_SUPABASE_DB_URL` (password inside it) | Render **then** `.env` | `python -c "from live import store; print(store.select('run_status').tail(3))"` |
| 5 | Alpaca paper keys | `EFB_ALPACA_PAPER_API_KEY`, `EFB_ALPACA_PAPER_SECRET_KEY` (and the account id they must reach) | Render then `.env` | `python scripts/verify_account.py` |
| 6 | Resend key | `EFB_RESEND_API_KEY` | Render then `.env` | `curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $EFB_RESEND_API_KEY" https://api.resend.com/domains` -> `200` |
| 7 | Cloudflare deploy | wrangler OAuth token, `~/.wrangler/config/default.toml` | this machine | `npx wrangler whoami` |

The rule behind the order: **create the new credential, put it in every consumer,
prove it works, and only then revoke the old one.** A rotation that revokes first
leaves the 22:30 evening or the 15:30 morning unable to start.

## Two things that are easy to get wrong

- **The snapshot R2 token is Render-only.** It is not in this machine's `.env`, so
  `head_bucket` locally will fail with the *local* seed token if the two are confused:
  export the pair you are testing, and check the bucket name, not just the status.
- **The database password and its connection string move together.** Copy the pooler
  string (session pooler, port 5432) as shown when the password is reset; the code
  refuses the transaction pooler. Update Render and `.env` in the same minute, then run
  the SELECT above.

## If a rotation goes wrong

Nothing here is one-way except the revoke step, so a mistake before it costs nothing:
put the previous value back and re-run the check. If a family is left half-rotated,
the run refuses at its own preflight (the seed download, the snapshot config, the
account identity check), which is loud and safe: it does not trade. The evening's
failure email names the step; `efb.run_status` carries the same reason for the page.

After the seventh family passes, confirm the next morning's `efb.cron_runs` row
appears (Monday 15:30 UTC) and that the page still renders - that is the end-to-end
proof that all seven consumers are on the new credentials.
