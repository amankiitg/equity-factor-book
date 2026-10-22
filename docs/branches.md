# Branches, worktrees and scratch directories

State after the 2026-10-22 merges. One branch is live besides `main`; everything else
is either merged into `main` (so its commits are in history) or preserved as an
`archive/<branch>` tag on `origin`.

## What is left, and why

| branch | tip | worktree | why it stays |
|---|---|---|---|
| `main` | `e7969b6` | `equity-factor-book` | production; the main checkout is on it, and every branch below except the last is in its history |
| `research-daily-design` | `94c536e` | `efb-daily-design` | the daily-panel study (`docs/research/daily_design_study.md`) the cadence flag's settings come from; not merged, because it is a study rather than a change to the loop |

## Merged on 2026-10-22

| branch | tip | merge commit | what merged |
|---|---|---|---|
| `page-legends` | `ac851db` | `606ba5d` | a legend with units on every chart, and dated notes the snapshot carries |
| `cadence-flag` | `31378ac` | `a25557b` | `EFB_CADENCE`, `EFB_DRIFT_GUARD`, `EFB_HEDGE_MODE`, the hold-day path that finishes the last rebalance's unfilled legs and deferred reversals, and the page pill. **Every flag is off on `main`**; the identity proof is that with the flags unset the manifest is byte-identical to the one `main` wrote before |
| `attribution-refinalize` | `c8efec6` | `e7969b6` | a close's cost is re-priced once its fills exist, from the evening job, which is the first run with both the fills and a tree |
| `owner-fixes` | this commit | the merge that carries this file | the owner-fix notes, the backups the database writes were proved against, and the scripts that applied and restored them |

`owner-fixes` still tracks `origin/main` from the worktree it was created in; it is
merged, so the tracking branch is now the merge point rather than a divergence. The
one upstream left broken on purpose is `research-daily-design` after
`origin/research-churn2` was deleted - set it with:

```bash
git branch -u origin/research-daily-design research-daily-design
```

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

Fifteen were removed with `git worktree remove --force` after `git status
--porcelain` showed nothing but `.venv`, `web/node_modules` or the `data-src`
symlink: `efb-b1`, `efb-b2`, `efb-b4`, `efb-b5`, `efb-b6`, `efb-cadence`,
`efb-churn`, `efb-churn2`, `efb-diag`, `efb-etf-hedge`, `efb-ic-decay`,
`efb-merge-a` (detached HEAD at `5059ecb`), `efb-nov11-merge`, `efb-page-v4`,
`efb-skyd`. Then `git worktree prune`. The four that remain are the four branches
in the first table; the main checkout is on `main`.

## Scratch directories

- Deleted: `/tmp/icdecay` (873 MB), `/tmp/cadence` (0 B) - 873 MB freed.
- Kept: `/tmp/churn` (1.8 GB, the study data copy) and `/tmp/nov11merge` (338 MB,
  the cut trees the attribution recompute used, needed if the owner approves the
  full P&L recompute).
