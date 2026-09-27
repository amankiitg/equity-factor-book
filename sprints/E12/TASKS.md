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
      single gap is 0.6258 of the reversal exposure, and the timing P&L is +141.4 bp
      against a total P&L of +520.7 bp on those sessions, so it is **27.2 percent of
      their net P&L** (its absolute size, 660.5 bp, is 15.3 percent of the 4,316.5 bp
      of absolute daily P&L; the denominator is stated because the two readings
      differ). An average taken over all 3,645 sessions would divide that by twenty
      and read as nothing; an earlier note in this file did exactly that and was
      wrong. `data/attribution/` carries
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
      factor and 27.2 percent of the net P&L measured above. The fix moves every
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

- [x] After each evening run, attribute every stored day not yet attributed, from
      the stored positions and the XS-v1 artifacts, and store the rows.
      `efb.attribution.from_positions` builds the books from the store's own
      `positions` table (the same point-in-time convention `daily_weights` uses for
      the seed, so live and historical days go through one implementation) and skips
      the days the table already holds. `live/attribution_job.py` reads the day's cost,
      forecast and fill counts from the store's `reconciliation` and `orders` tables,
      and `scripts/run_live_daily.py` calls it after the reconciliation is stored.
- [x] A failure is logged and never stops the trading run. The call is inside its own
      handler that scrubs the reason, logs at warning, and returns; a test pins that
      there is no re-raise and no `logger.exception` at that call site.

## 6. Live page

- [x] Attribution section: cumulative P&L split into factor, idio and cost, the
      hedge's factor P&L per day, the raw-beta line, realized versus expected cost.
      `live/snapshot.py::attribution_block` builds it from the store's attribution
      table, `docs/snapshot.schema.json` declares it (and the builder's keys are
      checked against the schema), `web/src/types.ts` mirrors it, and `App.tsx`
      renders it as its own section with the worst day's identity residual beside the
      sums. The page fixtures carry the seed artifact's real block, so the section is
      tested with numbers rather than a stub.

## 7. The skill test

- [x] Idio P&L mean, t-statistic and information ratio with standard errors.
      `efb.attribution.skill_test`: the mean and its standard error, the t, the
      annualized information ratio with its own error, and the book's Sharpe with
      **both** of `efb.perf`'s standard errors, i.i.d. and Lo 2002, annualized the
      same way the Sharpe is.
- [x] The days needed to detect a given IR at a stated power. `n = (t / IR_daily)^2`,
      quoted for IRs of 0.25, 0.5, 1.0 and 2.0 at the t of 2.0 the criterion sets:
      16,128, 4,032, 1,008 and 252 days. The closed form is rounded before the
      ceiling, because it lands a few ulps above its own integer and 1,009 days would
      be a float artefact rather than a number.
- [x] A plain-English verdict, and the F12.3 rule that no skill is claimed unless the
      t-statistic exceeds 2. The bar is a constant (`DETECTION_T`), the verdict is a
      sentence, and the seed book's own verdict is recorded with the caveat that its
      Sharpe was selected on this sample.

## 8. `scripts/review_week.py`

- [x] Per day: the P&L split, realized factor P&L against the near-zero the hedge
      promises, cost realized versus expected, fill differences, forecast versus
      realized volatility, with a plain-English summary. The day's identity residual
      and the hedge's own timing line are in the row as well, because the row is what
      makes the summary checkable.
- [x] Works on however many days exist. Tested at one day, at three, at a window and
      at nothing: a single day is described as a single day rather than as a
      distribution, the cost and volatility lines say when they have no data behind
      them instead of printing a number anyway, and the skill line refuses to read a
      two-day t-statistic as clearing a bar.

## 9. Memo and walkthrough

- [x] `docs/research/E12_attribution_report.md` and
      `notebooks/E12_walkthrough.ipynb`, scaffolded on the seed books with every
      number read from a stored file, so the live run swaps inputs and not code. The
      memo is generated by `sprints/E12/write_memo.py` and the notebook by
      `sprints/E12/build_walkthrough.py`, executed headlessly and rendered to
      `notebooks/E12_walkthrough.html`.
- [x] `sprints/E12/RESULTS.json` registered by `sprints/E12/register_results.py`,
      with F12.1 to F12.3 read verbatim out of the roadmap. F12.1's verdict is
      `partial`, which is what the measurement says: it holds on 174 of the 3,645 seed
      sessions and misses by a median of 1.8 bp elsewhere. F12.2 and F12.3 are
      `pending`, and F12.3's expected verdict is written down as `luck`.
- [ ] **Not built, and named as open rather than dropped:** the regime table and the
      seven-way selection, sizing and timing decomposition, both of which are in the
      roadmap's E12 scope and neither of which is among this sprint's nine tasks. The
      memo's coverage section says so.

## Exit

- [ ] F12.1 re-evaluated on live days as they arrive.
- [ ] F12.2 and F12.3 evaluated once 30 live days exist; F12.3's expected verdict
      is luck, written down before the numbers.
- [ ] Walkthrough rendered to HTML and linked; D11 checked off.
- [ ] Merged into `main` only after the flip, on the owner's word.

## What the exit items mean now

- F12.1, F12.2 and F12.3 stay open because two of them are statements about thirty
  live trading days and the third can only be scored once it is a live book. Their
  machinery is standing, their numbers are registered, and F12.3's expected verdict
  is written down.
- "Walkthrough rendered and linked; D11 checked off": the notebook is rendered to
  `notebooks/E12_walkthrough.html` and both it and the memo are linked from the
  Methodology tab through `dashboard/tabs/methodology.py`, which is how E1 to E10
  are linked. D11 is the page's attribution section, built into the live page rather
  than as a new Streamlit tab: item 6 of the owner's list asks for the page, and the
  page is where the evening run's snapshot already goes.
