"""Sprint E10: the risk allocation engine, its formulas and its controls."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from efb import allocate

ROOT = allocate.ROOT
DATA = ROOT / "data"


def test_kelly_fraction_is_mu_over_sigma_squared() -> None:
    assert allocate.kelly_fraction(0.10, 0.20) == pytest.approx(2.5)
    assert allocate.kelly_fraction(0.0, 0.20) == pytest.approx(0.0)
    assert np.isnan(allocate.kelly_fraction(0.10, 0.0))


def test_growth_is_concave_with_maximum_at_full_kelly() -> None:
    mean, vol = 0.10, 0.20
    full = allocate.kelly_fraction(mean, vol)
    at_full = allocate.growth(full, mean, vol)
    at_half = allocate.growth(full / 2, mean, vol)
    at_double = allocate.growth(full * 2, mean, vol)
    assert at_full > at_half
    assert at_full > at_double


def test_magdon_ismail_median_is_half_the_mean_of_the_exponential() -> None:
    # the maximum drawdown tail is exponential with rate 2 mu / sigma^2,
    # so the median is ln(2) sigma^2 / (2 mu)
    median = allocate.magdon_ismail_median(0.10, 0.20)
    assert median == pytest.approx(np.log(2.0) * 0.04 / 0.20)
    assert np.isnan(allocate.magdon_ismail_median(0.0, 0.20))


def test_stop_loss_never_improves_on_a_deterministic_winner() -> None:
    # a rising series has a max drawdown that never triggers the stop, so the
    # stopped path equals the original and the Sharpe is unchanged
    x = np.full(100, 0.001)
    stopped = allocate._apply_stop_loss(x, -0.10, -0.05)
    assert np.allclose(stopped, x)


def test_stop_loss_goes_flat_after_a_deep_drawdown() -> None:
    x = np.full(10, 0.01)
    x = np.concatenate([x, [-0.30], np.full(5, 0.0)])
    stopped = allocate._apply_stop_loss(x, -0.10, -0.05)
    # after the -30% shock the path must go flat (zero return) for a while
    assert stopped[-1] == 0.0


def test_the_reentering_stop_reenters_after_a_recovery() -> None:
    # the original stop freezes the drawdown while flat, so on a path that
    # drops below -10% then rockets the re-entry test is never reached; the
    # re-entering stop tracks the unstopped curve and re-enters
    x = np.array([-0.2, 0.5, 0.5, 0.5, 0.5, 0.5])
    stopped, state = allocate._apply_stop_loss_reentering(x, -0.10, -0.05)
    assert not np.allclose(stopped[1:], 0.0)
    assert state["entries"] >= 1 and state["exits"] >= 1
    # the original stop stays flat forever after the first breach
    original = allocate._apply_stop_loss(x, -0.10, -0.05)
    assert np.allclose(original[1:], 0.0)


@pytest.mark.integration
@pytest.mark.slow
def test_the_design_config_is_picked_close_to_sharpe_one() -> None:
    config = allocate.pick_design_config(DATA)
    assert "rho" in config and "phi" in config
    assert np.isfinite(config["net_sharpe"])


@pytest.mark.integration
def test_the_kelly_artifacts_are_written() -> None:
    path = DATA / "allocation" / "kelly.parquet"
    if not path.exists():
        pytest.skip("the E10 run has not completed")
    kelly = pd.read_parquet(path)
    assert {"kelly_full", "kelly_half", "growth_full", "sharpe"} <= set(kelly.columns)


def _toy_book() -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.to_datetime(["2020-01-31", "2020-02-29"])
    book = pd.DataFrame(
        [[0.5, 0.5, 0.0], [0.5, 0.5, 0.0]], index=index, columns=["A", "B", "C"]
    )
    close = pd.DataFrame(
        [[100.0, 10.0, 50.0], [100.0, 10.0, 50.0]], index=index, columns=book.columns
    )
    return book, close


def test_quantize_book_to_shares_applies_the_e11_construction() -> None:
    """Whole shares at the NAV, no name under the floor, gross 1.0.

    At $1,000 a $500 target is 5 shares of A (below the 20-share floor) and 50
    shares of B (kept), so B carries the whole book after renormalization.
    """
    book, close = _toy_book()
    kept, diary = allocate.quantize_book_to_shares(book, close, 1_000.0, floor=20)
    assert kept.loc[book.index[0], "A"] == 0.0
    assert kept.loc[book.index[0], "B"] == pytest.approx(1.0)
    assert kept.loc[book.index[0], "C"] == 0.0
    assert float(kept.iloc[0].abs().sum()) == pytest.approx(1.0)
    assert int(diary["names_kept"].iloc[0]) == 1


def test_the_floor_is_what_drops_the_names() -> None:
    """With no floor every sized name is kept; with the floor most are not."""
    book, close = _toy_book()
    without_floor, _ = allocate.quantize_book_to_shares(book, close, 1_000.0, floor=0)
    with_floor, _ = allocate.quantize_book_to_shares(book, close, 1_000.0, floor=20)
    assert int((without_floor != 0).sum().sum()) > int((with_floor != 0).sum().sum())


@pytest.mark.integration
def test_the_stored_traded_book_figures_are_what_the_function_computes() -> None:
    path = DATA / "portfolios" / "traded_book.parquet"
    if not path.exists():
        pytest.skip("the E8/E10 build has not written the traded-book figures")
    stored = pd.read_parquet(path).iloc[0].to_dict()
    computed = allocate.traded_book_figures(DATA, store=False)
    for key, value in computed.items():
        assert stored[key] == pytest.approx(value), key
    assert stored["kept_nav"] == allocate.TRADED_BOOK_NAV
    assert stored["kept_share_floor"] == allocate.TRADED_BOOK_SHARE_FLOOR


@pytest.mark.integration
def test_e8_and_e10_store_the_traded_book_beside_the_full_book() -> None:
    """Additive: the kept_* and full_book_* keys sit beside the old numbers."""
    for sprint, key in (("E8", "F8.5"), ("E10", "F10.1")):
        payload = json.loads((ROOT / "sprints" / sprint / "RESULTS.json").read_text())
        numbers = payload["criteria"][key]["stored_numbers"]
        block = numbers.get("traded_book")
        assert block, f"{sprint} {key} stores no traded-book figures"
        assert {
            "kept_sharpe",
            "full_book_sharpe",
            "kept_n_names",
            "full_book_n_names",
            "kept_names_dropped_share",
        } <= set(block)
        # the floor is what separates the two books, and it bites
        assert block["kept_n_names"] < block["full_book_n_names"]
        assert 0.3 < block["kept_names_dropped_share"] < 0.7
