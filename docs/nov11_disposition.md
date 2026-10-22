# The nov11 list, item by item: where each one lives now

The nov11 work list was triaged in `docs/nov11_overnight_report.md` (items 1-33), built in
one batch, and merged to `main` as **`9e484f9`** ("Merge nov11 into main, with the design
change off by default", 2026-10-19). Five later items were built on their own branches and
merged one at a time on 2026-10-20. This file is the disposition: every item, what it was,
what happened to it, and where it can be found.

Statuses are exactly one of:

- **MERGED** - in `main`'s history; the commit or merge is named.
- **FLAGGED** - in `main` but inert until an `EFB_*` variable is set; the variable is named.
- **PARKED** - not in `main`; an `archive/<branch>` tag holds it, or it waits on an
  owner decision that no code can make.
- **DROPPED** - deliberately not done, with the reason the source gives.
- **OPEN** - no trace of it being done or dropped; named as open rather than guessed.

## Summary counts

| status | count | items |
|---|---|---|
| MERGED - in `main` and live | **24** | 1, 2, 3, 4, 5, 6, 7, 9, 14, 15, 16, 17, 19, 20, 21, 22, 23, 26, 28, 29, 30, 31, 32, 33 |
| FLAGGED - in `main`, inert until a variable is set | **2** | 12 (`EFB_FLOOR_RELEASE`), 18 (`EFB_SHORTABILITY_PRECHECK`) |
| PARKED - not in `main`, waiting on the owner | **3** | 8 (a trading decision), 11 (writes `efb.e11_prices`), 24's relabel |
| OPEN - no trace of it being done or dropped | **2** | 10, 13 (both triaged RESEARCH and never attempted) |
| DROPPED | **0** | - |

Two items are half in and half out, and the table below says which half: **25** (the
bridge term is item 22's; the broker read needs broker calls) and **27** (the preflight is
in; the push-side check needs a seed push). Item 24 is split three ways - research in,
relabel not done, and the hedge comparison now built as `EFB_HEDGE_MODE` and default-off.

## The list

| # | item | status | where it lives |
|---|---|---|---|
| 1 | the bridge cannot say a name arrived | MERGED `9e484f9` | `live/bridge.py:245` (`arrived_without_order`), counted in the identity's right-hand side at `:260` |
| 2 | the morning's cost line compares against the full cost, not the trading half | MERGED `9e484f9` | `live/notify.py` cost card, which now names the trading half |
| 3 | `reconciliation.filled_notional` is stored as `0` | MERGED `9e484f9` | the morning writes the number it already has; the live table now carries it (e.g. 2026-10-15: $429,573) |
| 4 | the morning reconciles the previous close a second time | MERGED `9e484f9`, then hardened by **B1** `50178c7` | `live/morning_job.py` completion record; `scripts/reconcile_fills.py` reads it |
| 5 | the NOT NULL NaN audit (28 columns) | MERGED `d45ef9e` (**B6** - same title, same item) | `scripts/nov11_notnull_audit.py`, `docs/nov11_notnull_audit.md`: 28 columns, 28 clean |
| 6 | a filled risk estimate is never reported | MERGED `9e484f9` | `live/evening_job.py:2810` (`n_specific_var_missing`) on the manifest, and the message beside it; the median fill itself stays |
| 7 | the sizing universe is not the risk universe | MERGED before the batch (`ab6955e` line of history) | `live/evening_job.py` `risk_names_or_stop` / `dropped_no_risk` / `MAX_RISK_DROPS` |
| 8 | a name with risk but no signal has no stated treatment | **PARKED** - the count is reported, the treatment is the owner's | count: `n_dropped_no_risk`; treatment (hold / hedge-only / exclude) is a trading decision and nothing in the code presumes one |
| 9 | `excluded` has no reason and no age | MERGED `9e484f9` | `live/evening_job.py::exclusion_reason` (`EXCLUDED_NO_GICS`, `EXCLUDED_NO_GICS_NO_PRICES`, `EXCLUDED_NO_RETURNS`) plus `excluded_detail` with its age |
| 10 | why is DD missing from `processed/returns.parquet`? | **OPEN** - triaged RESEARCH, not attempted | the build's own record of the 2025-11 spin-off is the place to look; no code and no note exists |
| 11 | the pricing fetch still spells PSKY | **PARKED** - blocked on a live write | resolving the rename changes the sized universe (SKYD becomes sizeable), so it is a trading change, and applying it writes `efb.e11_prices`, which is the owner's |
| 12 | the floor's hysteresis is unmeasured | **FLAGGED** `EFB_FLOOR_RELEASE` | built and off, with a measured negative result: `live/evening_job.py` floor band (`_releasable`, `sticky`/`release`), off at `release=1.0` |
| 13 | six names in the risk block outside the universe | **OPEN** - triaged RESEARCH, not attempted | no note and no count exists |
| 14 | one source for the specific variance | MERGED `9e484f9` | `store_proposal` refuses against the manifest's own `dropped_no_risk`, or takes the vector |
| 15 | zero is asymmetric | MERGED `9e484f9` | the write's refusal and the drop's predicate share one non-positive test |
| 16 | `dropped_no_risk` is not on the page | MERGED `9e484f9` | `live/snapshot.py:304` (`n_dropped_no_risk`, `dropped_no_risk`) |
| 17 | the SPY ticker list is not deduplicated | MERGED `9e484f9` | `live/evening_job.py:2272` (`spy_tickers = sorted(set(raw_tickers))`) |
| 18 | shortability is checked after sizing, not before | **FLAGGED** `EFB_SHORTABILITY_PRECHECK` | `live/evening_job.py` precheck block, default off, with an injected flag source so the flag-on path is testable |
| 19 | a refused leg reads ERROR and exits nonzero | MERGED `9e484f9` | `live/notify.py:1039` (`INCOMPLETE`), `live/morning_job.py:67` (`INCOMPLETE_STATUSES` / `INCOMPLETE_REASON_CODES`) |
| 20 | the evening's retry guard cannot see a close that already traded | MERGED `9e484f9`, extended by **B2** `ac38c4e` | `scripts/run_live_daily.py:973` (a traded second start is not re-priced) and `:1005`; B2 makes the traded start carry the first attempt's detail |
| 21 | the message's order count is the legs built, not sent | MERGED `9e484f9` | `live/notify.py:453` counts the legs with a broker id, the same thing `sent_notional` measures |
| 22 | the bridge cannot say a name exited with no order | MERGED `9e484f9` | `live/bridge.py:159` (`exited_without_order`), counted at `:304` |
| 23 | seven reds are missing from `known_test_failures.md` | MERGED `9e484f9` | `docs/known_test_failures.md`, refreshed from a gate run with one id and cause each |
| 24 | the hedge concentrates single-name risk | **PARKED + FLAGGED + OPEN** | research done (`docs/research/nov11_hedge.md` + two JSON files); the `variance_share_cap_binds` relabel is **not** done; the minimum-variance vs cap-then-rehedge comparison now exists as `EFB_HEDGE_MODE=cap_then_rehedge`, merged off by default in `1807479` and proven again on 2026-10-22 |
| 25 | an inactive asset is a corporate action, not a skip | **MERGED half + PARKED half** `9e484f9` | the exit-with-no-order term is item 22's (`live/bridge.py`); reading the broker's announcements and asset status needs broker calls, which are not allowed from the analysis sessions |
| 26 | `reconciliation.realized_annual_vol` is NaN on every row | MERGED `9e484f9` | `live/reconcile.py:247` (`realized_annual_vol_for`) computed where the morning writes the row; the NaN at `:206` is the evening's placeholder the morning replaces, and `scripts/backfill_reconciliation.py` filled the nine pre-nov11 rows |
| 27 | a new `data/` input read by a live path is a seed change | **MERGED (preflight) + PARKED (push-side check)** `9e484f9` | `live/seed.py` `record_reads` / `manifest_for`, and the preflight that refuses a read the manifest does not declare; the push-side check is blocked on a seed push |
| 28 | the attribution step's outcome goes nowhere | MERGED `9e484f9` | `scripts/run_live_daily.py:2257` `attribution_flags` onto the run row, and one consequence line in the message; on 2026-10-22 this became `n_refinalized` |
| 29 | `beta_history` should be read with a fallback | MERGED `9e484f9` | `efb/attribution.py:320` `_read_betas` - `except FileNotFoundError`, two empty columns and a warning instead of an empty section |
| 30 | publish the previous close's deferred reversals | MERGED `9e484f9`, consumed by the cadence work | `live/bridge.py:180` (`previous_reversals_pending`), `live/notify.py:406` (`deferred_reversals`); `reversal_targets` on the manifest since `a25557b` is what forces the second leg |
| 31 | publish the sent-only notional | MERGED `9e484f9` | `sent_notional` / `unsent_notional` on the reconciliation row and the snapshot |
| 32 | publish the under-minimum tickers | MERGED `9e484f9` | the set the count is already taken from (`live/evening_job.py`, `live/bridge.py` `under_minimum`) |
| 33 | `filled_notional` is `0.0` on every live row | MERGED `9e484f9` | the same fix as item 3 |

## The B items, and whether they have item numbers

PART B's six items were built later than the 1-33 list and mostly are not numbered. One
is a straight duplicate of a numbered item; the rest are defects found in the live run
that the list did not name, and they have no number to map to:

| B | merge | number | what it is |
|---|---|---|---|
| B1 | `50178c7` | relates to **4**, not the same item | reconcile-once reads the morning's filed completion record (its `run_status` row or the published block) rather than `efb.fills` alone |
| B2 | `ac38c4e` | relates to **20**, not the same item | a traded second start carries the failed first attempt's detail instead of overwriting it |
| B3 | not built | - | the shortability precheck applied to the *final* traded weights; a real refactor of the live construction and unprovable with the flag off, so left unstarted rather than half-landed |
| B4 | `425fcc1` | none - a new defect | the pre-hedge reconstruction squares `idio_vol` before sizing (`alpha / sigma^2`, where `positions.idio_vol` is sigma). This is the fix `scripts/recompute_attribution.py` applies |
| B5 | `9c3b0c3` | none - a new defect | a catch-up that priced a book reads green `PROPOSAL RUN: OK (caught up N sessions)` |
| B6 | `d45ef9e` | **is item 5** (same title, same audit) | the NOT NULL NaN audit against the live database |

## Archive tags that hold nov11 work

| tag | what it holds |
|---|---|
| `archive/nov11-into-main` | the report and not-null audit as they stood at the merge, and the branch's own history |
| `archive/flag-cap-then-rehedge` | `EFB_HEDGE_MODE=cap_then_rehedge` and the flag-on table naming every name it moves |
| `archive/page-v4` | the page's fourth round, which the nov11 merge took for `web/**` |

Restore any of them with `git checkout -b <branch> archive/<tag>`.

## What is genuinely open

1. **Item 8's decision**: whether a name with risk but no signal is held, hedge-only, or
   excluded. Code cannot choose this.
2. **Item 11**: PSKY's rename is not applied, because applying it writes `efb.e11_prices`.
3. **Item 24's relabel** (`variance_share_cap_binds`) and the hedge comparison, which is
   now measurable: `EFB_HEDGE_MODE=cap_then_rehedge` has been proven off-by-default twice.
4. **Items 10 and 13**, the two research questions, were never attempted. They need a
   measurement each, not a decision.
5. **B3**, the final-weights shortability loop.
