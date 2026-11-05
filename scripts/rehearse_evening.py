"""Run the whole evening in dry run, for a close that already happened, and show it.

The owner's rule after the KVUE nights: before an evening-path change is merged, the
full evening is rehearsed against the real store and the real broker - reads only,
no orders - for the closes that went wrong and for one ordinary close, and each one
must end `ok` and filed, with every name-level problem on the `Excluded tonight` or
refused line rather than a stop.

**Writes are suppressed, deliberately.** A plain `EFB_DRY_RUN=true` invocation still
writes: `efb.proposals`, `positions`, `orders` and `run_status` are keyed by the trade
date, so a rehearsal of 2026-11-04 would overwrite the real proposal, book and status
for a close that has already traded. This script patches every store write to a
counter, so the reads are the production reads and nothing real moves. The broker is
read through the same clients the run uses, and the order path is in dry run, so no
order can be sent.

Usage:

    python scripts/rehearse_evening.py 2026-10-29 2026-11-02 2026-11-03 2026-11-04
    python scripts/rehearse_evening.py --tree /tmp/some-extended-tree 2026-11-04

Each close gets its own run tree, copied from the seed and extended to that close, so
the artifact layers are built exactly as the evening builds them. The email body is
composed and captured, never delivered.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger("rehearse_evening")

# The live settings the evening runs under, so the rehearsal is the production shape.
LIVE_ENV = {
    "EFB_DRY_RUN": "true",
    "EFB_CADENCE": "21",
    "EFB_CADENCE_ANCHOR": "2026-10-23",
    "EFB_DRIFT_GUARD": "0.05",
    "EFB_SNAPSHOT": "off",
    "EFB_SHORTABILITY_PRECHECK": "true",
    "EFB_FORCE_HOUR": "true",
}


class _SuppressedWrites:
    """A store whose reads are real and whose writes are counted and dropped."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._originals: dict[str, Any] = {}

    def __enter__(self) -> _SuppressedWrites:
        from live import store

        for name in ("upsert", "delete", "execute", "write_local"):
            original = getattr(store, name, None)
            if original is None:
                continue
            self._originals[name] = original

            def _noop(*args: Any, __name: str = name, **kwargs: Any) -> int:
                self.calls.append(__name__)
                return 0

            setattr(store, name, _noop)
        return self

    def __exit__(self, *exc: object) -> None:
        from live import store

        for name, original in self._originals.items():
            setattr(store, name, original)


def _prepare_tree(close: str, seed_tree: Path | None) -> tuple[Path, Path]:
    """A run tree extended to `close`, and the proposals directory beside it."""
    from live import extend, seed

    root = Path(tempfile.mkdtemp(prefix=f"efb-rehearse-{close}-"))
    tree = root / "data"
    if seed_tree is not None:
        tree.mkdir(parents=True)
        for item in Path(seed_tree).iterdir():
            target = tree / item.name
            if item.is_dir():
                import shutil

                shutil.copytree(item, target)
            else:
                import shutil

                shutil.copy2(item, target)
    else:
        seed.install(tree)
    extend.extend_archives(data_root=tree)
    extend.extend_prices(data_root=tree, end=close)
    extend.extend_shares(data_root=tree, end=close)
    extend.extend_returns(data_root=tree)
    # The corporate-actions rule is applied by `rehearse` with the evening's own
    # window (`since=before_last`), not here over the whole history: a full replay
    # re-checks every flag ever recorded, which is a different job and it asks the
    # vendor for history the evening never touches.
    extend.extend_model(data_root=tree)
    proposals = root / "proposals"
    proposals.mkdir(exist_ok=True)
    return tree, proposals


def rehearse(close: str, *, seed_tree: Path | None = None) -> dict[str, Any]:
    """One close, through every step the evening takes that can see a name.

    It stops short of `run_live_daily.main()` on purpose, and says so: `main()`
    decides its target close from the clock (`staleness.target_close(now)`), builds
    its own run tree from the seed and refuses outside the 16:00-20:00 New York
    window, so it cannot be pointed at a close that has already happened without a
    clock override that would then be in the rehearsal rather than in the code. What
    it does run is the whole decision path in the order the evening runs it - extend,
    corporate actions, the staleness gate, the proposal build with the live settings
    and the real prior book, the morning's own dry-run submit against the real
    account, and the message - which is where every name-level check lives.
    """
    from live import (
        corporate_actions,
        evening_job,
        morning_job,
        notify,
        staleness,
        store,
    )

    tree, proposals = _prepare_tree(close, seed_tree)
    captured: dict[str, Any] = {}
    started = datetime.now(UTC)
    previous_env = {name: os.environ.get(name) for name in LIVE_ENV}
    os.environ.update(LIVE_ENV)
    try:
        before_last = extend_last_session(tree)
        outcome = corporate_actions.apply_to_artifact(tree, since=before_last)
        gate = staleness.check(root=tree, target=pd.Timestamp(close))
        captured["gate"] = {
            "status": gate["status"],
            "worst": gate.get("worst_input"),
            "behind": gate.get("worst_sessions_behind"),
            "inputs": {
                name: row["sessions_behind"] for name, row in gate["inputs"].items()
            },
        }
        if gate["status"] != "ok":
            captured["body"] = staleness.describe_failures(gate["failures"])
            return {
                "close": close,
                "exit": 1,
                "status": "stale_stopped",
                "subject": "",
                "body": captured["body"],
                "gate": captured["gate"],
                "writes_suppressed": 0,
                "asset_check": None,
                "tree": str(tree),
                "seconds": round((datetime.now(UTC) - started).total_seconds(), 1),
            }
        # The book the close was priced on, from the store's own record: the account
        # today holds whatever the intervening sessions did, so a live read would
        # re-price a past close against a book it never had. The broker is still read
        # for the asset check, which is the present-tense fact this exercise is about.
        held = _stored_book(store, close)
        prior = pd.DataFrame(
            [
                {"ticker": name, "weight": weight}
                for name, weight in held["held"].items()
            ]
        )
        # The proposal the morning reads is the file `build_proposal` writes, so the
        # two modules' proposal directories are pointed at this close's own temp
        # directory: the build runs with `store=True` - the real path, and the only
        # way to get the same file the evening's morning sees - while the store
        # writes it makes are suppressed and counted.
        saved_dirs = [(evening_job, evening_job.PROPOSAL_DIR)]
        saved_dirs.append((morning_job, morning_job.PROPOSAL_DIR))
        evening_job.PROPOSAL_DIR = proposals
        morning_job.PROPOSAL_DIR = proposals
        try:
            with _SuppressedWrites() as writes:
                manifest = evening_job.build_proposal(
                    data_root=tree,
                    as_of=pd.Timestamp(close),
                    nav=float(held["nav"]),
                    store=True,
                    previous=(
                        prior.set_index("ticker")["weight"].astype(float)
                        if len(prior)
                        else None
                    ),
                    shortable=None,
                )
                morning = morning_job.run_morning(
                    close,
                    data_root=tree,
                    dry_run=True,
                    positions=held["held"],
                    quantities=held.get("held_quantities"),
                    establishment=bool(held["establishment"]),
                    forced_names=set(),
                )
        finally:
            for module, original in saved_dirs:
                module.PROPOSAL_DIR = original
        order_path = notify_dry_run(
            notify, close, manifest, morning, outcome, gate, captured
        )
        captured["writes_suppressed"] = len(writes.calls)
        return {
            "close": close,
            "exit": 0 if order_path["status"] == "ok" else 1,
            "status": order_path["status"],
            "subject": order_path["subject"],
            "body": order_path["body"],
            "gate": captured["gate"],
            "writes_suppressed": len(writes.calls),
            "asset_check": morning.get("asset_check"),
            "n_kept": manifest.get("n_kept"),
            "excluded_tonight": manifest.get("excluded_tonight"),
            "tree": str(tree),
            "seconds": round((datetime.now(UTC) - started).total_seconds(), 1),
        }
    finally:
        for name, value in previous_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _stored_book(store_module: Any, close: str) -> dict[str, Any]:
    """The close's own book and NAV from the store: what the evening priced on."""
    frame = store_module.select("positions")
    nav_frame = store_module.select("nav")
    target = pd.Timestamp(close).normalize()
    weights: dict[str, float] = {}
    if len(frame) and "trade_date" in frame.columns:
        days = pd.to_datetime(frame["trade_date"]).dt.normalize()
        earlier = frame.loc[days <= target]
        if len(earlier):
            last = pd.to_datetime(earlier["trade_date"]).dt.normalize().max()
            mask = pd.to_datetime(earlier["trade_date"]).dt.normalize() == last
            rows = earlier.loc[mask]
            weights = dict(
                zip(
                    rows["ticker"].astype(str),
                    rows["weight"].astype(float),
                    strict=True,
                )
            )
    nav = 1_000_000.0
    if len(nav_frame) and "trade_date" in nav_frame.columns:
        nav_days = pd.to_datetime(nav_frame["trade_date"]).dt.normalize()
        earlier_nav = nav_frame.loc[nav_days <= target]
        if len(earlier_nav):
            column = "nav" if "nav" in earlier_nav.columns else earlier_nav.columns[-1]
            try:
                ordered = earlier_nav.sort_values("trade_date")
                nav = float(ordered[column].iloc[-1])
            except Exception:  # noqa: BLE001 - the paper NAV is the fallback
                nav = 1_000_000.0
    return {
        "held": weights,
        "nav": nav,
        "establishment": False,
        "held_quantities": None,
        "account_read": True,
        "source": f"store positions on or before {close}",
    }


def extend_last_session(tree: Path) -> pd.Timestamp | None:
    """The session the tree last held before this rehearsal extended it."""
    from live import extend

    return extend.last_price_session(tree)


def notify_dry_run(
    notify: Any,
    close: str,
    manifest: dict[str, Any],
    morning: dict[str, Any],
    outcome: Any,
    gate: dict[str, Any],
    captured: dict[str, Any],
) -> dict[str, Any]:
    """The evening's own message, composed and not sent, from the run's own facts."""
    body = notify.compose(
        status="ok" if morning.get("complete", True) else "incomplete",
        target_close=close,
        dry_run=True,
        orders=int(morning.get("orders") or 0),
        sent_orders=int(morning.get("sent_orders") or 0),
        gross=float(morning.get("intended_notional") or 0.0),
        detail="",
        catch_up_sessions=[],
        flags=[],
        store="suppressed (rehearsal)",
        snapshot="off (rehearsal)",
        monthly_view="not built: this run published no document",
        cadence=manifest.get("cadence"),
        drift_guard=manifest.get("drift_guard"),
        excluded_tonight=manifest.get("excluded_tonight") or [],
        excluded=manifest.get("excluded_detail") or [],
        refused_legs=morning.get("refused_legs") or [],
        unconfirmed_legs=0,
        no_price=manifest.get("dropped_no_price") or [],
        no_risk=manifest.get("dropped_no_risk") or [],
        no_short=manifest.get("dropped_no_short") or [],
        missing_var=manifest.get("n_specific_var_missing"),
        asset_check=morning.get("asset_check"),
        pending_acquisitions=[],
        cost_label="rebalance",
        cost_bps=float(manifest.get("realized_cost_bps") or 0.0),
    )
    captured["body"] = body
    status = "ok" if morning.get("complete", True) else "incomplete"
    return {
        "status": status,
        "subject": "",
        "body": body,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "closes", nargs="+", help="the closes to rehearse, oldest first"
    )
    parser.add_argument(
        "--tree", type=Path, default=None, help="reuse an extended tree"
    )
    parser.add_argument(
        "--json", type=Path, default=None, help="write the results here"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    results = [rehearse(close, seed_tree=args.tree) for close in args.closes]
    for result in results:
        print("=" * 78)
        print(f"{result['close']}  exit {result['exit']}  status {result['status']}")
        print(f"subject: {result['subject']}")
        print(result["body"])
    if args.json is not None:
        args.json.write_text(json.dumps(results, indent=1))
    bad = [r for r in results if r["status"] != "ok"]
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
