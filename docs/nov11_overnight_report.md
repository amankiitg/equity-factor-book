# Resume here

**Branch `nov11`, pushed to `origin/nov11`.** `main` is untouched at `37b0287` (the
page-v3 merge; it was `1e405be` when this batch was cut). Nothing is deployed, nothing
was merged to `main`, neither R2 bucket nor the broker was called, the live database was
only ever read (and only through `live/store.py`), and no secret was printed. Working
tree clean apart from the untracked `artifacts/` folder from the page review.

## What this batch did, in the order it was asked for

STEP 0, the page-v3 merge onto `nov11`: **completed with no conflicts** (`2613dc2`,
parents `eac1aad` + `37b0287`). `main`'s page-v3 touched `web/src` only, so both sides
survive by construction - page-v3's morning account-vs-target check, freshness clock and
sector drivers, and this branch's new bridge terms. The fixture writer did not change, so
the fixtures were not regenerated; `tests/test_e11_web_fixtures.py` passes 34/34, the web
suite is **207 passed** (was 186 before page-v3 arrived) and the full Python suite on the
merged tree is the same seven reds as the pre-merge baseline.

Then the build queue, one commit per item, in the order given:

| order | item | commit | what landed |
|---|---|---|---|
| 1 | 3 / 33 (+ the write half of 26) | `9f68c89` | the morning back-fills `filled_notional` and `realized_annual_vol` |
| 2 | 28 | `8a4c709` | the attribution step's outcome reaches the run row and the message |
| 3 | 31 | `6dbd0c1` | the sent-only notional is published and the turnover card stands on it |
| 4 | 32 | `1bad999` | a floor-skipped leg classifies by ticker, not by count |
| 5 | 16 | `4d54469` | the names the risk model could not measure are published and drawn |
| 6 | 30 | `90a87ed` | the previous close's deferral list is republished, and decides the class |
| 7 | 14 | `ac22681` | one source for the specific variance: the manifest's own drop record |
| 8 | 27 | `8a1b368` | the evening refuses a seed that does not cover every live input |
| 9 | 19 | `1aaca52` | a refused leg is INCOMPLETE and the day is filed; an unconfirmed one retries |
| 10 | 20 | `f072f2e` | a close whose legs are at the broker is not priced again |
| 11 | 4 | `23e6b5d` | the morning reconciles a close once |
| 12 | 9 | `b60e263` | an excluded name carries a reason and an age |
| 13 | 5 | `fb36ca0` | the NOT NULL NaN audit, and the seven columns it could not read |
| 14 | 12 | `c17a40f` | the floor band as a default-off flag, with a measured negative result |
| 15 | 18 | `82cb4a6` | the broker's lending flags, read before the sizing, behind a flag |
| 16 | cadence | `65945a1` | the memo, and why the switch is not built |
| 17 | 23 | this commit | the known-failures refresh, from the gate's own command |

## What is NOT done, and why (the next session starts here)

1. **Item 11 (the PSKY/SKYD rename at the pricing fetch)** - not built. It changes the
   sized universe (SKYD becomes sizeable), and *applying* it needs a fetch that writes
   `efb.e11_prices`, which is the owner's. The flag is straightforward once the fetch is
   allowed: resolve the rename where the prices are read, behind a default-off flag, with
   the identity proof on the current tree. The evidence is in the runbook (item 11) and
   in `docs/research/nov11_hedge.md`'s PSKY note.
2. **The cap-then-rehedge hedge** - not built. The research recommends it
   (`docs/research/nov11_hedge.md`: it holds both the 10% cap and exact neutrality at
   lower vol, same turnover), and it is a trading change the owner has to approve even
   behind a flag. The next step is the flag in `live/evening_job.py`'s hedge step with
   the same two-build identity proof the floor band got.
3. **Item 5's live half**: the audit tool is committed and it runs, but this session has
   no `EFB_SUPABASE_DB_URL`, so seven columns read `not read`. Running
   `.venv/bin/python scripts/nov11_notnull_audit.py --out docs/nov11_notnull_audit.md`
   with the URL set closes it.
4. **Item 26's historical rows**: the write half is in (`9f68c89`), so every row written
   from now on carries a measured `realized_annual_vol`. The nine rows already stored
   keep their NaN until someone runs the back-fill over them, which is a live write.
5. **Items 10 and 13** (why DD is missing from the returns panel; the six names the risk
   block carries that the universe does not) were RESEARCH items and were not in the
   queue this batch was given. Not attempted.
6. **Item 24's relabel** (`variance_share_cap_binds` is computed on the traded book, not
   the sizing stage): the research is done, the relabel itself is one comment and one
   label in `live/reconcile.py`/the page, and it is not done.
7. **Item 23** is done in the same commit as this report: see section 6.

## Background processes

None running, nothing detached and no stash. Three gate-suite runs were waited on - the
merge, the mid-batch check and the final one - and the throwaway `git worktree` of `main`
used to ask whether `main` itself was red was removed (`git worktree list` shows only the
checkout). One thing the next session should know about asking that question: the
worktree run **is not comparable** to the checkout's, because `live/state/` is git-ignored
and a fresh worktree has no store mirror, so dozens of tests fail on the mirror's absence
rather than on the code. `main` was measured instead by checking the checkout out
temporarily; `main` is red on the artifact-vintage ids this file records, and it is back
at `37b0287` with the branch checked out again.

## What the next session must know

1. **The seven reds are pre-existing** and are listed with causes in
   `docs/known_test_failures.md` (refreshed, section 6). Item 23's list is now the file's.
2. **Two flags are in the tree, both off**: `EFB_FLOOR_RELEASE` (item 12, with a
   measured negative result - read the note before turning it on) and
   `EFB_SHORTABILITY_PRECHECK` (item 18, unverified against the live broker).
3. **The floor band's measurement is a finding, not a bug**: on 2026-09-21's construction
   the band changes the kept set rather than holding it. `docs/research/nov11_turnover.md`
   has the table and the reason.
4. **`_rows()` in `scripts/run_live_daily.py`** is the one place manifest step-lists are
   turned into message rows; items 9/16/18 all use it.
5. **The page changed too**: `web/src/exceptions.ts` now has four expected classes and
   only two `UNCHECKED` ones, and `web/src/MetricsRow.tsx` stands the turnover card on
   `sent_notional` when the document carries it. The web suite is 207 tests; run
   `npx vitest run` in `web/` after any further `live/snapshot.py` shape change, and
   regenerate fixtures with `PYTHONPATH=. .venv/bin/python scripts/make_web_fixtures.py`
   whenever the snapshot writer changes (this batch did, twice).

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

### Status per item, at the end of this batch

| item | status | where |
|---|---|---|
| 1, 2, 3, 4, 5, 6, 9, 14, 15, 16, 17, 18, 19, 20, 21, 22, 26, 27, 28, 29, 30, 31, 32, 33 | **done** (two with a live-only half) | section 4 |
| 7 | **done on main before this batch**; the triage's numbers were re-checked against `risk_names_or_stop`/`MAX_RISK_DROPS` and hold | `live/evening_job.py` |
| 8 | **partly**: the count is reported (item 6); a name with risk and no signal still has no stated treatment, which is a trading decision | - |
| 10, 13 | **not attempted** - research questions that were not in the queue this batch was given | - |
| 11 | **not built** - applying it writes `efb.e11_prices`, which is the owner's | section 5 |
| 12 | **built and off**, with a measured negative result | section 5 |
| 23 | **done** - `docs/known_test_failures.md` refreshed with the branch's seven | section 6 |
| 24 | research done; the `variance_share_cap_binds` relabel is **not done** | section 3 |
| 25 | the bridge term is in (item 22); reading the broker's announcements is **blocked** (broker calls) | section 4 |
| cap-then-rehedge | **not built** - a trading change the owner has to approve | section 5 |
| cadence | **memo only**, and the memo says why | `docs/research/nov11_cadence.md` |

## 3. Research

Two notes, each with its numbers beside it in a JSON file, written before any code in
this batch.

**`docs/research/nov11_turnover.md`** - cost and turnover. The research engine charges
**no borrow at all**; the live cost model charges spread, commission and borrow as
21-session holding costs at a *1-session* frequency, so borrow is overstated 21x and it
is 99 bp of the 169 bp gross return - the design book's net Sharpe is 0.93 on the
engine's convention and **0.30 on the live one**. The live loop trades 40-50% of gross
every session against the panel's 35.6% once a month, about 25x the turnover per unit of
time, for 6.5-7.8% of NAV a year against a 1.7% gross edge. The floor's own churn is 147
round trips in nine closes, 84 returning the next session: **6.6 bp of NAV against a 0.67
bp per-session gross edge**, so the round-trip churn at the floor costs more than the
book's entire gross edge before any signal-driven trading is counted. Recommendation: fix
the cost model's horizon and add borrow to the engine before touching frequency.

**`docs/research/nov11_hedge.md`** - the hedge's concentration. The exact hedge leaves
20.4% mean and 28.8% worst single-name variance share on the live books since 2026-10-01
(SMCI 12.6% and MRNA created with no alpha on 2026-10-08, after a cap that held at 9.97%
pre-hedge). **Cap-then-rehedge holds both the 10% cap and exact factor neutrality at
lower vol and the same turnover** - recommended; minimum-variance factor neutralisation
has the lowest vol but 4.9% more gross and 81 flips; on the 176-month panel the three are
indistinguishable because the cap never binds there.

**`docs/research/nov11_cadence.md`** (written in this batch) - the three cadence shapes
side by side, why "run nightly, trade monthly" is a store/page design question rather
than a switch, and what the numbers say to settle first (the horizon, then the engine's
missing borrow).

## 4. Builds

One commit per item; two commits bundle two items each where the pair shares a file and a
test module (17+15, 1+22), which is disclosed here and in the commit messages.

| item | commit | the change | tests |
|---|---|---|---|
| 21 | `05e4896` | the message's order count is the legs with a broker id | `tests/test_nov11_sent_orders.py` |
| 2 | `cd1d2e9` | the morning compares realized cost against the trading half, borrow beside it | `tests/test_e11_notify.py` |
| 29 | `2fe6753` | a missing `beta_history` costs two columns, not the section | `tests/test_nov11_beta_fallback.py` |
| 17 + 15 | `8be4db6` | the universe is deduplicated; a zero variance is refused on both sides | `tests/test_nov11_universe_and_zero.py` |
| 6 | `e155072` | the count of names the risk block cannot measure is reported | `tests/test_nov11_missing_var.py` |
| 1 + 22 | `9c3268d` | the bridge names the legs it did not send and the position nobody ordered | `tests/test_e11_bridge.py` |
| 3 + 33 | `9f68c89` | the morning back-fills `filled_notional` and `realized_annual_vol` | `tests/test_nov11_reconcile_backfill.py` |
| 28 | `8a4c709` | the attribution step's outcome is a run-row flag and a message line | `tests/test_nov11_attribution_flag.py` |
| 31 | `6dbd0c1` | `reconciliation.sent_notional`/`unsent_notional` published; the card stands on the sent half | `tests/test_nov11_sent_notional_snapshot.py`, `web/src/sections.test.tsx` |
| 32 | `1bad999` | a floor-skipped leg is classified by ticker; the class leaves `UNCHECKED` | `web/src/exceptions.test.ts` |
| 16 | `4d54469` | `breadth.dropped_no_risk` published and drawn under the construction telemetry | `tests/test_nov11_breadth_drops.py`, `web/src/sections.test.tsx` |
| 30 | `90a87ed` | `bridge.previous_reversals_pending`, read from the document that is up, decides the class | `tests/test_nov11_previous_reversals.py`, `web/src/exceptions.test.ts` |
| 14 | `ac22681` | the write refuses against the manifest's own drop record, not a second artifact read | `tests/test_nov11_universe_and_zero.py`, `tests/test_run_live_daily.py` |
| 27 | `8a1b368` | `seed.preflight_inputs` refuses a tree that does not hold every declared live input | `tests/test_nov11_seed_preflight.py` |
| 19 | `1aaca52` | a refused leg is INCOMPLETE, named, filed, exit 0; an unconfirmed leg still retries | `tests/test_e11_notify.py`, `tests/test_run_live_daily.py` |
| 20 | `f072f2e` | the evening reads the close's own legs and refuses to re-price a traded close | `tests/test_nov11_retry_guards.py` |
| 4 | `23e6b5d` | the morning compares the close with the newest close it has reconciled | `tests/test_week1_fills_cron.py` |
| 9 | `b60e263` | `excluded_detail`: a reason per cause and an age from the stored manifests | `tests/test_nov11_excluded.py` |
| 5 | `fb36ca0` | `scripts/nov11_notnull_audit.py`, read-only, plus the mirror's answer | `tests/test_nov11_notnull_audit.py` |
| 12 | `c17a40f` | `EFB_FLOOR_RELEASE`: the band, off, with the identity proof and a measured negative result | `tests/test_nov11_floor_band.py` |
| 18 | `82cb4a6` | `EFB_SHORTABILITY_PRECHECK`: the broker's lending flags before the sizing | `tests/test_nov11_shortability.py` |
| cadence | `65945a1` | the memo; the switch is not built, and it says why | - |
| 23 | this commit | `docs/known_test_failures.md` refreshed from the gate's own command | the suite itself |

Six of the twelve web fixtures changed in this batch, and only because the snapshot
writer did: `reconciliation.sent_notional`/`unsent_notional` (item 31),
`bridge.previous_reversals_pending` (item 30) and `breadth.dropped_no_risk` (item 16) are
new keys on every document, all null or empty on the fixtures because the fixture writer
passes no source for them. Nothing else moved.

## 5. Flags

| flag | item | default | the identity proof | verified |
|---|---|---|---|---|
| `EFB_FLOOR_RELEASE` | 12 | unset = `1.0` = release at the floor | two builds of the live construction, kept book identical name for name and weight for weight (`tests/test_nov11_floor_band.py::test_the_default_book_is_identical_weight_for_weight`) | **built and off**, with a negative measurement attached |
| `EFB_SHORTABILITY_PRECHECK` | 18 | unset = off; only the exact word `true` opens it | no source injected means no name dropped: two builds, identical weight for weight (`tests/test_nov11_shortability.py`) | **built and off**; the read is exercised against a recorded feed shape, not the live broker |

**Not built, and why**: item 11's rename flag (applying it needs a fetch that writes
artifacts - the owner's), and the cap-then-rehedge hedge (a trading change the owner has
to approve even behind a flag; the research recommends it and the identity proof is the
same two-build pattern).

**The cadence flag**: not built either, and `docs/research/nov11_cadence.md` is the reason
rather than an excuse. "Run nightly, trade monthly" needs the loop to distinguish the book
it *publishes* from the book it *holds*, and today `efb.positions`, the snapshot's `book`,
the bridge's kept side and the page's sector deltas are one object; a switch wired into
the submission path alone would leave the positions check, the bridge's identities and the
page's exception count amber every non-cadence night with nothing wrong.

## 6. Tests

The gate command, run three times in this batch:

```
.venv/bin/python -m pytest tests/ -q -m "not slow and not requires_live_tree and not merge_guard"
```

| run | tree | result | what it proved |
|---|---|---|---|
| the page-v3 merge | `nov11` at `2613dc2` | 7 failed, 1483 passed | the merge itself added no red |
| mid-batch | `nov11` at `65945a1` | **14 failed**, 1531 passed | seven *new* reds, all of them tests the batch's own behaviour changes had written over |
| final | `nov11` at `d3d8a56` | **7 failed, 1538 passed, 1 skipped, 47 deselected** (11m48s) | zero new against the baseline |

The seven fixed between the second and third runs are the reason the per-item runs are
not enough, and they are listed in `d3d8a56`: item 19 moved the shortability refusal out
of `incomplete_legs` (`test_week1_borrow`, `test_e11_execution`, `test_e11_preflip_fixes`
asserted the old shape) and item 27's preflight refuses a tree that does not hold a
declared live input (`test_e11_staleness`'s synthetic tree wrote "all nine artifacts" and
now writes the tenth). Every one of the four is a *test* updated to the behaviour the
item asked for, not a behaviour reverted to make a test pass.

`docs/known_test_failures.md` is refreshed with the branch's own seven, each with its
cause (item 23): the four `test_week2_spinoff` ids are one CTVA back-adjustment refusal,
the two `test_e13_design_note` ids are the module-map enumeration (mechanical when a
branch adds modules), and the APH split is artifact vintage. The file's older 55-id
measurement on `main` is kept below them as the record of what the backport cleared.

Per-item tests, all green: `tests/test_nov11_sent_orders.py`,
`tests/test_nov11_sent_notional_snapshot.py`, `tests/test_nov11_breadth_drops.py`,
`tests/test_nov11_previous_reversals.py`, `tests/test_nov11_universe_and_zero.py`,
`tests/test_nov11_seed_preflight.py`, `tests/test_nov11_attribution_flag.py`,
`tests/test_nov11_reconcile_backfill.py`, `tests/test_nov11_retry_guards.py`,
`tests/test_nov11_excluded.py`, `tests/test_nov11_notnull_audit.py`,
`tests/test_nov11_floor_band.py`, `tests/test_nov11_shortability.py`, plus
`tests/test_e11_bridge.py`, `tests/test_e11_notify.py`, `tests/test_run_live_daily.py`,
`tests/test_week1_fills_cron.py`, `tests/test_e11_web_fixtures.py` and the web suite
(`npx vitest run` in `web/`: **207 passed**). `make lint` is clean (ruff, mypy on
`efb`/`live`/`scripts`, black).

The two ``slow`` identity proofs are marked `slow` and deselected by the gate command, so
they were run explicitly: `tests/test_nov11_floor_band.py -m slow` (12.1s) and the
`test_nov11_shortability.py` identity case (11.1s), both green.

## 7. Decisions only the owner can make

Ranked by what unblocks the most, and each one is a decision rather than a task.

1. **The cost model's horizon** (`docs/research/nov11_turnover.md`). The live loop trades
   every session while the model charges spread, commission and borrow on a 21-session
   horizon, so its largest term is overstated 21x. Every expected cost, every breakeven
   and every "was this trade worth it" answer rests on it. This is the one decision that
   changes what other decisions mean.
2. **Borrow in the research engine** (`efb/costs.py::_trade_cost` charges none). The
   design book was selected, and its Sharpe reported as ~1.0, on a cost model that omits
   the term that is 99 bp of its 169 bp live gross return; on the live model the same
   book's net Sharpe is 0.30. Adding it re-opens the E8 construction choice.
3. **The hedge**: cap-then-rehedge is recommended by `docs/research/nov11_hedge.md` and is
   not built; approving it is a trading decision, and the flag and its identity proof are
   a bounded piece of work once approved.
4. **The rebalance cadence** (`docs/research/nov11_cadence.md`): nightly, monthly, or
   run-nightly-trade-monthly. The third needs the published book and the held book to
   become two objects in the store, the bridge and the page - a design decision, not a
   switch.
5. **Whether to open `EFB_SHORTABILITY_PRECHECK`** (item 18). It changes the book, its
   breadth and its forecast by leaving out names the broker will not lend; the flag is
   built, off, and unverified against the live broker by design.
6. **Whether to open `EFB_FLOOR_RELEASE`** (item 12) - and to read the measurement first:
   on the live construction the band changes the kept set rather than holding it, so the
   shape that reduces churn is a no-trade band on the *leg*, which is its own decision.
7. **The three live-only halves**: running the NaN audit with `EFB_SUPABASE_DB_URL` set
   (item 5), back-filling `realized_annual_vol`/`filled_notional` on the nine stored rows
   (items 26/33), and the seed push that closes item 27's push side.
8. **Item 11's rename fetch**: applying it writes `efb.e11_prices`, so it is the owner's
   even though the flag is small.
9. **Items 10, 13 and 24's relabel**: two research questions left unanswered and one
   label to move. All three are cheap and none is blocking.
