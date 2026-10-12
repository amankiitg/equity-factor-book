# The NOT NULL NaN audit (item 5)

Run overnight against the **local parquet mirror**, because this session has no
`EFB_SUPABASE_DB_URL` and therefore no read-only access to the live database. The
tool is the deliverable and it is read-only:

```
.venv/bin/python scripts/nov11_notnull_audit.py --out docs/nov11_notnull_audit.md
```

with `EFB_SUPABASE_DB_URL` set (or `EFB_STORE=local` for the mirror), and it exits
non-zero if any column holds a NaN or a null, so it can be used as a check.

Two halves make the claim. **The declaration**: `not null` in Postgres does not
exclude a NaN (`select float8 'NaN' is not null` is true), so the schema says nothing
by itself; the 28 columns below are the numeric NOT NULL columns this repo declares,
parsed from `live/supabase_schema.sql` rather than asked of the live catalogue, so a
column added without a thought for the NaN it can hold appears in the next audit.
**The code**: the writers refuse a NaN where a fabricated number would be worst -
`scripts/run_live_daily.py::specific_std_or_refuse` refuses a variance that is not
finite *or* not positive (item 15), `efb.reconciliation.realized_annual_vol` is
nullable and computes rather than invents (item 26), and the attribution step's own
handler records its outcome (item 28).

**The data half is not finished**: the mirror is not the live store. Seven columns are
`not read` below, and the live run of the command above is what closes item 5.

# The NOT NULL NaN audit

Source: `local parquet (live/state/supabase)` (mode `local`) - **not the live database**. 28 NOT NULL numeric column(s) in `live/supabase_schema.sql`: 21 clean, 0 with a NaN or a null, 7 not read.

`not null` does not exclude a NaN in Postgres, so this is a claim about the data and not about the constraint. A column the source does not hold is `not read`, which is not a pass.

| table | column | rows | NaN | null | verdict |
|---|---|---|---|---|---|
| `broker_positions` | `market_value` | — | — | — | not read |
| `e11_corporate_actions` | `factor` | — | — | — | not read |
| `fills` | `fill_price` | — | — | — | not read |
| `fills` | `filled_notional` | — | — | — | not read |
| `fills` | `intended_notional` | — | — | — | not read |
| `nav` | `nav` | 1 | 0 | 0 | clean |
| `nav` | `realized_pnl` | 1 | 0 | 0 | clean |
| `orders` | `filled_notional` | 27 | 0 | 0 | clean |
| `orders` | `intended_notional` | 27 | 0 | 0 | clean |
| `positions` | `alpha` | 27 | 0 | 0 | clean |
| `positions` | `idio_vol` | 27 | 0 | 0 | clean |
| `positions` | `previous_weight` | 27 | 0 | 0 | clean |
| `positions` | `signed_notional` | 27 | 0 | 0 | clean |
| `positions` | `trade` | 27 | 0 | 0 | clean |
| `positions` | `weight` | 27 | 0 | 0 | clean |
| `positions` | `z` | 27 | 0 | 0 | clean |
| `proposals` | `achieved_annual_vol` | 1 | 0 | 0 | clean |
| `proposals` | `avg_trade_size` | 1 | 0 | 0 | clean |
| `proposals` | `expected_establishment_cost_bps` | 1 | 0 | 0 | clean |
| `proposals` | `gross` | 1 | 0 | 0 | clean |
| `proposals` | `idio_share_after_fmp` | 1 | 0 | 0 | clean |
| `proposals` | `max_abs_exposure_after_fmp` | 1 | 0 | 0 | clean |
| `proposals` | `n_eff_full_book` | — | — | — | not read |
| `proposals` | `n_eff_kept` | — | — | — | not read |
| `proposals` | `nav` | 1 | 0 | 0 | clean |
| `proposals` | `net` | 1 | 0 | 0 | clean |
| `proposals` | `notional` | 1 | 0 | 0 | clean |
| `proposals` | `target_annual_vol` | 1 | 0 | 0 | clean |
