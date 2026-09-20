# Sprint E4 Task 0 Probes

Sprint E4, 2026-09-20. Task 0 runs before any estimation, and this file is its
record. Every probe is implemented in `efb/probes.py` and run with
`python -m efb.probes --e4` (`--e4-offline` skips the network). The unit tests
are in `tests/test_e4_probes.py` and run offline.

Inherited constants this file relies on and does not restate: MODEL_START is
2011-01-03, XS-v1 is the incumbent with champion false and
eligible_for_champion true, TS-v1 is diagnostic only, the production
volatility estimator is EWMA(0.97), the regressand is the total return, and
Size and the sqrt(mcap) weights carry the documented look-ahead before
2015-10-23.

## 0a. Eigenvalue feasibility

N is the number of names with a complete return history inside the calendar
year, in the post-exclusion panel. T is the rolling window the covariance
estimator will use. Marchenko-Pastur needs both before any factor count is
claimed.

| Universe | 2011 N | 2015 N | 2020 N | 2026 N | median names present |
| --- | --- | --- | --- | --- | --- |
| model universe, sector-mapped | 428 | 457 | 481 | 499 | 473 (minimum 428) |
| panel, all names with a return | 517 | 557 | 584 | 613 | 584 (minimum 517) |

Ratios at the window lengths the sprint will use, taking the median name count
over the 3941 sessions from 2011-01-03 to 2026-09-03:

| Universe | T = 252 | T = 504 | T = 756 |
| --- | --- | --- | --- |
| model universe | N/T 1.877, MP edge 5.617 | N/T 0.938, MP edge 3.876 | N/T 0.626, MP edge 3.208 |
| panel | N/T 2.317, MP edge 6.362 | N/T 1.159, MP edge 4.312 | N/T 0.772, MP edge 3.530 |

Reading. The MP edge is the upper edge of the Marchenko-Pastur support for a
correlation matrix, `(1 + sqrt(N/T))^2`. With N near T the noise band is wide:
at T = 504 the model universe puts the edge at 3.876, so any eigenvalue below
about 3.9 is inside the noise band and a factor count read off raw
eigenvalues would be too high. This is the reason the sprint runs the lab at
T = 504 rather than 252, and the reason the residual PCA is quoted against the
same edge rather than against its own spectrum alone. At T = 252, N/T is
1.877 for the model universe and the edge is 5.617, which is where the
"eigenvalues near 1 and above" intuition breaks down.

## 0b. Point-in-time sector and constituent sources

Ten known delisted index members, with the removal date the pinned changes
table carries. Source 1, the changes table itself, dates membership and names
the issuer: it returned a dated removal for all ten names.

| Ticker | Removed security | Removal date |
| --- | --- | --- |
| CPWR | Compuware | 2011-12-31 |
| EP | El Paso Corporation | 2012-05-17 |
| MI | Marshall & Ilsley | 2011-07-05 |
| POM | Pepco Holdings | 2016-03-30 |
| ABK | Ambac Financial | 2008-06-10 |
| ABS | Albertsons | 2006-06-02 |
| ACAS | American Capital | 2009-03-03 |
| ACE | Chubb | 2016-01-19 |
| AGN | Allergan | 2015-03-23 |
| AKS | AK Steel | 2011-12-16 |

Source 2, EDGAR company search keyed by name, returned an assigned SIC code and
a CIK for four of the ten. SIC is the filer's own code and the submissions file
dates that filer's filings, so the classification belongs to the issuer rather
than to whoever holds the ticker today.

| Ticker | Issuer | SIC | SIC description | 10-K range on file |
| --- | --- | --- | --- | --- |
| CPWR | Compuware | 7372 | Services-Prepackaged Software | 2006-06-13 to 2014-07-29 |
| POM | Pepco Holdings | 4931 | Electric and Other Services Combined | 2009-03-02 to 2026-02-12 |
| ABK | Ambac Financial | 6351 | Surety Insurance | 2011-03-16 to 2026-03-04 |
| AKS | AK Steel | 3312 | Steel Works, Blast Furnaces and Rolling Mills | 2013-02-28 to 2020-03-10 |

The remaining six did not return a usable code, and the failure mode is
informative rather than random: a name search matches the modern namesake. MI
resolved to a CIK with 1002 filings and no SIC in the company block, ACE
resolved to Chubb's surviving registrant, ABS resolved to the 2020 Albertsons
relisting, ACAS to a current entity of the same name, and EP returned no
company block at all. So the source is reachable but not reliably keyed: it
needs an issuer-identity step, the same one `docs/open_items.md` already
records as the FIGI or PERMNO item, before a name maps to the right filer.

Source 2b, the Wikipedia REST summary, returned a one-line description for
four of ten names (Albertsons "American supermarket company", American Capital
"U.S. financial services firm", Allergan "American pharmaceutical company", AK
Steel "Defunct steel manufactuer") and was rate limited with HTTP 429 for the
rest on this run. Prose descriptions are not a sector taxonomy and one of the
four returned a disambiguation page, so this source is recorded as
unavailable for classification even when it answers.

Source 3, the yfinance sector field, returned a sector for exactly four of the
ten names, and in every case it was the current holder of the ticker rather
than the delisted issuer:

| Ticker | Removed issuer | yfinance long name | yfinance sector |
| --- | --- | --- | --- |
| CPWR | Compuware | Ocean Thermal Energy Corpora | Utilities |
| EP | El Paso Corporation | Empire Petroleum Corporation | Energy |
| MI | Marshall & Ilsley | NFT Limited | Consumer Cyclical |
| POM | Pepco Holdings | Pomdoctor Limited | Healthcare |

Verdict. No point-in-time GICS sector source is reachable. What exists is a
dated constituent list (already in the project), an issuer-level SIC code for a
minority of delisted names behind an identity step that the project does not
have, and a symbol-keyed sector field that is actively wrong for exactly the
reused symbols F2.6 found. The survivor restriction therefore stays open, and
Task 4 takes the measurement path rather than the repair path: the distortion
is priced, and the SIC finding is recorded as the partial source it is.

One specification note for Task 4. The brief's measurement window, "years where
the sector-mapped share is above 90 percent by market cap", selects every year
in the sample, because 2010 is already at 91.1 percent by market cap (8.85
percent outside). Cut by name instead and only 2024, 2025 and 2026 qualify,
which is too short a subsample to re-estimate the model on. The measurement
therefore needs a different cut, proposed as: re-estimate XS-v1 on the
low-distortion era (2020 onward, where the share outside is under 19 percent by
name and under 2 percent by cap) and compare premia, mean R squared and
specific variance against the full sample, and separately measure the
excluded names' own return and volatility differential against the included
names, which is available in the panel for 2010 to 2016. This needs sign-off
before Task 4 is written.

## 0c. The momentum factor's own volatility by exposure tercile

The terciles are the ones E3 stored in
`data/eval/xs_bias_by_exposure.parquet`: the momentum book's 141 rebalances
sorted on its own momentum exposure into three groups of 47. The probe
recomputes the grouping, checks it against the stored exposure means, and then
measures the factor itself.

| Bucket | Months | Exposure mean | Stored exposure mean | Predicted book vol | Realized book vol | Bias | Factor vol, forward 21d | Factor vol, trailing 21d |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| low | 47 | 0.561474 | 0.561474 | 0.054741 | 0.047864 | 0.895986 | 0.044215 | 0.047856 |
| mid | 47 | 0.731709 | 0.731709 | 0.058397 | 0.030325 | 0.584095 | 0.048546 | 0.048345 |
| high | 47 | 0.871312 | 0.871312 | 0.058181 | 0.029207 | 0.519080 | 0.053178 | 0.050125 |

Swings across the three buckets, low to high:

| Quantity | min | max | max minus min | low to high |
| --- | --- | --- | --- | --- |
| predicted book vol | 0.054741 | 0.058397 | 0.003656 | +0.003440 |
| realized book vol | 0.029207 | 0.047864 | 0.018658 | -0.018658 |
| factor vol, forward 21d | 0.044215 | 0.053178 | 0.008963 | +0.008963 |
| factor vol, trailing 21d | 0.047856 | 0.050125 | 0.002269 | +0.002269 |
| bias mean | 0.519080 | 0.895986 | 0.376906 | -0.376906 |

The tercile reconstruction reproduces the stored exposure means to six
decimals. Two numbers in the sprint brief were checked against the artifact
before Task 3 is written on them, and one of the two does not reproduce:

1. The brief says predicted volatility moves 0.0055 across the terciles. The
   stored artifact gives a maximum minus minimum of 0.003656 and a low to high
   movement of 0.003440. There is no pair of the three stored predicted
   volatilities that differs by 0.0055.
2. The brief says realized volatility moved 0.0187 in the opposite direction.
   That reproduces: 0.047864 down to 0.029207 is 0.018658.

The finding, and it decides Task 3. The momentum factor's own realized
volatility is not lower in the high-exposure months. It rises monotonically
with the book's exposure, from 0.044215 in the low tercile to 0.053178 in the
high one, and the near-dated measure is nearly flat (0.047856 to 0.050125). In
those same months the book's own realized volatility falls by two thirds, from
0.047864 to 0.029207, and the model's predicted volatility barely moves. So
explanation (ii) as the brief states it, that the factor was genuinely quiet
when the book was most exposed, is refuted by the measurement: the factor was
louder. The miss is not a quiet factor and not a flat factor variance; it is
that the book's realized risk is not a monotone function of its measured
momentum exposure, while the model prices it as though it were. Task 3 still
tests both explanations as written, with the half-life sweep on one side and
this measurement on the other, and the deliverable names which the evidence
supports. This probe already points to the answer being neither of the two as
stated, which is a result worth recording rather than a reason to reshape Task
3.

## What Task 0 changes downstream

1. Task 3 keeps both explanations and prints both, with the added requirement
   that the deliverable say plainly that the quiet-factor explanation is
   refuted by the factor's own realized volatility, so that the sprint cannot
   report a two-way test as though the answer were one of the two.
2. Task 4 is a measurement, not a repair, and its window needs the sign-off
   described above because the brief's window rule is degenerate.
3. Task 1 must quote N/T and the MP edge from 0a beside every factor count, and
   the eigenvalue work should run at T = 504 where the edge is 3.876 in the
   model universe and 4.312 in the panel.
4. The registry and the memo should carry the SIC finding as a partially
   reachable source with its identity caveat, because it is the most promising
   route to closing the survivor restriction and it needs the FIGI or PERMNO
   step that is already an open item.
