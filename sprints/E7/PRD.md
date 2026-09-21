# Sprint E7 PRD: Alpha Lab and Backtest Hygiene

Sprint E7, 2026-09-21. Tier 2. The sprint that answers the PM question
"does this signal contain information beyond the risks I already know about,
and after costs?"

## Research framing, copied verbatim from the roadmap

- Academic question: How is the information content of a signal measured, and
  how are the standard errors adjusted for the number of things tried?
- Practitioner question: Does this signal contain information beyond the
  factors I already know about, at a horizon I can trade, after costs?
- Research question: Do any of the candidate signals show factor-neutral,
  out-of-sample, cost-surviving information, and does a negative result change
  what the book does?

Objective. Build the harness that turns a signal into an expected return
honestly: information coefficients, decay, factor-neutral quantile returns,
the fundamental law check, and a multiple-testing ledger that records every
variant tried. No edge is claimed; the harness is the deliverable.

## Inherited constraints, all hard

1. The champion is provisional (F5.1 failed). Every signal's IC and every
   quantile spread are computed under the champion's idio volatility and
   under the alternative's, and the difference is stored (F7.4, new).
2. MODEL_START is 2011-01-03. The panel is the post-exclusion returns file;
   stale, outlier and interior-NaN rows are excluded and the counts printed.
   The survivor-only sector-mapped universe caveat is stated once.
3. The explicit missing-data semantics from E5 apply everywhere: no silent
   zero for a missing weight, exposure or signal value.
4. The FMP machinery from E6 is the only neutralization mechanism: factor
   neutrality is the exact in-model projection s_perp = s - X (X'X)^-1 X' s,
   and the capped stored FMPs are reported as their own variant, never
   substituted silently (their cap drift is stored from E6).
5. A stored criterion is never reworded. F7.1 to F7.3 are copied verbatim
   from `docs/roadmap_v2.md`. New findings take new IDs.
6. No number in any walkthrough or deliverable is typed by hand. Every signal
   report ships a traceability test.
7. Medians and win counts rather than means wherever a distribution is
   skewed.
8. Evidence snapshots cover every new artifact a criterion is scored on.
9. Short interest (FINRA) and post-earnings drift are admitted only if their
   data probes print rows first; a probe that prints nothing records the
   signal as unavailable in the ledger, not as NULL.
10. The multiple-testing ledger is append-only: every variant tried is a row,
    including variants that failed, and the row count is a stored number.

## Pre-registered falsification criteria

F7.1, F7.2 and F7.3 are the roadmap's, copied verbatim.

| ID | criterion | threshold |
| --- | --- | --- |
| F7.1 | Shift audit: moving every signal forward by one day flips or kills its IC. This proves the absence of leakage. | every signal's one-day-forward IC is not significant in the direction of the unshifted IC |
| F7.2 | Factor-neutral momentum IC mean above 0.02 with t above 2, reported separately in-sample 2010 to 2020 and out-of-sample 2021 to 2026. | neutralized momentum IC mean > 0.02 and t > 2, both periods stored |
| F7.3 | Any signal failing the out-of-sample deflated-Sharpe hurdle is labeled NULL in the ledger, and the ledger contains at least as many rows as signal runs executed. | every below-hurdle signal labeled NULL; ledger rows >= runs |
| F7.4 | New in E7: every signal's IC under the champion's idio volatility and under the alternative's, with the difference stored. | stored per signal, both models |

## The harness, formulas with inputs and outputs labeled

- Information coefficient: IC_t = rank-correlation(s_{t-1}, r_t), a Spearman
  rank correlation cross-sectionally per day. INPUT: signal s dated t-1,
  returns r dated t. OUTPUT: the daily IC series and its t-statistic with
  the Newey-West correction.
- Decay: the same correlation at horizons 1, 5, 21 and 63 days.
  INPUT: s dated t, forward returns at each horizon. OUTPUT: the decay curve.
- Factor neutralization: s_perp = s - X (X'X)^-1 X' s with X the
  cross-sectional design of the champion model at that date.
  INPUT: signal, design. OUTPUT: the neutralized signal and the raw-versus
  neutralized comparison.
- Quantile portfolios: names sorted on s_perp into five buckets, rebalanced
  on the E5 race grid, hedged with the E6 FMP machinery. INPUT: neutralized
  signal, grid. OUTPUT: quintile returns, spread, turnover, hit rate.
- Fundamental law: IR = IC x sqrt(N_effective), where N_effective is the
  stored effective breadth, compared with the realized IR of the quantile
  spread. INPUT: IC series, breadth. OUTPUT: the two IRs side by side.
- Multiple testing: the Bonferroni t-threshold for M variants, the deflated
  Sharpe ratio, and the Harvey-Liu-Zhu hurdle |t| > 3.
  INPUT: the ledger's M, each variant's Sharpe. OUTPUT: deflated Sharpe and
  the hurdle verdict per variant.
- Alpha conversion (the E8 input contract): alpha_i = IC x sigma_idio,i x z_i,
  shrunk by kappa toward zero. INPUT: IC, the champion's idio volatility,
  the z-score, the shrinkage. OUTPUT: `data/alpha/{signal}/alpha.parquet`
  with columns date, ticker, alpha, ic, sigma_idio, z, kappa stored
  explicitly.

## Signals

Momentum 12-1, short-term reversal, idio momentum on XS-v1 residuals, low
residual volatility; short interest and post-earnings drift only if their
probes print rows first.

## Regime conditioning

Every signal's IC is reported within VIX terciles, so a signal that only
works in calm markets is labeled as such rather than pooled.

## Deliverables

- `efb/alpha.py`, `efb/hygiene.py`
- `data/alpha/{signal}/{ic,decay,quantiles,alpha}.parquet`
- `docs/multiple_testing_ledger.md` (append-only)
- `docs/research/E7_signal_{name}.md`, one per signal, each with a
  traceability test
- `sprints/E7/RESULTS.json`
- Dashboard tab D6 Alpha Lab
- `notebooks/E7_walkthrough.ipynb`, rendered and published
- `make rebuild-e7`, `make rebuild` extended to E1 through E7

## The RG-Signal gate, asked verbatim after the sprint

1. Is the hypothesis clearly defined, with an economic reason the information
   should exist?
2. Is the data behind the signal reliable and point-in-time (E1 ledger flags)?
3. Does the basic empirical relationship exist in-sample, factor-neutral?
4. Does it survive simple out-of-sample testing (2021 to 2026) and the
   deflated-Sharpe hurdle?
5. Are the results economically meaningful after a rough cost estimate
   (break-even cost above realistic cost)?
6. Are the results robust to universe definition, weighting scheme and
   horizon?
7. Is there a plausible implementation path (turnover, capacity, whole
   shares)?

Each signal is labeled PASS or NULL against this checklist. Every signal
NULL is a successful sprint: the E8 construction machinery then runs on
synthetic alpha with a known IC.

## Book connection

EQI Ch8 (evaluating excess returns, backtesting, data snooping); APM Ch6
(expected returns as the sizing input) and Appendix (momentum, short
interest). What the implementation teaches that the book cannot: how quickly
results evaporate under hygiene, and that the harness, not the signal, is the
asset.

## What would falsify the sprint's conclusion

- Unstable or period-dependent IC; weak out-of-sample IC; IC that vanishes
  after neutralization.
- Excessive turnover relative to decay; break-even cost below realistic
  costs.
- Sensitivity to universe or weighting choices; a deflated Sharpe below the
  hurdle.
