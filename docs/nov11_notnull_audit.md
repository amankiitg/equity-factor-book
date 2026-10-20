# The NOT NULL NaN audit

Source: `postgres/efb` (mode `postgres`). 28 NOT NULL numeric column(s) in `live/supabase_schema.sql`: 28 clean, 0 with a NaN or a null, 0 not read.

`not null` does not exclude a NaN in Postgres, so this is a claim about the data and not about the constraint. A column the source does not hold is `not read`, which is not a pass.

| table | column | rows | NaN | null | verdict |
|---|---|---|---|---|---|
| `broker_positions` | `market_value` | 1797 | 0 | 0 | clean |
| `e11_corporate_actions` | `factor` | 1 | 0 | 0 | clean |
| `fills` | `fill_price` | 1527 | 0 | 0 | clean |
| `fills` | `filled_notional` | 1527 | 0 | 0 | clean |
| `fills` | `intended_notional` | 1527 | 0 | 0 | clean |
| `nav` | `nav` | 13 | 0 | 0 | clean |
| `nav` | `realized_pnl` | 13 | 0 | 0 | clean |
| `orders` | `filled_notional` | 2642 | 0 | 0 | clean |
| `orders` | `intended_notional` | 2642 | 0 | 0 | clean |
| `positions` | `alpha` | 2312 | 0 | 0 | clean |
| `positions` | `idio_vol` | 2312 | 0 | 0 | clean |
| `positions` | `previous_weight` | 2312 | 0 | 0 | clean |
| `positions` | `signed_notional` | 2312 | 0 | 0 | clean |
| `positions` | `trade` | 2312 | 0 | 0 | clean |
| `positions` | `weight` | 2312 | 0 | 0 | clean |
| `positions` | `z` | 2312 | 0 | 0 | clean |
| `proposals` | `achieved_annual_vol` | 14 | 0 | 0 | clean |
| `proposals` | `avg_trade_size` | 14 | 0 | 0 | clean |
| `proposals` | `expected_establishment_cost_bps` | 14 | 0 | 0 | clean |
| `proposals` | `gross` | 14 | 0 | 0 | clean |
| `proposals` | `idio_share_after_fmp` | 14 | 0 | 0 | clean |
| `proposals` | `max_abs_exposure_after_fmp` | 14 | 0 | 0 | clean |
| `proposals` | `n_eff_full_book` | 14 | 0 | 0 | clean |
| `proposals` | `n_eff_kept` | 14 | 0 | 0 | clean |
| `proposals` | `nav` | 14 | 0 | 0 | clean |
| `proposals` | `net` | 14 | 0 | 0 | clean |
| `proposals` | `notional` | 14 | 0 | 0 | clean |
| `proposals` | `target_annual_vol` | 14 | 0 | 0 | clean |
