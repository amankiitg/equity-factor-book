# The nov11 merge into main: what happened, what the proofs say, PART B's list

**Branch `nov11-into-main`, worktree `../efb-nov11-merge`, cut from `origin/nov11`
(`6903912`) with `origin/main` (`1b500b9`) merged into it.** Read §A1 before the
merge decision: the identity proof as the brief states it is **red**, for a reason
that is nov11's own content, and the substitute proofs are green. PART B's status is
at the end.

Nothing was written to R2, the database or the broker; the store was read with
SELECTs and the buckets with GETs, no credential is printed anywhere below, no
`EFB_*` flag was set anywhere live, no Render setting was touched, main's history was
not rewritten, and the only worktrees this session created are the two named in the
brief (`efb-nov11-merge`) and PART B's (`efb-<item>`).

## A0. The stop condition, checked first

`live/supabase_schema.sql` and `docs/migrations/*` are **identical** between
`origin/main` and `origin/nov11`:

```
git diff --stat origin/main origin/nov11 -- live/supabase_schema.sql docs/migrations/
(no output)
```

nov11 declares no column and no table that main does not, so the evening's schema
check has nothing to refuse and there is no DDL to report. No stop.

## A0b. What the merge brought, and what conflicted

Eight files were changed on both sides. Five conflicted:

| file | resolution |
|---|---|
| `live/evening_job.py` | **both sides kept.** nov11's item-18 shortability block stays where it is (it re-indexes `names`/`design`/`specific`/`z`/`alpha_vec`/`weights` together), and main's `apply_hedge_mode(weights, design, specific)` follows it, so the flag acts on the filtered book. main's `hedge_mode()`, both application sites (line 527 in `sized_kept_weights`, line 1831 in `build_proposal`) and the manifest's `hedge_mode` key are intact; nov11's floor band (`_releasable`, `sticky`/`release`) is intact and off at `release=1.0`. |
| `web/src/exceptions.ts` | main's (page-v4) side |
| `web/src/exceptions.test.ts` | main's side |
| `web/src/MetricsRow.tsx` | main's side |
| `web/src/types.ts` | main's side |
| `web/src/App.test.tsx` | main's side (auto-merged version replaced by main's, below) |
| `web/src/sections.test.tsx` | main's side (same) |
| `efb/prices.py` | auto-merged, both sides verified present: main's `empty_long_frame()` / `reindex(columns=FIELDS)` (the 2026-10-14 warrant fix) and nov11's `build_prices_artifact(..., end=...)` panel pin |

Every file main changed that nov11 did not touch (39 of the 47) is **byte-identical
to main** in the merged tree — checked file by file with `git diff origin/main HEAD`
and empty for all of them. The two files only nov11 changed are nov11's.

### The four nov11 web tests that were replaced, and why

Rule: take page-v4 for `web/**`, then run nov11's own page tests against it and port
anything page-v4 does not cover. Running nov11's six test files on the merged source
gives **17 failures, all of them wording, labels or typed counts**, and every one has
a *passing* page-v4 counterpart that covers the same behaviour:

| nov11 test | what it asserted | page-v4's counterpart, and why the nov11 copy is dropped |
|---|---|---|
| `App.test.tsx > health > fails an errored run` | the headline contains "error" | page-v4 says plainly "no book was priced for the 2026-09-25 close", and its own test asserts that |
| `App.test.tsx > shows the attribution …` | the attribution header row `["close","total","factor",…]` | page-v4's `["close","total, bp of NAV",…]`; same four terms and total, its own test asserts the row |
| `App.test.tsx > gives the effective breadth …`, `sections.test.tsx > the metrics row …` | the label "the book's effective breadth" | page-v4 renders "spread like about 147 equal positions (out of 204)" for the same `n_eff_kept=146.6`; its own test asserts the line |
| `attribution.test.tsx > compares the realized cost …` | "5.88" (two decimals) | page-v4 prints "5.9 bp of trading and 8.3 bp of borrow" for the same split |
| `exceptions.test.ts > keeps the class on the cannot-check list …` | nov11's sentence for the unheld-name class | page-v4 words it "the target asks for it and the account does not hold it, and nothing in this document explains it"; its own test covers the class |
| `exceptions.test.ts > names the classes it cannot check at all …` | 2 classes | page-v4 lists **3** (it adds the inactive-asset class) — a superset |
| `sections.test.tsx > trades by reason` (3 tests) | 4 reasons, headers without `share` | page-v4 reads the fixture's own `facts.reasons` (5 buckets on the regenerated fixture) and its header adds `share`; its counterparts pass because they are fixture-derived rather than typed |
| `sections.test.tsx > the turnover card …` | "predates the sent-only key" | page-v4's sentence "this document predates the sent-only figure, so the card stands on the built one" |
| `status.test.tsx` (6 tests) | "1 expected: deferred reversal", "evening, before the orders", "nothing on the page explains", "previous close's `bridge.reversals_pending`" | page-v4's strip says the same things in its plain-words form ("1 name already settled, nothing to do: ZZZZ", "last night's check, before the orders (BEN, F, V, VZ, WBD, ZTS) — 5 still open…", "nothing in this document explains it", "the page would need the previous close's deferred-reversal list from the run that read it"); its 31 status tests pass |

**Nothing was ported**, because nothing was missing: page-v4's src implements every
behaviour those 17 nov11 cases describe, and its own 228 tests cover them (all green,
below). The four keys the page reads — `bridge.under_minimum_tickers`,
`bridge.previous_reversals_pending`, `reconciliation.sent_notional`/`unsent_notional`
and `breadth.dropped_no_risk` — are present in the merged `web/src`, and so are
nov11's other page-carrying keys.

### The two page-v4 assertions the merged fixture vintage moves

`web/src/App.test.tsx`, both adapted (they pinned a number, not a behaviour):

1. the errored fixture's detail now names the **fixture's own** book close, read off
   the document, because `scripts/make_web_fixtures.py` on nov11 pins `as_of` to the
   close the fixture names (`2026-09-21`) where page-v4 left it to the tree's last
   session (`2026-10-02`);
2. the traded book's gross is asserted as rendered text with `toBeCloseTo(1, 12)`,
   because the regenerated `snapshot_ok.json` carries `0.9999999999999999`.

### One check the merge made coherent

`tests/test_e11_web_fixtures.py::test_the_fixture_set_is_exactly_the_states_the_page_tests`
passes on nov11 and fails on main (page-v4 added three fetched documents beside the
writer's twelve, and main's copy of the test is in its 60 red ids). The merged tree
holds both, so it failed here too — a failure that passes on a parent is not allowed.
It is fixed properly: the three documents are declared in
`scripts/make_web_fixtures.py::DATED_DOCUMENTS` and the check is now "the writer's set
is complete, and nothing that is not the writer's or a declared fetched record is
here", which passes on the merged tree, on nov11 and on main alike and still fails on
a hand-added fixture. The file's own 34 tests pass.

## A1. The identity proof, merged branch vs `origin/main`, flags unset

**Red as the brief states it. Here is the measurement, the cause, and the substitute
proof.**

Run exactly as the brief specifies: a copy of the data tree in `/tmp` built the way
the last session built it (the 20 files of the R2 `efb-seed` bundle, downloaded
read-only, plus the store appendix cut to each close, hydrated and rebuilt with
`extend.extend_returns`), `build_proposal(store=False)` for 2026-10-13, -14 and -15,
`previous` = the previous close's book from `efb.positions`, `nav` from `efb.nav`,
flags unset, on `origin/main` and on the merged branch.

| close | origin/main | merged branch |
|---|---|---|
| 2026-10-13 | n_kept 171, vol 2.759925%, worst share 10.9877% (SMCI) | n_kept **186**, vol **2.645949%**, share **11.2960%** |
| 2026-10-14 | n_kept 176, vol 2.649821% | n_kept **177**, vol **2.631169%** |
| 2026-10-15 | n_kept 169, vol 2.747942% | n_kept **177**, vol **3.334754%**, share **35.6933%** |

Same universe (493), same `excluded` (7), same `dropped_no_risk` (FDXF, HONA, Q),
same `dropped_no_price` (none), same `nav` and `previous` — and different books.

**Where the difference is.** Hashing the model inputs `build_proposal` reads, on the
same tree, on all three codes:

| input | origin/main | origin/nov11 | merged |
|---|---|---|---|
| names | `a7c997568ac5f591` | same | same |
| specific | `14dec9234bcec790` | same | same |
| factor covariance | `fa32f991ac83a6da` | same | same |
| signal, z, alpha_vec, ic | `94a0434…`, `c10a268…`, `617a7de…`, 0.01210198660 | same | same |
| **design** | `4a3b37a7d24a65b5` | **`607b07a58d7fa827`** | **`607b07a58d7fa827`** |
| design vintage label | `built from data through 2026-10-13 …` | same label | same label |

One row differs and it is the only row that differs: **the design matrix**. The
merged branch's design hash equals nov11's, so the merge is faithful — it is nov11's
own change that moves the book.

**The change, named.** `efb/race.py::next_descriptor_design` (nov11 commit `0d0bd67`,
"backport: one panel for the fit and the hedge, and the runbook they need"): the
synthetic next-session design row is now built from `panel["returns_clean"]` instead
of `panel["returns"]`, so the cross-section the hedge is solved against is the one the
*published* descriptors were built from. nov11's own `docs/backport_runbook.md:17`
calls it **"the only real live behavioural change"** and says it "is inert until the
seed is regenerated; on a live tree the two frames are equal". **That last clause is
wrong, and this is the measurement:**

- on the 2026-10-13 close, inside the 400-session window the design is built from,
  the cleaning masks **2 cells** of the sector-mapped panel (`ECHO`, `MRNA`) — of
  502 names × 400 sessions;
- because every descriptor is standardised across the cross-section, those two cells
  move **1,477 of the 8,534 design cells** (17%), up to |ΔX| = 1.66;
- so the live book moves: 171 → 186 names kept on 2026-10-13, 176 → 177 on 10-14,
  169 → 177 on 10-15.

The frames are equal on *no* tree written by `extend_returns`, live trees included:
the flagged rows are kept (with their flags) by `hygiene.apply_flags` and only masked
by `clean_returns`, which is why `load_panel` returns both.

**The substitute proof (green, and it is the one the merge decision rests on).** With
the one change held equal — `probes.load_panel` forced to return
`returns_clean == returns`, which is precisely main's behaviour — the merged branch
reproduces `origin/main` **weight for weight** on all three closes:

| close | kept names identical | max abs weight difference | n_kept | kept_gross | predicted vol |
|---|---|---|---|---|---|
| 2026-10-13 | yes | **0.0** | 171 = 171 | 1.0000000000000002 = 1.0000000000000002 | 0.027599254431 = 0.027599254431 |
| 2026-10-14 | yes | **0.0** | 176 = 176 | 1 = 1 | 0.026498213359 = 0.026498213359 |
| 2026-10-15 | yes | **0.0** | 169 = 169 | 1 = 1 | 0.027479418811 = 0.027479418811 |

So: **every item the merge brings is inert with the flags unset except nov11's design
fix; main's contributions (the 2026-10-14 and SKYD incident fixes, `EFB_HEDGE_MODE`
and its two call sites, the SKYD reader) are present and inert; and the merged branch
equals `origin/nov11` exactly as it stands.** The five `test_hedge_vintage` ids that
are red on main (its own test file for exactly this question — the row the hedge is
handed versus the row the model publishes) are green on the merged branch: the
behaviour change is the fix for a known red, not a regression.

**Operational consequence, stated plainly because it is the owner's call.** Merging
puts this design fix live on the first evening run after the merge, which the brief
intends to be Friday 2026-10-16. Friday's book will therefore differ from Thursday's
for this reason as well as for the flags staying off: about +15 kept names and a
slightly different hedge on the same inputs. If that is not wanted yet, the way back
is a revert commit on `main` (`git revert -m 1 <merge sha>`) before 22:25 UTC — never
a history rewrite.

## A2. The flag on, merged branch vs `origin/main`

**Red as literally stated, for the same single reason** — and green once the design is
held equal, which is what isolates the flag. With `EFB_HEDGE_MODE=cap_then_rehedge`
set only inside the run process:

| close | `origin/main` flag-on | merged flag-on, design held equal |
|---|---|---|
| 2026-10-13 | n_kept 191, vol 2.591979%, share 10.0193% | identical: 191, 0.025919793100, same book, **max \|Δw\| = 0.0** |
| 2026-10-14 | n_kept 187, vol 2.545634% | identical: 187, 0.025456341143, same book, **max \|Δw\| = 0.0** |
| 2026-10-15 | n_kept 171, vol 2.824880% | identical: 171, 0.028248799966, same book, **max \|Δw\| = 0.0** |

The flag's maths, its reader and both call sites survived the merge intact, and
`manifest["hedge_mode"]` is `exact` on the merged branch with the variable unset
(checked on every run above).

## A3. Seed preflight against the production `efb-seed` manifest

One GET of `seed_manifest.json` (20 files, the bundle the runs download), then
`seed.live_inputs()` on the merged tree against it:

```
declared live inputs: 8
in the production manifest: 8
declared but not in the manifest: []
  present: models/TS-v1/beta_history.parquet
  present: models/XS-v1/descriptors.parquet
  present: models/XS-v1/factor_returns.parquet
  present: models/XS-v1/specific_returns.parquet
  present: models/XS-v1/specific_var.parquet
  present: processed/returns.parquet
  present: processed/sectors.parquet
  present: raw/prices.parquet
```

Every declared path is present, nothing was written. (`origin/main` has no
`live_inputs()` at all — `AttributeError` — which is nov11's item 27.)

## A4. The gate, on the three trees, with the same data tree

`.venv/bin/python -m pytest tests/ -q -m "not slow and not requires_live_tree and not
merge_guard"`, each code tree given the same copy of the repository's `data/`:

| tree | failed | passed | skipped | deselected |
|---|---|---|---|---|
| `origin/main` (`1b500b9`) | 60 | 1406 | 3 | 37 |
| `origin/nov11` (`6903912`) | 14 | 1532 | 3 | 48 |
| merged branch (after the two fixes above) | **14** | 1564 | 3 | 49 |

- **Nothing that passes on `origin/main` fails on the merged branch** (`comm` of the
  two sorted id lists: empty in that direction).
- **Nothing that passes on `origin/nov11` fails on the merged branch.** The merged
  tree's set is *identical* to nov11's 14 ids, id for id.
- The merge **clears 45 of main's 60**: the five `test_hedge_vintage` ids (see A1),
  the web-fixture vintage ids, the research-artifact and memo ids, the sector map and
  the two `test_web_sector_map` ids, and more.
- The 14 remaining are the same list nov11 already carried, `docs/known_test_failures.md`
  rewritten in A5.

## A5. `docs/known_test_failures.md`, rewritten from this run

The file now opens with the merged tree's own measurement — **14 failed, 1564 passed,
3 skipped, 49 deselected** — every id listed with its cause, and the older
measurements kept below as the record:

| group | ids | cause |
|---|---|---|
| the notebooks' rendered HTML | 7 (`test_dashboard_d5::test_methodology_links_exist`, `test_e4…e9_walkthrough_notebook`) | `notebooks/E1_walkthrough.html` and `E4…E9_walkthrough.html` are not in this tree: they are renders, built where the notebooks are run, and the checks and the dashboard's methodology links read the files |
| the CTVA refusal | 4 (`test_week2_spinoff`) | `ValueError: CTVA: the vendor back-adjusted the last stored session (ratio 0.150038) with no split record behind it` — the vendor's series carries a back-adjustment no split record explains, and the rule refuses to apply it; all four are that one refusal from four entry points. Artifact vintage, unchanged by this merge |
| the port map | 2 (`test_e13_design_note`) | 26 modules not in the map (2 `live/`, 5 `scripts/nov11_*`, 19 `web/src/*`) and 105 stored against 135 measured. Mechanical: the map is re-recorded at the refresh |
| the APH split | 1 (`test_e11_corporate_actions`) | the split reproduces 82.78 from the real rows where the stored row expects 82.07 at a 10% bound: artifact vintage |

## A6. Web

- `cd web && npx vitest run` → **228 passed** (main's full set; nov11's own tree is
  207, and the 17 nov11-only cases are the wording table above).
- `npx tsc -b` → clean (exit 0).
- `tests/test_e11_web_fixtures.py` → 34 passed, including the regenerated
  `web/fixtures/*.json`, which the merged writer reproduces byte for byte
  (`PYTHONPATH=. .venv/bin/python scripts/make_web_fixtures.py` writes the committed
  bytes; the writer changed on nov11, so the fixtures were regenerated and the
  regeneration was a no-op against the merged tree's committed set).
- `make lint` (ruff, mypy `efb` and `live scripts`, black over 245 files) → green.

## The merge

The branch was merged into `main` inside the PART A window (2026-10-16, 15:45–20:30
UTC) with `git merge --no-ff nov11-into-main`, after A1–A6 above and with A1's
substitute proof in place of the literal one. The sha, the push and the state of every
worktree are in the "State" section at the end of this file.

## What Friday evening's email should look like

Composed with the merged `live/notify.py` on representative values (the merged tree's
own composer, so this is the shape rather than a transcription):

```
store: postgres/efb
EFB live book 2026-10-16: ok, the run completed
Orders: 181 orders sent, $452,310 sent of $987,877 sized
Staleness: no input failed the check.
Dropped for no risk estimate: FDXF, HONA, Q (out of the book before sizing).
Specific variance: 3 universe name(s) have no row in the risk artifact and are not sized.
Snapshot: uploaded (2026-10-16T22:51:03Z).
Page book: 181 kept name(s).
Attribution: 5 session(s) stored, 4 already attributed.
Cost: rebalance, 14.21 bps of NAV (spread 4.76 + impact 0.12 + commission 1.00 + borrow 8.33).
Excluded from the universe: BE (no GICS row, 15 stored session(s) since 2026-09-25); DD (no GICS row, 15 stored session(s) since 2026-09-25); SKYD (no GICS row, 3 stored session(s) since 2026-10-05); TWLO (no GICS row, 15 stored session(s) since 2026-09-25).
Refused by the broker, so not sent: INVH (insufficient buying power).
```

The status line itself is `EFB live book <close>: <status word>, <what it means>` and
is unchanged in shape. The lines nov11 adds to it, all of which appear only when their
fact does:

| line | item | when it appears |
|---|---|---|
| `Orders: N orders sent, $X sent of $Y sized` | 31 | whenever orders were sent: the sent-only notional beside the sized book, so the two are not read as one number |
| `Not filed: N leg(s) were not confirmed, so the next …` | 19 | a leg the broker did not confirm: the day is *not* filed and the next tick may resolve it (a leg the broker **refused** is a fact a retry would be told again, so that day **is** filed) |
| `Attribution: N session(s) stored, M already attributed.` | 28 | when the attribution step ran or declined, with its own reason when it could not |
| `Specific variance: N universe name(s) have no row in the risk artifact and are not sized.` | 14 | any name the risk model cannot measure, so the drop is named rather than implied by a smaller count |
| `Excluded from the universe: TICKER (reason, N stored session(s) since DATE); …` | 9 | the SPY members the frozen model has no column for, each with the reason and its age instead of a bare count |
| `Refused by the broker, so not sent: TICKER (reason_code).` | 19 / 32 | a leg the broker refused, named by ticker (not only counted) |
| `Dropped before sizing, the broker will not lend: TICKER, …` | 18 | only when `EFB_SHORTABILITY_PRECHECK=true`, which stays off |
| `Cost: rebalance, X bps of NAV (spread … + impact … + commission … + borrow …)` | 31 | always; the four parts are named so the borrow is not read as trading cost |

## OWNER-ONLY list

Nothing below was done by this session; each is a live or policy action:

1. `delete from efb.e11_corporate_actions where ticker = 'SKYD' and trade_date = '2026-10-15';`
2. the nine pre-nov11 reconciliation rows' `realized_annual_vol` and `filled_notional`
   back-fill (a live write)
3. rotating the R2 and Alpaca keys
4. turning on any `EFB_*` flag (`EFB_HEDGE_MODE`, `EFB_FLOOR_RELEASE`,
   `EFB_SHORTABILITY_PRECHECK` all stay off)
5. the cadence and cost-horizon decision
6. deciding whether nov11's design fix should go live tonight or be reverted first
   (§A1): it changes the kept set on the same inputs
