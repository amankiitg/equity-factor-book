"""Sprint E12: the attribution's arithmetic, and the pipeline on the seed's books.

Two levels, deliberately. The arithmetic is checked against numbers computed by
hand on a fixture small enough to do it on paper, because an identity that holds by
construction proves nothing about the arithmetic. The pipeline is then run over the
historical books the seed carries, which is where a real design, real factor returns
and real per-name returns meet: the identity has to survive all three at once.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from efb import attribution

ROOT = Path(__file__).resolve().parents[1]
# The one historical book the project's own artifacts decomposed, at one (rho, seed)
# combination, so the test runs on the same object the deliverable reports on.
SEED_BOOK = ROOT / "data" / "portfolios" / "mv_constrained.parquet"


class _FixturePanel:
    """A panel whose three pieces are given, so the arithmetic can be checked."""

    def __init__(
        self,
        returns: pd.DataFrame,
        factor_returns: pd.DataFrame,
        design: np.ndarray,
        betas: np.ndarray,
    ) -> None:
        self._returns = returns
        self.factor_returns = factor_returns
        self._design = design
        self._betas = betas
        # long, indexed by (date, ticker), the shape the panel artifact has
        self.returns = returns.stack(future_stack=True)

    def design(self, date: pd.Timestamp, names: list[str]) -> np.ndarray:
        return self._design

    def factor_names(self, date: pd.Timestamp) -> list[str]:
        return list(self.factor_returns.columns)

    def betas_at(self, date: pd.Timestamp, names: list[str]) -> np.ndarray:
        return self._betas


def test_the_components_are_the_arithmetic_not_just_an_identity() -> None:
    """Two names, one factor, numbers a reader can check on paper.

    w = (0.6, -0.4) gross 1.0, r = (0.02, -0.01), design X = (1.0, -0.5),
    f = 0.01. Factor exposure = 0.6*1.0 + (-0.4)*(-0.5) = 0.8, so the factor P&L
    is 0.8 * 0.01 = 0.008 and the gross is 0.6*0.02 + (-0.4)*(-0.01) = 0.016. The
    specific part is the rest: 0.008. A cost of -0.001 makes the total 0.015.
    """
    date = pd.Timestamp("2026-09-21")
    holdings = pd.DataFrame(
        {"date": [date, date], "ticker": ["AAA", "BBB"], "weight": [0.6, -0.4]}
    )
    panel = _FixturePanel(
        returns=pd.DataFrame({"AAA": [0.02], "BBB": [-0.01]}, index=[date]),
        factor_returns=pd.DataFrame({"market": [0.01]}, index=[date]),
        design=np.array([[1.0], [-0.5]]),
        betas=np.array([1.2, 0.4]),
    )

    frame = attribution.attribute_book(
        holdings, panel, costs={date: {"cost_usd": -0.001}}
    )
    row = frame.iloc[0]

    assert row["gross"] == pytest.approx(1.0)
    assert row["net"] == pytest.approx(0.2)
    assert row["pnl_factor"] == pytest.approx(0.008)
    assert row["pnl_idio"] == pytest.approx(0.008)
    assert row["pnl_cost"] == pytest.approx(-0.001)
    assert row["pnl_total"] == pytest.approx(0.015)
    assert row["pnl_factor_json"] == {"market": pytest.approx(0.008)}
    # The beta line is explanatory, not a fourth component: 0.6*1.2 + (-0.4)*0.4 =
    # 0.56 of market beta, times a 1% market, is 0.0056 of the specific P&L.
    assert row["book_beta"] == pytest.approx(0.56)
    assert row["pnl_beta"] == pytest.approx(0.0056)
    assert row["pnl_beta"] != pytest.approx(row["pnl_idio"])
    # And the residual is zero: the three components are the total, not near it.
    assert row["identity_residual"] == 0.0


def test_the_identity_holds_on_a_book_of_weights_that_cancel() -> None:
    """A dollar-neutral book, where a sign error cannot hide in a large gross."""
    date = pd.Timestamp("2026-09-22")
    holdings = pd.DataFrame(
        {
            "date": [date] * 4,
            "ticker": ["AAA", "BBB", "CCC", "DDD"],
            "weight": [0.5, -0.5, 0.25, -0.25],
        }
    )
    panel = _FixturePanel(
        returns=pd.DataFrame(
            {"AAA": [0.01], "BBB": [-0.008], "CCC": [0.004], "DDD": [-0.006]},
            index=[date],
        ),
        factor_returns=pd.DataFrame(
            {"market": [0.002], "size": [-0.003]}, index=[date]
        ),
        design=np.array([[1.0, 0.5], [-1.0, -0.5], [0.5, -1.0], [-0.5, 1.0]]),
        betas=np.array([1.0, 1.0, 0.9, 0.9]),
    )

    row = attribution.attribute_book(holdings, panel).iloc[0]

    assert row["identity_residual"] == 0.0
    assert row["pnl_total"] == pytest.approx(
        row["pnl_factor"] + row["pnl_idio"] + row["pnl_cost"]
    )


def test_daily_weights_use_the_book_dated_before_the_session() -> None:
    """The project's own convention, so the attribution cannot look ahead."""
    books = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2026-09-18", "2026-09-18", "2026-09-21", "2026-09-21"]
            ),
            "ticker": ["AAA", "BBB", "AAA", "CCC"],
            "weight": [0.5, -0.5, 0.3, -0.3],
        }
    )
    sessions = pd.Series(
        pd.to_datetime(["2026-09-17", "2026-09-18", "2026-09-21", "2026-09-22"])
    )

    held = attribution.daily_weights(books, sessions)

    # 09-17 and 09-18 have no book strictly before them, so they are dropped.
    assert sorted(held["date"].unique()) == [
        pd.Timestamp("2026-09-21"),
        pd.Timestamp("2026-09-22"),
    ]
    on_21 = held.loc[held["date"] == "2026-09-21"].set_index("ticker")["weight"]
    on_22 = held.loc[held["date"] == "2026-09-22"].set_index("ticker")["weight"]
    assert on_21.to_dict() == {"AAA": 0.5, "BBB": -0.5}, "the 09-18 book earns the 21st"
    assert on_22.to_dict() == {"AAA": 0.3, "CCC": -0.3}, "and the 09-21 book the 22nd"


def test_the_pipeline_attributes_the_seed_book_every_session() -> None:
    """The historical book the seed carries, through the real design and returns.

    This is the pipeline test the sprint asks for: books that predate the live loop,
    the model's own artifacts, one row per session, and the identity holding on
    every one of them.
    """
    books = pd.read_parquet(SEED_BOOK)
    books = books.loc[(books["rho"] == 0.02) & (books["seed"] == 0)].copy()
    books = books.loc[books["date"] >= "2019-01-01", ["date", "ticker", "weight"]]
    # gross ~15 at this rho, so the book is renormalized to 1.0: the identity holds
    # at any scale, and unit gross is what the live book is.
    books["weight"] = books["weight"] / books.groupby("date")["weight"].transform(
        lambda column: column.abs().sum()
    )
    panel = attribution.ModelPanel(ROOT / "data")
    sessions = panel.sessions[
        (panel.sessions > books["date"].min()) & (panel.sessions <= books["date"].max())
    ]
    assert len(sessions) > 100, "the window is meant to be years of sessions"

    holdings = attribution.daily_weights(books, pd.Series(sessions))
    frame = attribution.attribute_book(holdings, panel)

    assert len(frame) == holdings["date"].nunique() > 100
    assert frame["trade_date"].is_monotonic_increasing
    assert (frame["n_names"] > 100).all(), "a book of this size is not a toy book"
    assert frame["gross"].sub(1.0).abs().max() < 1e-9
    # The identity, on every session, at the tolerance the sprint set.
    assert frame["identity_residual"].abs().max() < attribution.IDENTITY_ATOL
    # The factor split is per factor, and the parts sum to the factor total.
    split = frame["pnl_factor_json"].apply(lambda mapping: float(sum(mapping.values())))
    assert np.allclose(split, frame["pnl_factor"], atol=1e-12)
    assert len(frame["pnl_factor_json"].iloc[0]) >= 10, "the design's columns are there"
    # The beta line is populated from the stored CAPM betas, and the market return
    # beside it, so the two can be read together.
    assert frame["book_beta"].notna().all()
    assert frame["pnl_beta"].notna().all()
    # A name whose return is missing that session contributes zero rather than a
    # fabricated number, so what matters is how much of the book that was: it is a
    # handful of sessions out of 1,884, never more than one name, and under a
    # basis point of gross. The count is reported per row so a growing hole is
    # visible rather than absorbed.
    assert frame["n_missing_return"].max() <= 1
    assert frame["missing_return_weight"].max() < 1e-3
    assert (frame["n_missing_return"] > 0).sum() <= 5
