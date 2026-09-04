# Hygiene Ledger

Append-only, timestamped record of every data policy decision in the EFB.
Each entry has a date, the decision, and the reason. Entries are never
edited or removed; corrections are new entries.

## 2026-09-04: Wikipedia changes table pinned to revision 1368675864

Decision. The S&P 500 constituent changes table is read from Wikipedia
revision 1368675864 (2026-08-10), not from the live page.

Reason. The live page removed the "Selected changes" table on 2026-08-11.
Revision 1368675864 is the last revision that still publishes it and
covers 1976-07-01 to 2026-08-05, enough for the 2010-to-today universe.
If the table returns to the live page, a later sprint re-pins and updates
this entry.

## 2026-09-04: FRED DTB3 cross-check recorded as null

Decision. The risk-free rate is the Kenneth French daily RF column. The
FRED DTB3 cross-check is recorded as a null.

Reason. FRED times out from the build host (three attempts, up to 90 s).
Per F1.1, a failing source is recorded in the ledger and the design
adapts; it is never silently dropped. FF RF is the authoritative daily
risk-free rate for E1.

## 2026-09-04: Share-class tickers mapped to yfinance symbols

Decision. Wikipedia tickers with a dot (BF.B, BRK.B) are requested from
yfinance with a hyphen (BF-B, BRK-B) and mapped back to the Wikipedia
form in every artifact.

Reason. yfinance uses the hyphen convention for share classes. Without
the mapping the two current members returned no data.

## 2026-09-04: yfinance Close is split-adjusted; Adj Close adds dividends

Decision. The price pipeline treats yfinance Close as already
split-adjusted and Adj Close as dividend-adjusted. The adjusted-close
audit compares Adj Close total returns with (close + dividend) / prior
close and never reapplies split factors.

Reason. Verified on the delivered series: the split action column records
split events whose adjustment is already inside Close. Reapplying the
factor doubles the adjustment and manufactures fake returns.

## 2026-09-04: Adj Close is authoritative for returns on corporate-action days

Decision. Returns (simple, log, excess) are computed from Adj Close.
Days where the audit disagrees with the close-plus-dividend series by
more than 1 bp are logged in events.parquet as corporate-action events;
the return is never overwritten.

Reason. On merger and special-dividend days (for example BKR on
2017-07-05, a $17.50 special distribution in the GE Oil and Gas
combination) the close-plus-dividend series and Adj Close disagree by
design, because the special distribution does not belong to the
continuing entity. Adj Close is the consistent continuing-holder series.

## 2026-09-04: Point-in-time flags per field

Decision. Per-field point-in-time status:

- prices (open, high, low, close, adj_close, volume, dividend): treated
  as point-in-time as delivered by the vendor, with the caveat that
  vendors revise historical series; rebuilds re-download and re-hash.
- universe membership: point-in-time by construction, rebuilt from the
  changes table, except that before the earliest covered event
  (1976-07-01) membership is extended backward unchanged.
- gics_sector, gics_sub_industry: NOT point-in-time. Known only for
  current members as of the snapshot date.
- shares outstanding: NOT point-in-time. yfinance returns a history for
  10 of 12 sampled names but it is current-vintage data, not the value
  known at each date. No artifact is built from it in E1.
- risk-free rate: FF RF is the daily series; not subject to look-ahead
  because it is a market-wide rate.

Reason. Free sources give current snapshots, not historical vintages.
Anything dated t that feeds a forecast must be data known at t; fields
flagged not point-in-time must never feed a forecast unmodified.

## 2026-09-04: Missing-data policy for prices

Decision. Missing prices stay NaN in the raw artifact. Returns are NaN
on any day where either leg of the return is missing. Coverage is
measured, never imputed.

Reason. Imputation hides coverage gaps from the dashboard and the
research gates. A later sprint that needs filled prices adds an explicit
imputation step with its own ledger entry.

## 2026-09-04: Delisting handling

Decision. A delisted name keeps its rows through its last traded day and
is NaN afterward. The last non-NaN return is not the delisting return:
no delisting-return source exists in the free stack. Returns after the
last price are documented delisting rows under F1.2.

Reason. CRSP-style delisting returns are not available from free
sources. Recording the policy prevents later sprints from confusing
post-delisting NaN with missing data.
