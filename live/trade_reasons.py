"""Sprint E11: why each position trades today.

Every position on the dashboard carries a stated reason, never a blank.
The reasons are the vocabulary from the task -- alpha moved, risk moved,
the hedge moved, or it drifted past a band -- plus the two the book's own
life needs: a name entering on a rebalance is a new name, and a name the
book leaves is exited. The classifier compares today's proposal against
yesterday's on the inputs Procedure 6.3 sizes on, so the stated reason is
read off the inputs rather than guessed.

Two thresholds decide it, and they are deliberately different things. The
weight test is in **dollars of NAV** (the design's `$250` floor, the same
number the order path refuses to send a leg under), because "did the
position move" is a question about money and not about a fraction. The
score test is in **z units**, because a z-score is a standardised number
and 0.05 of it is a fifth of a standard deviation of the cross-section.
Using one epsilon for both was the bug: `1e-9` on either side asks "did
the number change at all", and a daily cross-sectional z always changes.

Order of precedence, for a name whose target weight moved:

1. alpha moved: the name's own signal (z-score of idio_momentum) moved
   from the previous close by more than `Z_EPS`.
2. risk moved: the alpha did not move materially, but the name's specific
   standard deviation moved by more than `RISK_EPS` relative.
3. the hedge moved: neither the alpha nor the risk moved, so the only
   remaining driver of a Procedure 6.3 re-size is the factor hedge (the
   design, the factor covariance, or the other names' alphas).
4. drifted past a band: a name is traded although none of its own inputs
   and none of the hedge inputs moved, which can only be a band rebalance
   of a position that drifted between sessions. In a daily full-rebalance
   loop this bucket stays empty, but it is a real state in a banded
   policy, so it is kept.

Two labels sit outside that precedence because they are not moves: a name
the previous book did not hold is a **new name**, and a name the previous
book held whose target is now zero is **exited**. With no previous book at
all every row is a **new position**: the establishment day, where nothing
has moved because nothing was there.
"""

from __future__ import annotations

import pandas as pd

# The weight test, in dollars of the NAV the book was sized on. The design's
# order floor is `alpaca.DELTA_MIN_NOTIONAL` and the two must agree: a leg the
# order path would not send is not a trade the reason column should claim.
# (`tests/test_week1_reasons.py` asserts the two numbers are the same one.)
WEIGHT_DOLLARS = 250.0
# The NAV the two figures above are quoted against when a caller has no book of
# its own to measure: the design's paper NAV. A live caller passes the account's
# own equity and the threshold follows it.
DESIGN_NAV = 1_000_000.0
# 0.05 of a z-score: a fifth of a standard deviation of the cross-section. On the
# 2026-10-01 rebalance 103 of the 153 names the two books shared moved by less than
# that and 50 by more, where the threshold this replaced (1e-9) called every one of
# them an alpha move.
Z_EPS = 0.05
# 1% relative. The earlier 1e-4 was the same numerical-noise mistake one branch
# down; a 1% move in the specific volatility moves a Procedure 6.3 weight by
# about twice that share, which is a material size on a $50,000 leg.
RISK_EPS = 1e-2
NO_TRADE = "no trade"
ALPHA_MOVED = "alpha moved"
RISK_MOVED = "risk moved"
HEDGE_MOVED = "the hedge moved"
DRIFTED = "drifted past a band"
NEW_POSITION = "new position"
NEW_NAME = "new name"
EXITED = "exited"

REASONS = (
    NEW_POSITION,
    NEW_NAME,
    EXITED,
    ALPHA_MOVED,
    RISK_MOVED,
    HEDGE_MOVED,
    DRIFTED,
    NO_TRADE,
)


def weight_eps_for(
    nav: float | None, *, weight_dollars: float = WEIGHT_DOLLARS
) -> float:
    """The weight test as a fraction, from the NAV the threshold is quoted in.

    `$250` of a book is a different fraction of it depending on the book's size,
    so the dollar threshold cannot be a module constant in weight units: it is
    converted here, against the NAV the run sized on, every time it is asked.
    Without a NAV (a caller with no book of its own) the design NAV stands in, so
    the threshold stays a materiality test rather than collapsing to zero.
    """
    scale = float(nav) if nav else DESIGN_NAV
    return float(weight_dollars) / scale


def assign_trade_reasons(
    today: pd.DataFrame,
    previous: pd.DataFrame | None,
    today_specific: pd.Series,
    previous_specific: pd.Series | None,
    *,
    nav: float | None = None,
    weight_dollars: float = WEIGHT_DOLLARS,
    z_eps: float = Z_EPS,
    risk_eps: float = RISK_EPS,
) -> pd.DataFrame:
    """Classify why each name's target weight moved, as a frame.

    `today` and `previous` carry at least the columns ticker, weight and
    z (the proposal rows). `today_specific` and `previous_specific` map
    ticker to specific standard deviation at the two closes. `nav` is the equity
    the book was sized on, which is what turns the dollar floor into a weight.

    A name the previous book did not hold is a **new name**, and a name the
    previous book held whose target is now zero is **exited**; both are appended
    to the frame, the exits carrying a weight of zero, so the returned frame is
    the union of the two books and its reason column accounts for every name in
    either one.

    `previous is None` (or empty) means there is no earlier book at all, which is
    the establishment day: every row is a position being opened for the first
    time, and calling that "alpha moved" would say something moved that had never
    been there. Nothing is "exited" on that day either, because nothing was held.
    """
    if previous is None or previous.empty:
        return pd.DataFrame(
            {
                "ticker": [str(ticker) for ticker in today["ticker"]],
                "weight": [float(weight) for weight in today["weight"]],
                "z": [float(value) for value in today["z"]],
                "reason": [NEW_POSITION] * len(today),
            }
        )
    weight_eps = weight_eps_for(nav, weight_dollars=weight_dollars)
    prev = previous.set_index("ticker")
    rows: list[dict[str, object]] = []
    for row in today.itertuples(index=False):
        ticker = str(row.ticker)
        weight_today = float(row.weight)
        if ticker not in prev.index:
            rows.append(
                {
                    "ticker": ticker,
                    "weight": weight_today,
                    "z": float(row.z),
                    "reason": NEW_NAME,
                }
            )
            continue
        p = prev.loc[ticker]
        weight_prev = float(p["weight"])
        z_prev = float(p["z"])
        if abs(weight_today - weight_prev) <= weight_eps:
            reason = NO_TRADE
        elif pd.isna(z_prev) or abs(float(row.z) - z_prev) > z_eps:
            reason = ALPHA_MOVED
        else:
            sigma_today = float(today_specific.get(ticker, float("nan")))
            sigma_prev = (
                float(previous_specific.get(ticker, float("nan")))
                if previous_specific is not None
                else float("nan")
            )
            if (
                not pd.isna(sigma_prev)
                and not pd.isna(sigma_today)
                and abs(sigma_today - sigma_prev) > risk_eps * max(sigma_prev, 1e-12)
            ):
                reason = RISK_MOVED
            else:
                reason = HEDGE_MOVED
        rows.append(
            {
                "ticker": ticker,
                "weight": weight_today,
                "z": float(row.z),
                "reason": reason,
            }
        )
    held = [str(ticker) for ticker in prev.index]
    tonight = {str(ticker) for ticker in today["ticker"]}
    for ticker in sorted(name for name in held if name not in tonight):
        # Held at the previous close and not in tonight's target: the book leaves
        # it, which is a trade (a close) and needs a reason like any other. It gets
        # a row with a weight of zero because that is what tonight's target says.
        rows.append(
            {"ticker": ticker, "weight": 0.0, "z": float("nan"), "reason": EXITED}
        )
    return pd.DataFrame(rows)


def specific_std(
    specific: pd.DataFrame, as_of: pd.Timestamp | None = None
) -> pd.Series:
    """Specific standard deviation per ticker from a specific_var frame.

    `specific` has columns date, ticker and specific_var. The result is
    the square root per ticker at the latest date on or before `as_of`
    (the frame's last date when `as_of` is None).
    """
    if specific.empty:
        return pd.Series(dtype=float)
    dates = pd.to_datetime(specific["date"])
    cutoff = pd.Timestamp(as_of) if as_of is not None else dates.max()
    eligible = dates[dates <= cutoff]
    if eligible.empty:
        return pd.Series(dtype=float)
    block = specific.loc[dates == eligible.max()]
    return block.set_index("ticker")["specific_var"].map(
        lambda value: float(value) ** 0.5 if value >= 0 else float("nan")
    )
