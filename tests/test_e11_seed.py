"""The seed bucket: what is pushed, what is verified, and what is refused.

The manifest is measured from a run's own reads, the push is a local command that
refuses to run on Render, and every run downloads and verifies before it reads
anything. These tests drive a fake S3 client, so the request shapes, the hashes
and all four refusal paths are exercised without a bucket.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from live import runroot, seed
from scripts import push_seed

SETTINGS = {
    "EFB_SEED_R2_ACCOUNT_ID": "account123",
    "EFB_SEED_R2_BUCKET": "efb-seed",
    "EFB_SEED_R2_ACCESS_KEY_ID": "write-key-id",
    "EFB_SEED_R2_SECRET_ACCESS_KEY": "write-secret",
}


class _Body:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload


class _FakeS3:
    """A boto3-shaped client: records every put and answers every get."""

    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        self.objects = dict(objects or {})
        self.puts: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.puts.append(kwargs)
        self.objects[kwargs["Key"]] = kwargs["Body"]
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self.objects:
            raise KeyError(f"no {Key} in {Bucket}")
        return {"Body": _Body(self.objects[Key])}


def _tree(tmp_path: Path) -> Path:
    """A seed root with a version file and two artifacts."""
    root = tmp_path / "data"
    (root / "raw").mkdir(parents=True)
    (root / "models" / "XS-v1").mkdir(parents=True)
    (root / "VERSION.json").write_text(json.dumps({"data_hash": "abc123"}))
    (root / "raw" / "prices.parquet").write_bytes(b"prices-bytes")
    (root / "models" / "XS-v1" / "descriptors.parquet").write_bytes(b"desc-bytes")
    return root


def _manifest(root: Path) -> dict[str, Any]:
    # VERSION.json is in the seed because the run reads it: `appendix.data_hash`
    # takes the marker's data hash from it. Nothing in the live loop writes it,
    # so the seed's copy is the research pipeline's and stays that way.
    return seed.manifest_for(
        root,
        ["VERSION.json", "raw/prices.parquet", "models/XS-v1/descriptors.parquet"],
    )


# What the run reads, and how it is described. ------------------------------


def test_the_recorder_sees_a_parquet_read_and_a_text_read(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    outside = tmp_path / "elsewhere.txt"
    outside.write_text("not seed material")
    real = root / "raw" / "real.parquet"
    pd.DataFrame({"close": [1.0, 2.0]}).to_parquet(real)

    with seed.record_reads() as opened:
        pd.read_parquet(real)
        (root / "VERSION.json").read_text()
        outside.read_text()

    rels = seed.relative_reads(root, opened)

    assert rels == ["VERSION.json", "raw/real.parquet"]
    # and the wrapper is removed again, so nothing else in the process is watched
    assert pd.read_parquet.__name__ == "read_parquet"


def test_a_write_is_not_a_read(tmp_path: Path) -> None:
    root = _tree(tmp_path)

    with seed.record_reads() as opened:
        (root / "raw" / "written.parquet").write_bytes(b"written")

    assert seed.relative_reads(root, opened) == []


def test_the_manifest_describes_the_seed_not_the_run_tree(tmp_path: Path) -> None:
    """The run rewrites the files it reads, so the seed's bytes are the ones hashed."""
    seed_root = _tree(tmp_path / "pristine")
    run_tree = _tree(tmp_path / "run")
    (run_tree / "raw" / "prices.parquet").write_bytes(b"extended-and-different")

    manifest = _manifest(seed_root)

    assert manifest["n_files"] == 3
    assert manifest["data_hash"] == "abc123"
    assert manifest["total_bytes"] == sum(entry["bytes"] for entry in manifest["files"])
    entry = next(f for f in manifest["files"] if f["path"] == "raw/prices.parquet")
    assert entry["sha256"] == seed.sha256_file(seed_root / "raw" / "prices.parquet")
    assert entry["sha256"] != seed.sha256_file(run_tree / "raw" / "prices.parquet")


def test_a_file_the_run_read_but_the_seed_lacks_is_refused(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    with pytest.raises(seed.SeedUnavailable) as err:
        seed.manifest_for(root, ["raw/not_there.parquet"])
    assert "raw/not_there.parquet" in str(err.value)


def test_a_parquet_write_is_recorded_as_a_write_and_not_a_read(
    tmp_path: Path,
) -> None:
    """The write path pyarrow hides from `open`, which is why `to_parquet` is wrapped.

    Without this the recorder sees only the later read of the run's own output, and
    `manifest_for` refuses a file the seed root can never hold.
    """
    tree = tmp_path / "run"
    target = tree / "raw" / "produced.parquet"
    target.parent.mkdir(parents=True)

    with seed.record_reads() as opened:
        pd.DataFrame({"close": [1.0]}).to_parquet(target, index=False)

    assert opened.writes == {str(target)}
    assert seed.relative_reads(tree, opened) == []
    assert pd.DataFrame.to_parquet.__name__ == "to_parquet"


def test_a_file_the_run_produced_and_read_back_is_not_seed_material(
    tmp_path: Path,
) -> None:
    """Every ordinary evening fetches a session, so this is the common case."""
    seed_root = _tree(tmp_path / "pristine")
    tree = _tree(tmp_path / "run")
    # the seed tree's prices are bytes, but this one is read for real by the alias
    pd.DataFrame({"close": [1.0, 2.0]}).to_parquet(tree / "raw" / "prices.parquet")
    fetched = tree / "raw" / "spy_holdings" / "spy_holdings_2026-09-24.parquet"
    fetched.parent.mkdir(parents=True)

    with seed.record_reads() as opened:
        pd.DataFrame({"ticker": ["AAA"]}).to_parquet(fetched, index=False)
        pd.read_parquet(fetched)
        pd.read_parquet(tree / "raw" / "prices.parquet")

    material, produced = seed.seed_material(seed_root, tree, opened)

    assert produced == ["raw/spy_holdings/spy_holdings_2026-09-24.parquet"]
    assert material == ["raw/prices.parquet"]
    # and the manifest describes the seed, not the session the run just fetched
    assert seed.manifest_for(seed_root, material)["n_files"] == 1


def test_a_read_the_run_did_not_write_is_still_a_gap_in_the_seed(
    tmp_path: Path,
) -> None:
    """The control: wrapping the writers must not turn a missing input into a pass."""
    seed_root = _tree(tmp_path / "pristine")
    tree = _tree(tmp_path / "run")
    unheld = tree / "raw" / "new_input.parquet"
    pd.DataFrame({"close": [1.0]}).to_parquet(unheld, index=False)

    with seed.record_reads() as opened:
        pd.read_parquet(unheld)

    with pytest.raises(seed.SeedUnavailable) as err:
        seed.seed_material(seed_root, tree, opened)
    assert "raw/new_input.parquet" in str(err.value)
    assert "did not write" in str(err.value)


# The download, the verification, and the refusals. --------------------------


def test_download_writes_every_file_and_verifies_it(tmp_path: Path) -> None:
    seed_root = _tree(tmp_path / "pristine")
    manifest = _manifest(seed_root)
    objects = {
        entry["path"]: (seed_root / entry["path"]).read_bytes()
        for entry in manifest["files"]
    }
    client = _FakeS3(objects)
    target = tmp_path / "run" / "data"

    described = seed.download(
        target, manifest=manifest, client=client, settings=SETTINGS
    )

    assert described["n_files"] == 3
    assert (target / "raw" / "prices.parquet").read_bytes() == b"prices-bytes"
    assert (target / "VERSION.json").read_bytes() == (
        seed_root / "VERSION.json"
    ).read_bytes()


def test_a_body_with_the_wrong_hash_is_refused_before_it_is_used(
    tmp_path: Path,
) -> None:
    seed_root = _tree(tmp_path / "pristine")
    manifest = _manifest(seed_root)
    client = _FakeS3(
        {
            "VERSION.json": (seed_root / "VERSION.json").read_bytes(),
            "raw/prices.parquet": b"something-else-entirely",
        }
    )

    with pytest.raises(seed.SeedMismatch) as err:
        seed.download(
            tmp_path / "run", manifest=manifest, client=client, settings=SETTINGS
        )
    assert "raw/prices.parquet" in str(err.value)


def test_verify_refuses_a_missing_a_resized_and_a_changed_file(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    manifest = _manifest(root)

    seed.verify(root, manifest)  # the happy path first

    (root / "raw" / "prices.parquet").write_bytes(b"prices-bytes-plus-more")
    with pytest.raises(seed.SeedMismatch) as err:
        seed.verify(root, manifest)
    assert "raw/prices.parquet" in str(err.value)

    (root / "raw" / "prices.parquet").unlink()
    with pytest.raises(seed.SeedMismatch) as err:
        seed.verify(root, manifest)
    assert "is missing" in str(err.value)


def test_verify_refuses_a_tree_whose_version_hash_is_not_the_seeds(
    tmp_path: Path,
) -> None:
    """The version file ties the seed to the artifacts E1 to E10 were scored on."""
    root = _tree(tmp_path)
    manifest = _manifest(root)
    (root / "VERSION.json").write_text(json.dumps({"data_hash": "something-else"}))

    with pytest.raises(seed.SeedMismatch) as err:
        seed.verify(root, manifest)
    assert "something-else" in str(err.value)
    assert "abc123" in str(err.value)


def test_the_manifest_itself_is_refused_when_it_is_not_a_manifest(
    tmp_path: Path,
) -> None:
    client = _FakeS3({seed.MANIFEST_KEY: b'{"not": "a manifest"}'})
    with pytest.raises(seed.SeedUnavailable):
        seed.fetch_manifest(client=client, settings=SETTINGS)
    assert seed.MANIFEST_KEY in client.objects


# The push, which is local only. --------------------------------------------


def test_upload_pushes_every_file_and_the_manifest_with_a_checksum(
    tmp_path: Path,
) -> None:
    root = _tree(tmp_path)
    manifest = _manifest(root)
    client = _FakeS3()

    written = seed.upload(root, manifest, client=client, settings=SETTINGS)

    assert written == [
        "VERSION.json",
        "raw/prices.parquet",
        "models/XS-v1/descriptors.parquet",
        seed.MANIFEST_KEY,
    ]
    assert [put["Key"] for put in client.puts] == written
    prices = next(put for put in client.puts if put["Key"] == "raw/prices.parquet")
    assert prices["Bucket"] == "efb-seed"
    assert prices["Body"] == b"prices-bytes"
    assert prices["ChecksumSHA256"] == seed.checksum_sha256(b"prices-bytes")
    assert prices["ContentType"] == "application/octet-stream"
    pushed = json.loads(client.objects[seed.MANIFEST_KEY])
    assert [entry["path"] for entry in pushed["files"]] == written[:3]


def test_the_push_command_refuses_to_run_on_render(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("RENDER", "true")
    assert push_seed.main([]) == 2
    assert "never runs on Render" in capsys.readouterr().out


def test_the_seed_settings_name_the_missing_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in seed.SEED_ENVS:
        monkeypatch.delenv(name, raising=False)
    assert seed.configured() is False
    with pytest.raises(seed.SeedNotConfigured) as err:
        seed.seed_settings()
    assert seed.SEED_ENVS[0] in str(err.value)
    assert seed.SEED_ENVS[2] in str(err.value)
    monkeypatch.setenv(seed.SEED_ENVS[0], "account123")
    monkeypatch.setenv(seed.SEED_ENVS[2], "key-id")
    monkeypatch.setenv(seed.SEED_ENVS[3], "secret")
    assert seed.configured() is True
    # the bucket name is a name, not a secret, so it has a default
    assert seed.seed_settings()[seed.SEED_ENVS[1]] == seed.DEFAULT_BUCKET
    assert seed.seed_endpoint(SETTINGS) == "https://account123.r2.cloudflarestorage.com"


# The run tree's source. -----------------------------------------------------


def test_the_seed_source_is_never_guessed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in seed.SEED_ENVS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv(runroot.SEED_SOURCE_ENV, raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    with pytest.raises(runroot.RunRootUnavailable) as err:
        runroot.seed_source()
    assert runroot.SEED_SOURCE_ENV in str(err.value)
    assert seed.SEED_ENVS[0] in str(err.value)

    monkeypatch.setenv(runroot.SEED_SOURCE_ENV, "bucket")
    with pytest.raises(runroot.RunRootUnavailable):
        runroot.seed_source()

    monkeypatch.setenv(runroot.SEED_SOURCE_ENV, "local")
    assert runroot.seed_source() == "local"
    # and a local tree is refused where the deploy image holds none
    monkeypatch.setenv("RENDER", "true")
    with pytest.raises(runroot.RunRootUnavailable) as err:
        runroot.seed_source()
    assert "RENDER" in str(err.value)

    monkeypatch.delenv("RENDER")
    monkeypatch.setenv(seed.SEED_ENVS[0], "account123")
    monkeypatch.setenv(seed.SEED_ENVS[2], "key-id")
    monkeypatch.setenv(seed.SEED_ENVS[3], "secret")
    monkeypatch.delenv(runroot.SEED_SOURCE_ENV)
    assert runroot.seed_source() == "r2"


def test_prepare_copies_a_local_tree_and_refuses_one_without_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(runroot.SEED_SOURCE_ENV, "local")
    seed_root = _tree(tmp_path / "pristine")

    tree = runroot.prepare(seed=seed_root, dest=tmp_path / "run" / "data")

    assert (tree / "raw" / "prices.parquet").read_bytes() == b"prices-bytes"
    assert (tree / "VERSION.json").exists()
    # a copy, not the seed itself: writing to it leaves the seed alone
    (tree / "raw" / "prices.parquet").write_bytes(b"extended")
    assert (seed_root / "raw" / "prices.parquet").read_bytes() == b"prices-bytes"

    empty = tmp_path / "empty"
    (empty / "raw").mkdir(parents=True)
    with pytest.raises(runroot.RunRootUnavailable) as err:
        runroot.prepare(seed=empty, dest=tmp_path / "run2" / "data")
    assert "cannot start" in str(err.value)


def test_prepare_downloads_and_verifies_when_the_bucket_is_the_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The deploy path: no local tree, and a downloaded seed that must verify."""
    seed_root = _tree(tmp_path / "pristine")
    manifest = _manifest(seed_root)
    objects = {
        entry["path"]: (seed_root / entry["path"]).read_bytes()
        for entry in manifest["files"]
    }
    objects[seed.MANIFEST_KEY] = seed.manifest_text(manifest).encode()
    client = _FakeS3(objects)
    for name, value in SETTINGS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv(runroot.SEED_SOURCE_ENV, raising=False)
    monkeypatch.setattr(seed, "seed_client", lambda settings=None: client)

    tree = runroot.prepare(dest=tmp_path / "run" / "data")

    assert (tree / "raw" / "prices.parquet").read_bytes() == b"prices-bytes"
    assert runroot.seed_source() == "r2"
