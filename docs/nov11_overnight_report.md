# Resume here

**Branch `nov11`, pushed to `origin/nov11` at `9c3268d`.** `main` is untouched at
`1e405be`. Nothing is deployed, nothing was merged to `main`, no live database, R2
bucket or broker was written, and no secret was printed. Working tree clean (only
the untracked `artifacts/` folder from the page review).

## Done, with commits

| commit | what |
|---|---|
| `4c1d52d` | the setup merge: `origin/backport` into `nov11`, `--no-ff`, twelve conflicts none of them in `live/`, `scripts/` or `efb/` (two docs unions, seven regenerated fixtures) |
| `0e218be` | the triage table for all thirty-three items (section 2 below) |
| `c21cbd4` | research: turnover and cost (section 3) |
| `7318552` | research: the hedge's concentration (section 3) |
| `05e4896` | BUILD item 21: the message's order count is the legs sent |
| `cd1d2e9` | BUILD item 2: the morning compares the fills against the trading half |
| `2fe6753` | BUILD item 29: a missing `beta_history` costs two columns, not the section |
| `8be4db6` | BUILD items 17 and 15: the universe is deduplicated; a zero variance is refused on both sides |
| `e155072` | BUILD item 6: the count of names the risk block cannot measure is reported |
| `9c3268d` | BUILD items 1 and 22: the bridge names the legs it did not send and the position nobody ordered (this is also the item that was finished at the pause) |

**Two commits bundle two small items each** (`17`+`15`, and `1`+`22`): the pairs share
one file and one test module, and splitting them would have meant two commits
touching the same lines. Every other item is its own commit.

## Item in progress at the pause

None: items 1 and 22 were finished, tested and committed as `9c3268d` before the
pause. Nothing is left uncommitted and there is no stash.

## Next items, in the order they were being worked

The research is done; this is the build queue from here, highest value first:

1. **item 3 / 33** - `reconciliation.filled_notional` is `0.0` on every live row.
   Write it from the fills the morning already reconciles (or drop the column).
   `live/reconcile.py:202` writes `float("nan")` for `realized_annual_vol`; the
   `filled_notional` placeholder is written by the same row builder.
2. **item 26** - `realized_annual_vol` NaN on every row; compute it from the live
   P&L the loop now stores, or drop it. Same file as 33, so read them together.
3. **item 28** - the attribution step's outcome goes on the run row and in the
   evening email (`scripts/run_live_daily.py:1751`/`:1758`, `live/notify.py:640-672`).
4. **item 31, 32, 16** - publish `sent_notional`, the under-minimum tickers, and
   `dropped_no_risk` on the page. Cheap: one key each, plus the page-side render for
   16 (the page is a separate, deployed artefact - the key can land first).
5. **item 30** - publish the previous close's `bridge.reversals_pending`.
6. **item 14** - one source for the specific variance: `store_proposal` refuses
   against the manifest's own `dropped_no_risk` instead of re-reading a root.
7. **item 27** - the seed preflight over `seed.record_reads`/`manifest_for`.
8. **item 4, 20, 19** - the morning's double reconcile, the evening's retry guard,
   and INCOMPLETE exiting 0 on a refused leg.
9. **item 9** - `excluded` gains a reason and an age.
10. **item 5** - the 28-column NOT NULL NaN audit (read-only `SELECT`s).
11. **FLAG items**, each with a default-off flag and an identity proof: **18**
    (shortability before sizing), **11** (the PSKY/SKYD rename at the fetch), **12**
    (the floor's entry/exit band), and the **cap-then-rehedge hedge** that the
    section 3 research recommends - that last one is a trading change and needs the
    owner's approval even behind a flag.
12. **item 23** at the finish: refresh `docs/known_test_failures.md` from a run on
    `main` with the gate's command, one id at a time, each with its cause.

## Background processes

None running. The overnight research runs (three research scripts) and the baseline
test suite all completed; the two long ones (`nov11_turnover_research.py`,
`nov11_hedge_research.py --scope backtest`) were waited on and their outputs are in
`docs/research/*.json`. No server, watcher or detached process was left behind.

## What the next session must know

1. **The baseline on the merge commit is `7 failed, 1462 passed`** with the gate's
   own command (`.venv/bin/python -m pytest tests/ -q -m "not slow and not
   requires_live_tree and not merge_guard"`). The seven are the four
   `test_week2_spinoff` ids that item 23 lists as missing from the known-failures
   file, two in `test_e13_design_note` (a new test on the backport branch: the
   module map does not know the merged tree's modules), and
   `test_e11_corporate_actions.py::test_the_aph_split_is_reproduced_from_the_real_rows`.
   `tests/test_e12_attribution.py::test_the_pipeline_attributes_the_seed_book_every_session`
   is **borderline against pytest-timeout**: 89.9s alone against a 120s limit, and it
   timed out once when the machine was loaded. Treat a timeout there as load, not as
   a regression, and re-run it alone.
2. **`tests/test_e11_snapshot.py::test_the_hedge_drives_the_exposures_to_zero` is red
   in a targeted run and green inside the full suite** - item 23 says so, and it
   reproduced exactly that way tonight. It is not a regression from this branch.
3. **The merged tree's fixtures were regenerated** and that moved `book.gross` to
   `0.9999999999999999` for a book that is exactly invested, which broke a page test
   pinned with `toBe(1)`. Fixed in `9c3268d` with `toBeCloseTo(1, 12)`. Any further
   writer change needs `PYTHONPATH=. .venv/bin/python scripts/make_web_fixtures.py`
   and `npx vitest run` in `web/`.
4. **The two research conclusions in five lines each** are in section 3; their
   headline is that the research cost model charges no borrow at all while the live
   model's borrow is 99 bp a year against a 169 bp gross return, and that the live
   loop trades 40-50% of the book's gross every session against the panel's 35.6%
   once a month - about 25x the turnover per unit of time.
5. **The cost model's horizon is the decision that unblocks the rest.** The live
   model charges spread, commission and borrow as 21-session holding costs at a
   frequency of one session, so at the live loop's own frequency the borrow
   overstates the annual cost by 21x. Every "expected cost" the loop prints, and
   every judgement about whether a night's trading was worth it, rests on that until
   it is settled. It is decision 1 in section 7.
6. **`live/evening_job.py` gained a module logger** (`logger = logging.getLogger`)
   in `8be4db6`; it previously logged through nothing, which is why item 17's
   duplicate warning needed it.
7. **Read-only live reads used tonight**: `efb.positions`, `efb.proposals`,
   `efb.orders` via `live/store.py`. The `.env` file is only ever read through
   code, never echoed. The store's live rows lag the committed research tree
   (the committed panel ends 2026-10-02), so research scripts fall back to the
   artifact's own last block for live closes after that - stated in
   `scripts/nov11_hedge_research.py::pieces_at`.

# The November 11 list, worked overnight

Branch `nov11`, cut from `origin/main` (`1e405be`) with `origin/backport`
(`4017f63`) merged in `--no-ff`. Nothing here is merged to `main`, nothing is
deployed, and the live database, both R2 buckets and the broker are untouched:
the only live reads are `SELECT`s.

Written overnight, unattended. Where something was ambiguous I took the
conservative reading, recorded it here, and moved on; the decisions that are
only the owner's are at the end.

## 1. The merge, and its resolutions

Twelve conflicts, none of them under `live/`, `scripts/` or `efb/`, so the merge
ran as instructed:

| file | resolution |
|---|---|
| `docs/open_items.md` | both sides appended one dated entry at the same place; kept both, in the file's date order (2026-09-26, then 2026-10-03) |
| `docs/hygiene_ledger.md` | both sides appended at EOF; kept both blocks in date order (the backport's fifteen entries, then this branch's three). 105 entries, none dropped |
| `web/fixtures/*.json` (7 of 12) | generated files; took a side, then regenerated all twelve with `scripts/make_web_fixtures.py` on the merged tree, which is what `tests/test_e11_web_fixtures.py` asserts. The fixture book moves 188 → 204 names because the merged tree's panel is what the writer builds the 2026-09-21 proposal from |

What arrives from `backport` is large (122 files, +25,550/-5,779) and includes
`efb/`, `live/` and `scripts/`. It arrives by instruction; `main` is untouched
and the branch is not deployed.

## 2. Triage

BUILD = safe, testable, no trading change. FLAG = trading change, built behind a
default-off flag with an identity proof. RESEARCH = a question, not code.
BLOCKED = needs a live write, a seed push, a migration, or the owner's decision.

| # | item | triage | why, and the shape of the work |
|---|---|---|---|
| 1 | the bridge cannot say a name arrived | BUILD | `arrived_without_order`, the mirror of the existing removal term, in the identity's right-hand side. Bookkeeping only (`live/bridge.py`) |
| 2 | the morning's cost line compares against the full cost, not the trading half | BUILD | one line in `live/notify.py`, beside the card that already labels it |
| 3 | `reconciliation.filled_notional` is stored as `0` | BUILD | same fix as 33; the morning writes the number it already has |
| 4 | the morning reconciles the previous close a second time | BUILD | guard on the close actually reconciled, not on the date; `tests/test_week1_fills_cron.py` |
| 5 | the NOT NULL NaN audit (28 columns) | BUILD | a read-only audit over `information_schema` + a NaN scan, and the answer recorded per column. Needs live `SELECT`s only |
| 6 | a filled risk estimate is never reported | BUILD | report `_missing`'s count on the manifest and in the message; the median fill itself stays |
| 7 | the sizing universe is not the risk universe | **done on main** | `risk_names_or_stop` / `dropped_no_risk` / `MAX_RISK_DROPS` are already there (`live/evening_job.py:443`, `:1284`, `:1438`). Verify against the item's numbers and record it |
| 8 | a name with risk but no signal has no stated treatment | BUILD (report) + **BLOCKED** (the choice) | the count and the names can be recorded now; hold / hedge-only / exclude is a trading decision and is the owner's |
| 9 | `excluded` has no reason and no age | BUILD (reason + age) + **BLOCKED** (the path back) | the reason is derivable (no GICS row / no prices / not in the returns panel) and the age from the stored manifests; a path back needs a rebuild or a fetch, which is a decision |
| 10 | why is DD missing from `processed/returns.parquet`? | RESEARCH | read the build's own record for the 2025-11 spin-off; no code |
| 11 | the pricing fetch still spells PSKY | FLAG + **BLOCKED** to apply | resolving the rename changes the sized universe (SKYD becomes sizeable) so it is a trading change behind a default-off flag; applying it needs a fetch that writes `efb.e11_prices`, which is the owner's |
| 12 | the floor's hysteresis is unmeasured | RESEARCH (measure) + FLAG (the band) | the churn measurement is research; an entry/exit band changes the kept set, so it is a flag |
| 13 | six names in the risk block outside the universe | RESEARCH | answer harmless-or-not with counts; no code |
| 14 | one source for the specific variance | BUILD | `store_proposal` refuses against the manifest's own `dropped_no_risk`, or takes the vector. No trading change |
| 15 | zero is asymmetric | BUILD | tighten the write's refusal to non-positive and share one predicate with the drop's |
| 16 | `dropped_no_risk` is not on the page | BUILD | a snapshot key (page-side rendering is a second, separate change) |
| 17 | the SPY ticker list is not deduplicated | BUILD | `sorted(set(...))` with a warning when it drops one |
| 18 | shortability is checked after sizing, not before | FLAG | the broker's flags decide which names the book holds, so it is behind a default-off flag with an injected flag source; **no broker call can be made tonight**, so it is built and tested against a recorded fixture, not verified live |
| 19 | a refused leg reads ERROR and exits nonzero | BUILD | a broker refusal of a leg becomes INCOMPLETE and exits 0; a real failure still exits nonzero. No trading change |
| 20 | the evening's retry guard cannot see a close that already traded | BUILD | refuse an evening whose close already has orders, or record the close as traded. Makes a rerun not trade |
| 21 | the message's order count is the legs built, not sent | BUILD | count the legs with a broker id, which is what `sent_notional` measures |
| 22 | the bridge cannot say a name exited with no order | BUILD | a third named term; `under_minimum` counts only minimum-coded legs |
| 23 | seven reds are missing from `known_test_failures.md` | BUILD | refresh the file from a run on `main` with the gate's own command, one id at a time, each with its cause |
| 24 | the hedge concentrates single-name risk | RESEARCH (the comparison) + BUILD (the relabel) | minimum-variance neutralization vs cap-then-rehedge is research; `variance_share_cap_binds` is relabelled (or complemented) because it reads the post-hedge book |
| 25 | an inactive asset is a corporate action, not a skip | BUILD (the bridge term) + **BLOCKED** (the broker read) | the exit-with-no-order term is item 22; reading the broker's announcements and asset status needs broker calls, which are not allowed tonight |
| 26 | `reconciliation.realized_annual_vol` is NaN on every row | BUILD | compute it where the row is written, from the live P&L the loop now stores, or drop the column |
| 27 | a new `data/` input read by a live path is a seed change | BUILD (the preflight) + **BLOCKED** (the push-side check) | the preflight is code over `seed.record_reads`/`manifest_for`; the push-side check needs a seed push |
| 28 | the attribution step's outcome goes nowhere | BUILD | the run row's `detail`/`failures` and one consequence line in the message |
| 29 | `beta_history` should be read with a fallback | BUILD | a `try`/`except FileNotFoundError` around the one read, so two columns degrade instead of the section |
| 30 | publish the previous close's deferred reversals | BUILD | one more key in the bridge block, from the block the evening already reads |
| 31 | publish the sent-only notional | BUILD | `sent_notional` (and `unsent_notional`) on the reconciliation row and the snapshot |
| 32 | publish the under-minimum tickers | BUILD | the set the count is already taken from |
| 33 | `filled_notional` is `0.0` on every live row | BUILD | the same fix as 3 |

Order of work: the research first (section 3), then the builds one commit each
(section 4), then the flags (section 5), then the gate and the known-failures
refresh (section 6).

## 3. Research

(to be completed)

## 4. Builds

(to be completed)

## 5. Flags

(to be completed)

## 6. Tests

(to be completed)

## 7. Decisions only the owner can make

(to be completed)
