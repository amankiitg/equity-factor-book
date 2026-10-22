# Handoff, 2026-10-22 01:30 UTC

Paused by instruction. **Two branches are not merged because their gate has not passed.**
Nothing is half-written: the database writes below are applied and verified, the page is
deployed and verified, and every branch is pushed.

Deadline for the rest: **Thursday 2026-10-22 21:30 UTC**, and never inside the run
windows (15:25-15:45 and 22:25-23:00 UTC).

## What is on `main` right now

`main` = **`606ba5d`** — the `page-legends` merge (`--no-ff`), gate run on the merge
commit: **14 failed, 1585 passed**, the 14 being exactly `docs/known_test_failures.md`.

Every new flag is **off** on `main`: `cadence-flag` is not merged, so `EFB_CADENCE`,
`EFB_CADENCE_ANCHOR`, `EFB_DRIFT_GUARD` and `EFB_HEDGE_MODE` do not exist in the
construction at all. No Render variable was set. The identity proof for the branch that
carries them is 0.0 (below), but that is a branch proof, not a statement about `main`.

## Part 1 — the attribution chart and legends: DONE, merged, deployed

1. **Read (read-only)**: `efb.attribution` holds 18 rows, 2026-09-28..2026-10-21. The
   15 rows recomputed on 2026-10-20 still hold the corrected values, to the digit, in
   `docs/owner_fixes/attribution_recompute.md`. 2026-09-28 was still on the old formula
   (18.6918%).
2. **Where the chart's series comes from**: the store -> the evening -> `live/snapshot.py::_risk_path`
   -> `latest.json` in R2 -> the Worker -> the page. **Tonight's document (2026-10-21,
   uploaded after the 22:56:35 attribution write) carries the corrected values for
   09-29..10-19 and the stale 18.69% for 09-28.** I could not read R2 to confirm: this
   machine holds `EFB_SEED_R2_*` and not the snapshot bucket's `EFB_R2_*`. The next
   evening rebuilds the document and picks up the 09-28 write.
3. **The drop explained**: before the fix the series ran 18.69 -> 15.61 -> 9.36; the
   first two points were the old formula. After it, 15.61 -> 15.61 -> 9.36. The
   remaining 6.2-point step is real and is the **establishment book**: on 09-28 and
   09-29 the book held 150 names with `hedged_vol` 16.47% (the hedge not yet complete),
   and on 09-30 it was 175 names at 2.87%. It is a one-time transition at the start of
   the live period, not a current risk level. That is now a dated note on the page.
4. **Series made consistent**: 2026-09-28 *was* reconstructible (it rebuilds from the
   09-29 book), so it took the same narrow recompute — **18.6918% -> 15.6087%**,
   `hedged_vol` untouched at 16.4721%, identity -3.11e-17, no other column. Backup
   `backups/attribution_0928_before.json`; rollback:
   `python scripts/restore_attribution.py --backup docs/owner_fixes/backups/attribution_0928_before.json --apply`.
5. **Legends, notes, page**: every one of the four charts (`cumulative`, `daily`,
   `risk-path`, `hedge-vol`) now carries a caption with its unit (bp of NAV / % of
   predicted variance / % annualized) and a legend naming every series, with area
   series drawn as swatches. The snapshot carries `attribution.notes` (code, not the
   store: `live.snapshot.ATTRIBUTION_NOTES`), drawn as numbered markers with their
   text, seeded with 09-28, 10-20 and 10-21.

   **Verified at 390px** against the built page and a fixture, in a real browser:
   `scrollWidth == clientWidth == 390`, all four charts 340px wide with their legends
   and units, three notes listed, a marker only on an in-window date, and the only
   elements past the viewport edge are inside the attribution table's own
   `overflow-x-auto`.

   **Worker: `a4082203-e469-48b1-8001-641f6b63ddc0` -> `dd3110ad-7ae6-4715-9540-4288cd3f1f74`.**
   Rollback: `cd web && npx wrangler rollback a4082203-e469-48b1-8001-641f6b63ddc0`.

## Part 2a — the actual-fills recompute: DONE, applied and verified

`--since 2026-10-09`, full row, eight rows (10-09, 10-12, 10-13, 10-14, 10-15, 10-16,
10-19, 10-20). `pnl_cost`, `pnl_total`, `realized_cost_bps`, `realized_vol`,
`vol_ratio` and `n_filled` moved; `pre_hedge_vol` was restated identically on every
row; the identity closes everywhere. The full before/after table is in
`docs/owner_fixes/attribution_recompute.md`.

2026-10-13: `pnl_total` +0.00135 -> +0.00033, `pnl_cost` -0.00143 -> -0.00244, which is
the +13 bp day becoming a +3 bp day — the number the last handoff predicted.

Backup `backups/attribution_fills_before.json` (8 rows). Rollback:
`python scripts/restore_attribution.py --backup docs/owner_fixes/backups/attribution_fills_before.json --apply`.
Verified with a NaN-aware diff of every stored column against both backups: the
expected columns and `written_at`, nothing else; a re-run reports `other cols = 0`.

## Part 2b — the forward fix: WRITTEN, NOT MERGED (gate not run)

Branch **`attribution-refinalize`**, head **`de27f05`**, pushed, **not merged**.

`live.attribution_job.refinalize(day, root)` re-attributes one close against the fills
it now has and rewrites the row; `scripts/reconcile_fills.py` calls it right after the
fills are stored, which is the first run that can price the day. Idempotent three ways:
no fills means nothing to price, a matching `n_filled` means the row is left as stored,
and the row is written only when the cost columns actually move. The corrected
pre-hedge volatility is restated, never altered — `REFINALIZED` deliberately excludes
it.

`tests/test_attribution_refinalize.py` (7 tests): the three the brief named, plus
dry-run, no-row and "the cost is the fills' own". They pass, as do
`test_e12_attribution_job.py` and `test_e12_attribution.py` (28 together).

**What is missing: the full gate.** Run
`.venv/bin/python -m pytest tests/ -q -m "not slow and not requires_live_tree and not merge_guard"`
in `../efb-attr-fin`, expect the 14 known failures, then merge.

## Part 3 — the guard and the reversal addendum: WRITTEN, NOT MERGED (gate failed, fix untested)

Branch **`cadence-flag`**, head **`37d010e`**, pushed, **not merged**.

**The gate for `160ed2d` FAILED: 39 failures, not 14.** 25 were new, all in
`test_e11_positions.py`, `test_e11_staleness.py` and `test_e11_notify.py`, and all one
cause: `previous_close_reversals(as_of)` read a name the scope had not bound yet
(`as_of` is set from the manifest further down the run). `37d010e` changes it to
`str(gate["target_close"])`, and those three files now pass **100/100**. **The full
suite has not been re-run since that fix.** That is the one gate between this branch and
a merge.

What is on the branch:

- **`EFB_DRIFT_GUARD`** (a fraction; unset = off): on a hold day, measure the held
  book's worst absolute factor exposure against the design it will be held with, and
  past the threshold take the minimum-norm correction, under the active hedge mode (so
  `cap_then_rehedge` runs its cap rounds as G5H did). Every name it moves is forced.
  `manifest["drift_guard"]` and `manifest["cadence"]["drift_guard"]` record
  `fired / threshold / exposure_before / exposure_after / turnover / legs[]`.
- **The pill**: `hold day, guard re-hedged 6.7% -> 0.0%`, still green.
- **The reversal addendum, CONFIRMED and fixed.** The code path was exactly as the
  addendum describes: `_target_legs` closes a sign flip and defers
  `deferred_target_notional`; on a hold day the published book is read from the
  **account** (`prior_book(holdings, ...)`), where the leg closed the name to zero, and
  the hold filter only passes closes and live sign flips — so the second leg waited for
  the next rebalance, with the book claiming a position the account did not have. The
  fix writes the deferred target back into the held book on a hold day
  (`_with_deferred_targets`), records it as `manifest["reversal_targets"]`, and forces
  those names. It is gated on `calendar["day"] == HOLD`, so the daily loop is untouched.
- **Tests**: `tests/test_cadence_guard.py`, 18 tests — the reversal's two legs, the
  control (the filter still drops an unnamed leg), a completed reversal sending
  nothing, the daily path, the guard firing and not firing, the guard measuring after
  the reversal is placed, legs matching weights, and the flag's parsing.
- **Identity (flags unset)**: max abs weight difference **0.0** on 2026-10-15, 10-16,
  10-19 and 10-20 (same names, same `kept_gross`), against `main` at `606ba5d`.
- **Shadow** (`--guard 0.05 --hedge cap_then_rehedge --seed-reversal ADM`): 13 closes,
  1 rebalance and 12 holds; the guard fires on 10-13 (5.31%), 10-15 (6.73%) and 10-16
  (7.91%), each to 0.00%; monthly traded $1,201,740 against the daily loop's
  $5,984,875. The seeded reversal: ADM closes long on 10-01 with
  `deferred = -0.006986`, and the **short leg lands on 10-02, a hold day — 1 order,
  $7,167**. Full table in `docs/cadence_flag.md`.

**One session short of the brief's window**: the newest cut tree is the 2026-10-20 one,
so the shadow covers 10-01..10-20 and not 10-21. The 10-21 session exists only in the
evening's run tree, which is not reachable read-only from this machine.

## Part 4 — owner-fixes into main: NOT DONE (no merge started)

Branch **`owner-fixes`**, head **`51fbcb4`**, pushed. It carries `docs/`, `scripts/`
and the backups — `docs/turn_on_monthly.md` (Part 5), the applied sections in
`docs/owner_fixes/attribution_recompute.md`, `scripts/backup_attribution_rows.py`, the
`--diff` flag on `scripts/recompute_attribution.py`, `docs/branches.md`.

Nothing outside `docs/` and `scripts/` has been touched this session on that branch; the
diff against `main` still needs the check the brief asks for (`git diff --stat
origin/main...owner-fixes`). No gate was run on it.

## Part 5 — the owner's switch: WRITTEN (`docs/turn_on_monthly.md`, on `owner-fixes`)

The four variables, the service they belong on (`efb-live-daily`, the one cron that runs
both slots — it is the only service that reads any of them), the timing, what the first
evening does, the read-only query against `efb.proposals.manifest`, and how to turn it
off. **Do not hand this to the owner before Parts 2b and 3 are merged** — the document
describes flags that are not on `main` yet.

## Surprises, and what to know

1. **A merge went in without its schema change.** I committed the page changes, then
   fixed `docs/snapshot.schema.json` and merged before committing the fix. The gate on
   the merge commit caught it
   (`test_the_builder_and_the_schema_declare_the_same_block`); I committed the schema,
   redid the merge as a single `--no-ff` commit `606ba5d`, and re-ran the full gate —
   14 known. Worth knowing because the first gate run's *count* looked right and only
   the id list showed the extra one.
2. **`make lint` is red on `main` for a file this session never touched**:
   `tests/test_live_panel_parity.py` is not black-clean at `origin/main`. I left it
   alone and reverted a reformat I had briefly applied.
3. **The identity proof is a weight proof, not a document proof.** With every flag
   unset the branch's manifests still carry a `cadence` block (k=1, "rebalance day")
   that `main` does not write, and a `drift_guard: null` key. The weights are identical
   to 0.0, which is the gate the brief named, but a run's manifest is not byte-identical.
   If the owner wants that too, it is a small gating change in `evening_job`.
4. **The guard's correction moves every name** (493 legs, minimum-norm), which is why a
   fire costs ~2-3% of NAV in turnover even though only 56-88 legs clear the $250 order
   minimum.

## Open questions for the owner

1. Run `EFB_DESIGN_RETURNS=clean` live? Unchanged from the last handoff, still open.
2. Should the manifest stay byte-identical to `main` with the flags off (no `cadence`
   block at all when `k = 1`)? See surprise 3.
3. A deferred leg that only partially fills is not re-forced on the following hold day
   (only a *deferred* reversal is). That is outside the addendum's scope and I did not
   widen it; worth deciding before the flag goes on.

## Exact next step on resume

```bash
# 1. the one gate between cadence-flag and a merge
cd /Users/amankesarwani/PycharmProjects/efb-cadence-flag && git pull --ff-only
../equity-factor-book/.venv/bin/python -m pytest tests/ -q \
  -m "not slow and not requires_live_tree and not merge_guard"
#    expect 14 failed (docs/known_test_failures.md), 1598+ passed;
#    then a fresh worktree off origin/main, --no-ff merge, gate on the merge, push.

# 2. the same for attribution-refinalize (de27f05), in ../efb-attr-fin.

# 3. owner-fixes (51fbcb4): check `git diff --stat origin/main...owner-fixes` touches
#    only docs/ and scripts/, then merge --no-ff and push.

# 4. once 2 and 3 are on main, redeploy the page once more (the hold-day pill) and
#    record the version; then hand the owner docs/turn_on_monthly.md.
```

Data symlinks: `../efb-attr-fin`, `../efb-cadence-flag`, `../efb-page-legends` and
`../efb-merge-1` point `data/` at `/tmp/efb-pl-data` (a writable copy of the repo's
data). Remove the symlink and `git checkout -- data` before committing in any of them —
that is why `git status` shows deleted `data/` files there.
