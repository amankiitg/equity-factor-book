"""Sprint E8: sizing and portfolio construction on synthetic alpha.

Every input here is synthetic and labeled: z(i,t) = rho *
standardized(e(i,t+h)) + sqrt(1 - rho^2) * eps(i,t), where e is the XS-v1
specific return over the forward horizon. It uses future data deliberately,
so it is a controlled experiment, never a backtest, and no synthetic number
is placed beside a real-signal number without the label.

The constructions all read the same inputs: alpha through the E7 contract
alpha_i = IC * sigma_idio_i * z_i shrunk by kappa, the champion design X,
factor covariance F and specific variance D. The fundamental-law transfer
coefficient table (F8.5) is the decision-relevant output.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from efb import alpha as alpha_mod
from efb import eval_risk, hedge, race

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"

RHOS = (0.02, 0.05, 0.10)
SEEDS = (0, 1, 2, 3, 4)
HORIZON = 21  # h, the alpha's forward horizon in sessions
TARGET_ANNUAL_VOL = 0.10
TARGET_VOL = TARGET_ANNUAL_VOL * np.sqrt(HORIZON / 252.0)  # per-rebalance
KAPPA = alpha_mod.KAPPA
CONSTRUCTIONS = (
    "proportional",
    "sharpe",
    "procedure_6_3",
    "mv_unconstrained",
    "mv_constrained",
    "combined",
    "shrunk",
)
LONG_SHORT_FAMILY = "long_short"


def _forward_specific(
    specific_wide: pd.DataFrame, date: pd.Timestamp, names: list[str]
) -> np.ndarray:
    """The realized specific return of each name over the h sessions after `date`."""
    block = specific_wide.loc[specific_wide.index > date].iloc[:HORIZON]
    if len(block) < HORIZON:
        return np.full(len(names), np.nan)
    sub = block.reindex(columns=names).to_numpy(dtype=float)
    with np.errstate(invalid="ignore"):
        return np.prod(1.0 + sub, axis=0) - 1.0


def _standardize(values: np.ndarray) -> np.ndarray:
    """The cross-sectional z-score, NaN kept where the input is NaN."""
    finite = np.isfinite(values)
    out = np.full(values.shape, np.nan)
    if finite.sum() < 10:
        return out
    mean = float(np.nanmean(values))
    std = float(np.nanstd(values))
    if std <= 0:
        return out
    out[finite] = (values[finite] - mean) / std
    return out


def date_pieces(
    data_root: Path = DATA_ROOT,
) -> dict[pd.Timestamp, dict[str, np.ndarray]]:
    """The champion design, factor covariance and specific variance per grid date.

    These depend only on the date, not on the rho, seed or construction, so
    the whole experiment shares one computation per date.
    """
    root = Path(data_root)
    wide, _counts = eval_risk.load_clean_wide(root)
    grid = race.race_grid(root)
    pieces: dict[pd.Timestamp, dict[str, np.ndarray]] = {}
    for date in grid:
        names = eval_risk._window_names(wide, date)
        if len(names) < 50:
            continue
        supplied = eval_risk._xs_pieces(date, names, root)
        if supplied is None:
            continue
        pieces[pd.Timestamp(date)] = {
            "names": np.asarray(names),
            "design": supplied["design"],
            "factor_covariance": supplied["factor_covariance"],
            "specific": supplied["specific"],
            "sigma": np.sqrt(np.maximum(supplied["specific"], 1e-12)),
        }
    return pieces


def synthetic_alpha(
    data_root: Path = DATA_ROOT,
    rho: float = 0.05,
    seed: int = 0,
    pieces: dict[pd.Timestamp, dict[str, np.ndarray]] | None = None,
) -> pd.DataFrame:
    """The synthetic alpha over the E5 race grid, one row per name per date.

    OUTPUT columns: date, ticker, z, e_h, sigma_idio, alpha, rho, seed, ic.
    The label `source = synthetic controlled experiment` travels in the
    frame so no consumer mistakes it for a real signal.
    """
    root = Path(data_root)
    grid = race.race_grid(root)
    pieces = pieces if pieces is not None else date_pieces(root)
    specific = pd.read_parquet(root / "models" / "XS-v1" / "specific_returns.parquet")
    specific["date"] = pd.to_datetime(specific["date"])
    specific_wide = specific.pivot(
        index="date", columns="ticker", values="specific_return"
    )
    rng = np.random.default_rng(seed)
    rows: list[pd.DataFrame] = []
    for date in grid:
        if date not in pieces:
            continue
        names = list(pieces[date]["names"])
        sigma = pieces[date]["sigma"]
        e_h = _forward_specific(specific_wide, date, names)
        finite = np.isfinite(e_h)
        z = np.full(len(names), np.nan)
        z[finite] = rho * _standardize(e_h[finite]) + np.sqrt(
            1.0 - rho**2
        ) * rng.normal(size=int(finite.sum()))
        alpha = rho * sigma * z * KAPPA
        rows.append(
            pd.DataFrame(
                {
                    "date": date,
                    "ticker": names,
                    "z": z,
                    "e_h": e_h,
                    "sigma_idio": sigma,
                    "alpha": alpha,
                    "rho": rho,
                    "seed": seed,
                    "ic": np.nan,
                    "source": "synthetic controlled experiment",
                }
            )
        )
    if not rows:
        return pd.DataFrame(
            columns=[
                "date",
                "ticker",
                "z",
                "e_h",
                "sigma_idio",
                "alpha",
                "rho",
                "seed",
                "ic",
                "source",
            ]
        )
    frame = pd.concat(rows, ignore_index=True)
    # the measured cross-sectional IC of z against the forward specific
    # return, stored per date so the known IC is checked, not assumed
    ics: dict[pd.Timestamp, float] = {}
    for date, group in frame.groupby("date"):
        both = group[["z", "e_h"]].dropna()
        if len(both) < 10:
            continue
        ics[pd.Timestamp(date)] = float(both["z"].rank().corr(both["e_h"].rank()))
    frame["ic"] = frame["date"].map(ics)
    return frame


def _assembled(
    date: pd.Timestamp, names: list[str], supplied: dict[str, np.ndarray]
) -> dict[str, np.ndarray]:
    """The inputs a construction reads on one date."""
    return {
        "design": supplied["design"],
        "factor_covariance": supplied["factor_covariance"],
        "specific": supplied["specific"],
        "sigma": np.sqrt(np.maximum(supplied["specific"], 1e-12)),
    }


def _sigma_inverse_alpha(
    alpha: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
) -> np.ndarray:
    """Sigma^-1 alpha by Woodbury with Sigma = X F X' + D, factor-neutral alpha."""
    d_inv = 1.0 / np.maximum(specific, 1e-12)
    u = d_inv * alpha
    xd = design * d_inv[:, None]
    inner = np.linalg.inv(factor_covariance) + design.T @ xd
    v = np.linalg.solve(inner, design.T @ u)
    return u - d_inv * (design @ v)


def _decompose(
    weights: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
) -> dict[str, float]:
    """The book's factor and idio variance split and its factor exposures."""
    factor_var = float(weights @ design @ factor_covariance @ design.T @ weights)
    idio_var = float(weights @ (specific * weights))
    total = factor_var + idio_var
    return {
        "factor_variance": factor_var,
        "idio_variance": idio_var,
        "idio_share": idio_var / total if total > 0 else float("nan"),
        "gross": float(np.abs(weights).sum()),
        "net": float(weights.sum()),
        "n_eff": (
            float(np.abs(weights).sum() ** 2 / (weights**2).sum())
            if (weights**2).sum() > 0
            else 0.0
        ),
    }


def _vol_target(
    weights: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
) -> np.ndarray:
    """Scale the weights so the book's ex-ante volatility equals the target."""
    var = float(weights @ design @ factor_covariance @ design.T @ weights) + float(
        weights @ (specific * weights)
    )
    if not np.isfinite(var) or var <= 0:
        return weights
    return weights * (TARGET_VOL / np.sqrt(var))


def proportional(alpha: np.ndarray, specific: np.ndarray) -> np.ndarray:
    """w proportional to alpha / sigma^2."""
    denom = np.maximum(specific, 1e-12)
    return alpha / denom


def sharpe_rule(alpha: np.ndarray, specific: np.ndarray) -> np.ndarray:
    """w proportional to SR / sigma with SR = alpha / sigma."""
    denom = np.maximum(specific, 1e-12)
    return alpha / denom


def procedure_6_3(
    alpha: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
) -> np.ndarray:
    """Size on D^-1 alpha, then hedge factors with the exact in-model FMPs."""
    sized = proportional(alpha, specific)
    exposures = design.T @ sized
    hedge_weights, _names = hedge.fmp_hedge_exact(design, exposures)
    return sized + hedge_weights


def shrunk(alpha: np.ndarray, specific: np.ndarray, lam: float) -> np.ndarray:
    """w proportional to alpha / (sigma^2 + lambda), the ridge shrinkage."""
    denom = np.maximum(specific, 1e-12) + lam
    return alpha / denom


def _resample_dispersion(
    alpha: np.ndarray,
    specific: np.ndarray,
    e_std: np.ndarray,
    rho: float,
    rng: np.random.Generator,
    lam: float = 0.0,
) -> float:
    """The mean absolute weight change under one IC-consistent redraw."""
    finite = np.isfinite(alpha) & np.isfinite(specific) & np.isfinite(e_std)
    if finite.sum() < 10:
        return 0.0
    alpha = alpha[finite]
    specific = specific[finite]
    e_std = e_std[finite]
    z_resampled = rho * e_std + np.sqrt(1.0 - rho**2) * rng.normal(size=len(alpha))
    sigma = np.sqrt(np.maximum(specific, 1e-12))
    alpha_new = rho * sigma * z_resampled * KAPPA
    before = shrunk(alpha, specific, lam) if lam else proportional(alpha, specific)
    after = (
        shrunk(alpha_new, specific, lam) if lam else proportional(alpha_new, specific)
    )
    scale_before = np.abs(before).mean()
    if not np.isfinite(scale_before) or scale_before <= 0:
        return 0.0
    return float(np.abs(before - after).mean() / scale_before)


def _realized_returns(
    weights_wide: pd.DataFrame, alpha_frame: pd.DataFrame
) -> pd.Series:
    """The per-rebalance realized return w' e_h, aligned on dates."""
    e_wide = alpha_frame.pivot_table(index="date", columns="ticker", values="e_h")
    common = weights_wide.index.intersection(e_wide.index)
    values: list[float] = []
    for date in common:
        w = weights_wide.loc[date].reindex(e_wide.columns).to_numpy(dtype=float)
        e = e_wide.loc[date].reindex(e_wide.columns).to_numpy(dtype=float)
        both = np.isfinite(w) & np.isfinite(e)
        values.append(float((w[both] * e[both]).sum()))
    return pd.Series(values, index=common)


def construct(
    alpha_frame: pd.DataFrame,
    construction: str,
    data_root: Path = DATA_ROOT,
    lam: float = 0.0,
    corr: float = 0.0,
    other_alpha: pd.DataFrame | None = None,
    pieces: dict[pd.Timestamp, dict[str, np.ndarray]] | None = None,
) -> pd.DataFrame:
    """Run one construction over every date of the alpha frame.

    OUTPUT: a long frame of per-date weights with the decomposition columns.
    """
    root = Path(data_root)
    pieces = pieces if pieces is not None else date_pieces(root)
    rows: list[dict[str, object]] = []
    for date, group in alpha_frame.groupby("date"):
        if date not in pieces:
            continue
        names = list(pieces[date]["names"])
        design = pieces[date]["design"]
        factor_covariance = pieces[date]["factor_covariance"]
        specific = pieces[date]["specific"]
        alpha = group.set_index("ticker")["alpha"].reindex(names).to_numpy(dtype=float)
        if construction == "combined" and other_alpha is not None:
            # two synthetic signals on the same truth carry the same IC, so
            # the IC-weighted combination is the plain sum, and their known
            # cross-correlation is rho^2, stored for the walkthrough
            other = (
                other_alpha.loc[other_alpha["date"] == date]
                .set_index("ticker")["alpha"]
                .reindex(names)
                .to_numpy(dtype=float)
            )
            alpha = alpha + other
        if construction in ("proportional", "sharpe"):
            raw = proportional(alpha, specific)
        elif construction == "procedure_6_3":
            raw = procedure_6_3(alpha, design, factor_covariance, specific)
        elif construction == "mv_unconstrained":
            raw = _sigma_inverse_alpha(alpha, design, factor_covariance, specific)
        elif construction == "mv_constrained":
            from efb import optimize

            raw = optimize.constrained_mv(
                alpha, design, factor_covariance, specific, date, names, root
            )
        elif construction == "shrunk":
            raw = shrunk(alpha, specific, lam)
        else:
            raw = proportional(alpha, specific)
        if construction == "mv_constrained":
            # the QP's risk aversion already sets the scale; vol targeting
            # after the fact would scale the constrained solution straight
            # through the gross and position caps
            weights = raw
        else:
            weights = _vol_target(raw, design, factor_covariance, specific)
        decomposition = _decompose(weights, design, factor_covariance, specific)
        # the FMP-hedged book: the exposure the exact in-model FMPs remove
        # and the idio share that is left, the number F8.2 and F8.6 score
        exposures = design.T @ weights
        hedge_weights, _hedge_names = hedge.fmp_hedge_exact(design, exposures)
        hedged = weights + hedge_weights
        hedged_decomposition = _decompose(hedged, design, factor_covariance, specific)
        max_violation = 0.0
        if construction == "mv_constrained":
            from efb import optimize

            violations = optimize.constraint_violations(
                weights, design, date, names, root
            )
            max_violation = float(max(violations.values()))
        for ticker, weight in zip(names, weights, strict=True):
            rows.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "weight": float(weight) if np.isfinite(weight) else np.nan,
                    "construction": construction,
                    "rho": group["rho"].iloc[0],
                    "seed": group["seed"].iloc[0],
                    "idio_share_after_fmp": hedged_decomposition["idio_share"],
                    "max_violation": max_violation,
                    **decomposition,
                }
            )
        del alpha, raw, weights, design, factor_covariance, specific
    return pd.DataFrame(rows)


def store_realized_ic(data_root: Path = DATA_ROOT, store: bool = True) -> pd.DataFrame:
    """The measured cross-sectional IC of each synthetic seed, per rho.

    The measured IC differs from the nominal rho by sampling error, most at
    rho 0.02. F8.5 uses this realized IC, not the nominal rho.
    """
    root = Path(data_root)
    pieces = date_pieces(root)
    rows: list[dict[str, object]] = []
    for rho in RHOS:
        for seed in SEEDS:
            frame = synthetic_alpha(root, rho, seed, pieces=pieces)
            measured = float(frame.groupby("date")["ic"].mean().mean())
            rows.append({"rho": rho, "seed": seed, "realized_ic": measured})
    out = pd.DataFrame(rows)
    if store:
        out.to_parquet(root / "portfolios" / "e8_realized_ic.parquet", index=False)
    return out


def store_neff(data_root: Path = DATA_ROOT, store: bool = True) -> pd.DataFrame:
    """The effective breadth per rebalance date.

    N_eff is the participation ratio of the XS-v1 specific-return
    correlation matrix over the trailing 504-session window:
    (sum of eigenvalues)^2 / (sum of squared eigenvalues). E4 measured
    strong residual co-movement, so N_eff sits well below the name count.
    """
    root = Path(data_root)
    wide, _counts = eval_risk.load_clean_wide(root)
    grid = race.race_grid(root)
    specific = pd.read_parquet(root / "models" / "XS-v1" / "specific_returns.parquet")
    specific["date"] = pd.to_datetime(specific["date"])
    specific_wide = specific.pivot(
        index="date", columns="ticker", values="specific_return"
    )
    rows: list[dict[str, object]] = []
    for date in grid:
        names = eval_risk._window_names(wide, date)
        if len(names) < 50:
            continue
        window = specific_wide.loc[:date].iloc[-504:].reindex(columns=names)
        window = window.dropna(axis=1, how="any")
        if window.shape[1] < 50:
            continue
        correlation = np.corrcoef(window.to_numpy(dtype=float).T)
        eigenvalues = np.linalg.eigvalsh(correlation)
        eigenvalues = np.clip(eigenvalues, 0.0, None)
        total = float(eigenvalues.sum())
        n_eff = float(total**2 / (eigenvalues**2).sum()) if total > 0 else 0.0
        rows.append(
            {
                "date": pd.Timestamp(date),
                "n_names": int(window.shape[1]),
                "n_eff": n_eff,
                "largest_eigenvalue": float(eigenvalues.max()),
            }
        )
    out = pd.DataFrame(rows)
    if store:
        out.to_parquet(root / "portfolios" / "e8_neff.parquet", index=False)
    return out


def run(
    data_root: Path = DATA_ROOT,
    store: bool = True,
    constructions: tuple[str, ...] = CONSTRUCTIONS,
) -> dict[str, object]:
    """The full E8 experiment: every rho, seed and construction over the grid."""
    root = Path(data_root)
    pieces = date_pieces(root)
    alpha_frames: dict[tuple[float, int], pd.DataFrame] = {}
    for rho in RHOS:
        for seed in SEEDS:
            print(f"synthetic alpha rho={rho} seed={seed}")
            alpha_frames[(rho, seed)] = synthetic_alpha(root, rho, seed, pieces=pieces)
    all_rows: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []
    for rho in RHOS:
        for seed in SEEDS:
            frame = alpha_frames[(rho, seed)]
            for construction in constructions:
                print(f"  {construction} rho={rho} seed={seed}")
                built = construct(
                    frame,
                    construction,
                    root,
                    lam=0.0,
                    corr=0.5,
                    other_alpha=(
                        alpha_frames[(rho, (seed + 1) % len(SEEDS))]
                        if construction == "combined"
                        else None
                    ),
                    pieces=pieces,
                )
                if built.empty:
                    continue
                all_rows.append(built)
                weights_wide = built.pivot_table(
                    index="date", columns="ticker", values="weight"
                )
                realized = _realized_returns(weights_wide, frame)
                ir = (
                    float(realized.mean() / realized.std(ddof=1))
                    if len(realized) > 10 and realized.std(ddof=1) > 0
                    else float("nan")
                )
                summary_rows.append(
                    {
                        "construction": construction,
                        "rho": rho,
                        "seed": seed,
                        "n_dates": int(weights_wide.shape[0]),
                        "realized_ir": ir,
                        "mean_idio_share": float(built["idio_share"].mean()),
                        "mean_idio_share_after_fmp": float(
                            built["idio_share_after_fmp"].mean()
                        ),
                        "mean_n_eff": float(built["n_eff"].mean()),
                        "mean_gross": float(built["gross"].mean()),
                        "max_violation": float(
                            built["max_violation"].max()
                            if "max_violation" in built.columns
                            else 0.0
                        ),
                    }
                )
    weights = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
    summary = pd.DataFrame(summary_rows)
    if store:
        out_dir = root / "portfolios"
        out_dir.mkdir(parents=True, exist_ok=True)
        if not weights.empty:
            for construction, group in weights.groupby("construction"):
                group.drop(columns=["construction"]).to_parquet(
                    out_dir / f"{construction}.parquet", index=False
                )
        summary.to_parquet(out_dir / "e8_summary.parquet", index=False)
    return {"weights": weights, "summary": summary}


def f84_resampling(data_root: Path = DATA_ROOT, store: bool = True) -> pd.DataFrame:
    """F8.4: the resampling dispersion per rho and the shrinkage needed.

    For each rho the proportional weights are redrawn with IC-consistent
    noise; if the mean absolute weight change exceeds 30% the ridge lambda
    is increased on a log grid until it falls below. The lambda chosen per
    rho is the recorded shrinkage.
    """
    root = Path(data_root)
    pieces = date_pieces(root)
    rows: list[dict[str, object]] = []
    for rho in RHOS:
        dispersions: list[float] = []
        for seed in SEEDS:
            frame = synthetic_alpha(root, rho, seed, pieces=pieces)
            rng = np.random.default_rng(seed + 10_000)
            for _date, group in frame.groupby("date"):
                if _date not in pieces:
                    continue
                names = list(pieces[_date]["names"])
                specific = pieces[_date]["specific"]
                alpha = group.set_index("ticker")["alpha"].reindex(names).to_numpy()
                e_h = group.set_index("ticker")["e_h"].reindex(names).to_numpy()
                e_std = _standardize(e_h)
                if np.isfinite(e_h).sum() < 10:
                    continue
                dispersions.append(
                    _resample_dispersion(alpha, specific, e_std, rho, rng, lam=0.0)
                )
        lam = 0.0
        dispersion = float(np.mean(dispersions)) if dispersions else float("nan")
        if dispersion > 0.30:
            for lam_candidate in np.logspace(-6, -1, 24):
                sample: list[float] = []
                rng = np.random.default_rng(10_000)
                frame = synthetic_alpha(root, rho, 0, pieces=pieces)
                for _date, group in list(frame.groupby("date"))[:12]:
                    if _date not in pieces:
                        continue
                    names = list(pieces[_date]["names"])
                    alpha = group.set_index("ticker")["alpha"].reindex(names).to_numpy()
                    e_std = _standardize(
                        group.set_index("ticker")["e_h"].reindex(names).to_numpy()
                    )
                    sample.append(
                        _resample_dispersion(
                            alpha,
                            pieces[_date]["specific"],
                            e_std,
                            rho,
                            rng,
                            lam=float(lam_candidate),
                        )
                    )
                candidate_dispersion = (
                    float(np.mean(sample)) if sample else float("nan")
                )
                if np.isfinite(candidate_dispersion) and candidate_dispersion < 0.30:
                    lam = float(lam_candidate)
                    dispersion = candidate_dispersion
                    break
        rows.append(
            {
                "rho": rho,
                "dispersion_lambda_0": (
                    float(np.mean(dispersions)) if dispersions else float("nan")
                ),
                "dispersion_after_shrinkage": dispersion,
                "lambda_chosen": lam,
            }
        )
    frame = pd.DataFrame(rows)
    if store:
        frame.to_parquet(root / "portfolios" / "e8_f84_resampling.parquet", index=False)
    return frame
