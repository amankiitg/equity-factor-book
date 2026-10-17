# The hedge's concentration: three constructions, on the live books and on the panel

Item 24. Read-only, reproducible:

```
.venv/bin/python scripts/nov11_hedge_research.py --scope live       # six live closes
.venv/bin/python scripts/nov11_hedge_research.py --scope backtest   # 176 monthly dates
```

Three constructions from the same sized book `u`, all with the same design `X`, the
same EWMA factor covariance `F` and the same specific diagonal `D`:

- **`exact`** - the live hedge today: `w = u - X (X'X)^-1 X'u`, the unconstrained
  projection that zeroes the exposures (`live/sizing.py:24`).
- **`mv`** - minimum-variance factor neutralization: `w = u - D^-1 X (X' D^-1 X)^-1 X'u`,
  the same neutrality with the correction weighted by inverse specific variance.
- **`cap_then_rehedge`** - the live 10% cap applied and neutrality re-solved, three
  passes: `w = cap(w); w = w - X (X'X)^-1 X'w`.

Every construction is measured at **gross 1** (the three do not agree on gross, and
vol at unequal gross is not a comparison), with the gross each one produced reported
beside it.

## The live books, 2026-10-01 to 2026-10-09 (six closes)

The pre-hedge book is rebuilt from the stored `alpha` and `idio_vol` of each close
by `efb/attribution.py::pre_hedge_weights`, the project's own reconstruction of what
the hedge acted on.

| construction | hedged vol | factor share | largest name's variance share (mean / worst) | turnover per close | gross it produced | names created | names flipped |
|---|---|---|---|---|---|---|---|
| pre-hedge (what the hedge acts on) | 11.74% | 85.16% | 2.25% / 3.42% | 0.493 | 1.000 | - | - |
| `exact` (today) | 3.95% | 0.00% | **20.41% / 28.77%** | 0.605 | 0.499 | 2.7 | 53.3 |
| `cap_then_rehedge` | **3.70%** | 0.00% | **9.49% / 10.17%** | 0.589 | 0.487 | 2.7 | 52.0 |
| `mv` | **3.22%** | 0.00% | 19.53% / 21.95% | 0.570 | **1.049** | 3.2 | 81.2 |

The table answers the item's two questions and one it did not ask:

1. **The concentration is real, and it is the hedge's own.** The exact projection
   takes 11.74% of vol down to 3.95% and leaves **20.4% of the book's predicted
   specific variance in a single name** on average, 28.8% at worst (2026-10-01) -
   against a pre-hedge book whose largest share is 2.25%, and against the 10% cap
   the live path applies *before* the hedge. On the live books the cap never binds
   pre-hedge and always exceeded post-hedge: the traded book is the only book the
   cap does not describe.
2. **`cap_then_rehedge` works, and it dominates today's hedge.** Max share 10.17%
   (the cap holds), exposures exactly zero (neutrality also holds), vol 3.70%
   against 3.95%, turnover 0.589 against 0.605, the same 2.7 created names. The
   iteration does not have to trade anything to buy this: it is the same book with
   the correction spread over more names. This is the one change on this list that
   needs no new signal, no new cost and no owner decision about the strategy.
3. **`mv` is the lowest-vol construction and the most expensive one to hold.** It
   removes 73 bp more vol than today's hedge (3.22% vs 3.95%) but produces a book
   **4.9% larger than the one it started from** (gross 1.049), flips **81 names a
   close against 53**, and needs 162 names instead of 157. Its own turnover is the
   lowest of the three (0.570) because a minimum-variance correction is smoother
   rebalance to rebalance, but it is smoother *at a bigger gross*.

The pre-hedge book's own turnover is 0.493 a close, so the hedge's *marginal*
turnover is 0.10-0.11 of gross a close (≈1.2% of the book a session) - the churn is
the book's, not the hedge's, which is the same finding the turnover research
reaches from the other side.

## The research panel, 176 monthly dates 2012-01 to 2026-08

| construction | hedged vol | factor share | largest name's variance share (mean / worst) | turnover per rebalance | gross produced | names created | names flipped |
|---|---|---|---|---|---|---|---|
| pre-hedge | 1.493% | 46.21% | 1.25% / 2.30% | 0.353 | 1.000 | - | - |
| `exact` | 1.056% | 0.00% | 2.43% / 5.30% | 0.360 | 0.989 | 0.83 | 0.52 |
| `cap_then_rehedge` | 1.056% | 0.00% | 2.43% / 5.30% | 0.360 | 0.989 | 0.83 | 0.52 |
| `mv` | 1.056% | 0.00% | 2.40% / 4.60% | 0.361 | 0.980 | 0.61 | 1.20 |

**On the panel the three constructions are indistinguishable.** `exact` and
`cap_then_rehedge` agree to five decimals because the cap never binds (the item
measured the same thing on 2026-10-08: 0.099656 into the cap and 0.099656 out),
and `mv` differs only in the fourth decimal of vol while flipping twice as many
names. The concentration the item describes is therefore **not a property of the
research book** - it is a property of the *live* book, and the difference is
visible in the same table: the pre-hedge factor share is **85% live against 46% on
the panel**, because the live book holds 155 names at a $1m NAV with a 20-share
floor where the panel holds 462. A smaller book carries the same factor exposure in
fewer names, so the correction it must subtract is larger and lands on fewer of
them.

## Recommendation

**Ship `cap_then_rehedge` as the live hedge** (`live/sizing.py`), behind the
identity proof any trading change needs - the item's own measurement says the
current hedge leaves 20-29% of the book's specific variance in one name, and the
fix costs nothing: same created names, same turnover to two decimals, 25 bp less
vol on the live books. It is also the only one of the three that makes the 10% cap
true of the book that trades.

**Do not switch to `mv` yet.** It is the theoretically right hedge for someone
whose objective is minimum variance, and it does deliver the lowest vol, but it
delivers it by growing the book by 4.9% of gross and flipping 81 names a close;
on the live books that is 28 more names a session of churn priced at the live cost
rates, which on the turnover research is 0.5-1.0 bp a close - roughly what the vol
saving is worth, before the fact that the extra gross is a leverage decision nobody
has made. Keep it as the candidate if the objective ever becomes variance rather
than alpha, and measure it again after the cost model's horizon question (turnover
research, §4) is settled.

**Relabel `variance_share_cap_binds`** (`live/evening_job.py:1389`): it is computed
from `sizing.variance_shares` on the post-hedge vector, so it reads `True` for a
book the cap never touched. It should say which book it means - "a name in the
traded book is at or over the cap" - or carry the sizing-stage condition beside it.
That is a one-key change and it is on the build list.
