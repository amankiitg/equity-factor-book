# EFB live book monitor

One screen: the evening cron's snapshot, served by a Worker on Cloudflare behind
Access. The browser never queries Postgres and never reaches R2 — the Worker reads
`latest.json` through a binding and the bucket stays private.

## Live book

**https://efb-live-book.nutritrack.workers.dev**

The page sits behind **Cloudflare Access**, and the only identity allowed is the
owner's email address: signing in is an email one-time PIN, and until it is
answered every path — the page and the API alike — answers a redirect to the
login rather than any content. It updates after each weekday evening run (the
cron fires at 22:30 UTC, inside the after-hours window), so the book on it is
always the last proposal the loop actually priced.

It shows, in order: the run's status and target close, the snapshot's age and the
dry-run banner; the positions check against the paper account; the book (ticker,
side, weight and the trade reason, largest absolute weight first); the orders the
run proposed or sent; the factor exposures before and after the hedge, as one
table with the GICS sectors named and a before/after bar per factor; and the run
status line — the gate's inputs and how far behind each one was, the cost with its
four components, and whether the owner was notified.

```
npm install
npm run test        # vitest: the page, the Worker, the fixtures, the leak check
npm run dev         # the page on a dev server (the endpoint 403s without Access)
npm run deploy      # vite build && wrangler deploy
```

## What the owner creates

1. **The R2 bucket `efb-snapshots`**, private. The cron's `EFB_R2_*` credentials
   are scoped to it with object read and write, and the Worker reads it through
   the binding in `wrangler.jsonc` — no key ever reaches the browser.
2. **A Cloudflare Access application** in front of the Worker's hostname, with the
   owner's email as the only allowed identity.
3. **The two values** from that Access application, in `wrangler.jsonc`:
   `ACCESS_TEAM_DOMAIN` (the team domain, `*.cloudflareaccess.com`) and
   `ACCESS_AUD` (the application's AUD tag). Both are identifiers, not secrets.
4. **The cron's snapshot credentials** on Render: `EFB_SNAPSHOT=on` plus
   `EFB_R2_ACCOUNT_ID`, `EFB_R2_BUCKET=efb-snapshots`, `EFB_R2_ACCESS_KEY_ID`,
   `EFB_R2_SECRET_ACCESS_KEY`.

## What it shows, in order

- Status first: the run's status and target close, the snapshot's age, and a
  failure state for a stopped run, an errored run, a late snapshot (past
  `expected_next_by`), or no snapshot at all.
- The catch-up label, the dry-run banner, and the positions check against the
  store.
- The book: ticker, side, weight and the trade reason, largest absolute weight
  first, dated with its own close whenever that close is not the target.
- Factor exposures before and after the hedge, side by side, with the hedge.

Breadth is on the page as the two labelled numbers (`n_eff_kept` and
`n_eff_full_book`), never as an unqualified `n_eff`.
