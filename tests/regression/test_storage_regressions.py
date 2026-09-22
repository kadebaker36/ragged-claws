"""Storage regressions for changed versions, conflicts, and point-in-time state."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from ragged_claws.ingestion import (
    SourceObservationConflictError,
    SyntheticAdapter,
    SyntheticStagingRecord,
)
from ragged_claws.models import (
    Event,
    FeatureValue,
    ObservationRole,
    SourceLineage,
    SourceObservation,
    TemporalPrecision,
    TemporalValue,
)
from ragged_claws.storage import (
    CanonicalConflictError,
    CanonicalParquetStore,
    DataLayout,
    RawCaptureManifest,
)
from ragged_claws.temporal import EligibilityReason, evaluate_eligibility

FIXTURES = Path(__file__).parents[1] / "fixtures" / "synthetic"
FIXTURE_V1 = FIXTURES / "persistence_event_v1.json"
FIXTURE_V2 = FIXTURES / "persistence_event_v2.json"


@pytest.mark.parametrize(
    ("semantic_field", "update"),
    [
        pytest.param(
            "public_time",
            {
                "public_time": TemporalValue(
                    raw_value="2024-05-06T08:00:00-04:00",
                    precision=TemporalPrecision.SECOND,
                    timestamp=datetime.fromisoformat("2024-05-06T08:00:00-04:00"),
                )
            },
            id="public-time",
        ),
        pytest.param(
            "parser_version",
            {"parser_version": "synthetic-json/conflicting"},
            id="parser-version",
        ),
        pytest.param(
            "lineage",
            {
                "lineage": SourceLineage(
                    source_family="synthetic.changed-family",
                    observation_role=ObservationRole.SYNTHETIC,
                )
            },
            id="lineage",
        ),
    ],
)
def test_repeated_source_version_rejects_semantic_disagreement_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    semantic_field: str,
    update: dict[str, object],
) -> None:
    adapter = SyntheticAdapter(DataLayout(tmp_path))
    raw_bytes = FIXTURE_V1.read_bytes()
    first = adapter.ingest(
        raw_bytes,
        source_native_id="invented-record-001",
        retrieved_at=datetime(2024, 5, 6, 21, 0, tzinfo=UTC),
        observed_at=datetime(2024, 5, 6, 21, 1, tzinfo=UTC),
    )
    observation_path = adapter.store.path_for(SourceObservation)
    authoritative_bytes = observation_path.read_bytes()
    build_observation = adapter.observation

    def conflicting_observation(
        staging: SyntheticStagingRecord,
        manifest: RawCaptureManifest,
    ) -> SourceObservation:
        return build_observation(staging, manifest).model_copy(update=update)

    monkeypatch.setattr(adapter, "observation", conflicting_observation)
    with pytest.raises(SourceObservationConflictError, match=semantic_field):
        adapter.ingest(
            raw_bytes,
            source_native_id="invented-record-001",
            retrieved_at=datetime(2024, 5, 7, 21, 0, tzinfo=UTC),
            observed_at=datetime(2024, 5, 7, 21, 1, tzinfo=UTC),
        )

    assert observation_path.read_bytes() == authoritative_bytes
    assert adapter.store.load(SourceObservation) == (first.bundle.observation,)
    assert len(list(adapter.layout.raw_manifests.glob("*.json"))) == 2


def test_canonical_event_timing_uses_accepted_observation_public_time(tmp_path: Path) -> None:
    adapter = SyntheticAdapter(DataLayout(tmp_path))
    first = adapter.ingest(
        FIXTURE_V1.read_bytes(),
        source_native_id="invented-record-001",
        retrieved_at=datetime(2024, 5, 6, 21, 0, tzinfo=UTC),
        observed_at=datetime(2024, 5, 6, 21, 1, tzinfo=UTC),
    )
    disagreeing_staging = first.staging.model_copy(
        update={
            "public_time": TemporalValue(
                raw_value="2024-05-06T08:00:00-04:00",
                precision=TemporalPrecision.SECOND,
                timestamp=datetime.fromisoformat("2024-05-06T08:00:00-04:00"),
            )
        }
    )

    remapped = adapter.canonicalize(disagreeing_staging, first.bundle.observation)

    assert remapped.event.public_time == first.bundle.observation.public_time
    assert remapped.event.public_time != disagreeing_staging.public_time
    assert remapped.event.actionable_at == first.bundle.event.actionable_at


def test_changed_source_version_preserves_both_raw_objects_and_observations(
    tmp_path: Path,
) -> None:
    layout = DataLayout(tmp_path)
    adapter = SyntheticAdapter(layout)
    first_bytes = FIXTURE_V1.read_bytes()
    changed_bytes = FIXTURE_V2.read_bytes()
    first_manifest = adapter.capture(
        first_bytes,
        source_native_id="invented-record-001",
        retrieved_at=datetime(2024, 5, 6, 21, 0, tzinfo=UTC),
        observed_at=datetime(2024, 5, 6, 21, 1, tzinfo=UTC),
        source_locator="fixture://synthetic/persistence-event-v1",
    )
    changed_manifest = adapter.capture(
        changed_bytes,
        source_native_id="invented-record-001",
        retrieved_at=datetime(2024, 5, 7, 21, 0, tzinfo=UTC),
        observed_at=datetime(2024, 5, 7, 21, 1, tzinfo=UTC),
        source_locator="fixture://synthetic/persistence-event-v2",
    )
    first_observation = adapter.observation(
        adapter.normalize(first_bytes, first_manifest), first_manifest
    )
    changed_observation = adapter.observation(
        adapter.normalize(changed_bytes, changed_manifest), changed_manifest
    )
    adapter.store.persist(SourceObservation, (first_observation, changed_observation))

    first_path = (
        layout.raw_objects
        / first_manifest.content_hash.value[:2]
        / first_manifest.content_hash.value
    )
    changed_path = (
        layout.raw_objects
        / changed_manifest.content_hash.value[:2]
        / changed_manifest.content_hash.value
    )
    assert first_path.read_bytes() == first_bytes
    assert changed_path.read_bytes() == changed_bytes
    assert first_manifest.content_hash != changed_manifest.content_hash
    assert first_observation.source_observation_id != changed_observation.source_observation_id
    assert len(adapter.store.load(SourceObservation)) == 2


def test_changed_canonical_payload_with_same_event_id_is_not_reconciled_silently(
    tmp_path: Path,
) -> None:
    adapter = SyntheticAdapter(DataLayout(tmp_path))
    first = adapter.ingest(
        FIXTURE_V1.read_bytes(),
        source_native_id="invented-record-001",
        retrieved_at=datetime(2024, 5, 6, 21, 0, tzinfo=UTC),
        observed_at=datetime(2024, 5, 6, 21, 1, tzinfo=UTC),
    )
    conflicting = first.bundle.event.model_copy(update={"event_type": "synthetic_correction"})

    with pytest.raises(CanonicalConflictError, match="different canonical payload"):
        adapter.store.persist(Event, (conflicting,))

    assert adapter.store.load(Event) == (first.bundle.event,)


def test_point_in_time_metadata_survives_parquet_roundtrip(tmp_path: Path) -> None:
    store = CanonicalParquetStore(DataLayout(tmp_path))
    later_known = FeatureValue(
        feature_value_id=UUID("80000000-0000-4000-8000-000000000099"),
        name="later_known_metric",
        value=Decimal("0.1200"),
        known_from=TemporalValue(
            raw_value="2024-01-01T00:00:00Z",
            precision=TemporalPrecision.SECOND,
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        ),
        source_observation_ids=(UUID("11111111-1111-4111-8111-111111111111"),),
    )
    store.persist(FeatureValue, (later_known,))

    reloaded = store.load(FeatureValue)[0]
    decision = evaluate_eligibility(
        snapshot_at=datetime(2020, 6, 1, tzinfo=UTC),
        known_from=reloaded.known_from,
    )

    assert reloaded == later_known
    assert isinstance(reloaded.value, Decimal)
    assert reloaded.value.as_tuple().exponent == -4
    assert not decision.eligible
    assert decision.reason is EligibilityReason.KNOWN_AFTER_SNAPSHOT
