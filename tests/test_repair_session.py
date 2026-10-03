"""The one-session repair: what it changes, what it must not.

The tree here is synthetic and small: sixty names over 280 sessions, a market
factor plus idiosyncratic noise, and one session in the middle where a name's
return is a spinoff print (-83.8%, flagged `outlier`) rather than a return. The
artifacts are built from that dirty panel exactly as the live extension builds
them, and then the repair runs on it.

A second tree holds the same panel with no print at all, so the repaired risk
estimate can be compared against what the model would have said had the vendor
reported the spinoff as the corporate action it was rather than as a price.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from efb import alpha as alpha_mod
from efb import probes
from efb.models import fundamental as fx
from live import appendix, extend, store
from scripts import repair_session

NAMES = [f"N{index:02d}" for index in range(60)]
# The design needs 231 sessions of history before its first cross-section (momentum
# is a 231-session product) and the signal needs 231 sessions after that, so the
# panel has to be long enough for both or there is nothing to repair.
SESSIONS = 600
PRINT_SESSION = 500
PRINT_TICKER = "N07"
PRINT_RETURN = -0.838
SECTORS = ("Tech", "Energy", "Health")
DATES = pd.bdate_range("2024-01-01", periods=SESSIONS)
SESSION = DATES[PRINT_SESSION]


def _synthetic_tree(root: Path, *, with_print: bool) -> None:
    """A panel with one flagged spinoff print."""
    (root / "raw").mkdir(parents=True)
    (root / "processed").mkdir(parents=True)
    (root / "models" / "XS-v1").mkdir(parents=True)
    rng = np.random.default_rng(7)
    market = pd.Series(rng.normal(0.0004, 0.008, SESSIONS), index=DATES)
    beta = pd.Series(np.linspace(0.6, 1.4, len(NAMES)), index=NAMES)
    noise = rng.normal(0.0, 0.006, (SESSIONS, len(NAMES)))
    returns = pd.DataFrame(
        market.to_numpy()[:, None] * beta.to_numpy()[None, :] + noise,
        index=DATES,
        columns=NAMES,
    )
    if with_print:
        returns.iloc[PRINT_SESSION, NAMES.index(PRINT_TICKER)] = PRINT_RETURN
    level = 50.0 * (1.0 + returns).cumprod()
    stacked = returns.stack(future_stack=True)
    stacked.index = stacked.index.set_names(["date", "ticker"])

    long = stacked.rename("r").reset_index().set_index(["date", "ticker"])
    long["g"] = np.log1p(long["r"])
    long["excess"] = long["r"]
    long["stale"] = False
    long["outlier"] = False
    if with_print:
        long.loc[(SESSION, PRINT_TICKER), "outlier"] = True
    long.to_parquet(root / "processed" / "returns.parquet")

    closes = level.stack(future_stack=True)
    closes.index = closes.index.set_names(["date", "ticker"])
    prices = pd.DataFrame({"close": closes})
    prices["volume"] = 1_000_000.0
    prices.to_parquet(root / "raw" / "prices.parquet")

    pd.DataFrame(
        {
            "ticker": NAMES,
            "gics_sector": [
                SECTORS[index % len(SECTORS)] for index in range(len(NAMES))
            ],
        }
    ).to_parquet(root / "processed" / "sectors.parquet", index=False)
    pd.DataFrame(True, index=DATES, columns=NAMES).to_parquet(
        root / "processed" / "universe_membership.parquet"
    )
    pd.DataFrame(
        {
            "ticker": NAMES * SESSIONS,
            "date": list(DATES) * len(NAMES),
            "shares": 1_000_000.0,
        }
    ).to_parquet(root / "raw" / "shares_history.parquet", index=False)


def _seed_artifacts(root: Path) -> None:
    """The first session's rows, so `extend_model` has somewhere to append from."""
    inputs = probes.load_panel(root)
    returns = inputs["returns"]
    close = inputs["close"]
    volume = inputs["volume"]
    shares = inputs["shares"]
    look_ahead = inputs["look_ahead"]
    sectors = inputs["sectors"]
    mapped = inputs["mapped"]
    assert isinstance(returns, pd.DataFrame)
    assert isinstance(close, pd.DataFrame)
    assert isinstance(volume, pd.DataFrame)
    assert isinstance(shares, pd.DataFrame)
    assert isinstance(look_ahead, pd.DataFrame)
    assert isinstance(sectors, pd.Series)
    assert isinstance(mapped, list)
    cap = fx.market_cap(close[mapped], shares[mapped])
    proxy = fx.market_proxy(returns[mapped], cap)
    design = fx.build_design(
        returns=returns[mapped],
        close=close[mapped],
        volume=volume[mapped],
        market_cap=cap,
        sectors=sectors,
        proxy=proxy,
    )
    first = design.days[0]
    xs = root / "models" / "XS-v1"
    extend._descriptor_rows_for_dates(
        design, [first.date], look_ahead[mapped], mapped
    ).to_parquet(xs / "descriptors.parquet", index=False)
    tables = fx.fit_panel(
        fx.DesignResult(
            factor_names=design.factor_names,
            days=[first],
            standardized=design.standardized,
            stats=design.stats,
        )
    )
    tables["factor_returns"].assign(date=first.date).to_parquet(
        xs / "factor_returns.parquet", index=False
    )
    tables["specific_returns"].assign(date=first.date).to_parquet(
        xs / "specific_returns.parquet", index=False
    )
    tables["xs_r2"].assign(date=first.date).to_parquet(
        xs / "xs_r2.parquet", index=False
    )
    pd.DataFrame(
        columns=[
            "date",
            "ticker",
            "specific_var_raw",
            "specific_var",
            "bucket",
            "bucket_mean",
            "n_obs",
        ]
    ).to_parquet(xs / "specific_var.parquet", index=False)
    factor_wide = (
        tables["factor_returns"]
        .assign(date=first.date)
        .pivot(index="date", columns="factor", values="f")
        .reindex(columns=list(fx.FACTOR_NAMES))
        .dropna()
    )
    fx.ewma_factor_cov(factor_wide, half_life=fx.F_HALF_LIFE).to_parquet(
        xs / "factor_cov.parquet"
    )


def _build_tree(root: Path, *, with_print: bool) -> None:
    _synthetic_tree(root, with_print=with_print)
    _seed_artifacts(root)
    extend.extend_model(root)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _variance(root: Path, session: pd.Timestamp, ticker: str) -> float:
    frame = pd.read_parquet(root / "models" / "XS-v1" / "specific_var.parquet")
    block = frame.loc[
        (pd.to_datetime(frame["date"]) == session) & (frame["ticker"] == ticker)
    ]["specific_var"]
    return float(block.iloc[0]) if len(block) else float("nan")


def _specific_return(root: Path, session: pd.Timestamp, ticker: str) -> float:
    frame = pd.read_parquet(root / "models" / "XS-v1" / "specific_returns.parquet")
    block = frame.loc[
        (pd.to_datetime(frame["date"]) == session) & (frame["ticker"] == ticker)
    ]["specific_return"]
    return float(block.iloc[0]) if len(block) else float("nan")


@pytest.fixture
def trees(tmp_path: Path) -> tuple[Path, Path]:
    dirty = tmp_path / "dirty"
    clean = tmp_path / "clean"
    dirty.mkdir()
    clean.mkdir()
    _build_tree(dirty, with_print=True)
    _build_tree(clean, with_print=False)
    return dirty, clean


def test_the_repair_takes_the_print_out_of_the_fit_and_leaves_the_record(
    trees: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fitted row goes, the print stays, every earlier session stays too.

    A nulled row is not the same thing as the clean tree: a name with no return
    that session is out of that session's cross-section, where the clean tree has
    it priced. So the fitted value is compared as an absence and the risk estimate
    as a level, and the byte comparisons are what pin that nothing else moved.
    """
    dirty, clean = trees
    fitted_before = _specific_return(dirty, SESSION, PRINT_TICKER)
    variance_before = _variance(dirty, SESSION, PRINT_TICKER)
    assert float(fitted_before) < -0.5, "the print is in the fitted rows to start"
    returns_before = _file_hash(dirty / "processed" / "returns.parquet")

    writes: list[tuple[str, str, list[dict]]] = []
    monkeypatch.setattr(
        store,
        "replace_by_date",
        lambda table, on, rows: writes.append((table, str(on), list(rows))),
    )

    report = repair_session.repair(dirty, PRINT_TICKER, SESSION, write=True)

    assert pd.isna(_specific_return(dirty, SESSION, PRINT_TICKER))

    # the print and its flag are the record: neither is touched
    assert _file_hash(dirty / "processed" / "returns.parquet") == returns_before
    raw = pd.read_parquet(dirty / "processed" / "returns.parquet")
    assert raw.loc[(SESSION, PRINT_TICKER), "r"] == pytest.approx(PRINT_RETURN)
    assert bool(raw.loc[(SESSION, PRINT_TICKER), "outlier"]) is True

    # the inflated variance is gone, and the level is the clean tree's
    variance_after = _variance(dirty, SESSION, PRINT_TICKER)
    clean_variance = _variance(clean, SESSION, PRINT_TICKER)
    assert clean_variance > 0.0, "the clean tree has no estimate to compare against"
    assert variance_after < 0.1 * variance_before
    assert variance_after == pytest.approx(clean_variance, rel=0.35)
    assert report["variance_before"] == pytest.approx(variance_before, rel=1e-9)
    assert report["variance_after"] == pytest.approx(variance_after, rel=1e-9)
    assert (
        report["history_hash_before"] == report["history_hash_after"]
    ), "the repair moved a session it was not asked to move"
    assert report["returns_untouched"] is True

    # the appendix got this session, one table at a time, with no fitted row for
    # the name that could not be priced. `e11_factor_cov` is not written: it holds
    # no rows for any date, because the publish path filters the dateless
    # snapshot's 1970-01-01 stamp out against the seed cutoff before it can be
    # restamped, so there is nothing there to replace and inventing the table's
    # first rows is not a repair. The covariance the book hedges with is
    # recomputed from the factor returns.
    assert {table for table, _on, _rows in writes} == {
        "e11_descriptors",
        "e11_factor_returns",
        "e11_specific_returns",
        "e11_specific_var",
    }
    for table, on, rows in writes:
        assert on == str(SESSION.date())
        assert len(rows) > 0
        if table == "e11_specific_returns":
            for row in rows:
                if row["ticker"] == PRINT_TICKER:
                    assert row["specific_return"] is None or pd.isna(
                        row["specific_return"]
                    ), "the appendix kept a fitted specific return for the repair"


def test_the_repaired_session_is_out_of_the_signal_window(
    trees: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A window holding the null is null, which the contract reads as no signal.

    This is why the repair is not cosmetic: `idio_momentum` is a product of 231
    stored specific returns ending 21 sessions back, so a persisted print reaches
    the signal for a year. Nulled, the window is null and `build_proposal` fills
    that name's z-score with zero, which is a target of zero rather than a short.
    """
    dirty, _clean = trees
    session = DATES[PRINT_SESSION]
    later = DATES[PRINT_SESSION + 25]

    before = alpha_mod.idio_momentum(dirty)
    before = before.loc[
        (pd.to_datetime(before["date"]) == later) & (before["ticker"] == PRINT_TICKER),
        "signal",
    ]
    assert len(before) == 1 and np.isfinite(float(before.iloc[0]))

    monkeypatch.setattr(store, "replace_by_date", lambda *args, **kwargs: None)
    repair_session.repair(dirty, PRINT_TICKER, session, write=True)

    after = alpha_mod.idio_momentum(dirty)
    fixed = after.loc[
        (pd.to_datetime(after["date"]) == later) & (after["ticker"] == PRINT_TICKER),
        "signal",
    ]
    assert len(fixed) == 1 and pd.isna(
        fixed.iloc[0]
    ), "the day still reaches the signal window"

    # the names whose window is intact are still priced: one nulled cell does not
    # blank the cross-section
    day = after.loc[pd.to_datetime(after["date"]) == later]
    day = day.set_index("ticker")["signal"]
    others = day.drop(index=PRINT_TICKER, errors="ignore").dropna()
    assert len(others) >= 50


def test_a_refit_row_for_the_masked_name_is_replaced_not_duplicated() -> None:
    """The collision that reaches Postgres as a unique-key violation.

    A refit still emits a row for the masked name wherever the value is a
    function of the cross-section rather than of that name's own return, so the
    explicit null row cannot simply be appended: the store deletes the date and
    then inserts it without an upsert, and two rows for one key arrive as a
    failure *after* the delete, which reads as a half-repaired date.
    """
    session = DATES[PRINT_SESSION]
    other = NAMES[8]
    keyed = pd.DataFrame(
        {
            "date": [session, session, session, session],
            "ticker": [PRINT_TICKER, other, PRINT_TICKER, other],
            "descriptor": ["market", "market", "size", "size"],
            "value_z": [1.0, 0.2, -1.4, 0.3],
        }
    )
    repaired = pd.DataFrame(
        {
            "date": [session, session],
            "ticker": [PRINT_TICKER, other],
            "descriptor": ["market", "market"],
            "value_z": [np.nan, 0.25],
        }
    )

    out = repair_session._with_repaired_session(
        keyed, session, repaired, PRINT_TICKER, null_the_ticker=True
    )
    keys = ["date", "ticker", "descriptor"]
    assert not out.duplicated(subset=keys).any(), "two rows for one key"
    mine = out.loc[out["ticker"] == PRINT_TICKER, "value_z"]
    assert len(mine) == 1 and pd.isna(mine.iloc[0]), "the masked name kept a value"

    # a refit that hands the same key twice is refused here, not by the database
    doubled = pd.concat([repaired, repaired.iloc[[1]]], ignore_index=True)
    with pytest.raises(SystemExit, match="share a key"):
        repair_session._with_repaired_session(
            keyed, session, doubled, PRINT_TICKER, null_the_ticker=True
        )


def test_the_appendix_payload_is_one_session_and_loses_no_rows(
    trees: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete scope and insert scope have to be the same date, key for key."""
    dirty, _clean = trees
    spec_by_table = {spec.table: spec for spec in appendix.SPECS}
    before = {
        spec.table: int(
            (
                pd.to_datetime(
                    pd.read_parquet(
                        dirty / "models" / "XS-v1" / f"{spec.name}.parquet"
                    )["date"]
                )
                == SESSION
            ).sum()
        )
        for spec in appendix.SPECS
        if spec.name in repair_session.APPENDIX_INPUTS
    }

    writes: list[tuple[str, str, list[dict]]] = []
    monkeypatch.setattr(
        store,
        "replace_by_date",
        lambda table, on, rows: writes.append((table, str(on), list(rows))),
    )
    repair_session.repair(dirty, PRINT_TICKER, SESSION, write=True)

    assert {table for table, _on, _rows in writes} == set(before)
    for table, on, rows in writes:
        assert on == str(SESSION.date())
        frame = pd.DataFrame(rows)
        spec = spec_by_table[table]
        keys = [column for column in spec.key if column in frame.columns]
        assert keys == list(spec.key), f"{table} payload is missing a key column"
        dates = {
            str(pd.Timestamp(value).date()) for value in frame[appendix.DATE_COLUMN]
        }
        assert dates == {str(SESSION.date())}, f"{table} payload reaches {dates}"
        assert not frame.duplicated(subset=keys).any(), f"{table} has a duplicate key"
        assert (
            len(frame) == before[table]
        ), f"{table}: {before[table]} rows before the repair, {len(frame)} after"


def test_the_repair_is_a_fixed_point_on_a_session_it_already_repaired(
    trees: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rerun after a partial failure rewrites the same rows and nothing else.

    The tree it runs on already carries a repaired session, so the artifacts it
    writes have to be the ones that were already there, byte for byte, and the
    session it refits has to hash to itself.
    """
    _dirty, clean = trees
    monkeypatch.setattr(store, "replace_by_date", lambda *args, **kwargs: None)

    first = repair_session.repair(clean, PRINT_TICKER, SESSION, write=True)
    second = repair_session.repair(clean, PRINT_TICKER, SESSION, write=True)

    assert (
        first["session_hash_before"] != first["session_hash_after"]
    ), "the first run did not change the session"
    assert second["file_hash_before"] == first["file_hash_after"]
    assert second["file_hash_after"] == first["file_hash_after"]
    assert second["session_hash_before"] == second["session_hash_after"]
    assert second["history_hash_before"] == second["history_hash_after"]


def test_the_mask_removes_the_one_cell_and_leaves_other_flagged_ones(
    tmp_path: Path,
) -> None:
    """The loader-parity cleaning is a different fix, and this repair may not be it.

    `extend_model` fits `probes.load_panel` as it stands, flagged rows and all, so
    a re-fit that cleans the frame first fits the session under rules its
    neighbours were never fitted under. It is visible too: MRNA carries a flag on
    the real 2026-10-01, and cleaning removes its row from the appendix for that
    date while the repair is only asked to correct one name.
    """
    root = tmp_path / "flagged"
    root.mkdir()
    _build_tree(root, with_print=True)
    path = root / "processed" / "returns.parquet"
    frame = pd.read_parquet(path)
    other = NAMES[8]
    frame.loc[(SESSION, other), "outlier"] = True
    frame.to_parquet(path)

    panel = repair_session.masked_panel(root, PRINT_TICKER, SESSION)
    returns = panel["returns"]
    assert isinstance(returns, pd.DataFrame)
    assert pd.isna(returns.loc[SESSION, PRINT_TICKER]), "the target cell survived"
    assert returns.loc[SESSION, other] == pytest.approx(
        float(frame.loc[(SESSION, other), "r"])
    ), "the mask reached a cell it was not asked about"


def _correct_the_print(root: Path, clean: Path) -> None:
    """Put the clean panel's return into the printed cell of `root`'s panel.

    This is what a recorded corporate action does to the real panel: the cell stops
    being a print and becomes the name's own return, so a refit has something real to
    keep while the stored artifacts still hold the print's fit.
    """
    corrected = float(
        pd.read_parquet(clean / "processed" / "returns.parquet").loc[
            (SESSION, PRINT_TICKER), "r"
        ]
    )
    path = root / "processed" / "returns.parquet"
    frame = pd.read_parquet(path)
    frame.loc[(SESSION, PRINT_TICKER), "r"] = corrected
    frame.loc[(SESSION, PRINT_TICKER), "outlier"] = False
    frame.to_parquet(path)


def test_the_refit_keeps_the_name_and_its_row(
    trees: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the cell corrected, the name stays in the session it was corrected for.

    The masked mode refits the session *without* the name, which is the right answer
    when the cell is a print nothing explains and the wrong one once a recorded
    corporate action has put the true return back in the panel: masking here throws
    a real observation away. The panel below carries the name's own return for that
    session, as the corrected panel does, the refit keeps every name, and the fitted
    value is the level the clean panel gives rather than the print's.
    """
    dirty, clean = trees
    _correct_the_print(dirty, clean)
    path = dirty / "processed" / "returns.parquet"
    returns_before = _file_hash(path)

    writes: list[tuple[str, str, list[dict]]] = []
    monkeypatch.setattr(
        store,
        "replace_by_date",
        lambda table, on, rows: writes.append((table, str(on), list(rows))),
    )

    report = repair_session.repair(dirty, PRINT_TICKER, SESSION, write=True, mask=False)

    assert report["mode"] == "refit"
    # the corner the masked mode gets wrong: the name is priced, not nulled
    value = _specific_return(dirty, SESSION, PRINT_TICKER)
    assert np.isfinite(value), "the refit nulled the name it was asked about"
    assert value == pytest.approx(
        _specific_return(clean, SESSION, PRINT_TICKER), rel=0.35
    ), "the refit's value is not the level the clean panel gives"
    # and the appendix carries that value rather than an explicit null row
    kept = [
        row
        for table, _on, rows in writes
        if table == "e11_specific_returns"
        for row in rows
        if row["ticker"] == PRINT_TICKER
    ]
    assert len(kept) == 1, "the appendix lost the name's own row"
    assert kept[0]["specific_return"] is not None
    assert np.isfinite(float(kept[0]["specific_return"]))

    # the print's own record and every earlier session are still untouched
    assert report["returns_untouched"] is True
    assert _file_hash(path) == returns_before
    assert report["history_hash_before"] == report["history_hash_after"]


def test_a_second_refit_changes_nothing(
    trees: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refit twice on a corrected panel: the second run rewrites the same rows.

    The masked mode has its fixed-point test; this is the refit mode's. The stored
    session still holds the print's fit, so the first run has to change it and the
    second has to hash to itself, with every earlier session untouched and no key
    gained or lost.
    """
    dirty, clean = trees
    _correct_the_print(dirty, clean)
    monkeypatch.setattr(store, "replace_by_date", lambda *args, **kwargs: None)

    first = repair_session.repair(dirty, PRINT_TICKER, SESSION, write=True, mask=False)
    second = repair_session.repair(dirty, PRINT_TICKER, SESSION, write=True, mask=False)

    assert (
        first["session_hash_before"] != first["session_hash_after"]
    ), "the first run did not change the session the print was fitted into"
    assert second["session_hash_before"] == second["session_hash_after"]
    assert second["session_hash_before"] == first["session_hash_after"]
    assert second["file_hash_after"] == first["file_hash_after"]
    assert second["history_hash_before"] == second["history_hash_after"]
    assert second["row_set_changed"] == {}
