"""Sprint E11: the construction table, the owner's decision surface.

Rows: minimum position size of $1,500, $2,000, $3,000 and $5,000, plus top N
by absolute alpha at N = 150 and N = 200, plus one flagged two-part floor row
(min $1,500 dollars and min 20 shares). Each row drops names, re-runs
Procedure 6.3 on the kept subset, renormalizes to gross 1.0, then quantizes to
whole shares. The dollar floor is applied iteratively to a fixed point, so a
name admitted after the kept set is scaled up is reported.

Every floor row also carries the largest valid prefix, the rule E11-F13
pre-registered as the book: ordered by |w_i| / floor_i on the full-book weights
and checked on the final weights. It is measured beside the enforced book, not
installed as one, because on this data it keeps far fewer names than the
drop-only loop on every floor row, which is the stop that rule pre-registered.

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
from live.evening_job import (
    DATA_ROOT,
    PAPER_NAV,
    SHARE_FLOOR,
    SIGNAL,
    _close_prices,
    _decomposition,
    _scale_to_target,
    _stored_ic,
    below_floor,
    enforce_floor_by_drop_then_admit,
    enforce_floor_by_prefix,
    finalize_kept_set,
    floor_book_violations,
    floor_order,
    floor_shortfalls,
    load_spy_universe,
)

ROOT = Path(__file__).resolve().parents[1]
TABLE_PATH = ROOT / "live" / "construction_table.parquet"
WEIGHTS_PATH = ROOT / "live" / "construction_weights.parquet"

MIN_POSITION_ROWS = (1500.0, 2000.0, 3000.0, 5000.0)
TOP_N_ROWS = (150, 200)
MIN_SHARES_ROW = SHARE_FLOOR  # the two-part floor's share leg


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
    """TS-v1's raw beta beside XS-v1's beta-descriptor pipeline stages.

    The raw beta is TS-v1's unshrunk 252-day CAPM beta, read at its latest
    date (2026-09-03; the live extension did not rebuild TS-v1). The stages
    come from XS-v1's descriptors artifact at its latest date (2026-09-21,
    the close the book is hedged against): `value_raw` is the Vasicek-shrunk
    beta, `value_winsor` the 3-MAD clipped value, `value_z` the standardized
    value before orthogonalization, `value_z_orth` the finished descriptor the
    FMP hedge zeroes. A name the descriptor cross-section drops contributes
    zero to the hedge, so every stage is filled with 0 for it, and the name is
    recorded as a zero fill. Market cap, the weight XS-v1's fit uses, is read
    at its own latest date (2026-09-03, frozen beside TS-v1).
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
    winsor_map: dict[str, float] = {}
    standardized_map: dict[str, float] = {}
    descriptor_map: dict[str, float] = {}
    zero_filled: set[str] = set()
    for ticker in names:
        if ticker in day.index:
            shrunk = day.loc[ticker, "value_raw"]
            winsor = day.loc[ticker, "value_winsor"]
            standardized = day.loc[ticker, "value_z"]
            descriptor = day.loc[ticker, "value_z_orth"]
            shrunk_map[ticker] = float(shrunk) if pd.notna(shrunk) else 0.0
            winsor_map[ticker] = float(winsor) if pd.notna(winsor) else 0.0
            standardized_map[ticker] = (
                float(standardized) if pd.notna(standardized) else 0.0
            )
            descriptor_map[ticker] = float(descriptor) if pd.notna(descriptor) else 0.0
            # a name present in the cross-section but with no descriptor value
            # is filled with 0 just as a name absent from it is: count it.
            if pd.isna(descriptor):
                zero_filled.add(ticker)
        else:
            shrunk_map[ticker] = 0.0
            winsor_map[ticker] = 0.0
            standardized_map[ticker] = 0.0
            descriptor_map[ticker] = 0.0
            zero_filled.add(ticker)

    mcap = pd.read_parquet(root / "processed" / "market_cap.parquet")
    mcap_latest = pd.to_datetime(mcap["date"]).max()
    mcap_day = mcap.loc[pd.to_datetime(mcap["date"]) == mcap_latest].set_index(
        "ticker"
    )["market_cap"]
    mcap_map = {
        ticker: (float(mcap_day.loc[ticker]) if ticker in mcap_day.index else 0.0)
        for ticker in names
    }

    return {
        "raw": raw_map,
        "filled": filled,
        "shrunk": shrunk_map,
        "winsor": winsor_map,
        "standardized": standardized_map,
        "descriptor": descriptor_map,
        "zero_filled": zero_filled,
        "mcap": mcap_map,
        "raw_date": raw_latest,
        "descriptor_date": stamp,
    }


def _cap_weighted_slope(x: np.ndarray, y: np.ndarray, mcap: np.ndarray) -> float:
    """The slope of y on x under XS-v1's sqrt-cap weights.

    Only names with positive market cap and finite x and y enter. The
    intercept is not computed: the book is dollar-neutral, so it cancels out
    of the exposure to the residual.
    """
    ok = (mcap > 0) & np.isfinite(x) & np.isfinite(y)
    if int(ok.sum()) < 3:
        return 0.0
    weights = mcap[ok]
    xc = x[ok]
    yc = y[ok]
    xw = float((weights * xc).sum() / weights.sum())
    yw = float((weights * yc).sum() / weights.sum())
    num = float((weights * (xc - xw) * (yc - yw)).sum())
    den = float((weights * (xc - xw) ** 2).sum())
    return num / den if den > 0 else 0.0


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


def _iterative_combined_floor(
    full_weights: np.ndarray,
    nav: float,
    prices: np.ndarray,
    dollar_floor: float,
    share_floor: int,
) -> np.ndarray:
    """The combined dollar-and-share floor applied to a fixed point.

    Name i clears the floor when its post-renormalization notional is at
    least the dollar floor and at least share_floor whole shares, which is
    the single condition |w_i| * nav >= max(dollar_floor, share_floor *
    price_i) * S where S is the kept gross. Sorting by the ratio
    |w_i| / max(dollar_floor, share_floor * price_i) makes the kept set a
    prefix, so the longest prefix whose last name still clears against its
    own gross is the fixed point, exactly as for the dollar-only floor.
    """
    thresholds = np.maximum(dollar_floor, share_floor * prices)
    order = np.argsort(-(np.abs(full_weights) / thresholds))
    running = 0.0
    keep = np.zeros(len(full_weights), dtype=bool)
    for position in order:
        weight = abs(float(full_weights[position]))
        if (
            abs(full_weights[position]) * nav
            >= (running + weight) * thresholds[position]
        ):
            running += weight
            keep[position] = True
        else:
            break
    return keep


def _one_pass_combined_floor(
    full_weights: np.ndarray,
    nav: float,
    prices: np.ndarray,
    dollar_floor: float,
    share_floor: int,
) -> np.ndarray:
    """The combined floor applied once, before any renormalization."""
    return (np.abs(full_weights) * nav >= dollar_floor) & (
        np.abs(full_weights) * nav / np.maximum(prices, 1e-12) >= share_floor
    )


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
    finalize: dict[str, Any] | None = None,
    dollar_floor: float = 0.0,
    share_floor: int = 0,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Size, renormalize, quantize and measure one kept set.

    Returns the summary row and one record per kept name (ticker, side,
    weight, z and alpha) so the dashboard can render any construction's
    names, weights and trade reasons.
    """
    if finalize is None:
        finalize = finalize_kept_set(
            keep, names, alpha_vec, design, factor_covariance, specific, close, nav
        )
    idx = np.asarray(finalize["idx"], dtype=int)
    names_sub = cast(list[str], finalize["names_sub"])
    w_sub = np.asarray(finalize["w_sub"], dtype=float)
    decomp = cast(dict[str, Any], finalize["decomp"])
    quant = cast(dict[str, Any], finalize["quant"])
    dist = cast(dict[str, Any], quant["distribution"])
    prices = np.asarray(finalize["prices"], dtype=float)
    shares = np.asarray(finalize["shares"], dtype=int)
    q_notional = np.asarray(finalize["q_notional"], dtype=float)
    gross_q = float(finalize["gross_q"])

    gross_before = float(np.abs(full_weights[idx]).sum())
    alpha_sub = alpha_vec[idx]

    # net dollar, three ways
    net_share_of_gross = float(w_sub.sum())  # gross is 1.0 after renormalization
    if abs(net_share_of_gross) < 1e-9:
        net_share_of_gross = 0.0
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
    winsor_map = cast(dict[str, float], beta_stages["winsor"])
    standardized_map = cast(dict[str, float], beta_stages["standardized"])
    descriptor_map = cast(dict[str, float], beta_stages["descriptor"])
    mcap_map = cast(dict[str, float], beta_stages["mcap"])
    filled_names = cast(set[str], beta_stages["filled"])
    zero_filled_names = cast(set[str], beta_stages["zero_filled"])
    beta_sub = np.array([raw_map[t] for t in names_sub])
    realized_market_beta = float(w_sub @ beta_sub)
    shrunk_sub = np.array([shrunk_map[t] for t in names_sub])
    descriptor_sub = np.array([descriptor_map[t] for t in names_sub])
    realized_market_beta_shrunk = float(w_sub @ shrunk_sub)
    realized_market_beta_descriptor = float(w_sub @ descriptor_sub)

    # the raw-units decomposition: for each stage, regress the raw beta on the
    # stage across the full cross-section with XS-v1's cap weights and report
    # the book's exposure to the residual. Because the book is dollar-neutral
    # the intercept cancels, so the exposure is w' raw - slope * w' stage.
    raw_full = np.array([raw_map[t] for t in names])
    mcap_full = np.array([mcap_map[t] for t in names])
    residual_exposures: dict[str, float] = {}
    for stage_name, stage_map in (
        ("shrunk", shrunk_map),
        ("winsor", winsor_map),
        ("standardized", standardized_map),
        ("descriptor", descriptor_map),
    ):
        stage_full = np.array([stage_map[t] for t in names])
        slope = _cap_weighted_slope(stage_full, raw_full, mcap_full)
        stage_sub = np.array([stage_map[t] for t in names_sub])
        residual_exposures[stage_name] = float(
            w_sub @ beta_sub - slope * (w_sub @ stage_sub)
        )

    not_filled = np.array([t not in filled_names for t in names_sub])
    n_beta_filled = int((~not_filled).sum())
    if not_filled.sum():
        realized_market_beta_ex_fills = float(
            (w_sub[not_filled] @ beta_sub[not_filled]) / np.abs(w_sub[not_filled]).sum()
        )
    else:
        realized_market_beta_ex_fills = float("nan")
    not_zero_filled = np.array([t not in zero_filled_names for t in names_sub])
    n_beta_zero_filled = int((~not_zero_filled).sum())
    if not_zero_filled.sum():
        realized_market_beta_ex_zero_fills = float(
            (w_sub[not_zero_filled] @ beta_sub[not_zero_filled])
            / np.abs(w_sub[not_zero_filled]).sum()
        )
    else:
        realized_market_beta_ex_zero_fills = float("nan")
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
    n_eff_kept = decomp["effective_breadth"]
    p90_error = float(dist["rounding_error_pct_of_target_quantiles"]["0.9"])
    n_below = int(below_floor(shares, prices, dollar_floor, share_floor).sum())
    worst_shares, worst_dollars = floor_shortfalls(
        shares, prices, dollar_floor, share_floor
    )

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
        "n_beta_zero_filled": n_beta_zero_filled,
        "realized_market_beta_ex_zero_fills": realized_market_beta_ex_zero_fills,
        "realized_market_beta_shrunk": realized_market_beta_shrunk,
        "realized_market_beta_descriptor": realized_market_beta_descriptor,
        "corr_raw_vs_descriptor": corr_raw_vs_descriptor,
        "residual_exposure_shrunk": residual_exposures["shrunk"],
        "residual_exposure_winsor": residual_exposures["winsor"],
        "residual_exposure_standardized": residual_exposures["standardized"],
        "residual_exposure_descriptor": residual_exposures["descriptor"],
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
        "n_below_floor_final": n_below,
        "worst_floor_shortfall_shares": worst_shares,
        "worst_floor_shortfall_dollars": worst_dollars,
    }, per_name


def _stamp_admit_columns(
    row: dict[str, object],
    search: dict[str, Any],
    violations: list[str],
) -> None:
    """Record the search behind an installed floor book, and its check result.

    The check result is a string rather than a gate, because one row of the
    table cannot satisfy the name-count margin (`min_position_5000` keeps 35
    names against the 51 the owner's rank margin needs) and stopping the
    build would hide the measurement. The build reports it; the live path
    raises on it.

    The search's run time is not stored here, because a clock reading would
    make the artifact differ on every build; the proposal manifest carries it.
    """
    row["n_kept_drop_only"] = search["n_drop_only"]
    row["n_kept_one_pass_admission"] = search["n_one_pass_admission"]
    row["admit_cycles"] = search["cycles"]
    row["admit_passes"] = search["admit_passes"]
    row["admit_extra"] = search["admitted"]
    row["admit_converged"] = search["converged"]
    row["floor_book_checks"] = "ok" if not violations else "; ".join(violations)


def _enforce_row(
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
    sides: np.ndarray,
    signal_z: np.ndarray,
    label: str,
    flagged_for_veto: bool,
    pre: dict[str, object],
    post: dict[str, object],
    dollar_floor: float,
    share_floor: int,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Install the floor book: drop, then admit, to a local maximum (E11-F13R).

    The book is the drop-only fixed point, then the names admitted in the
    |w_i| / floor_i order while the enlarged set's final weights still clear
    every kept name's floor, repeated until a full cycle changes nothing. Its
    checks are recorded per row; every kept name clears its floor in the final
    weights by construction of the rule, and the other four checks are
    measured.

    Two superseded rules are recorded beside the book: the drop-only count,
    and the largest valid prefix E11-F13 pre-registered, which keeps far fewer
    names than the drop-only loop on every floor row and is the stop that rule
    fired. The pre and post rows carry the one-pass and the full-weight fixed
    point, whose below-floor count is recorded against the book.
    """
    floor_rule_order = floor_order(
        close, names, full_weights, dollar_floor, share_floor
    )
    enforced_keep, enforced_finalize, search = enforce_floor_by_drop_then_admit(
        names,
        alpha_vec,
        design,
        factor_covariance,
        specific,
        close,
        nav,
        full_weights,
        dollar_floor,
        share_floor,
        order=floor_rule_order,
    )
    violations = floor_book_violations(
        enforced_keep,
        names,
        alpha_vec,
        design,
        factor_covariance,
        specific,
        close,
        nav,
        dollar_floor,
        share_floor,
    )
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
        enforced_keep,
        sides,
        signal_z,
        label,
        flagged_for_veto,
        finalize=enforced_finalize,
        dollar_floor=dollar_floor,
        share_floor=share_floor,
    )
    row["n_kept_pre_iteration"] = pre["n_kept"]
    row["n_kept_post_iteration"] = post["n_kept"]
    row["n_kept_post_enforcement"] = row["n_kept"]
    row["quant_error_p90_pre_iteration"] = pre["quant_error_p90_pct_of_target"]
    row["quant_error_p90_post_iteration"] = post["quant_error_p90_pct_of_target"]
    row["quant_error_p90_post_enforcement"] = row["quant_error_p90_pct_of_target"]
    row["n_below_floor_final_pre_enforcement"] = post["n_below_floor_final"]
    row["worst_floor_shortfall_shares_pre_enforcement"] = post[
        "worst_floor_shortfall_shares"
    ]
    row["worst_floor_shortfall_dollars_pre_enforcement"] = post[
        "worst_floor_shortfall_dollars"
    ]
    row["floor_enforcement_passes"] = search["admit_passes"]
    row["floor_enforcement_converged"] = search["converged"]
    _stamp_admit_columns(row, search, violations)

    prefix_keep, prefix_finalize, prefix_k = enforce_floor_by_prefix(
        names,
        alpha_vec,
        design,
        factor_covariance,
        specific,
        close,
        nav,
        full_weights,
        dollar_floor,
        share_floor,
    )
    prefix_row, _prefix_names = _compute_row(
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
        prefix_keep,
        sides,
        signal_z,
        label,
        flagged_for_veto,
        finalize=prefix_finalize,
        dollar_floor=dollar_floor,
        share_floor=share_floor,
    )
    row["n_kept_prefix"] = prefix_row["n_kept"]
    row["floor_prefix_k"] = prefix_k
    row["floor_prefix_scans"] = len(names) - prefix_k + 1
    row["n_eff_kept_prefix"] = prefix_row["n_eff_kept"]
    row["total_error_share_of_nav_prefix"] = prefix_row[
        "total_gross_error_share_of_nav"
    ]
    row["quant_error_p90_pct_of_target_prefix"] = prefix_row[
        "quant_error_p90_pct_of_target"
    ]
    row["max_weight_share_of_gross_prefix"] = prefix_row["max_weight_share_of_gross"]
    row["net_dollar_share_of_gross_prefix"] = prefix_row["net_dollar_share_of_gross"]

    # robustness, measured and not used to select: the same rule with the names
    # ordered by |alpha| descending instead of |w_i| / floor_i
    alpha_keep, _alpha_finalize, _alpha_search = enforce_floor_by_drop_then_admit(
        names,
        alpha_vec,
        design,
        factor_covariance,
        specific,
        close,
        nav,
        full_weights,
        dollar_floor,
        share_floor,
        order=np.argsort(-np.abs(alpha_vec), kind="stable"),
    )
    alpha_row, _alpha_names = _compute_row(
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
        alpha_keep,
        sides,
        signal_z,
        label,
        flagged_for_veto,
        dollar_floor=dollar_floor,
        share_floor=share_floor,
    )
    row["n_kept_alpha_order"] = int(alpha_keep.sum())
    row["n_eff_kept_alpha_order"] = alpha_row["n_eff_kept"]
    row["n_eff_alpha_gap_pct"] = (
        (float(alpha_row["n_eff_kept"]) - float(row["n_eff_kept"]))
        / float(row["n_eff_kept"])
        * 100.0
    )
    return row, row_names


def _no_floor_row(row: dict[str, object]) -> None:
    """Stamp the no-floor rows with vacuous enforcement columns for a uniform schema."""
    row["n_kept_post_enforcement"] = row["n_kept"]
    row["quant_error_p90_post_enforcement"] = row["quant_error_p90_pct_of_target"]
    row["n_kept_prefix"] = row["n_kept"]
    row["floor_prefix_k"] = row["n_kept"]
    row["floor_prefix_scans"] = 0
    row["n_eff_kept_prefix"] = row["n_eff_kept"]
    row["total_error_share_of_nav_prefix"] = row["total_gross_error_share_of_nav"]
    row["quant_error_p90_pct_of_target_prefix"] = row["quant_error_p90_pct_of_target"]
    row["max_weight_share_of_gross_prefix"] = row["max_weight_share_of_gross"]
    row["net_dollar_share_of_gross_prefix"] = row["net_dollar_share_of_gross"]
    row["n_below_floor_final_pre_enforcement"] = 0
    row["worst_floor_shortfall_shares_pre_enforcement"] = 0.0
    row["worst_floor_shortfall_dollars_pre_enforcement"] = 0.0
    row["n_kept_drop_only"] = row["n_kept"]
    row["n_kept_one_pass_admission"] = row["n_kept"]
    row["admit_cycles"] = 0
    row["admit_passes"] = 0
    row["admit_extra"] = 0
    row["admit_converged"] = True
    row["floor_book_checks"] = "ok"
    row["n_kept_alpha_order"] = row["n_kept"]
    row["n_eff_kept_alpha_order"] = row["n_eff_kept"]
    row["n_eff_alpha_gap_pct"] = 0.0


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
    n_eff_full = full_decomp["effective_breadth"]

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
            dollar_floor=threshold,
        )
        iterative_keep = _iterative_floor(full_weights, nav, threshold)
        post, _post_names = _compute_row(
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
            dollar_floor=threshold,
        )
        row, row_names = _enforce_row(
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
            full_weights,
            signal_z,
            f"min_position_{int(threshold)}",
            False,
            pre,
            post,
            threshold,
            0,
        )
        rows.append(row)
        per_name_rows.extend(row_names)

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
        _no_floor_row(row)
        rows.append(row)
        per_name_rows.extend(row_names)

    prices_full = np.array([close.get(t, 0.0) for t in names])

    # the two-part floor, one pass and at its full-weight fixed point, then
    # enforced on the final weights. Pre and post mean the same thing here as
    # on every dollar row: one-pass versus the full-weight fixed point; the
    # enforced row is the floor checked on the vector that actually trades.
    two_pass_keep = _one_pass_combined_floor(
        full_weights, nav, prices_full, 1500.0, MIN_SHARES_ROW
    )
    two_fixed_keep = _iterative_combined_floor(
        full_weights, nav, prices_full, 1500.0, MIN_SHARES_ROW
    )
    two_pre, _two_pre_names = _compute_row(
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
        two_pass_keep,
        full_weights,
        signal_z,
        "two_part_floor_1500_20shares",
        True,
        dollar_floor=1500.0,
        share_floor=MIN_SHARES_ROW,
    )
    two_post, _two_post_names = _compute_row(
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
        two_fixed_keep,
        full_weights,
        signal_z,
        "two_part_floor_1500_20shares",
        True,
        dollar_floor=1500.0,
        share_floor=MIN_SHARES_ROW,
    )
    two_row, two_row_names = _enforce_row(
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
        full_weights,
        signal_z,
        "two_part_floor_1500_20shares",
        True,
        two_pre,
        two_post,
        1500.0,
        MIN_SHARES_ROW,
    )
    rows.append(two_row)
    per_name_rows.extend(two_row_names)

    # the flagged share-only floor: min 20 shares, no dollar leg. One pass and
    # its full-weight fixed point, then enforced on the final weights.
    share_only_pass = (
        np.abs(full_weights) * nav / np.maximum(prices_full, 1e-12)
    ) >= MIN_SHARES_ROW
    share_only_fixed = _iterative_combined_floor(
        full_weights, nav, prices_full, 0.0, MIN_SHARES_ROW
    )
    share_pre, _share_pre_names = _compute_row(
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
        share_only_pass,
        full_weights,
        signal_z,
        "share_only_20shares",
        True,
        share_floor=MIN_SHARES_ROW,
    )
    share_post, _share_post_names = _compute_row(
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
        share_only_fixed,
        full_weights,
        signal_z,
        "share_only_20shares",
        True,
        share_floor=MIN_SHARES_ROW,
    )
    share_row, share_row_names = _enforce_row(
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
        full_weights,
        signal_z,
        "share_only_20shares",
        True,
        share_pre,
        share_post,
        0.0,
        MIN_SHARES_ROW,
    )
    rows.append(share_row)
    per_name_rows.extend(share_row_names)

    # the full 499-name book as the reference row: no floor, no drop, so it
    # shows whether the raw-beta residual is the signal's tilt or something
    # the drop creates.
    full_keep = np.ones(len(names), dtype=bool)
    full_row, full_names = _compute_row(
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
        full_keep,
        full_weights,
        signal_z,
        "full_book_499",
        False,
    )
    full_row["n_kept_pre_iteration"] = full_row["n_kept"]
    full_row["n_kept_post_iteration"] = full_row["n_kept"]
    full_row["quant_error_p90_pre_iteration"] = full_row[
        "quant_error_p90_pct_of_target"
    ]
    full_row["quant_error_p90_post_iteration"] = full_row[
        "quant_error_p90_pct_of_target"
    ]
    _no_floor_row(full_row)
    rows.append(full_row)
    per_name_rows.extend(full_names)

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


def construction_label(proposal: dict[str, Any]) -> str:
    """The construction, generated only from the artifact's own fields.

    Three readers share this: the Streamlit page, the d10 tab and the snapshot the
    Cloudflare page shows. None of them may assert a label beside an artifact, so
    an artifact that does not record its construction gets told so rather than
    filled in from the registry or the table.
    """
    kind = proposal.get("construction")
    if kind is None:
        return "construction parameters not recorded in this artifact"
    floor_dollars = proposal.get("construction_floor_dollars", 0)
    floor_shares = proposal.get("construction_floor_shares", 0)
    top_n = proposal.get("construction_top_n", 0)
    iterated = bool(proposal.get("floor_iterated"))
    if kind == "min_position":
        label = f"min position ${floor_dollars:,.0f}"
    elif kind == "two_part":
        label = f"min ${floor_dollars:,.0f} and {int(floor_shares)} shares"
    elif kind == "share_only":
        label = f"min {int(floor_shares)} shares"
    elif kind == "top_n":
        label = f"top {int(top_n)} by absolute alpha"
    else:
        label = str(kind)
    if iterated:
        label += " (iterated to a fixed point)"
    else:
        label += " (one pass, not iterated)"
    return label
