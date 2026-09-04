---
description: Execute the highest-priority open EFB sprint task, tests first. Usage: /quant-dev E1
argument-hint: [E1..E13]
---

Pick the highest priority open task in `sprints/E<n>/TASKS.md` (first `- [ ]`,
P0 before P1 before P2). Announce which task you are working on. Follow TDD:
write the test first, run it to see it fail, implement the minimum code, re-run
until green. Numbers over adjectives: print inputs, intermediate quantities and
outputs for AAPL, XOM, JPM and one seed portfolio. Store every F criterion you
touch in `sprints/E<n>/RESULTS.json`.

For E1 use the verbatim prompt below. For E2 and E3 copy the
`/quant-dev, Sprint E<n>` block verbatim from `docs/roadmap_v2.md`. E4 onward
uses the generic template below.

---

## Verbatim prompt for Sprint E1

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

## Generic template (E4 onward)

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
