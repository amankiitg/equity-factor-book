"""Sprint E11 live: incremental extension integrity.

Rows dated on or before 2026-09-03 in descriptors, factor_returns and
specific_returns are frozen invariants: every extension appends new
sessions without touching them. The pre-cutoff block hashes are recorded
here and asserted, and the extension must have added sessions after the
frozen as-of.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from live import extend

ROOT = Path(__file__).resolve().parents[1]
XS = ROOT / "data" / "models" / "XS-v1"

# recorded before the first extension, and unchanged after it
BASELINE = {
    "descriptors": ("8f93968f67f31cd33453a7fad13685d74748f3f480f17406954459fdd31caafa"),
    "factor_returns": (
        "42a31d64e0cb7619f09669cfdac217085172ccd577ee37c304da6bab3246700a"
    ),
    "specific_returns": (
        "176dc4b39fb75f1dae6afd0f6afea3b14c64bd6ebcc855450d392d46bd9d489a"
    ),
}


def test_block_hash_is_deterministic() -> None:
    frame = pd.DataFrame(
        {
            "date": ["2026-09-01", "2026-09-02"],
            "ticker": ["A", "A"],
            "descriptor": ["size", "size"],
            "value": [1.0, 2.0],
        }
    )
    assert extend._block_hash(frame, pd.Timestamp("2026-09-03")) == extend._block_hash(
        frame, pd.Timestamp("2026-09-03")
    )


@pytest.mark.integration
@pytest.mark.slow
def test_pre_cutoff_blocks_are_byte_identical() -> None:
    if not (XS / "factor_returns.parquet").exists():
        pytest.skip("XS-v1 artifacts not built")
    current = extend.incremental_integrity()
    for name, expected in BASELINE.items():
        assert current[name] == expected, name


@pytest.mark.integration
def test_sessions_after_the_frozen_as_of_were_appended() -> None:
    for name in ("descriptors", "factor_returns", "specific_returns"):
        frame = pd.read_parquet(XS / f"{name}.parquet")
        last = pd.to_datetime(frame["date"]).max()
        assert last > pd.Timestamp("2026-09-03"), name


@pytest.mark.integration
@pytest.mark.slow
def test_identity_drops_do_not_reappear_in_the_extension() -> None:
    """The extension applies the E1 identity exclusions, so a reused
    symbol does not come back with another company's history. DD is the
    one dropped ticker the sector file maps, so it is the one the buggy
    extension put back into returns and specific_returns.
    """
    returns_frame = pd.read_parquet(ROOT / "data" / "processed" / "returns.parquet")
    specific = pd.read_parquet(XS / "specific_returns.parquet")
    assert "DD" not in set(returns_frame.index.get_level_values("ticker"))
    assert "DD" not in set(specific["ticker"])


def _live_tree(root: Path) -> None:
    """A tree with a four-name panel and a two-name universe."""
    (root / "raw" / "spy_holdings").mkdir(parents=True)
    (root / "processed").mkdir(parents=True)
    pd.DataFrame(
        {"ticker": ["LIVE1", "LIVE2", "DELISTED", "HELD"], "gics_sector": ["Tech"] * 4}
    ).to_parquet(root / "processed" / "sectors.parquet")
    index = pd.MultiIndex.from_product(
        [[pd.Timestamp("2026-09-21")], ["LIVE1", "LIVE2", "DELISTED", "HELD"]],
        names=["date", "ticker"],
    )
    pd.DataFrame({"ret": [0.1] * 4}, index=index).to_parquet(
        root / "processed" / "returns.parquet"
    )
    pd.DataFrame(
        {"ticker": ["LIVE1", "LIVE2"], "as_of": ["2026-09-21"] * 2}
    ).to_parquet(root / "raw" / "spy_holdings" / "spy_holdings_2026-09-21.parquet")


def test_the_fetch_is_the_live_universe_and_the_book_not_the_frozen_panel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The panel is every name the history ever held, and most are delisted.

    Asking the vendor about the panel every evening produced 206 failures a night,
    which bury the one failure that would matter. Nothing outside the universe and
    the held book can reach the book being priced, so nothing else is asked for.
    """
    from live import snapshot

    root = tmp_path / "data"
    _live_tree(root)
    book = pd.DataFrame({"ticker": ["HELD"], "weight": [1.0]})
    monkeypatch.setattr(snapshot, "previous_proposal", lambda: (None, book, None))

    # the held name is outside the universe and is still fetched
    assert extend._live_tickers(root) == ["HELD", "LIVE1", "LIVE2"]

    # a store that cannot answer leaves the universe, which is what the run needs
    # to price: the held names are a convenience, not a requirement
    def explode() -> None:
        raise RuntimeError("the store is unreachable")

    monkeypatch.setattr(snapshot, "previous_proposal", explode)
    assert extend._live_tickers(root) == ["LIVE1", "LIVE2"]

    # and the frozen panel still exists for the callers that ask for it
    assert extend._frozen_tickers(root) == ["DELISTED", "HELD", "LIVE1", "LIVE2"]
