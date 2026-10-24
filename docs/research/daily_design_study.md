# What the drift guard costs once the loadings refresh every evening

`docs/research/churn_followup.md` measured the monthly book's exposure against the
frozen descriptor artifact, which publishes on month ends: 29 design days in a
586-session window. Live is not like that. `race.next_descriptor_design` builds the
next session's row from tonight's close, every night, so between two publishes the
frozen tree sees no drift at all and the guard it priced (+8.6 bp/yr, 1.3 turns) could
only ever fire on a publish date.

This study rebuilds the design for **every** session and reruns the same window,
cadence, universe and cost model, so exposure is measured on all 586 sessions and a
guard's cost is the cost of reacting to real drift.

## What was measured, and one correction that changed the answer

Panel: 586 sessions, 2024-06-03..2026-10-02, built by
`scripts/build_daily_design_panel.py` with `race.next_descriptor_design`'s live branch
(data through each close): **557 built, 29 published, 0 stale**, 1,750,954 cells.

**The first run of this study was wrong and is kept, not deleted.** It installed the
daily panel as the *measurement* design only, leaving the tree's
`models/XS-v1/descriptors.parquet` on the frozen month-end rows, so the construction
(`efb/eval_risk.py::_risk_inputs` -> `race.next_descriptor_design`) hedged on a row up
to 21 sessions old while the measurement used tonight's row. The difference between
those two rows is not drift, and it swamped everything else: a freshly built book
showed a **15.71% median** phantom exposure over 14 sampled sessions, versus **0.00%
on a month end**, the one day in the sample where the two rows coincide. That run is
at `docs/research/daily_design_study_staleloadings.json`.

The fix is the one the live loop has: the tree now carries the nightly rows. In the
data copy (never the repo's `data/`):

```bash
cd /tmp/churn/daily/models/XS-v1
cp descriptors.parquet descriptors_frozen_month_end.parquet
python - <<'PY'
import pandas as pd, numpy as np
f = pd.read_parquet("descriptors_frozen_month_end.parquet")
d = pd.read_parquet("descriptors_daily.parquet")
keep = f[pd.to_datetime(f["date"]) < d["date"].min()]          # history before the window
daily = pd.DataFrame({
    "date": pd.to_datetime(d["date"]), "ticker": d["ticker"],
    "descriptor": d["descriptor"], "value_raw": np.nan, "value_winsor": np.nan,
    "value_z": np.nan, "value_z_orth": d["value_z_orth"].astype(float),
    "n_obs": np.nan, "look_ahead": False,
})
pd.concat([keep, daily], ignore_index=True).sort_values(
    ["date", "ticker", "descriptor"]).to_parquet("descriptors.parquet", index=False)
PY
```

No `(date, ticker, descriptor)` is duplicated (2,316,708 rows, 747 dates), and
`next_descriptor_design` now takes its *published* branch - "the shape a replay has
when the artifact carries the daily rows" - so the hedge is built for the session the
book earns, exactly as live builds it. `value_raw`, `value_winsor`, `value_z` and
`n_obs` are NaN and `look_ahead` False on the rows this writes; the evening path reads
only `date` and `value_z_orth`, and `look_ahead` is consumed from the panel inside
`efb/build.py`, not from this file.

Residual after the swap, same 14 sessions: **median 3.71%, max 9.20%**. That is not
zero and should not be - a book hedged to *tomorrow's* row is measured against
*tonight's* row, so a one-session basis is real. It is also the floor of every number
below.

## The variants, measured every session

586 sessions, NAV 1,000,000, 2.33 years, universe frozen at the 2026-09-18 SPY archive
(dates dated for every session, so P&L levels are indicative and the comparison is the
result). Exposure is the worst absolute factor exposure of the held book, measured
after that session's trading against that session's design.

| variant | cadence | hedge | tov/reb | tov/yr | cost bp/yr | net bp | alpha | expo median | p95 | p99 | max | max at rebalance | var share avg | var share max | guard fires | guard cost | guard tov/yr |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **D1** | 1 | exact | 38.70% | 97.53 | **624.6** | **-389.9** | 83.4% | **4.04%** | **10.66%** | 15.70% | 20.91% | 20.91% | 15.1% | 34.8% | - | - | - |
| **B0** | 21 | exact | 78.29% | 9.43 | **62.4** | **+82.1** | baseline | 6.56% | 21.71% | 29.35% | 47.86% | 14.60% | 17.2% | 61.1% | - | - | - |
| **G3** | 21 | exact | 79.07% | 14.10 | 93.4 | +74.5 | 92.9% | **1.00%** | **2.90%** | 6.85% | 14.72% | 14.72% | 16.1% | 46.4% | 255 (46%) | 30.3 | 4.58 |
| **G5** | 21 | exact | 78.95% | 13.41 | 88.7 | **+96.4** | 94.2% | 2.17% | 4.72% | 6.85% | 14.66% | 14.66% | 16.1% | 46.9% | 139 (25%) | 25.7 | 3.91 |
| **B0H** | 21 | cap_then_rehedge | 78.23% | 9.42 | 62.1 | +44.9 | 96.2% | 6.56% | 19.51% | 27.20% | 43.10% | 15.31% | 12.4% | 32.5% | - | - | - |
| **G3H** | 21 | cap_then_rehedge | 78.98% | 14.03 | 92.6 | +38.3 | 88.3% | 1.02% | 2.93% | 7.62% | 15.20% | 15.20% | 11.7% | 33.7% | 257 (46%) | 29.8 | 4.52 |
| **G5H** | 21 | cap_then_rehedge | 78.93% | 13.15 | 86.7 | +48.0 | 91.0% | 2.18% | 4.76% | 7.68% | 15.30% | 15.30% | 11.8% | 34.1% | 132 (24%) | 23.8 | 3.64 |

`alpha` is the held book's realised alpha against the fresh-target alpha, relative to
B0 (the frozen study's convention). `guard cost` is the trading cost the guard itself
adds, in bp/yr; `guard tov/yr` is its turnover. Fires are counted against the 558 hold
days.

### Net at the design anchor (169 bp gross)

`net = 169 - cost - borrow x (rate / 2%)`, the same restatement
`churn_followup.md` uses.

| variant | cost bp | net at borrow 0.5% | net at borrow 2.0% |
|---|---|---|---|
| B0 | 62.4 | **+81.2** | +5.1 |
| D1 | 624.6 | **-480.6** | -555.5 |
| G3 | 93.4 | +50.4 | -25.3 |
| **G5** | 88.7 | **+55.1** | -20.5 |
| B0H | 62.1 | **+81.5** | +5.4 |
| G3H | 92.6 | +51.2 | -24.4 |
| G5H | 86.7 | +57.2 | -18.4 |

## Is monthly + guard better than daily, and at which threshold?

**Yes, decisively, and the answer does not depend on the borrow rate.** Daily
rebalancing turns the book over 97.5 times a year for 624.6 bp of trading cost and nets
-481 bp at the anchor; the monthly variants turn over 9.4-14.1 times for 62-93 bp. The
guard is the whole of the monthly premium: it costs 26.3 bp at 5% and 31.0 bp at 3%,
takes 3.6-4.6 of the ~14 annual turns, and buys a p95 worst-factor exposure of 4.72%
(G5) or 2.90% (G3) against B0's 21.71% and D1's 10.66%. **5% is the better default**:
it is 4.7 bp cheaper than 3%, keeps 1.3 more points of alpha, and lands inside the
measured noise floor - a freshly built book already carries a ~3.7% median exposure to
tonight's row because it is hedged to tomorrow's - whereas the 3% bound is *below* that
floor, which is why it fires on 46% of hold days rather than 25% and only gets the
median to 1.00% by re-solving against the row it is measured with. Choose 3% only if
3% is a hard risk limit and ~30 bp/yr plus 1.3 points of alpha is an acceptable price
for a p95 of 2.90%. One number in that table is worth reading twice: the largest
exposure either guard ever shows - 14.7% - is the **rebalance-day** value, taken
immediately after the monthly rebalance and removed at the next close, and it is what
sets `max`. The guards bound the drift between rebalances, not the construction.

**D1's own exposure is not zero.** A daily book is hedged to the next session's row and
measured against tonight's, so it carries a one-session basis: median 4.04%, p95
10.66%, max 20.91% - and its max is its own rebalance-day value, i.e. even a same-day
re-solve leaves ~4% typical and up to 21% on the worst day. So daily does not buy
neutrality; it buys a lower tail at 10x the cost.

**The correction to the frozen study is in the guard's price, not its direction.** The
frozen panel priced the guard at +8.6 bp/yr and 1.3 turns, because on a month-end-only
artifact the book is exactly neutral on every day the artifact does not change. On a
panel that refreshes nightly the same guard costs **25.7-30.3 bp/yr and 3.6-4.6 turns**
- three to three and a half times more - and it now fires on a quarter to a half of all
hold days.

## Caveats

1. **Clean versus raw.** The panel is built on the `EFB_DESIGN_RETURNS=clean` returns
   branch, because that is the branch the frozen rows this panel is validated against
   were fitted on. Live runs **raw**: `efb/race.py::design_returns` treats unset and
   `raw` alike and says in its own docstring that `clean` "is not the default until the
   owner asks for it". The two panels produce a different cross-section and a different
   kept book (`efb/race.py`'s comment records 171 -> 186 names on one window), so the
   **absolute levels here may shift if live is measured on raw loadings; the ranking
   and the guard's cost relative to B0 should not**, because every variant reads the
   same panel and the same cost model.
2. **P&L levels are indicative.** The universe is frozen at 2026-09-18 and applied to
   the past, so survivorship is in the levels; the cross-variant comparison is the
   result.
3. **The one-session basis is in every number.** The hedge is built for the session the
   book earns and the exposure is measured against the row dated the close, which is
   the live shape and leaves ~3.7% median for a fresh book. A guard threshold below
   that floor is partly chasing the basis, not drift.
4. **The guard's projection is a pure hedge, not a rebalance.** It trades the
   minimum-norm change that zeroes the measured exposures and touches nothing else, so
   its turnover is hedge turnover. Whether the owner wants the book's *positions*
   moved that way on a hold day is a policy question this study does not answer.

## Reproducing

The scripts that follow are in `archive/research-daily-design`, not on `main`; restore the
tag into a worktree first.

```bash
git worktree add ../efb-daily-design archive/research-daily-design     # from the main checkout
cd /Users/amankesarwani/PycharmProjects/efb-daily-design
set -a; source ../equity-factor-book/.env; set +a
EFB_DESIGN_RETURNS=clean python scripts/build_daily_design_panel.py --root /tmp/churn/daily   # 21.6 min
EFB_DESIGN_RETURNS=clean python scripts/validate_daily_panel.py --root /tmp/churn/daily       # checks (a) and (b)
# install the nightly rows as descriptors.parquet, per the snippet at the top of this file
EFB_DESIGN_RETURNS=clean python scripts/daily_design_study.py run \
  --root /tmp/churn/daily --out docs/research/daily_design_study.json                        # 80 min
```

`D1` alone is 60 minutes of that (586 re-solves); the rest are 3 minutes each. The
partial file `/tmp/daily_design_study_rows.partial.json` makes the run resumable and is
keyed on the `--out` stem, so delete it (or change the stem) before a run that must not
reuse old rows.

## Validation of the panel

- **(a) rebuilt month-ends against the frozen published rows**, 29 sessions, 502 names
  on every one: max abs difference `size 0.0`, `beta 3.1e-15`, `momentum 2.7e-15`,
  `reversal 4.4e-15`, `resid_vol 1.4e-13`, `liquidity 4.5e-15`; no day over 1e-06.
  **Pass.**
- **(b) against `efb.e11_descriptors`, 2026-09-04..2026-10-02** (20 dates, 59,680
  cells): median |diff| 0.0080, max 2.16 (momentum), per-descriptor medians 0.0037
  (liquidity) to 0.0153 (reversal). **This is a cross-tree comparison and it does not
  agree.** The study copy is a 2026-10-03 snapshot and the store rows were built by the
  live tree from live data; the underlying returns differ on exactly those dates (max
  |delta r| 6.0e-05 on 2026-09-29 but 1.48e-02 on 09-30 and ~1.0e-02 on 10-01/10-02,
  tens of names per close), and the copy has 811 raw names against the live tree's 830.
  Check (a), which is same-tree and same-code, is the one that validates the panel.

## What this does not settle

- Whether the owner should run `EFB_DESIGN_RETURNS=clean` live (open question carried
  from `docs/owner_fixes/HANDOFF.md`).
- The borrow rate. Every monthly variant is negative at the anchor at 2% borrow and
  positive at 0.5%; `efb/costs.BORROW_RATE` is 2%, and the churn follow-up's C5 is the
  place that question belongs.
- Whether a monthly book with a 5% guard beats the current daily production
  configuration on *net alpha* rather than on this frozen-universe cost model.
