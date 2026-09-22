"""End-to-end synthetic raw-to-canonical persistence and catalog test."""

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from ragged_claws.ingestion import SyntheticAdapter
from ragged_claws.models import Event, EventEvidence, Provenance, SourceObservation
from ragged_claws.storage import (
    CanonicalParquetStore,
    DataLayout,
    parquet_metadata,
    query_catalog,
    raw_object_path,
    rebuild_catalog,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "synthetic" / "persistence_event_v1.json"


def test_duplicate_ingestion_is_idempotent_and_catalog_is_rebuildable(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    adapter = SyntheticAdapter(layout)
    raw_bytes = FIXTURE.read_bytes()
    first = adapter.ingest(
        raw_bytes,
        source_native_id="invented-record-001",
        retrieved_at=datetime(2024, 5, 6, 21, 0, tzinfo=UTC),
        observed_at=datetime(2024, 5, 6, 21, 1, tzinfo=UTC),
    )
    curated_hashes_before = _dataset_hashes(layout.curated)
    staging_hashes_before = _dataset_hashes(layout.staging)
    catalog = rebuild_catalog(layout)
    for view_name in ("source_observation", "provenance", "event_evidence", "event"):
        assert query_catalog(catalog, f'SELECT count(*) FROM "{view_name}"') == [(1,)]
    query_before_duplicate = query_catalog(
        catalog,
        'SELECT record_id, payload_json FROM "event" ORDER BY record_id',
    )

    repeated = adapter.ingest(
        raw_bytes,
        source_native_id="invented-record-001",
        retrieved_at=datetime(2024, 5, 7, 21, 0, tzinfo=UTC),
        observed_at=datetime(2024, 5, 7, 21, 1, tzinfo=UTC),
        source_locator="fixture://synthetic/later-retrieval-location",
    )

    assert raw_object_path(layout, first.manifest.content_hash.value).read_bytes() == raw_bytes
    assert first.manifest.capture_id != repeated.manifest.capture_id
    assert len(list(layout.raw_objects.rglob(first.manifest.content_hash.value))) == 1
    assert len(list(layout.raw_manifests.glob("*.json"))) == 2
    assert first.bundle.observation == repeated.bundle.observation
    assert repeated.bundle.observation.retrieved_at == first.manifest.retrieved_at
    assert repeated.manifest.source_locator == "fixture://synthetic/later-retrieval-location"
    assert repeated.bundle.observation.source_locator == first.bundle.observation.source_locator
    assert repeated.bundle.event.public_time == repeated.bundle.observation.public_time
    assert repeated.bundle.event.actionable_at == first.bundle.event.actionable_at
    assert _dataset_hashes(layout.curated) == curated_hashes_before
    assert _dataset_hashes(layout.staging) == staging_hashes_before
    rebuilt_after_duplicate = rebuild_catalog(layout)
    query_after_duplicate = query_catalog(
        rebuilt_after_duplicate,
        'SELECT record_id, payload_json FROM "event" ORDER BY record_id',
    )
    assert query_after_duplicate == query_before_duplicate

    store = CanonicalParquetStore(layout)
    assert store.load(SourceObservation) == (first.bundle.observation,)
    assert store.load(Provenance) == (first.bundle.provenance,)
    assert store.load(EventEvidence) == (first.bundle.evidence,)
    assert store.load(Event) == (first.bundle.event,)
    assert adapter.load_staging() == (first.staging,)
    reloaded_event = store.load(Event)[0]
    assert reloaded_event.financial_values[0].value == Decimal("1234.5600")
    assert reloaded_event.financial_values[0].value.as_tuple().exponent == -4
    assert reloaded_event.public_time == first.staging.public_time

    for model_type in (SourceObservation, Provenance, EventEvidence, Event):
        metadata = parquet_metadata(store.path_for(model_type))
        assert metadata["storage_format"] == "ragged_claws.canonical_json_envelope"
        assert metadata["storage_version"] == "1.0.0"
        assert metadata["dataset_kind"] == "curated"
        assert metadata["canonical_model"] == model_type.__name__
        assert metadata["canonical_schema_version"] == "1.0.0"
        assert metadata["codec"] == "pydantic_json"
        assert metadata["codec_version"] == "1.0.0"
    assert parquet_metadata(adapter.staging_path)["dataset_kind"] == "staging"

    before_rebuild = query_catalog(
        rebuilt_after_duplicate,
        'SELECT record_id, payload_json FROM "event" ORDER BY record_id',
    )
    rebuilt_after_duplicate.unlink()
    assert not rebuilt_after_duplicate.exists()
    rebuilt = rebuild_catalog(layout)
    after_rebuild = query_catalog(
        rebuilt,
        'SELECT record_id, payload_json FROM "event" ORDER BY record_id',
    )
    assert after_rebuild == before_rebuild
    assert len(after_rebuild) == 1
    assert store.load(Event) == (first.bundle.event,)


def _dataset_hashes(directory: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.glob("*.parquet"))
    }
