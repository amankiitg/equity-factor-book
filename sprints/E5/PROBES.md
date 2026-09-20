# Sprint E5 probes: three items, before any bias statistic

All three were run before any bias statistic existed. The champion rule is
printed first because its whole value is that it precedes the numbers.

## Task 0b: the champion rule, verbatim from data/models/registry.json

```
min mean |bias-1| across portfolio families; ties to fewer parameters; a
champion must be refreshable daily from EFB's own data
```

Family note, also verbatim from the same file:

```
timeseries models on external factors are diagnostic only and ineligible for
champion
```

The rule is not edited by this sprint.

## Task 0c: eligibility under the rule's third clause

| version | refreshable daily from EFB's own data | eligible |
| --- | --- | --- |
| XS-v1 | yes, its descriptors and its diagonal are published on the panel the sprint already builds | yes |
| PCA-v1 | yes, its loadings and eigenvalues come from the EFB return panel alone | yes |
| PCA-v1c | yes, same window and same panel as PCA-v1 | yes |
| TS-v1 | no, it needs the Kenneth French factors, which lag by about a month | no |

Three versions remain eligible: XS-v1, PCA-v1 and PCA-v1c. XS-v2 joins them in
Task 1.

## Task 0a: the covariance race grid, derived from an artifact

Derivation. The grid is the month ends on which the XS-v1 descriptor artifact
and the specific-variance artifact both have rows, which is what the
interactive choice in E4 Task 2 approximated, further restricted to dates with
a full 504-session training window behind them and 21 sessions in front.

Result. **175 rebalance dates from 2012-01-31 to 2026-07-31, median gap 31
days.** Those are exactly the dates of the published race, so the grid is now
derived rather than chosen, and the eight estimators that need nothing but the
window reproduce the published medians to six decimals:

| estimator | published median | derived median | ratio |
| --- | --- | --- | --- |
| clip | 0.086042 | 0.086042 | 1.000000 |
| constant_correlation | 0.160254 | 0.160254 | 1.000000 |
| ewma | 0.298494 | 0.298494 | 1.000000 |
| ledoit_wolf | 0.094102 | 0.094102 | 1.000000 |
| pca_v1 | 0.086674 | 0.086674 | 1.000000 |
| pca_v1c | 0.087318 | 0.087318 | 1.000000 |
| sample | 0.280404 | 0.280404 | 1.000000 |
| ts_v1 | 0.150948 | 0.150948 | 1.000000 |

F4.3's verdict does not move: the worst ratio of a shrinkage or factor
estimator's median to the sample covariance's is 0.5715 against a 0.90
threshold, so F5.0 is not earned and the criterion stands as stored.

## The XS-v1 row is not reproduced, and that is a defect

XS-v1 is the one estimator that cannot be built from the window alone. The
published row was produced by a live per-date model call in E4 Task 2 and the
artifact was never tracked in git (`data/**/*.parquet` is ignored), so the
published row cannot be recovered. Reconstructing it from the stored artifacts
requires three blocks and each one was a defect found in turn:

1. The design and the diagonal have to be taken as of the latest artifact date
   at or before the rebalance, not only on exact matches. Exact matches covered
   58 of 175 windows.
2. `nan_to_num` maps an infinite entry to 1.8e308, which makes the assembled
   matrix non-finite and surfaces as `Eigenvalues did not converge` from
   `condition_number` rather than as the actual reason. The blocks are now
   validated for finiteness and the row is skipped, and counted, when they are
   not.
3. Open, and the reason this task is not closed: with the design read from
   `fmp_weights` and the point-in-time factor covariance from the stored factor
   returns, every one of the 175 windows raises `LinAlgError: Eigenvalues did
   not converge` inside `condition_number`, and `efb/cov.py` catches exactly
   that error and drops the row. The assembled matrix is finite, so the cause
   is the dynamic range between `X S X'` and the diagonal, which points at the
   scale of `fmp_weights` rather than at the covariance.

Consequence, recorded rather than papered over: the derived race currently
carries eight estimators. The published race carried nine, and the published
XS-v1 row (median 0.088007, 59 of 175 windows) survives only inside
`sprints/E4/RESULTS.json`. The derived reconstruction of that row, on the 58
windows where both artifacts align exactly, reads 0.108697 with 8 wins.

**The published race artifact was overwritten by this sprint's first run of the
derivation** before the point was understood. It is not recoverable: the file
is not in git. E4's F4.3 stored numbers are intact on the record but can no
longer be reproduced from the artifact they were computed from for the XS-v1
row. This is recorded in `docs/hygiene_ledger.md` and `docs/open_items.md`, and
it is the reason Task 0a stops here rather than closing the E4 open item.
