"""The hedge is built against the design for the session the book is held over.

The book written at the close of `t` earns the session after `t`, so the
exposures it has to shed are the ones that session carries: the design row the
model dates with the next session. That row's raw descriptors are computed from
data through `t`, because every descriptor on a row is a shifted quantity, so the
row is knowable at the close with one exception. `fx.standardize` z-scores each
row over the names priced on the row's own date, and that set is fixed by the next
session's own prices, which do not exist yet. So:

- on an ordinary session the priced set is unchanged, the built row IS the
  published row, and the hedge leaves nothing: measured on 2026-09-17 and
  2026-09-18 the design matrices agree to 7e-14 and the book's exposure under the
  published row is 1e-15 and 3e-14, against 5.5e-03 and 4.5e-03 for the row dated
  the close, which is what the negative control below asserts;
- on the session before a market holiday the set moves, because a longer gap is
  what lets names be added or dropped, and the built row cannot see it. Measured
  on 2026-09-04 to 2026-09-08 (Labor Day) one name that was not priced at the
  close is in the next cross-section, so its z is 0 here and a full z there,
  while every name priced on both dates moves by at most 3.7e-02 through the
  cross-sectional statistics. The book's exposure under the published row is
  1.8e-03, bounded here at 5e-03, against 4.1e-03 for the row dated the close.

The bound is per book and per pair; the run records the realized number for the
traded book in the proposal manifest (`previous_book_exposure_vs_published`),
which is the only place the real number exists, one session after the hedge.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from efb import eval_risk, race
from live import sizing

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# A published pair per case: two ordinary sessions and the one that spans Labor
# Day, which is the only pair in the published daily window whose priced set
# moves.
PAIRS = (
    ("2026-09-17", "2026-09-18"),
    ("2026-09-18", "2026-09-21"),
    ("2026-09-04", "2026-09-08"),
)
HOLIDAY_PAIR = ("2026-09-04", "2026-09-08")

# The bound the ordinary sessions have to meet, and the bound the session before
# a market holiday is held to instead. The second is measured, not chosen: it is
# the worst residual any of the books tried here leaves on that pair, and it
# cannot be tightened to the first because the priced set it depends on is not
# knowable at the close.
EXACT = 1e-10
HOLIDAY_BOUND = 5e-3

pytestmark = pytest.mark.timeout(300)


def _trimmed_root(cut: pd.Timestamp, base: Path) -> Path:
    """A data root whose panel stops at `cut`, with the artifacts shared.

    The live shape: no session after the close is in the panel, so the
    construction has to build the next session's row rather than find it. The
    descriptor artifact is symlinked in full, which is what leaves the published
    row available to compare the built row against.
    """
    dest = base / str(cut.date())
    (dest / "processed").mkdir(parents=True, exist_ok=True)
    (dest / "raw").mkdir(parents=True, exist_ok=True)
    returns = pd.read_parquet(DATA / "processed" / "returns.parquet")
    dates = pd.DatetimeIndex(sorted(returns.index.get_level_values("date").unique()))
    keep = set(dates[dates <= cut][-race.NEXT_DESIGN_WINDOW :])
    returns.loc[returns.index.get_level_values("date").isin(keep)].to_parquet(
        dest / "processed" / "returns.parquet"
    )
    prices = pd.read_parquet(DATA / "raw" / "prices.parquet")
    prices.loc[prices.index.get_level_values("date").isin(keep)].to_parquet(
        dest / "raw" / "prices.parquet"
    )
    shares = pd.read_parquet(DATA / "raw" / "shares_history.parquet")
    shares.loc[pd.to_datetime(shares["date"]) <= cut].to_parquet(
        dest / "raw" / "shares_history.parquet"
    )
    for rel in (
        "processed/sectors.parquet",
        "processed/universe_membership.parquet",
        "models/XS-v1/descriptors.parquet",
    ):
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        (dest / rel).symlink_to((DATA / rel).resolve())
    return dest


def _published_names(following: pd.Timestamp) -> list[str]:
    descriptors = pd.read_parquet(DATA / "models" / "XS-v1" / "descriptors.parquet")
    day = descriptors.loc[pd.to_datetime(descriptors["date"]) == following]
    return sorted(str(ticker) for ticker in day["ticker"].unique())


def _book(size_z: np.ndarray) -> np.ndarray:
    """A dollar-neutral book from the published row's own size z.

    The traded book is runtime state, so the test builds one from the row being
    tested instead: long the names with a positive size z, short the rest, the
    same weight each, made exactly dollar neutral. It carries real exposures
    (the row dated the close leaves 4e-03 through it) and it is reproducible.
    """
    side = np.where(size_z > 0, 1.0, 0.0) - 0.5
    weights = side / np.abs(side).sum()
    return weights - weights.mean()


def _residual(used: np.ndarray, published: np.ndarray, weights: np.ndarray) -> float:
    """The book's worst exposure under `published` after hedging on `used`."""
    hedged = weights + sizing.hedge_exact_robust(used, used.T @ weights)
    return float(np.abs(published.T @ hedged).max())


@pytest.fixture(scope="module")
def designs(tmp_path_factory: pytest.TempPathFactory) -> dict[tuple[str, str], dict]:
    """The three designs and the names they are read on, for every pair."""
    base = tmp_path_factory.mktemp("hedge_vintage")
    out: dict[tuple[str, str], dict] = {}
    for cut, following in PAIRS:
        cut_ts, following_ts = pd.Timestamp(cut), pd.Timestamp(following)
        names = _published_names(following_ts)
        trimmed = _trimmed_root(cut_ts, base)
        built = race.next_descriptor_design(cut_ts, names, trimmed)
        assert built is not None, f"the row for {following} could not be built at {cut}"
        matrix, label = built
        out[(cut, following)] = {
            "built": matrix,
            "label": label,
            "published": race._descriptor_design(following_ts, names, DATA),
            "stale": race._descriptor_design(cut_ts, names, DATA),
            "names": names,
        }
    return out


def test_the_row_built_at_the_close_is_the_row_the_model_publishes(designs) -> None:
    """An ordinary session's priced set does not move, so the row is exact."""
    for pair in PAIRS[:2]:
        case = designs[pair]
        gap = float(np.abs(case["built"] - case["published"]).max())
        assert str(case["label"]).startswith("built from data through"), (
            f"{pair[0]} -> {pair[1]}: the hedge used {case['label']!r}, so this is"
            " not the live close shape the bound is about"
        )
        assert gap < EXACT, (
            f"{pair[0]} -> {pair[1]}: the built row is {gap:.3e} from the published"
            " row, so the priced set moved on a session it should not have"
        )


def test_the_book_carries_no_exposure_under_the_published_row(designs) -> None:
    """The measure the owner asked for: exposure after the hedge, under the row
    the model publishes for the next session, on an ordinary pair."""
    for pair in PAIRS[:2]:
        case = designs[pair]
        size_z = case["published"][:, 1]
        weights = _book(size_z)
        residual = _residual(case["built"], case["published"], weights)
        assert residual < EXACT, (
            f"{pair[0]} -> {pair[1]}: the hedged book holds {residual:.3e} of"
            " exposure under the published row"
        )


def test_the_row_dated_the_close_fails_that_bound(designs) -> None:
    """The negative control: today's design must leave a real exposure.

    If this passed, the test above would be measuring nothing.
    """
    for pair, case in designs.items():
        size_z = case["published"][:, 1]
        weights = _book(size_z)
        stale = _residual(case["stale"], case["published"], weights)
        assert stale > EXACT, (
            f"{pair[0]} -> {pair[1]}: the row dated the close leaves {stale:.3e},"
            " which is the exposure the hedge is supposed to remove"
        )


def test_the_session_before_a_holiday_is_bounded_and_not_exact(designs) -> None:
    """The priced set moves over a holiday, and the built row cannot know it.

    One name that was not priced at the 2026-09-04 close is in the 2026-09-08
    cross-section, so its z is 0 in the built row and a full z in the published
    one, and every name priced on both dates moves slightly because the
    cross-sectional statistics are taken over the changed set. The proof that the
    case is real is the size of the moved rows: at least one carries a whole z
    (0.5 or more), which no shift in the statistics can produce.
    """
    case = designs[HOLIDAY_PAIR]
    difference = np.abs(case["built"] - case["published"])
    per_name = difference.max(axis=1)
    entering = int((per_name > 0.5).sum())
    band = per_name[(per_name > 0) & (per_name <= 0.5)]
    moved_but_priced = float(band.max()) if band.size else 0.0
    assert entering >= 1, "the holiday pair no longer exercises a moved priced set"
    assert moved_but_priced < 5e-2, (
        f"a name priced on both dates moved by {moved_but_priced:.3e}, more than"
        " the cross-sectional statistics can explain"
    )
    weights = _book(case["published"][:, 1])
    residual = _residual(case["built"], case["published"], weights)
    stale = _residual(case["stale"], case["published"], weights)
    assert residual <= HOLIDAY_BOUND, f"the holiday pair left {residual:.3e}"
    assert residual < stale, (
        f"the built row left {residual:.3e} against {stale:.3e} for the row dated"
        " the close, so the change makes this session worse"
    )


def test_a_published_next_session_row_is_used_as_it_stands() -> None:
    """With the panel reaching past the close, the model's own row is the one.

    That is the replay shape: the row dated the next session is in the artifact,
    so it is used rather than rebuilt, and the label says so.
    """
    names = _published_names(pd.Timestamp("2026-09-18"))
    built = race.next_descriptor_design(pd.Timestamp("2026-09-17"), names, DATA)
    assert built is not None
    matrix, label = built
    assert label.startswith("published 2026-09-18")
    expected = race._descriptor_design(pd.Timestamp("2026-09-18"), names, DATA)
    assert np.array_equal(matrix, expected)


def test_the_hedge_is_handed_the_next_sessions_row() -> None:
    """The call site: `_xs_pieces` is what the live run hedges with."""
    names = _published_names(pd.Timestamp("2026-09-18"))
    pieces = eval_risk._xs_pieces(pd.Timestamp("2026-09-17"), names, DATA)
    assert pieces is not None
    assert str(pieces["design_vintage"]).startswith("published 2026-09-18")
    expected = race._descriptor_design(pd.Timestamp("2026-09-18"), names, DATA)
    assert np.array_equal(pieces["design"], expected)


def test_the_builder_declines_rather_than_hedging_on_a_short_window(tmp_path) -> None:
    """A close with too little history behind it keeps the row dated the close.

    The build needs four hundred sessions behind it, because the longest
    descriptor chain (the beta window and then the residual-volatility window)
    reaches back that far. Below it the cross-section would be standardized over
    names whose descriptors are still NaN, so the row dated the close is returned
    and the label says why rather than hedging on a partial cross-section.
    """
    early = pd.Timestamp("2011-06-01")
    root = _trimmed_root(early, tmp_path)
    names = ["AAPL", "MSFT"]
    matrix, label = race.next_descriptor_design(early, names, root)
    stale = race.descriptor_stamp(early, root)
    assert stale is not None
    assert label.startswith(f"stale {stale.date()}")
    assert "fewer than" in label
    assert np.array_equal(matrix, race._descriptor_design(early, names, root))


def test_a_sparse_replay_keeps_the_row_dated_the_close() -> None:
    """A tree that publishes month ends cannot supply the next session's row.

    The panel reaches past the close but the model has published nothing for the
    next session, so there is nothing to hedge against and the row dated the close
    is used, which is what this path used before the change. The seed tree is the
    example: its rows are month ends except for the recent daily tail.
    """
    date = pd.Timestamp("2026-09-01")
    names = ["AAPL", "MSFT"]
    matrix, label = race.next_descriptor_design(date, names, DATA)
    stale = race.descriptor_stamp(date, DATA)
    assert stale is not None
    assert label.startswith(f"stale {stale.date()}")
    assert "published no row for" in label
    assert np.array_equal(matrix, race._descriptor_design(date, names, DATA))
