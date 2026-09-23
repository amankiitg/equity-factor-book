"""Sprint E11: the construction table, the owner's decision surface.

Six rows: minimum position size of $1,500, $2,000, $3,000 and $5,000, plus
top N by absolute alpha at N = 150 and N = 200. Each row drops names, re-runs
Procedure 6.3 on the kept subset (so the exact FMP hedge is recomputed on the
subset, never carried over from the 499-name book), renormalizes to gross 1.0,
then quantizes to whole shares. The rows report post-hedge exposure and idio
share, the per-name quantization error distribution, the maximum
post-renormalization weight, and both breadth bounds.

Nothing executes here and nothing is chosen: the owner picks from the table.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from efb import alpha as alpha_mod
from efb import eval_risk, size
from live import alpaca, sizing
from live.evening_job import (
    DATA_ROOT,
    PAPER_NAV,
    SIGNAL,
    _close_prices,
    _decomposition,
    _scale_to_target,
    _stored_ic,
    load_spy_universe,
)

ROOT = Path(__file__).resolve().parents[1]
TABLE_PATH = ROOT / "live" / "construction_table.parquet"

MIN_POSITION_ROWS = (1500.0, 2000.0, 3000.0, 5000.0)
TOP_N_ROWS = (150, 200)


def _raw_pieces(
    root: Path, as_of_ts: pd.Timestamp
) -> tuple[list[str], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """The raw alpha and model pieces the full book is sized from."""
    universe, _spy_path = load_spy_universe(root)
    spy_tickers = sorted(universe["ticker"].astype(str).str.upper().str.strip())
    wide, _counts = eval_risk.load_clean_wide(root)
    wide_names = [str(column) for column in wide.columns]
    names = [ticker for ticker in spy_tickers if ticker in wide_names]
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
    return names, alpha_vec, design, factor_covariance, specific


def _row_for_selection(
    names: list[str],
    alpha_vec: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
    full_weights: np.ndarray,
    close: dict[str, float],
    nav: float,
    n_eff_full: float,
    keep: np.ndarray,
    label: str,
    side_by_alpha: bool,
) -> dict[str, object]:
    """One construction row: drop, re-hedge, renormalize, quantize, report."""
    idx = np.where(keep)[0]
    alpha_sub = alpha_vec[idx]
    design_sub = design[idx]
    specific_sub = specific[idx]
    names_sub = [names[i] for i in idx]

    # kept gross before renormalization: the kept names' share of the full book
    gross_before = float(np.abs(full_weights[idx]).sum())

    # re-run Procedure 6.3 on the subset, then renormalize to gross 1.0
    w_sub = sizing.procedure_6_3_robust(
        alpha_sub, design_sub, factor_covariance, specific_sub
    )
    w_sub = sizing.renormalize(w_sub, gross=1.0)

    decomp = _decomposition(w_sub, design_sub, factor_covariance, specific_sub)
    quant = cast(
        dict[str, Any],
        alpaca.whole_share_quantization(
            pd.DataFrame({"ticker": names_sub, "weight": w_sub}), close, nav
        ),
    )
    dist = cast(dict[str, Any], quant["distribution"])

    sides = alpha_sub if side_by_alpha else full_weights[idx]
    n_selected = int(len(idx))
    n_eff_kept = decomp["n_eff"]

    return {
        "construction": label,
        "n_kept": n_selected,
        "n_effective": int(decomp["n_nonzero"]),
        "n_dropped": len(names) - n_selected,
        "n_long": int((sides > 0).sum()),
        "n_short": int((sides < 0).sum()),
        "kept_gross_before_renorm": gross_before,
        "kept_gross_after_renorm": float(np.abs(w_sub).sum()),
        "quant_error_median_pct_of_target": float(
            dist["rounding_error_pct_of_target_quantiles"]["0.5"]
        ),
        "quant_error_p90_pct_of_target": float(
            dist["rounding_error_pct_of_target_quantiles"]["0.9"]
        ),
        "total_gross_error_share_of_nav": float(quant["gross_weight_error"]),
        "post_hedge_max_abs_exposure": float(decomp["max_abs_exposure"]),
        "post_hedge_idio_share": float(decomp["idio_share"]),
        "max_weight_share_of_gross": float(np.abs(w_sub).max()),
        "breadth_naive": float(math.sqrt(460.0 / max(n_selected, 1))),
        "breadth_governing": float(math.sqrt(n_eff_full / max(n_eff_kept, 1e-12))),
        "n_eff_kept": n_eff_kept,
        "n_eff_full": n_eff_full,
    }


def build_table(
    data_root: Path = DATA_ROOT,
    as_of: pd.Timestamp | None = None,
    nav: float = PAPER_NAV,
    store: bool = True,
) -> pd.DataFrame:
    """Build the six-row construction table for the owner's decision."""
    root = Path(data_root)
    # resolve the as-of from the wide frame, as build_proposal does
    wide, _counts = eval_risk.load_clean_wide(root)
    as_of_ts = pd.Timestamp(as_of) if as_of is not None else wide.index.max()
    names, alpha_vec, design, factor_covariance, specific = _raw_pieces(root, as_of_ts)
    close = _close_prices(as_of_ts, root)

    full_weights = size.procedure_6_3(alpha_vec, design, factor_covariance, specific)
    full_weights, _gross_cap_bound = _scale_to_target(
        full_weights, design, factor_covariance, specific
    )
    full_decomp = _decomposition(full_weights, design, factor_covariance, specific)
    n_eff_full = full_decomp["n_eff"]

    rows: list[dict[str, object]] = []
    for threshold in MIN_POSITION_ROWS:
        keep = np.abs(full_weights) * nav >= threshold
        rows.append(
            _row_for_selection(
                names,
                alpha_vec,
                design,
                factor_covariance,
                specific,
                full_weights,
                close,
                nav,
                n_eff_full,
                keep,
                f"min_position_{int(threshold)}",
                side_by_alpha=False,
            )
        )
    for n_names in TOP_N_ROWS:
        top_idx = np.argsort(np.abs(alpha_vec))[::-1][:n_names]
        keep = np.zeros(len(names), dtype=bool)
        keep[top_idx] = True
        rows.append(
            _row_for_selection(
                names,
                alpha_vec,
                design,
                factor_covariance,
                specific,
                full_weights,
                close,
                nav,
                n_eff_full,
                keep,
                f"top_n_{n_names}",
                side_by_alpha=True,
            )
        )

    table = pd.DataFrame(rows)
    if store:
        table.to_parquet(TABLE_PATH, index=False)
    return table


def main() -> int:
    """The CLI entrypoint: print the table for the owner."""
    table = build_table()
    print(table.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
