# The nov11 merge into main: what happened, what the proofs say, PART B's list

## Resume here

**Resumed at 2026-10-16 22:15 UTC on the owner's second brief, and the first half of it
is done: A-1 is committed, A-2's four proofs passed, A-3's table is below, tonight's run
is clean, and A-4's merge is the one step left (it waits on the gate run, §A-4b). PART
B is five of six items built, tested and pushed; B3 is not started and its entry point
is named at the end of this file.**

`origin/main` was `1b500b9` when this session started and is unchanged until the merge.
The branch is `origin/nov11-into-main`; its tip is recorded at the end of this file.

The new brief's items are written `A-1` to `A-4` (with a hyphen) and the first
session's are `A0` to `A6`; both are below, the second half under its own headings.

### What this session changed on the branch

| commit | what | why |
|---|---|---|
| `a952213` | `EFB_DESIGN_RETURNS` in `efb/race.py`, on the manifest for every book | A-1: nov11's design panel is a live behaviour change, and the merge's default must be origin/main's |
| `c61c928` | the two `tests/test_live_panel_parity.py` checks state the flag's contract | one asserted the clean panel as the default, which is now the opt-in |
| `3611e04` | `live/extend.py::extend_model` takes its frame from `race.design_panel` too | one flag, one panel: the fit and the design cannot diverge in either mode |

### The exact next step

Run the gate (§A-4b), then merge `nov11-into-main` into `main` inside the owner's window
(23:00 UTC Friday 2026-10-16 to 20:30 UTC Monday 2026-10-19, and only while Friday's run
stays clean — it is):

```
cd /Users/amankesarwani/PycharmProjects/efb-nov11-merge
git fetch origin                                  # origin/main must still be 1b500b9
git checkout main && git merge --no-ff nov11-into-main
git push origin main
git rev-parse origin/main                         # record the sha here
```

If the push is rejected: fetch, merge the new `origin/main` in, re-run the identity proof
(§A-2) and the touched tests, retry once, then stop.

## A-2. The four proofs, on four closes including tonight's

Built exactly as the brief says: a copy of the data tree per close in `/tmp`, the R2
`efb-seed` bundle plus the store appendix cut to that close, `build_proposal(store=False)`
with `previous` = the latest stored book before it and that close's NAV from `efb.nav`.
The four closes are 2026-10-13, -14, -15 and **-16**, the last one from tonight's run
(hydrated 163,505 appendix rows; the 10-16 tree carries the session).

| proof | left | right | closes | result |
|---|---|---|---|---|
| flags unset (strict) | `origin/main` | `nov11-into-main` | 4 | **PASS** — same kept names, `max abs weight difference exactly 0.0`, same `kept_gross`, `n_kept`, excluded and dropped lists |
| `EFB_HEDGE_MODE=cap_then_rehedge`, in-process | `origin/main` | `nov11-into-main` | 4 | **PASS** — identical, weight for weight |
| `EFB_DESIGN_RETURNS=clean`, in-process | `origin/nov11` | `nov11-into-main` | 4 | **PASS** — the merged branch's flag-on book is nov11's own, exactly |

A1's substitute proof is therefore no longer needed: with the flag unset the branch *is*
`origin/main`, weight for weight, on every close including tonight's. The books' own
numbers, all four closes: kept 171/176/169/170 names at gross 1.0, predicted vol
2.76%/2.65%/2.75%/3.01%, worst single-name variance share 10.99%/8.84%/11.98%/12.25%,
traded notional $449,701/$485,040/$441,589/$489,148 — the last of which is 48.9% of NAV,
in the same family as the live record's 44%.

## A-3. Design `raw` versus `clean`, per close

`EFB_DESIGN_RETURNS` unset (`raw`, origin/main's panel) against `clean` (nov11's), same
merged branch, same trees, same flags otherwise. Owner decision later; **the flag stays
unset everywhere.**

| close | n_kept raw | n_kept clean | names that differ | pred vol raw | pred vol clean | worst share raw | worst share clean | traded notional raw | traded notional clean |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-13 | 171 | 186 | 204 | 2.7599% | 2.6459% | 10.99% | 11.30% | $449,701 | $393,316 |
| 2026-10-14 | 176 | 177 | 198 | 2.6498% | 2.6312% | 8.84% | 10.30% | $485,040 | $479,920 |
| 2026-10-15 | 169 | 177 | 194 | 2.7479% | 3.3348% | 11.98% | **35.69%** | $441,589 | $440,010 |
| 2026-10-16 | 170 | 180 | 195 | 3.0109% | 2.8720% | 12.25% | 11.74% | $489,148 | $428,987 |

Read it as: the clean panel changes about 200 of ~500 names every day, so it is not a
tweak; the predicted volatility is a wash (better two days, worse two); and on
2026-10-15 the clean book's worst single-name share is **35.69% against 11.98%**, three
times the raw book's. A concentration that large on the traded book is the argument for
leaving the flag unset until the owner has priced it.

## A-4. Tonight's run, and the gate

**Tonight's run (the 2026-10-16 close) is clean**, read-only from `efb.run_status`:

```
2026-10-16 live_daily  status=ok  orders=181  gross_notional=486,633.14
```

`ok` with a priced book, so the merge condition is met. Two nearby rows are worth
knowing rather than fixing here: 2026-10-14's evening ran `error` (a `KeyError` on
`dividend`/`split_factor`, so that close has no booked run and no stored positions), and
2026-10-13 and -15 are both `ok`.

### A-4b. The gate on the merged tree

### PART B: five of six built, tested and pushed

One branch and one commit set per item, cut from `a952213` (the branch head before the
merge; the merge commit's tree is that tree, so a B branch cut from either is the same
content). Nothing in PART B is merged to `main` yet: the PART B window is 23:00 UTC
Monday 2026-10-19 to 20:30 UTC Tuesday 2026-10-20 and needs Monday's run clean.

| item | branch | head | what it does | tests | status |
|---|---|---|---|---|---|
| B1 | `nov11-b1-reconcile-once` | `9340d1b` | reconcile-once reads the morning's completion record (its filed `run_status` row or the published block), not `efb.fills` alone | 3 new, and the existing repeat test rewritten; the subset's failures are exactly the base's 23 | **pushed** |
| B2 | `nov11-b2-traded-story` | `fba2619` | a traded second start carries the failed first attempt's detail instead of overwriting it | 2 new; subset 23 failed / 75 passed against the base's 23 / 73, the same failing set | **pushed** |
| B3 | - | - | not started; see below | - | **not built** |
| B4 | `nov11-b4-attribution-variance` | `f4459ee` | the pre-hedge reconstruction squares `idio_vol` before sizing | 2 new; `tests/test_e12_attribution_job.py` 15 passed | **pushed** |
| B5 | `nov11-b5-catchup-pill` | `25c44de` | a catch-up that priced a book reads green `PROPOSAL RUN: OK (caught up N sessions)` | 2 new; `tsc -b` clean, `App.test.tsx` + `status.test.tsx` green | **pushed**, deploy waits for its merge |
| B6 | `nov11-b6-notnull-audit` | `5664c60` | the NOT NULL NaN audit run against the live database | read-only; 28 columns, 28 clean, 0 NaN, 0 null | **pushed** |

**B4's evidence, every stored attribution day** (computed locally and read-only on the
live-era tree, nothing written). `pre-hedge` is the reconstructed sized book's predicted
volatility and `effect` is that minus the held book's; the held book's own number does not
move, because the fix is upstream of the book that traded:

| close | pre-hedge before | pre-hedge after | hedged (both) | effect before | effect after |
|---|---|---|---|---|---|
| 2026-09-29 | 11.98% | 9.36% | 2.87% | 9.11pp | 6.49pp |
| 2026-09-30 | 11.75% | 8.93% | 2.76% | 8.99pp | 6.17pp |
| 2026-10-01 | 11.55% | 9.01% | 2.68% | 8.87pp | 6.34pp |
| 2026-10-02 | 10.77% | 8.46% | 2.48% | 8.29pp | 5.98pp |
| 2026-10-05 | 10.26% | 7.85% | 2.55% | 7.71pp | 5.30pp |
| 2026-10-06 | 9.87% | 7.62% | 2.51% | 7.36pp | 5.12pp |
| 2026-10-08 | 9.77% | 7.48% | 2.66% | 7.11pp | 4.82pp |
| 2026-10-09 | 9.34% | 7.30% | 2.77% | 6.57pp | 4.53pp |
| 2026-10-12 | 10.53% | 8.04% | 2.64% | 7.89pp | 5.41pp |
| 2026-10-13 | 9.47% | 7.43% | 2.76% | 6.71pp | 4.67pp |
| 2026-10-15 | 10.14% | 7.86% | 2.75% | 7.40pp | 5.11pp |
| 2026-10-16 | 10.81% | 8.13% | 3.01% | 7.79pp | 5.12pp |

Three stored days (2026-09-28, -10-07, -10-14) have no position rows to rebuild from -
the evenings that did not book - so their stored `pre_hedge_vol` is what it always was.
The four-term identity still closes: recomputed from each stored row,
`pnl_total - (pnl_factor + pnl_idio + pnl_cost)` is under 1e-16 on 14 of the 15 days, and
2026-09-29's 6.08e-05 is the case that row already records (`n_computed_specific` 2,
`n_missing_return` 1, missing weight 0.0057). **No stored row was rewritten.** The days
the owner may want recomputed are the twelve above.

**B3 is not built, and it should not be built the way the others were.** The precheck's
drop sits right after the full-book sizing and before the hedge
(`live/evening_job.py:1808-1830`, `drop_not_shortable` at `:126`), which is exactly the
brief's point: the hedge flips signs, so a name the sizing put short can trade long.
Checking the *final* traded weights means lifting the block from that drop to the
quantized kept book (roughly `:1808` to `:1900`) into a function that takes the surviving
names and returns the final book, calling it in a loop of at most three rounds and
recording the names each round. That is a real refactor of the live construction, and a
flag-off identity proof cannot see it: the flag has to be on in the test to reach the
code. It is left unstarted rather than half-landed - with the flag off everywhere, a
half-built loop would sit in the file with nothing to notice it.

## PLAN C: the cadence study, in its own worktree

`research-cadence` is pushed, and `docs/research/cadence_study.md` carries the window,
the table and the recommendation. The short version: the live construction cannot be
built before its universe seam, so the window is stated and the universe is frozen at the
oldest local archive, with the substitution's size measured against the native builds.

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
are in main's red list are **deselected** on the merged branch, not fixed by it: that
file is `pytest.mark.requires_live_tree` on nov11 (main's copy carries only the
timeout marker), because it needs a run root the loop has extended one session at a
time and cannot run here at all — `EFB_RUN_ROOT=<run root> python -m pytest
tests/test_hedge_vintage.py` is the deliberate check, and the file's own docstring says
which two of its eight are green only on a tree whose published rows came from the
panel this branch fits on. So the design change is *consistent* with that file's
subject; it is not what removes those ids from the list.

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
- The merge **clears 45 of main's 60**. Eleven of those are *deselections* rather
  than fixes — nov11 marks `tests/test_hedge_vintage.py` (5 ids) and other
  live-tree-only files `requires_live_tree`, which the gate expression excludes (37
  deselected on main, 49 on the merged tree) — and the rest are nov11 fixing main's
  vintage failures: the web fixtures, the research artifacts and memos, the sector map
  and the two `test_web_sector_map` ids.
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
