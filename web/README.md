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
dry-run banner; the positions check against the paper account; the summary cards
and the run's own book figures; a diverging bar per GICS sector; the ten largest
longs and shorts; where the trades came from, by reason; the factor exposures
before and after the hedge; the full holdings table, collapsed until it is asked
for; and the run status line, meaning the gate's inputs and how far behind each
one was, the cost with its four components, and whether the owner was notified.

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
- The book: the summary cards (long and short name counts and dollars, the net,
  `n_eff_kept`, the largest position, the top ten's share of gross, the expected
  cost), then the run's own figures, which are construction, gross with its
  notional, the full book before the floor, the net, both effective breadths and
  the cost with its label. The book is dated with its own close whenever that
  close is not the target.
- By sector: one diverging bar per GICS sector, long gross to the right and short
  gross to the left on a single scale, with the long and short name counts and
  the sector's own net beside each bar.
- The ten largest longs and the ten largest shorts, side by side, each with its
  weight, its dollars and its trade reason.
- Trades by reason: the names and the dollars the run recorded under each reason,
  with the ten largest positions beside it.
- Factor exposures before and after the hedge, side by side, with the hedge.
- The full holdings table, collapsed by default, sortable on every column, with a
  sector filter and a ticker search.
- Two panels wait for data the snapshot does not carry yet and hide themselves
  until it does: risk concentration (each name's share of the book's predicted
  specific variance, with the sizing cap drawn as a line) and movers (the
  session's top and bottom contributors by name and by sector). An empty panel
  would say the answer is nothing rather than that the run has not written it.

The dollars are derived, not assumed: the snapshot states the traded book's gross
and the same book's notional, and the page reads one over the other as the book in
dollars per unit of weight. Nothing on the page hard-codes the paper account's
opening balance.

Breadth is on the page as the two labelled numbers (`n_eff_kept` and
`n_eff_full_book`), never as an unqualified `n_eff`.

## The sector map

The snapshot has no sector per name, so the page carries a bundled ticker-to-GICS
map, generated from the stored files rather than typed:

```
.venv/bin/python scripts/make_sector_map.py     # regenerate it
```

It comes from `data/processed/sectors.parquet`, the ticker-to-GICS table the risk
model itself uses, and the dated `data/raw/spy_holdings/` archive, which names the
current membership and whose own `sector` column is a placeholder. The code-to-name
table is `efb.models.fundamental.SECTOR_CODES`, the same one the design columns are
built from. `tests/test_web_sector_map.py` regenerates it and asserts the committed
bytes, so the map cannot drift from the files it came from. A name neither file can
place is rendered as Unmapped rather than guessed at, and three of the current
index's tickers are in that state.

## Eyeballing a build locally

```
npm run build
mkdir -p dist/api && cp fixtures/snapshot_ok.json dist/api/snapshot
python3 -m http.server 4173 --directory dist
```

Swap in `fixtures/snapshot_no_book.json` to see the state where every book section
is hidden and nothing claims a flat book. Clear `dist/` before running `npm run
test`: the leak check reads every file under `dist/`, and a staged snapshot
carries the word `supabase` in its `store` field, so it fails that check until the
next build replaces the directory.
