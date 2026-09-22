"""Sprint E11: the evening proposal job.

Previous-close data only. Build tomorrow's target book: `idio_momentum`
as alpha, Procedure 6.3 sizing under the champion XS-v1, the exact FMP
hedge, the E8 constraint set, E9 costs and the E10 vol target capped by
the gross cap. The universe comes from the SPY archive, never the frozen
history. Nothing executes here; the job writes one dated proposal.

The seam is documented, never bridged: the risk model is frozen on the
pinned Wikipedia history (through its last close), while the universe is
the live SPY archive from 2026-09-18 forward. SPY names the frozen model
does not know are excluded and counted, not imputed.
"""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from efb import alpha as alpha_mod
from efb import costs as costs_mod
from efb import eval_risk, size
from efb.build import hash_file

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"
PROPOSAL_DIR = ROOT / "live" / "proposals"

SIGNAL = "idio_momentum"
SPY_UNIVERSE_MIN_AS_OF = date(2026, 9, 18)  # the live-universe seam
TARGET_ANNUAL_VOL = 0.10  # the E10 target
GROSS_CAP = 1.0  # the E8 gross cap, a hard ceiling
PAPER_NAV = 100_000.0  # the paper notional the morning job runs
REFERENCE_AUM = 1e8  # the capacity-curve reference, kept for the E6 finding
TRADING_DAYS = 252
HORIZON = 21  # the rebalance horizon, the E6 and E9 convention
MIN_NAMES = 50

# the frozen model inputs whose content the proposal is pinned to
INPUT_ARTIFACTS = (
    "models/XS-v1/descriptors.parquet",
    "models/XS-v1/factor_returns.parquet",
    "models/XS-v1/specific_var.parquet",
    "models/XS-v1/specific_returns.parquet",
    "alpha/summary.parquet",
    "processed/sectors.parquet",
)


def load_spy_universe(data_root: Path = DATA_ROOT) -> tuple[pd.DataFrame, Path]:
    """The live universe from the SPY archive, asserted rather than assumed.

    The latest dated SPY holdings file is the universe. The seam is
    enforced: a file dated before the live-universe seam fails loudly
    instead of silently falling back to the frozen history.
    """
    root = Path(data_root)
    archive_dir = root / "raw" / "spy_holdings"
    files = sorted(archive_dir.glob("spy_holdings_*.parquet"))
    if not files:
        raise FileNotFoundError(f"no SPY archive files under {archive_dir}")
    path = files[-1]
    frame = pd.read_parquet(path)
    as_of = pd.to_datetime(frame["as_of"].iloc[0]).date()
    if as_of < SPY_UNIVERSE_MIN_AS_OF:
        raise ValueError(
            f"SPY archive {path.name} is dated {as_of}, before the live "
            f"universe seam {SPY_UNIVERSE_MIN_AS_OF}"
        )
    return frame, path


def _stored_ic(signal: str, data_root: Path) -> float:
    """The stored horizon-1 IC of the signal, read, never typed by hand."""
    summary = pd.read_parquet(data_root / "alpha" / "summary.parquet")
    rows = summary.loc[summary["signal"] == signal]
    if rows.empty:
        raise ValueError(f"no stored alpha summary row for signal {signal!r}")
    return float(rows["ic_h1_mean"].iloc[0])


def _decomposition(
    weights: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
) -> dict[str, float]:
    """The book's risk split and its factor-neutrality after the hedge."""
    factor_var = float(weights @ design @ factor_covariance @ design.T @ weights)
    idio_var = float(weights @ (specific * weights))
    total = factor_var + idio_var
    return {
        "factor_variance": factor_var,
        "idio_variance": idio_var,
        "idio_share": idio_var / total if total > 0 else float("nan"),
        "max_abs_exposure": float(np.abs(design.T @ weights).max()),
        "gross": float(np.abs(weights).sum()),
        "net": float(weights.sum()),
        "n_eff": (
            float(np.abs(weights).sum() ** 2 / (weights**2).sum())
            if (weights**2).sum() > 0
            else 0.0
        ),
        "n_nonzero": int((np.abs(weights) > 1e-12).sum()),
    }


def _expected_establishment_cost(
    weights: np.ndarray,
    names: list[str],
    specific: np.ndarray,
    aum: float,
    root: Path,
) -> float:
    """The E9 transaction cost of building the book from flat, in bps of AUM."""
    prices = pd.read_parquet(root / "raw" / "prices.parquet")
    spread = costs_mod.spread_schedule(prices, root)
    adv = costs_mod._adv_per_ticker(prices)
    sigma = np.sqrt(np.maximum(specific, 1e-12))
    spread_map = spread.reindex(names).fillna(spread.median()).to_numpy(dtype=float)
    adv_map = adv.reindex(names).fillna(adv.median()).to_numpy(dtype=float)
    fraction = costs_mod._trade_cost(
        weights, spread_map, sigma, adv_map, aum, costs_mod.IMPACT_K
    )
    return float(fraction) * 1e4


def _input_as_of(root: Path) -> dict[str, str]:
    """The as-of date of every model input the proposal reads, one field each."""
    prices_frame = pd.read_parquet(root / "raw" / "prices.parquet")
    shares = pd.read_parquet(root / "raw" / "shares_history.parquet")
    sectors = pd.read_parquet(root / "processed" / "sectors.parquet")
    descriptors = pd.read_parquet(root / "models" / "XS-v1" / "descriptors.parquet")
    factor_returns = pd.read_parquet(
        root / "models" / "XS-v1" / "factor_returns.parquet"
    )
    specific_returns = pd.read_parquet(
        root / "models" / "XS-v1" / "specific_returns.parquet"
    )
    specific_var = pd.read_parquet(root / "models" / "XS-v1" / "specific_var.parquet")
    factor_last = str(pd.to_datetime(factor_returns["date"]).max().date())
    price_last = str(
        pd.Timestamp(prices_frame.index.get_level_values("date").max()).date()
    )
    return {
        "prices": price_last,
        "shares": str(pd.to_datetime(shares["date"]).max().date()),
        "sectors": str(pd.to_datetime(sectors["as_of"]).max().date()),
        "descriptors": str(pd.to_datetime(descriptors["date"]).max().date()),
        "factor_returns": factor_last,
        "specific_returns": str(pd.to_datetime(specific_returns["date"]).max().date()),
        "factor_cov": factor_last,
        "specific_var": str(pd.to_datetime(specific_var["date"]).max().date()),
    }


def _cost_decomposition(
    weights: np.ndarray,
    names: list[str],
    specific: np.ndarray,
    nav: float,
    root: Path,
) -> dict[str, float]:
    """The establishment cost split into spread, impact, commission and borrow.

    Each component is in basis points of the paper NAV. Borrow is the
    annualized rate on the short leg over one rebalance horizon, the same
    horizon E6's per-rebalance number uses.
    """
    prices = pd.read_parquet(root / "raw" / "prices.parquet")
    spread = costs_mod.spread_schedule(prices, root)
    adv = costs_mod._adv_per_ticker(prices)
    sigma = np.sqrt(np.maximum(specific, 1e-12))
    spread_map = spread.reindex(names).fillna(spread.median()).to_numpy(dtype=float)
    adv_map = adv.reindex(names).fillna(adv.median()).to_numpy(dtype=float)
    dollar_trade = np.abs(weights) * nav
    impact = (
        costs_mod.IMPACT_K
        * sigma
        * np.sqrt(np.maximum(dollar_trade, 0.0) / np.maximum(adv_map, 1.0))
    )
    spread_bps = float(np.sum(spread_map * np.abs(weights))) * 1e4
    commission_bps = float(np.sum(costs_mod.COMMISSION * np.abs(weights))) * 1e4
    impact_bps = float(np.sum(impact * np.abs(weights))) * 1e4
    short_gross = float(np.maximum(-weights, 0.0).sum())
    borrow_bps = costs_mod.BORROW_RATE * short_gross * (HORIZON / TRADING_DAYS) * 1e4
    total = spread_bps + commission_bps + impact_bps + borrow_bps
    return {
        "spread_bps": spread_bps,
        "impact_bps": impact_bps,
        "commission_bps": commission_bps,
        "borrow_bps": borrow_bps,
        "total_bps": total,
        "notional": float(np.abs(weights).sum()) * nav,
        "avg_trade_size": float(np.abs(weights).mean()) * nav,
    }


def build_proposal(
    data_root: Path = DATA_ROOT,
    as_of: pd.Timestamp | None = None,
    nav: float = PAPER_NAV,
    store: bool = True,
) -> dict[str, object]:
    """Build tomorrow's target book and write the dated proposal artifacts.

    Returns the proposal manifest: the universe source and seam, the as-of
    date of every model input and the max staleness, the decomposition
    after the hedge, the achieved vol against the E10 target, the four-way
    E9 cost split, and the hashes of every frozen input.
    """
    root = Path(data_root)
    universe, spy_path = load_spy_universe(root)
    universe_as_of = str(pd.to_datetime(universe["as_of"].iloc[0]).date())
    spy_tickers = sorted(universe["ticker"].astype(str).str.upper().str.strip())

    wide, _counts = eval_risk.load_clean_wide(root)
    as_of_ts = pd.Timestamp(as_of) if as_of is not None else wide.index.max()
    wide_names = [str(column) for column in wide.columns]
    names = [ticker for ticker in spy_tickers if ticker in wide_names]
    excluded = [ticker for ticker in spy_tickers if ticker not in wide_names]
    if len(names) < MIN_NAMES:
        raise ValueError(
            f"the SPY universe overlaps the frozen model on only {len(names)} "
            f"names, below the {MIN_NAMES} floor"
        )

    pieces = eval_risk._xs_pieces(as_of_ts, names, root)
    if pieces is None:
        raise ValueError(f"no XS-v1 pieces available at {as_of_ts.date()}")
    design = pieces["design"]
    factor_covariance = pieces["factor_covariance"]
    specific = pieces["specific"]

    ic = _stored_ic(SIGNAL, root)
    kappa = alpha_mod.KAPPA
    signal = alpha_mod.idio_momentum(root)
    day = signal.loc[pd.to_datetime(signal["date"]) == as_of_ts]
    if day.empty:
        raise ValueError(f"no {SIGNAL} signal row on {as_of_ts.date()}")
    raw = day.set_index("ticker")["signal"].reindex(names)
    z = (raw - raw.mean()) / raw.std(ddof=1)
    z = z.fillna(0.0).to_numpy(dtype=float)
    alpha_vec = np.where(
        np.isfinite(specific),
        ic * specific * z * kappa,
        ic * float(np.nanmedian(specific)) * z * kappa,
    )

    # Procedure 6.3: size on D^-1 alpha, then hedge factors with the exact
    # in-model FMPs. The hedge drives every factor exposure, styles and
    # sectors included, to zero to machine precision.
    weights = size.procedure_6_3(alpha_vec, design, factor_covariance, specific)
    pre_scale = _decomposition(weights, design, factor_covariance, specific)

    # E10 vol target, capped by the E8 gross cap. A null alpha cannot reach
    # the 10% target inside gross 1, so the cap binds and the achieved vol
    # is stored beside the target.
    daily_var = float(
        weights @ design @ factor_covariance @ design.T @ weights
        + weights @ (specific * weights)
    )
    daily_vol = math.sqrt(daily_var) if daily_var > 0 else 0.0
    target_daily_vol = TARGET_ANNUAL_VOL / math.sqrt(TRADING_DAYS)
    scale = target_daily_vol / daily_vol if daily_vol > 0 else 1.0
    gross_cap_bound = False
    if scale * pre_scale["gross"] > GROSS_CAP:
        scale = GROSS_CAP / pre_scale["gross"]
        gross_cap_bound = True
    weights = weights * scale
    decomposition = _decomposition(weights, design, factor_covariance, specific)

    cost = _cost_decomposition(weights, names, specific, nav, root)

    input_as_of = _input_as_of(root)
    input_as_of["universe"] = universe_as_of
    staleness = max(
        (as_of_ts - pd.Timestamp(value)).days for value in input_as_of.values()
    )

    manifest: dict[str, object] = {
        "signal": SIGNAL,
        "as_of": str(as_of_ts.date()),
        "universe_source": str(spy_path.relative_to(root)),
        "universe_as_of": universe_as_of,
        "n_names": len(names),
        "n_excluded": len(excluded),
        "excluded": excluded,
        "ic": ic,
        "kappa": kappa,
        "idio_share_after_fmp": decomposition["idio_share"],
        "max_abs_exposure_after_fmp": decomposition["max_abs_exposure"],
        "gross": decomposition["gross"],
        "net": decomposition["net"],
        "n_eff": decomposition["n_eff"],
        "n_nonzero": decomposition["n_nonzero"],
        "target_annual_vol": TARGET_ANNUAL_VOL,
        "achieved_annual_vol": float(
            math.sqrt(decomposition["idio_variance"] + decomposition["factor_variance"])
            * math.sqrt(TRADING_DAYS)
        ),
        "gross_cap_bound": gross_cap_bound,
        "nav": nav,
        "expected_establishment_cost_bps": cost["total_bps"],
        "cost_breakdown_bps": {
            "spread": cost["spread_bps"],
            "impact": cost["impact_bps"],
            "commission": cost["commission_bps"],
            "borrow": cost["borrow_bps"],
            "total": cost["total_bps"],
        },
        "notional": cost["notional"],
        "avg_trade_size": cost["avg_trade_size"],
        "input_as_of": input_as_of,
        "max_input_staleness_days": staleness,
        "input_hashes": {
            artifact: hash_file(root / artifact) for artifact in INPUT_ARTIFACTS
        },
    }

    if store:
        PROPOSAL_DIR.mkdir(parents=True, exist_ok=True)
        stamp = str(as_of_ts.date())
        rows = pd.DataFrame(
            {
                "ticker": names,
                "weight": weights,
                "side": np.where(weights >= 0, "long", "short"),
                "z": z,
                "alpha": alpha_vec,
            }
        )
        rows = rows.loc[rows["weight"].abs() > 1e-12].reset_index(drop=True)
        rows.to_parquet(PROPOSAL_DIR / f"proposal_{stamp}.parquet", index=False)
        manifest_path = PROPOSAL_DIR / f"proposal_{stamp}.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    return manifest


def main() -> int:
    """The cron entrypoint: build the proposal, nothing executes."""
    manifest = build_proposal()
    print(
        f"proposal {manifest['as_of']}: {manifest['n_names']} names, "
        f"idio share after FMP {manifest['idio_share_after_fmp']:.4f}, "
        f"gross {manifest['gross']:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
