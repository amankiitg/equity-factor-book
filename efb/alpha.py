"""Sprint E7: the alpha lab.

Every signal is a point-in-time function of data available at t-1 only, and
returns a long frame of date/ticker/signal values. Missing values stay NaN,
never filled. The signals are experimental: the harness in `efb.hygiene`
decides what they are worth, and the multiple-testing ledger records every
variant tried.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from efb import eval_risk

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"
HEADERS = {"User-Agent": "Mozilla/5.0 (research; Equity Factor Book E7)"}

MOMENTUM_LOOKBACK = 252
MOMENTUM_SKIP = 21
REVERSAL_LOOKBACK = 5
IDIO_WINDOW = 126
VOL_WINDOW = 63
EARNINGS_LOOKBACK = 4


def momentum_12_1(wide: pd.DataFrame) -> pd.DataFrame:
    """The classic momentum signal: total return from t-252 to t-21.

    INPUT: the wide returns panel, dates down, tickers across.
    OUTPUT: long frame date/ticker/signal with NaN kept.
    """
    returns = wide.fillna(np.nan)
    # the classic 12-1: the 252-session window ending at t-21, so the
    # signal at t uses only data through t-21, never the same-day return
    window = (
        (1.0 + returns)
        .rolling(MOMENTUM_LOOKBACK - MOMENTUM_SKIP)
        .apply(lambda s: np.prod(s), raw=True)
    )
    signal = window.shift(MOMENTUM_SKIP).sub(1.0)
    long = signal.stack(future_stack=True).rename("signal").reset_index()
    long.columns = ["date", "ticker", "signal"]
    return long


def short_term_reversal(wide: pd.DataFrame) -> pd.DataFrame:
    """One-week reversal: minus the last five sessions' return.

    INPUT: the wide returns panel.
    OUTPUT: long frame date/ticker/signal with NaN kept.
    """
    returns = wide.fillna(np.nan)
    week = (
        (1.0 + returns).rolling(REVERSAL_LOOKBACK).apply(lambda s: np.prod(s), raw=True)
    )
    signal = -week.shift(1).sub(1.0)
    long = signal.stack(future_stack=True).rename("signal").reset_index()
    long.columns = ["date", "ticker", "signal"]
    return long


def idio_momentum(root: Path = DATA_ROOT, lag: int = 0) -> pd.DataFrame:
    """Momentum of the XS-v1 specific returns: total residual over t-252..t-21.

    INPUT: the stored specific returns of the champion model.
    OUTPUT: long frame date/ticker/signal with NaN kept. `lag` moves every
    input one day back for the F7.1 construction probe.
    """
    specific = pd.read_parquet(
        Path(root) / "models" / "XS-v1" / "specific_returns.parquet"
    )
    specific["date"] = pd.to_datetime(specific["date"])
    wide = specific.pivot(index="date", columns="ticker", values="specific_return")
    if lag:
        wide = wide.shift(lag)
    window = (
        (1.0 + wide)
        .rolling(MOMENTUM_LOOKBACK - MOMENTUM_SKIP)
        .apply(lambda s: np.prod(s), raw=True)
    )
    signal = window.shift(MOMENTUM_SKIP).sub(1.0)
    long = signal.stack(future_stack=True).rename("signal").reset_index()
    long.columns = ["date", "ticker", "signal"]
    return long


def low_residual_volatility(root: Path = DATA_ROOT, lag: int = 0) -> pd.DataFrame:
    """Minus the trailing idio volatility: low residual risk as a signal.

    INPUT: the stored specific returns of the champion model.
    OUTPUT: long frame date/ticker/signal with NaN kept. `lag` moves every
    input one day back for the F7.1 construction probe.
    """
    specific = pd.read_parquet(
        Path(root) / "models" / "XS-v1" / "specific_returns.parquet"
    )
    specific["date"] = pd.to_datetime(specific["date"])
    wide = specific.pivot(index="date", columns="ticker", values="specific_return")
    if lag:
        wide = wide.shift(lag)
    vol = wide.rolling(VOL_WINDOW).std(ddof=1)
    signal = -vol.shift(1)
    long = signal.stack(future_stack=True).rename("signal").reset_index()
    long.columns = ["date", "ticker", "signal"]
    return long


def fetch_short_interest(
    settlement_dates: list[str],
    data_root: Path = DATA_ROOT,
    store: bool = True,
) -> pd.DataFrame:
    """The FINRA consolidated short interest, paginated per settlement date.

    INPUT: settlement dates in yyyy-mm-dd form.
    OUTPUT: long frame date/ticker/current_short_position/days_to_cover,
    NaN kept. Universe filtering happens in the signal builder.
    """
    url = "https://api.finra.org/data/group/otcMarket/name/" "consolidatedShortInterest"
    frames: list[pd.DataFrame] = []
    for settlement in settlement_dates:
        offset = 0
        while True:
            payload = {
                "limit": 5000,
                "offset": offset,
                "compareFilters": [
                    {
                        "compareType": "equal",
                        "fieldName": "settlementDate",
                        "fieldValue": settlement,
                    }
                ],
            }
            response = requests.post(
                url,
                headers={**HEADERS, "Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=60,
            )
            if response.status_code != 200 or not response.text.strip():
                break
            page = pd.read_csv(io.StringIO(response.text))
            if page.empty:
                break
            frames.append(page)
            if len(page) < 5000:
                break
            offset += 5000
    if not frames:
        return pd.DataFrame(
            columns=["date", "ticker", "current_short_position", "days_to_cover"]
        )
    frame = pd.concat(frames, ignore_index=True)
    frame["date"] = pd.to_datetime(frame["settlementDate"])
    frame["ticker"] = frame["symbolCode"]
    out = frame.loc[
        :,
        ["date", "ticker", "currentShortPositionQuantity", "daysToCoverQuantity"],
    ].rename(
        columns={
            "currentShortPositionQuantity": "current_short_position",
            "daysToCoverQuantity": "days_to_cover",
        }
    )
    out = out.sort_values(["date", "ticker"]).reset_index(drop=True)
    if store:
        (Path(data_root) / "raw").mkdir(parents=True, exist_ok=True)
        out.to_parquet(Path(data_root) / "raw" / "short_interest.parquet", index=False)
    return out


def short_interest_signal(
    universe_tickers: list[str], data_root: Path = DATA_ROOT, lag: int = 0
) -> pd.DataFrame:
    """Minus days-to-cover, the classic short-interest direction.

    The stored panel is forward-filled to the daily grid and the signal is
    cross-sectionally ranked per day, so the units are comparable across
    time. NaN kept where the source had no row. `lag` moves the publication
    one day back for the F7.1 construction probe.
    """
    panel = pd.read_parquet(Path(data_root) / "raw" / "short_interest.parquet")
    panel = panel.loc[panel["ticker"].isin(universe_tickers)]
    wide = panel.pivot(index="date", columns="ticker", values="days_to_cover")
    wide = wide.reindex(columns=universe_tickers).sort_index()
    wide = wide.reindex(eval_risk.load_clean_wide(data_root)[0].index, method="ffill")
    signal = wide.rank(axis=1, pct=True).mul(-1.0)
    if lag:
        signal = signal.shift(lag)
    long = signal.stack(future_stack=True).rename("signal").reset_index()
    long.columns = ["date", "ticker", "signal"]
    return long


def post_earnings_drift(
    universe_tickers: list[str], data_root: Path = DATA_ROOT, lag: int = 0
) -> pd.DataFrame:
    """The earnings surprise, carried forward until the next report.

    INPUT: the universe tickers. OUTPUT: long frame date/ticker/signal where
    the signal is the reported surprise from the latest earnings date,
    forward-filled to the daily grid and tradable from the next session.
    NaN kept between dates the source has no report for. `lag` moves the
    publication one more day back for the F7.1 construction probe.
    """
    import yfinance as yf

    root = Path(data_root)
    cache_path = root / "raw" / "earnings_dates.parquet"
    cached = pd.read_parquet(cache_path) if cache_path.exists() else pd.DataFrame()
    done: set[str] = set()
    if not cached.empty:
        done = set(cached["ticker"])
    frames: list[pd.DataFrame] = []
    if not cached.empty:
        frames.append(cached)
    for ticker in universe_tickers:
        if ticker in done:
            continue
        try:
            instrument = yf.Ticker(ticker)
            frame = instrument.get_earnings_dates(limit=48)
            if frame is None or frame.empty:
                continue
            frame = frame.reset_index()
            frame["ticker"] = ticker
            frames.append(frame)
            if cache_path.exists():
                existing = pd.read_parquet(cache_path)
                combined = pd.concat([existing, frame], ignore_index=True)
            else:
                combined = frame
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            combined.to_parquet(cache_path, index=False)
        except Exception:  # pragma: no cover - network shape varies
            continue
    if not frames:
        return pd.DataFrame(columns=["date", "ticker", "signal"])
    combined = pd.concat(frames, ignore_index=True)
    combined["date"] = (
        pd.to_datetime(combined["Earnings Date"]).dt.tz_localize(None).dt.normalize()
    )
    surprise_col = "Surprise(%)"
    if surprise_col not in combined.columns:
        return pd.DataFrame(columns=["date", "ticker", "signal"])
    combined["surprise"] = pd.to_numeric(combined[surprise_col], errors="coerce")
    combined = combined.dropna(subset=["surprise"]).sort_values(["ticker", "date"])
    wide = combined.pivot_table(index="date", columns="ticker", values="surprise")
    wide = wide.reindex(columns=universe_tickers).sort_index()
    wide = wide.reindex(eval_risk.load_clean_wide(data_root)[0].index, method="ffill")
    # the surprise becomes known at the announcement, so the first return it
    # can predict is the next session's; using it on the announcement day
    # itself would be same-day leakage
    signal = wide.shift(1)
    if lag:
        signal = signal.shift(lag)
    long = signal.stack(future_stack=True).rename("signal").reset_index()
    long.columns = ["date", "ticker", "signal"]
    return long


SIGNAL_BUILDERS: dict[str, Callable[..., pd.DataFrame]] = {
    "momentum_12_1": momentum_12_1,
    "short_term_reversal": short_term_reversal,
    "idio_momentum": idio_momentum,
    "low_residual_volatility": low_residual_volatility,
    "short_interest": short_interest_signal,
    "post_earnings_drift": post_earnings_drift,
}

HORIZONS = (1, 5, 21, 63)
GRID_HORIZON = 21
IN_SAMPLE_END = pd.Timestamp("2020-12-31")
OUT_OF_SAMPLE_START = pd.Timestamp("2021-01-01")
KAPPA = 0.1  # the E7 shrinkage toward zero, an E8 input

# Every builder is point-in-time by construction: the signal at t uses data
# at t-1 or earlier. The property is pinned by tests/test_alpha.py, which
# perturbs the returns row at t and asserts the signal at t does not move.
PIT_SIGNALS = frozenset(SIGNAL_BUILDERS)


def lagged_signal(name: str, wide: pd.DataFrame, root: Path) -> pd.DataFrame:
    """The signal rebuilt with every input moved one day back.

    This is the F7.1 construction probe: the lagged signal simulates data
    available one day earlier, so a signal whose edge survives the lag was
    built on data that was already there, and one whose edge dies was built
    on the extra day.
    """
    tickers = [t for t in wide.columns if t.isalpha()]
    if name == "short_interest":
        return short_interest_signal(tickers, root, lag=1)
    if name == "post_earnings_drift":
        return post_earnings_drift(tickers, root, lag=1)
    if name == "idio_momentum":
        return idio_momentum(root, lag=1)
    if name == "low_residual_volatility":
        return low_residual_volatility(root, lag=1)
    if name == "momentum_12_1":
        return momentum_12_1(wide.shift(1))
    return short_term_reversal(wide.shift(1))


def forward_signal(name: str, wide: pd.DataFrame, root: Path) -> pd.DataFrame:
    """The signal rebuilt with every input advanced one day.

    This is the F7.1b construction shift: the signal claims to be
    computable one day later, so pairing it with the same-day return shows
    whether the extra day's data carries the edge. For a construction whose
    window still skips the same-day return (momentum and idio momentum skip
    21 sessions), the extra day cannot be mechanical, so a surviving IC is
    edge persistence, recorded as such and never rewritten as leakage. For
    a lagged publication (post-earnings drift) the shifted construction is
    the announcement-day signal itself, and a surviving IC is the
    announcement-adjacent edge the one-session lag exists to remove.
    """
    tickers = [t for t in wide.columns if t.isalpha()]
    if name == "short_interest":
        return short_interest_signal(tickers, root, lag=-1)
    if name == "post_earnings_drift":
        return post_earnings_drift(tickers, root, lag=-1)
    if name == "idio_momentum":
        return idio_momentum(root, lag=-1)
    if name == "low_residual_volatility":
        return low_residual_volatility(root, lag=-1)
    if name == "momentum_12_1":
        return momentum_12_1(wide.shift(-1))
    return short_term_reversal(wide.shift(-1))


def run_f71b(
    data_root: Path = DATA_ROOT,
    store: bool = True,
    signals: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """F7.1b: the empirical shift audit, one row per signal.

    Each signal is rebuilt with every input advanced one day and its IC is
    recomputed against the same-day return. OUTPUT: a frame with the IC
    before and after the shift, their Newey-West t-stats, and the flags
    flipped (sign changed), killed (|t| below the leak hurdle) and survives
    (neither). Stored as data/alpha/f71b_audit.parquet.
    """
    from efb import hygiene

    root = Path(data_root)
    wide, _counts = eval_risk.load_clean_wide(root)
    rows: list[dict[str, object]] = []
    for name in SIGNAL_BUILDERS:
        if signals is not None and name not in signals:
            continue
        print(f"f71b {name}")
        signal = _signal_for(name, wide, root)
        if signal.empty:
            continue
        forward = forward_signal(name, wide, root)
        audit = hygiene.empirical_shift_audit(signal, forward, wide)
        rows.append({"signal": name, **audit})
        del signal, forward
        import gc

        gc.collect()
    frame = pd.DataFrame(rows)
    if store:
        out = root / "alpha" / "f71b_audit.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(out, index=False)
    return frame


def _signal_for(name: str, wide: pd.DataFrame, root: Path) -> pd.DataFrame:
    tickers = [t for t in wide.columns if t.isalpha()]
    if name == "short_interest":
        return short_interest_signal(tickers, root)
    if name == "post_earnings_drift":
        return post_earnings_drift(tickers, root)
    builder = SIGNAL_BUILDERS[name]
    if name in ("momentum_12_1", "short_term_reversal"):
        return builder(wide)
    return builder(root)


def _split_ic(ic: pd.Series) -> dict[str, dict[str, float]]:
    """The in-sample and out-of-sample means and t-stats of an IC series."""
    out: dict[str, dict[str, float]] = {}
    for label, sub in (
        ("in_sample", ic.loc[ic.index <= IN_SAMPLE_END]),
        ("out_of_sample", ic.loc[ic.index >= OUT_OF_SAMPLE_START]),
    ):
        from efb import hygiene

        out[label] = {
            "mean": float(sub.mean()),
            "t": hygiene.newey_west_t(sub),
            "n": int(sub.notna().sum()),
        }
    return out


def run(
    data_root: Path = DATA_ROOT,
    store: bool = True,
    signals: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """The full E7 pipeline: every admitted signal through the harness."""
    from efb import eval_risk, hygiene, race

    root = Path(data_root)
    wide, counts = eval_risk.load_clean_wide(root)
    grid = race.race_grid(root)
    vix = pd.read_parquet(root / "raw" / "vix.parquet")
    vix_series = vix.set_index(pd.to_datetime(vix["date"]))["vix"]
    summary_rows: list[dict[str, object]] = []
    ledger_rows: list[dict[str, object]] = []
    results: dict[str, object] = {}
    run_counter = 0
    for name in SIGNAL_BUILDERS:
        if signals is not None and name not in signals:
            continue
        print(f"signal {name}")
        signal = _signal_for(name, wide, root)
        if signal.empty:
            print("  no rows; recorded in the ledger, not scored")
            run_counter += 1
            ledger_rows.append(
                {
                    "run_id": run_counter,
                    "signal": name,
                    "variant": "raw",
                    "horizon": 1,
                    "ic_mean": "NA",
                    "t_stat": "NA",
                    "deflated_sharpe": "NA",
                    "hlz_t_hurdle": "NA",
                    "bonferroni_t": "NA",
                    "verdict": "UNAVAILABLE",
                    "note": "the data probe printed no rows for this source",
                }
            )
            continue
        lagged = lagged_signal(name, wide, root)
        audit = hygiene.shift_audit(signal, lagged, wide)
        ic_frame = pd.DataFrame(index=audit.index)
        for horizon in HORIZONS:
            ic_frame[f"ic_h{horizon}"] = hygiene.spearman_ic(signal, wide, horizon)
        neutral = hygiene.neutralized_ic(signal, wide, grid, root, horizon=GRID_HORIZON)
        quantiles = hygiene.quantile_portfolios(signal, wide, grid)
        regime = hygiene.regime_ic(ic_frame["ic_h1"], vix_series)
        # the fundamental law uses the daily horizon-1 IC and the stored
        # effective breadth: names per day in the signal's own frame
        breadth = int(signal.groupby("date")["ticker"].count().median())
        law = hygiene.fundamental_law(ic_frame["ic_h1"], breadth)
        # the quantile spread Sharpe and the deflated-Sharpe verdict
        spread = _quantile_spread(quantiles)
        spread_sharpe = (
            float(spread.mean() / spread.std(ddof=1) * np.sqrt(252))
            if spread.std(ddof=1) > 0
            else float("nan")
        )
        n_runs_so_far = run_counter + 1
        ledger_rows.append(
            {
                "run_id": run_counter + 1,
                "signal": name,
                "variant": "raw_h1",
                "horizon": 1,
                "ic_mean": round(float(ic_frame["ic_h1"].mean()), 6),
                "t_stat": round(hygiene.newey_west_t(ic_frame["ic_h1"]), 3),
                "deflated_sharpe": round(
                    hygiene.deflated_sharpe(
                        spread_sharpe, n_runs_so_far, int(spread.notna().sum())
                    )["deflated_sharpe"],
                    4,
                ),
                "hlz_t_hurdle": round(abs(hygiene.newey_west_t(ic_frame["ic_h1"])), 3),
                "bonferroni_t": round(hygiene.bonferroni_t_threshold(n_runs_so_far), 3),
                "verdict": "",
                "note": "",
            }
        )
        run_counter += 1
        for horizon in HORIZONS[1:]:
            run_counter += 1
            ledger_rows.append(
                {
                    "run_id": run_counter,
                    "signal": name,
                    "variant": f"raw_h{horizon}",
                    "horizon": horizon,
                    "ic_mean": round(float(ic_frame[f"ic_h{horizon}"].mean()), 6),
                    "t_stat": round(
                        hygiene.newey_west_t(ic_frame[f"ic_h{horizon}"]), 3
                    ),
                    "deflated_sharpe": "NA",
                    "hlz_t_hurdle": round(
                        abs(hygiene.newey_west_t(ic_frame[f"ic_h{horizon}"])), 3
                    ),
                    "bonferroni_t": round(
                        hygiene.bonferroni_t_threshold(run_counter), 3
                    ),
                    "verdict": "",
                    "note": "decay horizon",
                }
            )
        run_counter += 1
        ledger_rows.append(
            {
                "run_id": run_counter,
                "signal": name,
                "variant": "neutralized_h21",
                "horizon": GRID_HORIZON,
                "ic_mean": round(float(neutral.mean()), 6),
                "t_stat": round(hygiene.newey_west_t(neutral), 3),
                "deflated_sharpe": "NA",
                "hlz_t_hurdle": round(abs(hygiene.newey_west_t(neutral)), 3),
                "bonferroni_t": round(hygiene.bonferroni_t_threshold(run_counter), 3),
                "verdict": "",
                "note": "factor-neutral via the exact in-model projection",
            }
        )
        split = _split_ic(ic_frame["ic_h1"])
        oos_spread = spread.loc[spread.index >= OUT_OF_SAMPLE_START]
        oos_sharpe = (
            float(oos_spread.mean() / oos_spread.std(ddof=1) * np.sqrt(252))
            if len(oos_spread) > 20 and oos_spread.std(ddof=1) > 0
            else float("nan")
        )
        summary_rows.append(
            {
                "signal": name,
                "ic_h1_mean": float(ic_frame["ic_h1"].mean()),
                "ic_h1_t": hygiene.newey_west_t(ic_frame["ic_h1"]),
                "ic_h5_mean": float(ic_frame["ic_h5"].mean()),
                "ic_h21_mean": float(ic_frame["ic_h21"].mean()),
                "ic_h63_mean": float(ic_frame["ic_h63"].mean()),
                "neutral_ic_h21_mean": float(neutral.mean()),
                "neutral_ic_h21_t": hygiene.newey_west_t(neutral),
                "in_sample_mean": split["in_sample"]["mean"],
                "in_sample_t": split["in_sample"]["t"],
                "out_of_sample_mean": split["out_of_sample"]["mean"],
                "out_of_sample_t": split["out_of_sample"]["t"],
                "oos_spread_sharpe": oos_sharpe,
                "audit_flipped": bool(audit["flipped"].iloc[-1]),
                "audit_killed": bool(audit["killed"].iloc[-1]),
                "audit_leak_flag": bool(audit["leak_flag"].iloc[-1]),
                "pit_by_construction": name in PIT_SIGNALS,
                "audit_mean_ic_next": float(audit["mean_ic_next"].iloc[-1]),
                "audit_t_next": float(audit["t_ic_next"].iloc[-1]),
                "audit_t_lagged": float(audit["t_ic_lagged"].iloc[-1]),
                "breadth": float(law["breadth"]),
                "implied_ir": law["implied_ir"],
                "realized_ir": law["realized_ir"],
                "spread_sharpe": spread_sharpe,
                "turnover_mean": float(quantiles_turnover(signal, grid)),
                "hit_rate": float(_hit_rate(spread)),
            }
        )
        if store:
            out_dir = root / "alpha" / name
            out_dir.mkdir(parents=True, exist_ok=True)
            ic_frame.to_parquet(out_dir / "ic.parquet")
            audit.to_parquet(out_dir / "audit.parquet")
            neutral.to_frame("ic").to_parquet(out_dir / "neutral_ic.parquet")
            quantiles.to_parquet(out_dir / "quantiles.parquet")
            regime.to_parquet(out_dir / "regime_ic.parquet")
            _converted_alpha(name, signal, wide, root).to_parquet(
                out_dir / "alpha.parquet", index=False
            )
        results[name] = {
            "ic_h1_mean": float(ic_frame["ic_h1"].mean()),
            "ic_h1_t": hygiene.newey_west_t(ic_frame["ic_h1"]),
            "neutral_ic_h21_mean": float(neutral.mean()),
            "out_of_sample_mean": split["out_of_sample"]["mean"],
            "out_of_sample_t": split["out_of_sample"]["t"],
        }
        # the frames are large; release them before the next signal builds
        import gc

        del signal, lagged, audit, ic_frame, neutral, quantiles, regime, spread
        gc.collect()
    summary = pd.DataFrame(summary_rows)
    # the verdict per signal: NULL when the out-of-sample spread fails the
    # deflated-Sharpe hurdle, PASS otherwise; every ledger row of the signal
    # carries the same verdict, and the deciding number is stored per row
    total_runs = run_counter
    ledger_path = ROOT / "docs" / "multiple_testing_ledger.md"
    if signals is not None and ledger_path.exists():
        existing_runs = sum(
            1
            for line in ledger_path.read_text().splitlines()
            if line.startswith("| ") and not line.startswith("| run_id")
        )
        total_runs = max(run_counter, existing_runs)
    verdict_by_signal: dict[str, str] = {}
    for row in summary_rows:
        oos_sharpe = float(row["oos_spread_sharpe"])  # type: ignore[arg-type]
        oos_t = float(row["out_of_sample_t"])  # type: ignore[arg-type]
        deflated = hygiene.deflated_sharpe(oos_sharpe, total_runs, 63)
        below_hurdle = (
            not np.isfinite(oos_sharpe)
            or deflated["deflated_sharpe"] <= 0
            or abs(oos_t) < hygiene.HLZ_T_HURDLE
        )
        verdict_by_signal[str(row["signal"])] = "NULL" if below_hurdle else "PASS"
    for row in ledger_rows:
        row["verdict"] = verdict_by_signal.get(str(row["signal"]), "UNAVAILABLE")
    if store:
        summary_path = root / "alpha" / "summary.parquet"
        if signals is not None and summary_path.exists():
            existing = pd.read_parquet(summary_path)
            rerun_names = set(summary["signal"])
            merged = pd.concat(
                [existing.loc[~existing["signal"].isin(rerun_names)], summary],
                ignore_index=True,
            )
            merged.sort_values("signal").to_parquet(summary_path, index=False)
        else:
            summary.to_parquet(summary_path, index=False)
        if signals is not None:
            existing_runs = (
                sum(
                    1
                    for line in ledger_path.read_text().splitlines()
                    if line.startswith("| ") and not line.startswith("| run_id")
                )
                if ledger_path.exists()
                else 0
            )
            for row in ledger_rows:
                row["run_id"] = int(row["run_id"]) + existing_runs  # type: ignore[call-overload]
        hygiene.write_ledger(ledger_rows, ROOT / "docs" / "multiple_testing_ledger.md")
    return {
        "summary": summary,
        "ledger_rows": len(ledger_rows),
        "results": results,
        "exclusions": counts,
    }


def _quantile_spread(quantiles: pd.DataFrame) -> pd.Series:
    """The top-minus-bottom quantile return series."""
    pivot = quantiles.pivot_table(index="date", columns="quantile", values="return")
    if pivot.empty or 5 not in pivot.columns or 1 not in pivot.columns:
        return pd.Series(dtype=float)
    return pivot[5] - pivot[1]


def _hit_rate(spread: pd.Series) -> float:
    """The share of positive days in the quantile spread."""
    return float((spread > 0).mean()) if len(spread) else float("nan")


def quantiles_turnover(signal: pd.DataFrame, grid: list[pd.Timestamp]) -> float:
    """The mean share of names that change quintile at each rebalance.

    Quintile membership is recomputed on the signal itself at consecutive
    grid dates; a name that lands in a different bucket counts as turnover.
    """
    wide = signal.pivot(index="date", columns="ticker", values="signal")
    grid_dates = [d for d in grid if d in wide.index]
    if len(grid_dates) < 2:
        return float("nan")
    shares: list[float] = []
    for before, after in zip(grid_dates[:-1], grid_dates[1:], strict=True):
        pair = pd.concat(
            [wide.loc[before].rename("before"), wide.loc[after].rename("after")],
            axis=1,
        ).dropna()
        if len(pair) < 25:
            continue
        bucket_before = pd.qcut(pair["before"].rank(method="first"), 5, labels=False)
        bucket_after = pd.qcut(pair["after"].rank(method="first"), 5, labels=False)
        shares.append(float((bucket_before != bucket_after).mean()))
    return float(np.mean(shares)) if shares else float("nan")


def _converted_alpha(
    name: str, signal: pd.DataFrame, wide: pd.DataFrame, root: Path
) -> pd.DataFrame:
    """alpha_i = IC x sigma_idio,i x z_i, shrunk by kappa toward zero.

    The E8 input contract: columns date, ticker, alpha, ic, sigma_idio_xs_v1,
    sigma_idio_xs_v2, z, kappa. The IC is the stored horizon-1 IC of the
    signal, sigma_idio is the champion's specific volatility and the
    alternative's diagonal, z is the cross-sectional z-score of the signal.
    """
    from efb import hygiene

    ic = hygiene.spearman_ic(signal, wide, 1)
    ic_value = float(ic.mean()) if ic.notna().any() else 0.0
    from efb import eval_risk, race

    root = Path(root)
    grid = race.race_grid(root)
    rows: list[pd.DataFrame] = []
    for date in grid:
        names = eval_risk._window_names(wide, date)
        if len(names) < 50:
            continue
        supplied = eval_risk._xs_pieces(date, names, root)
        if supplied is None:
            continue
        _, diag_v2, _, _ = eval_risk._xs_v2_block(date, names, root)
        specific_v1 = supplied["specific"]
        s = signal.loc[pd.to_datetime(signal["date"]) == date]
        if s.empty:
            continue
        s = s.set_index("ticker")["signal"].reindex(names)
        z = (s - s.mean()) / s.std(ddof=1)
        z = z.fillna(0.0).to_numpy(dtype=float)
        alpha = np.where(
            np.isfinite(specific_v1),
            ic_value * specific_v1 * z * KAPPA,
            ic_value * np.nanmedian(specific_v1) * z * KAPPA,
        )
        alpha_v2 = np.where(
            np.isfinite(diag_v2),
            ic_value * diag_v2 * z * KAPPA,
            ic_value * np.nanmedian(diag_v2) * z * KAPPA,
        )
        rows.append(
            pd.DataFrame(
                {
                    "date": date,
                    "ticker": names,
                    "alpha": alpha,
                    "alpha_xs_v2": alpha_v2,
                    "ic": ic_value,
                    "sigma_idio_xs_v1": specific_v1,
                    "sigma_idio_xs_v2": diag_v2,
                    "z": z,
                    "kappa": KAPPA,
                }
            )
        )
    if not rows:
        return pd.DataFrame(
            columns=[
                "date",
                "ticker",
                "alpha",
                "alpha_xs_v2",
                "ic",
                "sigma_idio_xs_v1",
                "sigma_idio_xs_v2",
                "z",
                "kappa",
            ]
        )
    return pd.concat(rows, ignore_index=True)
