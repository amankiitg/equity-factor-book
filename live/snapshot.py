"""B-cron: the one JSON snapshot the Cloudflare page reads.

Render keeps running one service, the evening cron, and that cron writes a single
JSON document every run and uploads it to Cloudflare R2. The browser never reaches
R2 and never reaches Supabase: a Worker reads the object through a binding on an
Access-protected hostname and serves it, so the bucket stays private and the
positions stay behind Access.

**Written on every run, including `stale_stopped` and `error`.** A page that shows
nothing when the run fails is worse than no page, because it looks like a quiet
evening. The snapshot carries the run's own status, so the failure is the news.

**`EFB_SNAPSHOT` is required, `on` or `off`, and the two are not symmetric.**

| `EFB_SNAPSHOT` | `dry_run` | what happens |
| --- | --- | --- |
| `on` | either | the snapshot is written and uploaded; a failed upload fails the run |
| `off` | true | nothing is uploaded, and the run records `snapshot: off` in
`run_status` and in the email, because the gate evenings run before the page
exists |
| `off` | false | an `error`: the flip cannot happen without a working page |

**JSON has no NaN.** Every float goes through `store.json_text`, which turns NaN and
infinity into `null`, and a test asserts the serialized document contains no bare
`NaN`.

**`expected_next_by`** is computed here from the NYSE calendar, the cron's own slot
and a stated grace, so the browser needs no calendar of its own: it compares the
current time with the instant the next snapshot should already exist by.

**No unqualified `n_eff`.** The breadth keys are `n_eff_kept` for the book that
trades and `n_eff_full_book` for the 499-name book before the floor, with the same
labels item 3 put on both pages.

**A stopped run's book comes from the store, never from a file.** Render's disk is
the deploy image, so the newest `live/proposals/` file there is whatever was
committed, and showing it on a stale evening would tell the owner they hold a book
from weeks ago. `previous_proposal` reads the last proposal the loop actually
proposed, and when the store holds none the book is empty and says why.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from live import breadth, construction_table, staleness, store

SCHEMA_VERSION = 1
SNAPSHOT_ENV = "EFB_SNAPSHOT"
ON = "on"
OFF = "off"
LATEST_KEY = "latest.json"
DATED_TEMPLATE = "snapshots/{close}.json"

R2_ENVS = (
    "EFB_R2_ACCOUNT_ID",
    "EFB_R2_BUCKET",
    "EFB_R2_ACCESS_KEY_ID",
    "EFB_R2_SECRET_ACCESS_KEY",
)
R2_REGION = "auto"
# R2 is S3-compatible, so the client is boto3 against the account's endpoint, and
# every object goes up as one `put_object` with this content type and a checksum.
R2_ENDPOINT_TEMPLATE = "https://{account}.r2.cloudflarestorage.com"
CONTENT_TYPE = "application/json"

# Why a stopped run's book is empty, when it is. Stated rather than implied: the
# page shows an empty book with this sentence beside it.
NO_STORED_BOOK = "no proposal is in the store yet"
STORED_BOOK_HAS_NO_ROWS = "the store's latest proposal has no position rows"


class SnapshotNotConfigured(RuntimeError):
    """The snapshot cannot be written as configured, so the run has to stop."""


class SnapshotNotAllowed(RuntimeError):
    """`EFB_SNAPSHOT` is off where it has to be on."""


def snapshot_mode() -> str:
    """`on` or `off`, and never a default.

    The switch is required, because both of its defaults are wrong somewhere: an
    unasked-for `off` would let a live run skip the page, and an unasked-for `on`
    would make the gate evenings depend on a bucket that does not exist yet.
    """
    value = os.environ.get(SNAPSHOT_ENV, "").strip().lower()
    if value not in (ON, OFF):
        raise SnapshotNotConfigured(
            f"{SNAPSHOT_ENV} must be {ON!r} or {OFF!r} and it is "
            f"{value!r}; it is required because neither default is safe"
        )
    return value


def check_snapshot(dry_run: bool, mode: str | None = None) -> str:
    """The mode, after refusing `off` on a live run."""
    resolved = mode or snapshot_mode()
    if resolved == OFF and not dry_run:
        raise SnapshotNotAllowed(
            f"{SNAPSHOT_ENV}={OFF} while dry_run is false: the flip cannot happen "
            f"before the page can show a real snapshot"
        )
    return resolved


def check_snapshot_config(dry_run: bool) -> str:
    """The switch and the credentials, checked before the run does anything.

    `write_snapshot` reads both when the evening is over, which is the wrong place
    to discover a missing credential: by then the book has been sized and the
    orders have been sent, and the page is where the owner sees the book. A run
    that trades and then cannot publish is a run that traded invisibly. This is the
    same check the writer makes, moved to the start of the run, so a
    misconfiguration costs nothing and never reaches a submission.

    Returns the mode, exactly as `check_snapshot` would.
    """
    mode = check_snapshot(dry_run)
    if mode == ON:
        # The four variables are what an upload needs; naming them here means the
        # message says which one is missing before anything is priced.
        r2_settings()
    return mode


def expected_next_by(target_close: Any) -> str:
    """The UTC instant by which the next run's snapshot should exist.

    One source for the browser's expectation and for the gate's late window:
    `live.staleness.expected_next_by`, which reads the cron's own slot from
    render.yaml's schedule and the grace that sits beside it.
    """
    return staleness.expected_next_by(target_close)


def _iso(value: Any) -> str | None:
    """A date or timestamp as an ISO string, or None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return pd.Timestamp(value).isoformat()


def _day(value: Any) -> str | None:
    """A session as the day it is, never with a midnight time stapled to it.

    The page shows these beside `target_close` and `book_as_of`, which are days for
    the same reason: a reader comparing two closes must not have to know that one
    spelling carries a time and the other does not.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return str(pd.Timestamp(value))[:10]


def _kept(proposal: dict[str, Any], key: str, full_key: str | None = None) -> Any:
    """A figure for the book that trades, or the full book's when there is none.

    `gross`, `net` and the forecast volatility on the page describe the book the
    owner holds: the kept set after the hedge. The 499-name book is published
    beside each of them under its own name. A proposal written before the kept
    figure existed carries only the full-book number, which is then what the page
    has. A stored null is treated as absent for the same reason: the key being
    present is not a value.
    """
    kept = proposal.get(key)
    if kept is not None:
        return kept
    return proposal.get(full_key) if full_key else None


def construction_label(manifest: dict[str, Any] | None) -> str:
    """The construction, generated only from the artifact's own fields."""
    return construction_table.construction_label(manifest or {})


def build(
    *,
    run: dict[str, Any],
    manifest: dict[str, Any] | None = None,
    book: pd.DataFrame | None = None,
    reconciliation: dict[str, Any] | None = None,
    construction: dict[str, Any] | None = None,
    book_reason: str | None = None,
    actual: dict[str, Any] | None = None,
    bridge_block: dict[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """The document the page reads, assembled from what the run already knows.

    Nothing here is recomputed: every number comes from the proposal's manifest,
    the proposal's own rows with their trade reasons, the construction table's
    chosen row and the run's own status, so the page cannot disagree with the book
    the owner confirmed.
    """
    proposal = manifest or {}
    rows = book if book is not None else pd.DataFrame()
    chosen = construction or {}
    stamp = generated_at or datetime.now(UTC)
    target_close = _iso(run.get("target_close")) or proposal.get("as_of")
    names: list[dict[str, Any]] = []
    if len(rows):
        ordered = rows.reindex(rows["weight"].abs().sort_values(ascending=False).index)
        for entry in ordered.to_dict("records"):
            names.append(
                {
                    "ticker": str(entry.get("ticker")),
                    "weight": _number(entry.get("weight")),
                    "side": str(entry.get("side") or ""),
                    "reason": entry.get("reason"),
                    "z": _number(entry.get("z")),
                    "alpha": _number(entry.get("alpha")),
                    # The dollars the evening actually traded in this name, which is
                    # what the page's trades-by-reason table needs to say where the
                    # turnover came from. Named for what it is - the leg's own
                    # notional, absolute - because the book above it is a holding and
                    # this is a movement, and the two are different questions about
                    # the same name. The key is present only for a frame that carries
                    # the column, which every evening's own book does now: a book
                    # published before the column existed has no traded dollars to
                    # state, and a zero invented for it would read as a measured one.
                    **(
                        {"traded_notional": _number(entry.get("traded_notional"))}
                        if "traded_notional" in rows.columns
                        else {}
                    ),
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": stamp.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "target_close": target_close,
        # The close of the proposal the book came from. On a run that proposed one
        # it is the target close; on a stopped run it is the close of the book the
        # page is still showing, so the page can never show a book without its date.
        # Normalized the same way as `target_close`, because the page compares the
        # two to decide whether to date the book, and two spellings of one close
        # would read as a difference.
        "book_as_of": _iso(proposal.get("as_of")),
        "expected_next_by": expected_next_by(target_close) if target_close else None,
        "dry_run": bool(run.get("dry_run", True)),
        "store": run.get("store"),
        "run_status": {
            "status": run.get("status"),
            "detail": run.get("detail") or "",
            "failing_inputs": _json_value(run.get("failures"), []),
            "worst_input": run.get("worst_input"),
            "worst_sessions_behind": run.get("worst_sessions_behind"),
            "catch_up": bool(run.get("catch_up", False)),
            "catch_up_sessions": _json_value(run.get("catch_up_sessions"), []),
            "splits": _json_value(run.get("splits"), []),
            "flags": _json_value(run.get("flags"), []),
            "notify_status": run.get("notify_status"),
            "snapshot": run.get("snapshot"),
            # The day's kind: an establishment run creates the book and may trade
            # up to the full book, and its cost is labelled establishment; from the
            # second trading day the run is a rebalance under the absolute brake.
            "establishment": bool(run.get("establishment", False)),
            "cost_label": run.get("cost_label"),
        },
        "construction": construction_table.construction_label(proposal),
        # The account's book against the store's, read before the orders were
        # built. The page shows it beside the book, because a book the loop
        # believes it holds and the account does not is the one failure that
        # makes every number below it wrong.
        "positions": _positions_block(run.get("positions_check")),
        "breadth": {
            "n_eff_kept": _number(proposal.get("n_eff_kept")),
            "n_eff_full_book": _number(proposal.get("n_eff_full_book")),
            "kept_label": breadth.BOOK_LABEL,
            "full_book_label": breadth.FULL_BOOK_LABEL,
        },
        "book": {
            "n_names": len(names),
            "n_kept": _number(proposal.get("n_kept")),
            "n_long": _number(chosen.get("n_long")),
            "n_short": _number(chosen.get("n_short")),
            # These four describe the book that trades and the 499-name book
            # beside it. `kept_gross` is the kept set after the hedge,
            # renormalized to exactly 1.0, and `notional` is that book in dollars;
            # `kept_achieved_annual_vol` is its forecast volatility. The
            # manifest's own `gross`, `net` and `achieved_annual_vol` are the
            # *499-name* book after sizing and before the floor, which is a
            # different book and is published under its own name rather than as
            # "the gross" of a book the owner does not hold. A stored null counts
            # as absent: a manifest row read back from the store can carry the key
            # with no value.
            "gross": _number(_kept(proposal, "kept_gross", "gross")),
            "gross_notional": _number(proposal.get("notional")),
            "full_book_gross": _number(proposal.get("gross")),
            "net": _number(_kept(proposal, "kept_net", "net")),
            "full_book_net": _number(proposal.get("net")),
            "max_kept_weight": _number(proposal.get("max_kept_weight")),
            "achieved_annual_vol": _number(
                _kept(proposal, "kept_achieved_annual_vol", "achieved_annual_vol")
            ),
            "full_book_achieved_annual_vol": _number(
                proposal.get("achieved_annual_vol")
            ),
            "expected_cost_bps": _number(
                proposal.get("expected_establishment_cost_bps")
            ),
            # The same cost, split the way the proposal computes it: trading
            # (spread + impact + commission) and borrow, the cost of holding the
            # short leg over the horizon. The page compares the fills against the
            # trading half only, because borrow is not something a fill price can
            # be measured against, and a total alone leaves the reader unable to
            # tell which part a miss belongs to.
            "expected_cost_split": _cost_split(proposal),
            # Why the book is empty, when it is. A stopped evening whose store
            # holds nothing must not read as a book of zero names for no stated
            # reason, so the reason travels with the empty book.
            "reason": book_reason,
            "names": names,
        },
        # One value per design column, named by fx.ESTIMATED_NAMES, after the
        # hedge. The hedge itself stays in `hedge` beside them.
        "exposures_before_hedge": _numbers(proposal.get("exposures_before_hedge")),
        "exposures_after_hedge": _numbers(proposal.get("exposures_after_hedge")),
        "hedge": {
            "idio_share_after_fmp": _number(proposal.get("idio_share_after_fmp")),
            "max_abs_exposure_after_fmp": _number(
                proposal.get("max_abs_exposure_after_fmp")
            ),
            "post_hedge_idio_share": _number(chosen.get("post_hedge_idio_share")),
            "post_hedge_max_abs_exposure": _number(
                chosen.get("post_hedge_max_abs_exposure")
            ),
        },
        "exposures": {
            "realized_market_beta": _number(chosen.get("realized_market_beta")),
            "realized_market_beta_shrunk": _number(
                chosen.get("realized_market_beta_shrunk")
            ),
            "residual_exposure_shrunk": _number(chosen.get("residual_exposure_shrunk")),
            "residual_exposure_winsor": _number(chosen.get("residual_exposure_winsor")),
        },
        "reconciliation": {
            key: _number((reconciliation or {}).get(key))
            for key in (
                "intended_notional",
                "filled_notional",
                "realized_annual_vol",
                "expected_cost_bps",
            )
        }
        | {
            # The traded book's risk figures and the full book's, each under its
            # own names, from the manifest via the reconciled row.
            "traded_risk": _json_value((reconciliation or {}).get("traded_risk"), None),
            "full_risk": _json_value((reconciliation or {}).get("full_risk"), None),
        }
        # The part of the day's P&L no order of the loop's explains, from the same
        # row the store holds. Present only when the row carries it, which is the
        # evening's own row: a document built without a reconciliation has no P&L
        # to adjust, and a zero invented for it would read as a measured nought.
        | (
            {
                "unexplained_adjustment": _number(
                    (reconciliation or {}).get("unexplained_adjustment")
                )
            }
            if (reconciliation or {}).get("unexplained_adjustment") is not None
            else {}
        ),
        # The account's own book beside the target, and the fills behind it. The
        # evening's own account read fills it, and the 15:30 UTC reconciler
        # rewrites it with what the evening's orders did. It is absent, rather than
        # null, when nobody has read the account: a key that said null would read as
        # an account holding nothing, which is a different statement from an account
        # nobody read.
        **({"actual_holdings": _actual_block(actual)} if actual else {}),
        # The bridge: how the held book became the orders and then the positions.
        # The evening publishes the first half of it and the morning completes it, so
        # the page can connect three sets it draws side by side without recomputing
        # any of the arithmetic - and can say so when the arithmetic does not add up.
        # Absent (not null) when nobody built one, which is a stopped run: a bridge of
        # zeroes would read as an evening that moved nothing.
        **({"bridge": _bridge_block(bridge_block)} if bridge_block else {}),
        # E12: what the book earned, split into factor, idio and cost, with the
        # hedge's own factor P&L and the raw-beta line beside it. The block is
        # built by `attribution_block` from the store's attribution table and
        # handed in through `run`, so this function stays a pure assembler and a
        # page can never be built from a recomputation of the store's numbers.
        "attribution": _attribution_document(run.get("attribution")),
    }


def _cost_split(proposal: dict[str, Any]) -> dict[str, Any]:
    """The day's expected cost, split into trading and borrow, in bps of NAV.

    Read from the proposal's own `cost_breakdown_bps`, which the evening built as
    spread + impact + commission + borrow, so the parts sum to the total by
    construction rather than by this function's arithmetic. Trading is the three
    the fills can actually be measured against; borrow is the holding cost, and
    comparing an execution price to it would be comparing a fill to a calendar.

    Empty when the manifest predates the breakdown: a part nobody computed is not
    invented here, and the page says what it has rather than zeroes.
    """
    from live import reconcile

    breakdown = reconcile.cost_breakdown(proposal)
    if not breakdown:
        return {}
    parts = {
        str(name): _number(breakdown.get(name))
        for name in ("spread", "impact", "commission", "borrow")
        if breakdown.get(name) is not None
    }
    if not parts:
        return {}
    trading = [
        value
        for name, value in parts.items()
        if name in ("spread", "impact", "commission") and value is not None
    ]
    return {
        **parts,
        "trading": float(sum(trading)),
        "total": _number(breakdown.get("total")),
    }


def _actual_block(raw: dict[str, Any] | None) -> dict[str, Any]:
    """The account's book as the page's own object, with the non-finite nulled.

    Formatted here and measured by the caller, like every other block: the fills
    reconciler reads the account and this writes down what it read, so the two
    cannot disagree about the book the owner holds.
    """
    block = raw or {}
    names = [
        {
            "ticker": str(entry.get("ticker")),
            "side": entry.get("side"),
            "notional": _number(entry.get("notional")),
            "weight": _number(entry.get("weight")),
        }
        for entry in (block.get("names") or [])
    ]
    fills_block = block.get("fills")
    return {
        "as_of": _iso(block.get("as_of")),
        "close": _iso(block.get("close")),
        # Which run read the account: the evening's read is the book it sized from,
        # the morning's is what the evening's orders left behind. Carried through
        # rather than inferred, because `fills` being absent means the evening read
        # it and not that nothing filled.
        "read_by": block.get("read_by"),
        "n_names": _number(block.get("n_names")) if names else 0,
        "gross_notional": _number(block.get("gross_notional")),
        "net_notional": _number(block.get("net_notional")),
        "names": names,
        "fills": (
            {
                "trade_date": _iso(fills_block.get("trade_date")),
                "n_orders": _number(fills_block.get("n_orders")),
                "n_filled": _number(fills_block.get("n_filled")),
                "n_unfilled": _number(fills_block.get("n_unfilled")),
                "not_sent": _number(fills_block.get("not_sent")),
                "realized_cost_bps": _number(fills_block.get("realized_cost_bps")),
                # The same number averaged over every day the loop has reconciled,
                # with how many days are in it. One day of realized cost is mostly
                # the overnight move - the order is sent after one close and fills
                # at the next open - so the average is the figure that can be read
                # as execution quality, and the count is stated because an average
                # of two days is not an average of twenty.
                "realized_cost_avg_bps": _number(
                    fills_block.get("realized_cost_avg_bps")
                ),
                "realized_cost_days": _number(fills_block.get("realized_cost_days")),
                "expected_cost_bps": _number(fills_block.get("expected_cost_bps")),
                "unfilled": list(fills_block.get("unfilled") or []),
                "not_sent_lines": list(fills_block.get("not_sent_lines") or []),
                "unread": list(fills_block.get("unread") or []),
            }
            if isinstance(fills_block, dict)
            else None
        ),
        # The names that left the account with nothing of the loop's to explain
        # them, written beside the book because that is where a reader looks for a
        # name that is no longer there. Absent (rather than an empty list) when the
        # question was not asked, so the page can say "not read" instead of "none".
        **({"exits": _exits_block(block.get("exits"))} if block.get("exits") else {}),
    }


def _bridge_block(raw: Any) -> dict[str, Any]:
    """The bridge as the page's own object, with the non-finite nulled.

    Counts pass through as they are, because they are what the identities are
    checked against and a count rounded on its way to the page would be a check
    against a different number. The two name lists are lists of strings and the
    removals keep their ticker, shares and dollars: they are the evidence under the
    counts, and the four fields are what the reader needs to look one up.
    """
    block = raw if isinstance(raw, dict) else {}
    return {
        "close": _iso(block.get("close")),
        "seen_by": block.get("seen_by"),
        "book": _number(block.get("book")),
        "held_before": _number(block.get("held_before")),
        "in_both": _number(block.get("in_both")),
        "opened": _number(block.get("opened")),
        "exited": _number(block.get("exited")),
        "changed": _number(block.get("changed")),
        "under_minimum": _number(block.get("under_minimum")),
        "orders_sent": _number(block.get("orders_sent")),
        "filled": _number(block.get("filled")),
        "did_not_fill": _number(block.get("did_not_fill")),
        "held_after": _number(block.get("held_after")),
        "under_minimum_usd": _number(block.get("under_minimum_usd")),
        "reversals_pending": [
            str(name) for name in (block.get("reversals_pending") or [])
        ],
        "removed_without_order": [
            {
                "ticker": str(item.get("ticker")),
                "quantity": _number(item.get("quantity")),
                "notional": _number(item.get("notional")),
            }
            for item in (block.get("removed_without_order") or [])
            if isinstance(item, dict) and item.get("ticker")
        ],
        "unexplained": [str(name) for name in (block.get("unexplained") or [])],
        "identities": [
            {
                "name": str(item.get("name")),
                "left": _number(item.get("left")),
                "right": _number(item.get("right")),
                "holds": bool(item.get("holds")),
            }
            for item in (block.get("identities") or [])
            if isinstance(item, dict)
        ],
        "holds": bool(block.get("holds", False)),
    }


def _exits_block(raw: Any) -> dict[str, Any]:
    """The departures block as the page's own object, with the non-finite nulled."""
    block = raw if isinstance(raw, dict) else {}
    return {
        "previous_read": _iso(block.get("previous_read")),
        "feed": block.get("feed"),
        "window": block.get("window"),
        "names": [
            {
                "ticker": str(entry.get("ticker")),
                "quantity": _number(entry.get("quantity")),
                "notional": _number(entry.get("notional")),
            }
            for entry in (block.get("names") or [])
        ],
    }


def _positions_block(raw: Any) -> dict[str, Any]:
    """The stored position check as the page's own object, minus the name maps.

    The two name maps are summarized rather than shipped: the counts, the names
    that are only in one book, and the largest drift are the evidence, and the
    document is read on every page load.
    """
    check = _json_value(raw, {})
    if not isinstance(check, dict):
        check = {}
    return {
        "matches": check.get("matches"),
        "n_broker": _number(check.get("n_broker")),
        "n_store": _number(check.get("n_store")),
        "source": check.get("source"),
        "note": check.get("note"),
        "missing_at_broker": check.get("missing_at_broker") or [],
        "missing_in_store": check.get("missing_in_store") or [],
        "max_abs_drift": _number(check.get("max_abs_drift")),
    }


def _number(value: Any) -> Any:
    """A float, an int, or None. Never a NaN or an infinity.

    JSON cannot carry either, so the document and its text would disagree if this
    let them through: `null` is the one way to say the run did not have a number.
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):  # pragma: no cover - arrays and the like
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _json_value(value: Any, fallback: Any) -> Any:
    """A stored JSON string read back, or the fallback."""
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _numbers(value: Any) -> dict[str, Any]:
    """A dict of numbers with the non-finite ones nulled, or an empty dict."""
    if not isinstance(value, dict):
        return {}
    return {str(key): _number(item) for key, item in value.items()}


def _mean(values: list[float]) -> float | None:
    """The mean of the days that carry a number, or None when none does.

    Over the days that have one rather than over the period: an average that
    counted a missing day as a zero would report a cost nobody paid.
    """
    return _number(sum(values) / len(values)) if values else None


# The page shows a month of days. The attribution itself is stored for every day
# the loop has traded, and the cumulative sums below are over all of them.
ATTRIBUTION_DAYS = 30

# The first day of the live period. The loop was rehearsed on the seed's own books
# before the flip, so the store holds a few sessions that are not the live book's;
# they are attributed (the table is a record of what was held) and left out of the
# view the page opens on.
LIVE_PERIOD_START = "2026-10-01"

# The research panel's own attribution artifact, built by
# `scripts/build_attribution.py` from the seed's stored book. It is not in git (the
# parquet artifacts are ignored), so the backtest view exists only where the seed
# bundle on the host carries it; without it the view is absent rather than empty.
DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
BACKTEST_DAILY = "daily.parquet"
BACKTEST_MONTHLY = "monthly.parquet"


def empty_attribution(note: str) -> dict[str, Any]:
    """The attribution block for a run with nothing to show, and why."""
    return {
        "live": _empty_period("the live book has no attributed day yet"),
        "backtest": None,
        "note": note,
    }


def _empty_period(note: str) -> dict[str, Any]:
    """One period with nothing in it: the same keys, so the page has one shape."""
    return {
        "label": "",
        "first_day": None,
        "last_day": None,
        "n_days": 0,
        "n_days_carried": 0,
        "cumulative": {
            "pnl_total": None,
            "pnl_factor": None,
            "pnl_idio": None,
            "pnl_cost": None,
            "pnl_unexplained": None,
            "max_identity_residual": None,
            "n_computed_specific": 0,
        },
        "by_factor": {},
        "daily": [],
        "monthly": [],
        "cost": {
            "expected_bps": None,
            "expected_trading_bps": None,
            "expected_borrow_bps": None,
            "realized_bps": None,
            "n_realized": 0,
        },
        "risk": None,
        "note": note,
    }


def _period(
    frame: pd.DataFrame,
    *,
    label: str,
    note: str,
    days: int | None = None,
    monthly: pd.DataFrame | None = None,
    risk: bool = False,
) -> dict[str, Any]:
    """One attribution period: the days it holds, the sums and the risk path.

    `frame` is every row of the period, newest last, and `days` bounds only the
    per-day series that travels in the payload. The cumulative sums are over all of
    it, so a bounded series never shortens a total.
    """
    ordered = frame.sort_values("trade_date")
    carried = ordered if days is None else ordered.tail(days)
    by_factor: dict[str, float] = {}
    for record in ordered.to_dict("records"):
        split = _numbers(_json_value(record.get("pnl_factor_json"), {}))
        for name, value in split.items():
            if value is None:
                continue
            by_factor[name] = by_factor.get(name, 0.0) + float(value)
    expected = [
        float(value)
        for value in ordered.get("expected_cost_bps", [])
        if _number(value) is not None
    ]
    # The expected cost's two halves, from the reconciliation row's own parts. They
    # are averaged over the days that carry one rather than over the period, so a
    # day whose split the store never recorded cannot drag either half to zero.
    trading = [
        float(value)
        for value in ordered.get("expected_trading_bps", [])
        if _number(value) is not None
    ]
    borrow = [
        float(value)
        for value in ordered.get("expected_borrow_bps", [])
        if _number(value) is not None
    ]
    realized = [
        float(value)
        for value in ordered.get("realized_cost_bps", [])
        if _number(value) is not None
    ]
    residual = [
        abs(float(value))
        for value in ordered.get("identity_residual", [])
        if _number(value) is not None
    ]
    return {
        "label": label,
        "first_day": _day(ordered["trade_date"].iloc[0]),
        "last_day": _day(ordered["trade_date"].iloc[-1]),
        "n_days": int(len(ordered)),
        "n_days_carried": int(len(carried)),
        "cumulative": {
            "pnl_total": _number(ordered["pnl_total"].sum()),
            "pnl_factor": _number(ordered["pnl_factor"].sum()),
            "pnl_idio": _number(ordered["pnl_idio"].sum()),
            "pnl_cost": _number(ordered["pnl_cost"].sum()),
            # The fourth displayed term: the panel's own return minus the three
            # components, which is the stored residual's sum and is zero on a
            # period whose artifacts reproduce the panel.
            "pnl_unexplained": _number(ordered["identity_residual"].sum()),
            "max_identity_residual": _number(max(residual)) if residual else None,
            "n_computed_specific": int(ordered["n_computed_specific"].sum()),
        },
        "by_factor": {
            name: _number(value) for name, value in sorted(by_factor.items())
        },
        "daily": [
            {
                "trade_date": _day(record.get("trade_date")),
                "pnl_total": _number(record.get("pnl_total")),
                "pnl_factor": _number(record.get("pnl_factor")),
                "pnl_idio": _number(record.get("pnl_idio")),
                "pnl_cost": _number(record.get("pnl_cost")),
                # The term that makes the row add up: total minus the three, which
                # is the stored artifact disagreement rather than a fourth estimate.
                "pnl_unexplained": _number(record.get("identity_residual")),
                # The hedge's own factor P&L for the day: the P&L the exposure gap
                # between the two design vintages produced. On a book whose hedge
                # did its job this is the part that should have been zero.
                "pnl_timing": _number(record.get("pnl_timing")),
                "book_beta": _number(record.get("book_beta")),
                "market_return": _number(record.get("market_return")),
                "pnl_beta": _number(record.get("pnl_beta")),
                "realized_vol": _number(record.get("realized_vol")),
                "forecast_vol": _number(record.get("forecast_vol")),
                # The two books the hedge stands between: the sized book it acted
                # on, and the book that was held. The difference is what it removed.
                "pre_hedge_vol": _number(record.get("pre_hedge_vol")),
                "hedged_vol": _number(record.get("hedged_vol")),
                "factor_var_share": _number(record.get("factor_var_share")),
                "idio_var_share": _number(record.get("idio_var_share")),
            }
            for record in carried.to_dict("records")
        ],
        "monthly": _monthly_series(monthly),
        "cost": {
            "expected_bps": _mean(expected),
            # The half of the expectation a fill price can be measured against, and
            # the half it cannot: borrow is the short leg's cost over the horizon
            # and no execution price pays it.
            "expected_trading_bps": _mean(trading),
            "expected_borrow_bps": _mean(borrow),
            "realized_bps": _mean(realized),
            "n_realized": len(realized),
        },
        "risk": _risk_path(ordered) if risk else None,
        "note": note,
    }


def _monthly_series(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    """The backtest's month sums, so its chart is a decade without a decade of rows."""
    if frame is None or getattr(frame, "empty", True) or "month" not in frame.columns:
        return []
    ordered = frame.sort_values("month")
    return [
        {
            "month": str(record.get("month")),
            "pnl_total": _number(record.get("pnl_total")),
            "pnl_factor": _number(record.get("pnl_factor")),
            "pnl_idio": _number(record.get("pnl_idio")),
            "pnl_cost": _number(record.get("pnl_cost")),
            "n_sessions": int(record.get("n_sessions") or 0),
        }
        for record in ordered.to_dict("records")
    ]


def _risk_path(frame: pd.DataFrame) -> dict[str, Any] | None:
    """Today's factor-versus-specific risk split, and the path that led to it.

    Absent when no day of the period carries one: a book whose risk model could not
    reach the dates is described by the section above it and not by a share of
    nothing.
    """
    rows = [
        {
            "trade_date": _day(record.get("trade_date")),
            "factor_share": _number(record.get("factor_var_share")),
            "idio_share": _number(record.get("idio_var_share")),
            "pre_hedge_vol": _number(record.get("pre_hedge_vol")),
            "hedged_vol": _number(record.get("hedged_vol")),
        }
        for record in frame.to_dict("records")
        if _number(record.get("factor_var_share")) is not None
    ]
    if not rows:
        return None
    return {
        "as_of": rows[-1]["trade_date"],
        "factor_share": rows[-1]["factor_share"],
        "idio_share": rows[-1]["idio_share"],
        "pre_hedge_vol": rows[-1]["pre_hedge_vol"],
        "hedged_vol": rows[-1]["hedged_vol"],
        "path": rows,
    }


def attribution_block(
    frame: pd.DataFrame | None = None,
    backtest: tuple[pd.DataFrame, pd.DataFrame] | None = None,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """The attribution section: the live book, and the research panel beside it.

    The store's `attribution` table is the live book's own days, which the evening
    run fills for every day it has not already attributed, so the page and the memo
    cannot disagree about a day. The page opens on it, from `LIVE_PERIOD_START`: the
    rehearsal sessions the flip left in the table are attributed but are not the
    live book, and the note says how many were left out.

    The research panel's 2012-2026 attribution is the seed's own artifact and comes
    back as a **separate, labelled period**. It is a backtest of a book nobody
    traded, its cost is zero by construction and its identity is bounded by the
    vintage of the descriptors on file, so it is not a view to open on.

    A period's residual travels with its sums rather than being assumed away:
    `pnl_unexplained` is the stored residual and the per-day rows add up to the
    total by construction, so a decomposition that does not close is visible as its
    own band rather than absorbed into the terms beside it.
    """
    if frame is None:
        frame = store.select("attribution")
    live_frame = pd.DataFrame()
    left_out = 0
    if not frame.empty and "trade_date" in frame.columns:
        ordered = frame.sort_values("trade_date").copy()
        ordered["trade_date"] = pd.to_datetime(ordered["trade_date"])
        left_out = int((ordered["trade_date"] < pd.Timestamp(LIVE_PERIOD_START)).sum())
        start = pd.Timestamp(LIVE_PERIOD_START)
        live_frame = ordered.loc[ordered["trade_date"] >= start]
    live_note = ""
    if left_out:
        live_note = (
            f"{left_out} rehearsal session(s) before {LIVE_PERIOD_START} are stored "
            "and are not part of the live book's own period"
        )
    live = (
        _period(
            live_frame,
            label=f"the live book, from {LIVE_PERIOD_START}",
            note=live_note,
            risk=True,
        )
        if not live_frame.empty
        else _empty_period("no live session is attributed yet")
    )
    backtest_frame, monthly_frame = (
        backtest if backtest is not None else _read_backtest(root)
    )
    backtest_period = (
        _period(
            backtest_frame,
            label="the research panel, the seed's own book",
            note=(
                "a backtest of the seed book, not the live book: no leg was traded, "
                "so its cost is zero, and its identity is bounded by the vintage of "
                "the descriptors on file"
            ),
            days=ATTRIBUTION_DAYS,
            monthly=monthly_frame,
        )
        if not backtest_frame.empty
        else None
    )
    return {
        "live": live,
        "backtest": backtest_period,
        "note": "" if not live_frame.empty else "no attributed day is stored yet",
    }


def _read_backtest(root: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The research panel's attribution artifact, or two empty frames."""
    base = Path(root) if root is not None else DATA_ROOT
    daily_path = base / "attribution" / BACKTEST_DAILY
    monthly_path = base / "attribution" / BACKTEST_MONTHLY
    if not daily_path.exists():
        return pd.DataFrame(), pd.DataFrame()
    daily = pd.read_parquet(daily_path)
    monthly = pd.read_parquet(monthly_path) if monthly_path.exists() else pd.DataFrame()
    return daily, monthly


def _attribution_document(raw: Any) -> dict[str, Any]:
    """The block the run passed, or an empty one that says it was not read."""
    value = _json_value(raw, None)
    if not isinstance(value, dict):
        return empty_attribution("the run did not read the attribution store")
    return value


def payload_text(payload: dict[str, Any]) -> str:
    """The JSON text: sorted keys, no NaN, no bare NaN anywhere."""
    return store.json_text(payload, sort_keys=True) + "\n"


def r2_settings() -> dict[str, str]:
    """The four R2 variables, or an error naming what is missing."""
    missing = [name for name in R2_ENVS if not os.environ.get(name, "").strip()]
    if missing:
        raise SnapshotNotConfigured(
            f"the snapshot is on but {', '.join(missing)} "
            f"{'is' if len(missing) == 1 else 'are'} not set, so it cannot be uploaded"
        )
    return {name: os.environ[name].strip() for name in R2_ENVS}


def r2_endpoint(settings: dict[str, str] | None = None) -> str:
    """The account's S3-compatible endpoint, which is what R2 speaks."""
    values = settings or r2_settings()
    return R2_ENDPOINT_TEMPLATE.format(account=values["EFB_R2_ACCOUNT_ID"])


def r2_client(settings: dict[str, str] | None = None) -> Any:
    """A boto3 S3 client for the snapshot bucket.

    R2 is S3-compatible, so the client is a maintained library pointed at the
    account's endpoint rather than a hand-written signer: one less piece of
    cryptography in this repository and a signature the vendor keeps correct.
    `region_name="auto"` is what Cloudflare documents for R2. boto3 is imported
    here, not at module import, so the research stack and the test suite do not
    need it unless a snapshot is actually uploaded.
    """
    values = settings or r2_settings()
    import boto3  # noqa: PLC0415 - only a real upload needs the client

    return boto3.client(
        "s3",
        endpoint_url=r2_endpoint(values),
        region_name=R2_REGION,
        aws_access_key_id=values["EFB_R2_ACCESS_KEY_ID"],
        aws_secret_access_key=values["EFB_R2_SECRET_ACCESS_KEY"],
    )


def checksum_sha256(body: bytes) -> str:
    """The base64 SHA-256 R2 checks a body against, so a truncated one is refused."""
    return base64.b64encode(hashlib.sha256(body).digest()).decode()


def put_object(
    key: str,
    text: str,
    *,
    settings: dict[str, str] | None = None,
    poster: Callable[..., Any] | None = None,
) -> None:
    """One single-object PUT, with the content type and a checksum.

    One object, one key, one verb. The checksum is what makes a truncated body a
    refused upload rather than a stored one: R2 verifies it against the bytes it
    received. `poster` is the put callable, so a test drives the request's shape,
    its two keys, its body and its checksum without a network.
    """
    values = settings or r2_settings()
    body = text.encode()
    put = poster or r2_client(values).put_object
    put(
        Bucket=values["EFB_R2_BUCKET"],
        Key=key,
        Body=body,
        ContentType=CONTENT_TYPE,
        ChecksumSHA256=checksum_sha256(body),
    )


def get_object_text(
    key: str,
    *,
    settings: dict[str, str] | None = None,
    getter: Callable[..., Any] | None = None,
) -> str:
    """One single-object GET, so what the page reads can be read back.

    The only way to say that the page has the document the run published is to
    read the object the page fetches. `getter` is the get callable, so a test
    drives the read without a network.
    """
    values = settings or r2_settings()
    get = getter or r2_client(values).get_object
    response = get(Bucket=values["EFB_R2_BUCKET"], Key=key)
    body = response["Body"].read()
    return body.decode() if isinstance(body, (bytes, bytearray)) else str(body)


PAGE_BOOK_MATCH = "match"
PAGE_BOOK_EMPTY = "empty"
PAGE_BOOK_SHORT = "short"
PAGE_BOOK_UNREAD = "unread"


def check_published_book(
    *,
    expected: Any,
    key: str = LATEST_KEY,
    settings: dict[str, str] | None = None,
    getter: Callable[..., Any] | None = None,
) -> tuple[str, str]:
    """Read the published document back and compare its book to the kept set.

    The per-name list is the one thing on the page that comes from a frame rather
    than from the manifest, so it is the one thing that can go missing while every
    number around it stays right: the 2026-10-01 evening published an empty
    `book.names` beside a gross of 100%, a correct hedge and 188 orders. `expected`
    is the run's own `n_kept`, read from the same manifest the document was built
    from, so this compares the page with the run's own statement about the book
    rather than with a second file that could drift away from it.

    Returns `(verdict, line)`. The line is written for the evening's message and is
    empty when there is nothing to say. It never raises: the snapshot is written
    after the orders, so nothing here may fail a run that has already traded, and a
    read that cannot be made is `unread`, which names the bucket as the thing to
    check rather than calling the book empty.
    """
    try:
        payload = json.loads(get_object_text(key, settings=settings, getter=getter))
    except Exception as exc:  # noqa: BLE001 - the verdict is the report
        return PAGE_BOOK_UNREAD, f"could not be read back ({type(exc).__name__})"
    book = payload.get("book") if isinstance(payload, dict) else None
    entries = book.get("names") if isinstance(book, dict) else None
    published = len(entries) if isinstance(entries, list) else 0
    kept = _number(expected)
    if kept is None or kept <= 0:
        # A manifest that names no kept count cannot say what the list should be,
        # so an empty list is still reported and a non-empty one is not judged.
        if published:
            return PAGE_BOOK_MATCH, ""
        return PAGE_BOOK_EMPTY, f"empty (0 names are in {key})"
    if published == kept:
        return PAGE_BOOK_MATCH, ""
    if not published:
        return PAGE_BOOK_EMPTY, f"empty (0 of the {kept:.0f} kept names are in {key})"
    return PAGE_BOOK_SHORT, f"{published} of the {kept:.0f} kept names are in {key}"


def keys_for(close: Any) -> list[str]:
    """`latest.json` and the dated copy, in that order."""
    stamp = pd.Timestamp(close).date().isoformat() if close else "unknown"
    return [LATEST_KEY, DATED_TEMPLATE.format(close=stamp)]


def write_snapshot(
    *,
    run: dict[str, Any],
    manifest: dict[str, Any] | None = None,
    book: pd.DataFrame | None = None,
    reconciliation: dict[str, Any] | None = None,
    construction: dict[str, Any] | None = None,
    book_reason: str | None = None,
    actual: dict[str, Any] | None = None,
    bridge_block: dict[str, Any] | None = None,
    dry_run: bool = True,
    mode: str | None = None,
    poster: Callable[..., Any] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build and upload the snapshot, or record that it is deliberately off.

    Returns the summary the run stores and the message quotes: `snapshot: on
    (latest.json, snapshots/<close>.json)` or `snapshot: off (dry run)`.
    """
    resolved = check_snapshot(dry_run, mode)
    payload = build(
        run=run,
        manifest=manifest,
        book=book,
        reconciliation=reconciliation,
        construction=construction,
        book_reason=book_reason,
        actual=actual,
        bridge_block=bridge_block,
        generated_at=generated_at,
    )
    if resolved == OFF:
        payload["run_status"]["snapshot"] = f"{OFF} (dry run)"
        return {
            "mode": OFF,
            "written": [],
            "detail": f"snapshot: {OFF} (dry run)",
            "payload": payload,
        }
    text = payload_text(payload)
    written = keys_for(payload.get("target_close"))
    for key in written:
        put_object(key, text, poster=poster)
    return {
        "mode": ON,
        "written": written,
        "detail": f"snapshot: {ON} ({', '.join(written)})",
        "payload": payload,
    }


def chosen_row(manifest: dict[str, Any] | None, root: Any = None) -> dict[str, Any]:
    """The construction table's row for this manifest's construction.

    The table holds one row per candidate construction, so the row is selected by
    the name the manifest records rather than by position or by best number.
    """
    path = (
        Path(root) / "construction_table.parquet"
        if root is not None
        else Path(__file__).resolve().parents[1] / "live" / "construction_table.parquet"
    )
    if not path.exists():
        return {}
    table = pd.read_parquet(path)
    if table.empty or "construction" not in table.columns:
        return {}
    wanted = str((manifest or {}).get("construction") or "")
    if not wanted:
        return {}
    # The table names its rows by kind and floor ("share_only_20shares"), while
    # the manifest records the kind and the floor as fields, so the row is found
    # by the kind and then by the floor. An ambiguous match returns nothing
    # rather than a plausible row: the page shows the book without the table's
    # derived numbers instead of another construction's.
    rows = table.loc[table["construction"].astype(str).str.startswith(wanted)]
    floor = (manifest or {}).get("construction_floor_dollars")
    if floor and len(rows) > 1:
        rows = rows.loc[
            rows["construction"].astype(str).str.contains(f"_{int(floor)}", regex=False)
        ]
    n_kept = (manifest or {}).get("n_kept")
    if n_kept is not None and len(rows) > 1 and "n_kept" in rows.columns:
        rows = rows.loc[rows["n_kept"] == n_kept]
    if len(rows) != 1:
        return {}
    return {
        str(key): value
        for key, value in rows.iloc[-1].to_dict().items()
        if value is not None
    }


def previous_proposal() -> (
    tuple[dict[str, Any] | None, pd.DataFrame | None, str | None]
):
    """The last proposal in the store, so a stopped run still shows the book.

    Read from the store and never from `live/proposals/`. On Render the disk is
    the deploy image, so the newest file there is whatever was committed, and a
    stale evening would show the owner a book from weeks ago as the one they
    hold. The store holds the last book the loop actually proposed, with the trade
    reasons of the evening that proposed it.

    Returns the manifest, the rows and the reason the book is empty, which is None
    when it is not empty. When the store holds no proposal the book is empty and
    the reason says so; there is no fallback to a committed file, because a book
    that was never proposed is not a book the owner holds.
    """
    proposals = store.select("proposals")
    if proposals.empty:
        return None, None, NO_STORED_BOOK
    latest = proposals.sort_values("trade_date").iloc[-1].to_dict()
    manifest = _json_value(latest.get("manifest"), None)
    if not isinstance(manifest, dict):
        # A row without a manifest cannot date a book, so it is not shown as one.
        return None, None, NO_STORED_BOOK
    positions = store.select("positions")
    if positions.empty:
        return manifest, None, STORED_BOOK_HAS_NO_ROWS
    # The store hands dates back as dates from Postgres and as timestamps from the
    # parquet fallback, so the session is compared as its date string.
    keep = (
        positions["trade_date"].astype(str).str.slice(0, 10)
        == str(latest["trade_date"])[:10]
    )
    frame = positions.loc[keep]
    if frame.empty:
        return manifest, None, STORED_BOOK_HAS_NO_ROWS
    return manifest, frame.reset_index(drop=True), None
