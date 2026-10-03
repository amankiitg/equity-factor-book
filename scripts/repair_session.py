"""Re-fit one mis-served session out of the model without rewriting the print.

The vendor served CTVA's 2026-10-01 Vylor spinoff as a price: the close went from
77.65 on 2026-09-30 to 12.57, -83.81%, with no split record, no restated adjusted
close and no dividend. `processed/returns.parquet` holds that print with its
`outlier` flag, and it should: the artifact is the record, and the flags are what
say a cell is unusable.

What the flags cannot do by themselves is unwrite a fitted row. The day was fitted
before anyone looked at it, so `models/XS-v1/specific_returns.parquet` carries a
specific return of -0.79 for CTVA that session, and everything downstream that
reads the fitted artifacts keeps seeing it: the specific variance is an EWMA over
those stored returns, and the signal is a 231-session product of them, so the print
would keep reaching the model for a year.

So this script re-fits one session from a panel in which the flagged rows are
nulled, which is the panel the research path has always fitted, and replaces that
session's rows:

    descriptors, factor_returns, specific_returns, xs_r2   that session's rows
    specific_var                                           that session's rows
    factor_cov                                             the snapshot

The repaired ticker gets an explicit null row in `specific_returns` and
`descriptors`, because the fit produces no row for a name it could not price and a
missing key reads as a value that was never considered. Every other session is
left byte for byte as it was, and `processed/returns.parquet` is not touched at
all, so `make verify-evidence` still describes the same data and the ledger entry
is how the change is announced.

**Two modes, and the difference is the name's own row.** The default masks the
name out of the session's panel and leaves the fit without it, which is the right
answer when the cell is a print nothing explains: the name cannot be priced from
it, and an explicit null is what says so. `--refit` keeps every name, including the
one it was asked about, and re-derives the session from the panel as it stands.
That is the right answer once the cell has been **corrected** rather than removed: a
recorded spin-off puts the true total return into the panel, so the name's own
return is a real observation again, and masking it would delete the return instead
of using it. Both modes fit one session, refuse a payload that is not exactly that
session or that carries a key twice, and leave every other session byte for byte as
it was; the report says which mode ran, under `mode`.

**A rerun of `--refit` is a fixed point in value, not a byte comparison.** Measured
on the real panel for 2026-10-01 and 2026-10-02: a rerun reproduces CTVA's specific
return and variance to one or two units in the last place and leaves `xs_r2`
byte-identical, while `descriptors`, `factor_returns`, `specific_returns` and
`specific_var` hash differently. Those hashes are taken over the in-memory frame, so
they are not a byte comparison across a run boundary either: within a run,
`history_hash_before == history_hash_after` is what holds, and it is the check that
no earlier session moved.

Dry run by default. `--write` performs the artifact writes and, for every input it
repaired, replaces that session in the appendix by key, so no other session and no
other input is touched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from efb import probes  # noqa: E402
from efb.models import fundamental as fx  # noqa: E402
from live import appendix, extend, runroot, store  # noqa: E402

# The artifacts the repair rewrites, and which of them the appendix carries.
REPAIRED_ARTIFACTS = (
    "descriptors",
    "factor_returns",
    "specific_returns",
    "xs_r2",
    "specific_var",
    "factor_cov",
)
APPENDIX_INPUTS = ("descriptors", "factor_returns", "specific_returns", "specific_var")


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _session_hash(frame: pd.DataFrame, session: pd.Timestamp, keys: list[str]) -> str:
    """SHA-256 of one session's rows, in the artifact's own key order.

    Same idea as `live.extend._block_hash`, scoped to one date so the before and
    after of the repaired session and of every session before it can be compared.
    """
    block = frame.loc[pd.to_datetime(frame["date"]) == session]
    block = block.sort_values(keys)
    return hashlib.sha256(block.to_csv(index=False).encode()).hexdigest()


def _history_hash(frame: pd.DataFrame, session: pd.Timestamp, keys: list[str]) -> str:
    """SHA-256 of every row before the session, so a repair can prove it kept them."""
    block = frame.loc[pd.to_datetime(frame["date"]) < session]
    block = block.sort_values(keys)
    return hashlib.sha256(block.to_csv(index=False).encode()).hexdigest()


def _keys_for(frame: pd.DataFrame) -> list[str]:
    if "descriptor" in frame.columns:
        return ["date", "ticker", "descriptor"]
    if "factor" in frame.columns:
        return ["date", "factor"]
    if "ticker" in frame.columns:
        return ["date", "ticker"]
    return ["date"]


def masked_panel(
    root: Path, ticker: str, session: pd.Timestamp, *, mask: bool = True
) -> dict[str, object]:
    """The panel the loop itself fits from, and the one cell the repair is about.

    `extend_model` fits `probes.load_panel` as it stands, flagged rows and all.
    That is the loader-parity gap, and it is parked on its own branch because
    closing it moves `n_eff` and the fixtures across the whole history. A repair
    may not apply that fix quietly to one session, so the panel here is the
    loop's own panel and the only edit is the name and the day it was asked
    about.

    `mask=False` is the refit mode: the panel is returned as it stands, every name
    kept, and the named ticker's value is read for the report rather than removed.
    That is for a cell that has been corrected rather than one that is a print.

    Cleaning instead (`efb.hygiene.clean_returns`) nulls every flagged cell in
    the history, which is a different decision and a visible one: MRNA is flagged
    on 2026-10-01, so cleaning drops it out of that session's cross-section and
    costs the appendix a row it had, while re-fitting the session under rules its
    neighbours were never fitted under.
    """
    inputs = probes.load_panel(root)
    returns = inputs["returns"]
    assert isinstance(returns, pd.DataFrame)
    if ticker not in returns.columns:
        raise SystemExit(f"{ticker} is not a column of the returns panel")
    if session not in returns.index:
        raise SystemExit(f"{session.date()} is not a row of the returns panel")
    edited = returns.copy()
    inputs["masked_value"] = float(edited.loc[session, ticker])
    if mask:
        edited.loc[session, ticker] = np.nan
    inputs["returns"] = edited
    return inputs


def refit(
    root: Path, ticker: str, session: pd.Timestamp, *, mask: bool = True
) -> dict[str, pd.DataFrame]:
    """The repaired rows for one session, fitted from the panel `mask` describes."""
    inputs = masked_panel(root, ticker, session, mask=mask)
    returns = inputs["returns"]
    close = inputs["close"]
    volume = inputs["volume"]
    sectors = inputs["sectors"]
    shares = inputs["shares"]
    mapped = inputs["mapped"]
    look_ahead = inputs["look_ahead"]
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
    days = [day for day in design.days if day.date == session]
    if len(days) != 1:
        raise SystemExit(
            f"{session.date()} is not one cross-section in this panel "
            f"({len(days)} found): the session either has no usable returns or the "
            "artifacts do not reach it"
        )
    sub = fx.DesignResult(
        factor_names=design.factor_names,
        days=days,
        standardized=design.standardized,
        stats=design.stats,
    )
    tables = fx.fit_panel(sub)
    rows = {
        "descriptors": extend._descriptor_rows_for_dates(
            design, [session], look_ahead[mapped], mapped
        )
    }
    rows.update(
        {
            name: table
            for name, table in tables.items()
            if isinstance(table, pd.DataFrame)
        }
    )
    for frame in rows.values():
        frame["date"] = session
    return rows


def _null_rows(like: pd.DataFrame, ticker: str, session: pd.Timestamp) -> pd.DataFrame:
    """One explicit null row per key for the name the session could not price."""
    if "descriptor" in like.columns:
        descriptors = sorted(set(like["descriptor"].astype(str)))
        keys = pd.DataFrame(
            {
                "date": [session] * len(descriptors),
                "ticker": [ticker] * len(descriptors),
                "descriptor": descriptors,
            }
        )
    else:
        keys = pd.DataFrame({"date": [session], "ticker": [ticker]})
    out = keys.copy()
    for column in like.columns:
        if column not in out.columns:
            out[column] = np.nan
    return out[list(like.columns)]


def _with_repaired_session(
    frame: pd.DataFrame,
    session: pd.Timestamp,
    repaired: pd.DataFrame,
    ticker: str,
    *,
    null_the_ticker: bool,
) -> pd.DataFrame:
    """One artifact: drop that session's rows and put the repaired ones in.

    The name the session could not be priced for is *replaced*, never appended
    to. A refit still emits a row for it wherever the value is a function of the
    cross-section rather than of the name's own return, so a descriptor row for
    the masked name comes back with a null value, and appending an explicit null
    row on top of it hands the store two rows for one key. `replace_by_date`
    deletes and then inserts without an upsert, so that arrives as a unique-key
    violation *after* the delete has landed: the date looks half-repaired when
    the real fault is a duplicated row. The masked name's refit rows are
    therefore dropped first, and the key set is asserted unique before the frame
    leaves here.
    """
    keep = pd.to_datetime(frame["date"]) != session
    rows = repaired.reindex(columns=frame.columns)
    if null_the_ticker:
        if "ticker" not in rows.columns:
            raise SystemExit(f"cannot null {ticker}: the frame has no ticker column")
        rows = rows.loc[rows["ticker"].astype(str) != ticker]
        rows = pd.concat(
            [rows, _null_rows(repaired, ticker, session)], ignore_index=True
        )
    out = pd.concat([frame.loc[keep], rows], ignore_index=True)
    keys = _keys_for(out)
    duplicated = out.loc[out.duplicated(subset=keys, keep=False), keys]
    if not duplicated.empty:
        named = sorted(
            "|".join(str(value) for value in row)
            for row in duplicated.itertuples(index=False)
        )
        raise SystemExit(
            f"{len(duplicated)} repaired rows share a key, which the store would "
            f"refuse after deleting the date: {named[:5]}"
        )
    return out.sort_values(keys).reset_index(drop=True)


def _session_block(
    spec: appendix.InputSpec, root: Path, session: pd.Timestamp
) -> pd.DataFrame:
    """The session's rows for one appendix table, and nothing else.

    `replace_by_date` deletes exactly the rows whose date it was given, so the
    insert has to carry exactly that date's rows. Three ways the two scopes can
    disagree, all of them checked here rather than in Postgres: a payload that
    reaches another date inserts against rows the delete never touched, a
    payload with two rows for one key is refused outright, and an empty payload
    silently empties a date the repair was asked to fill. `artifact_rows`'
    cutoff keeps the rows *after* it, so it reads the repaired session on, and
    the date filter is what makes the scopes equal.
    """
    rows = appendix.artifact_rows(spec, root, cutoff=session - pd.Timedelta(days=1))
    rows = rows.loc[pd.to_datetime(rows[appendix.DATE_COLUMN]) == session]
    if rows.empty:
        raise SystemExit(f"{spec.table} would replace {session.date()} with no rows")
    dates = sorted(
        {str(value.date()) for value in pd.to_datetime(rows[appendix.DATE_COLUMN])}
    )
    if dates != [str(session.date())]:
        raise SystemExit(
            f"{spec.table} payload reaches {dates}, not {session.date()} alone"
        )
    duplicated = rows.loc[rows.duplicated(subset=list(spec.key), keep=False)]
    if not duplicated.empty:
        raise SystemExit(
            f"{spec.table} payload has {len(duplicated)} rows sharing one of its "
            f"keys, which the insert would refuse"
        )
    return rows


def repair(
    root: Path, ticker: str, session: pd.Timestamp, *, write: bool, mask: bool = True
) -> dict[str, object]:
    """Re-fit the session and replace it, in the tree and (with `write`) the store.

    `mask` is the mode: True refits the session without the named name, False
    (`--refit`) keeps every name including that one. See the module docstring.
    """
    xs = root / "models" / "XS-v1"
    paths = {name: xs / f"{name}.parquet" for name in REPAIRED_ARTIFACTS}
    before_files = {name: _file_hash(path) for name, path in paths.items()}
    before_frames = {name: pd.read_parquet(path) for name, path in paths.items()}
    before_sessions = {
        name: _session_hash(frame, session, _keys_for(frame))
        for name, frame in before_frames.items()
        if "date" in frame.columns
    }
    before_appendix = {
        spec.name: appendix.appendix_identity(spec)
        for spec in appendix.SPECS
        if spec.name in APPENDIX_INPUTS
    }
    returns_path = root / "processed" / "returns.parquet"

    old_row = before_frames["specific_returns"]
    old_row = old_row.loc[
        (pd.to_datetime(old_row["date"]) == session) & (old_row["ticker"] == ticker),
        "specific_return",
    ]
    old_specific = float(old_row.iloc[0]) if len(old_row) else float("nan")
    old_variance = before_frames["specific_var"]
    old_variance = old_variance.loc[
        (pd.to_datetime(old_variance["date"]) == session)
        & (old_variance["ticker"] == ticker),
        "specific_var",
    ]
    old_variance_value = (
        float(old_variance.iloc[0]) if len(old_variance) else float("nan")
    )
    old_sigma = (
        float(np.sqrt(old_variance_value)) if len(old_variance) else float("nan")
    )

    repaired = refit(root, ticker, session, mask=mask)

    frames = dict(before_frames)
    frames["descriptors"] = _with_repaired_session(
        before_frames["descriptors"],
        session,
        repaired["descriptors"],
        ticker,
        null_the_ticker=mask,
    )
    frames["factor_returns"] = _with_repaired_session(
        before_frames["factor_returns"],
        session,
        repaired["factor_returns"],
        ticker,
        null_the_ticker=False,
    )
    frames["specific_returns"] = _with_repaired_session(
        before_frames["specific_returns"],
        session,
        repaired["specific_returns"],
        ticker,
        null_the_ticker=mask,
    )
    frames["xs_r2"] = _with_repaired_session(
        before_frames["xs_r2"],
        session,
        repaired["xs_r2"],
        ticker,
        null_the_ticker=False,
    )

    # The two rolling artifacts, recomputed over the repaired history exactly as
    # `extend.extend_model` recomputes them. The factor covariance is a dateless
    # snapshot, so it is replaced whole; the specific variance keeps every earlier
    # session's rows, because an EWMA's past does not move when a later
    # observation does.
    factor_wide = (
        frames["factor_returns"]
        .pivot(index="date", columns="factor", values="f")
        .reindex(columns=list(fx.FACTOR_NAMES))
        .dropna()
    )
    frames["factor_cov"] = fx.ewma_factor_cov(factor_wide, half_life=fx.F_HALF_LIFE)
    inputs = masked_panel(root, ticker, session, mask=mask)
    sectors = inputs["sectors"]
    shares = inputs["shares"]
    close = inputs["close"]
    mapped = inputs["mapped"]
    assert isinstance(sectors, pd.Series)
    assert isinstance(shares, pd.DataFrame)
    assert isinstance(close, pd.DataFrame)
    cap = fx.market_cap(close[mapped], shares[mapped])
    specific_wide = frames["specific_returns"].pivot(
        index="date", columns="ticker", values="specific_return"
    )
    variance = fx.specific_variance(
        specific_wide,
        sectors,
        cap,
        dates=[session],
        half_life=fx.D_HALF_LIFE,
        shrink_k=fx.D_SHRINK_K,
    )
    variance["date"] = session
    frames["specific_var"] = _with_repaired_session(
        before_frames["specific_var"],
        session,
        variance.reindex(columns=before_frames["specific_var"].columns),
        ticker,
        null_the_ticker=False,
    )

    # A re-fit can move the session's name set: a name whose return the panel does
    # not carry drops out, and one the fitted session was missing comes back, which
    # is how a date repaired under the wrong mask is put right. Neither is silent:
    # the counts and the names that moved are reported. What is refused, before any
    # statement runs, is a payload that is not exactly this session, or that
    # carries a key twice.
    session_rows_before = {
        name: int((pd.to_datetime(before_frames[name]["date"]) == session).sum())
        for name in APPENDIX_INPUTS
    }
    session_rows = {
        name: int((pd.to_datetime(frames[name]["date"]) == session).sum())
        for name in APPENDIX_INPUTS
    }
    row_set_changed: dict[str, object] = {}
    for name in APPENDIX_INPUTS:
        if session_rows[name] == session_rows_before[name]:
            continue
        keys = _keys_for(before_frames[name])
        was = before_frames[name]
        now = frames[name]
        before_keys = {
            tuple(row)
            for row in was.loc[pd.to_datetime(was["date"]) == session, keys].to_numpy()
        }
        after_keys = {
            tuple(row)
            for row in now.loc[pd.to_datetime(now["date"]) == session, keys].to_numpy()
        }
        row_set_changed[name] = {
            "rows_before": session_rows_before[name],
            "rows_after": session_rows[name],
            "gained": sorted(
                "|".join(map(str, key)) for key in after_keys - before_keys
            )[:20],
            "lost": sorted("|".join(map(str, key)) for key in before_keys - after_keys)[
                :20
            ],
        }

    after_sessions = {
        name: _session_hash(frame, session, _keys_for(frame))
        for name, frame in frames.items()
        if "date" in frame.columns
    }
    before_block = {
        name: _history_hash(frame, session, _keys_for(frame))
        for name, frame in before_frames.items()
        if "date" in frame.columns
    }
    after_block = {
        name: _history_hash(frame, session, _keys_for(frame))
        for name, frame in frames.items()
        if "date" in frame.columns
    }

    new_variance = frames["specific_var"]
    new_variance = new_variance.loc[
        (pd.to_datetime(new_variance["date"]) == session)
        & (new_variance["ticker"] == ticker),
        "specific_var",
    ]
    new_variance_value = (
        float(new_variance.iloc[0]) if len(new_variance) else float("nan")
    )
    new_sigma = (
        float(np.sqrt(new_variance_value)) if len(new_variance) else float("nan")
    )
    new_row = frames["specific_returns"]
    new_row = new_row.loc[
        (pd.to_datetime(new_row["date"]) == session) & (new_row["ticker"] == ticker),
        "specific_return",
    ]
    new_specific = float(new_row.iloc[0]) if len(new_row) else float("nan")

    report: dict[str, object] = {
        "ticker": ticker,
        "session": str(session.date()),
        "mode": "mask" if mask else "refit",
        "specific_return_before": old_specific,
        "specific_return_after": new_specific,
        "variance_before": old_variance_value,
        "variance_after": new_variance_value,
        "payload_rows_before": session_rows_before,
        "payload_rows_after": session_rows,
        "row_set_changed": row_set_changed,
        "sigma_before": old_sigma,
        "sigma_after": new_sigma,
        "session_hash_before": before_sessions,
        "session_hash_after": after_sessions,
        "history_hash_before": before_block,
        "history_hash_after": after_block,
        "file_hash_before": before_files,
        "returns_untouched": None,
        "appendix_before": before_appendix,
        "written": {},
    }

    returns_hash = _file_hash(returns_path)
    if not write:
        report["returns_untouched"] = True
        report["file_hash_after"] = {
            name: _file_hash(path) for name, path in paths.items()
        }
        report["appendix_after"] = before_appendix
        return report

    for name in REPAIRED_ARTIFACTS:
        frames[name].to_parquet(paths[name], index=False)
    report["file_hash_after"] = {name: _file_hash(path) for name, path in paths.items()}
    report["returns_untouched"] = _file_hash(returns_path) == returns_hash

    written: dict[str, int] = {}
    for spec in appendix.SPECS:
        if spec.name not in APPENDIX_INPUTS:
            continue
        rows = _session_block(spec, root, session)
        if len(rows) != session_rows[spec.name]:
            raise SystemExit(
                f"{spec.table}: {len(rows)} rows in the payload but "
                f"{session_rows[spec.name]} in the repaired artifact"
            )
        store.replace_by_date(spec.table, str(session.date()), rows.to_dict("records"))
        written[spec.name] = int(len(rows))
    # `e11_factor_cov` is deliberately not written. It holds no rows for any
    # date, and that is the publish path's own state rather than anything this
    # repair produced: the covariance artifact is a dateless snapshot stamped
    # 1970-01-01, and `persist_new_sessions` reads it with a cutoff filter that
    # drops every row before the stamp is replaced, so the loop has never put a
    # session in this table. Writing one date here would invent the first rows a
    # table the loop does not populate, and the covariance the book actually
    # hedges with is recomputed from the factor returns by
    # `efb.eval_risk._xs_pieces`, not read from it.
    report["written"] = written
    report["appendix_after"] = {
        spec.name: appendix.appendix_identity(spec)
        for spec in appendix.SPECS
        if spec.name in APPENDIX_INPUTS
    }
    return report


def load_tree(work: Path, tree: Path | None) -> Path:
    """The run's own tree, brought to the session the repair is for.

    Materializing from the bucket and hydrating the appendix is what the cron
    does, and so is extending the panel: `processed/returns.parquet` is not an
    appendix input, so it is the one artifact a hydrated tree has to rebuild from
    the prices before the model can be fitted. Nothing is fetched from the vendor:
    the prices and share counts the appendix supplied are the run's own.
    """
    root = tree
    if root is None:
        target = work / "data"
        target.parent.mkdir(parents=True, exist_ok=True)
        root = runroot.prepare(dest=target)
    appendix.open_store(root)
    extend.extend_returns(root)
    return root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ticker", required=True, help="the name to re-fit out")
    parser.add_argument("--session", required=True, help="the session, YYYY-MM-DD")
    parser.add_argument("--tree", type=Path, default=None, help="a prepared run tree")
    parser.add_argument(
        "--work",
        type=Path,
        default=Path("/tmp/efb-repair"),
        help="where to materialize the tree when --tree is not given",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the artifacts and replace the session in the appendix",
    )
    parser.add_argument(
        "--refit",
        action="store_true",
        help=(
            "keep every name in the session, including --ticker, and re-derive "
            "it from the panel as it stands; the default masks --ticker out"
        ),
    )
    args = parser.parse_args(argv)

    session = pd.Timestamp(args.session)
    root = load_tree(args.work, args.tree)
    report = repair(root, args.ticker, session, write=args.write, mask=not args.refit)
    print(json.dumps(report, indent=2, default=str))
    print()
    print(f"tree: {root}")
    print("dry run: nothing was written" if not args.write else "written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
