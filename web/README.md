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

It shows, in order: one status strip (the run's status pill, the dry-run or live
banner, the snapshot's time and age, the target close, whether the owner was
notified, and one line saying so when the book is not tonight's); the panels that
carry a warning, a stopped run or the unfilled misses; a dense row of the run's
headline numbers; then two columns on a wide screen (the factor exposures before
and after the hedge beside the sector bars, the ten largest longs and shorts and
the trades by reason); then a drawer holding the full book and the account's own
book, each with its own tab and one shared search box.

The account's own book is written twice a day: the evening run fills it from the
account read it makes before sizing, and the 15:30 UTC reconciliation rewrites it
with what those orders did. It is read in the drawer's second tab, and its fills
are summarized on the metrics row. A run that could not read the account publishes
no block, and the strip says so in one line rather than drawing an empty book.

Screenshots of the rendered page, taken from a headless browser at 1280px and
390px against the fixture that stands for a clean run, are
`docs/img/live_page_ok_1280.png` and `docs/img/live_page_ok_390.png`.

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

- The status strip: the status pill, the dry-run or live banner, the snapshot's
  timestamp in UTC with its age, the target close, whether the owner was notified,
  and a note when the book shown is not the target close's. The pill reads
  `expired` for a snapshot past `expected_next_by`, `catch_up` for a run that
  replayed earlier sessions, and the run's own status for a stopped or errored
  run. Red is reserved for a stopped run, an errored run and a missing snapshot;
  amber is for a late snapshot, for unfilled orders and for deferred legs, which
  are routine rather than failures.
- The panels that need reading, in the order they should be read: the run's own
  status line, the positions check against the store, and the unfilled misses,
  each as one line plus its detail.
- The metrics row: gross and net, the long and short name counts with their
  dollars, `n_eff_kept` and `n_eff_full_book` with their labels, the largest
  position, the expected cost, the top ten's share of gross, the full book before
  the floor, and, when the account was read, the fills as filled of sent and the
  realized cost against the expected. A value the snapshot does not carry reads
  `n/a`; nothing is filled in with a zero.
- Two columns on a wide screen, one on a phone: the factor exposures before and
  after the hedge (one bar scale, set by the largest exposure on the page, so a
  factor the hedge has taken out is a flat line at zero) beside, in turn, the
  sector bars (long gross to the right and short gross to the left on a single
  scale, with the long and short name counts and the sector's own net), the ten
  largest longs and shorts with their weights, dollars and trade reasons, and the
  trades by reason.
- The drawer at the bottom, closed until it is asked for: one search box over two
  tabs, the full book (sortable on every column, with a sector filter) and the
  account's own book (the union of held and target, sorted by the largest
  absolute drift first). Typing a ticker opens the tab that has the name. The
  full book is 180 to 235 rows, which is why it is behind a tab rather than on
  the page.
- Two panels wait for data the snapshot does not carry yet and hide themselves
  until it does: risk concentration (each name's share of the book's predicted
  specific variance, with the sizing cap drawn as a line) and movers (the
  session's top and bottom contributors by name and by sector). An empty panel
  would say the answer is nothing rather than that the run has not written it.
- The accounting that used to be repeated at the end of the page is gone: the
  long and short gross footer under the sector bars and the separate ten largest
  names list both restated the metrics row.

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
