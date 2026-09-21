# E5 risk model diagnostic: is the risk number trustworthy, and by how much in stress?

Sprint E5, 2026-09-20. Every number in this memo is quoted from
`sprints/E5/RESULTS.json`, `data/models/registry.json` or a stored parquet
artifact, and `tests/test_e5_memo.py` fails the moment one drifts.

## The answer, in one paragraph

The XS family's risk numbers are the most trustworthy ones this project has,
but none of the six versions is calibrated: every version underforecasts the
long-only family (the factor versions sit at 1.105, the rest at 1.128 to
1.131) and every version underforecasts stress by a large margin, worst in
2020 Q1 when the champion's bias reached 2.8471 and even the best version
reached 2.8305. The pre-registered champion rule declares **XS-v1** with a
deciding number of 0.0607 (mean |bias-1| across the four families), and the
recommended stress haircut on that champion is 1.8471: in stress, multiply
the model's forecast by 2.85 rather than trust it. A bias number on a calm
day is fine; the days that matter are the 2020 Q1 days, and on those days
every model fails in the same direction, which is why the haircut is stored
as a number with a stated basis rather than hidden in prose.

## The champion decision, with its rule and its arithmetic

The rule was pre-registered before any bias statistic existed and is applied
exactly as printed:

```
min mean |bias-1| across portfolio families; ties to fewer parameters; a
champion must be refreshable daily from EFB's own data
```

TS-v1 is diagnostic only and ineligible, per the family note. The arithmetic
on the stored family-pooled table:

| version | mean |bias-1| | inside 0.9 to 1.1 every family | champion |
| --- | --- | --- | --- |
| XS-v1 | 0.0607 | no | yes |
| XS-v2 | 0.0672 | no | no |
| PCA-v1 | 0.1388 | no | no |
| PCA-v1c | 0.1392 | no | no |

The gap between XS-v1 and XS-v2 (0.0065) is outside the winner's confidence
band, so the tiebreak is never reached, and the stress-regime guard does not
fire: the champion's high-VIX bias of 1.3239 is within 0.01 of the best
runner-up's, not materially worse. The champion is XS-v1, declared by the
rule, not chosen.

## The full heatmap: pooled bias by version and family

| version | long only | long short | factor tilted | sector concentrated |
| --- | --- | --- | --- | --- |
| xs_v1 | 1.1050 | 1.0186 | 0.9726 | 1.0917 |
| xs_v2 | 1.1048 | 1.0256 | 0.9426 | 1.0809 |
| sample | 1.1304 | 1.0752 | 1.1859 | 1.1258 |
| ts_v1 | 1.1312 | 1.0663 | 1.6456 | 1.2343 |
| pca_v1 | 1.1286 | 1.0729 | 1.2238 | 1.1301 |
| pca_v1c | 1.1284 | 1.0755 | 1.2177 | 1.1352 |

Two structural facts. First, every version sits above 1.10 on long only,
which is why F5.1 fails: no model is calibrated across all four families.
Second, the XS versions dominate the factor tilted family (0.9726 and 0.9426)
where the covariance-only models fail badly (1.1859 to 1.6456): the tilted
books load on the styles XS-v1 models explicitly.

## The criteria, as stored

| ID | verdict | headline number |
| --- | --- | --- |
| F5.1 | fail | no version inside 0.9 to 1.1 on every family; the closest mean family bias is XS-v2 at 1.0385 |
| F5.2 | fail | pca_v1c's long/short distance 0.0755 misses the sample's 0.0752 by 0.0003 |
| F5.3 | pass | 2020 Q1 is every version's worst episode, reported not hidden |
| F5.4 | pass | regime table for all six versions; champion's stress bias 1.3239 and recovery 13 trading days stored |
| F5.5 | pass | XS-v2 against XS-v1 stored both ways |

F5.2 deserves its own sentence: it fails by three ten-thousandths. The
long/short |bias-1| of pca_v1c is 0.0755 against the sample covariance's
0.0752, and the criterion says every factor version must clear the sample.
It is recorded as a fail with its mechanism, not rounded away.

## The regime table: bias by VIX tercile and episode, with recovery

| version | 2020 Q1 bias | 2022 bias | recovery from the 2020 Q1 peak (trading days) |
| --- | --- | --- | --- |
| xs_v1 | 2.8471 | 1.1393 | 13 |
| xs_v2 | 2.8305 | 1.1292 | 13 |
| sample | 3.2050 | 1.1892 | 13 |
| pca_v1 | 3.2236 | 1.1993 | 13 |
| pca_v1c | 3.2320 | 1.2013 | 13 |
| ts_v1 | 3.4989 | 1.3552 | 13 |

The champion's high-VIX-tercile bias is 1.3239 against 1.1050 in calm
regimes, and its worst single family in 2020 Q1 is long only at 3.6738. The
recommended stress haircut is therefore **1.8471**, the champion's 2020 Q1
bias of 2.8471 minus one: a stress forecast is the model times 2.85, on the
stated basis that this is the fraction the model underforecast in its worst
named episode. Every version recovers within 13 trading days after the
2020-03-16 peak, so the bias is a level problem, not a persistence problem.

## XS-v2 against XS-v1, on the same families

| family | XS-v1 bias | XS-v2 bias | ratio |
| --- | --- | --- | --- |
| factor tilted | 0.9726 | 0.9426 | 0.9691 |
| long only | 1.1050 | 1.1048 | 0.9998 |
| long short | 1.0186 | 1.0256 | 1.0069 |
| sector concentrated | 1.0917 | 1.0809 | 0.9901 |

The residual covariance fixes the tilted books (0.9426 against 0.9726) and
gains a hair on the other families, but it costs XS-v1's lead on long/short,
which is why the rule, run on all four families, still prefers XS-v1. The
gain the sprint was built to find is real and it is confined to the family
the residual structure should help most, which is exactly the kind of
narrow result the criterion exists to surface.

## The champion's known weaknesses

1. **Long only is not calibrated.** XS-v1's long-only bias is 1.1050, outside
   the 0.9 to 1.1 band, and no version is inside it on every family.
2. **Stress is not calibrated.** The high-VIX bias is 1.3239 and the 2020 Q1
   bias is 2.8471; the 1.8471 haircut is an admission, stored as a number.
3. **The horizon direct estimate disagrees with the scaled one.** The
   sqrt(21) scaled bias on long only is 0.9787 against a direct 21-day
   1.1594, so the 21-day model itself overshoots where the 1-day model does
   not; the ratio is stored per family and is not close to one.
4. **The universe is a survivor-only cross-section.** The 502 sector-mapped
   names carry the documented look-ahead before 2015-10-23 in size and
   sqrt(mcap) weights, and every number above inherits it.
5. **The decision was close.** XS-v2 trails by 0.0065 on the deciding number
   and wins the factor tilted family outright; a reweighted family set could
   move the call, which is why the next section exists.

## What would falsify this?

- The champion's edge disappears when the families are reweighted or the seed
  books are excluded: the decision was an artefact of the sample.
- Every version's bias moves outside 0.9 to 1.1 on a second horizon, so the
  ranking is horizon specific rather than a property of the models.
- The XS-v2 gain is confined to the families it was built on and reverses on
  long-only books, so the residual covariance is a momentum-book fix rather
  than a risk-model fix. (The stored ratio on long only is 0.9998, so this
  is currently a draw, not a reversal.)
- The regime split shows the ranking reverses in stress, so a single champion
  cannot be declared for all regimes. (The high-VIX gap between XS-v1 and
  XS-v2 is 0.01, so this has not happened yet.)
