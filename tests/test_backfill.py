"""The two repairs a missing GICS row needs: the bars, and the rows they feed.

A name is in the design only when the sector table carries it, so the label going
missing is what stopped BE, ILMN and P - and BE and P also lost eleven sessions of
bars to the vendor in the same window, which no label can fix. These are the tests for
`live.extend.fill_missing_sessions` and `live.extend.variance_for_newcomers`, the two
pieces that write the missing rows without rewriting anyone else's.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from efb import prices as prices_mod
from live import extend

DAYS = pd.bdate_range("2026-09-01", periods=6)
NAMES = ["AAA", "BBB", "CCC"]


def _tree(tmp_path, hole: tuple[str, str] | None = None):
    """A tree with the files the panel loader reads, and one missing bar."""
    root = tmp_path / "tree"
    (root / "raw").mkdir(parents=True)
    (root / "processed").mkdir()
    price_rows = []
    for day in DAYS:
        for index, name in enumerate(NAMES):
            close = 100.0 + index + float(day.day)
            if hole is not None and (str(day.date()), name) == hole:
                close = float("nan")
            price_rows.append(
                {
                    "date": day,
                    "ticker": name,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "adj_close": close,
                    "volume": 1_000.0,
                    "dividend": 0.0,
                    "split_factor": 1.0,
                }
            )
    frame = pd.DataFrame(price_rows).set_index(["date", "ticker"]).sort_index()
    frame.to_parquet(root / "raw" / "prices.parquet")
    returns = frame["close"].groupby(level="ticker").pct_change(fill_method=None)
    # The artifact's own shape: a (date, ticker) index and the five columns, never a
    # long frame with date and ticker as columns.
    long = pd.DataFrame({"r": returns}).reindex(frame.index)
    long["g"] = np.log1p(long["r"])
    long["excess"] = long["r"]
    long["stale"] = False
    long["outlier"] = False
    long.to_parquet(root / "processed" / "returns.parquet")
    pd.DataFrame(
        {"ticker": NAMES, "gics_sector": ["Industrials"] * len(NAMES)}
    ).to_parquet(root / "processed" / "sectors.parquet", index=False)
    pd.DataFrame(True, index=DAYS, columns=NAMES).to_parquet(
        root / "processed" / "universe_membership.parquet"
    )
    pd.DataFrame(
        {
            "date": list(DAYS) * len(NAMES),
            "ticker": [n for n in NAMES for _ in DAYS],
            "close": 100.0,
            "shares": 1e7,
        }
    ).to_parquet(root / "processed" / "market_cap.parquet", index=False)
    pd.DataFrame({"date": DAYS, "rf": 0.0}).to_parquet(
        root / "raw" / "factors_ff.parquet", index=False
    )
    return root


def _bars(names: list[str]) -> pd.DataFrame:
    rows = []
    for day in DAYS[1:]:
        for name in names:
            rows.append(
                {
                    "date": day,
                    "ticker": name,
                    "open": 105.0,
                    "high": 105.0,
                    "low": 105.0,
                    "close": 105.0,
                    "adj_close": 105.0,
                    "volume": 1_000.0,
                    "dividend": 0.0,
                    "split_factor": 1.0,
                }
            )
    return pd.DataFrame(rows).set_index(["date", "ticker"]).sort_index()


def test_a_missing_bar_is_fetched_and_its_return_recomputed(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _tree(tmp_path, hole=("2026-09-02", "AAA"))
    path = root / "raw" / "prices.parquet"
    before = path.read_bytes()
    called: dict[str, object] = {}

    def _download(tickers, **kwargs):
        called["tickers"] = list(tickers)
        called.update(kwargs)
        return _bars(list(tickers))

    monkeypatch.setattr(prices_mod, "download_prices", _download)
    dry = extend.fill_missing_sessions(
        root, ["AAA"], "2026-09-01", "2026-09-08", write=False
    )
    assert dry["filled"] == {"AAA": 1}
    assert path.read_bytes() == before, "a dry run writes nothing"

    report = extend.fill_missing_sessions(root, ["AAA"], "2026-09-01", "2026-09-08")
    assert report["returns_rows"] >= 1
    assert called["threads"] is False, "a hole repair asks single threaded"
    prices = pd.read_parquet(path)
    held = prices.loc[(pd.Timestamp("2026-09-02"), "AAA"), "close"]
    assert held == pytest.approx(105.0)
    returns = pd.read_parquet(root / "processed" / "returns.parquet").reset_index()
    row = returns.loc[
        (pd.to_datetime(returns["date"]) == pd.Timestamp("2026-09-02"))
        & (returns["ticker"] == "AAA")
    ]
    assert not row.empty and row["r"].notna().all(), "the return is no longer a hole"


def test_a_half_applied_repair_is_finished_rather_than_refused(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bar written without its return row is what an interrupted repair leaves."""
    root = _tree(tmp_path)
    monkeypatch.setattr(prices_mod, "download_prices", lambda *a, **k: _bars(["AAA"]))
    report = extend.fill_missing_sessions(root, ["AAA"], "2026-09-01", "2026-09-08")
    assert "AAA" not in report["sessions"], "no bar is missing, only a return row"


def test_only_the_named_names_get_a_variance_row(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _tree(tmp_path)
    xs = root / "models" / "XS-v1"
    xs.mkdir(parents=True)
    specific = pd.DataFrame(
        [
            {
                "date": day,
                "ticker": name,
                "specific_return": 0.01 * (index + 1),
            }
            for day in DAYS
            for index, name in enumerate(NAMES)
        ]
    )
    specific.to_parquet(xs / "specific_returns.parquet", index=False)
    prior = specific.assign(
        specific_var_raw=1e-4,
        specific_var=1e-4,
        bucket="Industrials|1",
        bucket_mean=1e-4,
        n_obs=float(len(DAYS)),
    ).drop(columns=["specific_return"])
    prior.to_parquet(xs / "specific_var.parquet", index=False)

    report = extend.variance_for_newcomers(root, ["CCC"], list(DAYS))
    assert report["names"] == ["CCC"]
    after = pd.read_parquet(xs / "specific_var.parquet")
    others = after.loc[after["ticker"] != "CCC"].reset_index(drop=True)
    untouched = prior.loc[prior["ticker"] != "CCC"].reset_index(drop=True)
    assert others.equals(untouched), "every other name's row is the row it was"
    assert len(after) == len(prior) + len(DAYS), "only the newcomer's rows are added"
    assert set(after.loc[after["ticker"] == "CCC", "specific_var"]) != {1e-4}
