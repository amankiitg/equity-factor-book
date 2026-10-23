# Branches, worktrees and scratch directories

State after the 2026-10-23 cleanup. **Two branches remain, one worktree besides the main
checkout, and nine archive tags.** Everything else is merged into `main` (so its commits
are in history) or preserved as an `archive/<branch>` tag on `origin`.

## What is left, and why

State after the 2026-10-23 close-out. **Four branches, two worktrees.** Everything that
merged today is deleted, locally and on `origin`; its tip is in the table below, so it can
be restored from `main`'s history.

| branch | tip | worktree | why it stays |
|---|---|---|---|
| `main` | `a8e0546` | `equity-factor-book` | production; every branch below except the three studies and the two held ones is in its history |
| `research-daily-design` | `94c536e` | `efb-daily-design` | the daily-panel study (`docs/research/daily_design_study.md`) that `docs/turn_on_monthly.md` points at for the cadence settings; a study, not a change to the loop |
| `research-exec-timing` | `e7b2235` | - | `docs/research/exec_timing.md`: the open against 10:00 ET against the fills, on twelve days. Research only, never merged |
| `spinoff-explains-adjustment` | `44e04ca` | - | **held under the freeze**: the CTVA back-adjustment, plus an owner decision on which contract wins |
| `order-time-quotes` | `4cdbc30` | - | **held under the freeze**: records the bid, ask and mid with every order. Changes the morning path and needs `docs/migrations/e13_order_quotes.sql` applied |

`handoff` (`63c440c`) was written mid-session when the work looked like it would
overrun; it did not, and the branch is deleted. This file and
`docs/known_test_failures.md` say everything it said.

### Held under the trading freeze, with their proofs

Both are pushed and both have their own tests green; neither may merge before Monday
2026-10-26 00:00 UTC, because both change what the evening or the morning does.

| branch | proof | the exact merge |
|---|---|---|
| `spinoff-explains-adjustment` | `tests/test_e11_corporate_actions.py` 6 passed (the stop contract intact); `tests/test_week2_spinoff.py` 47 passed with the recorded-spin-off exemption, the four stale-contract ids still failing; lint scope green | decide the contract, then `git merge --no-ff spinoff-explains-adjustment` from a fresh worktree off `origin/main` and gate |
| `order-time-quotes` | 15 tests in `tests/test_order_quotes.py` and `tests/test_cost_split.py`; `test_e11_preflip_fixes.py` and `test_run_live_daily.py` unaffected (60 passed); ruff and black clean in the lint scope | apply `docs/migrations/e13_order_quotes.sql`, then merge from a fresh worktree and gate |

## The merges of 2026-10-23

| branch | tip | merge commit | what merged | gate |
|---|---|---|---|---|
| `e13-port-map` | `61c0c25` | `a633e70` | 37 rows added to the port map and the stored counts re-recorded: 146 modules, 156 mapped rows | 5 failed, 1659 passed |
| `borrow-rate-035` | `a9d63f5` | `459ea31` | `BORROW_RATE` 2% to 0.35% with its source in the code and in `docs/borrow_rate.md`, eleven web fixtures restated (the borrow term and its total, nothing else), and the E9 artifact test separated from the live constant | 5 failed, 1660 passed |
| `docs-closeout` | `029eb12` | `a8e0546` | the nov11 close-out, `docs/known_test_failures.md` at five ids, the two tree recipes, and this file | 5 failed, 1660 passed |

All three were cut from `origin/main` in a fresh worktree, merged `--no-ff`, gated on the
merge commit, pushed, and then deleted.

## The merges of 2026-10-22, all in `main`

| branch | tip | merge commit | what merged |
|---|---|---|---|
| `page-legends` | `ac851db` | `606ba5d` | a legend with units on every chart, and dated notes the snapshot carries |
| `cadence-flag` | `31378ac` | `a25557b` | `EFB_CADENCE`, `EFB_DRIFT_GUARD`, `EFB_HEDGE_MODE`, the hold-day path that finishes the last rebalance's unfilled legs and deferred reversals, and the page pill. **Every flag is off on `main`**; with the flags unset the manifest is byte-identical to the one `main` wrote before |
| `attribution-refinalize` | `c8efec6` | `e7969b6` | a close's cost is re-priced once its fills exist, from the evening job, which is the first run with both the fills and a tree |
| `owner-fixes` | `0a70387` | `2e91018` | the owner-fix notes, the backups the database writes were proved against, and the scripts that applied and restored them |
| `fix-realized-vol` | `4169a26` | `1f2d575` | the realized volatility measured over the P&L history instead of over the batch a run happened to attribute, the rows it repaired, and the missing legend on the realized-against-forecast chart |
| `cost-measurement` | `1ef9375` | `8f2af8d` | `scripts/cost_split.py`: measured cost split into the overnight move and the execution |
| `debt-lint` | `5e2f49a` | `32225cf` | seven gate ids that could never pass made to skip with their reason, the three lines lint was red on, and `docs/known_test_failures.md` cut to the seven real ones |
| `docs-research-2` | `8c915de` | `1e3afa8` | `docs/borrow_rate.md`, `docs/nov11_disposition.md`, and the switch and branch docs |
| `fix-cost-estimate` | `8ebf172` | `0c97c75` | the evening's cost estimate prices the trade rather than the book; reporting only, proven weight-identical on four closes |

Their branches were deleted, locally and on `origin`, on 2026-10-23. The tips above are
still reachable from `main`, so `git checkout -b <branch> <tip>` restores any of them.

## Archive tags

Every archived branch is also **deleted**, locally and on `origin`. The tag is the
only handle; the commits are otherwise unreachable.

| tag | sha | what it holds | doc it contains |
|---|---|---|---|
| `archive/e12` | `11dd459` | the e12 migration in the repo; superseded by `main`, which already carries the work, so the tag is a safety net only | none - nothing it adds over `main` |
| `archive/flag-cap-then-rehedge` | `9207e16` | `EFB_HEDGE_MODE=cap_then_rehedge`, and the flag-on table naming every name it moves | `docs/flag_cap_then_rehedge.md` |
| `archive/nov11-into-main` | `f498ad3` | the Monday nov11 merge report, verbatim, and where the cadence study landed | `docs/nov11_merge_report.md` |
| `archive/page-v4` | `8f66b24` | the design-review page, ten items, page only | `docs/page_v4_report.md`, `docs/page_v4_merge_note.md` |
| `archive/research-cadence` | `a3c40c1` | the cadence study: weekly, with a 25% resize band | `docs/research/cadence_study.md` (+ `.json`) |
| `archive/research-churn` | `3adad90` | the churn study: the floor is a fifth of the 87% churn | `docs/research/churn_study.md`, `cadence_study.md` (+ `.json`) |
| `archive/research-churn2` | `04c2b26` | the churn follow-up: live loadings refresh nightly, B0R, the 23% exposure | `docs/research/churn_followup.md` (+ `.json`, `churn_followup_exposure.json`) |
| `archive/research-etf-hedge` | `271e01f` | the ETF overlay measured on four hedges | `docs/research/etf_overlay_hedge.md` (+ two `.json`) |
| `archive/research-ic-decay` | `808db7c` | the live signal's IC half-life is 64 sessions | `docs/research/ic_decay.md` (+ `.json`) |

`archive/nov11-into-main` differs from `main` only in `docs/nov11_merge_report.md`
and `docs/nov11_notnull_audit.md` (main has the later edits); the four older code
branches (`e12`, `flag-cap-then-rehedge`, `page-v4`, `nov11-into-main`) are behind
`main` and their content is superseded there.

## Deleted because merged

These failed nothing - `git merge-base --is-ancestor <tip> origin/main` is true, so
every commit is in `main`'s history and `git log` still finds them:

| branch | sha | gone from |
|---|---|---|
| `nov11` | `6903912` | local + origin |
| `nov11-b1-reconcile-once` | `975736f` | local + origin |
| `nov11-b2-traded-story` | `8f7f102` | local + origin |
| `nov11-b4-attribution-variance` | `2098cc6` | local + origin |
| `nov11-b5-catchup-pill` | `ab6955e` | local + origin |
| `nov11-b6-notnull-audit` | `129315c` | local + origin |
| `diag-1014` | `c80f29a` | local + origin |
| `backport` | `4017f63` | local + origin |
| `e12-rebased` | `346dc48` | local + origin |
| `fix-skyd-spinoff` | `68f1fe7` | local + origin |
| `page-v2` | `f1ac66b` | local + origin |
| `page-v3` | `de65557` | local + origin |
| `actual-holdings` | `bc958d2` | local only |
| `fix-fills-display` | `e6698f4` | local only |
| `fix-no-risk-estimate` | `9e1cc61` | local only |
| `fix-page-trade-cost` | `3eea23c` | local only |
| `fix-symbol-resolution` | `b6bd323` | local only |
| `live-page-redesign` | `fb20ff3` | local only |
| `page-columns` | `bc14037` | local only |

There was no `nov11-b3-*` branch to park.

The nine branches merged on 2026-10-22 and deleted on 2026-10-23 are in the table at the
top of this file with their tips; they are in `main`'s history, not archived.

## Restoring anything

```bash
git fetch origin --tags
git checkout -b <branch> archive/<branch>        # archived work
git checkout -b <branch> <sha>                   # a merged branch, from the table above
```

To restore one into its own worktree:

```bash
git worktree add ../efb-<branch> -b <branch> archive/<branch>
```

## Worktrees removed

The 2026-10-23 close-out removed eleven more after `git status --porcelain` showed
nothing but `.venv`, `web/node_modules` or the `data` symlink: `efb-borrow`, `efb-ctva`,
`efb-docs2`, `efb-docs3`, `efb-e13`, `efb-exec`, `efb-handoff`, `efb-m-borrow`,
`efb-m-borrow2`, `efb-m-docs`, `efb-m-e13`, `efb-quotes`. **Two remain**: the main
checkout, on `main`, and `efb-daily-design`, holding `research-daily-design`.

The earlier 2026-10-23 cleanup removed nine with `git worktree remove --force` after
`git status --porcelain` showed nothing but `.venv`, `web/node_modules` or the `data`
symlink: `efb-attr-fin`, `efb-cadence-flag`, `efb-cost`, `efb-costmeas`, `efb-debt`,
`efb-docs2`, `efb-owner-fixes`, `efb-page-legends`, `efb-vol`. Then `git worktree
prune`. Fifteen more went in the 2026-10-21 cleanup (see `git log docs/branches.md`).
**One worktree remains besides the main checkout**: `efb-daily-design`, holding
`research-daily-design`.

## Scratch directories

Every `/tmp` tree the project built is gone as of 2026-10-23:

| path | size | what it was |
|---|---|---|
| `/tmp/efb-pl-data` | 873 MB | a copy of the live artifact tree, used as `data/` in the worktrees that ran gates |
| `/tmp/nov11merge` | 338 MB | the cut trees per close that the identity proofs and the attribution recompute read |
| `/tmp/churn` | 938 MB | the daily-design study's panel, descriptors and partial rows |

**2.1 GB freed.** All three were rebuildable: the artifact tree from the seed bucket
(`scripts/push_seed.py` pulls it, `live/seed.py` verifies every hash), the cut trees from
the store plus the seed, and the daily-design panel by re-running
`scripts/daily_design_study.py` on `research-daily-design`. Every database write they
supported is applied, verified, and backed up under `docs/owner_fixes/backups/` with a
restore script proved by dry run.

Deleted in the 2026-10-21 cleanup: `/tmp/icdecay` (873 MB) and `/tmp/cadence` (0 B).
