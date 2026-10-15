# page-v4 — the page round four, paused mid-batch

## Resume here

Everything below is committed on `page-v4` (branch pushed to `origin`) and the
worktree `/Users/amankesarwani/PycharmProjects/efb-page-v4` is clean. Nothing was
merged into `main`, nothing was pushed to `main`, and nothing was deployed: the
owner's pause arrived before the 00:45 UTC window opened.

To resume, in `/Users/amankesarwani/PycharmProjects/efb-page-v4`:

```bash
ln -s /Users/amankesarwani/PycharmProjects/equity-factor-book/web/node_modules web/node_modules
cd web && npx vitest run && npx tsc -b && cd ..            # expect 218 passing
V=/Users/amankesarwani/PycharmProjects/equity-factor-book/.venv/bin
make lint RUFF=$V/ruff MYPY=$V/mypy BLACK=$V/black          # not yet run on this branch
```

Then, in order:

1. **Measure, do not look.** A measurement script is still to be written (call it
   `scripts/page_v4_measure.mjs` or run it ad hoc): start `vite preview` (or serve
   `web/dist`) with `web/fixtures/snapshot_2026-10-14_morning.json` behind
   `/api/snapshot`, then record, at 1440px and 390px: `document.body.scrollHeight`,
   whether `document.body.scrollWidth > clientWidth`, whether any table except the
   attribution table overflows its container, and the reconciliation headline's
   bounding box against the 844px first viewport. Write those numbers into this
   file (P10).
2. **Screenshots as files only** (the owner reads them; the vision proxy is not to
   be used): before and after, at 1440px and 390px, into `artifacts/page-v4/`.
   The "before" render is `origin/main` (37b0287, the page as it stands today) with
   the same morning fixture behind the same endpoint.
3. **Local smoke test**: build, serve against the morning fixture, the dated
   fixture and one older fixture (`snapshot_ok.json`); no console errors, every
   section renders.
4. **Gate**: `git diff --stat origin/main...page-v4` must show only `web/`,
   `docs/` and `artifacts/`.
5. **Merge and deploy**, inside an allowed window:
   `git checkout main && git merge --no-ff page-v4`, `git push origin main`, then
   `cd web && npx wrangler deploy`. Record the new version id here.
6. **Trial merge with nov11**: scratch worktree on page-v4,
   `git merge --no-commit origin/nov11`, list the conflicted files, then
   `git merge --abort`; write `docs/page_v4_merge_note.md` (not started).

Rollback target, read from `npx wrangler deployments list` on 2026-10-14 and still
current then: **`7adf883d-b4de-4f4e-a566-a62663cb5d81`** (created
2026-10-12T17:30:21Z).

```bash
cd web && npx wrangler rollback 7adf883d-b4de-4f4e-a566-a62663cb5d81
```

## What this branch is

The page-only batch for 2026-10-14, in `web/**` only. No Python was touched: the
sizing, hedge, orders, reconciliation, snapshot writer, notify and scripts are
untouched, and nothing was written to R2, the database or the broker.

Two snapshots were fetched read-only from `efb-snapshots` and committed:

- `web/fixtures/snapshot_2026-10-14_morning.json` — today's `latest.json`: the
  morning read of 2026-10-14 15:31 UTC against the 2026-10-13 close, proposal ok,
  reconciliation clean, PCG and PYPL the two expected mismatches.
- `web/fixtures/snapshot_2026-10-13_evening.json` — **byte for byte the same file**
  (md5 `173013c1694f4b7a8fb33f9f58db6281`). The bucket's dated key is not a separate
  evening document: the morning rewrites both keys, so `snapshots/2026-10-13.json`
  had already been overwritten with the morning's own bytes when it was fetched.
  The file is committed under both names as the brief asked, and the fixtures test
  says so. The evening rendering is exercised by the committed
  `snapshot_position_removed.json` (an evening read) and by the unit tests that flip
  `read_by`.

Numbers taken from the real document and used in the work below: turnover card
`$447,195.23` (`reconciliation.intended_notional`; the writer publishes no
`sent_notional` yet), per-name traded `$288,236.54`, so the exited row is
`$158,958.69`; bridge 185 held → 31 opened / 45 exited / 115 resized / 25 under the
floor → 191 orders → 191 filled → 169 held, book 171; `n_eff_kept` 130.5 of 171
names; the hedge moved 71 names for `$72,939.27` (16.3% of turnover); SMCI carries
11.0% of predicted stock-specific risk.

## P1–P10

| # | Item | State |
|---|---|---|
| P1 | Attribution: unit in the header, `est` tag, short cost note, one-sentence beta | **done, tested** |
| P2 | "Not checked here" → one line behind a toggle, one sentence each | **done, tested** |
| P3 | Mismatch rows: plain label plus what happens next | **done, tested** |
| P4 | Evening pre-order panel collapsed to one line, resolved/unresolved | **done, tested** (the `previous_reversals_pending` case is tested in `exceptions.test.ts`; the panel's own wording with the key present is not) |
| P5 | Glossary with exactly three definitions | **done, tested** |
| P6 | Trades by reason add up: exited row and share column | **done, tested on the real fixture** |
| P7 | Bridge arithmetic toggle, every identity checked | **done, tested** |
| P8 | Metric cards: `n_eff` subtitle, telemetry in three lines, drift % plus reason, turnover basis | **done**; `n_eff`, the drift lines and the trades table are tested, the telemetry wording and the `sent_notional` basis are not |
| P9 | Hedge panels: one-sentence opening, variance line as a share of a total | **done**; the opening sentence is tested, the variance wording is not |
| P10 | Phone: "is anything wrong today?" at zero scroll, no sideways table scroll | **not verified** — the measurement run was not made before the pause |

Forward compatibility with nov11 (the keys `main`'s writer does not publish yet):

- **ported and doing the work**: `bridge.under_minimum_tickers` (files a leg the
  floor left untraded as expected, target side only), `bridge.previous_reversals_pending`
  (files the previous close's deferrals, and keeps the class on the cannot-check list
  when the value is null rather than empty), and `reconciliation.sent_notional` /
  `unsent_notional` as the turnover card's basis (`sent_notional` when present,
  `intended_notional` otherwise, with the card's label and its note moving with it).
- **not ported**: `breadth.n_dropped_no_risk` / `breadth.dropped_no_risk` — the types
  are declared, the line that prints the names the risk model could not measure is
  still to be added to `MetricsRow.tsx`.
- `web/src/types.ts`, `exceptions.ts` and their tests follow nov11's shapes, so the
  future merge should be "take page-v4, then run nov11's web tests" — to be confirmed
  by the trial merge.

## Test status at the last run (2026-10-15 00:40 UTC, after merging origin/main)

```
cd web && npx vitest run    → 9 files, 218 tests, all passing
cd web && npx tsc -b        → clean
make lint                   → NOT RUN on this branch since the changes landed
```

The suite grew from 186 tests on `main` to 218: the fixtures test now covers the two
new documents (bridge numbers per fixture, the departure block present and empty),
and there are new cases for the labels, the nov11 keys, the arithmetic toggle, the
glossary, the exited row, the drift wording and the hedge opening.

## Not done, left over for a later window

- P10's measurements and every screenshot (before and after).
- The local smoke test against three fixtures.
- `make lint` on this branch.
- `docs/page_v4_merge_note.md` and the trial merge with `origin/nov11`.
- The `dropped_no_risk` line (nov11's third key).
- PART B, the ETF overlay hedge study: **not started** — the brief starts it after
  PART A is deployed or the cutoff passes.

## Environment note

The main checkout at `/Users/amankesarwani/PycharmProjects/equity-factor-book` is at
`6903912 [nov11]` — it advanced from `eac1aad` during the day (the nov11 report
commit, not this work). Nothing in this branch touched it; the only commands run
against that repository from here were `git worktree add` and `git worktree remove`.
A scratch worktree at `/tmp/efb4-before` (a detached checkout of `origin/main`'s
page, used to prepare the "before" state) has been removed.
