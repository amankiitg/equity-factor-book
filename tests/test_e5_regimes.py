"""Sprint E5 Task 4: regimes, recovery times and the stress haircut.

Every version appears in the regime table, the episode windows are the stored
ones, and the haircut is a number with a stated basis.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from efb import eval_risk

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "eval"
VIX = ROOT / "data" / "raw" / "vix.parquet"


def test_the_episode_windows_are_the_stored_ones() -> None:
    assert eval_risk.EPISODES == {
        "2020_q1": (pd.Timestamp("2020-01-01"), pd.Timestamp("2020-03-31")),
        "2022": (pd.Timestamp("2022-01-03"), pd.Timestamp("2022-12-30")),
    }


@pytest.mark.integration
def test_the_vix_artifact_is_stored_and_named() -> None:
    assert VIX.exists(), "the VIX artifact has not been fetched"
    vix = pd.read_parquet(VIX)
    assert {"date", "vix"} <= set(vix.columns)
    assert len(vix) > 3000
    assert vix["vix"].between(5, 120).mean() > 0.9


@pytest.mark.integration
def test_every_version_appears_in_the_regime_table() -> None:
    if not (EVAL / "e5_regimes.parquet").exists():
        pytest.skip("the regime table has not been built yet")
    table = pd.read_parquet(EVAL / "e5_regimes.parquet")
    assert not table.empty
    for version in eval_risk.VERSIONS:
        assert version in set(table["version"]), version
    for regime in ("vix_low", "vix_mid", "vix_high", "2020_q1", "2022"):
        assert regime in set(table["regime"]), regime
    # both episodes must carry a row for every version so F5.3 can be scored
    episodes = table.loc[table["regime"].isin(("2020_q1", "2022"))]
    coverage = episodes.groupby("version")["regime"].nunique()
    assert (coverage == 2).all(), "a version is missing one episode row"


@pytest.mark.integration
def test_the_stress_haircut_is_a_number_with_a_stated_basis() -> None:
    if not (EVAL / "e5_stress_haircut.parquet").exists():
        pytest.skip("the champion has not been declared yet")
    haircut = pd.read_parquet(EVAL / "e5_stress_haircut.parquet")
    assert len(haircut) == 1
    assert isinstance(haircut.iloc[0]["stress_haircut"], float)
    assert haircut.iloc[0]["stress_haircut"] >= 0
    assert haircut.iloc[0]["basis"]
