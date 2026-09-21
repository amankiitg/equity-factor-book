"""Sprint E5 Task 3: horizon consistency and the asset-level check.

The sqrt(21) scaling is applied to the daily forecast and never to the
realized number, and the asset-level table covers every version and family.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from efb import eval_risk

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "eval"


def test_the_sqrt21_scaling_touches_the_forecast_not_the_realized() -> None:
    r_21 = np.array([0.02, -0.03, 0.01])
    sigma_daily = 0.012
    z = eval_risk.z_scaled_21(r_21, sigma_daily)
    expected = r_21 / (np.sqrt(21) * sigma_daily)
    assert np.allclose(z, expected)
    # doubling the realized return doubles z: the realized number is never scaled
    assert np.allclose(eval_risk.z_scaled_21(2 * r_21, sigma_daily), 2 * z)


@pytest.mark.integration
def test_the_horizon_table_covers_every_version_and_family() -> None:
    if not (EVAL / "e5_horizon.parquet").exists():
        pytest.skip("the horizon table has not been built yet")
    table = pd.read_parquet(EVAL / "e5_horizon.parquet")
    assert not table.empty
    assert set(table["version"]) == set(eval_risk.VERSIONS), set(table["version"])
    assert set(table["family"]) == set(eval_risk.FAMILIES), set(table["family"])
    assert (table["bias_scaled"] > 0).all()
    assert (table["bias_direct"] > 0).all()


@pytest.mark.integration
def test_the_asset_level_table_covers_every_version_and_family() -> None:
    if not (EVAL / "e5_asset_level.parquet").exists():
        pytest.skip("the asset-level table has not been built yet")
    table = pd.read_parquet(EVAL / "e5_asset_level.parquet")
    assert not table.empty
    assert set(table["version"]) == set(eval_risk.VERSIONS), set(table["version"])
    assert set(table["family"]) == set(eval_risk.FAMILIES), set(table["family"])
    assert (table["n_obs"] >= 30).all()
