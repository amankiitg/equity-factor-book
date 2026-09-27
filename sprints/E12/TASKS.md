# Sprint E12: tasks

Sequenced so that everything buildable before live data is built, and the two
criteria that need 30 live days are left with their machinery standing and their
verdicts pending. One commit per item.

## 1. Sprint documents

- [x] `sprints/E12/PRD.md`, with F12.1 to F12.3 copied verbatim from
      `docs/roadmap_v2.md` and each marked for what it can be evaluated on.
- [x] This file.

## 2. Holdings-based attribution (`efb/attribution.py`)

- [x] One row per session: factor P&L by factor, idio P&L, cost, the
      reconciliation residual, the book's exposures under both design vintages,
      the raw CAPM-beta line, realized versus forecast volatility with the bias
      statistic, target versus filled and the cost columns.
- [x] The stored specific returns, with the session-dated reported design: the
      reconciliation closes to 6.9e-18 on the dates the current build produced.
- [x] Point-in-time weights: the book dated before the session earns it, no
      fill-forward, no target in place of a holding.

## 3. Hedge timing

- [x] Measure, per seed-book session, the book's factor exposure under the design
      dated the session against the design at the previous close, and the factor
      P&L that gap produces. Measured over the whole seed book, 3,645 sessions from
      2012-02-01 to 2026-07-31 at (rho 0.02, seed 0). **The two vintages differ on
      174 of those sessions**, which are the sessions that follow a rebalance date:
      the seed's descriptor artifact is a monthly snapshot, so on the other 3,471
      sessions the design dated the session and the design dated the book's own close
      are the same object and the gap is identically zero. Over the 174 sessions
      where it bites, the mean per-factor exposure gap is **0.01967**, the largest
      single gap is 0.6258 of the reversal exposure, and the timing P&L is +0.014142
      against +0.052066 of total P&L on those sessions, so it is **15.3 percent of
      the absolute P&L on the sessions where it bites**. An average taken over all
      3,645 sessions would divide that by twenty and read as nothing; the earlier
      note in this file did exactly that and was wrong. `data/attribution/` carries
      the per-session `exposure_json`, `book_exposure_json`, `pnl_timing` and
      `pnl_timing_json` behind these numbers.
- [x] Answer whether the session-dated design is computable at the previous close.
      **It is, and the first answer recorded here was wrong.** Every descriptor on
      row `t` of `descriptors.parquet` is built from data through the previous close:
      `efb/models/fundamental.py` writes size as `log(market_cap.shift(1))`, and beta,
      residual volatility and liquidity each carry `.shift(1)` on their window, with
      reversal shifting the return series by one; only momentum reaches further back
      (through `t-21`). Verified on the stored artifact: for 2026-09-21 the size
      descriptor matches log market cap at the 2026-09-18 close to 0.000e+00 for LITE,
      MRNA and AAPL, and misses the same-day cap by 8.4e-03 to 1.2e-01. So the design
      dated a session is previous-close data, and pairing it with that session's
      returns is correct rather than look-ahead: the stored mean R-squared 0.329586
      matches the shift test's **lagged** figure 0.329462 to 1.2e-04, where the
      look-ahead variant is 0.364005. The `shift_test` docstring describes its own
      "next cross-section" variant and must not be read as the stored fit's vintage.
- [x] The consequence, recorded as a **post-flip fix** and not applied: the live hedge
      is one session stale. The evening of close `t` hedges with the design dated `t`
      (data through `t-1`), while the book earns its return over `t` to `t+1`, whose
      exposure is described by the design dated `t+1`, which needs only `t`'s close and
      is available in the same evening. The drift this leaves is the 0.01967 per
      factor and 15.3 percent of the absolute P&L measured above. The fix moves every
      stored book, the guard numbers and the recorded ex-ante risk, so it waits for
      the flip. Written up in `docs/open_items.md`.
- [x] Reported; the live hedge is unchanged.
- [x] Measured on the whole seed book and reported: the reconciliation closes to
      **median 1.771e-04, max 1.233e-02** over 3,645 sessions, and to 6.9e-18 on the
      three 2026 sessions the current build produced. F12.1's 1e-10 is a statement
      about the current build's dates; the older vintages' stored factor and specific
      returns do not reproduce their own panel to that tolerance, and the two facts
      are kept apart rather than averaged into one.

## 4. `efb.attribution`, the table

Given to the owner as SQL, separately from this file:

```sql
create table if not exists efb.attribution (
    trade_date date not null,
    n_names integer,
    gross double precision,
    net double precision,
    pnl_total double precision,
    pnl_factor double precision,
    pnl_idio double precision,
    pnl_cost double precision,
    identity_residual double precision,
    pnl_factor_json jsonb,
    n_computed_specific integer,
    book_beta double precision,
    market_return double precision,
    pnl_beta double precision,
    forecast_vol double precision,
    realized_vol double precision,
    vol_ratio double precision,
    bias_statistic double precision,
    expected_cost_bps double precision,
    realized_cost_bps double precision,
    n_target integer,
    n_filled integer,
    max_fill_gap double precision,
    n_missing_return integer,
    missing_return_weight double precision,
    written_at timestamptz not null default now(),
    primary key (trade_date)
);

alter table efb.attribution enable row level security;
alter table efb.attribution disable row level security;
grant select, insert, update on efb.attribution to efb_writer;
```

- [x] Added to `live/supabase_schema.sql` with the same idempotent `add column if
      not exists` block the other tables carry, and the table registered in
      `live/store.py` with `trade_date` as its key. The create block carries the
      three columns added with the hedge-timing line, and the additive block
      repeats them, so a database provisioned from the earlier file gets them too.
      `efb/attribution.TABLE_COLUMNS` is the row's own column list and the store
      test compares it against the schema, which is the drift check the other
      tables have.

## 5. Evening wiring

- [ ] After each evening run, attribute every stored day not yet attributed, from
      the stored positions and the XS-v1 artifacts, and store the rows.
- [ ] A failure is logged and never stops the trading run.

## 6. Live page

- [ ] Attribution section: cumulative P&L split into factor, idio and cost, the
      hedge's factor P&L per day, the raw-beta line, realized versus expected cost.

## 7. The skill test

- [ ] Idio P&L mean, t-statistic and information ratio with standard errors.
- [ ] The days needed to detect a given IR at a stated power.
- [ ] A plain-English verdict, and the F12.3 rule that no skill is claimed unless
      the t-statistic exceeds 2.

## 8. `scripts/review_week.py`

- [ ] Per day: the P&L split, realized factor P&L against the near-zero the hedge
      promises, cost realized versus expected, fill differences, forecast versus
      realized volatility, with a plain-English summary.
- [ ] Works on however many days exist, so it can run after day one.

## 9. Memo and walkthrough

- [ ] `docs/research/E12_attribution_report.md` and
      `notebooks/E12_walkthrough.ipynb`, scaffolded on the seed books with every
      number read from a stored file, so the live run swaps inputs and not code.

## Exit

- [ ] F12.1 re-evaluated on live days as they arrive.
- [ ] F12.2 and F12.3 evaluated once 30 live days exist; F12.3's expected verdict
      is luck, written down before the numbers.
- [ ] Walkthrough rendered to HTML and linked; D11 checked off.
- [ ] Merged into `main` only after the flip, on the owner's word.
