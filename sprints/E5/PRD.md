# Sprint E5 PRD: Risk Model Evaluation

Sprint E5, 2026-09-20. Tier 2. Gate G2. The sprint that declares a champion.

## Research framing, copied from the roadmap

- Academic question: How do we test whether a covariance forecast is
  calibrated, at the portfolio level and across horizons?
- Practitioner question: Can I trust the risk number I am looking at, and by
  how much does it underforecast when I need it most?
- Research question: Which model version is best calibrated across portfolio
  types and regimes, and how much worse is every model in stress?

Objective. Test every model version the way a vendor model would be tested:
bias statistics, coverage, calibration and horizon consistency across families
of portfolios, then declare a champion by a rule written down before the
numbers were seen.

## The champion rule, verbatim from data/models/registry.json

```
min mean |bias-1| across portfolio families; ties to fewer parameters; a
champion must be refreshable daily from EFB's own data
```

Family note, also verbatim from the registry:

```
timeseries models on external factors are diagnostic only and ineligible for
champion
```

The rule is not edited by this sprint. Task 0b prints it before a single bias
statistic exists, and the walkthrough shows that it did.

## Inherited constraints, all hard

1. MODEL_START is 2011-01-03. The panel is the post-exclusion returns file;
   stale, outlier and interior-NaN rows are excluded and the counts printed.
2. Four registered versions, none champion: TS-v1 (diagnostic only, external
   factors, ineligible), XS-v1, PCA-v1 (correlation), PCA-v1c (covariance).
   Task 1 adds XS-v2, and XS-v1 is not edited.
3. The regressand is the total return. Size and the sqrt(mcap) weights carry a
   documented look-ahead before 2015-10-23.
4. The XS-v1 universe is the 502 sector-mapped names, a survivor-only
   cross-section. Every E5 number inherits it and says so once.
5. A stored criterion is never reworded. F5.1 to F5.3 are copied verbatim from
   `docs/roadmap_v2.md`. New findings take new IDs.
6. No number in any walkthrough or deliverable is typed by hand. The
   deliverable ships a traceability test of the `tests/test_e4_memo.py` kind,
   per the E4 process decision.
7. Prefer medians and win counts to means wherever a distribution is skewed.

## Pre-registered falsification criteria

F5.1, F5.2 and F5.3 are the roadmap's, copied verbatim.

| ID | criterion | threshold |
| --- | --- | --- |
| F5.1 | At least one model version achieves mean bias between 0.9 and 1.1 across all portfolio families. | 0.9 <= mean bias <= 1.1 for every family for at least one version |
| F5.2 | Factor-based models beat the sample covariance on bias for long/short portfolios. | every factor version's long/short mean bias closer to 1 than the sample covariance's |
| F5.3 | Bias is worst in 2020 Q1 for every model. This is expected and is reported, not hidden. | every version's 2020 Q1 bias is its worst episode, and it is reported |
| F5.4 | Regime table produced for every model version; the champion's stress-regime bias and its recovery time in trading days are stored alongside its average bias. | stored for every version, champion's numbers present |
| F5.5 | New in E5: XS-v2's bias against XS-v1's on the same families, stored both ways. | stored, whatever it shows |
| F5.0 | New in E5, conditional on Task 0a: the race grid's effect on F4.3. | stored only if Task 0a moves F4.3's verdict |

F5.5 exists because E4 left the residual-covariance question open on four
independent measurements and this sprint builds the version that answers it.

## The four stop conditions this sprint carries

1. Task 0a moves F4.3's verdict. That is a finding about grid sensitivity: store
   it as F5.0, keep both numbers, and report.
2. XS-v2 cannot be built as specified. Report before improvising a variant.
3. No version lands inside 0.9 to 1.1 mean bias across all families: F5.1 fails,
   no model is fit for decisions, print the table and stop before declaring a
   champion anyway.
4. Two versions tie inside the confidence band and the rule's tiebreak does not
   separate them.
5. Any earlier stored criterion, F1.x to F4.x, changes verdict.
6. A build, render or publish step fails in a way two attempts cannot fix.

Everything else, including an unfavourable number, is recorded and the run
continues.

## Task 0, three items before any bias statistic

a) Close the E4 open item on the covariance race grid: derive the rebalance grid
   from an artifact, rebuild `data/eval/cov_horse_race.parquet` from it, and
   confirm F4.3's verdict. Afterwards `make rebuild` reproduces F4.3 from raw.
b) Print the champion rule out of `registry.json`, verbatim, before any bias
   statistic exists.
c) Print each candidate version's eligibility under the rule, with the reason.
   TS-v1 is ineligible because it needs the Kenneth French factors, which lag by
   about a month.

## Task 1: XS-v2

XS-v1 with the diagonal specific variance replaced by a residual covariance: a
low-rank plus diagonal structure on the specific returns, k leading residual
principal components plus the shrunk diagonal remainder, with k chosen by the
Marchenko-Pastur rule the project already uses and stored. Registered with
champion false, eligible true, its own parameters, data hash and artifacts hash.
XS-v1 is not edited.

## Tasks 2 onward: the evaluation

Portfolio families from the panel with no look-ahead: long only, long short,
factor tilted (one book per style) and sector concentrated, at least 50 random
portfolios per family plus the two seed books from E2 and E3 so the seed numbers
stay comparable across sprints.

Standardized returns z_t = r_t / sigma_hat_{t|t-1}; bias B = sqrt(mean of z
squared) with its confidence band; rolling 12-month bias. Coverage: share of |z|
above 1.96 against a nominal 5 percent, Q-Q, MAD ratio, at portfolio and asset
level. Horizon consistency: the 1-day model scaled by sqrt(21) against a
directly estimated 21-day model. Regime analysis: bias, coverage and recovery
time within VIX terciles and within the named episodes 2020 Q1 and 2022, with
the recovery time in trading days for the champion and a recommended stress
haircut.

The champion rule is applied exactly as printed in Task 0b, with the arithmetic
shown, and `champion: true` is set on that entry alone. If two versions tie
inside the confidence band, that is said and the rule's tiebreak is applied
rather than a choice being made.

## Deliverables

- `efb/eval_risk.py`, `data/eval/bias_{model}_{family}.parquet`, and the regime
  and horizon tables
- `data/models/XS-v2/*`, one more registry entry
- Dashboard tab D4 Risk Model Evaluation: bias heatmap by version, family and
  regime; rolling 12-month bias with bands; calibration and Q-Q; the horizon
  table; the champion badge showing the rule and the deciding number
- `docs/research/E5_risk_model_diagnostic.md` with its traceability test
- `notebooks/E5_walkthrough.ipynb`, rendered and published
- `make rebuild-e5`, with `make rebuild` extended to E1 through E5

## Dashboard D4 spec

Every panel builder raises on an empty read, and every earlier tab still renders
under each registered version. No panel fits a model; D4 reads parquet only.

## Book connection

EQI Ch5 (evaluating risk models); APM Ch3 and Ch7 (what a good risk number looks
like). What the implementation teaches that the book cannot: the regime
dimension, because averages hide the only days that matter, and that champion
selection is a governance act whose rule must precede the numbers.

## What would falsify the sprint's conclusion

- The champion's edge disappears when the families are reweighted or when the
  seed books are excluded: the decision was an artefact of the sample.
- Every version's bias moves outside 0.9 to 1.1 on a second horizon, so the
  ranking is horizon specific rather than a property of the models.
- The XS-v2 gain is confined to the families it was built on and reverses on
  long-only books, so the residual covariance is a momentum-book fix rather than
  a risk-model fix.
- The regime split shows the ranking reverses in stress, so a single champion
  cannot be declared for all regimes.
