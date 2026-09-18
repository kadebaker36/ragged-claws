"""Reusable canonical model fixtures built only from synthetic values."""

from datetime import UTC, datetime
from uuid import UUID

from ragged_claws.models import (
    ContentHash,
    DerivationKind,
    ObservationRole,
    PartialDate,
    Provenance,
    RetentionClass,
    SourceLineage,
    SourceObservation,
    TemporalPrecision,
    TemporalValue,
)

OBSERVATION_ID = UUID("11111111-1111-4111-8111-111111111111")
PROVENANCE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
EVENT_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
EVIDENCE_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
ISSUER_ID = UUID("10000000-0000-4000-8000-000000000001")
PERSON_ID = UUID("10000000-0000-4000-8000-000000000002")
SECURITY_ID = UUID("20000000-0000-4000-8000-000000000001")
LISTING_ID = UUID("30000000-0000-4000-8000-000000000001")
OBSERVED_AT = datetime(2024, 5, 6, 21, 0, tzinfo=UTC)


def partial_temporal(
    raw_value: str,
    precision: TemporalPrecision,
    *,
    year: int | None = None,
    month: int | None = None,
    day: int | None = None,
) -> TemporalValue:
    partial = PartialDate(
        raw_value=raw_value,
        precision=precision,
        year=year,
        month=month,
        day=day,
    )
    return TemporalValue(raw_value=raw_value, precision=precision, partial_date=partial)


def source_observation(
    observation_id: UUID = OBSERVATION_ID,
    *,
    provider_namespace: str = "sec.edgar",
    source_native_id: str = "0000000000-24-000001",
    source_family: str = "sec.edgar.form4",
    underlying_source_family: str | None = None,
    role: ObservationRole = ObservationRole.PRIMARY_SOURCE,
) -> SourceObservation:
    return SourceObservation(
        source_observation_id=observation_id,
        provider_namespace=provider_namespace,
        source_native_id=source_native_id,
        lineage=SourceLineage(
            source_family=source_family,
            underlying_source_family=underlying_source_family,
            observation_role=role,
        ),
        retrieved_at=OBSERVED_AT,
        observed_at=OBSERVED_AT,
        public_time=TemporalValue(
            raw_value="2024-05-06T16:42:15-04:00",
            precision=TemporalPrecision.SECOND,
            timestamp=datetime.fromisoformat("2024-05-06T16:42:15-04:00"),
            source_timezone="America/New_York",
        ),
        raw_content_hash=ContentHash(value="a" * 64),
        adapter_version="test-adapter/1",
        parser_version="test-parser/1",
        source_locator="https://example.invalid/source/1",
        retention_class=RetentionClass.PUBLIC,
        license_name="synthetic-test-data",
    )


def provenance(*observation_ids: UUID) -> Provenance:
    return Provenance(
        provenance_id=PROVENANCE_ID,
        source_observation_ids=observation_ids or (OBSERVATION_ID,),
        derivation_kind=DerivationKind.SYNTHETIC_TEST,
        derived_at=OBSERVED_AT,
        transform_version="test-mapping/1",
    )
