"""Sprint E5, Task 0a: the covariance race's rebalance grid, derived.

E4 left this open: the race had 175 windows and its grid was chosen
interactively in Task 2, so `rebuild_e4` versioned the artifact without being
able to reproduce it. The grid the interactive choice approximated is the month
ends where the XS-v1 descriptor and specific-variance artifacts both have rows:
those are the dates the model can price, which is what the race needs. This
module derives them from the artifacts, rebuilds the race from the derivation,
and reports whether F4.3's verdict survives the change.

If the verdict moves, the finding is that F4.3 is grid sensitive, it is stored
as F5.0, and both readings are kept.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from efb import cov, hygiene
from efb.models import fundamental as fx

ROOT = Path(__file__).resolve().parents[1]
MIN_NAMES = 50

# The model needs this much published factor history before a point-in-time
# covariance exists. Windows behind this are skipped for the XS-v1 row only.
MIN_FACTOR_HISTORY = 126

# Sessions of history `next_descriptor_design` needs to build a row that matches
# the one the model will publish. The longest descriptor chain is the beta window
# (252) followed by the residual-volatility window (63), so 400 sessions is
# enough and the build stays a pure function of the window: every descriptor is a
# rolling statistic or a shift, and none of them reaches further back than this.
NEXT_DESIGN_WINDOW = 400

# (date, n_names, n_names the model could not price) for every supplier call,
# so the XS-v1 row can be read knowing how much of it is the model's fallback
_COVERAGE: list[tuple[pd.Timestamp, int, int]] = []
_SKIPPED: list[pd.Timestamp] = []


def race_grid(
    data_root: Path = ROOT / "data", window: int = cov.WINDOW
) -> list[pd.Timestamp]:
    """The month ends the model can price, from the artifacts alone.

    A date qualifies when both the descriptor file and the specific-variance
    file have rows for it, so the design matrix and the diagonal are both
    available on the same day, and when `window` sessions of history exist
    behind it.
    """
    root = Path(data_root)
    descriptors = pd.read_parquet(root / "models" / "XS-v1" / "descriptors.parquet")
    specific = pd.read_parquet(root / "models" / "XS-v1" / "specific_var.parquet")
    returns = pd.read_parquet(root / "processed" / "returns.parquet")
    clean = hygiene.clean_returns(returns)
    sessions = pd.DatetimeIndex(sorted(clean.index.get_level_values("date").unique()))
    shared = sorted(
        set(pd.to_datetime(descriptors["date"]).unique())
        & set(pd.to_datetime(specific["date"]).unique())
    )
    positions = {date: index for index, date in enumerate(sessions)}
    out: list[pd.Timestamp] = []
    for date in shared:
        date = pd.Timestamp(date)
        position = positions.get(date)
        if position is None or position < window:
            continue
        if position + cov.MIN_VARIANCE_DAYS >= len(sessions):
            continue
        out.append(date)
    return out


def _as_of(frame: pd.DataFrame, date: pd.Timestamp) -> pd.Timestamp | None:
    """The most recent artifact date at or before `date`, or None.

    The model publishes on its own month ends and a rebalance does not always
    fall on one. Using the latest date at or before the rebalance is what a
    live run would have used and carries no look-ahead; skipping the date
    instead is what left the first version of this supplier covering 58 of 175
    windows.
    """
    available = pd.DatetimeIndex(sorted(pd.to_datetime(frame["date"]).unique()))
    usable = available[available <= date]
    return None if len(usable) == 0 else pd.Timestamp(usable[-1])


def _fmp_design(date: pd.Timestamp, names: list[str], data_root: Path) -> np.ndarray:
    """The design read from `fmp_weights`, which are portfolio weights.

    Kept for the diagnosis rather than for the race: FMP weights are portfolio
    weights summing to roughly one per factor, so `X S X'` sits orders of
    magnitude below the specific diagonal and the assembled matrix is close to
    singular. That is a specification mismatch, not a numerical accident.
    """
    weights = pd.read_parquet(data_root / "models" / "XS-v1" / "fmp_weights.parquet")
    stamp = _as_of(weights, date)
    weights = weights.loc[pd.to_datetime(weights["date"]) == stamp]
    wide = weights.pivot_table(index="ticker", columns="factor", values="weight")
    factors = list(fx.ESTIMATED_NAMES)
    wide = wide.reindex(index=names, columns=factors)
    return np.nan_to_num(wide.to_numpy(dtype=float), nan=0.0, posinf=0.0, neginf=0.0)


def _sector_codes(data_root: Path) -> pd.Series:
    """The sector label per ticker, from whichever column the file carries."""
    sectors = pd.read_parquet(data_root / "processed" / "sectors.parquet")
    sector_column = [c for c in sectors.columns if c != "ticker"][0]
    return sectors.set_index("ticker")[sector_column]


def _design_from_styles(
    z: pd.DataFrame, names: list[str], codes: pd.Series
) -> np.ndarray:
    """One day's design matrix from its orthogonalized z and the sector map.

    INPUT: the pivot of `value_z_orth` by ticker and descriptor, the names the
    caller wants in the row, and the sector label per ticker. OUTPUT: the
    constant, the six non-market styles and one dummy per estimated sector with
    the reference sector dropped, in `fx.ESTIMATED_NAMES` order.

    Shared by the published row and the row built for the next session, so the
    two cannot assemble the same day differently: a name the cross-section drops
    is a zero row rather than a missing one, and a name with no sector is its
    own string, which matches no dummy.
    """
    styles = [name for name in fx.STYLE_NAMES if name != "market"]
    aligned = z.reindex(index=names, columns=styles)
    design = np.column_stack(
        [np.ones(len(names)), np.nan_to_num(aligned.to_numpy(dtype=float), nan=0.0)]
    )
    labels = codes.reindex(names).astype(str)
    # `SECTOR_FACTORS_ESTIMATED` names sectors by code, while the sector file may
    # hold either the code or the sector name, so both are accepted here
    by_code = {str(code): name for name, code in fx.SECTOR_CODES.items()}
    for factor in fx.SECTOR_FACTORS_ESTIMATED:
        code = factor.replace("sector_", "")
        sector_name = str(by_code.get(code, code))
        column = ((labels == code) | (labels == sector_name)).to_numpy(dtype=float)
        design = np.column_stack([design, column])
    return design


def descriptor_stamp(date: pd.Timestamp, data_root: Path) -> pd.Timestamp | None:
    """The date of the descriptor row the artifact serves for `date`.

    The latest published row at or before `date`, which is what every reader of
    the artifact gets. A run that reports a number measured against that row
    records this beside it, so a row older than the close cannot pass for the
    close's own.
    """
    descriptors = pd.read_parquet(
        Path(data_root) / "models" / "XS-v1" / "descriptors.parquet"
    )
    return _as_of(descriptors, date)


def _descriptor_design(
    date: pd.Timestamp, names: list[str], data_root: Path
) -> np.ndarray:
    """The standardized descriptor matrix plus the sector dummies.

    This is the design the model itself uses and the one that belongs in
    `Sigma = X F X' + D`: the six non-market styles standardized and
    orthogonalized, the market column as the constant the fit uses, and one
    dummy per estimated sector with the reference sector dropped. Column order
    is `fx.ESTIMATED_NAMES`, which is the order the factor covariance is
    stored in.
    """
    descriptors = pd.read_parquet(
        data_root / "models" / "XS-v1" / "descriptors.parquet"
    )
    stamp = _as_of(descriptors, date)
    day = descriptors.loc[pd.to_datetime(descriptors["date"]) == stamp]
    z = day.pivot_table(index="ticker", columns="descriptor", values="value_z_orth")
    return _design_from_styles(z, names, _sector_codes(Path(data_root)))


def _published_z(descriptors: pd.DataFrame, stamp: pd.Timestamp) -> pd.DataFrame:
    """One published row's `value_z_orth`, pivoted by ticker and descriptor."""
    day = descriptors.loc[pd.to_datetime(descriptors["date"]) == stamp]
    return day.pivot_table(index="ticker", columns="descriptor", values="value_z_orth")


def _session_after(date: pd.Timestamp, data_root: Path) -> pd.Timestamp | None:
    """The next session after `date`, or None when the panel stops at `date`.

    Read from the returns artifact's index alone, which is the session grid every
    other frame is reindexed to, so this cannot disagree with the panel a build
    reads. Reading only the index keeps the sparse-replay path off the panel load.
    """
    frame = pd.read_parquet(data_root / "processed" / "returns.parquet", columns=[])
    sessions = pd.DatetimeIndex(frame.index.get_level_values("date").unique())
    ahead = sessions.sort_values()[sessions > date]
    return pd.Timestamp(ahead[0]) if len(ahead) else None


def next_descriptor_design(
    date: pd.Timestamp, names: list[str], data_root: Path
) -> tuple[np.ndarray, str]:
    """The design for the session after `date`, and a label naming its vintage.

    The book built at the close of `date` is held over the next session, so the
    exposures the hedge has to zero are the ones that session carries: the design
    row the model dates with the next session. That row's raw descriptors are
    computed from data through `date`, because every descriptor on a row is a
    shifted quantity, so the row is knowable at this close with one exception.
    `fx.standardize` takes its cross-section over the names priced on the row's
    own date, and that set is fixed by the next session's own prices, which do
    not exist yet. Three readings follow, and the label says which one was used:

    - the model has published the row for the next session, so it is used as it
      stands. It is exactly the object to hedge against. This is the shape a
      replay has when the artifact carries the daily rows.
    - the panel stops at the close, which is the live shape, so the row is built
      here from data through `date` with the cross-section taken as the names
      priced at `date`. The build is exact whenever the priced set does not move
      between the two sessions, which is every ordinary session, and it cannot be
      exact on the session before a market holiday, when the set does move.
      Measured on 2026-09-04 to 2026-09-08 (Labor Day) one name is priced at the
      next close and not at this one, so its z is zero here and a full z there,
      and the traded book is left with 4e-03 of exposure against 5.8e-02 for the
      row dated the close.
    - neither: the tree publishes sparsely, so a live run at that close would have
      published a row this tree does not have (the seed's month ends), or there is
      too little history behind the close to build one. The row dated `date` is
      used, which is what every caller used before this change.

    Always returns a design. A label starting with `stale` means the row dated the
    close was used, so the caller records that this hedge is one session behind.
    """
    from efb import probes  # the shared panel loader that live/extend.py reads

    root = Path(data_root)
    stamp = pd.Timestamp(date)
    descriptors = pd.read_parquet(root / "models" / "XS-v1" / "descriptors.parquet")
    codes = _sector_codes(root)
    published = pd.DatetimeIndex(sorted(pd.to_datetime(descriptors["date"]).unique()))
    stale_stamp = _as_of(descriptors, stamp)
    if stale_stamp is None:
        raise RuntimeError(
            f"the descriptor artifact has no row at or before {stamp.date()}"
        )
    following = _session_after(stamp, root)

    if following is not None and following in published:
        label = f"published {following.date()} (the row the model dated it with)"
        return (
            _design_from_styles(_published_z(descriptors, following), names, codes),
            label,
        )

    if following is not None:
        label = (
            f"stale {stale_stamp.date()} (the panel reaches past the close and the"
            f" model has published no row for {following.date()})"
        )
        return (
            _design_from_styles(_published_z(descriptors, stale_stamp), names, codes),
            label,
        )

    panel = probes.load_panel(root)
    # The *cleaned* panel, because that is what the published rows were built from.
    # A row built here from the raw file would disagree with the row the model
    # publishes for the same session, and the hedge would then be solving for a
    # cross-section that does not exist: measured, every hedge-vintage comparison
    # failed once the published descriptors started coming from the cleaned panel
    # and this builder had not been changed to match. The priced set is read off the
    # same frame the model reads it off, so the two agree on who is in the
    # cross-section as well as on the numbers.
    frame = panel["returns_clean"]
    close = panel["close"]
    volume = panel["volume"]
    shares = panel["shares"]
    mapped = panel["mapped"]
    assert isinstance(frame, pd.DataFrame)
    assert isinstance(close, pd.DataFrame)
    assert isinstance(volume, pd.DataFrame)
    assert isinstance(shares, pd.DataFrame)
    assert isinstance(mapped, list)

    returns = frame[mapped]
    sessions = pd.DatetimeIndex(sorted(returns.index))
    window = sessions[sessions <= stamp][-NEXT_DESIGN_WINDOW:]
    if len(window) < NEXT_DESIGN_WINDOW:
        label = (
            f"stale {stale_stamp.date()} (only {len(window)} sessions behind the"
            f" close, fewer than the {NEXT_DESIGN_WINDOW} the built row needs)"
        )
        return (
            _design_from_styles(_published_z(descriptors, stale_stamp), names, codes),
            label,
        )

    # One synthetic row for the session being described, appended after the close.
    # Its returns encode the cross-section the standardisation is taken over: a
    # number where the name was priced at the close, NaN where it was not. Every
    # descriptor on that row is a shifted quantity, so it reads data through the
    # close and never this row's own values, and the label only has to be later
    # than the close for the shifts to line up.
    row_date = stamp + pd.Timedelta(days=1)
    priced = returns.loc[stamp].notna()
    blank = pd.DataFrame(np.nan, index=[row_date], columns=returns.columns, dtype=float)
    described = blank.copy()
    described.loc[row_date, priced[priced].index] = 0.0

    r = pd.concat([returns.loc[window], described])
    c = pd.concat([close[mapped].loc[window], blank])
    v = pd.concat([volume[mapped].loc[window], blank])
    sh = pd.concat([shares[mapped].loc[window], blank])
    cap = fx.market_cap(c, sh)
    raw = fx.raw_descriptors(r, c, v, cap, fx.market_proxy(r, cap))
    standard: dict[str, pd.DataFrame] = {"market": raw["market"]}
    for name in fx.STYLE_NAMES:
        if name == "market":
            continue
        frame_z, _table, _clipped = fx.standardize(raw[name], r.notna(), cap.shift(1))
        frame_z.columns = r.columns
        standard[name] = frame_z
    orthogonal = fx.orthogonalize(standard, fx.DEFAULT_ORTHOGONALIZATION)
    z = pd.DataFrame(
        {
            name: orthogonal[name].loc[row_date]
            for name in fx.STYLE_NAMES
            if name != "market"
        }
    )
    label = (
        f"built from data through {stamp.date()}"
        f" (cross-section: the {int(priced.sum())} names priced at the close)"
    )
    return _design_from_styles(z, names, codes), label


def design_diagnosis(
    data_root: Path, date: pd.Timestamp | None = None, n_names: int = 60
) -> dict[str, object]:
    """Both candidate designs' column norms and the condition each produces."""
    returns = pd.read_parquet(data_root / "processed" / "returns.parquet")
    clean = hygiene.clean_returns(returns)
    wide = clean.unstack("ticker")
    sectors = pd.read_parquet(data_root / "processed" / "sectors.parquet")
    wide = wide[[c for c in wide.columns if c in set(sectors["ticker"].astype(str))]]
    if date is None:
        date = race_grid(data_root)[100]
    # the names have to be complete over the training window, not over all
    # history: requiring the latter left an empty list on the first date the
    # diagnosis ran on and the median of an empty array raised
    train = wide.loc[:date].iloc[-cov.WINDOW :]
    complete = [c for c in wide.columns if train[c].notna().all()]
    names = complete[:n_names]
    if len(names) < 20:
        raise RuntimeError(
            f"the diagnosis found only {len(names)} complete names on {date.date()}"
        )
    ordered = list(fx.ESTIMATED_NAMES)
    factor_returns = pd.read_parquet(
        data_root / "models" / "XS-v1" / "factor_returns.parquet"
    )
    history = factor_returns.loc[
        (pd.to_datetime(factor_returns["date"]) < date)
        & (factor_returns["factor"].isin(ordered))
    ].pivot_table(index="date", columns="factor", values="f")
    history = history.loc[:, ordered].fillna(0.0)
    covariance = fx.ewma_factor_cov(history, half_life=fx.F_HALF_LIFE)
    latest = (
        covariance.index.get_level_values(0).max()
        if isinstance(covariance.index, pd.MultiIndex)
        else covariance.index.max()
    )
    block = (
        covariance.xs(latest, level=0)
        if isinstance(covariance.index, pd.MultiIndex)
        else covariance.loc[latest]
    )
    block = pd.DataFrame(block).reindex(index=ordered, columns=ordered)
    specific = _specific_for(date, names, data_root)[0]
    out: dict[str, object] = {"date": str(date), "n_names": len(names)}
    for label, design in (
        ("fmp_weights", _fmp_design(date, names, data_root)),
        ("descriptors", _descriptor_design(date, names, data_root)),
    ):
        matrix = cov.factor_cov(design, block.to_numpy(dtype=float), specific)
        norms = np.sqrt((design**2).sum(axis=0))
        factor_part = float(
            np.median(np.diag(design @ block.to_numpy(dtype=float) @ design.T))
        )
        out[label] = {
            "column_norms": [float(value) for value in norms],
            "max_column_norm": float(norms.max()),
            "median_factor_variance": factor_part,
            "median_specific_variance": float(np.median(specific)),
            "ratio": factor_part / float(np.median(specific)),
            "condition_number": condition_or_none(matrix),
        }
    return out


def condition_or_none(matrix: np.ndarray) -> float | None:
    try:
        return cov.condition_number(matrix)
    except np.linalg.LinAlgError:
        return None


def _design_for(date: pd.Timestamp, names: list[str], data_root: Path) -> np.ndarray:
    """The design used by the race: the descriptor matrix, not the FMP weights."""
    return _descriptor_design(date, names, data_root)


def _specific_for(
    date: pd.Timestamp, names: list[str], data_root: Path
) -> tuple[np.ndarray, int]:
    specific = pd.read_parquet(data_root / "models" / "XS-v1" / "specific_var.parquet")
    stamp = _as_of(specific, date)
    specific = specific.loc[pd.to_datetime(specific["date"]) == stamp]
    series = specific.set_index("ticker")["specific_var"]
    aligned = series.reindex(names)
    return aligned.to_numpy(dtype=float), int(aligned.isna().sum())


def xs_supplier(
    date: pd.Timestamp, names: list[str], data_root: Path
) -> dict[str, object] | None:
    """What the race needs for the XS-v1 row: design, factor covariance, diagonal.

    XS-v1 is the one estimator that cannot be built from the window alone, and
    it should not be: its design and its diagonal are the model's own
    artifacts. The factor covariance is estimated from the model's factor
    returns **up to the day before the rebalance**, with the model's own
    half-life, because `factor_cov.parquet` holds one full-sample snapshot and
    using that snapshot for every window would put look-ahead into the row.
    """
    factor_returns = pd.read_parquet(
        data_root / "models" / "XS-v1" / "factor_returns.parquet"
    )
    factor_returns = factor_returns.loc[pd.to_datetime(factor_returns["date"]) < date]
    if factor_returns["date"].nunique() < MIN_FACTOR_HISTORY:
        # The model has not published enough factor history to estimate a
        # covariance without look-ahead. The row is skipped and counted rather
        # than filled with the full-sample snapshot, which is what would make
        # the race flattering in exactly the way this sprint exists to detect.
        _SKIPPED.append(date)
        return None
    history = factor_returns.pivot_table(index="date", columns="factor", values="f")
    ordered = list(fx.ESTIMATED_NAMES)
    if not set(ordered).issubset(history.columns):
        raise RuntimeError("the stored factor returns do not cover every factor")
    # a sector factor is not estimated on every early date. An EWMA carries a
    # single NaN through the whole covariance, and dropping the incomplete rows
    # emptied the history entirely on dates where one sector had no estimate, so
    # a date with no estimate is treated as a zero factor return: the associated
    # design column then enters with a zero-variance factor and contributes no
    # risk, which is the honest reading of a sector the model did not estimate.
    history = history.loc[:, ordered].fillna(0.0)
    factor_covariance = fx.ewma_factor_cov(
        history.loc[:, ordered], half_life=fx.F_HALF_LIFE
    )
    # `ewma_factor_cov` returns the K x K block itself, labelled by factor, not a
    # date-indexed stack of blocks: its index IS the factor list. Reading it as a
    # stack and taking `index.max()` picked one row of the matrix and reindexed
    # that into (K, K), which is 272 of 289 cells NaN, so every window failed the
    # finiteness check below and the XS-v1 row was absent from the race on every
    # date. Measured 2026-10-03 on 2026-08-31: block (17, 17) with 272 NaN; with
    # the block read as the matrix it is (17, 17), 0 NaN, finite.
    block = pd.DataFrame(factor_covariance).reindex(index=ordered, columns=ordered)
    if block.shape != (len(ordered), len(ordered)):
        raise RuntimeError(f"the factor covariance block is {block.shape}")
    if not np.isfinite(block.to_numpy(dtype=float)).all():
        # a non-finite covariance is a real reason to skip the window, and it is
        # reported rather than silently flattened: the whole point of the
        # finiteness check is that the row says what it was built from.
        _SKIPPED.append(date)
        return None
    design = _design_for(date, names, data_root)
    specific, missing = _specific_for(date, names, data_root)
    # A name the model cannot price on this date gets no factor exposure and the
    # cross-sectional median of the model's own diagonal, which is the fallback
    # the model itself uses for an unmodelled name. The count is returned so the
    # race's row can be read knowing how much of it is the fallback.
    unmodelled = int(np.isnan(design).any(axis=1).sum())
    # `nan_to_num` alone maps an infinite entry to 1.8e308, which makes the
    # assembled matrix non-finite and `eigvalsh` fail with "did not converge"
    # rather than with the reason. Both infinities and NaNs become no exposure,
    # which is the model's own treatment of a name it cannot price.
    design = np.nan_to_num(design, nan=0.0, posinf=0.0, neginf=0.0)
    median_specific = float(np.nanmedian(specific))
    specific = np.where(np.isnan(specific), median_specific, specific)
    specific = np.nan_to_num(specific, nan=median_specific, posinf=0.0, neginf=0.0)
    covariance = block.to_numpy(dtype=float)
    blocks = (
        ("design", design),
        ("factor covariance", covariance),
        ("specific", specific),
    )
    if not all(np.isfinite(values).all() for _label, values in blocks):
        _SKIPPED.append(date)
        return None
    _COVERAGE.append((date, len(names), unmodelled + missing))
    return {
        "design": design,
        "factor_covariance": covariance,
        "specific": specific,
    }


def run(data_root: Path = ROOT / "data", store: bool = True) -> dict[str, object]:
    """Rebuild the race on the derived grid and compare F4.3 before and after."""
    root = Path(data_root)
    grid = race_grid(root)
    returns = pd.read_parquet(root / "processed" / "returns.parquet")
    sectors = pd.read_parquet(root / "processed" / "sectors.parquet")
    universe = set(pd.Series(sectors["ticker"]).astype(str))
    print("### Task 0a: the race grid, derived from the artifacts")
    print(f"rebalance dates {len(grid)} from {grid[0].date()} to {grid[-1].date()}")
    gaps = pd.Series(grid).diff().dt.days.dropna()
    print(
        f"median gap {gaps.median():.0f} days, min {gaps.min():.0f}, "
        f"max {gaps.max():.0f}"
    )

    race = cov.horse_race(
        returns,
        grid,
        xs_supplier=lambda date, names: xs_supplier(date, names, root),
        min_names=MIN_NAMES,
        universe=universe,
    )
    print(
        f"race rows {len(race)} across {race['date'].nunique()} dates and "
        f"{race['estimator'].nunique()} estimators"
    )
    if race.empty:
        raise RuntimeError("the derived grid produced no race rows")

    pivot = race.pivot(index="date", columns="estimator", values="realized_vol")
    medians = pivot.median()
    wins = (pivot.rank(axis=1, method="min") == 1).sum()
    table = pd.DataFrame({"median_realized_vol": medians, "windows_won": wins})
    print(table.round(6).to_string())

    stored = pd.read_parquet(root / "eval" / "cov_horse_race.parquet")
    stored_pivot = stored.pivot(
        index="date", columns="estimator", values="realized_vol"
    )
    stored_medians = stored_pivot.median()
    derived_path = root / "eval" / "cov_horse_race_derived_grid.parquet"
    race.to_parquet(derived_path, index=False)
    comparison = pd.DataFrame(
        {
            "stored_median": stored_medians,
            "derived_median": medians,
            "stored_windows": stored_pivot.notna().sum(),
            "derived_windows": pivot.notna().sum(),
        }
    )
    comparison["median_ratio"] = (
        comparison["derived_median"] / comparison["stored_median"]
    )
    print()
    print("stored against derived")
    print(comparison.round(6).to_string())

    ranked = table.sort_values("median_realized_vol")
    top = list(ranked.index[:4])
    factors = [
        name for name in ("ts_v1", "xs_v1", "pca_v1", "pca_v1c") if name in medians
    ]
    ratios = {
        name: float(medians[name] / medians["sample"])
        for name in (*factors, "clip", "constant_correlation", "ledoit_wolf")
    }
    worst = max(ratios.values())
    verdict = "pass" if worst <= 0.9 else "fail"
    stored_verdict = "pass"
    if store:
        race.to_parquet(root / "eval" / "cov_horse_race.parquet", index=False)
    print()
    print(
        f"F4.3 worst ratio on the derived grid {worst:.4f}, verdict {verdict}; "
        f"stored verdict {stored_verdict}"
    )
    print(f"top four by median: {top}")
    moved = verdict != stored_verdict
    if moved:
        print("STOP CONDITION 1: the derived grid moved F4.3's verdict, stored as F5.0")
    payload = {
        "n_dates": len(grid),
        "first_date": str(grid[0].date()),
        "last_date": str(grid[-1].date()),
        "median_gap_days": float(gaps.median()),
        "worst_ratio": worst,
        "derived_verdict": verdict,
        "stored_verdict": stored_verdict,
        "moved": moved,
        "medians": {k: float(v) for k, v in medians.items()},
        "windows_won": {k: int(v) for k, v in wins.items()},
        "median_ratio_to_stored": {
            k: float(v) for k, v in comparison["median_ratio"].items()
        },
    }
    (root / "eval" / "e5_race_grid.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )
    return payload
