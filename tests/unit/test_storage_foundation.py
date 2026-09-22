"""Focused tests for deterministic IDs, raw capture, and strict persistence."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from ragged_claws.models import RetentionClass, SourceObservation
from ragged_claws.storage import (
    CanonicalConflictError,
    CanonicalParquetStore,
    DataLayout,
    RawIntegrityError,
    capture_raw_bytes,
    deterministic_source_observation_id,
    load_manifest,
    raw_object_path,
)
from tests.model_helpers import source_observation


def test_source_observation_id_rule_is_stable_and_versioned() -> None:
    first = deterministic_source_observation_id(
        "synthetic.local", "invented-record-001", "a" * 64
    )
    repeated = deterministic_source_observation_id(
        "synthetic.local", "invented-record-001", "a" * 64
    )
    changed_version = deterministic_source_observation_id(
        "synthetic.local", "invented-record-001", "b" * 64
    )

    assert first == repeated
    assert first == UUID("c6d662d7-622f-563f-b673-4e0d510d62cb")
    assert first.version == 5
    assert changed_version != first


def test_raw_capture_reuses_bytes_but_preserves_distinct_retrievals(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    content = b'{"raw":"bytes remain exact"}\r\n'
    first_time = datetime(2024, 5, 6, 21, 0, tzinfo=UTC)
    later_time = datetime(2024, 5, 7, 21, 0, tzinfo=UTC)

    first = capture_raw_bytes(
        layout,
        content,
        provider_namespace="synthetic.local",
        source_family="synthetic.event",
        retrieved_at=first_time,
        request_parameters={"page": 1, "filters": {"z": True, "a": ["x", 2]}},
        source_native_id="invented-record-001",
        adapter_version="synthetic/1",
        retention_class=RetentionClass.PUBLIC,
    )
    reordered_repeat = capture_raw_bytes(
        layout,
        content,
        provider_namespace="synthetic.local",
        source_family="synthetic.event",
        retrieved_at=datetime.fromisoformat("2024-05-06T17:00:00-04:00"),
        request_parameters={"filters": {"a": ["x", 2], "z": True}, "page": 1},
        source_native_id="invented-record-001",
        adapter_version="synthetic/1",
        retention_class=RetentionClass.PUBLIC,
    )
    later = capture_raw_bytes(
        layout,
        content,
        provider_namespace="synthetic.local",
        source_family="synthetic.event",
        retrieved_at=later_time,
        request_parameters={"page": 1, "filters": {"z": True, "a": ["x", 2]}},
        source_native_id="invented-record-001",
        adapter_version="synthetic/1",
        retention_class=RetentionClass.PUBLIC,
    )

    object_path = raw_object_path(layout, first.content_hash.value)
    assert object_path.read_bytes() == content
    assert first.capture_id == reordered_repeat.capture_id
    assert reordered_repeat.retrieved_at == first_time
    assert reordered_repeat.retrieved_at.tzinfo is UTC
    assert later.capture_id != first.capture_id
    assert len(list(layout.raw_objects.rglob(first.content_hash.value))) == 1
    assert len(list(layout.raw_manifests.glob("*.json"))) == 2
    assert load_manifest(layout, later.capture_id) == later


def test_existing_raw_object_is_verified_before_reuse(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    content = b"original"
    manifest = capture_raw_bytes(
        layout,
        content,
        provider_namespace="synthetic.local",
        source_family="synthetic.event",
        retrieved_at=datetime(2024, 5, 6, tzinfo=UTC),
        source_native_id="invented-record-001",
        adapter_version="synthetic/1",
        retention_class=RetentionClass.PUBLIC,
    )
    raw_object_path(layout, manifest.content_hash.value).write_bytes(b"corrupt")

    with pytest.raises(RawIntegrityError, match="content verification"):
        capture_raw_bytes(
            layout,
            content,
            provider_namespace="synthetic.local",
            source_family="synthetic.event",
            retrieved_at=datetime(2024, 5, 7, tzinfo=UTC),
            source_native_id="invented-record-001",
            adapter_version="synthetic/1",
            retention_class=RetentionClass.PUBLIC,
        )


def test_same_canonical_id_with_different_payload_fails_loudly(tmp_path: Path) -> None:
    store = CanonicalParquetStore(DataLayout(tmp_path))
    original = source_observation()
    conflicting = original.model_copy(update={"adapter_version": "different/2"})

    assert store.persist(SourceObservation, (original,))
    assert not store.persist(SourceObservation, (original,))
    with pytest.raises(CanonicalConflictError, match="different canonical payload"):
        store.persist(SourceObservation, (conflicting,))

    assert store.load(SourceObservation) == (original,)

    empty_store = CanonicalParquetStore(DataLayout(tmp_path / "single-batch"))
    with pytest.raises(CanonicalConflictError, match="different canonical payload"):
        empty_store.persist(SourceObservation, (original, conflicting))
    assert empty_store.load(SourceObservation) == ()


def test_failed_parquet_write_keeps_prior_state_and_removes_temp_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = CanonicalParquetStore(DataLayout(tmp_path))
    original = source_observation()
    path = store.path_for(SourceObservation)
    store.persist(SourceObservation, (original,))
    before = path.read_bytes()
    additional = source_observation(
        UUID("11111111-1111-4111-8111-111111111112"),
        source_native_id="invented-record-002",
    )

    def fail_write(*args: object, **kwargs: object) -> None:
        raise OSError("synthetic write failure")

    monkeypatch.setattr("ragged_claws.storage.parquet.pq.write_table", fail_write)
    with pytest.raises(OSError, match="synthetic write failure"):
        store.persist(SourceObservation, (additional,))

    assert path.read_bytes() == before
    assert list(path.parent.glob(f".{path.name}.*.tmp")) == []
