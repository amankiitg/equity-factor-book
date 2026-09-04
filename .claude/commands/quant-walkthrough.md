---
description: Write the sprint walkthrough notebook that reproduces every number by hand. Usage: /quant-walkthrough E1
argument-hint: [E1..E13]
---

Run once the sprint's exit criteria are met. The notebook is the promotion
artifact for the model version and the evidence section of the research
deliverable.

For E1 use the verbatim prompt below. For E2 and E3 copy the
`/quant-walkthrough, Sprint E<n>` block verbatim from `docs/roadmap_v2.md`.
E4 onward uses the generic template below.

---

## Verbatim prompt for Sprint E1

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

## Generic template (E4 onward)

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
