"""Sprint E8 Task 4: the constrained mean-variance optimizer (cvxpy)."""

from __future__ import annotations

from pathlib import Path

import pytest

from efb import eval_risk, optimize, race

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


@pytest.mark.integration
def test_the_constrained_optimizer_respects_every_constraint() -> None:
    from efb import size as size_mod

    root = DATA
    wide, _counts = eval_risk.load_clean_wide(root)
    grid = race.race_grid(root)
    date = grid[len(grid) // 2]
    names = eval_risk._window_names(wide, date)
    supplied = eval_risk._xs_pieces(date, names, root)
    assert supplied is not None
    frame = size_mod.synthetic_alpha(root, rho=0.05, seed=0)
    group = frame.loc[frame["date"] == date]
    alpha = group.set_index("ticker")["alpha"].reindex(names).to_numpy(dtype=float)
    weights = optimize.constrained_mv(
        alpha,
        supplied["design"],
        supplied["factor_covariance"],
        supplied["specific"],
        date,
        names,
        root,
    )
    violations = optimize.constraint_violations(
        weights, supplied["design"], date, names, root
    )
    assert max(violations.values()) < 1e-8, violations
