
Equity Factor Book

Build Roadmap v2: learn the theory in Paleologo's APM and EQI, build the machinery, and develop the judgment to run a systematic book
This roadmap takes the Equity Factor Book (EFB) from raw prices to a hedged, sized, cost-aware, paper-traded long/short book with ex-post attribution, in thirteen sprints, and then designs the port to credit. Version 2 keeps the sprint structure, the numbering, the dates, the dashboard architecture and the prompts of version 1, and adds a bridge on every sprint between the academic concept and the portfolio decision it serves. The project is deliberately academic enough to learn each concept properly, and deliberately practitioner-facing enough that every concept ends in a question a PM would ask and an artifact a senior quant could read.

Committed milestone: Gate G1, Sunday September 20, 2026. Sprints E1 to E3 running end to end. Every later date is indicative and is re-planned at each gate.

Prepared September 1, 2026. Supersedes v1 of the same date.

The learning loop
Concept -> Intuition -> Academic formulation -> Implementation -> Empirical test -> Practitioner interpretation -> Research artifact. Every important concept in the two books passes through all seven steps; a concept that is implemented without the last two steps is a textbook exercise, and a concept that is skipped because it is not immediately profitable is a hole in the model.

Four principles, unchanged from v1, plus one
Build the machinery, not an edge. No signal is claimed to have an edge; a profitable strategy is not required for the project to succeed, and negative research results are legitimate outputs.
Every data claim is a hypothesis until a probe script prints the rows. Carried from the Credit Trading Lab.
Versions, not overwrites. Model versions in a registry with data hashes; the champion chosen by a rule written before the numbers.
Walkthrough before promotion. Numbers reproduced by hand on three names, every symbol labeled input or output.
New in v2: a negative result is a successful research outcome if it prevents a bad investment decision. Each sprint says in advance what would falsify it, and the research gates let the project record a null and move on rather than engineer around it.

Revision notes: v1 to v2
The assessment that produced this revision, kept here so the reasoning is auditable.
Already strong academically in v1
E2 to E5: estimation theory with standard errors, shrinkage, PCA and the Marchenko-Pastur edge, bias statistics; the walkthrough discipline that forces derivation by hand.
Already strong for a practitioner in v1
Probe scripts, the Hygiene Ledger, the registry and version selector, pre-registered falsification with numeric thresholds, Option A governance in the book, the credit port table.
Where v1 risked becoming a textbook exercise
E4 (an estimator zoo with no decision attached), E6 and E10 (techniques listed without the PM question they answer), and E3, which ran the cross-sectional regression without naming Fama-MacBeth or asking what the premia mean.
Where v1 was too implementation-heavy
Every sprint ended in parquet and a dashboard tab rather than a research artifact; E7 could become signal engineering with no gate before construction; E11 was pure infrastructure.
Changes made in v2
Every sprint opens with three research questions (academic, practitioner, research) and carries: concept and intuition, foundation, empirical tests and failure modes, Why This Matters to a PM, What Would Falsify This, a research deliverable, and a book connection. Academic vs practitioner contrasts appear where they teach something (E1 to E5, E7, E8).
Fama-MacBeth premia with Newey-West t-stats, descriptor orthogonalization and residualization added to E3 (F3.7); regime analysis added to E5 (F5.4), E7, E10 and E12; turnover and implementation constraints made explicit in E8 and E9.
Three research gates: RG-Data (end of E1), RG-Signal (end of E7, before construction and the book), RG-Operate (before E11). RG-Signal has a synthetic-alpha fallback so a null signal result still validates the construction machinery.
A learning-progression table mapping sprints to the transition from student to researcher to portfolio and risk researcher to systematic practitioner.
Every /quant-prd prompt now carries the research questions and demands the research deliverable; the generic walkthrough template ends with the deliverable's evidence section.
Nothing removed: the 13 sprints, numbering, G1 date, dashboard tabs D0 to D11, registry schema, coverage map and prompts are preserved.
Sprint plan at a glance
Sprint
Dates
Tier
Theme
Tab
Gate
E1
Sep 1 to 6
1
Universe, returns, Hygiene Ledger, perf library
D0
RG-Data
E2
Sep 7 to 13
1
Time-series factor models, volatility, TS-v1
D1
E3
Sep 14 to 20
1
Cross-sectional model, Fama-MacBeth, FMPs, Sigma, risk decomposition, XS-v1
D2
G1 Sep 20
E4
Sep 21 to 27
2
Statistical models (PCA), covariance estimator lab, PCA-v1
D3
E5
Sep 28 to Oct 4
2
Risk model evaluation, bias statistics, regimes, champion
D4
G2
E6
Oct 5 to 11
2
Hedging: beta, FMP, min-variance, partial
D5
E7
Oct 12 to 18
2
Alpha Lab, IC, backtest hygiene, multiple-testing ledger
D6
RG-Signal
E8
Oct 19 to 25
2
Sizing rules, Procedure 6.3, mean-variance, constraints, robustness
D7
G3
E9
Oct 26 to Nov 1
3
Transaction costs, turnover, t-cost-aware optimizer, capacity
D8
E10
Nov 2 to 8
3
Kelly, vol targeting, stop-loss efficiency, drawdowns by regime
D9
RG-Operate
E11
Nov 9 to 22
3
The Book: daily L/S paper trading (v8.x loop reused)
D10
E12
Nov 23 to 29
3
Ex-post attribution, skill vs luck
D11
E13
December
3
Credit port design (document only)
Method.
Tiers
Tier 1 (green), committed: E1 to E3, the September 20 gate. Fixed dates. If a week slips, cut optional tasks inside the sprint, never the date.
Tier 2 (purple), planned: E4 to E8, the risk-model and construction stack. Dates indicative; re-plan at G1 with the actual E1 to E3 velocity.
Tier 3 (amber), conditional: E9 to E13, scheduled around the Bracebridge start and the move. If time runs out, E9 and E10 reduce to their research deliverables on the seed book; E11 needs the 30-day window so it starts as soon as RG-Operate clears; E12 needs E11; E13 is writing.
Learning progression
The project is a gradual transition, not a set of implemented papers. At the end of each stage you should be able to answer the questions in the right-hand column without notes.
Sprints
Stage
What you can explain at the end
E1, E2
Quant finance student to quant researcher: learn the theory, build the machinery
Which return definition a covariance matrix wants; why a Sharpe needs a standard error; why a beta of 1.3 and 1.1 are often the same number; what a residual is and why everything later sizes on it
E3, E4, E5
Quant researcher to risk researcher: test empirical behaviour, understand risk
How a daily cross-sectional regression is a risk model and a Fama-MacBeth test at once; why an optimizer exploits covariance error; what a calibrated risk forecast means and how it fails in stress
E6, E7, E8
Portfolio and risk researcher: control exposures, evaluate information, construct
What a hedge cannot reach; why most signals die under hygiene; why the APM sizing rules are mean-variance under a factor model, and why constraints are regularizers
E9, E10, E11
Systematic practitioner: apply constraints and costs, run the book
Where net alpha stops; how much risk to run given an estimated Sharpe; what breaks in production that no backtest shows
E12, E13
Systematic practitioner: attribute P&L, translate to credit
Why you made or lost money to machine precision; which parts of the framework are mathematics and which are markets

Research gates
Infrastructure is never built around an unvalidated assumption. Three gates sit in front of the major engineering efforts; each is a checklist answered with stored numbers, and each has a documented exit for a negative answer. G1, G2 and G3 remain the milestone gates from v1.
RG-Data, end of E1, before any model is fit
Do the probe scripts print rows for every source, and is coverage above the F1.1 threshold?
Is the survivorship magnitude measured, and is it small enough for long/short research (long-only carries a caveat either way)?
Do the reconciliation checks (F1.3, F1.4) pass?
Exit on a negative answer: adapt the universe or the source, record the decision in the ledger, and re-run; E2 does not start on data that failed RG-Data.
RG-Signal, end of E7, before a signal feeds construction (E8) or the book (E11)
Is the hypothesis clearly defined, with an economic reason the information should exist?
Is the data behind the signal reliable and point-in-time (E1 ledger flags)?
Does the basic empirical relationship exist in-sample, factor-neutral?
Does it survive simple out-of-sample testing (2021 to 2026) and the deflated-Sharpe hurdle?
Are the results economically meaningful after a rough cost estimate (break-even cost above realistic cost)?
Are the results robust to universe definition, weighting scheme and horizon?
Is there a plausible implementation path (turnover, capacity, whole shares)?
Exit on a negative answer: the signal is labeled NULL in the Signal Evaluation Report and the ledger. If no signal passes, E8 runs on synthetic alpha with a known IC (a controlled input that tests the construction machinery more cleanly than a real signal would), and E11 runs a documented-null book on the best-behaved signal purely as an operational instrument, labeled as such. The expected E12 verdict is luck, and that is written down before E11 starts.
RG-Operate, end of E10, before the book runs (E11)
Has a champion risk model passed E5 with a stated stress haircut?
Is the hedge policy from E6 written down with its cost?
Has G3 passed: does the construction stack run end to end under the champion model with the constraint set from E8?
Are the cost-model parameters stated with their uncertainty (E9), and is the risk budget written per regime (E10)?
Exit on a negative answer: E11 waits; the missing item is finished first. Running a book on an unvalidated risk model teaches operations and nothing else.
A gate that returns a negative answer has done its job. The sprint that hit it is complete; the number goes into RESULTS.json and the research deliverable, and the next sprint adapts.
Book coverage map
Every technique in the two books, the sprint that builds it, and the dashboard tab that shows it. This table is the definition of comprehensive for this project; E12 closes when every row is checked off. Rows marked v2 were added in this revision.
Chapter references are by topic. EQI numbering follows the published dependency map (Ch2 Univariate Returns, Ch3 Performance, Ch4 Linear Models, Ch5 Evaluating Risk, Ch6 Fundamental and Ch7 Statistical Factor Models, Ch8 Evaluating Excess Returns, Ch9 Basic and Ch10 Advanced Portfolio Management, Ch11 Tcost-Aware, Ch12 Hedging, Ch13 Dynamic Risk Allocation, Ch14 Ex-Post Attribution). Check APM chapter numbers against your copy.
Element
APM
EQI
Sprint
Tab
Returns: simple, log, excess; aggregation; stylized facts
Ch3
Ch2
E1
D0
Performance metrics: Sharpe with SE, drawdown, hit rate, slugging
Ch3, Ch8
Ch3
E1, E12
D11
Volatility estimation: EWMA, GARCH(1,1), realized, state-space
Ch3
Ch2
E2
D1
Time-series factor models; beta estimation; residualization; HAC SEs
Ch4, Ch5
Ch4
E2
D1
Fundamental (cross-sectional) model; factor construction; WLS; FMPs
Ch5
Ch6
E3
D2
Fama-MacBeth premia and t-stats; descriptor orthogonalization (v2)
Ch5
Ch6
E3
D2
Factor covariance, specific risk, Sigma = X F X' + D
Ch5, Ch7
Ch6
E3
D2
Risk decomposition, MCR, contribution tables, exposure limits
Ch3, Ch7
Ch6
E3
D2
Statistical factor models: PCA, number of factors, rotation
Ch5
Ch7
E4
D3
Covariance and precision estimation, shrinkage, RMT clipping
Ch5
Ch4, Ch7
E4
D3
Risk model evaluation: bias statistics, coverage, horizon
Ch5
E5
D4
Regime analysis: risk, signals, drawdowns, attribution (v2)
Ch9
Ch5, Ch13
E5, E7, E10, E12
D4, D6, D9, D11
Hedging: beta, factor-neutral via FMPs, min-variance, partial
Ch4, Ch7
Ch12
E6
D5
Signal evaluation: IC, decay, fundamental law, neutralization
Ch6, App.
Ch8
E7
D6
Backtest hygiene: look-ahead, survivorship, snooping, deflated SR
Ch8
E7 (E1)
D6, D0
Momentum and short-interest anomalies as worked signals
App.
Ch8
E7
D6
Sizing: proportional rule, Sharpe rule, Procedure 6.3
Ch6
Ch9
E8
D7
Mean-variance with constraints; multiple signals; alpha shrinkage
Ch6
Ch9, Ch10
E8
D7
Turnover and implementation constraints (v2)
Ch6, Ch10
Ch10, Ch11
E8, E9
D7, D8
Transaction costs, t-cost-aware optimization, capacity
Ch10
Ch11
E9
D8
Kelly and fractional Kelly, vol targeting, drawdown control
Ch9
Ch13
E10
D9
Stop-loss efficiency analysis
Ch9
Ch13
E10
D9
The daily book: proposals, execution, governance
Ch2
E11
D10
Ex-post attribution: holdings-based, time-series, skill vs luck
Ch8
Ch14
E12
D11
Credit port: factor mapping, module map
E13
Method.
Dashboard architecture: the EFB Console
One Streamlit app, grown one tab per sprint, never rebuilt. It reads parquet and Supabase only and never recomputes a model. Every tab shows all of the information for its element: the inputs, the outputs, the version that produced them, the research deliverable that interprets them, and the walkthrough that derives them.
Global sidebar (from E1, extended in E4)
As-of date
Universe snapshot and data version hash (E1)
Model version selector: TS-vN, XS-vN, PCA-vN, with the champion badge (E4, E5)
Portfolio selector: seed books, the live book, or an uploaded CSV of weights (E3)
Regime selector: all, VIX terciles, named episodes; every tab that reports a statistic can be filtered by it (E5 onward)
Links to the Hygiene Ledger, the multiple-testing ledger, every research deliverable and every walkthrough (Methodology tab)
Tabs by sprint
Tab
Sprint
What it shows
D0 Data Health
E1
Coverage heatmap, missing and stale counts, universe size and changes, corporate-action and outlier log, the Hygiene Ledger rendered, the survivorship number
D1 Exposures
E2
Loadings with SEs, rolling beta with shrinkage overlays, R squared, idio vs total vol, vol estimator comparison with QLIKE, beta horse race
D2 Factor Model and Risk
E3
Factor returns and t-stats, Fama-MacBeth premia table, cross-sectional R squared, descriptors, factor covariance, FMP explorer, risk decomposition tables and MCR
D3 Covariance Lab
E4
Eigenvalue spectrum vs MP edge, PCA vs fundamental factors, residual factor audit, estimator comparison, version selector
D4 Risk Model Evaluation
E5
Bias heatmap by model, family and regime, rolling bias, calibration, horizon consistency, champion badge with rule and number
D5 Hedging Lab
E6
Before and after decomposition, hedge weights, exposures pre and post, tracking error, cost, rebalancing slider
D6 Alpha Lab
E7
IC and decay by regime, quantile spreads raw vs neutral, turnover and break-even cost, multiple-testing ledger, expected-return calculator, RG-Signal verdict per signal
D7 Sizing and Optimizer
E8
Inputs panel and outputs panel, rule comparison, constraint set, robustness result, worked-example card for one stock
D8 Cost and Capacity
E9
Cost curves, pre and post cost Sharpe with SE, turnover vs IR frontier, capacity curve with sensitivity to k
D9 Risk Allocation
E10
Kelly calculator, vol-target simulation, stop-loss efficiency with the i.i.d. control, drawdown distribution by regime
D10 Book Monitor
E11
Positions, P&L, ex-ante vs realized risk, exposures vs limits, proposals and overrides, guard events, realized vs modeled slippage
D11 Attribution
E12
Factor vs idio P&L, per-factor bars, selection vs sizing vs timing, holdings vs returns-based, seven-way table, skill vs luck card
Methodology
all
Registry, version notes, both ledgers, every research deliverable, every walkthrough, the credit port design note
Model registry schema (registry.json)
{
"TS-v1": {
"family": "timeseries",
"factors": ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "MOM"],
"window": 252, "half_life_beta": 126, "cov_half_life": 90,
"shrinkage": "vasicek",
"universe_hash": "...", "data_hash": "...",
"built_at": "2026-09-13", "champion": false,
"walkthrough": "notebooks/E2_walkthrough.html",
"deliverable": "docs/research/E2_exposure_study.md",
"results": "sprints/E2/RESULTS.json"
},
"XS-v1": { "family": "fundamental", "descriptors": [...],
"orthogonalization": {"momentum": ["beta", "size"]},
"weights": "sqrt_mcap", "f_half_life": 90, "nw_lags": 2,
"d_half_life": 42, "d_shrink": "sector_size", ... },
"PCA-v1": { "family": "statistical", "k": 8, "k_rule": "mp_edge", ... },
"champion_rule": "min mean |bias-1| across families; ties -> fewer params",
"champion": "XS-v1", "stress_haircut": 1.3
}
A new descriptor, a new half-life, or a new universe snapshot is a new version, never an edit. Old versions stay readable in every tab through the selector; that is how the dashboard answers the question of what changed when a number moves.

How to use this document
Work sequentially. Do not open Sprint N+1 until Sprint N's exit criteria are met, its walkthrough is rendered, and its research deliverable is written.

/quant-prd generates the sprint's PRD and TASKS in a fresh Claude session. Each block now ends with the research framing: the three questions and the deliverable. The TASKS ceiling is 10 atomic tasks with a test each, and two of them are always the deliverable and the criteria evaluation.

/quant-dev executes one task at a time, validates with printed numbers, and stores any F criterion it touches in RESULTS.json.

/quant-walkthrough writes the notebook that reproduces the sprint by hand. It is the promotion artifact and the evidence section of the research deliverable.
E1 to E3 carry the full prompt trio. E4 onward carry the /quant-prd block and use the generic templates below.
Falsification criteria are copied verbatim from this roadmap into each PRD and are not reworded after the number is seen; if a threshold was wrong, the next sprint registers a new criterion with a new ID.
Reading is implementation-led: read the chapter's core section before the sprint, enough to answer the Understand-before questions in the sprint's Book connection; do not summarize the chapter, build it.
Generic /quant-dev template (E4 onward)

/quant-dev
Sprint E<n>. Work on the highest priority open task in
sprints/E<n>/TASKS.md.
Process:
1. If the task depends on a data field, run its probe first and paste
the printed rows. Data-availability claims are hypotheses until then.
2. Implement with type hints, docstrings, and a unit test. Test on a
synthetic dataset with known parameters before real data.
3. Validate with numbers, not adjectives: print inputs, intermediate
quantities, and outputs for AAPL, XOM, JPM and one seed portfolio.
Run the sprint's empirical tests and look for its listed failure
modes; report which ones you checked.
4. Look-ahead check: anything dated t was computed from data through
t-1 when it feeds a forecast.
5. Check NaNs, infs, singular matrices, index alignment.
6. Store any F<n>.x number in sprints/E<n>/RESULTS.json.
7. If a data contract changed, update dashboard tab D<k> and confirm
every earlier tab still renders (regression test).
8. If the task is the research deliverable: write it for a senior
quant or risk manager, methodology first, then the stored numbers,
then the practitioner conclusion, then "What would falsify this?".
Output:
- Code summary
- Validation numbers (printed values)
- F criteria touched: pass, fail, or pending, with the stored number
- What this result means for the PM question of the sprint, in two
sentences
- Issues or blockers
- Next task recommendation
Generic /quant-walkthrough template (E4 onward)

/quant-walkthrough
Sprint E<n> is complete. Write notebooks/E<n>_walkthrough.ipynb.
Purpose: a mechanistic explanation of every estimator built this sprint,
reproduced by hand so that each dashboard number can be derived at a
whiteboard, and so that the research deliverable's numbers have an
audit trail.
Rules:
- Open with the sprint's three research questions and one paragraph of
intuition in your own words.
- For each formula: state it; label every symbol INPUT (file, column)
or OUTPUT (file, column); compute it step by step on three reference
names (AAPL, XOM, JPM) and one seed portfolio with plain numpy; show
the result matches the library output to 1e-8.
- Print intermediate matrices with their shapes. Numbers, not prose.
- One section per F<n>.x criterion: threshold, stored number, verdict,
and what a failure would have meant for a PM.
- One section mapping every panel of dashboard tab D<k> to the parquet
column it reads.
- One section "Evidence for the research deliverable": the tables the
deliverable cites, in the order it cites them.
- End with a credit port note: for each estimator, which inputs get
swapped in credit and which formulas survive unchanged.
- No em dashes anywhere.
Output: the notebook, rendered to HTML, linked from the Methodology tab.

Sprint E1: Universe, Returns and the Hygiene Ledger
Tue Sep 1 to Sun Sep 6. Tier 1.
Stage: Quant finance student to quant researcher: the data underneath every number
Book coverage: APM Ch3 (returns, vol, Sharpe). EQI Ch2 (univariate returns, stylized facts), Ch3 (performance measurement).
Research questions
Academic. What is a return, and which definition (simple, log, excess) is correct for which operation: aggregation through time, aggregation across assets, and risk measurement?
Practitioner. Can I trust the prices, the universe and the risk-free rate underneath every number this book will ever show?
Research. Is a free, survivorship-affected universe good enough to support factor-model research, and how large is the bias it introduces, in basis points per year?
Objective
Build the reproducible daily equity data layer and the Hygiene Ledger that every later sprint reads from. This sprint ends with parquet artifacts, a written ledger of every data decision, a performance-metrics library, and dashboard tab D0. No model is fitted here.
Academic concept and intuition
Concept. Return definitions and their algebra; the stylized facts of daily equity returns (fat tails, volatility clustering, near-zero autocorrelation of returns next to strong autocorrelation of squared returns); the Sharpe ratio as an estimated quantity with a standard error; survivorship and look-ahead bias in universe construction.
Intuition. Log returns add through time and simple returns add across a portfolio; mixing them is a bug that survives for years because it is small on any one day. Daily market returns have kurtosis far above 3, so any Gaussian risk number is a floor, not an estimate. A Sharpe ratio of 1.0 measured over three years carries a standard error near 0.7, so an eyeballed Sharpe is a hypothesis, not evidence. A universe built from today's index members is a universe of winners.
Foundation
The formulas the sprint implements; inputs and outputs are labeled in the walkthrough.
Simple return r_t = P_t / P_{t-1} - 1 on dividend-adjusted prices; log return g_t = ln(P_t / P_{t-1}); excess return r_t - rf_t with rf the daily T-bill rate (INPUT: prices.parquet adj_close; factors_ff.parquet RF).
Aggregation: sum of g over T days equals ln(P_T / P_0); portfolio return sum_i w_i r_i holds for simple returns only.
Sharpe SR = mean(r - rf) / std(r - rf), annualized by sqrt(252) only under i.i.d.; SE_iid(SR) approximately sqrt((1 + SR^2 / 2) / T); Lo (2002) corrects for autocorrelation (OUTPUT: efb/perf.py).
Survivorship: bias = return of buy-all-current-members minus return of the point-in-time membership, annualized.
Implementation scope
Task 0, before anything else: probe scripts for every data source (yfinance prices, Wikipedia constituents and changes table, Kenneth French library, GICS sectors, shares outstanding, risk-free rate). A source is not available until its probe has printed rows into sprints/E1/PROBES.md. This is the v7.1 discipline carried over.
Universe: current S&P 500 members plus every deleted name recoverable from the Wikipedia changes table; membership matrix (date x ticker) from 2010; survivorship bias measured (share of historical members with recoverable price history), not assumed away.
Prices: adjusted close audit against splits and dividends; total return vs price return; stale-price detection (zero-return runs of 5 or more days).
Returns: simple, log, and excess over the daily risk-free rate; aggregation rules (log returns add over time, simple returns add across assets); stylized-facts panel: fat tails, volatility clustering, autocorrelation of r and r squared.
Hygiene Ledger (docs/hygiene_ledger.md): missing-data policy, outlier policy (|r| > 50% flagged for review, never silently winsorized in raw), delisting handling, timezone and date alignment, a point-in-time flag on every field (shares outstanding and book value are NOT point-in-time from free sources; say so).
Performance-metrics library efb/perf.py: Sharpe with standard error (i.i.d. and Lo 2002 autocorrelation-adjusted), annualization, max drawdown, hit rate, slugging ratio. Every later sprint reports Sharpe with its standard error.
Deliverables and dashboard increment
data/raw/prices.parquet; data/processed/returns.parquet (simple, log, excess); universe_membership.parquet; factors_ff.parquet; sectors.parquet; data/VERSION.json (content hash)
docs/hygiene_ledger.md, sprints/E1/PROBES.md, efb/perf.py with tests
notebooks/E1_walkthrough.ipynb rendered to HTML
Dashboard tab D0 Data Health
Dashboard: D0 Data Health: coverage heatmap (ticker x month), missing and stale counts, universe size over time with additions and deletions, corporate-action and outlier event log, the Hygiene Ledger rendered in-app, data version hash in the sidebar.
Empirical tests and diagnostics
Tests
Stylized-facts table for three names and the equal-weight universe: kurtosis, ACF of r at lag 1, ACF of r^2 at lags 1, 5, 21.
Reconciliation: equal-weight universe vs FF market return (F1.3); adjusted total return vs dividend series (F1.4).
Survivorship measurement: buy-all-members vs point-in-time membership vs FF market, annualized gap (F1.5).
Sharpe SE comparison on the market factor: i.i.d. vs Lo (2002), and the direction of the difference.
Failure modes to look for
Missed split producing a fake 50% return that dominates covariance and factor returns for a year.
Universe look-ahead: using today's members historically inflates every long-only result.
Date misalignment between Kenneth French (US close) and yfinance; a one-day shift kills every later regression.
Stale prices (zero-return runs) that show up later as spurious low volatility.
Why this matters to a PM
PM question: "Can I trust the data underneath every number this book will ever show me?"
Problem it addresses. Every risk number, hedge ratio and attribution line rests on returns; a risk manager's first question about any model is what data it was fit on.
Decision it informs. Whether the data supports decisions at all, which names are excluded, what the universe is, and which fields are trusted as point-in-time.
If the analysis is wrong. A single corporate-action error propagates into the covariance matrix, the factor returns and the optimizer; survivorship makes a losing strategy look like a winning one.
Before trusting the output. The reconciliation numbers (F1.3, F1.4), the survivorship number (F1.5), and a ledger where every policy decision has a date and a reason.
What would falsify this?
Equal-weight universe fails to track the FF market return (F1.3): the data layer is wrong before any model exists.
Survivorship bias above 200 bp per year: every long-only backtest in later sprints carries a mandatory caveat, and long/short constructions are preferred.
A data source that fails its probe: recorded as a null, and the design routes around it (Research Gate RG-Data).
Research deliverable
Data Quality and Universe Note (docs/research/E1_data_note.md)
Sources, coverage, probe outputs, point-in-time status per field
Stylized-facts table with a one-paragraph interpretation for risk modeling
Survivorship magnitude in bp per year and what it implies for later sprints
Policy decisions and known limitations, written for a risk manager who has not seen the code
Book connection
Chapters. EQI Ch2 (univariate returns, stylized facts), Ch3 (performance measurement); APM Ch3 (returns, volatility, Sharpe).
Understand before implementing: Why log and simple returns aggregate differently, and which one a covariance matrix wants. Why a Sharpe ratio must be reported with its standard error, and what autocorrelation does to that error.
What the implementation teaches that the book cannot: How much of 'data' is policy: delistings, stale prints and corporate actions are decisions, not facts. Free data forces you to measure survivorship rather than read about it.
Academic vs practitioner
Academic perspective. Returns are given, i.i.d. is assumed for the Sharpe standard error, and the universe is the CRSP file with delisting returns.
Practitioner perspective. Returns are constructed; corporate actions and delistings decide the number; production cares about point-in-time flags and reproducibility far more than about the log-versus-simple debate.
Pre-registered falsification criteria
Numeric thresholds written before the numbers are seen; each is evaluated with a stored number in sprints/E1/RESULTS.json.
ID
Criterion
F1.1
Each probed source returns at least 95% of requested tickers with at least 10 years of daily history. A failing source is recorded in the ledger and the design adapts; it is never silently dropped.
F1.2
Zero NaNs in returns.parquet after the warm-up window, except documented delisting rows.
F1.3
Equal-weight universe daily return vs the Kenneth French market return (Mkt-RF + RF) correlation above 0.95. Lower means a date-alignment or adjustment bug, not a finding.
F1.4
Total returns computed from adjusted close reproduce the dividend-adjusted series within 1 bp per day on 20 randomly sampled names.
F1.5
Survivorship measured: the fraction of historical members with recoverable history is stored. If below 70%, the ledger records the bias magnitude via a naive buy-all-members backtest against the FF market return.
Exit criteria
All F1 criteria evaluated with stored numbers in sprints/E1/RESULTS.json; make rebuild-e1 runs end to end; D0 loads in under 3 seconds; walkthrough rendered. Research deliverable written and linked from the Methodology tab.

/quant-prd, Sprint E1
Paste into a fresh Claude session to generate this sprint's PRD and TASKS.

/quant-prd
This is Sprint E1 of the Equity Factor Book (EFB) project. Nothing exists
yet except the repo skeleton and the engineering standards in the roadmap
appendix.
Objective:
Build the reproducible daily equity data layer and the Hygiene Ledger that
every later sprint reads from. The sprint ends with parquet artifacts, a
written ledger of every data decision, a performance-metrics library, and
dashboard tab D0. No model is fitted in this sprint.
Task 0 (before anything else): probe scripts. For each source below,
print row count, first and last date, ticker coverage, NaN share, and
paste the printed output into sprints/E1/PROBES.md. A source is not
"available" until its probe has printed rows.
- yfinance daily OHLCV and adjusted close, S&P 500 members (current plus
recoverable deleted names), 2010 to today
- Wikipedia S&P 500 constituents table and the "Selected changes" table
- Kenneth French library: FF5 daily, Momentum daily, Short-term reversal
daily, 12 industry portfolios daily
- GICS sector per ticker
- Shares outstanding via yfinance: record whether history is returned or
only the current value
- Risk-free rate: FF RF column, cross-checked against FRED DTB3
Focus areas:
- Universe membership matrix (date x ticker) rebuilt from the changes
table; survivorship bias measured, not assumed away
- Adjusted close audit (splits, dividends); total vs price return
- Returns: simple, log, excess over daily RF; aggregation rules (EQI Ch2)
- Stylized-facts panel: fat tails, vol clustering, autocorrelation of r
and r^2 (EQI Ch2)
- Hygiene Ledger docs/hygiene_ledger.md: missing-data policy, stale-price
detection (zero-return runs >= 5 days), outlier policy (|r| > 50%
flagged, never silently winsorized in raw), delisting handling,
timezone and date alignment, point-in-time flag per field
- efb/perf.py: Sharpe with standard error (i.i.d. and Lo 2002),
annualization, max drawdown, hit rate, slugging (EQI Ch3, APM Ch3, Ch8)
Requirements:
- Exact formulas with every input and output labeled
- Parquet schemas (columns, dtypes, index) for data/raw/prices.parquet,
data/processed/returns.parquet, universe_membership.parquet,
factors_ff.parquet, sectors.parquet
- data/VERSION.json with a content hash of every artifact
- Pre-registered falsification criteria F1.1 to F1.5 copied verbatim from
the roadmap, each with its numeric threshold
- Dashboard tab D0 spec: coverage heatmap (ticker x month), missing and
stale counts, universe size over time, corporate-action and outlier
event log, ledger rendered in-app, data version in sidebar; reads
parquet only, never recomputes
- Max 10 atomic tasks, each with a test
- One command rebuilds everything: make rebuild-e1
Output:
- sprints/E1/PRD.md
- sprints/E1/TASKS.md
- sprints/E1/PROBES.md
Research framing (from the roadmap, copy into the PRD verbatim):
- Academic question: What is a return, and which definition (simple, log, excess) is correct for which operation: aggregation through time, aggregation across assets, and risk measurement?
- Practitioner question: Can I trust the prices, the universe and the risk-free rate underneath every number this book will ever show?
- Research question: Is a free, survivorship-affected universe good enough to support factor-model research, and how large is the bias it introduces, in basis points per year?
- Research deliverable: Data Quality and Universe Note, written for
a senior quant or risk manager; it must contain the methodology, the
stored numbers, the practitioner conclusion, and a section titled
"What would falsify this?". A negative verdict is a complete
deliverable.
- The TASKS.md must include one task that produces the deliverable and
one that evaluates every falsification criterion listed below.

/quant-dev, Sprint E1
Run iteratively on the highest-priority open task.

/quant-dev

Sprint E1, Universe, Returns and the Hygiene Ledger.
Work on the highest priority open task in sprints/E1/TASKS.md.
Process:
1. If the task depends on a data field, run its probe first and paste the
printed rows. Data-availability claims are hypotheses until then.
2. Implement with type hints, docstrings, and a unit test.
3. Validate with numbers, not adjectives:
- Prices: for 20 random names, total return from adjusted close vs
dividend-adjusted series, max abs daily difference in bp
- Universe: count of historical members recovered vs listed in the
changes table; store the fraction (F1.5)
- Returns: NaN count post warm-up (F1.2); equal-weight universe return
vs FF market return correlation (F1.3)
- Stale prices: list of tickers with zero-return runs >= 5 days
- Perf library: Sharpe and its SE on the FF market factor, both i.i.d.
and Lo 2002; the two SEs must differ in the expected direction
4. Check index alignment (business days only, no timezone drift), infs,
duplicate dates.
5. Write every policy decision you made into docs/hygiene_ledger.md as
you make it, with the date and the reason.
6. Store any F1.x number you produced in sprints/E1/RESULTS.json.
Output:
- Code summary
- Validation numbers (the printed values, not a description of them)
- F criteria touched: pass, fail, or pending, with the stored number
- Ledger entries added
- Issues or blockers
- Next task recommendation

/quant-walkthrough, Sprint E1
Run once the exit criteria are met. The notebook is the promotion artifact for the model version and the evidence behind the research deliverable.

/quant-walkthrough

Sprint E1 is complete. Write notebooks/E1_walkthrough.ipynb.
Purpose: a mechanistic explanation of the data layer, reproduced by hand,
so that every downstream sprint starts from numbers I have verified.
Sections:
1. Returns by hand. For AAPL, XOM and JPM on three consecutive dates,
compute simple, log, and excess returns from adjusted close and the
daily RF using plain arithmetic. Label each symbol INPUT (file, column)
or OUTPUT (file, column). Show they match returns.parquet to 1e-10.
2. Aggregation. Show on the same three names that log returns add over
time and simple returns add across an equal-weight portfolio, with the
numbers, and show where each approximation breaks.
3. Stylized facts with numbers: kurtosis of daily returns, autocorrelation
of r at lag 1 and of r^2 at lags 1, 5, 21, for the three names and the
equal-weight universe.
4. Sharpe with standard error: compute SR, the i.i.d. SE, and the Lo 2002
SE for the FF market factor step by step; explain why the two SEs
differ and which way.
5. Survivorship: the F1.5 number, and the naive buy-all-members backtest
vs FF market return, plotted, with the annualized gap in bp.
6. One section per F1.x criterion: threshold, stored number, verdict, and
what a failure would have meant.
7. Dashboard D0: map each panel to the parquet column it reads.
8. Credit port note: which of these definitions survive unchanged in
credit (excess return, Sharpe SE, ledger structure) and which get
re-specified (return definition becomes spread or excess-over-
duration-matched-Treasury return; universe membership becomes index
constituent files).
No em dashes anywhere in the notebook. Render to HTML and link it from
the dashboard Methodology tab.

Sprint E2: Time-Series Factor Models and Volatility
Mon Sep 7 to Sun Sep 13. Tier 1.
Stage: Quant researcher: estimating exposures and knowing their error
Book coverage: APM Ch4 (simple factor models, beta), Ch5 (time-series multifactor). EQI Ch2 (GARCH, realized and state-space variance), Ch4 (linear models).
Research questions
Academic. How is a stock's exposure to observed factors estimated by time-series regression, how uncertain is the estimate, and when does shrinkage improve it?
Practitioner. When the risk system says a stock has beta 1.3, how much should I believe it, how fast does it move, and what is its residual (idio) return?
Research. Do shrunk, exponentially weighted betas forecast next-quarter realized betas and portfolio volatility better than raw OLS betas, and do GARCH or EWMA forecasts beat trailing volatility?
Objective
Estimate per-stock exposures to observed factors by time-series regression, with honest standard errors and shrinkage, and build the volatility estimators the risk model will need. Register TS-v1 as the first model version.
Academic concept and intuition
Concept. The linear factor model r_i = alpha_i + beta_i' f + eps_i; OLS estimation and HAC standard errors; residualization (the residual is the idiosyncratic return, the object every later sprint sizes on); beta shrinkage (Vasicek, Blume); conditional heteroskedasticity (EWMA, GARCH(1,1)) and forecast evaluation (Mincer-Zarnowitz, QLIKE).
Intuition. Beta is a regression slope with a standard error near sigma_eps / (sigma_m sqrt(T)); with T = 252 that is typically 0.15 to 0.25, so a beta of 1.3 and a beta of 1.1 are often the same number. Shrinkage buys lower variance with a little bias. Volatility clusters, so yesterday's volatility is the best single predictor of today's; EWMA is GARCH with fewer parameters and a fixed persistence.
Foundation
The formulas the sprint implements; inputs and outputs are labeled in the walkthrough.
OLS: beta_hat = (X'X)^-1 X'y; residuals e = y - X beta_hat; R^2; residual vol sigma_eps (INPUT: returns.parquet excess, factors_ff.parquet; OUTPUT: TS-v1/loadings, residuals, idio_vol).
Newey-West covariance of beta_hat with lag L, which widens the SE when residuals are autocorrelated or heteroskedastic.
Vasicek: beta_s = w beta_hat + (1 - w) beta_bar, w = sigma_xs^2 / (sigma_xs^2 + SE^2); Blume: beta_s = 0.67 beta_hat + 0.33.
EWMA: sigma_t^2 = lambda sigma_{t-1}^2 + (1 - lambda) r_{t-1}^2; GARCH(1,1): sigma_t^2 = omega + a r_{t-1}^2 + b sigma_{t-1}^2; QLIKE(sigma_hat, r) = ln sigma_hat^2 + r^2 / sigma_hat^2.
Portfolio variance under the time-series model: sigma_p^2 = w' B F B' w + w' D w, F the EWMA factor covariance, D diagonal idio variances.
Implementation scope
Single-factor market model per stock: OLS beta, alpha, R squared, residual vol; full sample, rolling 252d, and exponentially weighted (half-lives 63 and 126).
Multi-factor time-series model: excess return on FF5 + Momentum (+ short-term reversal as an optional column); loadings matrix B (N x K), residual matrix, idio vol per stock.
Beta shrinkage: Vasicek (toward the cross-sectional mean, weighted by estimation error) and Blume; OLS vs Newey-West HAC standard errors.
Volatility estimators: EWMA (lambda 0.94 and 0.97), GARCH(1,1) via the arch package, realized vol (21d, 63d); Mincer-Zarnowitz regression and QLIKE loss for out-of-sample forecast comparison (EQI Ch2).
Factor covariance from FF factor returns (EWMA, half-life 90d) and the first portfolio-level risk number: sigma_p squared = w' B F B' w + w' D w, for the equal-weight seed portfolio.
Model registry v0: registry.json with TS-v1 (parameters, window, half-lives, data hash).
Deliverables and dashboard increment
efb/models/timeseries.py, efb/vol.py, efb/registry.py
data/models/TS-v1/{loadings, loadings_se, residuals, idio_vol, factor_cov}.parquet
notebooks/E2_walkthrough.ipynb (worked example on AAPL, XOM, JPM)
Dashboard tab D1 Exposures
Dashboard: D1 Exposures: per-stock loadings table with standard errors; rolling beta chart with raw, Vasicek and Blume overlays; R squared distribution; idio vol vs total vol scatter; volatility estimator comparison (EWMA, GARCH, realized) with QLIKE table; portfolio exposure panel for the selected portfolio.
Empirical tests and diagnostics
Tests
Beta forecast horse race: raw, Vasicek, Blume, EWMA-weighted betas predicting next-quarter realized beta, RMSE across the universe.
Residual cross-correlation (F2.2): is the FF factor set adequate for this universe?
Volatility forecast comparison on QLIKE and Mincer-Zarnowitz (F2.3); bias of predicted vs realized portfolio vol by year (F2.4).
Newey-West vs OLS SEs (F2.5).
Failure modes to look for
Short histories and recent IPOs producing betas with SEs above 0.5.
Regime breaks (2020) that a 252-day window takes a year to forget; a half-life choice is a horizon choice.
Collinearity among FF factors (HML vs CMA) making individual loadings unstable while their sum is fine.
High residual cross-correlation, which means the risk model is missing a common factor and idio risk is overstated.
Why this matters to a PM
PM question: "When the risk system says this stock has a beta of 1.3, how much should I believe it, and how fast does it change?"
Problem it addresses. Exposure is what you are paid for or what you hedge away; a stock's idio return is the only part a stock picker can claim.
Decision it informs. Hedge ratios, and whether a position the PM calls an idio story is in fact a factor bet.
If the analysis is wrong. Beta underestimated means under-hedged in a selloff; residual vol underestimated means oversized positions.
Before trusting the output. Standard errors next to every loading, stability across rolling windows, and a forecast test, not an in-sample fit.
What would falsify this?
Shrunk betas do not beat raw betas out of sample: shrinkage is decoration and TS-v2 drops it.
Residual correlations above 0.05: the observed-factor set is inadequate, which is the motivation for E3, not a failure of E2.
GARCH does not beat EWMA meaningfully on QLIKE: production uses EWMA, simplicity wins.
Research deliverable
Beta and Volatility Estimation Study (docs/research/E2_exposure_study.md)
Exposure report for the seed book: loadings with SEs, R^2, idio vol per name
The beta horse race and the volatility horse race, with the recommended estimator per use (hedging, risk, sizing)
One paragraph on what the residual correlation structure says about the factor set
Book connection
Chapters. APM Ch4 (simple factor models, beta), Ch5 (time-series multifactor); EQI Ch2 (GARCH, realized and state-space variance), Ch4 (linear models).
Understand before implementing: Why a single-stock regression has a low R^2 (0.2 to 0.4) and yet the beta is the most important number in the risk model. Why unconditional volatility is the wrong number when volatility clusters.
What the implementation teaches that the book cannot: The estimation error is the story; the point estimate is the least interesting output. The difference between an in-sample fit and a forecast, measured in QLIKE rather than asserted.
Academic vs practitioner
Academic perspective. Full-sample OLS with asymptotic standard errors, factors treated as known.
Practitioner perspective. Rolling or EWMA windows, shrinkage as default, the half-life set by the hedging horizon, and a vendor model that reports the beta but never its standard error.
Pre-registered falsification criteria
Numeric thresholds written before the numbers are seen; each is evaluated with a stored number in sprints/E2/RESULTS.json.
ID
Criterion
F2.1
Full-sample OLS beta vs mean of rolling 252d betas: cross-sectional correlation above 0.9.
F2.2
Mean pairwise correlation of FF5+MOM residuals across the universe below 0.05. Higher means a missing common factor; carry the finding into E3.
F2.3
GARCH(1,1) and EWMA(0.94) each beat trailing 252d vol on out-of-sample QLIKE for more than 60% of names.
F2.4
For the equal-weight seed portfolio, bias statistic (realized 63d forward vol over model-predicted vol) averages between 0.8 and 1.2 across calendar years.
F2.5
Newey-West SE exceeds OLS SE at lag 5 for more than 80% of names. If not, document the direction and why.
Exit criteria
All F2 criteria evaluated with stored numbers; registry contains TS-v1 with a data hash; D1 loads under 3 seconds; walkthrough rendered. Research deliverable written and linked from the Methodology tab.

/quant-prd, Sprint E2
Paste into a fresh Claude session to generate this sprint's PRD and TASKS.

/quant-prd
This is Sprint E2 of the Equity Factor Book (EFB) project. Sprint E1
outputs exist: returns.parquet, factors_ff.parquet, universe_membership,
sectors, efb/perf.py, dashboard tab D0, Hygiene Ledger.
Objective:
Estimate per-stock exposures to observed factors by time-series
regression, with honest standard errors and shrinkage, and build the
volatility estimators the risk model needs. Register TS-v1 as the first
model version. Ends with dashboard tab D1.
Focus areas:
- Single-factor market model per stock: OLS beta, alpha, R^2, residual
vol; full sample, rolling 252d, EWMA-weighted (half-lives 63, 126)
(APM Ch4)
- Multi-factor time-series model on FF5 + MOM (+ STR optional): loadings
B (N x K), residuals, idio vol (APM Ch5, EQI Ch4)
- Beta shrinkage: Vasicek and Blume; OLS vs Newey-West HAC SEs
- Volatility: EWMA (0.94, 0.97), GARCH(1,1) via arch, realized (21d,
63d); Mincer-Zarnowitz and QLIKE out-of-sample comparison (EQI Ch2)
- Factor covariance F from FF factor returns (EWMA half-life 90d)
- Portfolio risk under the time-series model:
sigma_p^2 = w' B F B' w + w' D w, for the equal-weight seed portfolio
- Model registry: efb/registry.py, registry.json, entry TS-v1
Requirements:
- Exact formulas: OLS estimator, Newey-West covariance with lag choice,
Vasicek and Blume shrinkage weights, EWMA recursion, GARCH(1,1)
equations, QLIKE loss. Inputs and outputs labeled for each.
- Every regression uses returns at t against factors at t; no look-ahead
in rolling windows (window ends at t-1 when used for forecasting)
- Parquet schemas for data/models/TS-v1/{loadings, loadings_se,
residuals, idio_vol, factor_cov}.parquet
- Registry schema: version id, model family, parameters, universe hash,
data hash, built_at, champion flag (false)
- Pre-registered criteria F2.1 to F2.5 copied verbatim
- Dashboard D1 spec: loadings table with SE, rolling beta with shrinkage
overlays, R^2 distribution, idio vs total vol scatter, vol estimator
comparison with QLIKE table, portfolio exposure panel; reads parquet
only
- Max 10 atomic tasks, each with a test
Output:
- sprints/E2/PRD.md
- sprints/E2/TASKS.md
Research framing (from the roadmap, copy into the PRD verbatim):
- Academic question: How is a stock's exposure to observed factors estimated by time-series regression, how uncertain is the estimate, and when does shrinkage improve it?
- Practitioner question: When the risk system says a stock has beta 1.3, how much should I believe it, how fast does it move, and what is its residual (idio) return?
- Research question: Do shrunk, exponentially weighted betas forecast next-quarter realized betas and portfolio volatility better than raw OLS betas, and do GARCH or EWMA forecasts beat trailing volatility?
- Research deliverable: Beta and Volatility Estimation Study, written for
a senior quant or risk manager; it must contain the methodology, the
stored numbers, the practitioner conclusion, and a section titled
"What would falsify this?". A negative verdict is a complete
deliverable.
- The TASKS.md must include one task that produces the deliverable and
one that evaluates every falsification criterion listed below.

/quant-dev, Sprint E2
Run iteratively on the highest-priority open task.

/quant-dev

Sprint E2, Time-Series Factor Models and Volatility.
Work on the highest priority open task in sprints/E2/TASKS.md.
Process:
1. Implement with type hints, docstrings, and a unit test. Test each
estimator on a synthetic dataset with known parameters first (known
beta, known GARCH parameters) and show the estimator recovers them.
2. Validate with numbers on AAPL, XOM, JPM and the equal-weight seed
portfolio:
- beta, alpha, R^2, residual vol with OLS SE and Newey-West SE
- Vasicek and Blume betas next to raw beta
- EWMA, GARCH(1,1), realized vol on the last date, and QLIKE over the
out-of-sample window
- portfolio sigma_p from w' B F B' w + w' D w, next to realized vol
3. Look-ahead check: for the rolling estimator, confirm the loading
dated t was fit on data through t-1.
4. Check NaNs, infs, singular matrices (names with short history), and
index alignment with returns.parquet.
5. Store any F2.x number in sprints/E2/RESULTS.json.
6. Add or update the registry entry TS-v1 if parameters changed.
Output:
- Code summary
- Validation numbers (printed values)
- F criteria touched: pass, fail, or pending, with the stored number
- Issues or blockers
- Next task recommendation

/quant-walkthrough, Sprint E2
Run once the exit criteria are met. The notebook is the promotion artifact for the model version and the evidence behind the research deliverable.

/quant-walkthrough

Sprint E2 is complete. Write notebooks/E2_walkthrough.ipynb.
Purpose: reproduce every estimator built this sprint by hand on three
names so that I can explain each number at a whiteboard.
Sections:
1. OLS market beta for AAPL by hand: build X and y from the parquet
files (label INPUT columns), compute (X'X)^-1 X'y with explicit
matrices printed, then residuals, R^2, residual vol. Match
TS-v1/loadings.parquet to 1e-8.
2. Standard errors: OLS SE and Newey-West SE at lag 5 computed step by
step; state in one paragraph why autocorrelated squared residuals
inflate the SE.
3. Multi-factor: repeat for FF5 + MOM on XOM; print the 6 x 1 loading
vector with SEs; interpret each loading in one sentence.
4. Shrinkage: Vasicek weight for JPM from its SE and the cross-sectional
dispersion of betas; Blume adjustment; show the three betas side by
side.
5. Volatility: EWMA recursion for 5 days by hand; GARCH(1,1) one-step
forecast from fitted parameters; realized 21d; QLIKE for each on the
out-of-sample window.
6. Portfolio risk: for the equal-weight seed portfolio, compute
w' B F B' w and w' D w separately, print both numbers, their sum,
and the factor share of variance.
7. One section per F2.x criterion: threshold, stored number, verdict.
8. Dashboard D1: map each panel to its parquet column.
9. Credit port note: in credit the time-series regressors become
duration-matched Treasury return, credit index excess return (IG or
HY), and equity of the issuer; the estimator code is unchanged.
No em dashes anywhere. Render to HTML and link from the Methodology tab.

Sprint E3: Cross-Sectional Fundamental Model and Risk Decomposition
Mon Sep 14 to Sun Sep 20. Tier 1. Gate: G1, Sep 20.
Stage: Quant researcher to risk researcher: the cross-section, and what a portfolio is really made of
Book coverage: APM Ch5 (fundamental factor models, factor-mimicking portfolios), Ch7 (factor risk). EQI Ch6 (fundamental factor models, factor covariance, specific risk).
Research questions
Academic. How can cross-sectional equity returns be decomposed into systematic factor exposures and idiosyncratic returns, and are the factor premia (Fama-MacBeth) distinguishable from zero?
Practitioner. If I hold this portfolio, how much of my risk is actually coming from unintended factor exposures, and which position reduces risk fastest if trimmed?
Research. Does the proposed risk model explain realized portfolio returns and volatility adequately enough to support portfolio decisions?
Objective
Build the Barra-style cross-sectional model: standardized descriptors, sector dummies, daily weighted least squares, factor-mimicking portfolios, factor covariance and specific risk, the full covariance matrix, and the risk decomposition tables from APM. Register XS-v1. This is the September 20 gate.
Academic concept and intuition
Concept. The fundamental (characteristic-based) factor model; descriptor construction, standardization and orthogonalization; the daily cross-sectional WLS regression, which is the second stage of Fama-MacBeth with characteristics in place of estimated betas; factor returns as the returns of factor-mimicking portfolios; Fama-MacBeth premia and their Newey-West t-statistics; the full covariance Sigma = X F X' + D; risk decomposition and marginal contribution to risk (Euler decomposition).
Intuition. The time-series model asks how a stock moves with the market; the cross-sectional model asks, on a given day, whether small stocks beat large stocks. The daily regression coefficient is the return of a portfolio with unit exposure to that characteristic and zero to every other, so factor returns are tradeable objects, not abstractions. The sector constraint identifies the market factor. Marginal contribution to risk tells you which position, if trimmed by a dollar, lowers portfolio risk the most. The decomposition is the difference between being a stock picker and being long momentum without knowing it.
Foundation
The formulas the sprint implements; inputs and outputs are labeled in the walkthrough.
Model: r_t = X_{t-1} f_t + e_t, X the N x K matrix of standardized descriptors and sector dummies dated t-1 (INPUT: XS-v1/descriptors; OUTPUT: factor_returns, specific_returns).
WLS with constraint: f_hat_t = (X'WX)^-1 X'W r_t, W = diag(sqrt mcap), subject to cap-weighted sector returns summing to zero; the rows of (X'WX)^-1 X'W are the factor-mimicking portfolios, with X' w_FMP(k) = e_k.
Orthogonalization: regress a descriptor on the others it should not proxy for (momentum on beta and size) and use the residual; report factor returns both ways.
Fama-MacBeth premium: lambda_k = mean_t f_kt, t-stat with Newey-West SE; the model does not require premia, the risk model only needs f_t to have covariance.
Covariance: F = EWMA covariance of f_t (half-life 90d, Newey-West lag 2); D = EWMA of e^2 (half-life 42d) shrunk toward sector-size buckets; Sigma = X F X' + D.
Decomposition: sigma_p = sqrt(w' Sigma w); MCR_i = (Sigma w)_i / sigma_p; sum_i w_i MCR_i = sigma_p; factor contribution k = x_k (F x)_k / sigma_p with x = X'w.
Implementation scope
Descriptors, computed from data through t-1: Market (constant 1), Size (log market cap; market cap = price x shares, with the shares history flag from the ledger), Beta (shrunk, from E2), Momentum (12-1), Short-term reversal (1m), Residual volatility (63d), Liquidity (log 63d dollar volume), Sector dummies (11 GICS). Value (book to price from yfinance) is non-point-in-time and enters an EXPERIMENTAL variant only.
Standardization: cross-sectional winsorization at plus or minus 3 MAD, z-score with cap-weighted mean and equal-weighted standard deviation, so the cap-weighted market has zero style exposure.
Daily cross-sectional WLS: r_t = X_{t-1} f_t + e_t with weights sqrt(market cap), and the identification constraint that cap-weighted sector factor returns sum to zero. Outputs: factor returns f_t (K x 1 per day), specific returns e_t, cross-sectional R squared.
Factor-mimicking portfolios: the rows of (X'WX)^-1 X'W, shown to be portfolios with unit exposure to their own factor and zero to every other.
Factor covariance F: EWMA on factor returns (half-life 90d) with a Newey-West lag-2 adjustment. Specific variance D: EWMA of squared specific returns (half-life 42d) with Bayesian shrinkage toward the sector-size bucket mean.
Full covariance Sigma = X F X' + D. Risk decomposition for any weight vector w: total, factor (by factor), idio; marginal contribution to risk MCR_i = (Sigma w)_i / sigma_p; contribution w_i x MCR_i; percent of variance; the APM-style risk decomposition table; portfolio exposures x = X'w against limits.
Seed portfolios to exercise the tables: an equal-weight sector-neutral long/short momentum quintile book, and a concentrated 20-name long-only book.
New in v2: Fama-MacBeth premia: mean factor return by factor with Newey-West t-stats, full sample and subperiods, reported in the research note (academic layer of the same regression).
New in v2: Orthogonalization: momentum residualized on beta and size, volatility on beta; factor returns reported with and without, so the sensitivity is a number rather than a worry.
Deliverables and dashboard increment
efb/models/fundamental.py (descriptors, standardization, WLS, FMPs, F, D), efb/risk.py (decompose, mcr, tables, exposures)
data/models/XS-v1/{descriptors, factor_returns, specific_returns, factor_cov, specific_var, fmp_weights, xs_r2}.parquet; registry entry XS-v1
notebooks/E3_walkthrough.ipynb
Dashboard tab D2 Factor Model and Risk
Dashboard: D2 Factor Model and Risk: factor returns (daily and cumulative), t-stats, cross-sectional R squared over time, descriptor distributions and coverage, factor covariance heatmap and correlation matrix, FMP weights explorer (top and bottom holdings of each FMP), and the Risk Decomposition panel: portfolio selector (seed books or an uploaded CSV of weights), variance split pie, per-factor contribution table, top-20 idio contributors, MCR bar chart, exposures vs limits.
Empirical tests and diagnostics
Tests
Cross-sectional R^2 series and its average (F3.1); FMP identity (F3.2); sector identification (F3.3); agreement with FF factors (F3.4).
Fama-MacBeth premia table with Newey-West t-stats, full sample and by subperiod (2010 to 2015, 2016 to 2020, 2021 to 2026).
Sensitivity: factor returns with and without orthogonalization; sqrt-mcap vs equal weighting; top-300 vs full universe.
Decomposition adds up (F3.5); bias statistic of the two seed books by year (F3.6).
Failure modes to look for
Multicollinearity among descriptors (VIF above 5) making factor returns swap sign between neighbors.
Descriptor coverage gaps that silently change the universe from day to day.
Look-ahead in market cap when shares outstanding are not point-in-time.
Specific returns still correlated within industries: the sector granularity is too coarse and idio risk is overstated.
Why this matters to a PM
PM question: "If I hold this portfolio, how much of my risk is coming from factor exposures I did not intend?"
Problem it addresses. Factor versus idio is the question every multi-manager platform asks of every PM; the platform's risk limits are written in these units.
Decision it informs. Trim or hedge a factor exposure, cap the factor share of variance, and identify which names are pure idio bets.
If the analysis is wrong. A model that attributes factor risk to idio makes a concentrated factor bet look diversified; a model that over-attributes to factors makes the PM hedge away their alpha.
Before trusting the output. Bias statistics (E5), the R^2 series, the FMP identity, agreement with the FF factors, and the same table computed under two weighting schemes.
What would falsify this?
Premia insignificant: acceptable and expected for a risk model, and it is written down; risk factors need not be priced.
Average cross-sectional R^2 below 15%: descriptor construction, weighting or standardization is wrong.
Realized volatility of the seed books outside the 0.8 to 1.25 bias band: the model is not fit to support decisions until E5 finds out why.
Decomposition materially different under equal weighting: the result depends on a methodological choice and the deliverable says so.
Research deliverable
Factor Model Research Note XS-v1 and Factor Exposure and Risk Report (docs/research/E3_factor_model_note.md, E3_risk_report.md)
Model specification, standardization and orthogonalization choices with the sensitivity tables
Fama-MacBeth premia table with the interpretation a PM needs: which factors are priced, which are only risk
The APM risk decomposition table for both seed books with commentary: the unintended bet, the top MCR names, the idio share
A one-paragraph verdict on whether XS-v1 can support decisions, pending E5
Book connection
Chapters. APM Ch5 (fundamental factor models, FMPs), Ch7 (factor risk, exposures); EQI Ch6 (fundamental factor models, factor covariance, specific risk).
Understand before implementing: Why a characteristic can serve as an exposure (the Barra view) instead of an estimated beta (the time-series view), and what each assumes. Why a constraint is needed to identify the market factor next to sector dummies, and what Fama-MacBeth standard errors correct.
What the implementation teaches that the book cannot: Standardization and orthogonalization choices move factor returns by more than the textbook suggests. How much of a stock-picker portfolio is factor once measured, and how sector neutrality arises by construction.
Academic vs practitioner
Academic perspective. Fama-MacBeth is a test of asset pricing: are the premia nonzero, with Shanken-corrected standard errors for estimated betas.
Practitioner perspective. The same regression run daily is a risk model: premia are irrelevant, stability and coverage matter, and the model is judged by bias tests on portfolios, never by t-statistics on premia.
Pre-registered falsification criteria
Numeric thresholds written before the numbers are seen; each is evaluated with a stored number in sprints/E3/RESULTS.json.
ID
Criterion
F3.1
Average daily cross-sectional R squared above 20%. Below 15% means descriptor construction or weighting is wrong, not that the market is unusual.
F3.2
FMP check: X' w_FMP(k) equals the unit vector e_k within 1e-8 for every factor k.
F3.3
Identification: cap-weighted sector factor returns sum to zero within 1e-10 on every day.
F3.4
Agreement with the time-series world: XS-v1 momentum factor return vs FF MOM daily correlation above 0.6; market factor vs Mkt-RF above 0.9.
F3.5
Decomposition adds up: factor variance plus idio variance equals w' Sigma w to machine precision; contributions sum to sigma_p.
F3.6
Bias statistic for both seed portfolios, monthly 2015 to 2026, between 0.8 and 1.25.
F3.7
The Fama-MacBeth premia table is produced with Newey-West t-stats for every factor and subperiod, whatever the verdict; a premium with |t| below 2 is reported as unpriced, not dropped.
Exit criteria
GATE G1 (Sep 20): make rebuild runs E1 through E3 from raw parquet to dashboard D2 in one command; registry holds TS-v1 and XS-v1 with data hashes; all F1 to F3 criteria evaluated with stored numbers; all three walkthroughs rendered and linked. Steps 1 through 3 of the build order are running. Research deliverable written and linked from the Methodology tab.

/quant-prd, Sprint E3
Paste into a fresh Claude session to generate this sprint's PRD and TASKS.

/quant-prd
This is Sprint E3 of the Equity Factor Book (EFB) project. Sprints E1
and E2 outputs exist: data layer, Hygiene Ledger, efb/perf.py, TS-v1
(loadings, idio vol, factor covariance), registry, dashboard tabs D0
and D1. This sprint is the September 20 gate.
Objective:
Build the Barra-style cross-sectional fundamental model, its factor
covariance and specific risk, the full covariance matrix, and the APM
risk decomposition tables. Register XS-v1. Ends with dashboard tab D2.
Focus areas:
- Descriptors from data through t-1: Market (1), Size (log mcap, shares
history flag from ledger), Beta (shrunk, from TS-v1), Momentum (12-1),
Short-term reversal (1m), Residual vol (63d), Liquidity (log 63d dollar
volume), Sector dummies (11 GICS). Value (book/price, yfinance, not
point-in-time) goes into an EXPERIMENTAL variant only. (EQI Ch6)
- Standardization: winsorize at +/- 3 MAD cross-sectionally; z-score
with cap-weighted mean, equal-weighted std
- Daily WLS: r_t = X_{t-1} f_t + e_t, weights sqrt(mcap), constraint
that cap-weighted sector factor returns sum to zero
- Factor-mimicking portfolios: rows of (X'WX)^-1 X'W (APM Ch5)
- Factor covariance F: EWMA half-life 90d, Newey-West lag 2
- Specific variance D: EWMA of e^2 half-life 42d, Bayesian shrinkage
toward sector-size bucket mean
- Sigma = X F X' + D; risk decomposition for any w: total, factor by
factor, idio; MCR_i = (Sigma w)_i / sigma_p; contribution w_i * MCR_i;
percent of variance; APM-style table; exposures x = X'w (APM Ch7)
- Seed portfolios: sector-neutral L/S momentum quintile book; 20-name
concentrated long book
Requirements:
- Exact formulas for every step with inputs and outputs labeled,
including the constrained WLS solution (state the constraint matrix)
- Parquet schemas for data/models/XS-v1/{descriptors, factor_returns,
specific_returns, factor_cov, specific_var, fmp_weights, xs_r2}
- Registry entry XS-v1 with parameters and data hash
- Pre-registered criteria F3.1 to F3.6 copied verbatim
- Dashboard D2 spec: factor returns daily and cumulative, t-stats,
cross-sectional R^2 series, descriptor distributions and coverage,
factor covariance heatmap, FMP explorer, and the Risk Decomposition
panel (portfolio selector including CSV upload, variance split,
per-factor contribution table, top-20 idio contributors, MCR bar
chart, exposures vs limits); reads parquet only
- Max 10 atomic tasks, each with a test
- Extend the one-command rebuild: make rebuild runs E1 to E3
Output:
- sprints/E3/PRD.md
- sprints/E3/TASKS.md
Research framing (from the roadmap, copy into the PRD verbatim):
- Academic question: How can cross-sectional equity returns be decomposed into systematic factor exposures and idiosyncratic returns, and are the factor premia (Fama-MacBeth) distinguishable from zero?
- Practitioner question: If I hold this portfolio, how much of my risk is actually coming from unintended factor exposures, and which position reduces risk fastest if trimmed?
- Research question: Does the proposed risk model explain realized portfolio returns and volatility adequately enough to support portfolio decisions?
- Research deliverable: Factor Model Research Note XS-v1 and Factor Exposure and Risk Report, written for
a senior quant or risk manager; it must contain the methodology, the
stored numbers, the practitioner conclusion, and a section titled
"What would falsify this?". A negative verdict is a complete
deliverable.
- The TASKS.md must include one task that produces the deliverable and
one that evaluates every falsification criterion listed below.

/quant-dev, Sprint E3
Run iteratively on the highest-priority open task.

/quant-dev

Sprint E3, Cross-Sectional Fundamental Model and Risk Decomposition.
Work on the highest priority open task in sprints/E3/TASKS.md.
Process:
1. Implement with type hints, docstrings, and a unit test. For the WLS
and FMP code, test first on a synthetic cross-section with known
factor returns and confirm recovery.
2. Validate with numbers:
- descriptor z-scores for AAPL, XOM, JPM on the last date, with the
raw value, the winsorized value, the cap-weighted mean and the
equal-weighted std used
- factor returns f_t on the last date with t-stats; cross-sectional
R^2 on that date and its average (F3.1)
- X' w_FMP(k) for every k, max abs deviation from e_k (F3.2)
- cap-weighted sum of sector factor returns, max abs over all days
(F3.3)
- correlation of XS momentum and market factor returns with FF MOM
and Mkt-RF (F3.4)
- for both seed portfolios: factor variance, idio variance, their sum
vs w' Sigma w (F3.5), the full APM table, the top-5 MCR names
- bias statistics for both seed portfolios by year (F3.6)
3. Look-ahead check: descriptors dated t use prices through t-1 only;
returns regressed on date t use X_{t-1}.
4. Check NaNs (descriptor coverage per day), singularity (sector with
one member), and index alignment with TS-v1 outputs.
5. Store any F3.x number in sprints/E3/RESULTS.json.
Output:
- Code summary
- Validation numbers (printed values)
- F criteria touched: pass, fail, or pending, with the stored number
- Issues or blockers
- Next task recommendation

/quant-walkthrough, Sprint E3
Run once the exit criteria are met. The notebook is the promotion artifact for the model version and the evidence behind the research deliverable.

/quant-walkthrough

Sprint E3 is complete and this is the September 20 gate. Write
notebooks/E3_walkthrough.ipynb.
Purpose: reproduce the cross-sectional model and the risk decomposition
by hand, on a 10-name sub-universe, so that every table in dashboard D2
is a number I can derive.
Sections:
1. Descriptors by hand for 10 names on one date: raw value, winsorized
value, cap-weighted mean, equal-weighted std, z-score. Label INPUT
columns and OUTPUT columns. Match XS-v1/descriptors.parquet.
2. One day of WLS by hand: build X (10 x K), W (sqrt mcap), the
constraint matrix, and solve for f_t with explicit numpy. Print f_t
next to XS-v1/factor_returns.parquet for that date. Then the
specific returns e_t and the cross-sectional R^2.
3. Factor-mimicking portfolios: compute (X'WX)^-1 X'W, show each row is
a portfolio, verify X' w_FMP(k) = e_k, and print the largest long and
short weights of the momentum FMP.
4. Covariance: F from the EWMA recursion for 3 days by hand with the
Newey-West adjustment shown; D for three names with the shrinkage
weight computed; assemble Sigma = X F X' + D and print its shape.
5. Risk decomposition for the 20-name long book: total variance, the
factor-by-factor table, idio, MCR for every name, contributions
summing to sigma_p, and the APM-style table reproduced exactly.
6. One section per F3.x criterion: threshold, stored number, verdict.
7. Dashboard D2: map each panel to its parquet column.
8. Credit port note: the descriptor set becomes duration (or DTS),
spread level, rating bucket dummies, sector dummies, issue size, age
and liquidity, spread momentum; the WLS, FMP, covariance and
decomposition code are unchanged. Write the credit X matrix
schematically for three bonds.
No em dashes anywhere. Render to HTML and link from the Methodology tab.

Sprint E4: Statistical Factor Models and the Covariance Lab
Mon Sep 21 to Sun Sep 27. Tier 2.
Stage: Risk researcher: how many factors, and which covariance
Book coverage: EQI Ch4 (starred sections on estimation), Ch7 (statistical factor models). APM Ch5 (statistical models).
Research questions
Academic. How many common factors are in equity returns, and how should a large covariance matrix be estimated when N is comparable to T?
Practitioner. Which covariance estimator gives portfolios that behave out of sample the way the estimator predicted?
Research. Do statistical factors capture risk the fundamental model misses, and does a blended model beat either alone?
Objective
Add the third model family (PCA) and a laboratory that compares covariance estimators on the same universe, so that every later choice of Sigma is a measured choice. Formalize the model registry and the dashboard version selector.
Academic concept and intuition
Concept. Eigendecomposition and PCA as dimensionality reduction; the Marchenko-Pastur law as the boundary between signal and noise eigenvalues; linear shrinkage (Ledoit-Wolf) toward a structured target; the precision matrix as the object an optimizer actually consumes; residual PCA on XS-v1 specific returns as a missing-factor detector.
Intuition. With N = 500 names and T = 500 days, the smallest eigenvalues of the sample covariance are noise, and an optimizer loves noise: it puts weight in spuriously low-variance directions. PCA finds the directions of common variation but does not name them; Marchenko-Pastur says where noise begins; shrinkage pulls the estimate toward something structured and pays a little bias for a lot less variance.
Foundation
The formulas the sprint implements; inputs and outputs are labeled in the walkthrough.
Sample covariance S = (1/T) R'R; eigendecomposition S = Q Lambda Q'; PCA model Sigma_k = Q_k Lambda_k Q_k' + diag(residual variance).
Marchenko-Pastur edge lambda_plus = sigma^2 (1 + sqrt(N/T))^2; eigenvalues above it are treated as factors.
Ledoit-Wolf: Sigma_LW = delta F + (1 - delta) S with delta estimated; eigenvalue clipping replaces noise eigenvalues by their mean.
Minimum-variance test portfolio: w = Sigma^-1 1 / (1' Sigma^-1 1), realized out-of-sample vol by estimator.
Implementation scope
PCA on total returns and on XS-v1 residuals; number of factors by scree, Marchenko-Pastur edge, and cross-validated likelihood; factor rotation for interpretability; PCA-v1 registered. Probabilistic PCA or factor analysis via EM as an optional task.
Covariance estimator zoo: sample, EWMA, Ledoit-Wolf linear shrinkage, constant-correlation shrinkage, eigenvalue clipping (RMT), TS-v1, XS-v1, PCA-v1; optional graphical lasso for the precision matrix.
The classic estimation-error test: out-of-sample minimum-variance portfolio volatility by estimator (N about 500, rolling 504-day windows).
Registry formalized: registry.json schema, champion flag, and a dashboard-wide version selector so every tab can be viewed under any model version.
Deliverables and dashboard increment
efb/models/statistical.py, efb/cov.py (estimator zoo), efb/registry.py v1
data/models/PCA-v1/{loadings, factor_returns, eigenvalues}.parquet; data/cov/{estimator}/ artifacts
notebooks/E4_walkthrough.ipynb; Dashboard tab D3 Covariance Lab
Dashboard: D3 Covariance Lab: eigenvalue spectrum vs the Marchenko-Pastur edge, explained variance curve, PCA-factor vs fundamental-factor correlation matrix, estimator comparison table (OOS min-variance vol, condition number, parameter count), global model-version selector wired into every existing tab.
Empirical tests and diagnostics
Tests
Out-of-sample minimum-variance vol horse race across estimators (F4.3); condition numbers.
Marchenko-Pastur factor count (F4.2); first PC vs market (F4.1).
Residual PCA on XS-v1 specific returns: is the largest residual eigenvalue above the MP edge? If so, a factor is missing.
Stability of PCA loadings across rolling windows (sign alignment, subspace overlap).
Failure modes to look for
Eigenvector instability and sign indeterminacy making PCA factors unusable for hedging.
Factor count k sensitive to the window; PCA factors mixing sectors and styles so no PM can name them.
Ill-conditioned Sigma producing leveraged, opposite positions in near-duplicate names.
Why this matters to a PM
PM question: "Which covariance matrix should the optimizer and the hedges actually use?"
Problem it addresses. An optimizer is a machine for exploiting covariance errors; the estimator choice decides whether the portfolio is what the PM thinks it is.
Decision it informs. Which Sigma feeds the optimizer and the hedges, and whether the fundamental model needs statistical factors added.
If the analysis is wrong. Leveraged positions in noise directions that look low risk until a stress day; hedges built on an unstable factor that flips sign.
Before trusting the output. The out-of-sample minimum-variance test, the condition number, and the E5 bias tests on the portfolios actually held.
What would falsify this?
Sample covariance wins out of sample: an estimation bug, since theory says it cannot with N near T.
Residual PCA finds a strong factor: XS-v1 is missing something, and XS-v2 adds a descriptor or an industry split.
PCA loadings unstable across windows: statistical factors are kept for diagnostics and excluded from hedging.
Research deliverable
Covariance Estimator Comparison and Residual Factor Audit (docs/research/E4_covariance_memo.md)
The horse-race table with a recommendation per use: optimizer, hedging, risk reporting
The residual factor audit: what, if anything, the fundamental model is missing
The registry decision: which versions are candidates for E5
Book connection
Chapters. EQI Ch4 (starred estimation sections), Ch7 (statistical factor models); APM Ch5 (statistical models).
Understand before implementing: What an eigenvalue of a covariance matrix means, and why N/T decides how many are trustworthy. Why shrinkage improves an estimator that is already unbiased.
What the implementation teaches that the book cannot: The number that matters is out-of-sample portfolio volatility, not in-sample explained variance. Statistical factors are excellent detectors and poor explanations.
Academic vs practitioner
Academic perspective. Optimal shrinkage intensity and random-matrix theory, with the sample covariance as the benchmark.
Practitioner perspective. Vendors blend fundamental and statistical factors; the choice is dominated by stability and by whether a PM can be told what the factor is.
Pre-registered falsification criteria
Numeric thresholds written before the numbers are seen; each is evaluated with a stored number in sprints/E4/RESULTS.json.
ID
Criterion
F4.1
First principal component vs the market factor: correlation above 0.95.
F4.2
Marchenko-Pastur edge isolates between 3 and 15 significant factors; the count is stored.
F4.3
OOS minimum-variance vol: shrinkage and factor estimators beat the sample covariance by more than 10%. If the sample covariance wins, that is an estimation bug.
F4.4
PCA-v1 with k factors explains at least as much cross-sectional variance as XS-v1 on a held-out residual test; both numbers stored.
Exit criteria
F4 evaluated; version selector works on D0 to D3; walkthrough rendered. Research deliverable written and linked from the Methodology tab.

/quant-prd, Sprint E4
Paste into a fresh Claude session to generate this sprint's PRD and TASKS.

/quant-prd
This is Sprint E4 of the Equity Factor Book (EFB) project. E1 to E3
exist: data layer, TS-v1, XS-v1, efb/risk.py, dashboard D0 to D2,
registry v0.
Objective:
Add statistical factor models (PCA) as the third model family and build
a Covariance Lab that compares estimators on the same universe. Register
PCA-v1. Formalize the registry with a champion flag and add a global
model-version selector to the dashboard. Ends with dashboard tab D3.
Focus areas:
- PCA on total returns and on XS-v1 residuals; number of factors via
scree, Marchenko-Pastur edge, cross-validated likelihood; rotation for
interpretability (EQI Ch7)
- Optional: probabilistic PCA / factor analysis via EM
- Estimator zoo in efb/cov.py: sample, EWMA, Ledoit-Wolf, constant
correlation, eigenvalue clipping, TS-v1, XS-v1, PCA-v1; optional
graphical lasso precision matrix (EQI Ch4 starred sections)
- OOS minimum-variance vol test by estimator, rolling 504-day windows
- Registry v1: schema with champion flag; dashboard version selector
Requirements:
- Exact formulas: PCA via SVD of the standardized return matrix,
Marchenko-Pastur edge, Ledoit-Wolf shrinkage intensity, clipping rule
- Parquet schemas for PCA-v1 and for each estimator's artifacts
- Pre-registered criteria F4.1 to F4.4 copied verbatim
- Dashboard D3 spec: eigenvalue spectrum vs MP edge, explained variance,
PCA vs fundamental factor correlation matrix, estimator comparison
table, global version selector wired into D0 to D2
- Max 10 atomic tasks, each with a test
Output:
- sprints/E4/PRD.md
- sprints/E4/TASKS.md
Research framing (from the roadmap, copy into the PRD verbatim):
- Academic question: How many common factors are in equity returns, and how should a large covariance matrix be estimated when N is comparable to T?
- Practitioner question: Which covariance estimator gives portfolios that behave out of sample the way the estimator predicted?
- Research question: Do statistical factors capture risk the fundamental model misses, and does a blended model beat either alone?
- Research deliverable: Covariance Estimator Comparison and Residual Factor Audit, written for
a senior quant or risk manager; it must contain the methodology, the
stored numbers, the practitioner conclusion, and a section titled
"What would falsify this?". A negative verdict is a complete
deliverable.
- The TASKS.md must include one task that produces the deliverable and
one that evaluates every falsification criterion listed below.

/quant-dev and /quant-walkthrough, Sprint E4
Use the generic templates from the "How to use this document" section with <n> = 4 and the dashboard tab named above. Add the sprint's tests and failure modes to step 3 of /quant-dev and the research deliverable to the walkthrough's final section.

Sprint E5: Risk Model Evaluation
Mon Sep 28 to Sun Oct 4. Tier 2. Gate: G2, champion risk model.
Stage: Risk researcher: can the risk number be trusted
Book coverage: EQI Ch5 (evaluating risk models). APM Ch3 and Ch7 (what a good risk number looks like).
Research questions
Academic. How do we test whether a covariance forecast is calibrated, at the portfolio level and across horizons?
Practitioner. Can I trust the risk number I am looking at, and by how much does it underforecast when I need it most?
Research. Which model version is best calibrated across portfolio types and regimes, and how much worse is every model in stress?
Objective
Test every model version the way a vendor model would be tested: bias statistics, coverage, calibration, and horizon consistency across families of portfolios. Declare a champion by a rule written down before the numbers are seen.
Academic concept and intuition
Concept. Bias statistics on standardized returns, coverage and calibration tests, horizon consistency, and regime analysis (calm versus stress, defined ex ante by VIX terciles and by named episodes: 2020 Q1, 2022).
Intuition. A risk model is a forecast of a distribution's scale. If realized over predicted volatility averages one and does not drift across portfolio types, the model is usable. Every model underforecasts entering a stress episode because volatility jumps faster than any half-life; the question is how badly and how fast it recovers.
Foundation
The formulas the sprint implements; inputs and outputs are labeled in the walkthrough.
Standardized return z_t = r_t / sigma_hat_{t|t-1}; bias B = sqrt(mean z^2), with an approximate confidence band of 1 plus or minus sqrt(1/(2T)) under normality.
Coverage: share of |z| above 1.96 (nominal 5%); Q-Q of z; MAD ratio mean|z| / 0.798.
Horizon: a 1-day model scaled by sqrt(21) vs a directly estimated 21-day model.
Regime split: bias computed within VIX terciles and within named episodes, on random portfolio families and the seed books.
Implementation scope
Bias statistics per model version on random portfolios (long-only, long/short, factor-tilted, sector-concentrated) and on the seed books; standardized returns z_t = r_t / predicted sigma_t; bias = std(z) with confidence bands; rolling 12-month windows.
Coverage and calibration: share of |z| above 1.96, Q-Q plots, mean absolute deviation ratio; portfolio level and asset level.
Horizon consistency: 1-day model scaled to 21 days vs a directly estimated 21-day model.
Champion rule, pre-registered: minimize mean |bias minus 1| across portfolio families; ties broken by fewer parameters. The decision and the number go into the registry.
New in v2: Regime analysis: bias, coverage and recovery time computed within VIX terciles and named episodes (2020 Q1, 2022), so the stress behaviour of each model version is a table, not an anecdote.
Deliverables and dashboard increment
efb/eval_risk.py; data/eval/bias_{model}_{family}.parquet
notebooks/E5_walkthrough.ipynb; Dashboard tab D4 Risk Model Evaluation
Dashboard: D4 Risk Model Evaluation: bias statistic heatmap (model version x portfolio family), rolling bias charts with bands, calibration and Q-Q plots, horizon-consistency table, champion badge with the rule and the number that decided it.
Empirical tests and diagnostics
Tests
Bias heatmap: model version x portfolio family x regime (F5.1, F5.2, F5.3).
Rolling 12-month bias with bands; recovery time after 2020 Q1 by half-life.
Coverage and Q-Q by model; horizon-consistency table.
Failure modes to look for
Bias driven by a handful of days; the average hides a fat tail.
Portfolio families built with look-ahead (today's factor loadings) that flatter the model.
Half-lives chosen on the same period they are tested on: the champion is snooped.
Why this matters to a PM
PM question: "Can I trust the risk number I am looking at, and when does it lie?"
Problem it addresses. The risk number sets position sizes, limits and leverage; a platform's drawdown rules are triggered by it.
Decision it informs. Which model is champion, what haircut to apply in stress, and whether long/short books need a different specific-risk treatment than long-only.
If the analysis is wrong. An under-risked book entering a crisis, or an over-risked book that never uses its budget.
Before trusting the output. The bias heatmap across families and regimes, not one average; a champion chosen by a rule fixed before the numbers.
What would falsify this?
No model version inside 0.9 to 1.1 on average: none is fit for decisions, and the sprint documents the gap and the candidate fix (shorter half-life, specific-risk shrinkage).
Bias differing strongly by family: the model is fine for long-only and poor for long/short, which points at specific risk.
Stress-regime bias above 1.5 for every model: the deliverable recommends a stress haircut rather than pretending.
Research deliverable
Risk Model Diagnostic Report (docs/research/E5_risk_model_diagnostic.md)
Champion decision with the rule and the number; the full heatmap
Regime table and recovery times; the recommended stress haircut
Known weaknesses of the champion and what XS-v2 or PCA-v2 should change
Book connection
Chapters. EQI Ch5 (evaluating risk models); APM Ch3 and Ch7 (what a good risk number looks like).
Understand before implementing: What a calibrated forecast means and why bias, not R^2, is the metric. Why risk models are tested on portfolios rather than on single assets.
What the implementation teaches that the book cannot: The regime dimension: averages hide the only days that matter. Champion selection is a governance act; the rule must precede the numbers.
Academic vs practitioner
Academic perspective. Likelihood-based model comparison and asymptotic tests on the covariance estimator.
Practitioner perspective. Bias statistics on the portfolios actually held, and the champion is whichever model the PM will still trust in a drawdown.
Pre-registered falsification criteria
Numeric thresholds written before the numbers are seen; each is evaluated with a stored number in sprints/E5/RESULTS.json.
ID
Criterion
F5.1
At least one model version achieves mean bias between 0.9 and 1.1 across all portfolio families.
F5.2
Factor-based models beat the sample covariance on bias for long/short portfolios.
F5.3
Bias is worst in 2020 Q1 for every model. This is expected and is reported, not hidden.
F5.4
Regime table produced for every model version; the champion's stress-regime bias and its recovery time in trading days are stored alongside its average bias.
Exit criteria
GATE G2: champion risk model declared in the registry with the deciding number; D4 rendered; walkthrough rendered. Research deliverable written and linked from the Methodology tab.

/quant-prd, Sprint E5
Paste into a fresh Claude session to generate this sprint's PRD and TASKS.

/quant-prd
This is Sprint E5 of the Equity Factor Book (EFB) project. E1 to E4
exist: three model families (TS-v1, XS-v1, PCA-v1), the estimator zoo,
registry v1, dashboard D0 to D3 with a version selector.
Objective:
Evaluate every model version like a vendor model: bias statistics,
coverage, calibration and horizon consistency across portfolio families,
and declare a champion by a rule fixed before the numbers are seen.
Ends with dashboard tab D4 and the champion flag set. (EQI Ch5)
Focus areas:
- Random portfolio families: long-only, long/short, factor-tilted,
sector-concentrated; plus the seed books
- Standardized returns z_t = r_t / sigma_hat_t; bias = std(z) with
confidence bands; rolling 12m windows
- Coverage (share |z| > 1.96), Q-Q, MAD ratio; portfolio and asset level
- Horizon consistency: 1d scaled to 21d vs direct 21d
- Champion rule: minimize mean |bias - 1| across families; ties broken
by fewer parameters; write the rule into registry.json before running
Requirements:
- Exact formulas for bias, its confidence band, coverage, MAD ratio
- Parquet schemas for data/eval/bias_{model}_{family}.parquet
- Pre-registered criteria F5.1 to F5.3 copied verbatim
- Dashboard D4 spec: bias heatmap (model x family), rolling bias with
bands, calibration and Q-Q, horizon table, champion badge with rule
and number
- Max 10 atomic tasks, each with a test
Output:
- sprints/E5/PRD.md
- sprints/E5/TASKS.md
Research framing (from the roadmap, copy into the PRD verbatim):
- Academic question: How do we test whether a covariance forecast is calibrated, at the portfolio level and across horizons?
- Practitioner question: Can I trust the risk number I am looking at, and by how much does it underforecast when I need it most?
- Research question: Which model version is best calibrated across portfolio types and regimes, and how much worse is every model in stress?
- Research deliverable: Risk Model Diagnostic Report, written for
a senior quant or risk manager; it must contain the methodology, the
stored numbers, the practitioner conclusion, and a section titled
"What would falsify this?". A negative verdict is a complete
deliverable.
- The TASKS.md must include one task that produces the deliverable and
one that evaluates every falsification criterion listed below.

/quant-dev and /quant-walkthrough, Sprint E5
Use the generic templates from the "How to use this document" section with <n> = 5 and the dashboard tab named above. Add the sprint's tests and failure modes to step 3 of /quant-dev and the research deliverable to the walkthrough's final section.

Sprint E6: Hedging
Mon Oct 5 to Sun Oct 11. Tier 2.
Stage: Portfolio and risk researcher: removing what you do not want to own
Book coverage: APM Ch4 (beta hedging), Ch7 (managing factor risk). EQI Ch12 (hedging).
Research questions
Academic. What is the minimum-variance hedge of a portfolio under a factor model with a restricted set of tradeable instruments, and how does it relate to the factor-mimicking portfolios?
Practitioner. How much unwanted beta and factor exposure can I remove with instruments I can actually trade, and what does the hedge cost in turnover, borrow and basis risk?
Research. Do model-implied hedges reduce realized factor P&L of the seed books, and how does hedge efficacy decay between rebalances?
Objective
Neutralize the factors you do not want and keep the idio you do: beta hedges, factor-neutral hedges via FMPs, minimum-variance hedges with a restricted instrument set, partial hedges, and the cost of each.
Academic concept and intuition
Concept. Hedging as projection: the exposure vector of a portfolio is projected onto the span of the hedge instruments; the FMP hedge is exact in-model, the ETF hedge is a regression with a residual; partial hedges, rebalancing frequency, and the cost of a hedge.
Intuition. Hedging is regression. You project the portfolio's factor exposure onto what you can trade; SPY and sector ETFs span the market and sectors but not momentum or size, so a residual factor exposure always remains. A hedge is a forecast of exposure, so it decays as exposures drift, and every rebalance costs.
Foundation
The formulas the sprint implements; inputs and outputs are labeled in the walkthrough.
Restricted hedge: h* = -(H' Sigma H)^-1 H' Sigma w, residual variance w' Sigma w - w' Sigma H (H' Sigma H)^-1 H' Sigma w (INPUT: champion Sigma, instrument returns; OUTPUT: hedge/{portfolio}_{method}).
FMP hedge: w_hedged = w - sum_k x_k FMP_k, with x = X'w; exact in-model, expensive in names.
Beta hedge as the one-instrument special case: h = -beta_p; partial hedge h = -c beta_p with c in [0, 1].
Hedge cost = turnover x cost model (E9 provisional constants) + borrow on short instruments; efficacy = share of factor variance removed.
Implementation scope
Beta hedge with SPY and sector ETFs: hedge ratio equals minus the portfolio beta; residual risk after the hedge.
Factor-neutral hedge via FMPs: given exposures x = X'w, subtract x_k times the k-th FMP; hedge portfolio, its turnover and borrow, residual idio share.
Minimum-variance hedge with a restricted instrument set H (SPY, IWM, QQQ, sector SPDRs): h* = minus (H' Sigma H)^-1 H' Sigma w; tracking error before and after.
Partial hedges and hedge rebalancing frequency vs cost; hedge efficacy measured on realized factor PnL of hedged vs unhedged seed books.
Deliverables and dashboard increment
efb/hedge.py; data/hedge/{portfolio}_{method}.parquet
notebooks/E6_walkthrough.ipynb; Dashboard tab D5 Hedging Lab
Dashboard: D5 Hedging Lab: pick a portfolio and an instrument set, see risk decomposition before and after, hedge weights, exposure bars pre and post, residual tracking error, estimated hedge cost, and a rebalancing-frequency slider.
Empirical tests and diagnostics
Tests
In-model efficacy: exposures after FMP hedge (F6.1); factor variance removed by the ETF hedge (F6.2).
Realized efficacy: beta and factor P&L of the hedged momentum book 2018 to 2026 (F6.3); efficacy vs rebalancing frequency.
Hedge-ratio stability day to day; basis risk of sector ETFs vs the model's sector factors.
Failure modes to look for
Overfitting the hedge with too many instruments, buying noise exposures.
Hedge cost exceeding the value of the variance removed for weak exposures.
Basis risk: the ETF's factor is not the model's factor.
Why this matters to a PM
PM question: "How much unwanted beta can I remove, and what does the hedge cost me?"
Problem it addresses. Platforms enforce tight factor limits; a PM who cannot hedge cannot hold the idio bet they want.
Decision it informs. Which exposures to hedge, with which instruments, how often, and how far (partial vs full).
If the analysis is wrong. Over-hedging removes alpha along with risk; an unstable hedge adds turnover and basis risk while appearing to reduce exposure.
Before trusting the output. Realized beta of the hedged book near zero, hedge cost accounted, and the residual exposure the instruments cannot reach stated explicitly.
What would falsify this?
The hedged book's realized beta is not near zero: the model exposures or the hedge ratios are wrong.
Hedge cost exceeds the variance removed in value terms: the hedge is not worth it and the deliverable says which exposures to leave.
Hedge ratios unstable day to day: the exposure forecast is too noisy to act on daily; weekly hedging is recommended.
Research deliverable
Hedge Effectiveness Study (docs/research/E6_hedge_study.md)
Before and after decompositions for both seed books under FMP and ETF hedges
Efficacy vs rebalancing frequency and the cost curve
Recommended hedge policy: which factors, which instruments, which cadence
Book connection
Chapters. APM Ch4 (beta hedging), Ch7 (managing factor risk); EQI Ch12 (hedging).
Understand before implementing: Why the single-factor hedge ratio is beta, and how the multi-factor generalization is the same projection. Why the FMP hedge is exact in-model and unusable in practice.
What the implementation teaches that the book cannot: The spanning limits of tradeable instruments. That a hedge is a forecast and decays.
Pre-registered falsification criteria
Numeric thresholds written before the numbers are seen; each is evaluated with a stored number in sprints/E6/RESULTS.json.
ID
Criterion
F6.1
Full FMP hedge drives every factor exposure below 1e-6 in absolute value and lifts the idio share of variance above 95%.
F6.2
ETF minimum-variance hedge removes more than 70% of the factor variance of the long-only seed book. ETFs cannot span every factor; the residual is reported.
F6.3
Realized: the hedged momentum long/short book has a beta to Mkt-RF within plus or minus 0.1 over 2018 to 2026.
Exit criteria
F6 evaluated; D5 rendered; walkthrough rendered. Research deliverable written and linked from the Methodology tab.

/quant-prd, Sprint E6
Paste into a fresh Claude session to generate this sprint's PRD and TASKS.

/quant-prd
This is Sprint E6 of the Equity Factor Book (EFB) project. E1 to E5
exist, including a champion risk model in the registry and dashboard
D0 to D4.
Objective:
Build the hedging toolkit: beta hedges, factor-neutral hedges via FMPs,
minimum-variance hedges with a restricted instrument set, partial
hedges, with the cost of each measured. Ends with dashboard tab D5.
(APM Ch4, Ch7; EQI Ch12)
Focus areas:
- Beta hedge with SPY and sector ETFs; residual risk after hedge
- FMP hedge: x = X'w, subtract sum_k x_k * FMP_k; turnover, borrow,
residual idio share
- Min-variance hedge with instruments H: h* = -(H' Sigma H)^-1 H' Sigma w
using the champion Sigma; tracking error before and after
- Partial hedge fraction and rebalancing frequency vs cost
- Efficacy on realized factor PnL of hedged vs unhedged seed books
Requirements:
- Exact formulas with inputs and outputs labeled; state which Sigma
version each hedge uses
- Parquet schemas for data/hedge/{portfolio}_{method}.parquet
- Pre-registered criteria F6.1 to F6.3 copied verbatim
- Dashboard D5 spec: portfolio and instrument selectors, before and
after decomposition, hedge weights, exposure bars, residual TE, cost
estimate, rebalancing slider
- Max 10 atomic tasks, each with a test
Output:
- sprints/E6/PRD.md
- sprints/E6/TASKS.md
Research framing (from the roadmap, copy into the PRD verbatim):
- Academic question: What is the minimum-variance hedge of a portfolio under a factor model with a restricted set of tradeable instruments, and how does it relate to the factor-mimicking portfolios?
- Practitioner question: How much unwanted beta and factor exposure can I remove with instruments I can actually trade, and what does the hedge cost in turnover, borrow and basis risk?
- Research question: Do model-implied hedges reduce realized factor P&L of the seed books, and how does hedge efficacy decay between rebalances?
- Research deliverable: Hedge Effectiveness Study, written for
a senior quant or risk manager; it must contain the methodology, the
stored numbers, the practitioner conclusion, and a section titled
"What would falsify this?". A negative verdict is a complete
deliverable.
- The TASKS.md must include one task that produces the deliverable and
one that evaluates every falsification criterion listed below.

/quant-dev and /quant-walkthrough, Sprint E6
Use the generic templates from the "How to use this document" section with <n> = 6 and the dashboard tab named above. Add the sprint's tests and failure modes to step 3 of /quant-dev and the research deliverable to the walkthrough's final section.

Sprint E7: Alpha Lab and Backtest Hygiene
Mon Oct 12 to Sun Oct 18. Tier 2.
Stage: Portfolio researcher: evaluating information without fooling yourself
Book coverage: APM Ch6 (expected returns as the sizing input), Appendix (momentum, short interest). EQI Ch8 (evaluating excess returns, data snooping, backtesting).
Research questions
Academic. How is the information content of a signal measured, and how are the standard errors adjusted for the number of things tried?
Practitioner. Does this signal contain information beyond the factors I already know about, at a horizon I can trade, after costs?
Research. Do any of the candidate signals show factor-neutral, out-of-sample, cost-surviving information, and does a negative result change what the book does?
Objective
Build the harness that turns a signal into an expected return honestly: information coefficients, decay, factor-neutral quantile returns, the fundamental law check, and a multiple-testing ledger that records every variant tried. No edge is claimed; the harness is the deliverable.
Academic concept and intuition
Concept. The information coefficient; the fundamental law IR approximately IC x sqrt(breadth); factor neutralization (a signal residualized on the risk factors: does it survive controlling for known factors?); decay and turnover; regime-conditional IC; multiple-testing corrections (Bonferroni, deflated Sharpe, the Harvey-Liu-Zhu hurdle); the conversion of a score into an expected return (Grinold).
Intuition. An IC of 0.03 is real only with large breadth and only if it survives neutralization; a signal correlated with momentum is momentum in disguise. With twenty variants tried, one will pass at 5% by construction. Turnover is the price of the horizon: a signal that decays in five days cannot be traded at monthly cost.
Foundation
The formulas the sprint implements; inputs and outputs are labeled in the walkthrough.
IC_t = rank-corr(s_{t-1}, r_t); IC decay at horizons 1, 5, 21, 63; fundamental law IR approx IC x sqrt(N_effective).
Neutralization: s_perp = s - X (X'X)^-1 X' s, X the risk-factor exposures; quantile portfolios built on s_perp and hedged with FMPs.
Multiple testing: Bonferroni t-threshold for M variants; deflated Sharpe ratio; HLZ hurdle |t| above 3.
Expected return: alpha_i = IC x sigma_idio,i x z_i, shrunk by kappa toward zero (OUTPUT: data/alpha, the E8 input contract).
Implementation scope
Signals, all experimental: momentum 12-1, short-term reversal, idio momentum (on XS residuals), low residual volatility, short interest (FINRA, probe first), post-earnings drift (yfinance earnings dates, probe first).
Evaluation: Spearman IC time series, IC decay by horizon (1, 5, 21, 63 days), factor-neutral quantile portfolios via FMPs, turnover, hit rate; fundamental-law check IR approximately IC x sqrt(breadth) against realized IR.
Backtest hygiene ledger: shift audit (every signal moved forward one day must lose its IC), survivorship number from E1, point-in-time flags, a multiple-testing ledger with every variant, Bonferroni-adjusted t-stats and a deflated Sharpe, the Harvey-Liu-Zhu hurdle of t above 3.
Alpha conversion: alpha_i = IC x sigma_idio,i x z_i (Grinold), with shrinkage toward zero; this is the input contract for E8 sizing.
New in v2: Regime-conditional IC: every signal's IC reported within VIX terciles and named episodes, so a signal that only works in calm markets is labeled as such.
Deliverables and dashboard increment
efb/alpha.py, efb/hygiene.py; data/alpha/{signal}/{ic, quantiles, decay}.parquet; docs/multiple_testing_ledger.md
notebooks/E7_walkthrough.ipynb; Dashboard tab D6 Alpha Lab
Dashboard: D6 Alpha Lab: signal selector, IC time series with t-stat, decay curve, quantile spread charts raw vs factor-neutral, turnover, the multiple-testing ledger as a table, and an expected-return calculator whose inputs (IC, idio vol, z-score, shrinkage) and outputs (alpha in bp per day) are labeled on screen.
Empirical tests and diagnostics
Tests
Shift audit (F7.1); in-sample vs out-of-sample IC with t-stats (F7.2); the multiple-testing ledger (F7.3).
IC by regime (VIX terciles) and by subperiod; sensitivity to universe and weighting.
Raw vs factor-neutral quantile spreads; turnover and break-even cost per signal.
Failure modes to look for
Leakage through descriptors computed with same-day data or through survivorship in the universe.
Horizon snooping: the best-looking decay horizon chosen after the fact.
A signal that is a known factor with extra steps.
Why this matters to a PM
PM question: "Does this signal contain information beyond the risks I already know about, and after costs?"
Problem it addresses. Expected returns are the scarce input; everything downstream is a transformation of them.
Decision it informs. Which signals earn a seat in construction, at what horizon, and whether the PM already owns this risk elsewhere.
If the analysis is wrong. Trading noise with real costs; loading a factor risk unknowingly; concentrating in the one period a signal worked.
Before trusting the output. Out-of-sample, factor-neutral, cost-surviving results, and a ledger listing everything that was tried, including what failed.
What would falsify this?
Unstable or period-dependent IC; weak out-of-sample IC; IC that vanishes after neutralization.
Excessive turnover relative to decay; break-even cost below realistic costs.
Sensitivity to universe or weighting choices; a deflated Sharpe below the hurdle.
Every signal NULL: a successful sprint. The construction machinery in E8 then runs on synthetic alpha with a known IC (Research Gate RG-Signal).
Research deliverable
Signal Evaluation Report, one per signal, with the Multiple-Testing Ledger (docs/research/E7_signal_{name}.md, docs/multiple_testing_ledger.md)
Hypothesis, economic rationale, construction, IC and decay tables, regime and subperiod tables, neutralized results
Verdict: PASS or NULL against the RG-Signal checklist, with the number that decided it
Negative results kept in full; the ledger row count equals the number of runs
Book connection
Chapters. EQI Ch8 (evaluating excess returns, backtesting, data snooping); APM Ch6 (expected returns as the sizing input) and Appendix (momentum, short interest).
Understand before implementing: The fundamental law and what breadth really counts. Why deflating a Sharpe ratio for the number of trials is not optional.
What the implementation teaches that the book cannot: How quickly results evaporate under hygiene. That the harness, not the signal, is the asset.
Academic vs practitioner
Academic perspective. The anomalies literature and its t-statistic hurdles, with the cross-section as the object of study.
Practitioner perspective. Capacity, decay, correlation with the existing book, whether the platform already runs it, and whether the PM can explain it in one sentence.
Pre-registered falsification criteria
Numeric thresholds written before the numbers are seen; each is evaluated with a stored number in sprints/E7/RESULTS.json.
ID
Criterion
F7.1
Shift audit: moving every signal forward by one day flips or kills its IC. This proves the absence of leakage.
F7.2
Factor-neutral momentum IC mean above 0.02 with t above 2, reported separately in-sample 2010 to 2020 and out-of-sample 2021 to 2026.
F7.3
Any signal failing the out-of-sample deflated-Sharpe hurdle is labeled NULL in the ledger, and the ledger contains at least as many rows as signal runs executed.
Exit criteria
F7 evaluated; ledger complete; D6 rendered; walkthrough rendered. Research deliverable written and linked from the Methodology tab.

/quant-prd, Sprint E7
Paste into a fresh Claude session to generate this sprint's PRD and TASKS.

/quant-prd
This is Sprint E7 of the Equity Factor Book (EFB) project. E1 to E6
exist: champion risk model, FMPs, hedging toolkit, dashboard D0 to D5.
Objective:
Build the alpha evaluation harness and the backtest hygiene ledger.
Turn each experimental signal into an honest expected return with an
IC, a decay curve, factor-neutral quantile returns, and a multiple-
testing record. No edge claim. Ends with dashboard tab D6.
(EQI Ch8; APM Ch6 and Appendix)
Focus areas:
- Signals (experimental): momentum 12-1, short-term reversal, idio
momentum on XS residuals, low residual vol, short interest (FINRA,
probe first), post-earnings drift (probe first)
- Spearman IC series, decay at 1, 5, 21, 63 days, factor-neutral
quantile portfolios via FMPs, turnover, hit rate; fundamental-law
check IR vs IC * sqrt(breadth)
- Hygiene: shift audit, survivorship number from E1, PIT flags,
multiple-testing ledger, Bonferroni t-stats, deflated Sharpe,
Harvey-Liu-Zhu t > 3 hurdle
- Alpha conversion: alpha_i = IC * sigma_idio,i * z_i with shrinkage;
this is the input contract for E8
Requirements:
- Exact formulas with inputs and outputs labeled
- Parquet schemas for data/alpha/{signal}/{ic, quantiles, decay}
- docs/multiple_testing_ledger.md appended automatically by the harness
- Pre-registered criteria F7.1 to F7.3 copied verbatim
- Dashboard D6 spec: signal selector, IC and t-stat, decay, quantile
spreads raw vs neutral, turnover, ledger table, expected-return
calculator with labeled inputs and outputs
- Max 10 atomic tasks, each with a test
Output:
- sprints/E7/PRD.md
- sprints/E7/TASKS.md
Research framing (from the roadmap, copy into the PRD verbatim):
- Academic question: How is the information content of a signal measured, and how are the standard errors adjusted for the number of things tried?
- Practitioner question: Does this signal contain information beyond the factors I already know about, at a horizon I can trade, after costs?
- Research question: Do any of the candidate signals show factor-neutral, out-of-sample, cost-surviving information, and does a negative result change what the book does?
- Research deliverable: Signal Evaluation Report, one per signal, with the Multiple-Testing Ledger, written for
a senior quant or risk manager; it must contain the methodology, the
stored numbers, the practitioner conclusion, and a section titled
"What would falsify this?". A negative verdict is a complete
deliverable.
- The TASKS.md must include one task that produces the deliverable and
one that evaluates every falsification criterion listed below.

/quant-dev and /quant-walkthrough, Sprint E7
Use the generic templates from the "How to use this document" section with <n> = 7 and the dashboard tab named above. Add the sprint's tests and failure modes to step 3 of /quant-dev and the research deliverable to the walkthrough's final section.

Sprint E8: Sizing and Portfolio Construction
Mon Oct 19 to Sun Oct 25. Tier 2. Gate: G3, construction stack.
Stage: Portfolio researcher to practitioner: from views to positions
Book coverage: APM Ch6 (proportional rule, Sharpe rule, Procedure 6.3 factor-neutral sizing). EQI Ch9 (basic portfolio management), Ch10 (advanced: constraints, multiple signals, shrinkage).
Research questions
Academic. Given expected returns and a covariance matrix, what is the optimal portfolio, and how does estimation error in both inputs change the answer?
Practitioner. Given uncertain expected returns and correlated risks, what positions should I actually hold, and which constraints protect me from my own inputs?
Research. Do the simple APM sizing rules match constrained mean-variance out of sample, and how much does alpha uncertainty degrade each?
Objective
Turn expected returns and the champion risk model into positions: the APM sizing rules, Procedure 6.3, mean-variance with constraints, multiple-signal combination, and robustness to alpha noise, all compared on the same inputs.
Academic concept and intuition
Concept. Mean-variance optimization and its closed form; the APM proportional and Sharpe rules as the diagonal special case; Procedure 6.3 (size on idio, hedge factors) as mean-variance under a factor model with factor-neutral alpha; constraints as regularizers; alpha shrinkage; multiple-signal combination; turnover and implementation constraints (gross, net, caps, liquidity, whole shares); robustness by resampling.
Intuition. Mean-variance weights are Sigma^-1 alpha, and the inverse amplifies estimation error in the low-variance directions. With factor-neutral alpha and a factor model, the optimizer reduces to sizing on idiosyncratic variance, which is exactly why the APM rules work. Constraints are not a nuisance; they are the regularization that keeps a noisy alpha from becoming a concentrated position.
Foundation
The formulas the sprint implements; inputs and outputs are labeled in the walkthrough.
w* = (1 / lambda) Sigma^-1 alpha; with Sigma = X F X' + D and alpha orthogonal to X, w* is proportional to D^-1 alpha, the proportional rule; the Sharpe rule follows from alpha_i = SR_i sigma_i.
Vol targeting: scale w so that sqrt(w' Sigma w) equals the target; Procedure 6.3: size on D^-1 alpha, then hedge x = X'w with FMPs.
Constrained QP in cvxpy: gross, net, position caps, sector-neutral and beta-neutral equalities, turnover cap.
Shrinkage alpha_s = kappa alpha; robustness: resample alpha with IC-consistent noise and measure weight dispersion.
Implementation scope
Proportional rule: w_i proportional to alpha_i / sigma_idio,i squared. Sharpe-based rule: w_i proportional to SR_i / sigma_idio,i. Both scaled to a book-level volatility target.
Procedure 6.3: size on idio, then hedge factors with FMPs; worked example carried through the walkthrough.
Mean-variance: maximize alpha'w minus (lambda / 2) w' Sigma w; closed form w = Sigma^-1 alpha / lambda; constrained version via cvxpy (gross, net, position caps, sector-neutral, beta-neutral); compared to the rules on the same alpha.
Multiple signals: IC-weighted combination and regression stacking; alpha shrinkage; robustness by resampling alpha with IC-consistent noise. The geometry of the frontier under the champion Sigma vs the sample Sigma.
Deliverables and dashboard increment
efb/size.py, efb/optimize.py; data/portfolios/{rule}/{weights, exposures, decomposition}.parquet
notebooks/E8_walkthrough.ipynb; Dashboard tab D7 Sizing and Optimizer
Dashboard: D7 Sizing and Optimizer: an inputs panel (alpha source, risk model version, target vol, constraints) and an outputs panel (weights, exposures, decomposition, ex-ante IR) with every quantity labeled INPUT or OUTPUT; side-by-side comparison of proportional, Sharpe, Procedure 6.3 and MV; a worked-example card that follows one stock from alpha to weight.
Empirical tests and diagnostics
Tests
Rules vs mean-variance under the same alpha and Sigma (F8.1); idio share after hedge (F8.2); constraint satisfaction (F8.3).
Robustness to alpha resampling (F8.4); frontier under the champion Sigma vs the sample Sigma.
Out-of-sample comparison of rules on the seed alpha or on synthetic alpha if RG-Signal returned no PASS.
Failure modes to look for
Infeasible constraint sets; corner solutions; leverage explosion from tiny idio variances.
Turnover that no cost model survives; positions that cannot be traded in whole shares at the book's size.
Why this matters to a PM
PM question: "Given uncertain expected returns and correlated risks, what positions should I actually hold?"
Problem it addresses. The question of how much, not what, is where most PM value is won and lost; this is the thesis of APM.
Decision it informs. Position sizes, limits, the target volatility and the constraint set the book will run under.
If the analysis is wrong. Concentration in low-volatility names with noisy alpha; a book whose exposures the PM cannot explain.
Before trusting the output. The robustness test, an exposure report after construction, and a worked example that follows one name from alpha to weight.
What would falsify this?
Rules and mean-variance differ materially: alpha is not factor-neutral or D is mis-specified; the deliverable says which.
The optimizer is unstable under alpha resampling: shrinkage is increased until it is, and the kappa is recorded.
Excessive concentration or turnover under the chosen constraints: the constraint set is revised, and the trade-off is a table.
Research deliverable
Portfolio Construction Memo (docs/research/E8_construction_memo.md)
The rule comparison table and the chosen approach, with the constraint set and its rationale
The robustness analysis and the shrinkage chosen
The exposure report of the constructed book under the champion model
Book connection
Chapters. APM Ch6 (proportional rule, Sharpe rule, Procedure 6.3); EQI Ch9 (basic portfolio management), Ch10 (advanced: constraints, multiple signals, shrinkage).
Understand before implementing: Why w is proportional to alpha over variance, and where the factor structure enters. Why constraints and shrinkage matter more than the objective function.
What the implementation teaches that the book cannot: That the optimizer's output must be explainable, or the PM will not run it. That implementation constraints are the first constraint, not the last.
Academic vs practitioner
Academic perspective. Unconstrained mean-variance and its refinements (Black-Litterman, robust optimization) with known inputs.
Practitioner perspective. Constraints, turnover budgets, whole shares and explainability, with inputs known to be wrong by an amount that is estimated.
Pre-registered falsification criteria
Numeric thresholds written before the numbers are seen; each is evaluated with a stored number in sprints/E8/RESULTS.json.
ID
Criterion
F8.1
Unconstrained mean-variance with factor-neutral alpha reproduces Procedure 6.3 weights within 1e-6; under the model they are the same object.
F8.2
The proportional-rule book has an idio share of variance above 90% after the FMP hedge.
F8.3
The constrained optimizer respects every constraint with maximum violation below 1e-8.
F8.4
Robustness: resampling alpha with IC-consistent noise changes weights by less than 30% mean absolute. If larger, increase shrinkage and record the lambda chosen.
Exit criteria
GATE G3: the construction stack (alpha to hedged, sized book) runs end to end under the champion model; F8 evaluated; D7 rendered; walkthrough rendered. Research deliverable written and linked from the Methodology tab.

/quant-prd, Sprint E8
Paste into a fresh Claude session to generate this sprint's PRD and TASKS.

/quant-prd
This is Sprint E8 of the Equity Factor Book (EFB) project. E1 to E7
exist: champion risk model, FMPs, hedging toolkit, alpha harness with
the alpha_i = IC * sigma_idio * z contract, dashboard D0 to D6.
Objective:
Build sizing and portfolio construction: APM proportional and Sharpe
rules, Procedure 6.3 factor-neutral sizing, mean-variance with
constraints, multiple-signal combination and alpha robustness, all
compared on the same inputs. Ends with dashboard tab D7.
(APM Ch6; EQI Ch9, Ch10)
Focus areas:
- Proportional rule w_i ~ alpha_i / sigma_idio,i^2; Sharpe rule
w_i ~ SR_i / sigma_idio,i; book-level vol targeting
- Procedure 6.3: size on idio, hedge factors with FMPs
- MV: max alpha'w - (lambda/2) w' Sigma w; closed form; constrained
(gross, net, caps, sector-neutral, beta-neutral) via cvxpy
- Multiple signals: IC-weighted and stacked; shrinkage; resampling
robustness; frontier under champion Sigma vs sample Sigma
Requirements:
- Exact formulas with inputs and outputs labeled, including the
vol-target scaling and the closed-form MV solution
- Parquet schemas for data/portfolios/{rule}/{weights, exposures,
decomposition}
- Pre-registered criteria F8.1 to F8.4 copied verbatim
- Dashboard D7 spec: inputs panel, outputs panel, side-by-side rule
comparison, worked-example card following one stock end to end
- Max 10 atomic tasks, each with a test
Output:
- sprints/E8/PRD.md
- sprints/E8/TASKS.md
Research framing (from the roadmap, copy into the PRD verbatim):
- Academic question: Given expected returns and a covariance matrix, what is the optimal portfolio, and how does estimation error in both inputs change the answer?
- Practitioner question: Given uncertain expected returns and correlated risks, what positions should I actually hold, and which constraints protect me from my own inputs?
- Research question: Do the simple APM sizing rules match constrained mean-variance out of sample, and how much does alpha uncertainty degrade each?
- Research deliverable: Portfolio Construction Memo, written for
a senior quant or risk manager; it must contain the methodology, the
stored numbers, the practitioner conclusion, and a section titled
"What would falsify this?". A negative verdict is a complete
deliverable.
- The TASKS.md must include one task that produces the deliverable and
one that evaluates every falsification criterion listed below.

/quant-dev and /quant-walkthrough, Sprint E8
Use the generic templates from the "How to use this document" section with <n> = 8 and the dashboard tab named above. Add the sprint's tests and failure modes to step 3 of /quant-dev and the research deliverable to the walkthrough's final section.

Sprint E9: Transaction Costs and Capacity
Mon Oct 26 to Sun Nov 1. Tier 3.
Stage: Practitioner: does the alpha survive implementation
Book coverage: APM Ch10 (capacity). EQI Ch11 (t-cost-aware portfolio management).
Research questions
Academic. How do transaction costs enter the portfolio problem, and how does the optimal trade change from full rebalancing to partial adjustment?
Practitioner. Does the theoretical alpha survive implementation, and at what AUM does it stop?
Research. What is the capacity of the seed book, and how much turnover is worth its cost?
Objective
Make construction cost-aware: a cost model, a turnover-penalized optimizer, trade scheduling, and the capacity curve of the seed book.
Academic concept and intuition
Concept. Spread and impact cost models (the square-root law), the Corwin-Schultz spread estimator, t-cost-aware mean-variance with a trade penalty, trading toward target, turnover and implementation constraints, and the capacity curve.
Intuition. Impact scales with the square root of trade size over daily volume, so doubling AUM raises cost per dollar by roughly 41% while alpha stays flat; there is an AUM at which net Sharpe halves. The optimal response to a new target is a partial move, not a full rebalance.
Foundation
The formulas the sprint implements; inputs and outputs are labeled in the walkthrough.
Cost(delta w) = half_spread x |delta w| + k sigma sqrt(|delta w| x AUM / ADV) + commission; Corwin-Schultz half-spread from daily high-low ranges.
Objective: alpha'w - (lambda / 2) w' Sigma w - TC(w - w_0); trade-toward-target as its first-order solution.
Capacity curve: net Sharpe as a function of AUM; halving AUM stored.
Implementation scope
Cost model: half-spread from a Corwin-Schultz high-low estimator (probe bid-ask availability first), square-root impact scaled by ADV, commissions, borrow for shorts.
T-cost-aware optimization: turnover penalty in the objective, trade-toward-target vs full rebalance, optimal rebalancing frequency.
Capacity curve: net Sharpe vs AUM for the seed book; the AUM at which net Sharpe halves.
Deliverables and dashboard increment
efb/costs.py, efb/optimize.py extended; data/costs/{cost_curves, capacity}.parquet
notebooks/E9_walkthrough.ipynb; Dashboard tab D8 Cost and Capacity
Dashboard: D8 Cost and Capacity: cost curves by size decile, pre and post cost Sharpe with SE, turnover vs ex-ante IR frontier, capacity curve with the halving point marked.
Empirical tests and diagnostics
Tests
Net Sharpe vs AUM (F9.1); turnover-penalized optimizer trade-off (F9.2); spread estimates vs size rank (F9.3).
Sensitivity of capacity to the impact coefficient k; rebalance frequency vs net IR.
Failure modes to look for
Cost parameters unverifiable from free data; the deliverable states the uncertainty instead of a point estimate.
Corwin-Schultz noise on illiquid names; borrow costs unavailable and proxied.
Why this matters to a PM
PM question: "Does the theoretical alpha survive implementation, and at what size does it stop?"
Problem it addresses. Gross alpha is a research number; net alpha is the business.
Decision it informs. The turnover budget, the rebalance cadence, and how much capital the strategy can take.
If the analysis is wrong. Over-trading a decaying signal; raising capital past capacity; underestimating costs on the short side.
Before trusting the output. Realized slippage vs the model, which only E11 can supply; until then, sensitivity tables to k.
What would falsify this?
Net Sharpe is not monotone in AUM: the cost model is mis-specified.
The turnover penalty destroys ex-ante IR: the signal horizon is wrong for the cost regime.
Realized fills in E11 outside the model's band: parameters are recalibrated and the capacity curve reissued.
Research deliverable
Transaction Cost and Capacity Analysis (docs/research/E9_tcost_capacity.md)
Cost model with parameters and their uncertainty; cost curves by size decile
Turnover vs IR frontier; recommended cadence and turnover budget
Capacity curve with the halving AUM and its sensitivity to k
Book connection
Chapters. EQI Ch11 (t-cost-aware portfolio management); APM Ch10 (capacity).
Understand before implementing: Why cost is concave in trade size and what that does to the optimal trade. Why capacity is a property of the strategy and the cost model together.
What the implementation teaches that the book cannot: That cost parameters are the least certain inputs in the whole stack. That the rebalance cadence is a decision, not a default.
Pre-registered falsification criteria
Numeric thresholds written before the numbers are seen; each is evaluated with a stored number in sprints/E9/RESULTS.json.
ID
Criterion
F9.1
Net Sharpe declines monotonically with AUM; the halving AUM is stored.
F9.2
The turnover-penalized optimizer cuts turnover by more than 50% with less than 20% loss of ex-ante IR.
F9.3
Corwin-Schultz spread estimates correlate above 0.5 with size rank (smaller names wider).
Exit criteria
F9 evaluated; D8 rendered; walkthrough rendered. Research deliverable written and linked from the Methodology tab.

/quant-prd, Sprint E9
Paste into a fresh Claude session to generate this sprint's PRD and TASKS.

/quant-prd
This is Sprint E9 of the Equity Factor Book (EFB) project. E1 to E8
exist: the full construction stack under the champion model, dashboard
D0 to D7.
Objective:
Make construction cost-aware: cost model, turnover-penalized optimizer,
trade scheduling, and the capacity curve of the seed book. Ends with
dashboard tab D8. (EQI Ch11; APM Ch10)
Focus areas:
- Cost model: Corwin-Schultz half-spread (probe first), sqrt impact
scaled by ADV, commissions, borrow
- Turnover penalty in the objective; trade-toward-target; optimal
rebalance frequency
- Capacity: net Sharpe vs AUM; halving AUM
Requirements:
- Exact formulas with inputs and outputs labeled, parameter values
stated with their source
- Parquet schemas for data/costs/{cost_curves, capacity}
- Pre-registered criteria F9.1 to F9.3 copied verbatim
- Dashboard D8 spec: cost curves by size decile, pre and post cost
Sharpe with SE, turnover vs IR frontier, capacity curve
- Max 10 atomic tasks, each with a test
Output:
- sprints/E9/PRD.md
- sprints/E9/TASKS.md
Research framing (from the roadmap, copy into the PRD verbatim):
- Academic question: How do transaction costs enter the portfolio problem, and how does the optimal trade change from full rebalancing to partial adjustment?
- Practitioner question: Does the theoretical alpha survive implementation, and at what AUM does it stop?
- Research question: What is the capacity of the seed book, and how much turnover is worth its cost?
- Research deliverable: Transaction Cost and Capacity Analysis, written for
a senior quant or risk manager; it must contain the methodology, the
stored numbers, the practitioner conclusion, and a section titled
"What would falsify this?". A negative verdict is a complete
deliverable.
- The TASKS.md must include one task that produces the deliverable and
one that evaluates every falsification criterion listed below.

/quant-dev and /quant-walkthrough, Sprint E9
Use the generic templates from the "How to use this document" section with <n> = 9 and the dashboard tab named above. Add the sprint's tests and failure modes to step 3 of /quant-dev and the research deliverable to the walkthrough's final section.

Sprint E10: Dynamic Risk Allocation and Loss Management
Mon Nov 2 to Sun Nov 8. Tier 3.
Stage: Practitioner: how much risk to run, and what to do when losing
Book coverage: APM Ch9 (managing losses, stop-loss efficiency). EQI Ch13 (dynamic risk allocation, Kelly, fractional Kelly, drawdowns).
Research questions
Academic. How much risk should a strategy with an estimated Sharpe ratio run, and under what return properties does a stop-loss add value?
Practitioner. How much can I lose before the model is wrong rather than unlucky, and what does the book do at that point?
Research. Does volatility targeting or a stop-loss improve the seed book's risk-adjusted outcome relative to i.i.d. controls, and how do drawdowns depend on the volatility regime?
Objective
Decide how much risk the book runs over time: Kelly and fractional Kelly for an estimated Sharpe, volatility targeting, drawdown control, and the APM stop-loss efficiency analysis tested on the seed book.
Academic concept and intuition
Concept. Kelly and fractional Kelly under an estimated Sharpe; growth versus drawdown; volatility targeting; the drawdown distribution given Sharpe and horizon; the APM stop-loss efficiency analysis; regime analysis of drawdowns.
Intuition. Kelly leverage is SR over sigma, and estimation error in SR makes full Kelly reckless: half Kelly gives up a quarter of the growth rate for far less variance. A stop-loss only helps if returns are positively autocorrelated; otherwise it truncates expected return. A one-Sharpe strategy has drawdowns over five years that routinely embarrass its owner, and the distribution can be written down in advance.
Foundation
The formulas the sprint implements; inputs and outputs are labeled in the walkthrough.
Kelly fraction f* = mu / sigma^2; growth g(f) = f mu - f^2 sigma^2 / 2; fractional f = c f*, with c set by the SE of the Sharpe estimate.
Vol targeting: scale_t = sigma_target / sigma_hat_t; drawdown approximation (Magdon-Ismail et al.) for expected maximum drawdown as a function of SR and horizon.
Stop-loss rule and its efficiency: Sharpe with and without the rule on bootstrapped i.i.d. returns (control) and on the real book.
Regime: drawdown depth and recovery within VIX terciles.
Implementation scope
Kelly and fractional Kelly for a book with an estimated (uncertain) Sharpe; the cost of over-betting when SR is overstated by one standard error.
Volatility targeting rules and their effect on realized vol dispersion across years; risk budgeting across sleeves.
Drawdown distribution given SR and horizon, simulated and analytical; stop-loss efficiency: does a stop-loss improve Sharpe on i.i.d. bootstrapped returns (control) and on the real book?
New in v2: Regime analysis of drawdowns: depth and recovery time within VIX terciles and named episodes, so the risk budget can be written per regime.
Deliverables and dashboard increment
efb/allocate.py; data/allocation/{kelly, voltarget, stoploss}.parquet
notebooks/E10_walkthrough.ipynb; Dashboard tab D9 Risk Allocation
Dashboard: D9 Risk Allocation: Kelly fraction calculator with inputs (SR, SE of SR, horizon) and outputs (full and fractional Kelly leverage) labeled, vol-target simulation, stop-loss efficiency curves, drawdown distribution vs analytical approximation.
Empirical tests and diagnostics
Tests
Simulated vs analytical drawdown distribution (F10.1); stop-loss efficiency control (F10.2); vol-target dispersion (F10.3).
Growth vs fraction curve with the SE of SR shaded; drawdowns by regime.
Failure modes to look for
Vol targeting raising turnover and costs; stop-losses interacting with rebalancing to create whipsaw.
Over-leverage on an overstated Sharpe; leverage constraints ignored.
Why this matters to a PM
PM question: "How much can I lose before the model is wrong rather than unlucky, and what do I do then?"
Problem it addresses. The risk budget and the loss rules are what a platform actually writes into a PM's contract.
Decision it informs. Leverage, the stop rules, and when to cut versus ride.
If the analysis is wrong. Over-leverage on an overstated Sharpe; cutting a good strategy at its worst moment because the rule was set without the distribution.
Before trusting the output. The drawdown distribution table for the book's Sharpe, and the i.i.d. control for any stop rule.
What would falsify this?
The stop-loss improves Sharpe in the i.i.d. control: a bug, since it cannot.
Vol targeting shows no effect on realized vol dispersion: the vol forecast is not doing its job (back to E2 and E5).
Drawdowns strongly regime-dependent: the risk budget is written per regime, not as one number.
Research deliverable
Risk Allocation and Drawdown Policy (docs/research/E10_risk_policy.md)
Kelly analysis with the chosen fraction and the reasoning from the SE of SR
Drawdown distribution table and the regime table
The stop-loss verdict and the volatility-targeting rule the book will run
Book connection
Chapters. EQI Ch13 (dynamic risk allocation, Kelly, fractional Kelly, drawdowns); APM Ch9 (managing losses, stop-loss efficiency).
Understand before implementing: Why full Kelly is the wrong answer for an estimated Sharpe. When a stop-loss can add value and when it only truncates.
What the implementation teaches that the book cannot: That a drawdown policy can be derived before the first loss. That the volatility regime, not the calendar, is the natural unit for a risk budget.
Pre-registered falsification criteria
Numeric thresholds written before the numbers are seen; each is evaluated with a stored number in sprints/E10/RESULTS.json.
ID
Criterion
F10.1
Simulated drawdown distribution matches the analytical approximation within 10% at the median for the seed book's SR.
F10.2
Control: on i.i.d. bootstrapped returns the stop-loss does not improve Sharpe. On the real book the result is reported either way.
F10.3
Vol targeting reduces the dispersion of realized annual vol across years by more than 40%.
Exit criteria
F10 evaluated; D9 rendered; walkthrough rendered. Research deliverable written and linked from the Methodology tab.

/quant-prd, Sprint E10
Paste into a fresh Claude session to generate this sprint's PRD and TASKS.

/quant-prd
This is Sprint E10 of the Equity Factor Book (EFB) project. E1 to E9
exist: cost-aware construction stack, dashboard D0 to D8.
Objective:
Dynamic risk allocation and loss management: Kelly and fractional
Kelly under Sharpe uncertainty, vol targeting, drawdown control, and
the APM stop-loss efficiency analysis on the seed book. Ends with
dashboard tab D9. (EQI Ch13; APM Ch9)
Focus areas:
- Kelly and fractional Kelly given SR and its SE; cost of over-betting
- Vol targeting; risk budgeting across sleeves
- Drawdown distribution (simulated and analytical) given SR and horizon
- Stop-loss efficiency: i.i.d. bootstrap control vs real book
Requirements:
- Exact formulas with inputs and outputs labeled
- Parquet schemas for data/allocation/{kelly, voltarget, stoploss}
- Pre-registered criteria F10.1 to F10.3 copied verbatim
- Dashboard D9 spec: Kelly calculator with labeled inputs and outputs,
vol-target simulation, stop-loss efficiency curves, drawdown
distribution vs analytical
- Max 10 atomic tasks, each with a test
Output:
- sprints/E10/PRD.md
- sprints/E10/TASKS.md
Research framing (from the roadmap, copy into the PRD verbatim):
- Academic question: How much risk should a strategy with an estimated Sharpe ratio run, and under what return properties does a stop-loss add value?
- Practitioner question: How much can I lose before the model is wrong rather than unlucky, and what does the book do at that point?
- Research question: Does volatility targeting or a stop-loss improve the seed book's risk-adjusted outcome relative to i.i.d. controls, and how do drawdowns depend on the volatility regime?
- Research deliverable: Risk Allocation and Drawdown Policy, written for
a senior quant or risk manager; it must contain the methodology, the
stored numbers, the practitioner conclusion, and a section titled
"What would falsify this?". A negative verdict is a complete
deliverable.
- The TASKS.md must include one task that produces the deliverable and
one that evaluates every falsification criterion listed below.

/quant-dev and /quant-walkthrough, Sprint E10
Use the generic templates from the "How to use this document" section with <n> = 10 and the dashboard tab named above. Add the sprint's tests and failure modes to step 3 of /quant-dev and the research deliverable to the walkthrough's final section.

Sprint E11: The Book: Daily Long/Short Paper Trading
Mon Nov 9 to Sun Nov 22 (two weeks). Tier 3.
Stage: Systematic practitioner: operating the book every day
Book coverage: APM Ch2 (from stock picking to portfolio management). Reuses the v8.x daily loop from the Credit Trading Lab.
Research questions
Academic. What must be true of a research pipeline for it to run in production without look-ahead, and how is the ex-ante forecast reconciled to the ex-post outcome?
Practitioner. Can this portfolio actually be operated every day, unattended, with every decision explainable the next morning?
Research. Over 30 trading days, does ex-ante risk match ex-post, and does realized cost match the E9 model?
Objective
Assemble the pieces into a daily long/short equity book that runs forward in paper: alpha from E7, sizing from E8, hedge from E6, costs from E9, vol target from E10, under the champion risk model. Same operational loop as v8.x: evening proposal, morning execute, Alpaca paper, Render plus Supabase, Option A governance.
Academic concept and intuition
Concept. The production loop as a research object: previous-close data only, idempotent jobs, append-only state, governance with logged overrides, and daily reconciliation of forecast to outcome.
Intuition. Research pipelines fail in production in ways backtests cannot show: a late data feed, a fractional short order, a corporate action overnight. The point of 30 days is not P&L; it is the log of everything that broke and the daily comparison of what the model said to what happened.
Foundation
The formulas the sprint implements; inputs and outputs are labeled in the walkthrough.
Evening job: descriptors (t-1) -> alpha -> weights (E8) -> hedge (E6) -> vol scale (E10) -> ex-ante decomposition stored (E3); morning job: execute with the two guards; state in Supabase.
Reconciliation: ex-ante sigma_p vs realized, realized slippage vs E9 model, exposures vs limits, every day.
Implementation scope
Book design: 60 to 100 names, sector-neutral, beta-neutral, whole-share shorts (the Alpaca constraint from v8.4), weekly rebalance with the turnover penalty.
Daily loop reuse: evening job computes descriptors, alpha, weights, hedge and stores the ex-ante risk decomposition; morning job executes with the two fail-safe guards; Supabase tables for decisions, positions, pnl_log, risk_log.
Option A governance carried over: the system proposes, overrides need logged reasoning, shadow-veto tracking.
Deliverables and dashboard increment
live/ jobs adapted from v8.x; Supabase schema extended with risk_log
notebooks/E11_walkthrough.ipynb; Dashboard tab D10 Book Monitor
Dashboard: D10 Book Monitor: positions, daily and cumulative P&L, today's ex-ante risk decomposition next to trailing realized vol, exposures vs limits, proposal and override log, guard events.
Empirical tests and diagnostics
Tests
30 days unattended (F11.1); daily decomposition stored and reconciled (F11.2); realized vol inside the champion's bias band (F11.3); slippage vs model.
Failure modes to look for
Data feed delay causing a same-day lookahead; whole-share quantization drifting exposures; override log not enforced.
Why this matters to a PM
PM question: "Can this portfolio actually be operated every day?"
Problem it addresses. A strategy that cannot be operated is a paper.
Decision it informs. Whether the stack is trustworthy enough to run, and which operational failures need a guard.
If the analysis is wrong. A silent look-ahead in production; an unlogged override that later looks like alpha.
Before trusting the output. The operations log, the daily reconciliation table, and the guard events.
What would falsify this?
A missed proposal in 30 days; a day without a stored decomposition; realized vol outside the bias band; realized slippage outside the E9 band.
Research deliverable
Operations Log and 30-Day Review (docs/research/E11_ops_review.md)
Every failure and its fix; the daily reconciliation table; realized vs modeled cost; what changed in the risk model, cost model and guards as a result
Book connection
Chapters. APM Ch2 (from stock picking to portfolio management); the v8.x Credit Trading Lab daily loop.
Understand before implementing: Why the proposer must never see today's intraday data. Why overrides are attributed separately from model alpha.
What the implementation teaches that the book cannot: What breaks that no backtest shows. That a null-alpha book is still a complete operational instrument.
Pre-registered falsification criteria
Numeric thresholds written before the numbers are seen; each is evaluated with a stored number in sprints/E11/RESULTS.json.
ID
Criterion
F11.1
30 consecutive trading days unattended with zero missed proposals.
F11.2
The ex-ante risk decomposition is stored every day and reconciles to the champion model's numbers on D2.
F11.3
Realized book vol over the window sits inside the champion model's bias band from E5.
Exit criteria
30 trading days complete; F11 evaluated; D10 rendered. Research deliverable written and linked from the Methodology tab.

/quant-prd, Sprint E11
Paste into a fresh Claude session to generate this sprint's PRD and TASKS.

/quant-prd
This is Sprint E11 of the Equity Factor Book (EFB) project. E1 to E10
exist: the full construction and allocation stack, dashboard D0 to D9.
The v8.x Credit Trading Lab daily loop (Alpaca paper, Render cron jobs,
Supabase state, Option A governance, two fail-safe guards) is available
to reuse.
Objective:
Assemble a daily long/short equity paper book from the EFB stack and
run it forward for 30 trading days. Ends with dashboard tab D10.
Focus areas:
- Book: 60 to 100 names, sector-neutral, beta-neutral, whole-share
shorts, weekly rebalance with turnover penalty
- Evening job: descriptors -> alpha -> weights -> hedge -> ex-ante risk
decomposition stored; morning job: execute with guards
- Supabase: decisions, positions, pnl_log, risk_log
- Option A governance and shadow-veto tracking carried over
Requirements:
- Exact daily sequence with timestamps and the data each step reads
(previous close only; no intraday data)
- Table schemas, append-only, idempotent re-runs
- Pre-registered criteria F11.1 to F11.3 copied verbatim
- Dashboard D10 spec: positions, P&L, ex-ante vs realized risk,
exposures vs limits, proposal and override log, guard events
- Max 10 atomic tasks, each with a test
Output:
- sprints/E11/PRD.md
- sprints/E11/TASKS.md
Research framing (from the roadmap, copy into the PRD verbatim):
- Academic question: What must be true of a research pipeline for it to run in production without look-ahead, and how is the ex-ante forecast reconciled to the ex-post outcome?
- Practitioner question: Can this portfolio actually be operated every day, unattended, with every decision explainable the next morning?
- Research question: Over 30 trading days, does ex-ante risk match ex-post, and does realized cost match the E9 model?
- Research deliverable: Operations Log and 30-Day Review, written for
a senior quant or risk manager; it must contain the methodology, the
stored numbers, the practitioner conclusion, and a section titled
"What would falsify this?". A negative verdict is a complete
deliverable.
- The TASKS.md must include one task that produces the deliverable and
one that evaluates every falsification criterion listed below.

/quant-dev and /quant-walkthrough, Sprint E11
Use the generic templates from the "How to use this document" section with <n> = 11 and the dashboard tab named above. Add the sprint's tests and failure modes to step 3 of /quant-dev and the research deliverable to the walkthrough's final section.

Sprint E12: Ex-Post Performance Attribution
Mon Nov 23 to Sun Nov 29. Tier 3.
Stage: Systematic practitioner: explaining every dollar
Book coverage: APM Ch8 (understand your performance). EQI Ch14 (ex-post performance attribution, skill vs luck).
Research questions
Academic. How is realized P&L decomposed into factor and idiosyncratic components under a factor model, and how are skill and luck separated statistically?
Practitioner. Why did I make or lose money, was it the bet I intended, and would a risk manager agree with my story?
Research. Is the book's P&L explained by intended idio bets, does holdings-based attribution agree with the returns-based view, and is any of it distinguishable from zero?
Objective
Explain every dollar the book made or lost: factor vs idio P&L from holdings, selection vs sizing vs timing, time-series attribution as a cross-check, the seven-way decomposition ported from the ETF book, and an honest skill-vs-luck verdict with Sharpe standard errors.
Academic concept and intuition
Concept. Holdings-based attribution (exposure times factor return, position times specific return), returns-based attribution (time-series regression of book returns on factor returns), selection versus sizing versus timing, the seven-way decomposition from the ETF book, regime-conditional P&L, and Sharpe with its standard error as the skill test.
Intuition. Attribution is the risk decomposition run backwards on realized returns: every dollar is a factor dollar, an idio dollar, or a cost dollar, to machine precision. The holdings view knows what you held; the regression view only sees what you earned; when they disagree, exposures drifted between rebalances. Thirty days cannot show skill, and the report should say so with a number.
Foundation
The formulas the sprint implements; inputs and outputs are labeled in the walkthrough.
Factor P&L_t = (X_{t-1}' w_{t-1})' f_t by factor; idio P&L_t = w_{t-1}' e_t; total = factor + idio + cost, reconciled to 1e-10.
Returns-based: regress book returns on factor returns, compare betas to average holdings-based exposures within SE.
Selection vs sizing vs timing; seven-way decomposition port; Sharpe with SE (E1 perf library), IR t-stat, hit rate and slugging.
Regime: P&L and attribution within VIX terciles.
Implementation scope
Holdings-based attribution: daily factor P&L = (X_{t-1}' w_{t-1})' f_t by factor, idio P&L = w_{t-1}' e_t, costs; cumulative and by period.
Selection vs sizing vs timing decomposition; time-series attribution by regressing book returns on factor returns and comparing betas to average holdings-based exposures.
Seven-way decomposition from the ETF book ported to equities; reconciliation to machine precision.
Skill vs luck: Sharpe with SE, IR t-stat, hit rate and slugging, and the rule that no skill is claimed unless t exceeds 2.
Deliverables and dashboard increment
efb/attribution.py; data/attribution/{daily, monthly, timeseries}.parquet
notebooks/E12_walkthrough.ipynb; Dashboard tab D11 Attribution
Dashboard: D11 Attribution: daily and cumulative factor vs idio P&L, per-factor bars, selection vs sizing vs timing, holdings-based vs time-series attribution side by side, the seven-way decomposition table, and a skill-vs-luck card showing Sharpe with its SE and the t-stat.
Empirical tests and diagnostics
Tests
Reconciliation (F12.1); holdings vs returns-based agreement (F12.2); the skill test (F12.3); regime attribution table.
Failure modes to look for
Exposures from the wrong date (t instead of t-1) breaking the reconciliation; costs omitted; the seven-way port mislabeling carry.
Why this matters to a PM
PM question: "Why did I make or lose money, and was it what I intended?"
Problem it addresses. The monthly conversation between a PM and the risk team is an attribution table.
Decision it informs. Whether the book is doing what it was built to do, which exposures to cut, and whether the process, not the P&L, justifies continuing.
If the analysis is wrong. Factor P&L mistaken for skill; idio losses hidden inside a factor rally; an override credited as alpha.
Before trusting the output. Reconciliation to machine precision, two attribution methods that agree, and a Sharpe with its standard error.
What would falsify this?
Reconciliation fails; the two methods disagree beyond SE; P&L concentrated in one regime or one name; performance disappearing after controlling for known factors.
Research deliverable
P&L Attribution Report (docs/research/E12_attribution_report.md)
Factor vs idio P&L, per factor, cumulative and by regime
Selection, sizing and timing; the seven-way table
The skill-vs-luck card with the honest verdict, and the coverage map checked off
Book connection
Chapters. APM Ch8 (understand your performance); EQI Ch14 (ex-post performance attribution, skill vs luck).
Understand before implementing: Why holdings-based and returns-based attribution are different estimators of the same thing. What a Sharpe standard error means for a 30-day track record.
What the implementation teaches that the book cannot: That attribution is a reconciliation discipline before it is an analysis. How to write a negative verdict about your own book.
Pre-registered falsification criteria
Numeric thresholds written before the numbers are seen; each is evaluated with a stored number in sprints/E12/RESULTS.json.
ID
Criterion
F12.1
Holdings-based factor P&L plus idio P&L plus costs equals total P&L to 1e-10 every day.
F12.2
Time-series attribution betas agree with average holdings-based exposures within one standard error.
F12.3
The reported Sharpe carries its SE and no skill is claimed unless t exceeds 2. The expected verdict is luck; write it down.
Exit criteria
F12 evaluated; D11 rendered; walkthrough rendered; the full APM and EQI coverage map is checked off. Research deliverable written and linked from the Methodology tab.

/quant-prd, Sprint E12
Paste into a fresh Claude session to generate this sprint's PRD and TASKS.

/quant-prd
This is Sprint E12 of the Equity Factor Book (EFB) project. E1 to E11
exist and the paper book has at least 30 trading days of history in
Supabase, with daily ex-ante risk decompositions stored.
Objective:
Ex-post performance attribution: holdings-based factor vs idio P&L,
selection vs sizing vs timing, time-series attribution as a cross-check,
the seven-way decomposition ported from the ETF book, and a skill vs
luck verdict with Sharpe standard errors. Ends with dashboard tab D11.
(EQI Ch14; APM Ch8)
Focus areas:
- Daily factor P&L by factor (X_{t-1}' w_{t-1})' f_t, idio P&L
w_{t-1}' e_t, costs; cumulative and by period
- Selection vs sizing vs timing; time-series attribution regression
and comparison with holdings-based exposures
- Seven-way decomposition port; machine-precision reconciliation
- Sharpe with SE, IR t-stat, hit rate, slugging; no skill claim unless
t > 2
Requirements:
- Exact formulas with inputs and outputs labeled
- Parquet schemas for data/attribution/{daily, monthly, timeseries}
- Pre-registered criteria F12.1 to F12.3 copied verbatim
- Dashboard D11 spec: factor vs idio P&L, per-factor bars, selection vs
sizing vs timing, holdings vs time-series side by side, seven-way
table, skill vs luck card
- Max 10 atomic tasks, each with a test
Output:
- sprints/E12/PRD.md
- sprints/E12/TASKS.md
Research framing (from the roadmap, copy into the PRD verbatim):
- Academic question: How is realized P&L decomposed into factor and idiosyncratic components under a factor model, and how are skill and luck separated statistically?
- Practitioner question: Why did I make or lose money, was it the bet I intended, and would a risk manager agree with my story?
- Research question: Is the book's P&L explained by intended idio bets, does holdings-based attribution agree with the returns-based view, and is any of it distinguishable from zero?
- Research deliverable: P&L Attribution Report, written for
a senior quant or risk manager; it must contain the methodology, the
stored numbers, the practitioner conclusion, and a section titled
"What would falsify this?". A negative verdict is a complete
deliverable.
- The TASKS.md must include one task that produces the deliverable and
one that evaluates every falsification criterion listed below.

/quant-dev and /quant-walkthrough, Sprint E12
Use the generic templates from the "How to use this document" section with <n> = 12 and the dashboard tab named above. Add the sprint's tests and failure modes to step 3 of /quant-dev and the research deliverable to the walkthrough's final section.

Sprint E13: Credit Port Design (document only)
December, alongside Bracebridge onboarding. Tier 3.
Stage: Translating the framework: from equities to credit
Book coverage: Everything above, re-specified for corporate credit.
Research questions
Academic. Which assumptions of the equity factor framework (linear exposures, daily liquid prices, diagonal specific risk) hold in corporate credit, and which break?
Practitioner. Which parts of this framework transfer directly to credit, and which require fundamentally different treatment before a credit PM would trust them?
Research. Which EFB numbers (bias bands, hedge efficacy, cost sensitivity) should be re-estimated first in credit, and what data would they need?
Objective
Write the design note that maps every EFB module to its credit counterpart, so the first weeks at Bracebridge start from a plan rather than a blank page. No code in this sprint; the deliverable is a document and a schematic credit X matrix.
Academic concept and intuition
Concept. Framework transfer: return definition (spread or excess-over-Treasury), duration and DTS as exposures, rating and sector buckets, illiquidity and stale marks in the hygiene ledger, and the modules that survive unchanged.
Intuition. The linear algebra does not care about the asset class; the data does. In credit the return definition, the liquidity of the prices and the meaning of specific risk change; the WLS, the FMPs, the decomposition, the hedging algebra and the attribution do not.
Foundation
The formulas the sprint implements; inputs and outputs are labeled in the walkthrough.
Credit X matrix, schematic for three bonds: duration or DTS, spread level, rating dummies, sector dummies, issue size, age, liquidity, spread momentum; return column as excess over duration-matched Treasury.
Implementation scope
Factor mapping table (see the appendix in this roadmap): which equity descriptors become duration or DTS, spread level, rating and sector buckets, issue size, age and liquidity, spread momentum.
Return definition: spread return or excess return over a duration-matched Treasury; the ledger rules for TRACE-style data (stale prints, size filters, dealer marks).
Which modules port unchanged (efb/risk.py, hedge, size, optimize, attribution, perf, hygiene) and which are re-specified (descriptors, universe, returns, costs).
Open questions for Igor and Sergey, written as questions with the EFB evidence that motivates each one.
Deliverables and dashboard increment
docs/credit_port_design.md with the schematic credit X matrix and the module map
Dashboard: Methodology tab: the design note linked; no new panels.
Empirical tests and diagnostics
Tests
Every module in the map with a status and a reason (F13.1); open questions each tied to an EFB number.
Failure modes to look for
Assuming daily prices exist for every bond; treating dealer marks as trades; ignoring carry and roll-down in attribution.
Why this matters to a PM
PM question: "Which parts of this framework transfer directly to credit, and which require fundamentally different treatment?"
Problem it addresses. A credit desk wants better factor models; it does not want an equity model with the labels changed.
Decision it informs. Where to start, what data to request, and which EFB results to reproduce first as a credibility check.
If the analysis is wrong. Porting the specific-risk treatment without accounting for illiquidity; hedging with instruments whose factor is not the model's factor.
Before trusting the output. A module map with reasons, and a first-90-days plan tied to numbers already produced in EFB.
What would falsify this?
A module marked unchanged that in fact depends on an equity-only assumption; an open question with no EFB evidence behind it.
Research deliverable
Credit Port Design Note (docs/credit_port_design.md)
Factor mapping table, schematic credit X matrix, module map with status and reason
Data requirements and the open questions for the research team, each with the EFB number that motivates it
Book connection
Chapters. Everything above, re-specified for credit; APM's asset-class-agnostic machinery is the premise of the whole project.
Understand before implementing: Which assumptions of the linear factor model are about mathematics and which are about markets.
What the implementation teaches that the book cannot: That the port is mostly re-specifying inputs, and that the hard part is the hygiene ledger.
Pre-registered falsification criteria
Numeric thresholds written before the numbers are seen; each is evaluated with a stored number in sprints/E13/RESULTS.json.
ID
Criterion
F13.1
Every EFB module appears in the port map with a status: unchanged, re-specified, or dropped, with one sentence of reason.
Exit criteria
Design note reviewed against the coverage map; nothing unmapped. Research deliverable written and linked from the Methodology tab.

/quant-prd, Sprint E13
Paste into a fresh Claude session to generate this sprint's PRD and TASKS.

/quant-prd
This is Sprint E13 of the Equity Factor Book (EFB) project, a
document-only sprint. E1 to E12 exist.
Objective:
Write docs/credit_port_design.md: the mapping of every EFB module to
its corporate-credit counterpart, so that credit factor-model work at
a fixed income fund starts from a plan.
Focus areas:
- Factor mapping: equity descriptors -> duration or DTS, spread level,
rating and sector dummies, issue size, age and liquidity, spread
momentum; schematic credit X matrix for three bonds
- Return definition in credit; ledger rules for TRACE-style data
- Module map: unchanged / re-specified / dropped, one reason each
- Open questions for the research team, each tied to an EFB number
Requirements:
- Every module in the EFB repo appears in the map (F13.1)
- No code; tables and prose only
- No em dashes
Output:
- docs/credit_port_design.md
Research framing (from the roadmap, copy into the PRD verbatim):
- Academic question: Which assumptions of the equity factor framework (linear exposures, daily liquid prices, diagonal specific risk) hold in corporate credit, and which break?
- Practitioner question: Which parts of this framework transfer directly to credit, and which require fundamentally different treatment before a credit PM would trust them?
- Research question: Which EFB numbers (bias bands, hedge efficacy, cost sensitivity) should be re-estimated first in credit, and what data would they need?
- Research deliverable: Credit Port Design Note, written for
a senior quant or risk manager; it must contain the methodology, the
stored numbers, the practitioner conclusion, and a section titled
"What would falsify this?". A negative verdict is a complete
deliverable.
- The TASKS.md must include one task that produces the deliverable and
one that evaluates every falsification criterion listed below.

/quant-dev and /quant-walkthrough, Sprint E13
Use the generic templates from the "How to use this document" section with <n> = 13 and the dashboard tab named above. Add the sprint's tests and failure modes to step 3 of /quant-dev and the research deliverable to the walkthrough's final section.

Appendix A: credit port mapping
The reason the book is built in equities. Each row is an equity element and the credit re-specification it becomes at Bracebridge. Formulas are unchanged wherever the row says so.
Equity element (EFB)
Credit counterpart
Formula status
Return: excess over RF
Excess return over duration-matched Treasury, or spread return; DTS-scaled variant
Unchanged after re-specification of the return column
Market factor (constant 1)
Credit market factor (IG or HY index excess return); rates factor via key-rate durations
Unchanged
Size (log mcap)
Issue size, issuer size (log)
Unchanged
Beta (to market)
Spread beta, DTS
Unchanged
Momentum (12-1)
Spread momentum; issuer equity momentum
Unchanged
Residual volatility
Spread volatility (residual)
Unchanged
Liquidity (dollar volume)
TRACE volume, bond age, size, days since last trade
Unchanged
Value (book to price)
Spread relative to rating and sector peers (rich or cheap residual)
Re-specified descriptor
Sector dummies (GICS)
Sector dummies plus rating-bucket dummies (AAA to CCC), seniority
Unchanged, more columns
Cross-sectional WLS, FMPs, Fama-MacBeth premia
Same, with weights by size or by inverse spread vol
Unchanged
Sigma = X F X' + D; decomposition; MCR
Same
Unchanged
Risk model evaluation, regimes
Same, with regimes defined on credit spreads (OAS terciles) rather than VIX
Unchanged, regime variable swapped
Hedging with SPY and sector ETFs
Hedging with CDX IG and HY, Treasury futures, LQD and HYG
Unchanged (instrument set swapped)
Sizing and MV optimization
Same, with issue-level position caps and liquidity constraints
Unchanged, constraints extended
Costs: spread and sqrt impact on ADV
Dealer bid-ask by rating and size, staleness of marks
Re-specified cost model
Attribution: holdings-based
Same, with carry and roll-down as explicit terms
Unchanged, two added terms
Hygiene Ledger
Adds stale prints, size filters, dealer-mark rules, index membership files
Unchanged structure

Appendix B: repository and cross-sprint standards
Repository structure
equity-factor-book/
data/
raw/            prices.parquet, factors_ff.parquet
processed/      returns.parquet, universe_membership.parquet, sectors.parquet
models/         TS-v1/, XS-v1/, PCA-v1/, ...
cov/ eval/ hedge/ alpha/ portfolios/ costs/ allocation/ attribution/
VERSION.json
efb/
perf.py vol.py registry.py risk.py cov.py eval_risk.py hedge.py
alpha.py hygiene.py size.py optimize.py costs.py allocate.py
attribution.py
models/ timeseries.py fundamental.py statistical.py
dashboard/
app.py          global sidebar, version and regime selectors, tab router
tabs/           d00_data.py ... d11_attribution.py, methodology.py
live/             evening_job.py, morning_job.py (from v8.x)
notebooks/        E1_walkthrough.ipynb ... E12_walkthrough.ipynb
sprints/          E1/ ... E13/  (PRD.md, TASKS.md, RESULTS.json, PROBES.md)
docs/
hygiene_ledger.md, multiple_testing_ledger.md, credit_port_design.md
research/       E1_data_note.md ... E12_attribution_report.md
tests/
Makefile          rebuild, rebuild-e1, ..., test, dashboard
Engineering discipline
Typed, documented, tested: pytest coverage above 70%; mypy, black, ruff in pre-commit; the test suite never shrinks.
Reproducible: fixed seeds; every artifact carries the data hash of its inputs; make rebuild reproduces the registry from raw.
No look-ahead: anything used as a forecast at t is computed from data through t-1; every sprint runs a shift audit.
Dashboard reads parquet and Supabase only; it never fits a model. A tab that needs a number not in parquet is a missing artifact, not a dashboard feature.
Numbers over adjectives: every /quant-dev output prints values; every walkthrough reconciles to 1e-8.
Ledgers are append-only and timestamped: the Hygiene Ledger (E1 onward) and the multiple-testing ledger (E7 onward).
Research deliverables live in docs/research/ and follow one template: research questions, methodology, stored numbers, practitioner conclusion, what would falsify this, open questions.
No em dashes in any artifact: documents, notebooks, prompts, docstrings, dashboard text.
Sprint exit checklist
All TASKS.md items closed, each with a passing test
Every F criterion evaluated with a stored number in RESULTS.json (pass, fail, or explicitly pending with a reason)
Parquet schemas stable and documented in the PRD
Registry entry written for any new model version
Dashboard tab renders in under 3 seconds with full history; every earlier tab still renders
Walkthrough notebook rendered to HTML and linked from the Methodology tab
Research deliverable written, with its What-would-falsify-this section, and linked from the Methodology tab
Ledger entries for every policy decision made during the sprint
The sprint's PM question answered in one paragraph at the top of the deliverable
Start with Sprint E1 today. Task 0 is the probe scripts; nothing is built until they print. G1 is September 20: E1 to E3 running from raw parquet to dashboard tab D2 in one command, with TS-v1 and XS-v1 in the registry, three walkthroughs rendered, and three research notes written. That is the deadline no visa office can move.
