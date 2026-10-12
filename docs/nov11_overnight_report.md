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
