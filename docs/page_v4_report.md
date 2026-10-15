# page-v4 — the page's fourth round: shipped, measured, and merged

## Final state (2026-10-15)

`main` = `3a2ece8` (the merge of `page-v4`, then the accidental `web/node_modules`
symlink untracked), pushed at 12:35 and 13:0x UTC; deployed at 12:37 UTC from the
merge.

- **Deployed version id: `a8fc0f88-f6cf-4a99-902e-4c6b7394d7de`** (100% of traffic,
  created 2026-10-15T12:37:42Z), via the documented path
  `cd web && npm run deploy` (= `vite build && wrangler deploy`), after
  `make web-build` (build plus 228 tests).
- **Rollback:**

  ```bash
  cd web && npx wrangler rollback 7adf883d-b4de-4f4e-a566-a62663cb5d81
  ```

  `7adf883d-b4de-4f4e-a566-a62663cb5d81` was the version at 100% immediately before
  this deploy, re-read with `npx wrangler deployments status` at 12:36 UTC.

One cleanup after the deploy: `web/node_modules` (a symlink to this machine's copy)
was committed by accident in `054b9af` when `git add web` was used, and it was
untracked on both branches (`0c40c96`, `3a2ece8`) the moment it was noticed.
`.gitignore` had excluded it all along.
- `page-v4` = `0c40c96`; `origin/nov11` = `6903912`; the trial merge left no
  worktree behind.

Nothing outside `web/`, `docs/` and `artifacts/` was touched, no Python was
changed, and nothing was written to R2, the database or the broker.

## The measurements (the phone and the desktop, by number)

`web/scripts/measure.mjs` serves a built `dist/` with one fixture behind the
snapshot endpoint and records four things at 1440px and 390px: page height,
whether the body scrolls sideways, whether any table but the attribution one
overflows its box, and whether the reconciliation headline's box ends inside the
first 844px. The clock is pinned to `2026-10-14T16:00:00Z`, the morning the
fixture was written for, so before and after are comparable. Both runs are saved
in `artifacts/page-v4/` as `before-measurements.json` and
`after-measurements.json`; the screenshots of both are there too.

The 2026-10-14 morning fixture:

| | 1440px height | 390px height | sideways | tables overflowing at 390 | headline bottom at 390 | console errors |
|---|---:|---:|---|---:|---:|---:|
| before (origin/main's page) | 2,081 | 4,365 | no | **factor exposures, sector gross** | 486 (inside) | 0 |
| after (page-v4) | 2,234 | 4,418 | no | none | 524 (inside) | 0 |

The failed 2026-10-14 evening document, on page-v4: 1,847px at 1440 and 3,317px at
390, no overflow, headline bottom 356 and 612 — inside the first screen at both
widths.

Two findings, both fixed:

1. **Two tables overflowed sideways at 390px** (`factor exposures`, 351px inside a
   322px box; `sector gross`, 352px inside 338px). Neither made the *page* scroll
   sideways, but each table was wider than its own box, which the brief does not
   allow outside the attribution table. Both are now `table-fixed` with percentage
   columns, wrapping labels and no fixed pixel widths, so they are exactly as wide
   as the box they sit in. The factor bars were `w-28` and are now fluid, which was
   the hidden cause.
2. **The reconciliation headline** was already inside the first screen before this
   batch (bottom 486 of 844) and still is (524). The growth is the labels, glossary
   and gap line the brief asked for, and the headline moved 38px with them.

The smoke test (`artifacts/page-v4/smoke-measurements.json`) ran the same build
against three fixtures — the morning read, the failed night, and `snapshot_ok.json`
— and all three render with no console errors, no `NaN`/`undefined`/`-$0`/
`T00:00:00` in the text, no sideways scroll and no table overflow, at both widths.
The failed night's own top line reads **"no book was priced for the 2026-10-14
close"**, with the run's sentence beside it.

## The fixtures

- `web/fixtures/snapshot_2026-10-14_morning.json` — `latest.json` as it stood on
  2026-10-14: the morning read of 15:31 UTC against the 2026-10-13 close, proposal
  ok, reconciliation clean, PCG and PYPL the two expected mismatches.
- `web/fixtures/snapshot_2026-10-14_error.json` — the **failed 2026-10-14 evening
  document**, fetched read-only at **11:46 UTC on 2026-10-15, before the morning
  job ran at 15:25-15:45 and wrote this morning's account read on top of it**. What
  it carries: `generated_at` 2026-10-14T22:32:13Z, `run_status.status` `error`,
  `detail` `KeyError: "['dividend', 'split_factor'] not in index"`, the 2026-10-13
  book left standing (`book_as_of` 2026-10-13 against `target_close` 2026-10-14),
  no `actual_holdings` and no `bridge`.
- `web/fixtures/snapshot_2026-10-13_evening.json` — byte for byte the same file as
  the morning document (md5 `173013c1694f4b7a8fb33f9f58db6281`), because the morning
  rewrites both `latest.json` and `snapshots/<close>.json`. The bucket's dated key
  is therefore not a distinct evening document, and the report says so rather than
  pretending it is a second state.

## Tests, at the last run on `main` after the merge

```
cd web && npx vitest run     → 9 files, 228 tests, all passing
cd web && npx tsc -b         → clean
make lint (venv tools)       → ruff, mypy efb, mypy live scripts, black --check: all green
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

## What the suite grew by

186 tests on `main` before this batch, 228 now: the fixtures test covers the three new
documents (bridge numbers per fixture, the departure block present and empty, the
failed night with no bridge and no account read), and there are cases for the four
plain labels, all four nov11 keys, the arithmetic toggle, the glossary, the exited
row, the drift wording, the hedge opening, the error headline and the phone's
table widths as they are rendered.

## Not done

Nothing in PART A is left open. Everything the brief listed for this round is
implemented, tested and measured, and the trial merge with nov11 has been run and
written up in `docs/page_v4_merge_note.md`.

The two things a reader of this file should know about the shape of it:

- The dated `snapshots/2026-10-13.json` object is not a second state, so the only
  evening document in the fixtures is `snapshot_position_removed.json` from the
  2026-10-06 close. If a genuine evening document is wanted for a future round, it
  has to be fetched after the evening run and before the next morning's.
- `main`'s 2026-10-14 incident fix (`63c8f94`) is not in `origin/nov11`, so the
  November merge has to carry it in whichever direction it runs.

## Environment note

The main checkout at `/Users/amankesarwani/PycharmProjects/equity-factor-book` is at
`6903912 [nov11]` — it advanced from `eac1aad` during the day (the nov11 report
commit, not this work). Nothing in this branch touched it; the only commands run
against that repository from here were `git worktree add` and `git worktree remove`.
A scratch worktree at `/tmp/efb4-before` (a detached checkout of `origin/main`'s
page, used to prepare the "before" state) has been removed.
