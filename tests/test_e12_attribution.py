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
from efb.models import fundamental as fx

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

    def raw_design(self, date: pd.Timestamp, names: list[str]) -> np.ndarray:
        return self._design

    def reported_design(self, date: pd.Timestamp, names: list[str]) -> np.ndarray:
        """The fixture's design is already the exposures its factors belong to."""
        return self._design

    def fit_or_stored(self, date, names, returns, raw):
        """The fixture's own split: the specific return is what r - X f is not."""
        factor_returns = self.factor_returns.loc[date]
        fitted = self._design @ factor_returns.to_numpy(dtype=float)
        specific = self._returns.loc[date].to_numpy(dtype=float) - fitted
        return factor_returns, specific, "fixture"

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


class _VintagePanel:
    """A panel whose design at the session is not the design at the book's close.

    The hedge zeroed the exposure of the design dated the close the book was built
    on; the model prices the session with the design dated the session. Measuring
    the gap needs a panel where the two differ, which the fixture panel cannot do
    because it returns one design for every date.
    """

    def __init__(
        self,
        returns: pd.DataFrame,
        factor_returns: pd.DataFrame,
        session_design: np.ndarray,
        book_design: np.ndarray,
        book_close: pd.Timestamp,
        betas: np.ndarray,
    ) -> None:
        self._returns = returns
        self.factor_returns = factor_returns
        self._session_design = session_design
        self._book_design = book_design
        self.book_close = pd.Timestamp(book_close)
        self._betas = betas
        self.returns = returns.stack(future_stack=True)

    def design(self, date: pd.Timestamp, names: list[str]) -> np.ndarray:
        return self._session_design

    def factor_names(self, date: pd.Timestamp) -> list[str]:
        return list(self.factor_returns.columns)

    def raw_design(self, date: pd.Timestamp, names: list[str]) -> np.ndarray:
        return self._session_design

    def reported_design(self, date: pd.Timestamp, names: list[str]) -> np.ndarray:
        """The book's own close gets the book's design, the session gets its own."""
        if pd.Timestamp(date) <= self.book_close:
            return self._book_design
        return self._session_design

    def fit_or_stored(self, date, names, returns, raw):
        factor_returns = self.factor_returns.loc[date]
        fitted = self._session_design @ factor_returns.to_numpy(dtype=float)
        specific = self._returns.loc[date, names].to_numpy(dtype=float) - fitted
        return factor_returns, specific, "fixture"

    def betas_at(self, date: pd.Timestamp, names: list[str]) -> np.ndarray:
        return self._betas


def test_the_hedge_timing_gap_is_measured_against_the_book_s_own_close() -> None:
    """The two design vintages, and the P&L between them, on numbers by hand.

    The book was built at the 09-18 close, where one name at weight 1.0 had a
    design exposure of 1.5, and the hedge zeroed that 1.5. The session is 09-21,
    where the same name's design exposure is 2.0 and the factor returns 1%. So the
    session's factor P&L is 2.0 * 0.01 = 0.02, the hedge's own vintage implies
    1.5 * 0.01 = 0.015, and the 0.5 of exposure drift is 0.005 of factor P&L that
    the hedge did not zero. The book must carry its own close, not the session, so
    the exposure dated the session can be read beside the one the hedge acted on.
    """
    book_close = pd.Timestamp("2026-09-18")
    session = pd.Timestamp("2026-09-21")
    books = pd.DataFrame({"date": [book_close], "ticker": ["AAA"], "weight": [1.0]})
    panel = _VintagePanel(
        returns=pd.DataFrame({"AAA": [0.03]}, index=[session]),
        factor_returns=pd.DataFrame({"market": [0.01]}, index=[session]),
        session_design=np.array([[2.0]]),
        book_design=np.array([[1.5]]),
        book_close=book_close,
        betas=np.array([1.1]),
    )

    held = attribution.daily_weights(books, pd.Series([session]))
    assert held["book_date"].iloc[0] == book_close

    row = attribution.attribute_book(held, panel).iloc[0]
    assert row["pnl_factor"] == pytest.approx(0.02)
    assert row["exposure_json"] == {"market": pytest.approx(2.0)}
    assert row["book_exposure_json"] == {"market": pytest.approx(1.5)}
    assert row["pnl_timing"] == pytest.approx(0.005)
    assert row["pnl_timing_json"] == {"market": pytest.approx(0.005)}
    # The timing line is a gap, not a fifth component: the identity still closes on
    # total = factor + idio + cost, with the timing already inside the factor part.
    assert row["identity_residual"] == 0.0


def test_the_pipeline_attributes_the_seed_book_every_session() -> None:
    """The historical book the seed carries, through the real design and returns.

    This is the pipeline test the sprint asks for: books that predate the live loop,
    the model's own artifacts, one row per session, and the identity holding on
    every one of them.
    """
    books = pd.read_parquet(SEED_BOOK)
    books = books.loc[(books["rho"] == 0.02) & (books["seed"] == 0)].copy()
    # One year of the seed's own book: every session of 2019 through the real
    # design, the real factor returns and the real specific returns. A year is
    # enough for the pipeline and stays inside the per-test timeout the suite runs
    # under, which the run over all 1,884 sessions of the book did not.
    books = books.loc[
        (books["date"] >= "2019-01-01") & (books["date"] <= "2019-12-31"),
        ["date", "ticker", "weight"],
    ]
    # gross ~15 at this rho, so the book is renormalized to 1.0: the identity holds
    # at any scale, and unit gross is what the live book is.
    books["weight"] = books["weight"] / books.groupby("date")["weight"].transform(
        lambda column: column.abs().sum()
    )
    panel = attribution.ModelPanel(ROOT / "data")
    sessions = panel.sessions[
        (panel.sessions > books["date"].min()) & (panel.sessions <= books["date"].max())
    ]
    assert len(sessions) > 200, "the window is a year of sessions"

    holdings = attribution.daily_weights(books, pd.Series(sessions))
    frame = attribution.attribute_book(holdings, panel)

    assert len(frame) == holdings["date"].nunique() > 200
    assert frame["trade_date"].is_monotonic_increasing
    assert (frame["n_names"] > 100).all(), "a book of this size is not a toy book"
    # The stored split is what the split uses: nothing had to be recomputed.
    assert (
        frame["n_computed_specific"] == 0
    ).all(), "the book should sit inside the model's own cross-section"
    assert frame["gross"].sub(1.0).abs().max() < 1e-9
    # The identity, and what it is worth: the stored split reconstructs the panel's
    # own total return exactly on the sessions the current build produced (checked
    # to 6.9e-18 on three 2026 dates below), and misses by a measured 1.9e-3 at its
    # worst and ~2e-4 in median on the 2019 sessions of this book, whose artifacts
    # were written by an earlier build. So this asserts the bound the old vintage
    # actually holds to, and the 2026 closure is asserted on its own: one 1e-10
    # would fail on the old data and hide which of the two things was true.
    assert frame["identity_residual"].abs().max() < 5e-3
    assert frame["identity_residual"].abs().median() < 5e-4
    # The factor split is per factor, and the parts sum to the factor total.
    split = frame["pnl_factor_json"].apply(lambda mapping: float(sum(mapping.values())))
    assert np.allclose(split, frame["pnl_factor"], atol=1e-12)
    assert len(frame["pnl_factor_json"].iloc[0]) >= 10, "the design's columns are there"
    # The beta line is populated from the stored CAPM betas, and the market return
    # beside it, so the two can be read together.
    assert frame["book_beta"].notna().all()
    assert frame["pnl_beta"].notna().all()
    # A name whose return is missing that session contributes zero rather than a
    # fabricated number, so what matters is how much of the book that was. The count
    # is reported per row so a growing hole is visible rather than absorbed, and the
    # subset here is small enough that the claim is about the pipeline rather than
    # about a rare name.
    assert frame["n_missing_return"].max() <= 2
    assert frame["missing_return_weight"].max() < 1e-2


def test_the_stored_split_reconstructs_the_return_on_the_current_build() -> None:
    """The check the sprint's identity rests on, on the sessions this build produced.

    X is the design the model's fit used - `race._descriptor_design` at the session,
    in the 18 reported columns - f the stored factor returns at the session and u
    the stored specific returns, against the panel's total return, which is the
    column XS-v1 regresses. Two wrong pairings are measured here too, so the
    conclusion cannot be read as luck: the design dated the previous close misses
    the return by ~1e-3 in median, and the 17-column design leaves a few names out
    by ~2e-2.

    The dates are the live vintage's, because that is what "the current build"
    means: 2026-09-30 and 2026-10-02 are sessions `live/extend.py` fitted with this
    code and these artifacts, and they close to 1e-17. The seed's September sessions
    were fitted by an older vintage and no longer reproduce their own panel -
    2026-09-18 misses by 3.0e-2 in the worst name, 5.4e-3 in the median - which is
    the disagreement the page carries as `pnl_unexplained` rather than folding into
    the three components.
    """
    panel = attribution.ModelPanel(ROOT / "data")
    dates = [pd.Timestamp(day) for day in ("2026-09-30", "2026-10-02")]
    for date in dates:
        previous = panel.sessions[panel.sessions < date][-1]
        day = panel.stored_specific[date]
        names = [str(ticker) for ticker in day.index]
        u = day.to_numpy(dtype=float)
        r = panel.returns.loc[date].reindex(names).to_numpy(dtype=float)
        ok = np.isfinite(r)
        f = panel.factor_returns.loc[date].reindex(panel.factor_names(date))

        current = panel.reported_design(date, names)[ok] @ f.to_numpy(dtype=float)
        lagged = attribution.reported_design(panel.raw_design(previous, names))[
            ok
        ] @ f.to_numpy(dtype=float)
        estimated = [name for name in f.index if name in fx.ESTIMATED_NAMES]
        unreported = panel.raw_design(date, names)[ok] @ f.reindex(estimated).to_numpy(
            dtype=float
        )

        assert np.nanmax(np.abs(current + u[ok] - r[ok])) < attribution.IDENTITY_ATOL
        assert np.nanmedian(np.abs(lagged + u[ok] - r[ok])) > 1e-4, "the lag misses"
        assert np.nanmax(np.abs(unreported + u[ok] - r[ok])) > 1e-3, "17 columns miss"

    # The seed's September vintage, measured rather than asserted: it is the reason
    # the section draws `pnl_unexplained` as its own term instead of folding a
    # disagreement into the components beside it.
    old = pd.Timestamp("2026-09-18")
    day = panel.stored_specific[old]
    names = [str(ticker) for ticker in day.index]
    u = day.to_numpy(dtype=float)
    r = panel.returns.loc[old].reindex(names).to_numpy(dtype=float)
    ok = np.isfinite(r)
    f = panel.factor_returns.loc[old].reindex(panel.factor_names(old))
    rebuilt = panel.reported_design(old, names)[ok] @ np.nan_to_num(
        f.to_numpy(dtype=float), nan=0.0
    )
    miss = np.abs(rebuilt + u[ok] - r[ok])
    assert np.nanmedian(miss) > 1e-3, "the older vintage now reproduces its panel"
    assert np.nanmax(miss) < 1e-1, "the disagreement grew past what the sprint measured"
