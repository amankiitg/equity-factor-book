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

Ten sprints built, E12's engine opening. HEAD c263021. `make test` 595
passed; `make lint` clean; `make verify-evidence` clean.
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
  Six criteria after the corrections: F10.2, F10.2b and F10.3b pass, F10.1 and
  F10.3 fail, F10.1b passes on a criterion fitted to the answer and is with the
  owner. **RG-Operate is not cleared**: the constituent source is stood up but
  not applied. Closed 2026-09-22 after two review rounds and 27 findings.
  The SSGA SPY daily holdings file is the ongoing source: 503 equity rows with
  CUSIP and SEDOL, archived dated and protected in the evidence snapshot.
  iShares IVV is recorded as a failing source, gated behind a disclaimer.

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

## Decisions the owner has made

Settled 2026-09-22. These are no longer open; build on them.

- **E11 trades `idio_momentum` through the full stack**, Procedure 6.3 sizing
  plus the FMP hedge, documented as a null book. **Paper only.**
- **The 30-day clock restarts on live data, and static days do not count.**
  The 2026-09-22 start is void: the loop ran on the frozen 2026-09-03 close and
  would have produced thirty identical proposals. Prices, descriptors, factor
  returns, specific returns and both covariance artifacts all extend **daily by
  incremental append**, never a refit, with pre-2026-09-04 rows byte-identical.
  Every proposal stores the as-of date of all nine model inputs. The clock is
  held until a sanity gate runs two consecutive real closes and shows the
  proposals differ, with the weight turnover printed.
- **F10.1b is re-registered** against F10.1's original 10% bar, verdict `fail`,
  through a `revisions` block, with the mean-versus-median note.
- **The universe stays split.** Historical artifacts stay frozen on the pinned
  Wikipedia changes table; the SPY archive supplies the live universe from
  2026-09-18 forward. The full reconstruction is **not** scheduled: it would
  move every artifact and hash E1 to E10 and put F1.1, F1.5, F3.1, F3.6, F5.1
  and F5.2 at risk, including the champion, and it recovers no history. The
  seam between the two sources is documented and never silently bridged.
- **The v8.x daily loop is at `/Users/amankesarwani/PycharmProjects/credit-trading-lab`**:
  `execution/`, `dashboard/`, `scripts/`, `render.yaml`, `.streamlit/`,
  `sprints/v8.1` and `v8.6`. **Guidance, not a template.** Reuse its loop
  shape, its Option A governance and its fail-safes; do not inherit its
  dashboard design. Its own README carries a lesson E12 must inherit:
  fixed-entry P&L accounting is mandatory, because rolling residuals marked to
  market with drifting parameters produced up to $13M of phantom P&L there.

## How the two agents split

Since 2026-09-22: **DeepSeek executes and verifies everything.** The reviewer
reads reports, keeps this file current, helps the owner decide, and writes the
next task. Every REPORT.md ends with a `## Verification` section per STANDARDS
rules 19 and 20; a report without it comes back unreviewed.

## Reserved decisions

Only the project owner makes these. Set `handoff/TASK.md` to `blocked` with the
question and write it at the top of the LOG entry. Do not decide these and do
not work around them.

1. **Any change to what E11 trades, or any move from paper to real money.**
2. **Anything that declares or changes the champion.**
3. **Any change to a stored criterion outside a `revisions` block.**
4. **Deleting or rewriting evidence, artifacts or git history.**
5. **Anything touching real money or real broker credentials. Paper only.**

## Remaining plan

In order. Each numbered item is roughly one TASK.md or less.

1. ~~The E10 review fixes.~~ **Done 2026-09-22**, two rounds, 27 findings.
2. ~~The ongoing constituent source.~~ **Done 2026-09-22.** SPY is the source,
   archived and protected; IVV is a recorded failing source; sector stays on
   the live Wikipedia page. It fixes membership forward only and reconstructs
   no history, so RG-Operate item 5 is stood up but not yet positive: applying
   it means re-running the universe reconstruction, which is reserved.
2b. **E12's attribution engine on the seed books**, which depends on nothing
   live. In progress; brought forward from step 4 because steps 3 and 4 are
   blocked or waiting.
3. **E11 setup, then the 30-day clock. This is the critical path.** The daily loop is reused from the
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
