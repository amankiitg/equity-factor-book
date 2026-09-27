"""The Cloudflare page's fixtures, built by the snapshot writer itself.

The page's tests run against JSON, never against a live store, so the fixtures
have to be real: one snapshot built from the 09-21 proposal, and the four state
variants the page has to render derived from it by `live.snapshot.build`. Nothing
here is hand-written JSON, because a hand-written snapshot can disagree with the
schema, with the writer and with the book without any test noticing.

Refresh them with:

    .venv/bin/python scripts/make_web_fixtures.py

`tests/test_e11_web_fixtures.py` rebuilds every one of them and asserts the
committed bytes are what this produces, so a change to the writer that would move
the page's input fails the suite instead of drifting into the fixtures.

The manifest is the one the evening job builds today, so `exposures_before_hedge`
and `exposures_after_hedge` are the hedge's own numbers rather than a
reconstruction, and the book's rows are that same manifest's own `kept_book`, so
the list the page draws, its count and `n_kept` are one run's answer and a test
can require them to agree. The committed `proposal_<close>.parquet` is a vintage
of an older rule, so it is read only for the two columns the manifest does not
carry, `z` and the contract alpha.

One fixture per evening type: an establishment evening, an ordinary rebalance, a
stopped run (on staleness and on an error), a run whose own deadline has passed, a
catch-up, and a closed day. The stopped and closed ones keep the last book the
loop did propose, which is the state the page has to show rather than a blank.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from live import bridge, evening_job, fills, snapshot, trade_reasons

ROOT = Path(__file__).resolve().parents[1]
PROPOSAL_DIR = ROOT / "live" / "proposals"
FIXTURE_DIR = ROOT / "web" / "fixtures"
CLOSE = "2026-09-21"
NEXT_CLOSE = "2026-09-22"
CATCH_UP_CLOSE = "2026-09-24"
STOPPED_CLOSE = "2026-09-25"
CLOSED_CLOSE = "2026-11-26"
# The evening whose account read found the PSKY position gone, three sessions
# after the close the fixtures' book is from. It is a real close from the record
# rather than a placeholder: the removal happened between the 2026-10-05 read and
# this one, and the fixture exists to carry it onto the page.
REMOVED_CLOSE = "2026-10-06"
STORE_LABEL = "local parquet (live/state/supabase)"
# The 2026-10-05 session as it was read out of the store: the sets and the legs the
# bridge needs, which the snapshot documents themselves do not carry. Read here
# rather than typed so the page's bridge is the real evening's arithmetic.
BRIDGE_SESSION = ROOT / "tests" / "fixtures" / "bridge_2026-10-05.json"
SPECIFIC = ROOT / "data" / "models" / "XS-v1" / "specific_var.parquet"
# The E12 attribution artifact: the seed book's own stored attribution, which is
# what the page's section is built from until the live days exist.
ATTRIBUTION = ROOT / "data" / "attribution" / "daily.parquet"

NAMES: tuple[str, ...] = (
    "snapshot_ok.json",
    "snapshot_stale_stopped.json",
    "snapshot_error.json",
    "snapshot_expired.json",
    "snapshot_catch_up.json",
    "snapshot_market_closed.json",
    "snapshot_establishment.json",
    "snapshot_no_book.json",
    # The account's own book beside the target book, which is the state every
    # evening is in once the 15:30 UTC reconciler has read the account.
    "snapshot_actual_holdings.json",
    # The 2026-10-05 morning's own reconciliation, which is the case the fill
    # card's denominator got wrong: 197 of 199 filled, 2 rejected, 34 never sent.
    "snapshot_fills_rejected.json",
    # The same morning, with the bridge broken: one name the book holds is not in
    # the account and nothing explains it, which is the case the bridge exists to
    # catch - the PSKY disappearance before Part B named it - and the only fixture
    # that exercises the page's amber line. Deliberately inconsistent, so no reader
    # can take it for a real session.
    "snapshot_bridge_broken.json",
    # The PSKY removal, three days later: a position that left the account with no
    # order and no activity behind it, named in `actual_holdings.exits` and carried
    # on the day's row as its own labelled adjustment rather than folded into the
    # P&L. The one fixture that exercises the page's amber line about a name that
    # walked out.
    "snapshot_position_removed.json",
)


def manifest() -> dict[str, Any]:
    """The 09-21 proposal as the evening job builds it today."""
    return evening_job.build_proposal(store=False)


def bridge_2026_10_05(*, drop_from_account: str = "") -> dict[str, Any]:
    """The bridge for the stored 2026-10-05 session, as the two runs computed it.

    The session fixture holds the sets the evening read and the account the morning
    read, so the block is built by `live.bridge` here rather than transcribed: a
    hand-written block could carry eight numbers that agree with each other and not
    with the run that published them. `drop_from_account` removes a name from the
    morning's read, which is how a broken bridge is produced - the name is then in
    the book, absent from the account and in neither of the lists that explain a
    gap, so the last identity fails and the block says so.
    """
    session = json.loads(BRIDGE_SESSION.read_text())
    evening = bridge.evening(
        close=session["close"],
        held_before=session["held_before"],
        book=session["book"],
        orders=pd.DataFrame(
            [
                {
                    "ticker": row["ticker"],
                    "intended_notional": row["intended_notional"],
                    "position_intent": row["position_intent"],
                    "reason_code": row["reason_code"],
                    "broker_order_id": "sent" if row["sent"] else "",
                }
                for row in session["orders"]
            ]
        ),
        reversals=session["deferred_reversals"],
    )
    held_after = [
        name for name in session["held_after"] if name != drop_from_account.upper()
    ]
    if drop_from_account and len(held_after) == len(session["held_after"]):
        raise RuntimeError(f"{drop_from_account} is not in the session's account")
    return bridge.completed(
        evening,
        filled=session["fills"]["filled"],
        did_not_fill=session["fills"]["did_not_fill"],
        held_after=held_after,
        book=session["book"],
        removed=session["removed_without_order"],
    )


def book(proposal: dict[str, Any], *, establishment: bool = False) -> pd.DataFrame:
    """The run's own book, name by name, carrying the reasons the run assigns.

    The rows come from the manifest the run published rather than from the
    committed `proposal_<close>.parquet`: that file is a vintage of an older rule,
    so its 150 rows and today's `n_kept` of 180 disagree at 09-21, and the page
    would list a book that is not the one its own heading counts. `kept_book` is
    the traded book the run carried into its manifest, so the list, its count and
    `n_kept` are one run's answer.

    The reasons come from `trade_reasons.assign_trade_reasons`, the function the
    run itself calls, so the page's reason column is the trade's reason and not a
    second opinion about it.
    """
    kept = pd.DataFrame(proposal.get("kept_book") or [])
    if kept.empty:
        raise RuntimeError("the manifest carries no kept book for the page")
    rows = pd.DataFrame(
        {
            "ticker": kept["ticker"].astype(str),
            "weight": kept["weight"].astype(float),
        }
    )
    rows["side"] = ["short" if weight < 0 else "long" for weight in rows["weight"]]
    # z and alpha are the page's two per-name columns that no manifest field
    # carries, so they come from the stored proposal's own rows where that vintage
    # has the name. A name the vintage lacks keeps a null rather than a guess.
    stored = pd.read_parquet(PROPOSAL_DIR / f"proposal_{CLOSE}.parquet")
    rows = rows.merge(stored[["ticker", "z", "alpha"]], on="ticker", how="left")
    specific = pd.read_parquet(SPECIFIC)
    as_of = pd.Timestamp(CLOSE)
    today_std = trade_reasons.specific_std(specific, as_of=as_of)
    # The session before this close, for the reasons and for the traded dollars
    # below. None when the close is the first one the directory holds.
    paths = sorted(PROPOSAL_DIR.glob("proposal_*.parquet"))
    previous = (
        pd.read_parquet(paths[-2])
        if len(paths) > 1 and paths[-1].stem == f"proposal_{CLOSE}"
        else None
    )
    if establishment:
        # The establishment evening, with no earlier book at all.
        reasons = trade_reasons.assign_trade_reasons(rows, None, today_std, None)
    else:
        reasons = trade_reasons.assign_trade_reasons(
            rows, previous, today_std, today_std, nav=float(proposal.get("nav") or 0.0)
        )
    merged = rows.merge(reasons[["ticker", "reason"]], on="ticker", how="left")
    merged["reason"] = merged["reason"].fillna(trade_reasons.ALPHA_MOVED)
    # The dollars the run traded in each name, which the page's trades-by-reason
    # table sums beside the held dollars. A run reads this from its own execution
    # log, and a fixture cannot: the plans the run wrote live under `live/logs/`,
    # which is not committed and not the same on any two machines. So it is derived
    # from the two stored sessions instead - the difference between this close's
    # weight and the previous close's, over the NAV the manifest sized from - which
    # is the leg the run's own delta logic would have built for the name: the whole
    # weight for a name the previous session did not carry, nothing for a name
    # unchanged between the two. Stood in for, and said so here rather than
    # presented as the evening's own log.
    nav = float(proposal.get("nav") or 0.0)
    before = (
        {str(row.ticker): float(row.weight) for row in previous.itertuples(index=False)}
        if previous is not None
        else {}
    )
    merged["traded_notional"] = [
        abs(float(weight) - float(before.get(str(ticker), 0.0))) * nav
        for ticker, weight in zip(merged["ticker"], merged["weight"])
    ]
    return merged


def _stamp(when: str) -> datetime:
    return datetime.fromisoformat(when).replace(tzinfo=UTC)


def account_book(nav: float) -> dict[str, float]:
    """The account's own book in dollars, as the broker reports it.

    Read from the stored `proposal_<close>.parquet`, which is the book the loop
    traded that evening: the committed file is a vintage of the older floor rule
    (150 names, where today's manifest keeps 188), so the account's book and the
    target book in these fixtures genuinely differ, and the page's target columns
    have real "not in the book" and "not held" rows rather than a copy of the
    target with a name or two shaved off. Weights are over the NAV the manifest
    sized from, which is the account's equity at the read.
    """
    rows = pd.read_parquet(PROPOSAL_DIR / f"proposal_{CLOSE}.parquet")
    held = {
        str(row.ticker): float(row.weight) * float(nav)
        for row in rows.itertuples(index=False)
    }
    return {ticker: value for ticker, value in held.items() if value}


def fills_report(target: dict[str, float], held: dict[str, float]) -> dict[str, Any]:
    """What the morning reconciliation found, as `reconcile_day` reports it.

    The one piece of the account fixture that stands in for a read rather than
    being one, because a fixture cannot ask the broker what became of the orders.
    The counts come from the two books: the legs the evening had to trade are the
    names it had to open (in the target, not held) plus the ones it had to close
    (held, not in the target), and two of those came back as misses. The miss lines
    are in the shape the email uses, which is `fills.unfilled_line`'s own shape.
    """
    opening = sorted(set(target) - set(held))
    closing = sorted(set(held) - set(target))
    legs = len(opening) + len(closing)
    misses = [
        f"{opening[0]} buy_to_open 4 canceled 12:15 UTC",
        f"{closing[0]} sell_to_open 3 expired 12:30 UTC",
    ]
    return {
        "trade_date": CLOSE,
        "n_orders": legs,
        "n_filled": legs - len(misses),
        "n_unfilled": len(misses),
        # Nothing was skipped at the guard: this fixture is about the account's
        # book, and a leg that was never sent has nothing to do with it.
        "not_sent": 0,
        # The realized cost of the evening that built this book, as the reconciler
        # prices it from the fills and the close. A fixture has no fills to price,
        # so the number is the fixture's own and the page is tested against it.
        "realized_cost_bps": 6.42,
        "unfilled": misses,
        "unread": [],
    }


def fills_report_rejected() -> dict[str, Any]:
    """The 2026-10-05 morning's reconciliation, with the numbers it produced.

    This is the fixture for the page's fill card, and it pins the one case the
    page got wrong: 199 orders sent, 197 filled, 2 rejected, and the 34 names
    under the $250 minimum never sent. The page read `n_orders - not_sent` as its
    denominator and printed "197 of 165 filled", subtracting the never-sent names
    a second time.

    Its counts are written here rather than derived from the fixture's own books,
    the way `fills_report` derives its. Those books are the 09-21 proposal and
    their leg count moves when the proposal moves; the bug this guards is about
    which field the denominator comes from, so the numbers have to be the
    incident's numbers whatever the book does. The miss lines are the real ones,
    in `fills.unfilled_line`'s own shape.
    """
    return {
        "trade_date": CLOSE,
        "n_orders": 199,
        "n_filled": 197,
        "n_unfilled": 2,
        # The names left untraded under the $250 minimum: never sent, so never
        # orders the broker could have filled, and counted apart from the misses.
        "not_sent": 34,
        # The realized cost of the evening that built this book, as the reconciler
        # prices it from the fills and the close. A fixture has no fills to price,
        # so the number is the fixture's own and the page is tested against it.
        "realized_cost_bps": 6.42,
        "unfilled": [
            "PSKY sell_to_close 30.11 rejected 08:00 UTC",
            "WBD sell_to_open 49 rejected 08:00 UTC",
        ],
        "unread": [],
    }
def attribution() -> dict[str, Any]:
    """The page's attribution block, from the sprint's stored artifact.

    Read through the same builder the run uses rather than stubbed by hand, so the
    fixture that covers the section has real numbers in it and a change to the
    builder reaches the page's tests. The seed artifact stands in for the live
    days until the clock has them, which is exactly what the memo and the
    walkthrough do.
    """
    if not ATTRIBUTION.exists():
        return snapshot.empty_attribution(
            "the seed attribution artifact has not been built"
        )
    return snapshot.attribution_block(pd.read_parquet(ATTRIBUTION))


def _run(**over: Any) -> dict[str, Any]:
    """A run row, of the shape `run_live_daily` hands the snapshot writer."""
    base: dict[str, Any] = {
        "status": "ok",
        "detail": "",
        "target_close": CLOSE,
        "dry_run": True,
        "store": STORE_LABEL,
        "snapshot": f"on ({snapshot.LATEST_KEY}, snapshots/{CLOSE}.json)",
        "notify_status": "sent",
        "catch_up": False,
        "catch_up_sessions": [],
        "splits": [],
        "flags": [],
        "failures": [],
        "establishment": False,
        "cost_label": "rebalance",
        # Every variant carries the same attribution, because it describes the
        # book and the book is the same in all of them.
        "attribution": attribution(),
    }
    base.update(over)
    return base


def snapshots() -> dict[str, dict[str, Any]]:
    """Every fixture, each an output of `live.snapshot.build`.

    The state variants are run rows the cron can genuinely produce, not edits of
    the ok document, so the page is tested against states the job has. Each of the
    first six keeps the 09-21 book: a stopped run still shows the last book, with
    `book_as_of` naming its close instead of the close it could not reach. The
    last one is the opposite case, a run with no book at all.
    """
    proposal = manifest()
    rows = book(proposal)
    chosen = snapshot.chosen_row(proposal)
    nav = float(proposal.get("nav") or 0.0)
    # The account's own book and the target book it is read against, both in
    # dollars over the same equity: they differ by construction (see
    # `account_book`), which is the whole point of the section.
    held = account_book(nav)
    target = {
        str(row.ticker): float(row.weight)
        for row in pd.DataFrame(proposal.get("kept_book") or []).itertuples(index=False)
    }
    built: dict[str, dict[str, Any]] = {
        NAMES[0]: snapshot.build(
            run=_run(),
            manifest=proposal,
            book=rows,
            construction=chosen,
            generated_at=_stamp("2026-09-21T22:41:00"),
        ),
        # Stale stop: the 09-22 evening could not reach the 09-22 close, so the
        # page shows the 09-21 book and says which close it is from.
        NAMES[1]: snapshot.build(
            run=_run(
                status="stale_stopped",
                target_close=STOPPED_CLOSE,
                detail=(
                    "the 09-25 evening asked for the 09-25 close and the vendor's "
                    "last usable session was 2026-09-21, past the grace"
                ),
                failures=["prices"],
                worst_input="prices",
                worst_sessions_behind=3,
                notify_status="sent",
            ),
            manifest=proposal,
            book=rows,
            construction=chosen,
            generated_at=_stamp("2026-09-25T22:41:00"),
        ),
        NAMES[2]: snapshot.build(
            run=_run(
                status="error",
                target_close=STOPPED_CLOSE,
                detail=(
                    "the proposal build raised on the 09-25 close: no usable close "
                    "price for 3 kept names"
                ),
                failures=["prices", "shares"],
                worst_input="shares",
                worst_sessions_behind=1,
                notify_status="sent",
            ),
            manifest=proposal,
            book=rows,
            construction=chosen,
            generated_at=_stamp("2026-09-25T22:41:00"),
        ),
        # Expired: an ok run whose own deadline has passed, which is the state the
        # page has to shout about rather than dress up as fresh.
        NAMES[3]: snapshot.build(
            run=_run(),
            manifest=proposal,
            book=rows,
            construction=chosen,
            generated_at=_stamp("2026-09-29T12:00:00"),
        ),
        # Catch-up: the clock resumed after a break, so the run covers the closes
        # it missed and the page labels it.
        NAMES[4]: snapshot.build(
            run=_run(
                target_close=CATCH_UP_CLOSE,
                catch_up=True,
                catch_up_sessions=[NEXT_CLOSE, "2026-09-23"],
                detail="the clock resumed after two missed evenings",
            ),
            manifest=proposal,
            book=rows,
            construction=chosen,
            generated_at=_stamp("2026-09-24T22:41:00"),
        ),
        # A closed day: Thanksgiving 2026. The run had nothing to price, so the
        # row is keyed by the closed date itself and the page must read it as a
        # day of no work rather than a day the loop broke. The book below it is
        # the last session's own, which is what the closed evening could not
        # change.
        NAMES[5]: snapshot.build(
            run=_run(
                status="market_closed",
                target_close=CLOSED_CLOSE,
                detail=f"there is no NYSE session on {CLOSED_CLOSE}",
                cost_label=None,
                notify_status="sent",
            ),
            manifest=proposal,
            book=rows,
            construction=chosen,
            generated_at=_stamp("2026-11-26T22:41:00"),
        ),
        # The establishment evening: the account is flat, the whole book is
        # opened, and every row's reason is a new position rather than a move.
        NAMES[6]: snapshot.build(
            run=_run(
                establishment=True,
                cost_label="establishment",
                detail=(
                    "the first live evening: the account is flat and the whole "
                    "book is established"
                ),
            ),
            manifest=proposal,
            book=book(proposal, establishment=True),
            construction=chosen,
            generated_at=_stamp("2026-09-21T22:41:00"),
        ),
        # No book at all: the evening found nothing in the store for the close it
        # asked for, so every number the page could derive from a book is absent
        # rather than zero, and the reason travels with the empty book. This is
        # the state that decides whether a section is hidden for want of data or
        # rendered as a row of zeroes claiming the book is flat.
        NAMES[7]: snapshot.build(
            run=_run(
                status="error",
                target_close=STOPPED_CLOSE,
                detail=(
                    "the 09-25 evening found no book in the store: nothing to price "
                    "and nothing to carry forward"
                ),
                failures=["store"],
                worst_input="store",
                cost_label=None,
            ),
            manifest=None,
            book=None,
            book_reason="the store holds no book for this close",
            generated_at=_stamp("2026-09-25T22:41:00"),
        ),
        # The account's own book, as the 15:30 UTC reconciler adds it: the book the
        # loop held after the 09-21 evening's orders settled, and the fills behind
        # it. The block is built by `fills.actual_holdings`, the function that
        # reconciler itself calls, so the fixture cannot carry a shape the page's
        # input does not have. The document is a live evening's rather than a dry
        # run's, because a block is a claim about the account and the account only
        # moves on a live evening.
        NAMES[8]: snapshot.build(
            run=_run(
                dry_run=False,
                detail="",
                notify_status="sent",
            ),
            manifest=proposal,
            book=rows,
            construction=chosen,
            actual=fills.actual_holdings(
                held,
                nav,
                as_of="2026-09-22T15:30:04+00:00",
                close=CLOSE,
                report=fills_report(target, held),
                expected_cost_bps=proposal.get("expected_establishment_cost_bps"),
                read_by=fills.READ_MORNING,
            ),
            generated_at=_stamp("2026-09-21T22:41:00"),
        ),
        # The morning of 2026-10-05's reconciliation, built the same way and with
        # the numbers that morning produced. The page's fill card is tested against
        # this document rather than against an object assembled in the test, so a
        # writer that changes what `n_orders` counts fails here as well.
        NAMES[9]: snapshot.build(
            run=_run(
                dry_run=False,
                detail="",
                notify_status="sent",
            ),
            manifest=proposal,
            book=rows,
            construction=chosen,
            actual=fills.actual_holdings(
                held,
                nav,
                as_of="2026-10-06T15:30:04+00:00",
                close=CLOSE,
                report=fills_report_rejected(),
                expected_cost_bps=proposal.get("expected_establishment_cost_bps"),
                read_by=fills.READ_MORNING,
            ),
            bridge_block=bridge_2026_10_05(),
            generated_at=_stamp("2026-09-21T22:41:00"),
        ),
        # The same morning with the bridge broken: the account holds one name fewer
        # than the book and neither a reversal nor a removal accounts for it. The
        # page has to draw that in amber with the two sides of the failing identity,
        # because a bridge that quietly agreed with itself would be the fourth number
        # to trust rather than the check it is meant to be.
        NAMES[10]: snapshot.build(
            run=_run(
                dry_run=False,
                detail="",
                notify_status="sent",
            ),
            manifest=proposal,
            book=rows,
            construction=chosen,
            actual=fills.actual_holdings(
                held,
                nav,
                as_of="2026-10-06T15:30:04+00:00",
                close=CLOSE,
                report=fills_report_rejected(),
                expected_cost_bps=proposal.get("expected_establishment_cost_bps"),
                read_by=fills.READ_MORNING,
            ),
            bridge_block=bridge_2026_10_05(drop_from_account="AEP"),
            generated_at=_stamp("2026-09-21T22:41:00"),
        ),
        # The PSKY removal, as the 2026-10-06 evening saw it. The account was read
        # that evening and PSKY was no longer in it: it had held 326.072572 shares
        # worth $3,211.81 when the previous evening read the account, and nothing
        # of the loop's explains where they went - the only closing leg of the run
        # was rejected at the open, and the broker's own activity feed names the
        # ticker nowhere between the two reads (see docs/hygiene_ledger.md). The
        # name is in `exits`, and the dollars are on the row as its own labelled
        # adjustment, which is where the page reads them: a paper-keeping artifact
        # is not a result of the strategy, and it is not netted out of the P&L in
        # silence either.
        NAMES[11]: snapshot.build(
            run=_run(
                target_close=REMOVED_CLOSE,
                dry_run=False,
                notify_status="sent",
            ),
            manifest=proposal,
            book=rows,
            construction=chosen,
            reconciliation={
                "intended_notional": 433_479.55,
                "filled_notional": 425_739.98,
                "realized_annual_vol": None,
                "expected_cost_bps": 14.54,
                "unexplained_adjustment": -3_211.81,
            },
            actual=fills.actual_holdings(
                held,
                nav,
                as_of="2026-10-06T22:41:09+00:00",
                read_by=fills.READ_EVENING,
                exits={
                    "previous_read": "2026-10-05",
                    "feed": "read",
                    "window": "2026-10-06T00:00:00Z to 2026-10-06T22:41:09+00:00",
                    "exits": [
                        {
                            "ticker": "PSKY",
                            "quantity": 326.072572039,
                            "notional": 3_211.81,
                        }
                    ],
                },
            ),
            generated_at=_stamp("2026-10-06T22:41:00"),
        ),
    }
    missing = [name for name in NAMES if name not in built]
    if missing:  # pragma: no cover - a guard against a variant going unwritten
        raise RuntimeError(f"no fixture was built for {', '.join(missing)}")
    return built


def write_all() -> list[Path]:
    """Write every fixture where the page's tests read it."""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, payload in snapshots().items():
        path = FIXTURE_DIR / name
        path.write_text(snapshot.payload_text(payload))
        written.append(path)
    return written


def main() -> int:
    for path in write_all():
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
