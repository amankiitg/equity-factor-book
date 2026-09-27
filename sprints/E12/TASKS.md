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
      2012-02-01 to 2026-07-31 at (rho 0.02, seed 0): the mean per-factor gap is
      1.694e-04, the largest single gap is 0.6258 of the reversal exposure, and the
      timing P&L sums to 0.014142 against a cumulative total P&L of 0.703958, so the
      two vintages disagree over about 2.0% of the book's P&L. `data/attribution/`
      carries the per-session `exposure_json`, `book_exposure_json`, `pnl_timing`
      and `pnl_timing_json` behind those numbers.
- [x] Answer whether the session-dated design is computable at the previous close.
      **It is not.** The model's own `shift_test` says so in the code:
      the size column is the log of market cap at the session, which is the previous
      cap times one plus the return being explained; and the beta, reversal, residual
      volatility and liquidity windows all end on the session. Only momentum is
      unaffected, because its window ends 21 sessions earlier. The script's
      correlation probe is printed as a negative control rather than as evidence: the
      same-day and previous-close caps differ by one day of returns, so their
      correlations agree to three decimals (0.2100 against 0.2093) and the test
      cannot separate the vintages at all.
- [x] Reported here; the live hedge is unchanged. The gap is material enough to
      measure and not material enough to act on before the flip.
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
