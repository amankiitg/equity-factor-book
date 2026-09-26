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

The book is the 09-21 proposal with the trade reasons the run assigns, and the
manifest is the one the evening job builds today, so `exposures_before_hedge` and
`exposures_after_hedge` are the hedge's own numbers rather than a reconstruction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from live import evening_job, snapshot, trade_reasons

ROOT = Path(__file__).resolve().parents[1]
PROPOSAL_DIR = ROOT / "live" / "proposals"
FIXTURE_DIR = ROOT / "web" / "fixtures"
CLOSE = "2026-09-21"
NEXT_CLOSE = "2026-09-22"
CATCH_UP_CLOSE = "2026-09-24"
STOPPED_CLOSE = "2026-09-25"
STORE_LABEL = "local parquet (live/state/supabase)"
SPECIFIC = ROOT / "data" / "models" / "XS-v1" / "specific_var.parquet"

NAMES: tuple[str, ...] = (
    "snapshot_ok.json",
    "snapshot_stale_stopped.json",
    "snapshot_error.json",
    "snapshot_expired.json",
    "snapshot_catch_up.json",
)


def manifest() -> dict[str, Any]:
    """The 09-21 proposal as the evening job builds it today."""
    return evening_job.build_proposal(store=False)


def book() -> pd.DataFrame:
    """The same close's rows, carrying the reasons the run assigns them.

    The reasons come from `trade_reasons.assign_trade_reasons`, the function the
    run itself calls, so the page's reason column is the trade's reason and not a
    second opinion about it.
    """
    rows = pd.read_parquet(PROPOSAL_DIR / f"proposal_{CLOSE}.parquet")
    paths = sorted(PROPOSAL_DIR.glob("proposal_*.parquet"))
    previous = (
        pd.read_parquet(paths[-2])
        if len(paths) > 1 and paths[-1].stem == f"proposal_{CLOSE}"
        else None
    )
    specific = pd.read_parquet(SPECIFIC)
    as_of = pd.Timestamp(CLOSE)
    today_std = trade_reasons.specific_std(specific, as_of=as_of)
    reasons = trade_reasons.assign_trade_reasons(rows, previous, today_std, today_std)
    merged = rows.merge(reasons[["ticker", "reason"]], on="ticker", how="left")
    merged["reason"] = merged["reason"].fillna("alpha moved")
    return merged


def _stamp(when: str) -> datetime:
    return datetime.fromisoformat(when).replace(tzinfo=UTC)


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
    }
    base.update(over)
    return base


def snapshots() -> dict[str, dict[str, Any]]:
    """Every fixture, each an output of `live.snapshot.build`.

    The four variants are run rows the cron can genuinely produce, not edits of
    the ok document, so the page is tested against states the job has, and each
    variant keeps the 09-21 book: a stopped run still shows the last book, with
    `book_as_of` naming its close instead of the close it could not reach.
    """
    proposal = manifest()
    rows = book()
    chosen = snapshot.chosen_row(proposal)
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
