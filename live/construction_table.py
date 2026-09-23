"""Sprint E11: the construction table, the owner's decision surface.

Rows: minimum position size of $1,500, $2,000, $3,000 and $5,000, plus top N
by absolute alpha at N = 150 and N = 200, plus one flagged two-part floor row
(min $1,500 dollars and min 20 shares). Each row drops names, re-runs
Procedure 6.3 on the kept subset, renormalizes to gross 1.0, then quantizes to
whole shares. The dollar floor is applied iteratively to a fixed point, so a
name admitted after the kept set is scaled up is reported.

Every row reports net dollar three ways, the realized market beta, the
per-name share-count distribution and what drives the p90 rounding-error tail,
plus post-hedge exposure and idio share, the maximum post-renormalization
weight, and both breadth bounds.

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
WEIGHTS_PATH = ROOT / "live" / "construction_weights.parquet"

MIN_POSITION_ROWS = (1500.0, 2000.0, 3000.0, 5000.0)
TOP_N_ROWS = (150, 200)
MIN_SHARES_ROW = 20  # the two-part floor's share leg


def _raw_pieces(
    root: Path, as_of_ts: pd.Timestamp
) -> tuple[list[str], np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """The raw alpha, signal z and model pieces the full book is sized from."""
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
    return names, alpha_vec, z, design, factor_covariance, specific


def _load_beta_stages(names: list[str], root: Path) -> dict[str, Any]:
    """The raw CAPM beta beside XS-v1's own beta-descriptor pipeline stages.

    The raw beta is the unshrunk 252-day CAPM beta from TS-v1's beta_history,
    read at its latest date (it ends 2026-09-03; the live extension did not
    rebuild it). The descriptor stages come from XS-v1's descriptors artifact
    at its latest date: `value_raw` is the Vasicek-shrunk beta before
    winsorization and z-scoring, `value_z_orth` is the finished descriptor the
    FMP hedge zeroes. A name the descriptor cross-section drops contributes
    zero to the hedge, so both stages are filled with 0 to match the design's
    own nan_to_num.
    """
    beta = pd.read_parquet(root / "models" / "TS-v1" / "beta_history.parquet")
    beta = beta[beta["method"] == "raw"]
    raw_latest = pd.to_datetime(beta["date"]).max()
    raw_series = beta.loc[pd.to_datetime(beta["date"]) == raw_latest].set_index(
        "ticker"
    )["beta"]
    median = float(raw_series.median())
    raw_map: dict[str, float] = {}
    filled: set[str] = set()
    for ticker in names:
        value = raw_series.get(ticker)
        if value is None or pd.isna(value):
            raw_map[ticker] = median
            filled.add(ticker)
        else:
            raw_map[ticker] = float(value)

    descriptors = pd.read_parquet(root / "models" / "XS-v1" / "descriptors.parquet")
    beta_desc = descriptors[descriptors["descriptor"] == "beta"]
    stamp = pd.to_datetime(beta_desc["date"]).max()
    day = beta_desc.loc[pd.to_datetime(beta_desc["date"]) == stamp].set_index("ticker")
    shrunk_map: dict[str, float] = {}
    descriptor_map: dict[str, float] = {}
    for ticker in names:
        if ticker in day.index:
            shrunk = day.loc[ticker, "value_raw"]
            descriptor = day.loc[ticker, "value_z_orth"]
            shrunk_map[ticker] = float(shrunk) if pd.notna(shrunk) else 0.0
            descriptor_map[ticker] = float(descriptor) if pd.notna(descriptor) else 0.0
        else:
            shrunk_map[ticker] = 0.0
            descriptor_map[ticker] = 0.0
    return {
        "raw": raw_map,
        "filled": filled,
        "shrunk": shrunk_map,
        "descriptor": descriptor_map,
    }


def _iterative_floor(full_weights: np.ndarray, nav: float, floor: float) -> np.ndarray:
    """The dollar floor applied to a fixed point.

    A dropped name worth x pre-renormalization is worth x / kept_gross after
    the kept set is scaled to gross 1.0, so it clears the floor when
    x >= floor * kept_gross. Admitting names raises kept_gross, which lowers
    the scale, which shrinks every survivor: the iteration admits names back
    until no further name clears the floor.
    """
    # A name i is kept iff d_i >= (floor / nav) * S where d_i is its dollar
    # size and S is the kept gross. Sorting by descending d_i makes the kept
    # set a prefix, so the fixed point is the longest prefix whose last name
    # still clears the floor against the prefix's own gross. Naive iteration
    # of this map oscillates (the map reverses inclusion), so solve it directly.
    dollars = np.abs(full_weights) * nav
    order = np.argsort(-dollars)
    running = 0.0
    keep = np.zeros(len(dollars), dtype=bool)
    for position in order:
        weight = abs(float(full_weights[position]))
        if dollars[position] >= floor * (running + weight):
            running += weight
            keep[position] = True
        else:
            break
    return keep


def _compute_row(
    names: list[str],
    alpha_vec: np.ndarray,
    design: np.ndarray,
    factor_covariance: np.ndarray,
    specific: np.ndarray,
    full_weights: np.ndarray,
    close: dict[str, float],
    beta_stages: dict[str, Any],
    nav: float,
    n_eff_full: float,
    keep: np.ndarray,
    sides: np.ndarray,
    signal_z: np.ndarray,
    label: str,
    flagged_for_veto: bool,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Size, renormalize, quantize and measure one kept set.

    Returns the summary row and one record per kept name (ticker, side,
    weight, z and alpha) so the dashboard can render any construction's
    names, weights and trade reasons.
    """
    idx = np.where(keep)[0]
    alpha_sub = alpha_vec[idx]
    design_sub = design[idx]
    specific_sub = specific[idx]
    names_sub = [names[i] for i in idx]

    gross_before = float(np.abs(full_weights[idx]).sum())

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

    # net dollar, three ways
    net_share_of_gross = float(w_sub.sum())  # gross is 1.0 after renormalization
    if abs(net_share_of_gross) < 1e-9:
        net_share_of_gross = 0.0
    prices = np.array([close.get(t, 0.0) for t in names_sub])
    shares = np.floor(np.abs(w_sub) * nav / np.maximum(prices, 1e-12)).astype(int)
    q_notional = shares * prices * np.sign(w_sub)
    gross_q = float(np.abs(q_notional).sum())
    net_share_post_quantization = (
        float(q_notional.sum()) / gross_q if gross_q > 0 else 0.0
    )
    if abs(net_share_post_quantization) < 1e-9:
        net_share_post_quantization = 0.0

    # realized market beta: w' beta over the raw CAPM betas, plus the
    # decomposition into the stages XS-v1's descriptor drops. The FMP hedge
    # zeroes the z-scored, winsorized descriptor, not the raw beta; the
    # residual is the winsorization and shrinkage the descriptor does not
    # span.
    raw_map = cast(dict[str, float], beta_stages["raw"])
    shrunk_map = cast(dict[str, float], beta_stages["shrunk"])
    descriptor_map = cast(dict[str, float], beta_stages["descriptor"])
    filled_names = cast(set[str], beta_stages["filled"])
    beta_sub = np.array([raw_map[t] for t in names_sub])
    realized_market_beta = float(w_sub @ beta_sub)
    shrunk_sub = np.array([shrunk_map[t] for t in names_sub])
    descriptor_sub = np.array([descriptor_map[t] for t in names_sub])
    realized_market_beta_shrunk = float(w_sub @ shrunk_sub)
    realized_market_beta_descriptor = float(w_sub @ descriptor_sub)
    not_filled = np.array([t not in filled_names for t in names_sub])
    n_beta_filled = int((~not_filled).sum())
    if not_filled.sum():
        realized_market_beta_ex_fills = float(
            (w_sub[not_filled] @ beta_sub[not_filled]) / np.abs(w_sub[not_filled]).sum()
        )
    else:
        realized_market_beta_ex_fills = float("nan")
    if not_filled.sum() > 1:
        corr_raw_vs_descriptor = float(
            np.corrcoef(beta_sub[not_filled], descriptor_sub[not_filled])[0, 1]
        )
    else:
        corr_raw_vs_descriptor = float("nan")

    # per-name share counts
    median_shares = float(np.median(shares))
    p10_shares = float(np.quantile(shares, 0.1))

    # what drives the p90 rounding-error tail
    target = np.abs(w_sub) * nav
    err_pct = np.abs(q_notional - w_sub * nav) / np.maximum(target, 1e-12)
    p90_thresh = float(np.quantile(err_pct, 0.9))
    tail = err_pct >= p90_thresh
    tail_shares = shares[tail]
    tail_prices = prices[tail]
    if int(tail.sum()) == 0:
        driver = "no tail"
    elif float(np.median(tail_shares)) < 20:
        driver = (
            f"high-priced names: {int(tail.sum())} names, median "
            f"{float(np.median(tail_shares)):.0f} shares at median "
            f"${float(np.median(tail_prices)):.0f}"
        )
    else:
        driver = (
            f"small positions: {int(tail.sum())} names, median "
            f"{float(np.median(tail_shares)):.0f} shares"
        )

    n_selected = int(len(idx))
    n_eff_kept = decomp["n_eff"]
    p90_error = float(dist["rounding_error_pct_of_target_quantiles"]["0.9"])

    per_name: list[dict[str, object]] = []
    for position, ticker in enumerate(names_sub):
        side_value = float(sides[idx[position]])
        side = "long" if side_value > 0 else "short" if side_value < 0 else "flat"
        per_name.append(
            {
                "construction": label,
                "ticker": ticker,
                "weight": float(w_sub[position]),
                "side": side,
                "z": float(signal_z[idx[position]]),
                "alpha": float(alpha_sub[position]),
            }
        )

    return {
        "construction": label,
        "flagged_for_veto": flagged_for_veto,
        "n_kept": n_selected,
        "n_effective": int(decomp["n_nonzero"]),
        "n_dropped": len(names) - n_selected,
        "n_long": int((sides[idx] > 0).sum()),
        "n_short": int((sides[idx] < 0).sum()),
        "kept_gross_before_renorm": gross_before,
        "kept_gross_after_renorm": float(np.abs(w_sub).sum()),
        "net_dollar_share_of_gross": net_share_of_gross,
        "net_dollar_share_of_gross_post_quantization": net_share_post_quantization,
        "realized_market_beta": realized_market_beta,
        "n_beta_filled": n_beta_filled,
        "realized_market_beta_ex_fills": realized_market_beta_ex_fills,
        "realized_market_beta_shrunk": realized_market_beta_shrunk,
        "realized_market_beta_descriptor": realized_market_beta_descriptor,
        "corr_raw_vs_descriptor": corr_raw_vs_descriptor,
        "median_share_count": median_shares,
        "p10_share_count": p10_shares,
        "p90_tail_driver": driver,
        "quant_error_median_pct_of_target": float(
            dist["rounding_error_pct_of_target_quantiles"]["0.5"]
        ),
        "quant_error_p90_pct_of_target": p90_error,
        "total_gross_error_share_of_nav": float(quant["gross_weight_error"]),
        "post_hedge_max_abs_exposure": float(decomp["max_abs_exposure"]),
        "post_hedge_idio_share": float(decomp["idio_share"]),
        "max_weight_share_of_gross": float(np.abs(w_sub).max()),
        "breadth_naive": float(math.sqrt(460.0 / max(n_selected, 1))),
        "breadth_governing": float(math.sqrt(n_eff_full / max(n_eff_kept, 1e-12))),
        "n_eff_kept": n_eff_kept,
        "n_eff_full": n_eff_full,
    }, per_name


def build_table(
    data_root: Path = DATA_ROOT,
    as_of: pd.Timestamp | None = None,
    nav: float = PAPER_NAV,
    store: bool = True,
) -> pd.DataFrame:
    """Build the construction table for the owner's decision."""
    root = Path(data_root)
    wide, _counts = eval_risk.load_clean_wide(root)
    as_of_ts = pd.Timestamp(as_of) if as_of is not None else wide.index.max()
    names, alpha_vec, signal_z, design, factor_covariance, specific = _raw_pieces(
        root, as_of_ts
    )
    close = _close_prices(as_of_ts, root)
    beta_stages = _load_beta_stages(names, root)

    full_weights = size.procedure_6_3(alpha_vec, design, factor_covariance, specific)
    full_weights, _gross_cap_bound = _scale_to_target(
        full_weights, design, factor_covariance, specific
    )
    full_decomp = _decomposition(full_weights, design, factor_covariance, specific)
    n_eff_full = full_decomp["n_eff"]

    rows: list[dict[str, object]] = []
    per_name_rows: list[dict[str, object]] = []
    for threshold in MIN_POSITION_ROWS:
        initial_keep = np.abs(full_weights) * nav >= threshold
        pre, _pre_names = _compute_row(
            names,
            alpha_vec,
            design,
            factor_covariance,
            specific,
            full_weights,
            close,
            beta_stages,
            nav,
            n_eff_full,
            initial_keep,
            full_weights,
            signal_z,
            f"min_position_{int(threshold)}",
            False,
        )
        iterative_keep = _iterative_floor(full_weights, nav, threshold)
        post, post_names = _compute_row(
            names,
            alpha_vec,
            design,
            factor_covariance,
            specific,
            full_weights,
            close,
            beta_stages,
            nav,
            n_eff_full,
            iterative_keep,
            full_weights,
            signal_z,
            f"min_position_{int(threshold)}",
            False,
        )
        post["n_kept_pre_iteration"] = pre["n_kept"]
        post["n_kept_post_iteration"] = post["n_kept"]
        post["quant_error_p90_pre_iteration"] = pre["quant_error_p90_pct_of_target"]
        post["quant_error_p90_post_iteration"] = post["quant_error_p90_pct_of_target"]
        rows.append(post)
        per_name_rows.extend(post_names)

    for n_names in TOP_N_ROWS:
        top_idx = np.argsort(np.abs(alpha_vec))[::-1][:n_names]
        keep = np.zeros(len(names), dtype=bool)
        keep[top_idx] = True
        row, row_names = _compute_row(
            names,
            alpha_vec,
            design,
            factor_covariance,
            specific,
            full_weights,
            close,
            beta_stages,
            nav,
            n_eff_full,
            keep,
            alpha_vec,
            signal_z,
            f"top_n_{n_names}",
            False,
        )
        row["n_kept_pre_iteration"] = row["n_kept"]
        row["n_kept_post_iteration"] = row["n_kept"]
        row["quant_error_p90_pre_iteration"] = row["quant_error_p90_pct_of_target"]
        row["quant_error_p90_post_iteration"] = row["quant_error_p90_pct_of_target"]
        rows.append(row)
        per_name_rows.extend(row_names)

    dollar_keep = _iterative_floor(full_weights, nav, 1500.0)
    prices_full = np.array([close.get(t, 0.0) for t in names])
    share_keep = (
        np.abs(full_weights) * nav / np.maximum(prices_full, 1e-12)
    ) >= MIN_SHARES_ROW
    two_part, two_part_names = _compute_row(
        names,
        alpha_vec,
        design,
        factor_covariance,
        specific,
        full_weights,
        close,
        beta_stages,
        nav,
        n_eff_full,
        dollar_keep & share_keep,
        full_weights,
        signal_z,
        "two_part_floor_1500_20shares",
        True,
    )
    # pre is the $1,500 dollar floor alone; post is dollar floor plus the
    # 20-share leg, so the share leg's effect on breadth and p90 is visible.
    two_part["n_kept_pre_iteration"] = int(dollar_keep.sum())
    two_part["n_kept_post_iteration"] = two_part["n_kept"]
    two_part["quant_error_p90_pre_iteration"] = rows[0][
        "quant_error_p90_post_iteration"
    ]
    two_part["quant_error_p90_post_iteration"] = two_part[
        "quant_error_p90_pct_of_target"
    ]
    rows.append(two_part)
    per_name_rows.extend(two_part_names)

    table = pd.DataFrame(rows)
    if store:
        table.to_parquet(TABLE_PATH, index=False)
        pd.DataFrame(per_name_rows).to_parquet(WEIGHTS_PATH, index=False)
    return table


def main() -> int:
    """The CLI entrypoint: print the table for the owner."""
    table = build_table()
    print(table.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
