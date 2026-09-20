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

from efb import factors, hygiene, identity, prices, returns, universe
from efb.models import fundamental as fx

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"
START = "2010-01-04"
WARMUP_START = "2009-12-15"

ARTIFACTS = [
    "raw/prices.parquet",
    "raw/factors_ff.parquet",
    "processed/returns.parquet",
    "processed/universe_membership.parquet",
    "processed/universe_changes.parquet",
    "processed/universe_constituents.parquet",
    "processed/ticker_identity.parquet",
    "processed/ticker_identity_readded.parquet",
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
    "eval/vol_horse_race_aligned.parquet",
    "eval/vol_window_dependence.parquet",
    "eval/momentum_exposure.parquet",
    "eval/momentum_exposure_rolling.parquet",
    "eval/portfolio_risk_snapshot.parquet",
    "portfolios/seed_ew.parquet",
    "portfolios/seed_mom_ls.parquet",
    "portfolios/seed_ew_risk.parquet",
    "portfolios/seed_mom_ls_risk.parquet",
    "portfolios/seed_mom_ls_risk_21.parquet",
]

E3_ARTIFACTS = [
    "raw/shares_history.parquet",
    "processed/market_cap.parquet",
    "models/XS-v1/descriptors.parquet",
    "models/XS-v1/factor_returns.parquet",
    "models/XS-v1/specific_returns.parquet",
    "models/XS-v1/fmp_weights.parquet",
    "models/XS-v1/xs_r2.parquet",
    "models/XS-v1/factor_cov.parquet",
    "models/XS-v1/specific_var.parquet",
    "models/registry.json",
    "eval/xs_fm_premia.parquet",
    "eval/xs_risk_decomposition.parquet",
    "eval/xs_bias.parquet",
    "eval/xs_bias_by_exposure.parquet",
    "eval/xs_coverage_by_year.parquet",
    "eval/xs_survivor_restriction.parquet",
    "eval/xs_exposure_timeseries.parquet",
    "eval/xs_residual_covariance.parquet",
]

MODEL_START = 2010
REGISTRY_PATH = DATA_ROOT / "models" / "registry.json"

# The registry entry records the data hash, so it cannot be inside the hash.
# Everything else the build writes is, which is what makes the number
# reproducible from the artifacts alone.
NON_DATA_ARTIFACTS = {"registry.json"}


def hash_file(path: Path) -> str:
    """SHA-256 content hash of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def combined_hash(artifacts: dict[str, dict[str, object]]) -> str:
    """One hash over every artifact hash, the data hash of a build."""
    digest = hashlib.sha256()
    for name in sorted(artifacts):
        if name in NON_DATA_ARTIFACTS:
            continue
        digest.update(name.encode())
        digest.update(str(artifacts[name].get("sha256", "")).encode())
    return digest.hexdigest()


def previous_data_hash(path: Path, restrict: list[str] | None = None) -> str | None:
    """Data hash of the manifest that is about to be replaced.

    `restrict` limits the comparison to the artifact names this build
    writes, so an E1 rebuild that replaces an E1 plus E2 manifest still
    compares like with like rather than hashing twenty files against
    seven.
    """
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:  # pragma: no cover - corrupt manifest
        return None
    artifacts = payload.get("artifacts", {})
    if restrict is not None:
        artifacts = {k: v for k, v in artifacts.items() if k in set(restrict)}
    if not artifacts:
        return None
    return combined_hash(artifacts)


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
        "data_hash": combined_hash(artifacts),
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
    changes.to_parquet(processed_dir / "universe_changes.parquet", index=False)
    constituents.to_parquet(
        processed_dir / "universe_constituents.parquet", index=False
    )
    members = universe.build_membership(changes, constituents, start=start, end=end)
    members.to_parquet(processed_dir / "universe_membership.parquet")
    sectors = universe.build_sectors(constituents, as_of=as_of)
    sectors.to_parquet(processed_dir / "sectors.parquet", index=False)

    # 4. Factors
    frames = factors.load_french_factors()
    factors_artifact = factors.build_factors_artifact(frames, start=start)
    factors_artifact.to_parquet(raw_dir / "factors_ff.parquet")

    # 5. Ticker identity, before returns are used by anything (C1, F2.6b)
    # and the re-add review that restores renamed current constituents (C6)
    identity_table = identity.run(data_root, verbose=False)
    readded_path = processed_dir / "ticker_identity_readded.parquet"
    readded_review = pd.read_parquet(readded_path) if readded_path.exists() else None
    identity_drops, identity_truncations = identity.exclusions(
        identity_table, readded=readded_review
    )

    # 6. Returns and hygiene flags
    returns_frame = returns.compute_returns(prices_artifact, factors_artifact["rf"])
    if identity_truncations:
        returns_frame = identity.drop_truncated(returns_frame, identity_truncations)
    if identity_drops:
        # a reused symbol carries another company's history, so the member's
        # returns are missing rather than wrong: keep the rows out entirely
        returns_frame = returns_frame[
            ~returns_frame.index.isin(identity_drops, level="ticker")
        ]
    returns_frame = hygiene.apply_flags(returns_frame)
    returns_frame.to_parquet(processed_dir / "returns.parquet")

    # 7. Event log
    membership_events = universe.membership_changes(members)
    events = hygiene.build_events(prices_artifact, returns_frame, membership_events)
    events.to_parquet(processed_dir / "events.parquet")

    # 8. Version file
    version_path = data_root / "VERSION.json"
    e1_names = [Path(rel).name for rel in ARTIFACTS]
    old_hash = previous_data_hash(version_path, restrict=e1_names)
    artifact_paths = [data_root / rel for rel in ARTIFACTS]
    payload = write_version(
        artifact_paths,
        version_path,
        note=(
            "Built by make rebuild-e1 (Sprint E1). Every data artifact "
            "carries a content hash here; the dashboard sidebar shows "
            "this version."
        ),
    )

    # 9. F criteria, stored so the numbers and the artifacts always agree
    if results_path is not None:
        from efb import evaluate

        inputs = evaluate.compute_from_artifacts(data_root=data_root)
        criteria = evaluate.evaluate_criteria(**inputs)
        # the same correction moves the E2 zero tier, so its old and new
        # values are recorded here too, against the E2 file's own history
        e2_path = data_root.parent / "sprints" / "E2" / "RESULTS.json"
        e2_previous: dict[str, dict[str, object]] = {}
        if e2_path.exists():
            e2_previous = json.loads(e2_path.read_text()).get("criteria", {})
        evaluate.write_results(
            criteria,
            results_path,
            data_hash=payload["data_hash"],
            previous_data_hash=old_hash,
            extra=evaluate.zero_tier_criteria(data_root),
            extra_previous=e2_previous,
            reference_values=evaluate.e1_reference_values(data_root),
        )

    return {
        "n_steps": 8,
        "version": payload,
        "n_tickers": len(tickers),
        "identity_dropped": identity_drops,
    }


def build_e2_artifacts(
    data_root: Path = DATA_ROOT,
    start: int = MODEL_START,
    include_garch: bool = True,
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

    # Ticker identity (close-out C1, criterion F2.6b). The symbol on the
    # other end of the name is the direct test for a reused ticker; the
    # level-shift check below stays as a safety net for names that were
    # never on the removed list.
    prices_frame = pd.read_parquet(raw_dir / "prices.parquet")
    broken = hygiene.series_break_tickers(prices_frame)
    identity_status = "skipped, no changes artifact"
    identity_table = pd.DataFrame()
    readded_review = pd.DataFrame()
    changes_path = processed_dir / "universe_changes.parquet"
    if changes_path.exists():
        changes = pd.read_parquet(changes_path)
        tickers = sorted(set(identity.removal_names(changes)))
        names = identity.fetch_symbol_names(
            tickers, cache_path=raw_dir / "yf_names.parquet"
        )
        identity_table = identity.identity_table(
            changes,
            prices_frame,
            names,
            members=members,
            breaks=set(broken),
        )
        identity_table.to_parquet(
            processed_dir / "ticker_identity.parquet", index=False
        )
        identity_status = "applied"
        # C6: the reused list is only final once the re-add and current
        # member cases are checked, so E2 reuses E1's review when it exists
        readded_path = processed_dir / "ticker_identity_readded.parquet"
        constituents_path = processed_dir / "universe_constituents.parquet"
        if readded_path.exists():
            readded_review = pd.read_parquet(readded_path)
        elif constituents_path.exists():
            readded_review = identity.readded_review(
                identity_table,
                changes,
                pd.read_parquet(constituents_path),
                names,
            )
            readded_review.to_parquet(readded_path, index=False)

    readded_reviewed = 0
    readded_kept: list[str] = []
    readded_staying_dropped: list[str] = []
    if "decision" in readded_review.columns:
        readded_reviewed = int(len(readded_review))
        readded_kept = sorted(
            readded_review.loc[
                readded_review["decision"] == "keep_truncated", "ticker"
            ].tolist()
        )
        readded_staying_dropped = sorted(
            readded_review.loc[
                readded_review["decision"] == "stays_dropped", "ticker"
            ].tolist()
        )

    identity_drops, identity_truncations = identity.exclusions(
        identity_table, readded=readded_review
    )
    if identity_truncations:
        returns_frame = identity.drop_truncated(returns_frame, identity_truncations)

    dropped = sorted(set(identity_drops) | set(broken))
    if dropped:
        returns_frame = returns_frame[
            ~returns_frame.index.isin(dropped, level="ticker")
        ]

    y_raw, fac, flags = ts.panel_from_artifacts(
        returns_frame, factors_frame, start=start, exclude_flags=False
    )
    # the multifactor fit masks and counts flagged rows itself
    y = y_raw.mask(flags["stale"].astype(bool)).mask(flags["outlier"].astype(bool))
    multi = ts.select_factors(fac)
    fit = ts.fit_factor_model(y_raw, multi, flags=flags)

    loadings = fit["loadings"].copy()
    loadings["r_squared"] = fit["r_squared"]
    loadings["n_obs"] = fit["n_obs"]
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
    # Volatility, momentum and portfolio risk read the flagged returns: a
    # single 95x day for one name dominates a mean QLIKE and a realized vol.
    returns_wide = hygiene.clean_returns(returns_frame).unstack("ticker")
    oos_start = (returns_wide.index.max() - pd.DateOffset(years=2)).strftime("%Y-%m-%d")
    # C7: one seeded random sample of names with full out-of-sample
    # coverage, fitted once, scored by both races
    garch_names: list[str] = []
    garch_params: dict[str, dict[str, float]] = {}
    garch_seed = vol.GARCH_SEED
    garch_failed: list[str] = []
    if include_garch:
        garch_names, garch_seed = vol.garch_sample(
            returns_wide, oos_start, n=vol.GARCH_SAMPLE, seed=vol.GARCH_SEED
        )
        garch_params, garch_failed = vol.fit_garch_universe(
            returns_wide, garch_names, split=oos_start
        )
    vol_table = vol.vol_horse_race(
        returns_wide,
        oos_start=oos_start,
        include_garch=include_garch,
        garch_names=garch_names,
        garch_params=garch_params,
    )
    vol_table.to_parquet(eval_dir / "vol_horse_race.parquet", index=False)

    # C3: the horizon-aligned evaluation. One-step forecasts against the same
    # day's squared return, and 21-day forecasts against the realized variance
    # of the next 21 days, both on the same window with flagged rows excluded.
    aligned = vol.aligned_horse_race(
        returns_wide,
        oos_start=oos_start,
        horizons=(1, 21),
        garch_names=garch_names,
        garch_params=garch_params,
    )
    aligned.to_parquet(eval_dir / "vol_horse_race_aligned.parquet", index=False)
    aligned_fits = {
        "fitted": aligned.attrs.get("garch_fitted", []),
        "failed": aligned.attrs.get("garch_failed", []),
    }
    if not include_garch:
        garch_params, garch_failed = {}, []

    # C7, second part, no new criterion: the same estimators over the whole
    # history from MODEL_START rather than the two-year out-of-sample window,
    # so the year-by-year comparison includes 2020 and answers whether the
    # trailing-wins result is a property of the window.
    window_rows: list[dict[str, object]] = []
    for method in ("ewma_094", "ewma_097"):
        full = vol.win_rate_by_year(
            returns_wide, oos_start=START, method=method, baseline="trailing_252"
        )
        window_rows.append(
            {
                "method": method,
                "baseline": "trailing_252",
                "scope": "day_level_pooled",
                "year": pd.NA,
                "win_share": full["pooled"],
                "n_obs": full["n_name_days"],
            }
        )
        window_rows.append(
            {
                "method": method,
                "baseline": "trailing_252",
                "scope": "day_level_excluding_2020",
                "year": pd.NA,
                "win_share": full["excluding_2020"],
                "n_obs": full["n_name_days"] - full["n_by_year"].get(2020, 0),
            }
        )
        for year, share in sorted(full["by_year"].items()):
            window_rows.append(
                {
                    "method": method,
                    "baseline": "trailing_252",
                    "scope": "day_level_by_year",
                    "year": int(year),
                    "win_share": float(share),
                    "n_obs": int(full["n_by_year"].get(int(year), 0)),
                }
            )
        # the name-level view, which is the one F2.3 is stated on: averaged
        # per name over the whole history against the same baseline, so the
        # two windows can be compared like for like
        for scope, window_start in (
            ("name_level_oos_window", oos_start),
            ("name_level_full_history", START),
        ):
            table = vol.vol_horse_race(returns_wide, oos_start=window_start)
            shares = vol.beats_baseline(table, baseline="trailing_252").set_index(
                "method"
            )
            window_rows.append(
                {
                    "method": method,
                    "baseline": "trailing_252",
                    "scope": scope,
                    "year": pd.NA,
                    "win_share": float(shares.loc[method, "win_share"]),
                    "n_obs": int(shares.loc[method, "n_names"]),
                }
            )
    window_frame = pd.DataFrame(window_rows)
    window_frame["year"] = window_frame["year"].astype("Int64")
    window_frame.to_parquet(eval_dir / "vol_window_dependence.parquet", index=False)

    # the seed books are also built from usable names only, so a spliced
    # series cannot sit in a portfolio while its returns are missing
    if broken:
        members = members.drop(columns=[c for c in members.columns if c in broken])
        sectors = sectors[~sectors["ticker"].isin(broken)]

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

    # C8(b): the same diagonal-model bias statistic for the momentum book,
    # on a 21-day forward window rather than 63, because a book that is
    # re-sorted every month is measured over the month it is held
    mom_risk_21 = pf.portfolio_risk_history(
        ls_weights,
        returns_wide,
        betas,
        factor_var,
        idio_var_rolling,
        forward=21,
    )
    mom_risk_21.to_parquet(port_dir / "seed_mom_ls_risk_21.parquet")

    rows = []
    for name, weights in (("seed_ew", ew_weights), ("seed_mom_ls", ls_weights)):
        w_last = weights.iloc[-1]
        w_last = w_last[w_last.abs() > 0]
        decomposition = pf.risk_decomposition(
            w_last, loadings[ts.MULTI_FACTORS], factor_cov, idio["idio_var"]
        )
        rows.append(
            {
                "portfolio": name,
                "survivorship_caveat": name == "seed_ew",
                **decomposition,
            }
        )
    pd.DataFrame(rows).to_parquet(
        eval_dir / "portfolio_risk_snapshot.parquet", index=False
    )

    # C4: the momentum seed book's own MOM exposure, and the three ways of
    # measuring how much of its risk is factor risk rather than residual.
    mom = pf.mom_sanity(
        ls_weights, returns_wide, fac[ts.MULTI_FACTORS], idio_var=idio["idio_var"]
    )
    mom_weights = ls_weights.iloc[-1]
    mom_weights = mom_weights[mom_weights.abs() > 0]
    mom_snapshot = pf.risk_decomposition(
        mom_weights, loadings[ts.MULTI_FACTORS], factor_cov, idio["idio_var"]
    )
    mom_loadings = mom["loadings"]
    assert isinstance(mom_loadings, pd.DataFrame)
    mom_rows = mom_loadings.reset_index(names="factor").assign(
        portfolio="seed_mom_ls",
        factor_share_regression_betas=mom["factor_share_with_mom"],
        factor_share_without_mom=mom["factor_share_without_mom"],
        mom_loading=mom["mom_loading"],
        mom_t_stat=mom["mom_t_stat"],
        mom_check_passes=mom["passes"],
    )
    mom_rows["factor_share_name_level_betas"] = mom_snapshot["factor_share"]
    mom_rows["regression_r_squared"] = mom_loadings["r_squared"].iloc[0]
    mom_rows.to_parquet(eval_dir / "momentum_exposure.parquet", index=False)

    # C8(a): the book's MOM exposure from rolling 252d name-level betas
    # dated at each rebalance, against the static full-sample aggregate
    rolling_betas = {
        name: ts._as_frame(ts.rolling_beta(y, fac[name], window=252, min_obs=126))
        for name in ts.MULTI_FACTORS
    }
    exposure_history = pf.rolling_book_exposure(
        ls_weights, rolling_betas, factor_cov, idio_var_rolling, factor="mom"
    )
    exposure_history.to_parquet(eval_dir / "momentum_exposure_rolling.parquet")
    static_exposure = float((mom_weights * loadings["mom"]).sum())
    exposure_stats = {
        "rolling_mean": float(exposure_history["exposure"].mean()),
        "rolling_min": float(exposure_history["exposure"].min()),
        "rolling_max": float(exposure_history["exposure"].max()),
        "rolling_share_mean": float(exposure_history["factor_share"].mean()),
        "static_aggregate": static_exposure,
        "static_share_last_month": mom_snapshot["factor_share"],
        "regression_loading": mom["mom_loading"],
        "n_rebalances": int(len(exposure_history)),
    }

    # the same combined hash rebuild_e2 writes into VERSION.json, so the
    # registry entry and the data manifest point at one identifier
    manifest = [data_root / rel for rel in ARTIFACTS + E2_ARTIFACTS]
    e2_data_hash = combined_hash(
        {path.name: {"sha256": hash_file(path)} for path in manifest if path.exists()}
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
                key: int(fit["exclusions"][key].sum())
                for key in ("stale", "outlier", "nan")
            },
            "series_break_tickers_dropped": broken,
            "identity_check": identity_status,
            "identity_dropped": identity_drops,
            "identity_truncated": {
                ticker: str(cutoff) for ticker, cutoff in identity_truncations.items()
            },
            # C6: which reused symbols turned out to be the same company
            # under a new name, and which stayed out of the panel
            "readded_reviewed": readded_reviewed,
            "readded_kept": readded_kept,
            "readded_staying_dropped": readded_staying_dropped,
            "garch_sample": len(garch_names),
            "garch_sample_size": len(garch_names),
            "garch_sample_tickers": garch_names,
            "garch_seed": garch_seed,
            "garch_fitted": len(aligned_fits["fitted"]),
            "garch_failed": len(aligned_fits["failed"]),
            "garch_not_converged": sorted(set(garch_failed)),
            "artifacts_hash": e2_data_hash,
            "mom_loading": mom["mom_loading"],
            "mom_t_stat": mom["mom_t_stat"],
            "mom_check_passes": mom["passes"],
            # C8: the same exposure measured from rolling betas at each
            # rebalance, which is the only way a monthly re-sorted book
            # can be measured at all
            "mom_exposure": exposure_stats,
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
        "identity_check": identity_status,
        "identity_dropped": identity_drops,
        "oos_start": oos_start,
        "readded_reviewed": readded_reviewed,
        "readded_kept": readded_kept,
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
    version_path = data_root / "VERSION.json"
    # the manifest hash about to be replaced, so the stored criteria carry
    # the identifier of the data they were measured on. E2's version file
    # covers E1 and E2 files, so the comparison is like for like
    old_hash = previous_data_hash(version_path)
    payload = write_version(
        artifact_paths,
        version_path,
        note=(
            "Built by make rebuild-e2 (Sprint E2). E1 and E2 artifacts, each "
            "with a content hash; the dashboard sidebar shows this version."
        ),
    )
    if results_path is not None:
        from efb import evaluate

        inputs = evaluate.compute_e2_from_artifacts(data_root=data_root)
        criteria = evaluate.evaluate_e2_criteria(**inputs)
        evaluate.write_results(
            criteria,
            results_path,
            sprint="E2",
            data_hash=payload["data_hash"],
            previous_data_hash=old_hash,
        )
    return {"n_steps": 8, "e1_tickers": e1["n_tickers"], "e2": e2, "version": payload}


SUBPERIODS = [
    ("full_sample", None, None),
    ("2011_2015", "2011-01-03", "2015-12-31"),
    ("2016_2020", "2016-01-01", "2020-12-31"),
    ("2021_2026", "2021-01-01", "2026-09-03"),
]


def _period_ends(design: fx.DesignResult, freq: str) -> list[pd.Timestamp]:
    """Last design date of each period ("M", "Q" or "Y")."""
    dates = pd.Series([day.date for day in design.days])
    return list(dates.groupby(dates.dt.to_period(freq)).max())


def _descriptor_frame(
    design: fx.DesignResult,
    look_ahead: pd.DataFrame,
    returns: pd.DataFrame,
) -> pd.DataFrame:
    """The descriptor artifact: month ends plus the final session.

    A daily long frame would be about fifteen million rows for no extra
    information, because every value is a deterministic function of the
    panel. Month ends plus the last cross-section is what the dashboard, the
    walkthrough and the research note read.
    """
    dates = [
        date for date in _period_ends(design, "M") if date in design.raw["size"].index
    ]
    if design.dates[-1] not in dates:
        dates.append(design.dates[-1])
    obs = design.raw.get("obs_count")
    rows: list[dict[str, object]] = []
    for name in fx.STYLE_NAMES:
        raw = design.raw[name]
        winsorized = design.winsorized.get(name, raw)
        pre = design.standard_pre.get(name, design.standardized[name])
        post = design.standardized[name]
        for date in dates:
            if date not in raw.index:
                continue
            for ticker in returns.columns:
                rows.append(
                    {
                        "date": date,
                        "ticker": ticker,
                        "descriptor": name,
                        "value_raw": (
                            float(raw.loc[date, ticker])
                            if pd.notna(raw.loc[date, ticker])
                            else np.nan
                        ),
                        "value_winsor": (
                            float(winsorized.loc[date, ticker])
                            if pd.notna(winsorized.loc[date, ticker])
                            else np.nan
                        ),
                        "value_z": (
                            float(pre.loc[date, ticker])
                            if pd.notna(pre.loc[date, ticker])
                            else np.nan
                        ),
                        "value_z_orth": (
                            float(post.loc[date, ticker])
                            if pd.notna(post.loc[date, ticker])
                            else np.nan
                        ),
                        "n_obs": (
                            float(obs.loc[date, ticker])
                            if obs is not None and pd.notna(obs.loc[date, ticker])
                            else np.nan
                        ),
                        "look_ahead": (
                            bool(look_ahead.loc[date, ticker])
                            if ticker in look_ahead.columns
                            and pd.notna(look_ahead.loc[date, ticker])
                            else False
                        ),
                    }
                )
    return pd.DataFrame(rows)


def _fmp_frame(design: fx.DesignResult, dates: list[pd.Timestamp]) -> pd.DataFrame:
    """Factor-mimicking weights at quarter ends, both weight sets.

    `unconstrained` is the object F3.2 tests: the rows of (X'WX)^-1 X'W, where
    X' w_FMP is exactly the unit vector. `identified` adds the adjustment that
    makes the cap-weighted sector returns sum to zero, which is the portfolio
    whose return is the reported factor return.
    """
    index = {day.date: day for day in design.days}
    rows: list[dict[str, object]] = []
    for date in dates:
        day = index.get(date)
        if day is None:
            continue
        fit = fx.wls_fit(day.design, day.returns, day.weights)
        weights = fx.sector_cap_weights(day)
        # estimated: the rows of (X'WX)^-1 X'W on the reduced design, where
        # X' w = I holds exactly. identified: the rows that reproduce the
        # reported factor returns, the reference sector included.
        transform = fx.identified_transform(weights)
        for kind, matrix, names in (
            ("estimated", fit.fmp_weights, list(fx.ESTIMATED_NAMES)),
            ("identified", transform @ fit.fmp_weights, list(design.factor_names)),
        ):
            for position, factor in enumerate(names):
                for ticker, value in zip(day.tickers, matrix[position], strict=True):
                    rows.append(
                        {
                            "date": date,
                            "factor": factor,
                            "ticker": ticker,
                            "weight": float(value),
                            "kind": kind,
                        }
                    )
    return pd.DataFrame(rows)


def _premia_frame(
    factor_wide: pd.DataFrame, subperiods: list[tuple[str, str | None, str | None]]
) -> pd.DataFrame:
    """Fama-MacBeth premia for the full sample and each subperiod."""
    tables: list[pd.DataFrame] = []
    for label, start, end in subperiods:
        window = factor_wide
        if start is not None:
            window = window.loc[start:]
        if end is not None:
            window = window.loc[:end]
        if window.empty:
            continue
        table = fx.fama_macbeth(window)
        table["period"] = label
        tables.append(table)
    return pd.concat(tables, ignore_index=True)


def _diagnostics(
    design: fx.DesignResult, xs_r2: pd.DataFrame, specific_wide: pd.DataFrame
) -> dict[str, object]:
    """The three diagnostics standing instruction B asks for.

    R squared by calendar year, by sector, and with the market factor alone
    against the full set. The market-only pass is the one refit; the other two
    read the stored fits. All three are computed here, while the design is in
    memory, and stored in the registry so the criterion can quote them without
    rebuilding the panel.
    """
    r_by_year = (
        xs_r2.assign(year=xs_r2["date"].dt.year)
        .groupby("year")["r_squared"]
        .mean()
        .round(6)
        .to_dict()
    )
    sector_values: dict[str, list[float]] = {sector: [] for sector in fx.SECTOR_NAMES}
    market_only: list[float] = []
    sectors_only: list[float] = []
    styles_only: list[float] = []
    n_styles = len(fx.STYLE_NAMES)
    for day in design.days:
        market_fit = fx.wls_fit(day.design[:, :1], day.returns, day.weights)
        market_only.append(market_fit.r_squared)
        sectors_only.append(
            fx.wls_fit(day.design[:, n_styles:], day.returns, day.weights).r_squared
        )
        styles_only.append(
            fx.wls_fit(day.design[:, :n_styles], day.returns, day.weights).r_squared
        )
        scale = day.weights / day.weights.mean()
        weighted_mean = float(np.average(day.returns, weights=scale))
        specific = (
            specific_wide.loc[day.date].reindex(day.tickers).to_numpy(dtype=float)
        )
        residual = specific**2 * scale
        spread = (day.returns - weighted_mean) ** 2 * scale
        for sector in fx.SECTOR_NAMES:
            mask = day.sector_names == sector
            total = float(spread[mask].sum())
            if total <= 0 or not np.isfinite(residual[mask]).any():
                continue
            sector_values[sector].append(
                1.0 - float(np.nan_to_num(residual[mask]).sum()) / total
            )
    by_sector = {
        sector: round(float(np.mean(values)), 6)
        for sector, values in sorted(sector_values.items())
        if values
    }
    return {
        "r_squared_by_year": {str(k): v for k, v in r_by_year.items()},
        # the market factor is the intercept in a cross-sectional model, so a
        # market-only fit explains no dispersion and its R squared is zero by
        # construction. The two informative comparisons are the sector block
        # alone and the style block alone.
        "r_squared_market_only_mean": round(float(np.mean(market_only)), 6),
        "r_squared_sectors_only_mean": round(float(np.mean(sectors_only)), 6),
        "r_squared_styles_only_mean": round(float(np.mean(styles_only)), 6),
        "r_squared_by_sector": by_sector,
    }


def _xs_parameters(
    *,
    design: fx.DesignResult,
    factor_returns: pd.DataFrame,
    xs_r2: pd.DataFrame,
    decomposition: pd.DataFrame,
    premia: pd.DataFrame,
    specific_month: pd.DataFrame,
    shares_long: pd.DataFrame,
    fmp: pd.DataFrame,
    artifacts_hash: str,
    start: str,
    end: str,
    diagnostics: dict[str, object] | None = None,
) -> dict[str, object]:
    """The registry parameter block for XS-v1."""
    factor_rows = decomposition.loc[decomposition["level"] == "factor"]
    return {
        "family": "fundamental",
        "assets": "equity",
        "universe_rule": (
            "sector-mapped panel names with a return and a complete descriptor row"
        ),
        "model_start": start,
        "model_end": end,
        "n_days": int(xs_r2.shape[0]),
        "n_factors": int(len(design.factor_names)),
        "descriptors": list(fx.STYLE_NAMES),
        "n_sectors": len(fx.SECTOR_NAMES),
        "sector_scheme": "gics",
        "sector_source": "processed/sectors.parquet",
        "identification": "cap_weighted_sector_factor_returns_sum_to_zero",
        "estimator": "wls",
        "weights": "sqrt_mcap",
        "winsorize": "3mad",
        "zscore_mean": "cap_weighted",
        "zscore_std": "equal_weighted",
        "orthogonalization": fx.DEFAULT_ORTHOGONALIZATION,
        "beta_source": "cap_weighted_universe_total_return",
        "beta_window": fx.BETA_WINDOW,
        "beta_min_obs": fx.BETA_MIN_OBS,
        "beta_shrinkage": "vasicek",
        "resid_vol_source": "one_factor_market_model_residual",
        "resid_vol_window": fx.RESID_VOL_WINDOW,
        "momentum_window": [fx.MOMENTUM_WINDOW, fx.MOMENTUM_SKIP],
        "reversal_window": fx.REVERSAL_WINDOW,
        "liquidity_window": fx.LIQUIDITY_WINDOW,
        "f_half_life": fx.F_HALF_LIFE,
        "n_lags": fx.NW_LAG,
        "d_half_life": fx.D_HALF_LIFE,
        "d_shrink": "sector_size",
        "d_shrink_k": fx.D_SHRINK_K,
        "min_names": fx.MIN_NAMES,
        "size_shares_source": "yfinance_get_shares_full",
        "size_shares_first_filed": str(
            pd.to_datetime(shares_long["date"]).min().date()
        ),
        "size_look_ahead": True,
        "size_look_ahead_note": (
            "the vendor share history starts to be filed in 2013-04 and is dense "
            "from 2015-10; earlier counts are backfilled from a name's first "
            "filing and are flagged per row in descriptors and market_cap"
        ),
        "n_names_mean": float(xs_r2["n_names"].mean()),
        "n_names_min": int(xs_r2["n_names"].min()),
        "r_squared_mean": float(xs_r2["r_squared"].mean()),
        "fmp_identity_max_abs_error": float(xs_r2["fmp_identity_max_abs_error"].max()),
        "sector_sum_max_abs": float(xs_r2["sector_cap_weighted_sum"].abs().max()),
        "n_days_below_300_names_e2_floor": int((xs_r2["n_names"] < 300).sum()),
        "mean_factor_share_seed_ew": float(
            factor_rows.loc[factor_rows["book"] == "seed_ew", "factor_variance"].mean()
            / float(
                factor_rows.loc[
                    factor_rows["book"] == "seed_ew", "total_variance"
                ].mean()
            )
        ),
        "n_premia_rows": int(premia.shape[0]),
        "n_unpriced": int((~premia["priced"].astype(bool)).sum()),
        "specific_var_dates": int(specific_month["date"].nunique()),
        "fmp_dates": int(fmp["date"].nunique()),
        "fmp_kinds": sorted(fmp["kind"].unique().tolist()),
        "artifacts_hash": artifacts_hash,
        **(diagnostics or {}),
    }


def build_e3_artifacts(
    data_root: Path = DATA_ROOT,
    verbose: bool = True,
) -> dict[str, object]:
    from efb import probes, registry, risk
    from efb.models import fundamental

    inputs = probes.load_panel(data_root)
    returns = inputs["returns"]
    close = inputs["close"]
    volume = inputs["volume"]
    sectors = inputs["sectors"]
    mapped = inputs["mapped"]
    shares = inputs["shares"]
    shares_long = inputs["shares_long"]
    membership = inputs["membership"]
    assert isinstance(returns, pd.DataFrame)
    assert isinstance(close, pd.DataFrame)
    assert isinstance(volume, pd.DataFrame)
    assert isinstance(sectors, pd.Series)
    assert isinstance(shares, pd.DataFrame)
    assert isinstance(shares_long, pd.DataFrame)
    assert isinstance(membership, pd.DataFrame)
    assert isinstance(mapped, list)

    raw_dir = data_root / "raw"
    processed_dir = data_root / "processed"
    xs_dir = data_root / "models" / "XS-v1"
    eval_dir = data_root / "eval"
    for directory in (raw_dir, processed_dir, xs_dir, eval_dir):
        directory.mkdir(parents=True, exist_ok=True)

    # 1. Share history, market cap. The union of the sector file and the panel
    # is asked for, not the sector file alone: the survivor-only measurement
    # needs a market cap for the members the sector file cannot reach, and a
    # name with no share count has no market cap at all.
    sector_frame = pd.read_parquet(processed_dir / "sectors.parquet")
    wanted = list(dict.fromkeys([*sector_frame["ticker"], *returns.columns]))
    history = probes.fetch_share_history(wanted)
    history.to_parquet(raw_dir / "shares_history.parquet", index=False)
    cap = fundamental.market_cap(close[mapped], shares[mapped])
    look_ahead = inputs["look_ahead"]
    assert isinstance(look_ahead, pd.DataFrame)
    market_cap_frame = pd.DataFrame(
        {
            "date": np.repeat(returns.index.to_numpy(), len(mapped)),
            "ticker": np.tile(np.array(mapped), len(returns.index)),
            "close": close[mapped].to_numpy().ravel(),
            "shares": shares[mapped].to_numpy().ravel(),
            "market_cap": cap.to_numpy().ravel(),
            "look_ahead": look_ahead[mapped].to_numpy().ravel(),
        }
    )
    as_of = shares_long.set_index(["date", "ticker"])["shares_as_of"]
    market_cap_frame["shares_as_of"] = as_of.reindex(
        pd.MultiIndex.from_arrays(
            [market_cap_frame["date"], market_cap_frame["ticker"]]
        )
    ).to_numpy()
    market_cap_frame = market_cap_frame[
        [
            "date",
            "ticker",
            "close",
            "shares",
            "shares_as_of",
            "market_cap",
            "look_ahead",
        ]
    ]
    market_cap_frame.to_parquet(processed_dir / "market_cap.parquet", index=False)

    # 2. Descriptors and the design
    proxy = fundamental.market_proxy(returns[mapped], cap)
    design = fundamental.build_design(
        returns=returns[mapped],
        close=close[mapped],
        volume=volume[mapped],
        market_cap=cap,
        sectors=sectors,
        proxy=proxy,
    )
    if not design.days:
        raise RuntimeError("no cross section cleared the minimum name count")
    descriptor_long = _descriptor_frame(design, look_ahead[mapped], returns[mapped])
    descriptor_long.to_parquet(xs_dir / "descriptors.parquet", index=False)

    # 3. Cross-sectional fits
    tables = fundamental.fit_panel(design)
    factor_returns = tables["factor_returns"]
    specific_returns = tables["specific_returns"]
    xs_r2 = tables["xs_r2"]
    factor_returns.to_parquet(xs_dir / "factor_returns.parquet", index=False)
    specific_returns.to_parquet(xs_dir / "specific_returns.parquet", index=False)
    xs_r2.to_parquet(xs_dir / "xs_r2.parquet", index=False)

    factor_wide = (
        factor_returns.pivot(index="date", columns="factor", values="f")
        .reindex(columns=list(fundamental.FACTOR_NAMES))
        .dropna()
    )
    specific_wide = specific_returns.pivot(
        index="date", columns="ticker", values="specific_return"
    )

    # 4. Factor-mimicking portfolios at quarter ends
    month_ends = _period_ends(design, "Q")
    fmp = _fmp_frame(design, month_ends)
    fmp.to_parquet(xs_dir / "fmp_weights.parquet", index=False)

    # 5. Covariance and specific variance
    factor_cov = fundamental.ewma_factor_cov(factor_wide, half_life=fx.F_HALF_LIFE)
    factor_cov.to_parquet(xs_dir / "factor_cov.parquet")
    specific_long = fundamental.specific_variance(
        specific_wide, sectors, cap, half_life=fx.D_HALF_LIFE, shrink_k=fx.D_SHRINK_K
    )
    specific_month = specific_long.loc[
        specific_long["date"].isin(_period_ends(design, "M"))
    ]
    specific_month.to_parquet(xs_dir / "specific_var.parquet", index=False)

    # 6. Fama-MacBeth premia, full sample and the three subperiods
    premia = _premia_frame(factor_wide, subperiods=SUBPERIODS)
    premia.to_parquet(eval_dir / "xs_fm_premia.parquet", index=False)

    # 7. Risk decomposition, bias, exposure timing, realized residual risk
    days = {day.date: day for day in design.days}
    portfolios = data_root / "portfolios"
    specific_by_date = {
        date: group.set_index("ticker")["specific_var"]
        for date, group in specific_month.groupby("date")
    }
    decomposition_rows: list[pd.DataFrame] = []
    bias_rows: list[pd.DataFrame] = []
    exposure_rows: list[pd.DataFrame] = []
    residual_rows: list[dict[str, object]] = []
    books = {
        "seed_ew": portfolios / "seed_ew.parquet",
        "seed_mom_ls": portfolios / "seed_mom_ls.parquet",
    }
    month_list = [d for d in _period_ends(design, "M") if d in days]
    for book, path in books.items():
        book_frame = pd.read_parquet(path)
        weights_by_date: dict[pd.Timestamp, pd.Series] = {}
        for date in month_list:
            rows = book_frame.loc[book_frame["date"] == date]
            if rows.empty:
                continue
            weights_by_date[date] = rows.set_index("ticker")["weight"].astype(float)
        exposure_rows.append(
            risk.exposure_series(
                days, weights_by_date, list(fundamental.FACTOR_NAMES), book=book
            )
        )
        bias = risk.segment_bias(
            days,
            weights_by_date,
            specific_month,
            factor_wide,
            returns[mapped],
            start="2015-01-01",
        )
        bias["book"] = book
        bias_rows.append(bias)
        for date, weights in weights_by_date.items():
            day = days[date]
            history = factor_wide.loc[:date]
            if len(history) < fx.F_HALF_LIFE:
                continue
            covariance = fundamental.ewma_factor_cov(history, half_life=fx.F_HALF_LIFE)
            specific = specific_by_date.get(date)
            if specific is None:
                continue
            result = risk.decompose(book, date, weights, day, covariance, specific)
            decomposition_rows.append(risk.decomposition_frame(result))
            if date >= pd.Timestamp("2015-01-01"):
                realized_cov = risk.realized_residual_covariance(
                    specific_wide, date, window=252
                )
                if not realized_cov.empty:
                    realized_idio = risk.realized_idio_variance(weights, realized_cov)
                    residual_rows.append(
                        {
                            "book": book,
                            "window_end": date,
                            "factor_share_diagonal": 1.0
                            - result.idio_variance / result.total_variance,
                            "factor_share_realized": 1.0
                            - realized_idio / result.total_variance,
                            "total_variance": result.total_variance,
                            "factor_variance_diagonal": result.factor_variance,
                            "idio_variance_diagonal": result.idio_variance,
                            "idio_variance_realized": realized_idio,
                            "n_names_covariance": int(realized_cov.shape[0]),
                        }
                    )
    decomposition = pd.concat(decomposition_rows, ignore_index=True)
    decomposition.to_parquet(eval_dir / "xs_risk_decomposition.parquet", index=False)
    bias_frame = pd.concat(bias_rows, ignore_index=True)
    bias_frame.to_parquet(eval_dir / "xs_bias.parquet", index=False)
    exposure_frame = pd.concat(exposure_rows, ignore_index=True)
    exposure_frame.to_parquet(eval_dir / "xs_exposure_timeseries.parquet", index=False)
    residual_frame = pd.DataFrame(residual_rows)
    residual_frame.to_parquet(eval_dir / "xs_residual_covariance.parquet", index=False)

    # 7b. The three tables the walkthrough's E3 close-out reads: the bias by the
    # book's own exposure, the bias beside the model's coverage, and the
    # survivor-only restriction as a stored frame rather than prose
    risk.bias_by_exposure(bias_frame, exposure_frame).to_parquet(
        eval_dir / "xs_bias_by_exposure.parquet", index=False
    )
    risk.coverage_by_year(bias_frame, decomposition).to_parquet(
        eval_dir / "xs_coverage_by_year.parquet", index=False
    )
    probes.members_outside_sector_file(
        membership, set(mapped), market_cap=(close * shares).shift(1)
    ).to_parquet(eval_dir / "xs_survivor_restriction.parquet", index=False)

    # 8. Registry entry, hashed after the artifacts exist
    artifacts_hash = combined_hash(
        {
            rel: {"sha256": hash_file(data_root / rel)}
            for rel in E3_ARTIFACTS
            if rel != "models/registry.json" and (data_root / rel).exists()
        }
    )
    parameters = _xs_parameters(
        design=design,
        factor_returns=factor_wide,
        xs_r2=xs_r2,
        decomposition=decomposition,
        premia=premia,
        specific_month=specific_month,
        shares_long=shares_long,
        fmp=fmp,
        artifacts_hash=artifacts_hash,
        start=str(xs_r2["date"].min().date()),
        end=str(xs_r2["date"].max().date()),
        diagnostics={
            **_diagnostics(design, xs_r2, specific_wide),
            **fx.shift_test(design),
        },
    )
    entry = registry.model_entry(
        version="XS-v1",
        family="fundamental",
        parameters=parameters,
        universe_path=processed_dir / "universe_membership.parquet",
        data_paths=[processed_dir / "returns.parquet", xs_dir / "descriptors.parquet"],
        walkthrough="notebooks/E3_walkthrough.html",
        deliverable="docs/research/E3_factor_model_note.md",
        results="sprints/E3/RESULTS.json",
        champion=False,
        eligible_for_champion=True,
    )
    registry.write_registry(data_root / "models" / "registry.json", entry)
    if verbose:
        print(
            json.dumps(
                {
                    "xs_start": parameters["model_start"],
                    "n_days": parameters["n_days"],
                    "mean_r_squared": parameters["r_squared_mean"],
                    "n_factors": parameters["n_factors"],
                },
                indent=2,
            )
        )
    return {
        "days": len(design.days),
        "factor_returns": factor_wide.shape,
        "specific_returns": specific_wide.shape,
        "decomposition_rows": len(decomposition),
        "residual_rows": len(residual_frame),
        "artifacts_hash": artifacts_hash,
        "parameters": parameters,
    }


def rebuild_e3(
    data_root: Path = DATA_ROOT,
    results_path: Path | None = None,
    full: bool = False,
) -> dict[str, object]:
    """Run the E3 build and version everything.

    With `full` the E1 and E2 legs run first, which is what `make rebuild`
    does and what gate G1 names as one command from raw parquet to the
    dashboard. Without it, as `make rebuild-e3` runs it, the E1 and E2
    artifacts are read from disk and only XS-v1 is rebuilt, which is the path
    the sprint iterates on.
    """
    e1: dict[str, object] | None = None
    e2: dict[str, object] | None = None
    if full:
        e1 = rebuild(data_root=data_root, start="2010-01-04", results_path=None)
        e2 = build_e2_artifacts(data_root=data_root, start=MODEL_START)
    e3 = build_e3_artifacts(data_root=data_root)
    artifact_paths = [
        data_root / rel for rel in ARTIFACTS + E2_ARTIFACTS + E3_ARTIFACTS
    ]
    version_path = data_root / "VERSION.json"
    old_hash = previous_data_hash(version_path)
    payload = write_version(
        artifact_paths,
        version_path,
        note=(
            "Built by make rebuild (Sprint E3). E1, E2 and E3 artifacts, each "
            "with a content hash; the dashboard sidebar shows this version."
        ),
    )
    if results_path is not None:
        from efb import evaluate

        inputs = evaluate.compute_e3_from_artifacts(data_root=data_root)
        criteria = evaluate.evaluate_e3_criteria(**inputs)
        evaluate.write_results(
            criteria,
            results_path,
            sprint="E3",
            data_hash=payload["data_hash"],
            previous_data_hash=old_hash,
        )
    return {
        "n_steps": 8,
        "full": full,
        "e1_tickers": (e1 or {}).get("n_tickers"),
        "e2": e2,
        "e3": e3,
        "version": payload,
    }


def build_pca_v1(
    data_root: Path = DATA_ROOT,
    store: bool = True,
    verbose: bool = True,
) -> dict[str, object]:
    """Sprint E4, Task 1: fit PCA-v1, store it, register it, and price F4.1 and F4.4.

    Two fits: the model universe, which becomes PCA-v1, and the wider panel,
    which is stored as a robustness spectrum. The registration writes the entry
    through `efb.registry` so the champion rule is carried rather than retyped.
    """
    from efb import registry
    from efb.models import statistical

    root = Path(data_root)
    returns = pd.read_parquet(root / "processed" / "returns.parquet")
    specific = pd.read_parquet(root / "models" / "XS-v1" / "specific_returns.parquet")
    sectors = pd.read_parquet(root / "processed" / "sectors.parquet")
    factor_returns = pd.read_parquet(root / "models" / "XS-v1" / "factor_returns.parquet")
    xs_r2 = pd.read_parquet(root / "models" / "XS-v1" / "xs_r2.parquet")
    as_of = pd.Timestamp("2026-09-03")
    mapped = list(sectors["ticker"])

    model = statistical.run(
        returns, specific, as_of=as_of, tickers=mapped, label="pca"
    )
    panel = statistical.run(
        returns, None, as_of=as_of, label="pca_panel", with_residuals=False
    )
    counts = model["diagnostics"]["total"]
    panel_counts = panel["diagnostics"]["total"]
    residual = model.get("residual_diagnostics", {})

    factor_frame = model["factor_returns"]
    first = factor_frame.loc[factor_frame["factor"] == "pca_01"].set_index("date")["f"]
    market = (
        factor_returns.loc[factor_returns["factor"] == "market"]
        .set_index("date")["f"]
        .sort_index()
    )
    joined = pd.concat([first, market], axis=1, join="inner").dropna()
    f4_1 = float(joined.iloc[:, 0].corr(joined.iloc[:, 1]))

    # F4.4: the held-out cross-sectional test. PCA loadings are fitted on the
    # training window and held fixed; the test regresses each held-out day's
    # cross-section on those loadings and compares with XS-v1's stored R
    # squared over the same days.
    train_end = pd.Timestamp("2024-08-30")
    wide = statistical.clean_wide(returns)
    wide = wide[[column for column in wide.columns if column in set(mapped)]]
    train = statistical.complete_block(wide, as_of=train_end, window=statistical.PCA_WINDOW)
    train_fit = statistical.fit(train)
    k_held = max(statistical.count_mp(train_fit), 1)
    loadings = pd.DataFrame(train_fit.loadings(k_held), index=train_fit.tickers)
    held_days = [date for date in wide.loc[train_end:].index if date > train_end]
    scores: list[float] = []
    for date in held_days:
        row = wide.loc[date].dropna()
        names = [name for name in row.index if name in loadings.index]
        if len(names) < 50:
            continue
        design = np.column_stack(
            [np.ones(len(names)), loadings.loc[names].to_numpy(dtype=float)]
        )
        target = row[names].to_numpy(dtype=float)
        fitted, *_ = np.linalg.lstsq(design, target, rcond=None)
        residual_values = target - design @ fitted
        total = float(((target - target.mean()) ** 2).sum())
        if total <= 0:
            continue
        scores.append(1.0 - float((residual_values**2).sum()) / total)
    r2_pca = float(np.mean(scores)) if scores else float("nan")
    xs_block = xs_r2.loc[(xs_r2["date"] > train_end) & (xs_r2["date"].isin(held_days))]
    r2_xs = float(xs_block["r_squared"].mean()) if len(xs_block) else float("nan")

    if verbose:
        print("### E4 Task 1: PCA-v1")
        print(f"model universe: N {model['diagnostics']['fit'].n_names}, "
              f"T {model['diagnostics']['fit'].n_days}, N/T {counts.n_over_t:.4f}, "
              f"MP edge {counts.edge:.4f}")
        print(f"factor counts: scree {counts.scree}, MP {counts.marchenko_pastur}, "
              f"cross-validated {counts.cross_validated}, selected {counts.selected}")
        print(f"panel robustness: N {panel['diagnostics']['fit'].n_names}, "
              f"N/T {panel_counts.n_over_t:.4f}, MP {panel_counts.marchenko_pastur}")
        if residual:
            print(f"residual PCA: largest {residual['largest_eigenvalue']:.4f} against "
                  f"edge {residual['edge']:.4f}, above edge {residual['above_edge']}, "
                  f"count above edge {residual['counts'].marchenko_pastur}")
        print(f"F4.1 first PC vs market: {f4_1:.4f} on {len(joined)} days")
        print(f"F4.4 held-out R squared: PCA {r2_pca:.4f} against XS-v1 {r2_xs:.4f} "
              f"over {len(scores)} days, k {k_held}")

    frames: dict[str, object] = {
        "f4_1_first_pc_vs_market": f4_1,
        "f4_4_pca_held_out_r_squared": r2_pca,
        "f4_4_xs_v1_held_out_r_squared": r2_xs,
        "f4_4_k": k_held,
        "f4_4_held_out_days": len(scores),
        "counts": counts,
        "panel_counts": panel_counts,
        "residual": residual,
        "loadings": model["loadings"],
        "factor_returns": factor_frame,
        "eigenvalues": model["spectrum"],
        "residual_spectrum": model.get("residual_spectrum"),
        "panel_spectrum": panel["spectrum"],
        "residual_loadings": model.get("residual_loadings"),
    }

    if store:
        target_dir = root / "models" / "PCA-v1"
        target_dir.mkdir(parents=True, exist_ok=True)
        model["loadings"].to_parquet(target_dir / "loadings.parquet", index=False)
        factor_frame.to_parquet(target_dir / "factor_returns.parquet", index=False)
        model["spectrum"].to_parquet(target_dir / "eigenvalues.parquet", index=False)
        panel["spectrum"].to_parquet(target_dir / "eigenvalues_panel.parquet", index=False)
        if model.get("residual_spectrum") is not None:
            model["residual_spectrum"].to_parquet(
                root / "eval" / "xs_residual_spectrum.parquet", index=False
            )
        if model.get("residual_loadings") is not None:
            model["residual_loadings"].to_parquet(
                root / "eval" / "xs_residual_loadings.parquet", index=False
            )
        entry = registry.model_entry(
            version="PCA-v1",
            family="statistical",
            parameters={
                "family": "statistical",
                "estimator": "principal component analysis on the correlation matrix",
                "window": statistical.PCA_WINDOW,
                "n_names": model["diagnostics"]["fit"].n_names,
                "n_days": model["diagnostics"]["fit"].n_days,
                "n_over_t": counts.n_over_t,
                "mp_edge": counts.edge,
                "n_factors": counts.selected,
                "n_factors_scree": counts.scree,
                "n_factors_mp": counts.marchenko_pastur,
                "n_factors_cv": counts.cross_validated,
                "rotation": "varimax",
                "residual_pca_largest_eigenvalue": float(
                    residual.get("largest_eigenvalue", float("nan"))
                ),
                "residual_pca_edge": float(residual.get("edge", float("nan"))),
                "residual_pca_above_edge": bool(residual.get("above_edge", False)),
            },
            universe_path=root / "processed" / "universe_membership.parquet",
            data_paths=[root / "processed" / "returns.parquet", root / "processed" / "sectors.parquet"],
            champion=False,
            eligible_for_champion=True,
            walkthrough="notebooks/E4_walkthrough.html",
            deliverable="docs/research/E4_covariance_memo.md",
            results="sprints/E4/RESULTS.json",
        )
        registry.write_registry(root / "models" / "registry.json", entry)
        frames["registry_entry"] = entry
    return frames


def main() -> None:
    if "--all" in sys.argv:
        summary = rebuild_e3(
            results_path=ROOT / "sprints" / "E3" / "RESULTS.json", full=True
        )
    elif "--e3" in sys.argv:
        summary = rebuild_e3(results_path=ROOT / "sprints" / "E3" / "RESULTS.json")
    elif "--e2" in sys.argv:
        summary = rebuild_e2(results_path=ROOT / "sprints" / "E2" / "RESULTS.json")
    else:
        summary = rebuild(results_path=ROOT / "sprints" / "E1" / "RESULTS.json")
    print(json.dumps({"n_steps": summary["n_steps"]}, indent=2))


if __name__ == "__main__":
    main()
