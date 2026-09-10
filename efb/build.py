"""One-command rebuild of the E1 data layer (Sprint E1, Task 7).

`python -m efb.build` (alias: make rebuild-e1) rebuilds every E1 artifact
from its sources, writes data/VERSION.json with a content hash per
artifact, and stores the F1 criteria in sprints/E1/RESULTS.json.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from efb import factors, hygiene, prices, returns, universe

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"
START = "2010-01-04"
WARMUP_START = "2009-12-15"

ARTIFACTS = [
    "raw/prices.parquet",
    "raw/factors_ff.parquet",
    "processed/returns.parquet",
    "processed/universe_membership.parquet",
    "processed/sectors.parquet",
    "processed/events.parquet",
]

E2_ARTIFACTS = [
    "models/TS-v1/loadings.parquet",
    "models/TS-v1/loadings_se.parquet",
    "models/TS-v1/residuals.parquet",
    "models/TS-v1/idio_vol.parquet",
    "models/TS-v1/factor_cov.parquet",
    "models/TS-v1/beta_history.parquet",
    "models/registry.json",
    "eval/beta_horse_race.parquet",
    "eval/vol_horse_race.parquet",
    "eval/portfolio_risk_snapshot.parquet",
    "portfolios/seed_ew.parquet",
    "portfolios/seed_mom_ls.parquet",
    "portfolios/seed_ew_risk.parquet",
    "portfolios/seed_mom_ls_risk.parquet",
]

MODEL_START = 2010
REGISTRY_PATH = DATA_ROOT / "models" / "registry.json"


def hash_file(path: Path) -> str:
    """SHA-256 content hash of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_version(artifact_paths: list[Path], out_path: Path, note: str) -> dict:
    """Write data/VERSION.json with a content hash of every artifact."""
    artifacts: dict[str, dict[str, object]] = {}
    for path in sorted(artifact_paths):
        artifacts[path.name] = {
            "sha256": hash_file(path),
            "bytes": path.stat().st_size,
        }
    payload = {
        "note": note,
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "artifacts": artifacts,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def rebuild(
    data_root: Path = DATA_ROOT,
    start: str = START,
    end: str | None = None,
    as_of: str | None = None,
    results_path: Path | None = None,
) -> dict[str, object]:
    """Rebuild all E1 artifacts from sources and version them.

    When results_path is given (the real sprints/E1/RESULTS.json), the F1
    criteria are recomputed from the fresh artifacts and stored there.
    """
    as_of = as_of or datetime.now(UTC).strftime("%Y-%m-%d")
    end = end or datetime.now(UTC).strftime("%Y-%m-%d")
    raw_dir = data_root / "raw"
    processed_dir = data_root / "processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    # 1. Universe sources
    constituents = universe.fetch_constituents()
    changes = universe.fetch_changes()
    tickers = universe.all_tickers(constituents, changes)

    # 2. Prices
    cache_path = raw_dir / "yf_cache.parquet"
    raw_prices = prices.load_or_download(
        tickers, cache_path, start=WARMUP_START, end=end
    )
    prices_artifact = prices.build_prices_artifact(raw_prices, start=start)
    prices.save_prices(prices_artifact, raw_dir / "prices.parquet")

    # 3. Universe membership and sectors
    members = universe.build_membership(changes, constituents, start=start, end=end)
    members.to_parquet(processed_dir / "universe_membership.parquet")
    sectors = universe.build_sectors(constituents, as_of=as_of)
    sectors.to_parquet(processed_dir / "sectors.parquet", index=False)

    # 4. Factors
    frames = factors.load_french_factors()
    factors_artifact = factors.build_factors_artifact(frames, start=start)
    factors_artifact.to_parquet(raw_dir / "factors_ff.parquet")

    # 5. Returns and hygiene flags
    returns_frame = returns.compute_returns(prices_artifact, factors_artifact["rf"])
    returns_frame = hygiene.apply_flags(returns_frame)
    returns_frame.to_parquet(processed_dir / "returns.parquet")

    # 6. Event log
    membership_events = universe.membership_changes(members)
    events = hygiene.build_events(prices_artifact, returns_frame, membership_events)
    events.to_parquet(processed_dir / "events.parquet")

    # 7. Version file
    artifact_paths = [data_root / rel for rel in ARTIFACTS]
    payload = write_version(
        artifact_paths,
        data_root / "VERSION.json",
        note=(
            "Built by make rebuild-e1 (Sprint E1). Every data artifact "
            "carries a content hash here; the dashboard sidebar shows "
            "this version."
        ),
    )

    # 8. F criteria, stored so the numbers and the artifacts always agree
    if results_path is not None:
        from efb import evaluate

        inputs = evaluate.compute_from_artifacts(data_root=data_root)
        criteria = evaluate.evaluate_criteria(**inputs)
        evaluate.write_results(criteria, results_path)

    return {"n_steps": 7, "version": payload, "n_tickers": len(tickers)}


def build_e2_artifacts(
    data_root: Path = DATA_ROOT,
    start: int = MODEL_START,
    include_garch: bool = True,
    garch_tickers: int = 60,
) -> dict[str, object]:
    """Build every E2 artifact from the E1 artifacts (Sprint E2, Task 6).

    Writes the TS-v1 loadings, SEs, residuals, idio vol and factor
    covariance, the monthly beta history, the beta and volatility horse
    races, the two seed portfolios with their risk histories, the
    portfolio risk snapshot, and the TS-v1 registry entry.
    """
    from efb import portfolios as pf
    from efb import registry, vol
    from efb.models import timeseries as ts

    raw_dir = data_root / "raw"
    processed_dir = data_root / "processed"
    model_dir = data_root / "models" / "TS-v1"
    eval_dir = data_root / "eval"
    port_dir = data_root / "portfolios"
    for directory in (model_dir, eval_dir, port_dir):
        directory.mkdir(parents=True, exist_ok=True)

    returns_frame = pd.read_parquet(processed_dir / "returns.parquet")
    factors_frame = pd.read_parquet(raw_dir / "factors_ff.parquet")
    members = pd.read_parquet(processed_dir / "universe_membership.parquet")
    sectors = pd.read_parquet(processed_dir / "sectors.parquet")

    y_raw, fac, flags = ts.panel_from_artifacts(
        returns_frame, factors_frame, start=start, exclude_flags=False
    )
    # the multifactor fit masks and counts flagged rows itself
    y = y_raw.mask(flags["stale"].astype(bool)).mask(flags["outlier"].astype(bool))
    multi = ts.select_factors(fac)
    fit = ts.fit_factor_model(y_raw, multi, flags=flags)

    loadings = fit["loadings"]
    loadings.to_parquet(model_dir / "loadings.parquet")
    se = pd.concat(
        {"ols": fit["loadings_ols_se"], "nw_l5": fit["loadings_nw_se"]}, axis=1
    )
    se.columns.names = ["method", "statistic"]
    se.to_parquet(model_dir / "loadings_se.parquet")
    fit["residuals"].to_parquet(model_dir / "residuals.parquet")
    sigma = fit["sigma_eps"]
    idio = pd.DataFrame(
        {
            "idio_vol": sigma,
            "idio_vol_ann": sigma * np.sqrt(252.0),
            "idio_var": sigma**2,
            "n_obs": fit["n_obs"],
        }
    )
    idio.to_parquet(model_dir / "idio_vol.parquet")
    factor_cov = pf.ewma_factor_cov(multi, half_life=90.0)
    factor_cov.to_parquet(model_dir / "factor_cov.parquet")

    history = ts.beta_history(
        y, fac["mkt_rf"], window=252, half_lives=(63, 126), min_obs=126
    )
    month_ends = pf.month_end_dates(history.index)
    snapshot = history.loc[history.index.isin(month_ends)].copy()
    snapshot.index.name = "date"
    long_beta = (
        snapshot.stack(level="method", future_stack=True)
        .stack(level="ticker", future_stack=True)
        .rename("beta")
        .reset_index()
    )
    long_beta.to_parquet(model_dir / "beta_history.parquet", index=False)

    beta_race = ts.beta_horse_race(y, fac["mkt_rf"])
    beta_race.to_parquet(eval_dir / "beta_horse_race.parquet", index=False)
    returns_wide = returns_frame["r"].unstack("ticker")
    oos_start = (returns_wide.index.max() - pd.DateOffset(years=2)).strftime("%Y-%m-%d")
    vol_table = vol.vol_horse_race(
        returns_wide,
        oos_start=oos_start,
        include_garch=include_garch,
        garch_tickers=garch_tickers,
    )
    vol_table.to_parquet(eval_dir / "vol_horse_race.parquet", index=False)

    ew_weights = pf.ew_seed_weights(members)
    ls_weights = pf.momentum_ls_weights(returns_wide, members, sectors)
    pf.to_long_weights(ew_weights, caveat=True).to_parquet(
        port_dir / "seed_ew.parquet", index=False
    )
    pf.to_long_weights(ls_weights, caveat=False).to_parquet(
        port_dir / "seed_mom_ls.parquet", index=False
    )

    betas = ts._as_frame(ts.rolling_beta(y, fac["mkt_rf"], window=252, min_obs=126))
    factor_var = vol.ewma_vol(fac["mkt_rf"], lam=0.5 ** (1.0 / 90.0), min_obs=60)
    residual_wide = fit["residuals"]["residual"].unstack("ticker")
    idio_var_rolling = pf.rolling_idio_var(residual_wide)
    for name, weights in (("seed_ew", ew_weights), ("seed_mom_ls", ls_weights)):
        risk = pf.portfolio_risk_history(
            weights, returns_wide, betas, factor_var, idio_var_rolling
        )
        risk.to_parquet(port_dir / f"{name}_risk.parquet")

    rows = []
    for name, weights in (("seed_ew", ew_weights), ("seed_mom_ls", ls_weights)):
        w_last = weights.iloc[-1]
        w_last = w_last[w_last.abs() > 0]
        decomposition = pf.risk_decomposition(
            w_last, loadings[ts.MULTI_FACTORS], factor_cov, idio["idio_var"]
        )
        rows.append(
            {"portfolio": name, "survivorship_caveat": name == "seed_ew", **decomposition}
        )
    pd.DataFrame(rows).to_parquet(
        eval_dir / "portfolio_risk_snapshot.parquet", index=False
    )

    entry = registry.model_entry(
        version="TS-v1",
        family="timeseries",
        parameters={
            "factors": ts.MULTI_FACTORS,
            "model_start": start,
            "nw_lag": ts.NW_LAG,
            "window": 252,
            "ewma_half_lives": [63, 126],
            "factor_cov_half_life": 90,
            "min_obs": ts.MIN_OBS,
            "exclusions": {
                key: int(fit["exclusions"][key].sum()) for key in ("stale", "outlier", "nan")
            },
        },
        universe_path=processed_dir / "universe_membership.parquet",
        data_paths=[raw_dir / "factors_ff.parquet", processed_dir / "returns.parquet"],
        walkthrough="notebooks/E2_walkthrough.html",
        deliverable="docs/research/E2_exposure_study.md",
        results="sprints/E2/RESULTS.json",
    )
    registry.write_registry(data_root / "models" / "registry.json", entry)
    return {
        "n_names": int(loadings.shape[0]),
        "n_dates": int(y.shape[0]),
        "exclusions": entry["parameters"]["exclusions"],
        "oos_start": oos_start,
    }


def rebuild_e2(
    data_root: Path = DATA_ROOT,
    results_path: Path | None = None,
    start: int = MODEL_START,
) -> dict[str, object]:
    """Run the E1 rebuild, then the E2 artifacts, and version everything."""
    e1 = rebuild(data_root=data_root, start="2010-01-04", results_path=None)
    e2 = build_e2_artifacts(data_root=data_root, start=start)
    artifact_paths = [data_root / rel for rel in ARTIFACTS + E2_ARTIFACTS]
    payload = write_version(
        artifact_paths,
        data_root / "VERSION.json",
        note="Built by make rebuild-e2 (Sprint E2). E1 and E2 artifacts, each with a content hash; the dashboard sidebar shows this version.",
    )
    if results_path is not None:
        from efb import evaluate

        inputs = evaluate.compute_e2_from_artifacts(data_root=data_root)
        criteria = evaluate.evaluate_e2_criteria(**inputs)
        evaluate.write_results(criteria, results_path, sprint="E2")
    return {"n_steps": 8, "e1_tickers": e1["n_tickers"], "e2": e2, "version": payload}


def main() -> None:
    if "--e2" in sys.argv:
        summary = rebuild_e2(results_path=ROOT / "sprints" / "E2" / "RESULTS.json")
    else:
        summary = rebuild(results_path=ROOT / "sprints" / "E1" / "RESULTS.json")
    print(json.dumps({"n_steps": summary["n_steps"]}, indent=2))


if __name__ == "__main__":
    main()
