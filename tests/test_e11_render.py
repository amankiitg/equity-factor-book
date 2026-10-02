"""Sprint E11 Part B: Render, Supabase, Alpaca and the live dashboard."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from live import alpaca, store, trade_reasons

ROOT = Path(__file__).resolve().parents[1]


def test_alpaca_dry_run_connect_returns_none() -> None:
    assert alpaca.connect(dry_run=True) is None


def test_alpaca_live_connect_names_the_missing_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if importlib.util.find_spec("alpaca") is not None:
        pytest.skip("alpaca-py is installed")
    monkeypatch.setenv("EFB_ALPACA_PAPER_API_KEY", "k")
    monkeypatch.setenv("EFB_ALPACA_PAPER_SECRET_KEY", "s")
    with pytest.raises(RuntimeError, match="alpaca-py"):
        alpaca.connect(dry_run=False)


def test_store_unknown_table_raises() -> None:
    with pytest.raises(ValueError, match="unknown live-series table"):
        store.upsert("not_a_table", [{"a": 1}])


def test_store_local_fallback_is_disjoint_from_state_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EFB_SUPABASE_DB_URL", raising=False)
    monkeypatch.setattr(store, "LOCAL_DIR", tmp_path)
    store.upsert(
        "nav", [{"trade_date": "2026-09-22", "nav": 100000.0, "realized_pnl": 0.0}]
    )
    frame = store.select("nav")
    assert len(frame) == 1
    assert float(frame["nav"].iloc[0]) == 100000.0
    assert (tmp_path / "nav.parquet").exists()


def test_store_is_supabase_false_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EFB_SUPABASE_DB_URL", raising=False)
    assert store.is_supabase() is False


def test_trade_reasons_classify_each_bucket() -> None:
    today = pd.DataFrame(
        {
            "ticker": ["A", "B", "C", "D"],
            "weight": [0.02, 0.02, 0.02, 0.01],
            "z": [1.5, 1.0, 1.0, 1.0],
        }
    )
    previous = pd.DataFrame(
        {
            "ticker": ["A", "B", "C", "D"],
            "weight": [0.01, 0.01, 0.01, 0.01],
            "z": [1.0, 1.0, 1.0, 1.0],
        }
    )
    today_specific = pd.Series({"A": 0.3, "B": 0.5, "C": 0.3, "D": 0.3})
    previous_specific = pd.Series({"A": 0.3, "B": 0.3, "C": 0.3, "D": 0.3})
    reasons = trade_reasons.assign_trade_reasons(
        today, previous, today_specific, previous_specific
    ).set_index("ticker")["reason"]
    assert reasons["A"] == "alpha moved"
    assert reasons["B"] == "risk moved"
    assert reasons["C"] == "the hedge moved"
    assert reasons["D"] == "no trade"


def test_trade_reasons_new_name_is_alpha() -> None:
    """A name new to a book that exists entered on its score: a new name.

    With no earlier book at all it is the establishment day instead, and every
    row says "new position": nothing moved, because nothing was there to move.
    """
    today = pd.DataFrame({"ticker": ["X"], "weight": [0.03], "z": [0.9]})
    existing_book = pd.DataFrame({"ticker": ["Y"], "weight": [0.02], "z": [1.0]})

    reasons = trade_reasons.assign_trade_reasons(
        today, existing_book, pd.Series(dtype=float), None
    )
    assert reasons["reason"].iloc[0] == "new name"

    established = trade_reasons.assign_trade_reasons(
        today, None, pd.Series(dtype=float), None
    )
    assert established["reason"].iloc[0] == "new position"


def test_render_dashboard_reads_no_research_parquet() -> None:
    """The Render app reads the live series and two tiny files, never a
    research parquet, so acceptance 7 holds by construction."""
    source = (ROOT / "live" / "dashboard_app.py").read_text()
    assert "read_parquet" not in source
    assert "data/" not in source


def test_render_dashboard_labels_the_construction_from_the_artifact() -> None:
    """The Render page's construction label is generated from the proposal's
    stored fields, never asserted beside the artifact."""
    from live import dashboard_app

    assert (
        dashboard_app._construction_label(
            {
                "construction": "share_only",
                "construction_floor_dollars": None,
                "construction_floor_shares": 20,
                "construction_top_n": None,
                "floor_iterated": True,
            }
        )
        == "min 20 shares (iterated to a fixed point)"
    )
    assert (
        dashboard_app._construction_label(
            {"construction": "min_position", "construction_floor_dollars": 5000.0}
        )
        == "min position $5,000 (one pass, not iterated)"
    )


def test_render_dashboard_reports_missing_construction_fields() -> None:
    from live import dashboard_app

    assert dashboard_app._construction_label({}) == (
        "construction parameters not recorded in this artifact"
    )


def test_the_regenerated_proposal_is_the_share_only_book() -> None:
    """Part 6 regenerated it under share-only; Part 5 regenerated it again on
    the 150-name drop-then-admit book. Both the D10 header and the Render page
    label it from its own fields."""
    import json

    from live import dashboard_app

    manifest = json.loads(
        (ROOT / "live" / "proposals" / "proposal_2026-09-21.json").read_text()
    )
    assert manifest["construction"] == "share_only"
    assert manifest["construction_floor_shares"] == 20
    assert manifest["construction_floor_dollars"] is None
    assert manifest["floor_iterated"] is True
    assert manifest["floor_rule"] == "drop_then_admit"
    assert manifest["n_kept"] == 150
    assert manifest["n_dropped"] == 349
    assert dashboard_app._construction_label(manifest) == (
        "min 20 shares (iterated to a fixed point)"
    )


def test_whole_share_quantization_counts_zero_rounds() -> None:
    rows = pd.DataFrame({"ticker": ["A", "B"], "weight": [0.000001, -0.000001]})
    prices = {"A": 100.0, "B": 100.0}
    nav = 1_000_000.0
    # each target notional is 1 dollar, one whole share costs 100, so both
    # round to zero shares, one long and one short
    result = alpaca.whole_share_quantization(rows, prices, nav)
    assert result["long_targets_rounding_to_zero"] == 1
    assert result["short_targets_rounding_to_zero"] == 1
    assert result["gross_weight_error"] > 0


def test_require_empty_account_rejects_existing_positions() -> None:
    class Account:
        id = "acct-efb"

    class Client:
        def get_account(self):
            return Account()

        def get_all_positions(self):
            return [object()]

    with pytest.raises(RuntimeError, match="refusing to trade"):
        alpaca.require_empty_account(Client())


def test_env_example_names_the_keys_without_values() -> None:
    text = (ROOT / ".env.example").read_text()
    lines = text.splitlines()
    # two keys carry safe non-secret defaults; every other key is empty
    defaults = {
        "EFB_DB_SCHEMA": "efb",
        "EFB_DRY_RUN": "true",
        "EFB_STORE": "local",
        "EFB_SEED_SOURCE": "local",
    }
    for name in (
        "EFB_ALPACA_PAPER_API_KEY",
        "EFB_ALPACA_PAPER_SECRET_KEY",
        "EFB_SUPABASE_DB_URL",
        "EFB_DB_SCHEMA",
        "EFB_SUPABASE_PROJECT_URL",
        "EFB_SUPABASE_ACCESS_TOKEN",
        "EFB_DRY_RUN",
        "EFB_STORE",
        "EFB_INIT_STORE",
        "EFB_SEED_R2_ACCOUNT_ID",
        "EFB_SEED_R2_BUCKET",
        "EFB_SEED_R2_ACCESS_KEY_ID",
        "EFB_SEED_R2_SECRET_ACCESS_KEY",
        "EFB_SEED_SOURCE",
        "EFB_RESEND_API_KEY",
        "EFB_NOTIFY_EMAIL_FROM",
        "EFB_NOTIFY_EMAIL_TO",
    ):
        match = [line for line in lines if line.startswith(name)]
        assert match, f"{name} missing from .env.example"
        expected = f"{name}={defaults.get(name, '')}"
        assert (
            match[0] == expected
        ), "the example carries only safe defaults, never a secret"


def test_render_yaml_commits_key_names_not_values() -> None:
    render = (ROOT / "render.yaml").read_text()
    assert "EFB_ALPACA_PAPER_API_KEY" in render
    assert "EFB_ALPACA_PAPER_SECRET_KEY" in render
    # direct Postgres, never PostgREST
    assert "EFB_SUPABASE_DB_URL" in render
    assert "EFB_DB_SCHEMA" in render
    assert "EFB_INIT_STORE" in render
    # the seed bucket: the cron reads it and has no write path into it
    assert "EFB_SEED_R2_ACCESS_KEY_ID" in render
    assert "EFB_SEED_R2_SECRET_ACCESS_KEY" in render
    # the account-wide access token must never reach a Render service
    assert "EFB_SUPABASE_ACCESS_TOKEN" not in render
    assert "EFB_SUPABASE_SECRET_KEY" not in render
    assert "sync: false" in render
    assert "AKIA" not in render
    assert "-----BEGIN" not in render


def _declared(service: str, name: str) -> bool:
    """Whether the blueprint declares this env var for a service.

    Matched on the declaration line rather than on the name, so the prose that
    explains why a variable is absent cannot read as a declaration.
    """
    return f"      - key: {name}\n" in service


# The one environment group both crons take, and the thirteen keys it holds. The
# same list is in `render.yaml`'s header (the reviewable copy) and this is the copy
# the tests compare against, so a key cannot be added to one without the other.
GROUP = "efb-live"
SHARED_KEYS = (
    "EFB_SUPABASE_DB_URL",
    "EFB_DB_SCHEMA",
    "EFB_ALPACA_PAPER_API_KEY",
    "EFB_ALPACA_PAPER_SECRET_KEY",
    "EFB_ALPACA_ACCOUNT_ID",
    "EFB_RESEND_API_KEY",
    "EFB_NOTIFY_EMAIL_FROM",
    "EFB_NOTIFY_EMAIL_TO",
    "EFB_SNAPSHOT",
    "EFB_R2_ACCOUNT_ID",
    "EFB_R2_BUCKET",
    "EFB_R2_ACCESS_KEY_ID",
    "EFB_R2_SECRET_ACCESS_KEY",
)


def test_render_yaml_runs_two_crons_and_only_the_evening_one_can_trade() -> None:
    """Two cron jobs, one that trades and one that only reads.

    No web service, so no read role and one fewer box to fall over. The
    reconciliation has to be its own job: it is the one that reports what the
    broker did with the evening's orders, and a read that fails must not be able
    to fail the run that prices the close, nor be hidden by it.
    """
    render = (ROOT / "render.yaml").read_text()
    assert "- type: web" not in render
    assert "efb-live-dashboard" not in render
    assert render.count("- type: cron") == 2
    evening, morning = render.split("    name: efb-fills-reconcile")
    # The shared keys live in one environment group now, so neither service
    # declares them and the filling job's environment is the group's.
    assert "      - fromGroup: efb-live\n" in evening
    assert "      - fromGroup: efb-live\n" in morning
    for name in SHARED_KEYS:
        assert not _declared(evening, name), f"{name} is the group's, not the cron's"
        assert not _declared(morning, name), f"{name} is the group's, not the cron's"
    for name in (
        "EFB_INIT_STORE",
        "EFB_DRY_RUN",
        "EFB_SEED_R2_ACCOUNT_ID",
        "EFB_SEED_R2_BUCKET",
        "EFB_SEED_R2_ACCESS_KEY_ID",
        "EFB_SEED_R2_SECRET_ACCESS_KEY",
    ):
        assert _declared(evening, name), f"{name} missing from the evening cron"
        assert not _declared(morning, name), f"{name} is not the fills cron's to hold"
    # names only: no key material, no address, no endpoint prose
    assert "re_" not in render
    assert "@" not in render
    # and the channel the code no longer has is gone from the blueprint
    assert "SLACK" not in render
    assert "EFB_NOTIFY_SLACK_WEBHOOK_URL" not in render


def test_the_environment_group_is_documented_with_exactly_the_keys_it_holds() -> None:
    """One list, in the file, that the group and the tests both answer to.

    Render ignores `sync: false` inside an environment group, so the group cannot
    be declared here with placeholder values: it would come out empty and every
    key would be missing. It is created in the dashboard instead, and this file
    carries the key NAMES so that what the group must hold is reviewable and
    testable rather than remembered. `tests/test_week1_fills_cron.py` checks the
    job's own runtime reads against the same list.
    """
    render = (ROOT / "render.yaml").read_text()
    header, _ = render.split("services:")
    for name in SHARED_KEYS:
        assert name in header, f"{name} is not documented in the blueprint header"
    # the keys the group must NOT hold, so cron 2 cannot inherit them
    for name in (
        "EFB_DRY_RUN",
        "EFB_INIT_STORE",
        "EFB_SEED_R2_ACCOUNT_ID",
        "EFB_SEED_R2_BUCKET",
        "EFB_SEED_R2_ACCESS_KEY_ID",
        "EFB_SEED_R2_SECRET_ACCESS_KEY",
        "EFB_STORE",
    ):
        assert (
            name
            not in header.split("The group holds exactly these")[1].split(
                "The evening cron adds"
            )[0]
        ), f"{name} must not be in the shared group"
    # and the file says why the group is not declared here
    assert "sync: false` inside an environment group" in header


def test_the_fills_reconciliation_is_its_own_weekday_morning_cron() -> None:
    """15:00 UTC on weekdays, the morning after the close it reconciles.

    Alpaca holds a DAY order for the after-hours session, so it fills at the next
    09:30 New York open; 15:00 UTC is 11:00 EDT and 10:00 EST, after that open on
    both sides of the daylight-time change, so the fills of one close cannot be
    read as the next one's and no leg is read while it is still working. The
    arithmetic against the exchange's own calendar is in
    `tests/test_week1_fills_cron.py`; this pins the file to the slot in code.
    """
    from scripts import reconcile_fills

    render = (ROOT / "render.yaml").read_text()
    _, morning = render.split("    name: efb-fills-reconcile")
    hour, minute = reconcile_fills.RUN_SLOT_UTC
    assert f'schedule: "{minute} {hour} * * 1-5"' in morning
    assert "startCommand: python scripts/reconcile_fills.py" in morning
    assert "plan: 2c-4g" in morning
    # the evening job's own slot is untouched
    evening = render.split("    name: efb-fills-reconcile")[0]
    assert 'schedule: "30 22 * * 1-5"' in evening
    assert "startCommand: python scripts/run_live_daily.py" in evening


def test_the_cron_is_created_on_the_four_gigabyte_plan() -> None:
    """Without `plan`, Render creates a cron on 0.5c-512mb and the peak kills it.

    The measured peak is 1.07 GiB, so the plan has to be at least 4 GB to keep the
    2x headroom rule. From Render's Blueprint reference, the `plan` field's Cron
    Job table: `2c-4g` is 2 CPU and 4 GB, and the same page says an omitted field
    gives a new cron job `0.5c-512mb`. The fills cron has no measurement of its
    own, so it is created on the plan whose measurement exists rather than on a
    smaller one that reads as a saving until it falls over.
    """
    render = (ROOT / "render.yaml").read_text()
    services = render.split("- type: cron")[1:]
    assert len(services) == 2
    for service in services:
        assert "plan: 2c-4g" in service
    assert "plan: 0.5c-512mb" not in render
    assert "plan: 1c-2g" not in render
