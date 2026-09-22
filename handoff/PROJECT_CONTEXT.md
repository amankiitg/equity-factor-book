# EFB project context

Both agents read this first, every turn. Reviewer owns this file; DeepSeek does
not edit it. Changes to it get a `handoff/LOG.md` entry saying why.

Companion files: `handoff/STANDARDS.md` (the standing rules), `handoff/TASK.md`
(the current unit of work), `handoff/LOG.md` (reviews, append-only),
`handoff/REPORT.md` (DeepSeek's report on the current task).

## Purpose

A learning instrument that builds every component of Paleologo's *Advanced
Portfolio Management* and *The Elements of Quantitative Investing* on free
equity data, and the template for porting the same machinery to corporate
credit. E13 is that port design, a document only.

It builds the machinery, not an edge. A profitable strategy is not required and
a negative result is a complete outcome. Each sprint bridges academic and
practitioner: three research questions, a PM question, pre-registered
falsification criteria with numeric thresholds written before the numbers exist,
and a research deliverable in `docs/research/` written for a senior quant or
risk manager. A concept implemented without the practitioner interpretation and
the written artifact is a textbook exercise.

Thirteen sprints in three tiers, with three research gates: RG-Data (end of E1),
RG-Signal (end of E7), RG-Operate (end of E10, before the book runs). A gate
that returns a negative answer has done its job.

## State

Ten sprints built. HEAD 5b77d6f. `make test` 586 passed; `make lint` clean.
Five model versions in `data/models/registry.json`; XS-v1 is champion, TS-v1 is
diagnostic only and ineligible. Dashboard tabs D0 to D9 exist; D10 and D11 do
not. `data/VERSION.json` hashes 143 artifacts at
`810a1ef6`. `live/` is empty apart from `.gitkeep`.

Verdicts and headline numbers, all from `sprints/E*/RESULTS.json`:

- **E1** universe, returns, Hygiene Ledger, perf library. Gate RG-Data. F1.3
  passes; F1.1, F1.2, F1.4, F1.5 fail. Survivorship: 44.79% of deleted members
  have recoverable history against a 70% bar, and the naive backtest of current
  members earns **365.10 bp a year** over a point-in-time universe (F1.5).
  Coverage of all requested tickers 77.16% against a 95% bar (F1.1).
- **E2** time-series models, volatility, TS-v1. Seven pass, four fail. The
  volatility horse race failed and was accepted: GARCH beats trailing 252d on
  out-of-sample QLIKE for 58.16% of names and EWMA(0.94) for 35.40%, against a
  60% bar (F2.3), so production stayed with the decay 0.97 estimate. F2.6b found
  **36 reused ticker symbols** among 373 names on the removed list.
- **E3** cross-sectional model, Fama-MacBeth, FMPs, XS-v1. Gate G1. Eight pass,
  F3.6 fails. Mean daily cross-sectional R squared **0.32945** over 3,941 days
  (F3.1); FMP identity to 1.2e-13, identification to 7.0e-18. F3.6: the
  equal-weight book's bias is 0.9570, in band, and the momentum book's is
  **0.6664**, below the 0.8 floor, so XS-v1 cannot yet size that book.
- **E4** statistical models, covariance lab, PCA-v1 and PCA-v1c. Five pass, F4.1
  and F4.4 fail. PC1 correlates with the market factor at 0.7970 (PCA-v1) and
  0.9306 (PCA-v1c) against a 0.95 bar; the Marchenko-Pastur edge isolates **13**
  significant factors. F4.6 measured the survivor distortion: the size factor
  correlates only **0.5778** between the full and mapped universes.
- **E5** risk model evaluation, regimes, champion. Three pass, F5.1 and F5.2
  fail. **F5.1 failed, so the champion is provisional**: no version is inside
  0.9 to 1.1 across all portfolio families (XS-v1 1.0470, XS-v2 1.0385). XS-v1
  is champion under the pre-registered rule. Stress haircut **1.8471**, recovery
  13 trading days from 2020 Q1 (F5.4).
- **E6** hedging. All seven pass. The exact in-model FMP hedge drives the worst
  factor exposure to **5.83e-15** and the idio share to 1.0, at 461.9 names
  traded per rebalance (F6.1). The as-stored quarterly capped FMPs are not a
  hedge: worst residual exposure 0.7552, worse than unhedged.
- **E7** alpha lab, multiple-testing ledger. Gate RG-Signal. Four pass, F7.2 and
  F7.1b fail. **All six signals are NULL at RG-Signal.** F7.2: factor-neutral
  momentum IC is **-0.010684 with t -1.549** against a bar of 0.02 and t 2.
  Beware two different verdicts in this sprint: `RG_SIGNAL.json` (the seven
  question checklist, decided on factor-neutral out-of-sample t) says NULL for
  all six, while F7.3's `verdict_by_signal` (the deflated-Sharpe ledger label on
  the raw spread) reads PASS for momentum_12_1 and idio_momentum. The gate
  verdict is the binding one.
- **E8** sizing, Procedure 6.3, constraints. Gate G3. Six pass, F8.1 and F8.4
  fail. F8.1b passes at **6.42e-17**: with alpha GLS-neutralized in the D^-1
  metric, unconstrained mean-variance, the proportional rule and Procedure 6.3
  are the same vector. The constrained optimizer's worst violation is 3.95e-09
  with **zero solver fallbacks** (F8.3).
- **E9** transaction costs, capacity. Two pass, F9.1 and F9.2 fail, **F9.3 is
  not evaluable**. F9.1 fails on a mechanism worth knowing: net mean return does
  decline monotonically in AUM, but net Sharpe does not, because the impact
  cost's cross-rebalance variance inflates the denominator. F9.2: turnover cut
  37.55% against a 50% bar, at an ex-ante IR loss of 6.49%.
- **E10** Kelly, vol targeting, stop-loss, drawdowns by regime. Gate RG-Operate.
  F10.2 passes; F10.1 and F10.3 fail. **RG-Operate is not cleared**: the ongoing
  constituent source is negative and blocks E11. Under review as of 2026-09-21;
  nine defects found, see the LOG entry of that date. The failing verdicts
  survive review; the arithmetic and the recorded mechanisms behind them do not.

## Standing findings

Later work must respect these. They are measured, not assumed.

1. **The historical cross-section is survivor-only.** The sector file maps only
   the 502 current members, so the historical cross-section contains only
   companies in the index today. Survivorship bias is about **366 bp a year**.
   Size and liquidity are distorted by it: the size factor correlates **0.578**
   between the full and mapped universes (F4.6). Owned by E4, not fixable on the
   current data.
2. **A ticker symbol is not an identity.** 36 reused symbols are excluded; 33
   left the estimation panel and 3 were restored with truncated history. Prices
   attach to symbols, not issuers, and the fix needs a security-identity source.
3. **The champion XS-v1 is provisional.** F5.1 failed: no model is calibrated
   across all portfolio families. Stress haircut **1.8471**. XS-v2, the residual
   covariance version, lost narrowly despite four E4 measurements supporting
   residual structure. Declaring or changing the champion is a reserved decision.
4. **All six signals are NULL at RG-Signal.** Their raw ICs are the known
   factors. Post-earnings drift's horizon-1 IC was announcement leakage, caught
   by F7.1c: its IC falls from 0.1240 to 0.0073 under the extra-day lag.
5. **Synthetic alpha uses future returns by construction.** It is a controlled
   experiment, never a backtest, and it can never trade live. The synthetic
   label travels with every number computed from it.
6. **Equity costs are an assumption, not a measurement.** A size-decile schedule
   of 1 to 10 bp half-spread, with a half and double sensitivity, because free
   daily OHLC cannot measure spreads for S&P 500 names. This is why F9.3 is
   recorded not evaluable rather than failed.
7. **Breadth.** IR is IC times sqrt(N) when forecast errors are independent, and
   IC times sqrt(N_eff) when they co-move the way residual returns do. Measured:
   **N_eff about 140 against N about 460** (F8.7: 139.89 and 461.89).
8. **Several criteria failed by construction** because the threshold was written
   before the object existed: F4.1, F7.2, F8.4, and F9.3 is not evaluable. They
   are recorded with their mechanisms and are never reworded. Neutralizing
   momentum against a risk model that contains momentum projects the signal out;
   that is F7.2's mechanism and it matters for the E11 decision.

## Reserved decisions

Only the project owner makes these. Set `handoff/TASK.md` to `blocked` with the
question and write it at the top of the LOG entry. Do not decide these and do
not work around them.

1. **What E11 trades.**
2. **Anything that declares or changes the champion.**
3. **Any change to a stored criterion outside a `revisions` block.**
4. **Deleting or rewriting evidence, artifacts or git history.**
5. **Anything touching real money or real broker credentials. Paper only.**

## Remaining plan

In order. Each numbered item is roughly one TASK.md or less.

1. **The E10 review fixes.** F10.1's sign and horizon, F10.3's estimator
   frequency, and the seven other defects in the 2026-09-21 LOG entry. Verdicts
   do not change.
2. **The ongoing constituent source**, iShares IVV or SSGA SPY daily holdings.
   This clears the blocking RG-Operate item. Assessed 2026-09-21: SPY fetches
   clean and carries CUSIP and SEDOL; IVV is behind a disclaimer and bot gate
   and returns HTTP 200 with HTML; sector still comes from the live Wikipedia
   page. Neither fund archives past files, so this fixes membership forward
   only and reconstructs no history.
3. **The E11 decision, then E11 setup.** The daily loop is reused from the
   owner's earlier Credit Trading Lab v8.x: evening proposal, morning execute,
   Alpaca paper, Render cron, Supabase state, Option A governance, two fail-safe
   guards. **That code is not in this repository** (`live/` holds only a
   `.gitkeep`). Ask the owner where it lives before assuming anything about it.
   E11 needs **30 trading days of calendar time**, so the clock starts as early
   as possible once the decision is made.
4. **While E11 accumulates days**, two things that depend on nothing live:
   build E12's attribution machinery and test it on the seed books' historical
   returns, so E12 is a run rather than a build on day 30; and write E13, the
   credit port design note, a document only.
5. **E12 on the live data** after 30 trading days.

## Working lessons

- **One TASK.md is one sprint or less.** Implementer sessions run out of working
  budget, and chained sprints stop mid-task.
- **Every real defect so far was found by reading an output, not the code**: two
  rows identical, a magnitude off by 100x, a sign mix, a result too clean. The
  E10 review is the same story: the code reads fine and the numbers are
  reproducible; what is wrong is what they measure. Review outputs.
- **Never rebuild an artifact a stored criterion was scored on without
  preserving it first.** E5 lost the published XS-v1 covariance race row that
  way, and it is not reproducible from any derivation.
- **Never rerun a full sprint build to add one artifact.** Use the
  `make rebuild-e<n>` target.
- **A stop condition exists only for irreversible or plan-changing events.**
  Everything else the implementer decides and records in `handoff/REPORT.md`.
- **Mechanistic explanations with worked numbers**, inputs and outputs labeled.
  A claim about a mechanism is checked against a measurement before it is
  written down; a recorded mechanism that a control contradicts is itself a
  defect, even when the verdict above it is right.
- **No em dashes anywhere**, including files under `handoff/`.
