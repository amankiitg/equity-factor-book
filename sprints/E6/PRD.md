# Sprint E6 PRD: Hedging

Sprint E6, 2026-09-20. Tier 2. The sprint that answers the PM question
"how much unwanted beta can I remove, and what does the hedge cost me?"

## Research framing, copied verbatim from the roadmap

- Academic question: What is the minimum-variance hedge of a portfolio under a
  factor model with a restricted set of tradeable instruments, and how does it
  relate to the factor-mimicking portfolios?
- Practitioner question: How much unwanted beta and factor exposure can I remove
  with instruments I can actually trade, and what does the hedge cost in
  turnover, borrow and basis risk?
- Research question: Do model-implied hedges reduce realized factor P&L of the
  seed books, and how does hedge efficacy decay between rebalances?

Objective. Neutralize the factors you do not want and keep the idio you do:
beta hedges, factor-neutral hedges via FMPs, minimum-variance hedges with a
restricted instrument set, partial hedges, and the cost of each.

## Inherited constraints, all hard

1. The champion is provisional, and this is the single most important inherited
   fact. XS-v1 won the rule at mean |bias-1| 0.0607 against XS-v2's 0.0672, but
   F5.1 failed: no version is calibrated inside 0.9 to 1.1 across all four
   portfolio families. Every headline hedge result is reported twice, once
   under the champion (XS-v1) and once under the alternative model (XS-v2, the
   best-calibrated XS variant on the long-only family), and the difference is
   stored as a number. The champion decision is not re-opened.
2. MODEL_START is 2011-01-03. The panel is the post-exclusion returns file;
   stale, outlier and interior-NaN rows are excluded and the counts printed.
   The survivor-only sector-mapped universe is stated once.
3. The two seed books from E2 and E3 carry forward unchanged, so the seed
   numbers stay comparable across sprints.
4. The explicit missing-data semantics from E5's 0 times NaN defect apply
   everywhere: no silent zero for a missing weight or a missing exposure.
5. A stored criterion is never reworded. F6.1 to F6.3 are copied verbatim from
   `docs/roadmap_v2.md`. New findings take new IDs.
6. No number in any walkthrough or deliverable is typed by hand. The deliverable
   ships a traceability test of the `tests/test_e5_memo.py` kind.
7. Medians and win counts rather than means wherever a distribution is skewed.
8. Evidence snapshots cover every new artifact a criterion is scored on.

## Pre-registered falsification criteria

F6.1, F6.2 and F6.3 are the roadmap's, copied verbatim.

| ID | criterion | threshold |
| --- | --- | --- |
| F6.1 | Full FMP hedge drives every factor exposure below 1e-6 in absolute value and lifts the idio share of variance above 95%. | max absolute exposure < 1e-6 after the FMP hedge; idio share > 0.95 |
| F6.2 | ETF minimum-variance hedge removes more than 70% of the factor variance of the long-only seed book. ETFs cannot span every factor; the residual is reported. | factor variance removed > 70% for seed_ew under the ETF min-variance hedge |
| F6.3 | Realized: the hedged momentum long/short book has a beta to Mkt-RF within plus or minus 0.1 over 2018 to 2026. | realized beta of the hedged seed_mom_ls in [-0.1, 0.1] |
| F6.4 | New in E6: every headline hedge result is reported under the champion and under the alternative model, with the difference stored. | stored, both models, the difference present |
| F6.5 | New in E6: the residual factor exposure the instrument set cannot reach is quantified per factor, since SPY and sector ETFs do not span momentum or size. | stored per factor per book |

## The hedge toolkit, formulas with inputs and outputs labeled

- Beta hedge, the one-instrument case: h = -beta_p units of SPY per dollar of
  book, where beta_p = cov(r_book, r_SPY) / var(r_SPY) over the trailing 252
  sessions. The partial hedge is h = -c beta_p for c in [0, 1].
  INPUT: book returns, SPY returns. OUTPUT: h, residual tracking error.
- FMP hedge: x = X'w, the book's factor exposures; the hedge subtracts
  sum_k x_k times FMP_k, the k-th factor-mimicking portfolio stored in
  `data/models/XS-v1/fmp_weights.parquet`. Exact in-model, expensive in names,
  so its name count and turnover are reported.
  INPUT: exposures X'w, FMP weights. OUTPUT: hedge weights per name, name
  count, turnover, residual idio share.
- Restricted minimum-variance hedge: h* = -(H' Sigma H)^-1 H' Sigma w with H
  the tradeable set (SPY, IWM, QQQ, the sector SPDRs), under the champion Sigma
  and under the alternative Sigma, with the residual variance
  w' Sigma w - w' Sigma H (H' Sigma H)^-1 H' Sigma w reported.
  INPUT: champion or alternative Sigma, instrument betas to the model factors.
  OUTPUT: h*, residual variance, factor variance removed.
- Hedge cost = turnover times a provisional cost model plus borrow on short
  instruments. Parameters, stated here as the E9 provisional constants: 5 bps
  per unit of hedge turnover, borrow 2.0 percent per year on short notional.
  The parameters and their source are stored with every cost number.

## Efficacy

Efficacy is measured on realized factor P&L, not on in-model exposures alone:
the hedged seed books' realized factor P&L and realized beta to Mkt-RF are
reported, and efficacy against rebalancing frequency (5, 21, 63 sessions) is a
stored curve, not a claim.

## Deliverables

- `efb/hedge.py`, `data/hedge/{portfolio}_{method}.parquet`,
  `data/raw/etf_prices.parquet`
- `sprints/E6/RESULTS.json`
- `docs/research/E6_hedge_study.md` with its traceability test
- Dashboard tab D5 Hedging Lab
- `notebooks/E6_walkthrough.ipynb`, rendered and published
- `make rebuild-e6`, `make rebuild` extended to E1 through E6

## Book connection

APM Ch4 (beta hedging), Ch7 (managing factor risk); EQI Ch12 (hedging). What
the implementation teaches that the book cannot: the spanning limits of
tradeable instruments, and that a hedge is a forecast and decays.

## What would falsify the sprint's conclusion

- The hedged book's realized beta is not near zero: the model exposures or the
  hedge ratios are wrong.
- Hedge cost exceeds the variance removed in value terms: the hedge is not
  worth it and the deliverable says which exposures to leave.
- Hedge ratios unstable day to day: the exposure forecast is too noisy to act
  on daily; weekly hedging is recommended.
