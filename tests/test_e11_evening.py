"""Sprint E11, Task 1 to Task 3: the evening proposal job.

The tests pin the three things the evening job must never get wrong: the
universe is the SPY archive and asserted as such, the proposal carries the
idio share after the FMP hedge, and a null book that cannot reach the E10
vol target inside the gross cap is capped rather than leveraged past it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from live import evening_job as ev


def _write_spy_archive(data_root: Path, as_of: str, tickers: list[str]) -> Path:
    """Write one fake dated SPY holdings file with the columns the loader reads."""
    out_dir = data_root / "raw" / "spy_holdings"
    out_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        {
            "ticker": tickers,
            "name": tickers,
            "identifier": [f"CUSIP{i:04d}" for i in range(len(tickers))],
            "sedol": [f"SEDOL{i:04d}" for i in range(len(tickers))],
            "weight": [1.0 / len(tickers)] * len(tickers),
            "sector": ["Information Technology"] * len(tickers),
            "shares held": [1] * len(tickers),
            "local currency": ["USD"] * len(tickers),
            "as_of": [as_of] * len(tickers),
        }
    )
    stamp = pd.to_datetime(as_of).strftime("%Y-%m-%d")
    path = out_dir / f"spy_holdings_{stamp}.parquet"
    frame.to_parquet(path, index=False)
    return path


def test_load_spy_universe_uses_the_latest_archive(tmp_path: Path) -> None:
    _write_spy_archive(tmp_path, "2026-09-17", ["AAA", "BBB"])
    _write_spy_archive(tmp_path, "2026-09-18", ["AAA", "CCC"])
    frame, path = ev.load_spy_universe(tmp_path)
    assert path.name == "spy_holdings_2026-09-18.parquet"
    assert sorted(frame["ticker"]) == ["AAA", "CCC"]


def test_load_spy_universe_rejects_an_archive_before_the_seam(tmp_path: Path) -> None:
    _write_spy_archive(tmp_path, "2026-09-17", ["AAA"])
    with pytest.raises(ValueError, match="before the live universe seam"):
        ev.load_spy_universe(tmp_path)


def test_load_spy_universe_fails_without_any_archive(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no SPY archive files"):
        ev.load_spy_universe(tmp_path)


def test_stored_ic_reads_the_summary_row(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame({"signal": ["idio_momentum"], "ic_h1_mean": [0.012102]})
    summary.to_parquet(tmp_path / "alpha" / "summary.parquet", index=False)
    assert ev._stored_ic("idio_momentum", tmp_path) == pytest.approx(0.012102)


def test_decomposition_reports_exposure_gross_and_net() -> None:
    design = np.ones((4, 1))  # market column only
    factor_covariance = np.eye(1)
    specific = np.full(4, 0.01)
    weights = np.array([0.25, -0.25, 0.25, -0.25])
    result = ev._decomposition(weights, design, factor_covariance, specific)
    assert result["gross"] == pytest.approx(1.0)
    assert result["net"] == pytest.approx(0.0)
    assert result["max_abs_exposure"] == pytest.approx(0.0)
    assert result["n_eff"] == pytest.approx(4.0)
    assert result["idio_share"] == pytest.approx(1.0)


def test_build_proposal_asserts_the_spy_universe_and_stores_idio_share() -> None:
    manifest = ev.build_proposal(store=False)
    # the universe is the SPY archive, asserted in the manifest
    assert manifest["universe_source"].startswith("raw/spy_holdings/")
    assert manifest["universe_as_of"] >= "2026-09-18"
    # the null book is factor-neutral after the exact FMP hedge
    assert manifest["idio_share_after_fmp"] == pytest.approx(1.0, abs=1e-9)
    assert manifest["max_abs_exposure_after_fmp"] < 1e-9
    # the E8 constraint set holds: gross capped, net zero, position cap
    assert manifest["gross"] == pytest.approx(1.0)
    assert abs(manifest["net"]) < 1e-9
    # the SPY names the frozen model does not know are excluded, not imputed
    assert manifest["n_excluded"] >= 1
    assert manifest["n_names"] + manifest["n_excluded"] >= 490


def test_build_proposal_caps_a_null_book_at_the_gross_cap() -> None:
    manifest = ev.build_proposal(store=False)
    # a null alpha cannot reach the 10% vol target inside gross 1, so the
    # cap binds and the achieved vol is stored below the target
    assert manifest["gross_cap_bound"] is True
    assert manifest["achieved_annual_vol"] < manifest["target_annual_vol"]
