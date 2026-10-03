"""The panel pin: a rebuild cannot extend the panel by re-reading sources.

Every `make rebuild-eN` takes an end date. Left off it is the stored panel's own
last session, not today, so re-running a rebuild after a source refresh reproduces
the panel the stored records were measured on. These tests drive the real E1 leg
offline and check the two directions that matter: a pin excludes newer source rows
that are genuinely there, and the default pin is the stored panel's end rather than
the clock.
"""

import pandas as pd
import pytest

from efb import build


def _fixtures(monkeypatch: pytest.MonkeyPatch, periods: int = 10) -> pd.DataFrame:
    """Synthetic universe, factors and price cache, as the offline rebuild uses.

    The price cache carries `periods` sessions, so a pin inside that range has
    newer source rows to ignore. That is the whole point: a fixture that stops at
    the pin could not tell a pinned read from an empty one.
    """
    changes = pd.DataFrame(
        {
            "effective_date": pd.to_datetime(["2015-01-02"]),
            "added_ticker": ["C"],
            "removed_ticker": ["A"],
            "reason": ["merger"],
        }
    )
    constituents = pd.DataFrame(
        {
            "symbol": ["B", "C"],
            "security": ["Bee", "Cee"],
            "gics_sector": ["Financials", "Tech"],
            "gics_sub_industry": ["Banks", "Software"],
            "date_added": pd.to_datetime(["2000-01-03", "2015-01-02"]),
        }
    )
    monkeypatch.setattr(build.universe, "fetch_constituents", lambda: constituents)
    monkeypatch.setattr(build.universe, "fetch_changes", lambda: changes)
    days = pd.bdate_range("2015-01-01", periods=periods)
    monkeypatch.setattr(
        build.factors,
        "load_french_factors",
        lambda: {
            "ff5": pd.DataFrame(
                {
                    "mkt_rf": [0.001] * len(days),
                    "smb": [0.0] * len(days),
                    "hml": [0.0] * len(days),
                    "rmw": [0.0] * len(days),
                    "cma": [0.0] * len(days),
                    "rf": [0.0001] * len(days),
                },
                index=days.rename("date"),
            ),
            "mom": pd.DataFrame({"mom": [0.0] * len(days)}, index=days.rename("date")),
            "strev": pd.DataFrame(
                {"st_rev": [0.0] * len(days)}, index=days.rename("date")
            ),
            "ind12": pd.DataFrame(
                {f"ind{i}": [0.0] * len(days) for i in range(1, 13)},
                index=days.rename("date"),
            ),
        },
    )
    close = [1.0 + 0.01 * step for step in range(len(days))]
    return pd.DataFrame(
        {
            "open": close * 3,
            "high": close * 3,
            "low": close * 3,
            "close": close * 3,
            "adj_close": close * 3,
            "volume": 100,
            "dividend": 0.0,
            "split_factor": 0.0,
        },
        index=pd.MultiIndex.from_product(
            [days, ["A", "B", "C"]], names=["date", "ticker"]
        ),
    )


def _panel_end(data_root) -> pd.Timestamp:
    frame = pd.read_parquet(data_root / "processed" / "returns.parquet")
    return pd.Timestamp(frame.index.get_level_values("date").max())


def _membership_end(data_root) -> pd.Timestamp:
    frame = pd.read_parquet(data_root / "processed" / "universe_membership.parquet")
    return pd.Timestamp(frame.index.max())


def test_a_pinned_end_ignores_newer_source_rows(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = _fixtures(monkeypatch, periods=10)
    root = tmp_path / "data"
    (root / "raw").mkdir(parents=True)
    cache.to_parquet(root / "raw" / "yf_cache.parquet")
    pin = pd.Timestamp("2015-01-08")

    build.rebuild(data_root=root, start="2015-01-01", end=str(pin.date()))

    # the pinned panel stops at the pin, in the prices artifact, the returns
    # artifact and the membership grid alike
    prices = pd.read_parquet(root / "raw" / "prices.parquet")
    assert pd.Timestamp(prices.index.get_level_values("date").max()) == pin
    assert _panel_end(root) == pin
    assert _membership_end(root) == pin


def test_the_same_sources_unpinned_do_reach_the_newer_rows(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control for the test above: the newer rows are really in the fixture."""
    cache = _fixtures(monkeypatch, periods=10)
    root = tmp_path / "data"
    (root / "raw").mkdir(parents=True)
    cache.to_parquet(root / "raw" / "yf_cache.parquet")
    later = pd.Timestamp("2015-01-14")

    build.rebuild(data_root=root, start="2015-01-01", end=str(later.date()))

    assert _panel_end(root) == later


def test_the_default_pin_is_the_stored_panel_not_today(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = _fixtures(monkeypatch, periods=10)
    root = tmp_path / "data"
    (root / "raw").mkdir(parents=True)
    cache.to_parquet(root / "raw" / "yf_cache.parquet")
    pin = pd.Timestamp("2015-01-08")

    build.rebuild(data_root=root, start="2015-01-01", end=str(pin.date()))
    assert build.stored_panel_end(root) == pin
    assert build.pinned_panel_end(None, root) == str(pin.date())

    # a source refresh lands in the cache, as a live run's would, and the next
    # rebuild without a pin still reproduces the panel the record names
    _fixtures(monkeypatch, periods=15).to_parquet(root / "raw" / "yf_cache.parquet")
    build.rebuild(data_root=root, start="2015-01-01")
    assert _panel_end(root) == pin
    assert _membership_end(root) == pin


def test_a_leg_that_reads_the_panel_refuses_an_earlier_pin(tmp_path) -> None:
    """A pin before the panel is refused, and refused before any work is done."""
    root = tmp_path / "data"
    (root / "processed").mkdir(parents=True)
    dates = pd.bdate_range("2026-09-28", periods=4)
    frame = pd.DataFrame(
        {"r": 0.0},
        index=pd.MultiIndex.from_product([dates, ["A"]], names=["date", "ticker"]),
    )
    frame.to_parquet(root / "processed" / "returns.parquet")

    # the default pin is the panel's own end, and an explicit later pin is fine
    assert build.pinned_panel_end(None, root) == "2026-10-01"
    assert build.pinned_panel_end("2026-10-30", root) == "2026-10-30"
    with pytest.raises(ValueError, match="cannot be pinned earlier"):
        build.pinned_panel_end("2026-09-29", root)
    # and a reading leg refuses it before touching an artifact, not halfway in
    with pytest.raises(ValueError, match="cannot be pinned earlier"):
        build.rebuild_e4(data_root=root, end="2026-09-29")

    # the E1 leg is the exception: it makes the panel, so an earlier pin re-cuts it
    assert build.pinned_panel_end("2026-09-29", root, reading=False) == "2026-09-29"
