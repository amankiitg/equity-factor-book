# The SKYD 2026-10-14 return: where it lives, and whether anything needs a fix

**Verdict: no fix is needed.** The false corporate action is gone, the only stored
copy of the return is derived nightly from prices that were never touched, and the
next evening rebuilds it correctly on its own. This note records the evidence and
the two queries that verify it after tonight's run.

Measured 2026-10-20, read-only.

## 1. The action row is gone

`efb.e11_corporate_actions` holds **one row**:

| trade_date | ticker | effective_date | factor | source | explained_by | new_ticker |
|---|---|---|---|---|---|---|
| 2026-10-01 | CTVA | 2026-10-01 | 1.0 | manual.record | spinoff | VYLR |

- **No `SKYD` row**, on 2026-10-15 or anywhere else.
- **No row whose other leg is a warrant, unit or right**, using
  `live.corporate_actions.is_derivative_line` on both the `ticker` and the
  `new_ticker` column (markers `WS, WT, W, WTS, U, UN, UNIT, R, RT, RIGHT`, matched
  on `.`, `-` or `/`): **0 hits**. The CTVA→VYLR row is a real spin-off.

## 2. Where the 2026-10-14 return is stored or derived

The correct value, from `efb.e11_prices` (SKYD close 9.27 on 10-13 → 7.06 on 10-14,
`adj_close` equal to `close`, `split_factor` 0): **−23.8403%**.

| place | what it is | value for 2026-10-14 SKYD | verdict |
|---|---|---|---|
| `efb.e11_prices` | the price panel the return is computed from | close 7.06 vs 9.27 → **−23.8403%** | **correct** |
| `efb.e11_corporate_actions` | the rule that rewrote it | row **deleted** | **gone** |
| `efb.e11_descriptors` | XS-v1 loads, built from the returns panel | **no SKYD row at all** (the model's sector map carries `PSKY`, not `SKYD`) | not affected |
| `efb.e11_specific_returns` | the fitted specific return | **no SKYD row**; PSKY's last is 2026-10-05 | not affected |
| `efb.e11_specific_var` | the diagonal | **no SKYD row**; PSKY's last is 2026-10-05 | not affected |
| `efb.positions` / `efb.attribution` | the book and its P&L | **no SKYD position**; PSKY's last is 2026-10-05 | not affected |
| `processed/returns.parquet` **in the run tree** | the artifact the evening reads, rebuilt every night from prices | ephemeral; the 2026-10-19 rebuild gives **−23.8403%** | self-healing |
| R2 seed `processed/returns.parquet` | the frozen bundle | ends **2026-09-21**, **0 SKYD rows** | not affected |
| R2 snapshots (`latest.json`, `snapshots/<close>.json`) | the page document | **could not be read**: `EFB_R2_*` is not configured on this machine. The document carries the book, weights and P&L blocks, never a per-name return | not a carrier |
| `efb.run_status` | the run's record | 2026-10-14 is the `error` row (`KeyError: ['dividend','split_factor']`); 2026-10-15's rows carry `splits: []`, `flags: []` | not the return |

There is **no table in `efb` that stores a total return**: the only `%return%`
columns are `e11_specific_returns.specific_return` and the attribution's P&L terms,
and neither has a SKYD row for any date.

**Why the model never saw the wrong number.** The false action rewrote SKYD's return
in the *returns artifact* of the 2026-10-15 run only. That evening also extended the
model, but XS-v1 fits on its *mapped* panel (`processed/sectors.parquet`), and the
sector map carries **PSKY** (Communication Services) and no SKYD. SKYD therefore has
no descriptor row and no specific-return row for any date, so the rewritten return
could not enter a stored model artifact.

## 3. Will tonight's run recompute it correctly?

**Yes, with nothing done.** The path, traced in `scripts/run_live_daily.py`:

1. `extend.extend_prices()` appends from the vendor; `raw/prices.parquet` is correct
   and was never touched by the rule (the rule edits returns, not prices).
2. `extend.extend_returns(run_tree)` calls `returns.compute_returns(prices, rf)` over
   **every session**, not only the new one, and then
   `corporate_actions.apply_recorded(returns, prices, recorded_spinoffs())`.
   `recorded_spinoffs()` is `store.select("efb.e11_corporate_actions")` - now one
   CTVA row - so SKYD is not corrected and its −23.8403% stands.
3. `corporate_actions.apply_to_artifact(...)` re-discovers spin-offs from the
   vendor's feed. Both discovery paths - `resolve_spinoffs` and
   `spinoffs_from_rows` - refuse a child where `is_derivative_line(child)` is true,
   so `SKYD.WS`/`SKYD/WS` can never be applied again even if the vendor re-files it.
4. `extend_model()` fits only the new sessions on the mapped panel, where SKYD is
   absent.

Evidence that this already works: the tree built for the 2026-10-19 close
(`/tmp/nov11merge/cut-2026-10-19/data`, from the R2 seed + the store appendix +
`extend_returns`, with the SKYD row **still present** at the time) carries
**−23.8403%**, because the derivative-line guard skipped the record.

## 4. Verification after tonight's run (read-only)

```sql
-- 1. the action did not come back
SELECT * FROM efb.e11_corporate_actions WHERE ticker = 'SKYD' OR new_ticker ILIKE '%WS%';

-- 2. the price panel still says -23.84%
SELECT trade_date, close, adj_close, split_factor FROM efb.e11_prices
WHERE ticker = 'SKYD' AND trade_date BETWEEN '2026-10-13' AND '2026-10-15'
ORDER BY trade_date;
```

The second query's 10-14 close divided by the 10-13 close, minus one, must be
**−23.8403%**. The recomputed artifact itself is not stored anywhere the owner can
query: it lives in the run tree and in `efb.e11_prices`, from which it is derived.
