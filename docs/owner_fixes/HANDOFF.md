# Handoff, 2026-10-21 01:00 UTC (2026-10-20 21:00 ET)

State at pause: **both authorised database writes are applied and verified; the
research panel is built and validated and the study got through one of seven
variants.** Nothing is half-written, no process is running.

## Part 1 - attribution recompute: **applied and verified**

`--since 2026-09-29`. `--since` is inclusive (`d >= Timestamp(args.since)`), so this
includes 09-29 and excludes **only** 2026-09-28, the day with no positions of its own
that is rebuilt from 09-29's book.

### Deviation: the documented full-row upsert was rejected by the stop rule

The full-row dry run failed the brief's "`realized_vol` unchanged on every day"
expectation. Its new `other cols` guard showed why - eight rows would have been
rewritten in P&L columns:

```
close         pre-hedge before   pre-hedge after  hedged before  hedged after  identity after  other cols
2026-10-09               9.77%             7.48%          2.66%         2.66%       -5.27e-17   6 (pnl_total, pnl_cost, realized_vol…)
2026-10-13              10.53%             8.04%          2.64%         2.64%       -9.44e-17   6 (pnl_total, pnl_cost, realized_vol…)
2026-10-14               9.46%             7.43%          2.76%         2.76%        6.42e-17   1 (realized_vol)
2026-10-15               9.46%             7.43%          2.76%         2.76%       -3.20e-17   6 (pnl_total, pnl_cost, realized_vol…)
2026-10-20               7.69%             7.69%          2.96%         2.96%        1.24e-16   2 (realized_vol, vol_ratio)
   (09-29 .. 10-08 had other cols = 0)
```

Cause, from `n_filled`: those rows were written before the morning had recorded the
day's fills (`n_filled = 0`), so their `pnl_cost` is an estimate. Recomputing today
charges the actual fill cost:

```
close       pnl_total old     pnl_total new    delta   pnl_cost old    pnl_cost new  n_filled old/new
2026-10-09     -0.0043212215     -0.0041165415  2.05e-04    -0.00141982     -0.00121514       0.0 / 171
2026-10-13      0.0013485556      0.0003346462 -1.01e-03    -0.00142579     -0.00243970       0.0 / 191
2026-10-15      0.0001925681      0.0005924712  4.00e-04    -0.00142888     -0.00102898       0.0 / 176
```

2026-10-13 would move from +13 bp to +3 bp. That is a P&L rewrite, not a volatility
fix, so it was **not** applied. Per the stop rule the remaining parts continued.

### What was applied

A new narrow mode, `--only-pre-hedge-vol`, which updates that one column:

```sql
UPDATE "efb"."attribution" SET "pre_hedge_vol" = %s, "written_at" = now()
WHERE "trade_date" = %s
```

15 rows, 2026-09-29..2026-10-19, stamped **2026-10-20 23:42:08 UTC** in the rows.

| close | pre-hedge before | pre-hedge after | change (pts) |
|---|---|---|---|
| 2026-09-28 | 18.6918% | 18.6918% | 0.000 (not selected) |
| 2026-09-29 | 18.6918% | 15.6087% | -3.083 |
| 2026-09-30 | 11.9783% | 9.3603% | -2.618 |
| 2026-10-01 | 11.7508% | 8.9281% | -2.823 |
| 2026-10-02 | 11.5482% | 9.0140% | -2.534 |
| 2026-10-05 | 10.7682% | 8.4590% | -2.309 |
| 2026-10-06 | 10.2577% | 7.8472% | -2.410 |
| 2026-10-07 | 9.8679% | 7.6226% | -2.245 |
| 2026-10-08 | 9.8679% | 7.6226% | -2.245 |
| 2026-10-09 | 9.7682% | 7.4761% | -2.292 |
| 2026-10-12 | 9.3394% | 7.2984% | -2.041 |
| 2026-10-13 | 10.5279% | 8.0421% | -2.486 |
| 2026-10-14 | 9.4650% | 7.4319% | -2.033 |
| 2026-10-15 | 9.4650% | 7.4319% | -2.033 |
| 2026-10-16 | 10.1428% | 7.8592% | -2.284 |
| 2026-10-19 | 10.8048% | 8.1306% | -2.674 |
| 2026-10-20 | 7.6891% | 7.6891% | 0.000 (already correct) |

Every fall is inside the brief's 1.9-3.1 point band. The four-term identity closes on
every day, with the two known residuals (6.08e-05 on 09-29, 1.54e-06 on 10-06)
unchanged. 2026-10-20 reproduces its stored value to 2.8e-17 - the control that the
script matches the live code.

**Verified after the apply**: 17 rows before and after, same 17 dates; 2026-09-28
changed in **no** column; the 15 applied rows changed in `pre_hedge_vol` +
`written_at` only; 2026-10-20 changed in no column; `hedged_vol`, `realized_vol`,
`pnl_*`, `n_filled`, `vol_ratio` byte-identical to the backup; re-running the dry run
says `every day already holds the recomputed pre-hedge vol: nothing to write`.

**Rollback**: `python scripts/restore_attribution.py --apply`
(backup `docs/owner_fixes/backups/attribution_before.json`, 16 rows; whole table in
`attribution_context_before.json`, 17). The restore dry run reproduced the backup
exactly **before** the apply (0 rows differing).

## Part 2 - reconciliation back-fill: **applied and verified**

Dry run reported **14** updatable rows - the brief's number, not 13. 2026-10-19
became updatable because its morning ran at 15:30 UTC on 10-20, and 2026-10-20 became
the new "no fills rows" close, exactly as 10-19 was before it. 2026-09-25 was
considered and left alone (no fills rows, and realised vol needs two attributed
sessions).

```
close         filled before   filled after  realized before  realized after   note
2026-09-25             0.00           0.00                -               -   not upserted
2026-09-29             0.00           0.00                -            4.64%
2026-09-30             0.00           0.00                -            3.46%
2026-10-01             0.00         517.42                -            2.83%
2026-10-02             0.00     411,229.54                -            2.81%
2026-10-05             0.00     425,739.98                -            2.70%
2026-10-06             0.00     342,598.25                -            2.53%
2026-10-08             0.00     494,417.34                -            2.19%
2026-10-09             0.00     376,262.54                -            2.59%
2026-10-12             0.00     409,357.31                -            2.77%
2026-10-13             0.00     437,952.78                -            2.64%
2026-10-15             0.00     429,573.30                -            2.26%
2026-10-16             0.00     480,740.60                -            2.75%
2026-10-19             0.00     394,934.52                -            2.46%
2026-10-20             0.00           0.00                -            2.40%
```

Applied ~23:44 UTC (`reconciliation` has no write stamp). `filled_notional` was
independently re-derived as `sum(abs(filled_notional))` per close from `efb.fills`
(2026-10-02: 207 legs, 411,229.54; 2026-10-16: 181 legs, 480,740.60; 2026-10-19: 163
legs, 394,934.52 - all matching), and `realized_annual_vol` comes from
`live.reconcile.realized_annual_vol_for`, the function `reconcile.backfill` calls for
a new morning.

**Verified**: post-apply dry run `0 row(s) would be updated`; the restore dry run
shows the two columns as the only difference with `other cols = 0` on all 14 rows
(`intended_notional`, `forecast_annual_vol`, the cost split and the risk blocks
unchanged); table still 15 rows on 15 dates.

**Rollback**: `python scripts/restore_reconciliation.py --apply`
(backup `reconciliation_before.json`, 14 rows; whole table
`reconciliation_context_before.json`, 15).

### Two bugs the apply forced out (fixed, committed)

1. **jsonb cannot be written back as an object.** `store.select` returns jsonb as a
   dict and `store.upsert` binds values straight to the placeholder, so the first
   `--apply` died with `psycopg.ProgrammingError: cannot adapt type 'dict' using
   placeholder '%s'`. It wrote nothing (verified against the backup). Rows are now
   re-encoded with `store.json_text`, which is what the evening's own writer passes.
2. **`Decimal` never equals the float that produced it**, so every re-run claimed 14
   rows needed updating and the verification could never pass. The change test now
   compares at `1e-9 * max(1, |new|)`.

## Part 3 - research: **panel built and validated; study stopped after B0**

Worktree `../efb-daily-design`, branch `research-daily-design`.

**Daily panel: complete.** 586 sessions (2024-06-03..2026-10-02): **557 built** with
the live branch (data through each close), **29 published** (the frozen month-ends),
**0 stale**. 1,750,954 cells, 2.21 s/session, 21.6 min.

- `/tmp/churn/daily/models/XS-v1/descriptors_daily.parquet` (15.4 MB)
- `/tmp/churn/daily/models/XS-v1/descriptors_daily.labels.json` (branch per session)
- data copy `/tmp/churn/daily` (893 MB); the repo's `data/` was never written to
- build log `/tmp/daily_panel_build.log`, validation log `/tmp/validate_panel2.log`

### Validation (a): built row vs the frozen published row, 29 month-ends - **pass, exact**

Max abs difference per descriptor over all 29 days: **size 0.0, beta 3.1e-15,
momentum 2.7e-15, reversal 4.4e-15, resid_vol 1.4e-13, liquidity 4.5e-15.** Days over
1e-06: none. 502 names on every day, all common.

This required building on the **cleaned** returns branch (`EFB_DESIGN_RETURNS=clean`).
The live default is the raw branch, which differs from the frozen rows (~1.4e-3 median
on beta/momentum/resid_vol, 0.63 on one name). The published artifact was fitted on
the clean panel, so the study uses clean to make its month-ends equal the frozen ones.

### Validation (b): rebuilt panel vs `efb.e11_descriptors`, 2026-09-04..10-02 - **disagrees**

20 dates, 59,680 cells matched (360 panel-only). Median |diff| **0.0080**, max
**2.16**:

| descriptor | median | max |
|---|---|---|
| size | 0.0065 | 0.040 |
| beta | 0.0074 | 0.674 |
| momentum | 0.0151 | **2.163** |
| reversal | 0.0153 | 0.284 |
| resid_vol | 0.0072 | 2.080 |
| liquidity | 0.0037 | 0.042 |

**Cause, proven:** the study copy is a 2026-10-03 snapshot and the store rows were
built by the live tree from live data. The underlying returns differ on exactly those
dates - `processed/returns.parquet` max |Δr| between the two trees is 6.0e-05 on
2026-09-29 but **1.48e-02 on 09-30** and 1.03-1.08e-02 on 10-01/10-02, with tens of
names differing per close, and the copy has 811 raw names against the live tree's 830
(502 mapped in common). So this is a **cross-tree** comparison, not a code-path
disagreement: check (a), which is same-tree and same-code, is exact. **Not a defect in
the panel**, but the owner should know it is not an agreement either.

### Study: 1 of 7 variants done when stopped

| variant | tov/reb | cost bp/yr | net bp | alpha | expo median | p95 | max | var share |
|---|---|---|---|---|---|---|---|---|
| **B0** monthly, no guard | 87.02% | 69.1 | 48.4 | 100% | **10.47%** | **22.67%** | **33.32%** | 47.09% |

B0 reproduces the frozen-panel B0 exactly on turnover, cost and net (its rebalance
days are month-ends, where the daily panel equals the frozen row) - the identity
check that the panel is usable. Exposure, now measured **every session** instead of
only at the 29 publishes, is **median 10.47%, p95 22.67%, max 33.32%** against the
frozen study's 0.53% median / 1.19% average. That is the headline so far: with
loadings refreshed nightly, a monthly book's true exposure is an order of magnitude
larger than the frozen panel could reveal, so G3's guard will fire far more often and
cost far more than the +8.6 bp/yr the frozen study estimated.

`D1` (daily rebalance) was running when the pause came - it re-solves the construction
on all 586 sessions, so it is the slowest variant (~25 min). G3, G5, B0H, G3H, G5H had
not started.

- Partial results (resume-safe): `/tmp/daily_design_study_rows.partial.json` (B0 only)
- Log: `/tmp/daily_study.log` (the two `StoreNotConfigured` warnings come from the
  variant's own store-free path and are expected)
- No `docs/research/daily_design_study.md` / `.json` was written yet.

### Open questions for the owner

1. **Should the live loop keep `EFB_DESIGN_RETURNS` unset (raw)?** The published
   artifact and the frozen rows are fitted on the clean panel; only the clean branch
   reproduces them. The study uses clean so its month-ends equal the frozen ones. If
   live really runs raw, the study's absolute exposure levels would shift somewhat
   (its ranking would not).
2. **The full-row attribution recompute is still available and still withheld.** If
   the owner wants `pnl_cost` / `realized_vol` for 10-09..10-19 re-derived from the now
   complete fills (2026-10-13 would move -1.01e-03), that is a separate explicit
   decision. Script and backups are ready: drop `--only-pre-hedge-vol`.

## Exact next step on resume

```bash
cd /Users/amankesarwani/PycharmProjects/efb-daily-design
set -a; source ../equity-factor-book/.env; set +a
EFB_DESIGN_RETURNS=clean python scripts/daily_design_study.py run \
  --root /tmp/churn/daily --out docs/research/daily_design_study.json
```

It resumes from `/tmp/daily_design_study_rows.partial.json`, so B0 is not repeated;
D1 takes ~25 min and the remaining five 2.5-4 min each. Then write
`docs/research/daily_design_study.md` from the JSON (D1/B0/G3/G5/B0H/G3H/G5H with
turnover, cost, guard fires and cost, alpha retained, exposure median/p95/max, worst
variance share, and net at 169 bp at borrow 0.5% and 2%) and push the branch.

Two cosmetic script fixes before that run: the partial row is written *before*
`row["cadence"]` and `row["net_at_anchor"]` are set, so a resumed row lacks both keys.
