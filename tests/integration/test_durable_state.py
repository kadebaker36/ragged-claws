"""Real validation/publication ordering against isolated object fakes; no cloud access."""

import importlib
import json
import os
import shutil
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from typer.testing import CliRunner

from ragged_claws.cli import app
from ragged_claws.durable.models import CloudPolicy, DurableError, FileEntry
from ragged_claws.durable.objects import (
    ConditionalConflict,
    IndeterminateWrite,
    LocalObjects,
    MemoryObjects,
    ObjectValue,
)
from ragged_claws.durable.sync import (
    POINTER_KEY,
    head,
    publish,
    restore,
    run_pipeline,
)
from ragged_claws.durable.validation import capture_layout, validate_layout
from ragged_claws.ingestion.littlesis import LittleSisAdapter
from ragged_claws.ingestion.sec import SecForm4Adapter
from ragged_claws.ingestion.synthetic import SyntheticAdapter, SyntheticStagingRecord
from ragged_claws.models import Event, RetentionClass
from ragged_claws.research.build import build
from ragged_claws.research.examples import prepare_sec
from ragged_claws.research.snapshot import digest, encoded, environment, freeze, verify_snapshot
from ragged_claws.storage import (
    CanonicalParquetStore,
    DataLayout,
    capture_raw_bytes,
    load_envelope_records,
    persist_envelope_records,
    query_catalog,
    rebuild_catalog,
)

ROOT = Path(__file__).parents[2]
NOW = datetime(2026, 10, 23, 5, tzinfo=UTC)
PUBLIC = CloudPolicy(review_reference="docs/19-durable-state.md#public-sec-scope")
INVENTED = CloudPolicy(
    scope="invented_engineering",
    invented_attestation=True,
    review_reference="fixture://INVENTED-ENGINEERING-NOT-REAL-CLOUD-RIGHTS",
)


def sec(layout: DataLayout, *, later: bool = False) -> None:
    metadata = json.loads((ROOT / "tests/fixtures/sec/provenance.json").read_bytes())
    SecForm4Adapter(layout).ingest(
        (ROOT / "tests/fixtures/sec/0000950170-24-105263.txt").read_bytes(),
        accession=metadata["accession"],
        source_locator=metadata["source_url"],
        retrieved_at=NOW + timedelta(days=int(later)),
        acceptance_timezone="America/New_York",
    )


def invented(layout: DataLayout, index: int = 1) -> None:
    value = json.loads((ROOT / "tests/fixtures/synthetic/persistence_event_v1.json").read_bytes())
    value.update(
        source_native_id=f"INVENTED-{index}",
        event_id=str(UUID(int=1000 + index)),
        event_evidence_id=str(UUID(int=2000 + index)),
        provenance_id=str(UUID(int=3000 + index)),
    )
    SyntheticAdapter(layout).ingest(
        encoded(value),
        source_native_id=value["source_native_id"],
        retrieved_at=NOW,
        observed_at=NOW,
    )


class TracedObjects(MemoryObjects):
    def __init__(self) -> None:
        super().__init__()
        self.puts: list[str] = []
        self.before: Callable[[str], None] = lambda _: None
        self.after: Callable[[str], None] = lambda _: None

    def put(self, key: str, content: bytes, *, expected_etag: str | None) -> str:
        self.before(key)
        result = super().put(key, content, expected_etag=expected_etag)
        self.puts.append(key)
        self.after(key)
        return result


def test_public_restore_ingest_validate_publish_restore_noop_append_and_cache(
    tmp_path: Path,
) -> None:
    objects = LocalObjects(tmp_path / "isolated-objects")
    initial = run_pipeline(objects, expected_parent=None, policy=PUBLIC, operation=sec)
    identity = initial.generation.generation_id
    assert initial.generation.record_counts["Event"] == 3
    with restore(objects, identity) as first:
        before = capture_layout(first.layout.root)
        (first.layout.root / ".env").write_text("INVENTED-PRIVATE-NOT-A-CREDENTIAL")
        first.layout.cache.mkdir(exist_ok=True)
        (first.layout.cache / "ignored.bin").write_bytes(b"cache")
        rebuild_catalog(first.layout)
        assert query_catalog(first.layout.catalog, "select count(*) from event")[0][0] == 3
        repeat = publish(objects, first.layout, expected_parent=identity, policy=PUBLIC)
        assert repeat.no_op and repeat.generation == initial.generation
        sec(first.layout, later=True)
        appended = publish(objects, first.layout, expected_parent=identity, policy=PUBLIC)
        assert not appended.no_op and appended.generation.parent_id == identity
        assert appended.generation.record_counts == initial.generation.record_counts
        assert len(appended.generation.files) == len(initial.generation.files) + 1
    assert not first.layout.root.exists()  # Only an owned temporary workspace was cleaned.
    with restore(objects, appended.generation.generation_id) as second:
        after = capture_layout(second.layout.root)
        assert all(after[name] == content for name, content in before.items())
        assert not second.layout.catalog.exists() and not (second.layout.root / ".env").exists()
        assert len(CanonicalParquetStore(second.layout, read_only=True).load(Event)) == 3
        rebuild_catalog(second.layout)
        assert query_catalog(second.layout.catalog, "select count(*) from event")[0][0] == 3
    with restore(objects, identity) as old:
        assert capture_layout(old.layout.root) == before


def test_invented_valid_canonical_append_and_conflicting_parent_id(tmp_path: Path) -> None:
    objects = TracedObjects()
    first = run_pipeline(objects, expected_parent=None, policy=INVENTED, operation=invented)
    identity = first.generation.generation_id
    second = run_pipeline(
        objects,
        expected_parent=identity,
        policy=INVENTED,
        operation=lambda layout: invented(layout, 2),
    )
    assert second.generation.record_counts["Event"] == 2
    with restore(objects, second.generation.generation_id) as restored:
        # Bypass the adapter: publication must independently enforce parent row identity.
        store = CanonicalParquetStore(restored.layout)
        events = store.load(Event)
        store.path_for(Event).unlink()
        store.persist(
            Event, (events[0].model_copy(update={"event_type": "different"}), *events[1:])
        )
        writes = len(objects.puts)
        with pytest.raises(DurableError, match="conflict"):
            publish(
                objects,
                restored.layout,
                expected_parent=second.generation.generation_id,
                policy=INVENTED,
            )
        assert len(objects.puts) == writes
    assert head(objects)[0].generation_id == second.generation.generation_id  # type: ignore[index]


@pytest.mark.parametrize("failure", ["ingestion", "integrity", "research"])
def test_pipeline_failure_never_advances_authority(failure: str) -> None:
    objects = TracedObjects()
    initial = run_pipeline(objects, expected_parent=None, policy=PUBLIC, operation=sec)
    original = objects.get(POINTER_KEY, limit=4096)

    def operation(layout: DataLayout) -> None:
        sec(layout, later=True)
        if failure == "integrity":
            next(layout.raw_objects.rglob("*" + "732")).write_bytes(b"corrupt")
        else:
            raise RuntimeError(f"INVENTED {failure} failure")

    writes = len(objects.puts)
    with pytest.raises((DurableError, RuntimeError)):
        run_pipeline(
            objects,
            expected_parent=initial.generation.generation_id,
            policy=PUBLIC,
            operation=operation,
        )
    assert objects.get(POINTER_KEY, limit=4096) == original and len(objects.puts) == writes
    with restore(objects, initial.generation.generation_id) as old:
        assert old.validated.record_counts["Event"] == 3


@pytest.mark.parametrize("stage", ["first_blob", "generation", "pointer", "lost_pointer_response"])
def test_interrupted_upload_preserves_old_generation(stage: str) -> None:
    objects = TracedObjects()
    initial = run_pipeline(objects, expected_parent=None, policy=PUBLIC, operation=sec)
    previous = objects.get(POINTER_KEY, limit=4096)

    def fail(key: str) -> None:
        if (
            (stage == "first_blob" and key.startswith("blobs/"))
            or (stage == "generation" and key.startswith("generations/"))
            or (stage in {"pointer", "lost_pointer_response"} and key == POINTER_KEY)
        ):
            raise IndeterminateWrite()

    if stage == "lost_pointer_response":
        objects.after = fail
    else:
        objects.before = fail
    with pytest.raises(IndeterminateWrite):
        run_pipeline(
            objects,
            expected_parent=initial.generation.generation_id,
            policy=PUBLIC,
            operation=lambda layout: sec(layout, later=True),
        )
    if stage != "lost_pointer_response":
        assert objects.get(POINTER_KEY, limit=4096) == previous
    # A lost response may have committed a fully validated new generation. Never claim otherwise.
    current = head(objects)
    assert current is not None
    with restore(objects, current[0].generation_id):
        pass
    with restore(objects, initial.generation.generation_id) as old:
        assert old.validated.record_counts["Event"] == 3


def test_stale_parent_and_pointer_race_do_not_overwrite_authority() -> None:
    objects = TracedObjects()
    initial = run_pipeline(objects, expected_parent=None, policy=INVENTED, operation=invented)
    with pytest.raises(DurableError, match="stale"):
        run_pipeline(objects, expected_parent=None, policy=INVENTED, operation=invented)

    def race(key: str) -> None:
        if key == POINTER_KEY:
            # An unrelated conditional change after the publisher's read must defeat its CAS.
            objects.values[key] = ObjectValue(
                objects.values[key].content, '"different-opaque-etag"'
            )

    objects.before = race
    with pytest.raises(ConditionalConflict):
        run_pipeline(
            objects,
            expected_parent=initial.generation.generation_id,
            policy=INVENTED,
            operation=lambda layout: invented(layout, 2),
        )
    assert head(objects)[0].generation_id == initial.generation.generation_id  # type: ignore[index]


@pytest.mark.parametrize("defect", ["missing", "corrupt", "truncated", "manifest"])
def test_missing_corrupt_or_truncated_remote_objects_never_yield_workspace(defect: str) -> None:
    objects = MemoryObjects()
    initial = run_pipeline(objects, expected_parent=None, policy=PUBLIC, operation=sec)
    if defect == "manifest":
        key = f"generations/{initial.generation.generation_id}.json"
        objects.values[key] = ObjectValue(b"{}", '"bad"')
    else:
        entry = initial.generation.files[0]
        key = f"blobs/{entry.sha256}"
        if defect == "missing":
            del objects.values[key]
        else:
            old = objects.values[key]
            objects.values[key] = ObjectValue(
                old.content[:-1] if defect == "truncated" else b"x" * len(old.content), old.etag
            )
    yielded = False
    with (
        pytest.raises((DurableError, ValueError)),
        restore(objects, initial.generation.generation_id),
    ):
        yielded = True
    assert not yielded


def test_readback_validation_precedes_pointer_and_immutable_bytes_never_overwrite() -> None:
    objects = TracedObjects()

    def corrupt(key: str) -> None:
        if key.startswith("blobs/"):
            value = objects.values[key]
            objects.values[key] = ObjectValue(b"x" * len(value.content), value.etag)

    objects.after = corrupt
    with pytest.raises(DurableError, match="hash"):
        run_pipeline(objects, expected_parent=None, policy=PUBLIC, operation=sec)
    assert head(objects) is None and POINTER_KEY not in objects.puts
    objects.after = lambda _: None
    old = dict(objects.values)
    with pytest.raises(DurableError, match="immutable_object_conflict"):
        run_pipeline(objects, expected_parent=None, policy=PUBLIC, operation=sec)
    assert all(objects.values[k] == v for k, v in old.items())


@pytest.mark.parametrize(
    "path",
    [
        "../raw/a",
        "/raw/a",
        "raw/../a",
        "raw\\a",
        "C:/raw/a",
        "cache/a",
        "raw/.env",
        "raw/CON",
        "raw/a.",
    ],
)
def test_unsafe_manifest_paths_rejected(path: str) -> None:
    with pytest.raises(ValueError):
        FileEntry(path=path, size=1, sha256="a" * 64)


def test_unsupported_file_symlink_and_bounds_rejected_before_any_upload(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path / "data")
    sec(layout)
    unsupported = layout.curated / "extra.json"
    unsupported.write_text("{}")
    objects = TracedObjects()
    with pytest.raises(DurableError, match="unsupported_canonical"):
        publish(objects, layout, expected_parent=None, policy=PUBLIC)
    assert not objects.puts
    unsupported.unlink()
    outside = tmp_path / "outside"
    outside.write_text("INVENTED private file")
    link = layout.staging / "escape.parquet"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("OS does not permit test symlink creation")
    with pytest.raises(DurableError, match="unsafe_layout"):
        publish(objects, layout, expected_parent=None, policy=PUBLIC)
    assert not objects.puts and outside.read_text() == "INVENTED private file"


@pytest.mark.parametrize("retention", [RetentionClass.RESTRICTED, RetentionClass.UNKNOWN])
def test_mixed_retention_rejected_even_without_canonical_observation(
    tmp_path: Path, retention: RetentionClass
) -> None:
    layout = DataLayout(tmp_path / "data")
    sec(layout)
    capture_raw_bytes(
        layout,
        b"INVENTED restricted fixture",
        provider_namespace="vendor.example",
        source_family="vendor.example",
        retrieved_at=NOW,
        adapter_version="invented/1",
        retention_class=retention,
    )
    objects = TracedObjects()
    with pytest.raises(DurableError) as error:
        publish(objects, layout, expected_parent=None, policy=PUBLIC)
    assert error.value.reasons["cloud_retention_or_source_not_approved"] >= 1
    assert not objects.puts


def test_share_alike_requires_review_and_notices_travel_with_generation(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path / "data")
    LittleSisAdapter(layout).ingest(
        (ROOT / "tests/fixtures/littlesis/recorded-297069.json").read_bytes(),
        source_locator="https://littlesis.org/api/relationships/297069",
        retrieved_at=NOW,
    )
    objects = TracedObjects()
    with pytest.raises(DurableError, match="cloud_retention"):
        publish(objects, layout, expected_parent=None, policy=PUBLIC)
    assert not objects.puts
    policy = PUBLIC.model_copy(
        update={"allow_littlesis": True, "review_reference": "fixture://reviewed-CC-BY-SA-4.0"}
    )
    result = publish(objects, layout, expected_parent=None, policy=policy)
    assert (
        result.generation.license_notices
        and "creativecommons.org/licenses/by-sa/4.0" in result.generation.license_notices[0]
    )
    with restore(objects, result.generation.generation_id) as clean:
        assert clean.validated.notices == result.generation.license_notices


def test_credentials_in_metadata_fail_without_echoing_value(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path / "data")
    sec(layout)
    capture_raw_bytes(
        layout,
        b"INVENTED",
        provider_namespace="sec.edgar",
        source_family="sec.ownership",
        retrieved_at=NOW,
        adapter_version="invented/1",
        retention_class=RetentionClass.PUBLIC,
        request_parameters={"api_key": "INVENTED-PRIVATE-NOT-A-REAL-SECRET"},
    )
    objects = TracedObjects()
    with pytest.raises(DurableError, match="credential_metadata") as error:
        publish(objects, layout, expected_parent=None, policy=PUBLIC)
    assert "INVENTED-PRIVATE-NOT-A-REAL-SECRET" not in str(error.value) and not objects.puts


def test_research_history_journals_and_old_code_fingerprints_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = tmp_path / "prepared"
    prepare_sec(
        prepared,
        ROOT / "tests/fixtures/sec/0000950170-24-105263.txt",
        ROOT / "tests/fixtures/sec/provenance.json",
        ROOT / "research/hypotheses/sec-p-s-v1.json",
        as_of=NOW,
    )
    layout = DataLayout(tmp_path / "durable")
    layout.create()
    snapshot = freeze(prepared, tmp_path / "frozen")
    frozen = layout.snapshots / str(snapshot.snapshot_id)
    shutil.copytree(tmp_path / "frozen", frozen)
    build(frozen, layout.research, layout.research / "registry")
    before = capture_layout(layout.root)
    objects = MemoryObjects()
    result = publish(objects, layout, expected_parent=None, policy=PUBLIC)
    _, lock, runtime = environment()
    monkeypatch.setattr(
        "ragged_claws.research.snapshot.environment", lambda: ("a" * 64, lock, runtime)
    )
    with restore(objects, result.generation.generation_id) as clean:
        assert capture_layout(clean.layout.root) == before
        historical = clean.layout.snapshots / str(snapshot.snapshot_id)
        with pytest.raises(ValueError, match="environment differs"):
            verify_snapshot(historical)
        assert (historical / "snapshot.json").read_bytes() == before[
            f"snapshots/{snapshot.snapshot_id}/snapshot.json"
        ]
    with restore(objects, result.generation.generation_id) as changed:
        finished = next(changed.layout.research.rglob("*.finished.json"))
        finished.write_text("{}")
        with pytest.raises(DurableError):
            publish(
                objects,
                changed.layout,
                expected_parent=result.generation.generation_id,
                policy=PUBLIC,
            )


def test_staging_identity_conflict_is_compared_to_restored_parent() -> None:
    objects = TracedObjects()
    first = run_pipeline(objects, expected_parent=None, policy=INVENTED, operation=invented)
    with restore(objects, first.generation.generation_id) as candidate:
        path = candidate.layout.staging / "synthetic_event.parquet"
        values = load_envelope_records(
            path,
            model_type=SyntheticStagingRecord,
            id_field="source_version_id",
            dataset_kind="staging",
            model_schema_version="1.0.0",
        )
        path.unlink()
        persist_envelope_records(
            path,
            model_type=SyntheticStagingRecord,
            id_field="source_version_id",
            records=(values[0].model_copy(update={"event_type": "changed"}),),
            dataset_kind="staging",
            model_schema_version="1.0.0",
        )
        validate_layout(candidate.layout.root, INVENTED)  # Candidate alone is structurally valid.
        before = list(objects.puts)
        with pytest.raises(DurableError, match="canonical_or_staging_identity_conflict"):
            publish(
                objects,
                candidate.layout,
                expected_parent=first.generation.generation_id,
                policy=INVENTED,
            )
        assert objects.puts == before


@pytest.mark.parametrize("defect", ["missing_manifest", "orphan_raw", "bad_parquet"])
def test_incomplete_evidence_or_schema_fails_before_upload(tmp_path: Path, defect: str) -> None:
    layout = DataLayout(tmp_path / "data")
    sec(layout)
    if defect == "missing_manifest":
        next(layout.raw_manifests.glob("*.json")).unlink()
    elif defect == "orphan_raw":
        content = b"INVENTED unknown rights"
        path = layout.raw_objects / digest(content)[:2] / digest(content)
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(content)
    else:
        (layout.curated / "event.parquet").write_bytes(b"truncated parquet")
    objects = TracedObjects()
    with pytest.raises(DurableError):
        publish(objects, layout, expected_parent=None, policy=PUBLIC)
    assert not objects.puts


def test_missing_parent_manifest_is_not_replaced_by_newest_object() -> None:
    objects = MemoryObjects()
    first = run_pipeline(objects, expected_parent=None, policy=INVENTED, operation=invented)
    second = run_pipeline(
        objects,
        expected_parent=first.generation.generation_id,
        policy=INVENTED,
        operation=lambda layout: invented(layout, 2),
    )
    del objects.values[f"generations/{first.generation.generation_id}.json"]
    with (
        pytest.raises(DurableError, match="missing"),
        restore(objects, second.generation.generation_id),
    ):
        pytest.fail("broken parent history must not be yielded")


def test_directory_escape_is_rejected_with_native_windows_junction_or_posix_symlink(
    tmp_path: Path,
) -> None:
    layout = DataLayout(tmp_path / "data")
    sec(layout)
    target = tmp_path / "outside"
    target.mkdir()
    (target / "private.txt").write_text("INVENTED private data")
    link = layout.staging / "escape"
    if os.name == "nt":
        importlib.import_module("_winapi").CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)
    with pytest.raises(DurableError, match="unsafe_layout"):
        validate_layout(layout.root, PUBLIC)
    assert (target / "private.txt").read_text() == "INVENTED private data"


def test_inactive_workflow_keeps_shared_single_writer_group_and_no_secret_path() -> None:
    path = ROOT / "ops/durable-runtime.yml.template"
    value = path.read_text()
    assert not (ROOT / ".github/workflows/durable-runtime.yml").exists()
    assert "group: ragged-claws-durable-production" in value
    assert "cancel-in-progress: false" in value and "if: ${{ false }}" in value
    assert "contents: read" in value and "ref: main" in value
    assert "secrets." not in value and "uses: actions/upload-artifact" not in value
    assert "pull_request_target:" not in value and "schedule:" not in value


def test_failed_pipeline_keeps_unpublished_inspection_history_private(tmp_path: Path) -> None:
    objects = MemoryObjects()
    first = run_pipeline(objects, expected_parent=None, policy=PUBLIC, operation=sec)
    previous = head(objects)
    roots: list[Path] = []

    def failed_inspection(layout: DataLayout) -> None:
        roots.append(layout.root)
        journal = layout.research / "registry" / "attempts" / "INVENTED.failed-inspection.json"
        journal.parent.mkdir(parents=True)
        journal.write_bytes(b"INVENTED failed-inspection evidence; no outcomes")
        raise DurableError("invented_inspection_failure")

    with pytest.raises(DurableError, match="invented_inspection_failure"):
        run_pipeline(
            objects,
            expected_parent=first.generation.generation_id,
            policy=PUBLIC,
            operation=failed_inspection,
            temporary_parent=tmp_path,
        )
    assert head(objects) == previous and roots[0].exists()
    assert (roots[0].parent / "failure-receipt.json").is_file()
    assert (
        next((roots[0] / "research").rglob("INVENTED.failed-inspection.json"))
        .read_bytes()
        .startswith(b"INVENTED")
    )


def test_offline_cli_recovery_demo_and_pinned_inspection(tmp_path: Path) -> None:
    output = tmp_path / "new-demo"
    runner = CliRunner()
    result = runner.invoke(app, ["durable-offline-demo", "--output", str(output)])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    report = json.loads((output / "recovery.json").read_bytes())
    assert summary["boundary"] == "LOCAL_FAKE_OBJECTS_NOT_REAL_R2"
    assert report["restored_event_count"] == report["duckdb_rebuild_event_count"] == 3
    assert report["no_op_repeat"] and report["previous_generation_recoverable"]
    assert report["pointer_unchanged_after_failures"] and len(report["failure_injections"]) == 2
    assert not report["real_R2_access_validated"] and not report["protocol_registered"]
    inspection = runner.invoke(
        app,
        [
            "durable-local-inspect",
            "--objects",
            str(output / "objects"),
            "--generation",
            report["authoritative_generation"],
        ],
    )
    assert inspection.exit_code == 0 and json.loads(inspection.output)["records"]["Event"] == 3
    conflict = runner.invoke(app, ["durable-offline-demo", "--output", str(output)])
    assert conflict.exit_code == 2 and "new_owned" in conflict.output
