# Backport runbook, branch `backport`

Research-only branch. It changes the research panel, the criteria and the tests;
it changes one thing on the live path (`efb/race.py`) and must not merge until
**2026-11-11**, when it lands together with a regenerated live seed. Until then
`make test` is the gate, and the two merge-time checks below are the ones no
default run can perform.

## 1. What this branch changes that the live cron executes

`scripts/run_cron.py` routes to `scripts/reconcile_fills.py` (`:113`, `:122`) and
`scripts.run_live_daily` (`:124`). Everything the live chain reaches from there,
that this branch touches:

| file | what changed | reached from | effect on a live run |
|---|---|---|---|
| `efb/race.py::next_descriptor_design` | builds the next-session design on `panel["returns_clean"]` instead of `panel["returns"]` (`efb/race.py:279`) | `efb/eval_risk.py:411` ← `live/evening_job.py:1205` | **the only real live behavioural change.** On a live tree the two frames are equal, so it is inert until the seed is regenerated; on the regenerated seed it changes the cross-section the hedge is solved against |
| `efb/hygiene.py::clean_returns` | `corrected` exception: a cell the corporate-action rule repaired is no longer masked by its own flag | `efb/eval_risk.py:156` (`load_clean_wide`) ← `live/evening_job.py:1191`; also `efb/race.py:60,338`, `efb/models/statistical.py:106` | inert while the live frame has no `corrected` column, which it does not until the seed is regenerated |
| `efb/probes.py::load_panel` | returns a new key, `returns_clean` | `live/extend.py:378` (still reads `inputs["returns"]`; see §3) | additive; no reader changes until the merge commit |
| `efb/build.py::build_e3_artifacts` | builds E3 from `inputs["returns_clean"]`, applies the recorded spin-offs | not on the cron path | changes the **seed**, i.e. the 2026-11-11 regeneration |
| `efb/evaluate.py`, `efb/models/fundamental.py` | criteria, docstring | not imported by `live/` | none |
| `efb/corporate_actions.py`, `scripts/collect_corporate_actions.py` | new | not imported by `live/` | none |

The XS-v1 fit itself (`efb/models/statistical.py`, `efb/cov.py`) is unchanged:
the fit consumes whatever panel it is handed, so the panel its caller passes is
the whole of the question.

## 2. Tests that need more than the repository tree

Both are **deselected, never skipped**: a default run reports them as
`N deselected`, and skipping them quietly is how the September hedge-vintage
pairs stopped existing without any test noticing.

| file | marker | what it needs | default run |
|---|---|---|---|
| `tests/test_hedge_vintage.py` | `requires_live_tree` | a run root the live loop has extended one session at a time, so that a descriptor row exists for the session after a month end | deselected |
| `tests/test_live_panel_parity.py::test_the_live_fit_and_the_next_design_read_one_panel` | `merge_guard` | the merge commit, not a tree (§3) | deselected |

    make test                                   # green today, 2 groups deselected
    make test-all                               # everything else, slow included
    EFB_RUN_ROOT=<run root> make test-live-tree # the vintage tests
    .venv/bin/python -m pytest tests/test_live_panel_parity.py -m merge_guard

`EFB_RUN_ROOT` is the same variable `live/runroot.py` materialises a run into
(`RUN_ROOT_ENV`, `live/runroot.py:31`). A tree rebuilt by `make rebuild-e3` is
**not** live-shaped: the build publishes descriptors at month ends plus the final
session, so it has no row for the session after a month end and cannot exercise
the vintage property at all.

## 3. Merge checklist, 2026-11-11

Ordered. Each step names the check that has to pass before the next one runs.
Steps 1 to 4 are the ones no default run performs.

| # | step | the command | the check |
|---|---|---|---|
| 1 | Read one panel | edit `live/extend.py:379`, `inputs["returns"]` to `inputs["returns_clean"]` | `make test-merge-guard` turns green (it is red before the edit) |
| 2 | Re-declare the champion if E3 was rebuilt | `python -c "from efb import eval_risk; eval_risk.apply_champion()"` | `data/models/registry.json` names XS-v1 again |
| 3 | Regenerate the live seed from this branch's artifacts | `.venv/bin/python -m scripts.push_seed --dry-run`, then the same without `--dry-run` | the manifest lists this branch's artifacts and no read is refused |
| 4 | Run the vintage tests on the regenerated seed | `EFB_RUN_ROOT=<run root> make test-live-tree` | the two the seed exists to fix pass, see §6 |
| 5 | Regenerate the web fixtures | `scripts/make_web_fixtures.py` | `make web-test` green |
| 6 | Run the full suite on the merged commit, with the seed in place | `make test-all` | green, no deselected group |
| 7 | State the end date on any further rebuild | `make rebuild END=<last session before the merge>` | `data/VERSION.json` records that session |
| 8 | Re-record the frozen block baseline if the seed moved a pre-cutoff row | `.venv/bin/python -c "from live import extend; print(extend.incremental_integrity())"` | `tests/test_e11_extend.py` green |
| 9 | Clear the 11 known reds the refresh exists to fix | `.venv/bin/python -m pytest tests/test_e11_bridge.py tests/test_e11_preflight.py tests/test_e11_notify.py tests/test_e11_symbol_resolution.py tests/test_run_live_daily.py tests/test_week1_fills_cron.py tests/test_e11_snapshot.py tests/test_e11_execution.py tests/test_week1_run_cron.py tests/test_e11_fills.py tests/test_e11_web_fixtures.py -q` | 0 failures. Any red still failing is fixed or recorded in note 9 below, never skipped and never `xfail` |

1. **Read one panel.** At merge, `live/extend.py` must read `returns_clean` as
   well, in the same commit, so the live model fit and `next_descriptor_design`
   use the same panel. The change is `live/extend.py:379`,
   `returns_frame = inputs["returns"]` to `inputs["returns_clean"]`. Run the
   guard before and after so the result is attributable to the edit:
   `.venv/bin/python -m pytest tests/test_live_panel_parity.py -m merge_guard`
2. **Re-declare the champion after any E3 rebuild.** `efb.build.rebuild_e3`
   registers XS-v1 with `champion=False`, and only the E5 step
   (`efb.eval_risk.apply_champion`, `efb/build.py:1981`) sets the flag, so
   `make rebuild-e3` on the real tree leaves the registry with no champion.
   Measured on 2026-10-03: rebuilding E3 on `data/` cleared it, three tests
   failed (`test_champion`, `test_build_e3::test_registry_entry_is_eligible_but_not_champion`,
   `test_dashboard_d3`), and
   `python -c "from efb import eval_risk; eval_risk.apply_champion()"` restored
   XS-v1 as the winner (mean |bias-1| 0.060664 against XS-v2 at 0.067194, the
   same winner as before the rebuild). Run that after the seed regeneration.
   Since the item 1 fix, a rebuild no longer also drops the `live` block, so the
   20-share floor survives an E3 rebuild; the champion flag still does not.
3. **Regenerate the live seed** from this branch's research artifacts, so the
   published descriptors and the repaired returns come from the same panel.
   `--dry-run` measures and prints without uploading, which is the rehearsal.
4. **Run the hedge-vintage tests on the regenerated seed**, materialised as a run
   root: `EFB_RUN_ROOT=<run root> make test-live-tree`, or directly
   `EFB_RUN_ROOT=<run root> python -m pytest tests/test_hedge_vintage.py`. Two of
   the eight assert that the row built at the close *is* the published row; on the
   regenerated seed they pass, and on a tree whose published rows were built from
   the raw panel they fail by construction.
5. **Regenerate the web fixtures** after the seed lands
   (`scripts/make_web_fixtures.py`) and re-run `make test-all` once, on the
   merged commit, with the seed in place.
6. **Re-score E6 with the month-end finding folded in** (item 3 of the back-port):
   see the entry in `docs/hygiene_ledger.md` dated 2026-10-03.
7. **Regenerate with the end date stated.** Every rebuild is pinned (§5). At the
   merge, state the session the seed means to reach,
   `make rebuild END=<last session before the merge>`, rather than taking the
   default, which deliberately reproduces the stored panel.
8. **Re-record the frozen-block baseline.** `tests/test_e11_extend.py` pins the
   content hash of the descriptor, factor-return and specific-return rows dated
   on or before 2026-09-03, and those recorded hashes were taken from a live
   tree. A research rebuild cannot satisfy them: the 2026-10-03 propagation pass
   measured `049fe6ea`, `a43d66ce` and `d65a67f1` where the file records
   `8f93968f`, `42a31d64` and `176dc4b3`, so the test was red on the branch
   before and after that pass. The pin belongs to the seed generation event: run
   `extend.incremental_integrity()` on the regenerated seed and copy its three
   values into `BASELINE`.
9. **Clear the 11 known reds.** Measured on `main` on 2026-10-06: eleven failures,
   all of them fixture or artifact vintage, none of them about behaviour. On this
   branch as it stands the same three files pass (101 tests), because the branch's
   fixture generator predates the writer changes that moved the page's inputs; the
   merged tree takes `main`'s, so the reds come back with the merge and are cleared
   by step 5. They are not this branch's own reds (§6): they are the live-page and
   live-loop suite's. Each line says what has to move.

   | # | test | cause | what clears it |
   |---|---|---|---|
   | 1-7 | `tests/test_e11_web_fixtures.py::test_every_fixture_is_what_the_writer_produces_now[snapshot_ok.json]`, `[snapshot_stale_stopped.json]`, `[snapshot_error.json]`, `[snapshot_expired.json]`, `[snapshot_catch_up.json]`, `[snapshot_market_closed.json]`, `[snapshot_establishment.json]` | stale fixtures: the committed documents are from the 2026-09-21 vintage and the writers no longer produce those bytes. Measured 2026-10-06, the regenerated `snapshot_ok.json` carries `book_as_of` 2026-10-02, and `breadth`, `hedge`, `exposures_before/after_hedge`, `expected_cost_bps` and `expected_cost_split` all move with the newer book | step 5: `scripts/make_web_fixtures.py` on the refreshed seed, committed with the fixtures it produces |
   | 8 | `tests/test_e11_web_fixtures.py::test_the_ok_snapshot_carries_the_book_and_both_exposure_vectors` | asserts the document's close equals `fixtures.CLOSE` (`2026-09-21`); the regenerated book is dated the newer close | re-pin `CLOSE`/`NEXT_CLOSE`/`CATCH_UP_CLOSE`/`STOPPED_CLOSE`/`REMOVED_CLOSE` in `scripts/make_web_fixtures.py` to the refreshed vintage, or derive them from the generated document instead of typing them |
   | 9 | `tests/test_e11_web_fixtures.py::test_the_stopped_snapshot_shows_the_last_book_under_its_own_close` | the same close pin, for the stopped variant | as row 8 |
   | 10 | `tests/test_e11_snapshot.py::test_the_hedge_drives_the_exposures_to_zero` | artifact vintage: it pins `manifest["n_eff_kept"] == 131.9175` and the manifest built from the tree's artifacts reports `140.887` | re-pin from the refreshed manifest, or read the figure off the artifact the manifest came from rather than typing it |
   | 11 | `tests/test_e11_notify.py::test_the_appended_sessions_are_measured_from_the_calendar` | the tree's price appendix has advanced nine sessions past the four dates the test types (`2026-09-16` .. `2026-09-21`), so the measured list is longer and correct | derive the expected window from the tree's own appendix - the same call the assertion is testing - instead of typing the dates |

   The exit condition is the whole of step 9: after the refresh this suite has
   **0 failures**, and a test still failing is either fixed or written down in
   this note with its reason. None of them may be skipped, deselected or marked
   `xfail` - a red that is silenced is how the September hedge-vintage pairs
   stopped existing without anyone noticing (§2).

   Until the refresh, every report on this work splits its failures into two
   lists: **known** (the 11 above) and **new**. A new failure is investigated on
   its own and is never counted among the known ones, so a real regression cannot
   hide in the eleven.

## 4. Rollback

Before 2026-11-11 the branch is parked and a rollback is `git checkout main`:
nothing on the live path has moved. After the merge, the merge is one commit and
the seed is one measured manifest, so both sides are reversible. In order:

1. **Stop the cron first.** `scripts/run_cron.py` is the only writer, and a run
   started against a half-restored tree is the failure mode, not a stale tree.
2. **Restore the research tree.** `git revert -m 1 <merge commit>` on `main`,
   which also returns `live/extend.py` to `inputs["returns"]`. `main` is what the
   evening reads.
3. **Restore the seed.** Run `scripts.push_seed` from a checkout of the pre-merge
   `main`, which re-uploads the pre-merge artifacts and writes the pre-merge
   manifest. Until that lands, unset `EFB_SEED_R2_*` so the run refuses at the
   seed check rather than sizing from a tree it cannot describe; `live/seed.py`
   refuses rather than starting.
4. **Re-declare the champion** on the restored tree
   (`eval_risk.apply_champion()`) and run `make test`.

What a rollback does not undo:

- **The store is append-only.** A proposal written while the merge was live stays
  on the record, and the next evening sizes from the restored seed against the
  real account, so the two are reconciled by the ordinary morning job rather than
  by editing rows. The rollback records the incident; it does not erase the
  evening.
- **A published snapshot or evidence directory** is a separate artifact with its
  own history (`evidence/MANIFEST.json`). Re-uploading an older one is a
  deliberate act, not part of the revert.

## 5. The panel pin, every rebuild takes an end date

`make rebuild-e1` … `make rebuild-e10` all take `END=YYYY-MM-DD`, and the entry
point behind them takes `--end`. Left unset the pin is the **stored panel's own last
session** (`efb.build.pinned_panel_end`, read from the date index of
`data/processed/returns.parquet`), not the clock, so a rebuild that re-reads sources
cannot extend the panel by accident. A first build, with no panel on disk, still
falls back to today, because there is nothing to freeze yet.

**`END=2026-10-02` is the date every rebuild in this pass used**: the stored panel's
last session (4,213 sessions from 2010-01-04, `data/processed/returns.parquet`),
which is the panel every re-scored record here was measured on. State that date when
re-running any of these rebuilds.

Two rules come with it:

- a leg that **reads** the panel (E2 … E10) refuses a pin earlier than the panel's
owned end, because it cannot un-read rows it has already been handed;
- `rebuild-e1` is the exception: it *makes* the panel, so an earlier pin re-cuts it,
  and an `END` past the stored end is how a run says it means to extend the panel.

The price and factor artifacts are clipped at the pin
(`efb.prices.build_prices_artifact`, `efb.factors.build_factors_artifact`) and the
membership grid is built to it (`efb.universe.build_membership`). Those are the two
ways the panel used to grow on an ordinary `make rebuild`: a price cache refreshed by
a live run, and a membership grid that ran to today. `tests/test_panel_freeze.py`
holds both directions, together with the control that the newer source rows really
are in the fixture.

## 6. The 2026-10-03 dry run, and what it settled

Everything here was measured on the branch, against a materialised run root, a
read-only Alpaca account and a read-only store. Nothing was uploaded, written to
the store or sent to a broker.

**1. The parity guard responds to the edit.** In a worktree of `e87ef1d` with
`live/extend.py:379` reading `returns_clean`, and the rest of the tree untouched,
`pytest tests/test_live_panel_parity.py -m merge_guard` is 1 passed, 2
deselected. The red in §2 is therefore the branch's statement about the two
readers, not an artefact of the test.

**2. The run root.** `data/` was copied to `/tmp/efb-bp/runroot/data`, the five
XS-v1 cross-sectional artifacts were frozen at the last month end (2026-08-31,
descriptors 667,660 to 660,632 rows) and the model was extended forward to
2026-10-02, so the tree carries one published descriptor row per session, which
the repository tree cannot.

The extension was one pass, not the live loop's one session at a time, and the
reason is cost: a pass truncated at its own close refits the whole panel, measured
at 879 s, so the 23 truncated passes the window needs are about five and a half
hours, against 870 s for the single pass that publishes all 23 sessions at once.
The equivalence is a property of the artifacts rather than an assumption: every
descriptor on a row is a shifted quantity standardised over the names priced on
that row's own date, so no session after the close enters it, and the vintage
tests are the check, because they rebuild each ordinary session's row from a
panel truncated at the close and require it to agree with the published row to
1e-10. They do.

**3. The hedge-vintage tests on the branch's own panel.** Six of the eight pass,
including the two the regenerated seed exists to fix:

- `test_the_row_built_at_the_close_is_the_row_the_model_publishes`
- `test_the_book_carries_no_exposure_under_the_published_row`

On the live tree `/tmp/efb-repair/data` those same two fail (the 2026-09-17 to
2026-09-18 pair leaves 1.022e-03 of exposure against a 1e-10 bound), which is the
by-construction failure §3 step 4 removes. Two different tests fail instead, and
both are facts about the panel rather than about the change:

- `test_a_sparse_replay_keeps_the_row_dated_the_close` hardcodes the 2026-09-01
  close and expects the artifact to publish nothing for 2026-09-02. That is the
  live tree's shape: its daily tail starts 2026-09-03, so it carries 209
  published dates. A research rebuild cannot reproduce it, because
  `extend_model` appends every session after the last published row, so the
  branch's root starts its tail on 2026-09-01 and carries 211. The stale
  fallback the test asserts is real and is exercised by
  `test_the_builder_declines_rather_than_hedging_on_a_short_window`; what is
  unreachable on this tree is the month-end gap that this particular hardcoded
  date stands for.
- `test_the_session_before_a_holiday_is_bounded_and_not_exact` asserts that at
  least one name is in the 2026-09-08 cross-section but not priced at the
  2026-09-04 close. On the corrected panel the 2026-09-04 close prices 502 names
  and the built row equals the published row to 5.4e-14, so no name enters and
  the assertion is not reachable. Read across every consecutive pair in
  2026-09-01 to 2026-10-02, the live tree's priced set moves three times (32
  names leave from 2026-09-03 to 2026-09-04, 325 leave and 2 enter from 2026-09-21
  to 2026-09-22, VYLR enters from 2026-09-30 to 2026-10-01) and the branch's root
  moves at none. The docstring's "the only pair in the published daily window
  whose priced set moves" is a property of the live tree's ragged price
  coverage; the corrected panel is dense enough that Labor Day no longer moves
  it. Re-pointing the case needs a pair the corrected panel moves, and this pass
  found none in the window, so the case is left red and named here rather than
  silently re-pointed.

**4. The book the merge would trade.** Built with the live path at the account's
own equity of 996,885.53 USD, against the proposal the store holds for
2026-10-02:

| | stored (tonight's live book) | built (this branch, same NAV) |
|---|---|---|
| n_kept | 204 | 199 |
| n_eff_kept | 152.603227 | 150.975015 |
| gross | 1.000000 | 1.000000 |
| kept gross before renormalisation | | 0.526437 |
| construction / floor | | share_only / drop_then_admit |

173 names are in both, 31 only in the stored book and 26 only in the built one,
and the first evening's turnover is 332,904 USD, 33.39% of NAV. The number that
matters is `n_kept`: 199 against 204, not the 502 the disabled 20-share floor
produced before item 1. The floor, the construction and the gross are unchanged
by the merge; what moves is the cross-section the corrected panel ranks.

**5. Not done here.** No seed was regenerated (`scripts.push_seed --dry-run`
needs the R2 credentials this pass deliberately does not use), so §3 steps 3 and
5 remain unmeasured, and §3 step 8's three hashes are measured but not yet
written into `tests/test_e11_extend.py`: on the dry run's tree they are
`bc7bba30da9b6a9955ecef20fa24cb6096f7e7686d877c7d3ae40e2375113ef5`,
`a43d66ce62e08eca28adf44b74867ab9a0718d1427973fa43362140ce4913be8` and
`d65a67f15f0bb844de7e3f6b7d49f9948d78d5a3aedd37f899550476e841f7dc` for the
descriptor, factor-return and specific-return blocks dated on or before
2026-09-03, against the `8f93968f`, `42a31d64` and `176dc4b3` the file records.
Those three are seed-generation values and are re-recorded on the day the seed
moves, not before.

Nothing in §1 was executed against a live tree by this branch: the effects in its
last column are read off the call sites, and the dry run above exercises the
research side of them plus the one live file the merge changes.

**6. The three reds that belong to the seed regeneration, not to this branch.**
They are left red deliberately, and none of them is skipped, deselected or
xfailed on the branch:

- `tests/test_hedge_vintage.py::test_a_sparse_replay_keeps_the_row_dated_the_close`
  and `::test_the_session_before_a_holiday_is_bounded_and_not_exact`. Both are
  the same family as §3 step 4: the first hardcodes a close whose next session a
  live tree has not published and a research tree cannot avoid publishing, and
  the second asserts that the priced set moves across Labor Day, which it does
  on the vendor's ragged live coverage and does not on the corrected panel. They
  are read on the regenerated seed, where the tree the live loop has extended is
  the artifact under test.
- `tests/test_e11_extend.py::test_pre_cutoff_blocks_are_byte_identical`. The
  baseline it pins was taken from a live tree, so a research rebuild cannot
  satisfy it; it is re-recorded by `extend.incremental_integrity()` on the day
  the seed moves, which is §3 step 8.

Two further reds are not the branch's either and are recorded in
`docs/hygiene_ledger.md`: the APH split case in `tests/test_e11_corporate_actions.py`,
whose premise is that the vendor's raw closes halve across the split and whose
cache now serves split-adjusted closes, and the beta-magnitude inequality in
`tests/test_construction_table.py`, which the corrected panel breaks on its
sparsest row.
