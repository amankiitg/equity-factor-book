"""A missing beta history costs two columns, not the section (item 29)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from efb import attribution

DATA = Path(__file__).resolve().parents[1] / "data"


def test_a_missing_beta_history_leaves_the_panel_usable(tmp_path: Path) -> None:
    # The 2026-10-09 failure in one test: the artifact is absent from the seed, the
    # report must still be built from the files that are there.
    root = tmp_path / "data"
    (root / "models" / "XS-v1").mkdir(parents=True)
    (root / "processed").mkdir(exist_ok=True)
    shutil.copy(
        DATA / "processed" / "returns.parquet", root / "processed" / "returns.parquet"
    )
    for name in ("factor_returns.parquet", "specific_returns.parquet"):
        shutil.copy(DATA / "models" / "XS-v1" / name, root / "models" / "XS-v1" / name)

    panel = attribution.ModelPanel(root)

    assert panel.betas.empty
    assert list(panel.betas.columns) == ["date", "ticker", "beta"]
    # The columns the artifact feeds are null, and the panel is still a panel.
    missing = panel.betas_at(pd.Timestamp("2026-09-21"), ["AAPL"])
    assert pd.isna(missing).all()


def test_the_real_artifact_still_loads() -> None:
    panel = attribution.ModelPanel(DATA)
    assert not panel.betas.empty
    assert {"date", "ticker", "beta"} <= set(panel.betas.columns)
