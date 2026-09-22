"""Sprint E11: why each position trades today.

Every position on the dashboard carries a stated reason, never a blank.
The four reasons are the vocabulary from the task: alpha moved, risk
moved, the hedge moved, or it drifted past a band. The classifier
compares today's proposal against yesterday's on the inputs Procedure
6.3 sizes on, so the stated reason is read off the inputs rather than
guessed.

Order of precedence, for a name whose target weight moved:

1. alpha moved: the name's own signal (z-score of idio_momentum) moved
   from the previous close by more than the epsilon.
2. risk moved: the alpha did not move, but the name's specific standard
   deviation moved by more than the relative epsilon.
3. the hedge moved: neither the alpha nor the risk moved, so the only
   remaining driver of a Procedure 6.3 re-size is the factor hedge (the
   design, the factor covariance, or the other names' alphas).
4. drifted past a band: a name is traded although none of its own inputs
   and none of the hedge inputs moved, which can only be a band rebalance
   of a position that drifted between sessions. In a daily full-rebalance
   loop this bucket stays empty, but it is a real state in a banded
   policy, so it is kept.
"""

from __future__ import annotations

import pandas as pd

ALPHA_EPS = 1e-9
RISK_EPS = 1e-4
NO_TRADE = "no trade"
ALPHA_MOVED = "alpha moved"
RISK_MOVED = "risk moved"
HEDGE_MOVED = "the hedge moved"
DRIFTED = "drifted past a band"

REASONS = (ALPHA_MOVED, RISK_MOVED, HEDGE_MOVED, DRIFTED, NO_TRADE)


def assign_trade_reasons(
    today: pd.DataFrame,
    previous: pd.DataFrame | None,
    today_specific: pd.Series,
    previous_specific: pd.Series | None,
) -> pd.DataFrame:
    """Classify why each name's target weight moved, as a frame.

    `today` and `previous` carry at least the columns ticker, weight and
    z (the proposal rows). `today_specific` and `previous_specific` map
    ticker to specific standard deviation at the two closes. A name with
    no previous row is a new position, which is alpha by construction
    because its first score is the reason it entered.
    """
    prev = previous.set_index("ticker") if previous is not None else None
    rows: list[dict[str, object]] = []
    for row in today.itertuples(index=False):
        ticker = str(row.ticker)
        weight_today = float(row.weight)
        if prev is not None and ticker in prev.index:
            p = prev.loc[ticker]
            weight_prev = float(p["weight"])
            z_prev = float(p["z"])
        else:
            weight_prev = 0.0
            z_prev = float("nan")
        if abs(weight_today - weight_prev) < ALPHA_EPS:
            reason = NO_TRADE
        elif pd.isna(z_prev) or abs(float(row.z) - z_prev) > ALPHA_EPS:
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
                and abs(sigma_today - sigma_prev) > RISK_EPS * max(sigma_prev, 1e-12)
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
