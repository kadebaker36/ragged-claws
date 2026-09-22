"""Tiny network-free synthetic adapter proving the M0 storage contract."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import UUID

from ragged_claws.models import (
    ContentHash,
    DerivationKind,
    Event,
    EventEvidence,
    FinancialValue,
    FinancialValueKind,
    ObservationRole,
    PartialDate,
    Provenance,
    RetentionClass,
    SourceLineage,
    SourceObservation,
    TemporalPrecision,
    TemporalValue,
)
from ragged_claws.models.base import CanonicalModel, NonEmptyStr, VersionedModel
from ragged_claws.storage import (
    CanonicalParquetStore,
    DataLayout,
    RawCaptureManifest,
    capture_raw_bytes,
    deterministic_source_observation_id,
    load_envelope_records,
    persist_envelope_records,
)
from ragged_claws.temporal import (
    ActionableTimeResolver,
    AvailabilityPolicy,
    apply_availability_policy,
)

PROVIDER_NAMESPACE = "synthetic.local"
SOURCE_FAMILY = "synthetic.event"
ADAPTER_VERSION = "synthetic-adapter/1.0.0"
PARSER_VERSION = "synthetic-json/1.0.0"
TRANSFORM_VERSION = "synthetic-mapping/1.0.0"
STAGING_SCHEMA_VERSION = "1.0.0"
_SOURCE_OBSERVATION_SEMANTIC_FIELDS = (
    "schema_version",
    "provider_namespace",
    "source_native_id",
    "lineage",
    "public_time",
    "raw_content_hash",
    "adapter_version",
    "parser_version",
    "retention_class",
    "license_name",
)


class SourceObservationConflictError(RuntimeError):
    """Raised when one deterministic observation ID has conflicting semantics."""


class SyntheticFixture(CanonicalModel):
    """Invented input contract; never a production provider representation."""

    fixture_version: Literal["1.0.0"]
    source_native_id: NonEmptyStr
    event_id: UUID
    event_evidence_id: UUID
    provenance_id: UUID
    event_type: NonEmptyStr
    occurrence_date: NonEmptyStr
    published_at: NonEmptyStr
    amount: Decimal
    currency: NonEmptyStr


class SyntheticStagingRecord(VersionedModel):
    """Small source-normalized staging shape used only by the M0 synthetic adapter."""

    source_version_id: UUID
    source_native_id: NonEmptyStr
    event_id: UUID
    event_evidence_id: UUID
    provenance_id: UUID
    event_type: NonEmptyStr
    occurrence_time: TemporalValue
    public_time: TemporalValue
    amount: Decimal
    currency: NonEmptyStr


@dataclass(frozen=True)
class SyntheticBundle:
    observation: SourceObservation
    provenance: Provenance
    evidence: EventEvidence
    event: Event


@dataclass(frozen=True)
class SyntheticIngestionResult:
    manifest: RawCaptureManifest
    staging: SyntheticStagingRecord
    bundle: SyntheticBundle


class SyntheticAdapter:
    """Expose capture, normalization, mapping, and persistence as visible phases."""

    def __init__(self, layout: DataLayout) -> None:
        self.layout = layout
        self.store = CanonicalParquetStore(layout)

    @property
    def staging_path(self) -> Path:
        return self.layout.staging / "synthetic_event.parquet"

    def capture(
        self,
        raw_bytes: bytes,
        *,
        source_native_id: str,
        retrieved_at: datetime,
        observed_at: datetime,
        source_locator: str,
    ) -> RawCaptureManifest:
        return capture_raw_bytes(
            self.layout,
            raw_bytes,
            provider_namespace=PROVIDER_NAMESPACE,
            source_family=SOURCE_FAMILY,
            retrieved_at=retrieved_at,
            observed_at=observed_at,
            request_parameters={"source_native_id": source_native_id},
            source_native_id=source_native_id,
            source_locator=source_locator,
            adapter_version=ADAPTER_VERSION,
            parser_version=PARSER_VERSION,
            retention_class=RetentionClass.PUBLIC,
            license_name="synthetic-test-data",
        )

    def normalize(
        self,
        raw_bytes: bytes,
        manifest: RawCaptureManifest,
    ) -> SyntheticStagingRecord:
        fixture = SyntheticFixture.model_validate_json(raw_bytes)
        if fixture.source_native_id != manifest.source_native_id:
            raise ValueError("fixture source-native ID disagrees with capture metadata")
        observation_id = deterministic_source_observation_id(
            manifest.provider_namespace,
            fixture.source_native_id,
            manifest.content_hash.value,
        )
        occurrence = _day_value(fixture.occurrence_date)
        public_time = TemporalValue(
            raw_value=fixture.published_at,
            precision=TemporalPrecision.SECOND,
            timestamp=datetime.fromisoformat(fixture.published_at),
            source_timezone="explicit-source-offset",
        )
        return SyntheticStagingRecord(
            source_version_id=observation_id,
            source_native_id=fixture.source_native_id,
            event_id=fixture.event_id,
            event_evidence_id=fixture.event_evidence_id,
            provenance_id=fixture.provenance_id,
            event_type=fixture.event_type,
            occurrence_time=occurrence,
            public_time=public_time,
            amount=fixture.amount,
            currency=fixture.currency,
        )

    def observation(
        self,
        staging: SyntheticStagingRecord,
        manifest: RawCaptureManifest,
    ) -> SourceObservation:
        return SourceObservation(
            source_observation_id=staging.source_version_id,
            provider_namespace=PROVIDER_NAMESPACE,
            source_native_id=staging.source_native_id,
            lineage=SourceLineage(
                source_family=SOURCE_FAMILY,
                observation_role=ObservationRole.SYNTHETIC,
            ),
            retrieved_at=manifest.retrieved_at,
            observed_at=manifest.observed_at or manifest.retrieved_at,
            public_time=staging.public_time,
            raw_content_hash=ContentHash(value=manifest.content_hash.value),
            adapter_version=ADAPTER_VERSION,
            parser_version=PARSER_VERSION,
            source_locator=manifest.source_locator,
            retention_class=manifest.retention_class,
            license_name=manifest.license_name,
        )

    def canonicalize(
        self,
        staging: SyntheticStagingRecord,
        observation: SourceObservation,
    ) -> SyntheticBundle:
        public_time = observation.public_time
        if public_time is None:
            raise ValueError("synthetic observations require public-time evidence")
        provenance = Provenance(
            provenance_id=staging.provenance_id,
            source_observation_ids=(observation.source_observation_id,),
            derivation_kind=DerivationKind.SYNTHETIC_TEST,
            derived_at=observation.observed_at,
            transform_version=TRANSFORM_VERSION,
        )
        evidence = EventEvidence(
            event_evidence_id=staging.event_evidence_id,
            event_id=staging.event_id,
            source_observation_ids=(observation.source_observation_id,),
            provenance_id=provenance.provenance_id,
        )
        availability = apply_availability_policy(
            public_time,
            AvailabilityPolicy(
                policy_id="synthetic_zero_delay",
                policy_version="1.0.0",
                delay=timedelta(0),
                rationale="Synthetic public timestamp is usable without added delay.",
                source_family=SOURCE_FAMILY,
            ),
        )
        actionability = ActionableTimeResolver().resolve(availability)
        event = Event(
            event_id=staging.event_id,
            event_type=staging.event_type,
            occurrence_time=staging.occurrence_time,
            public_time=public_time,
            actionable_at=actionability.actionable_at,
            financial_values=(
                FinancialValue(
                    name="disclosed_amount",
                    kind=FinancialValueKind.MONETARY_AMOUNT,
                    value=staging.amount,
                    currency=staging.currency,
                ),
            ),
            event_evidence_ids=(evidence.event_evidence_id,),
            provenance_id=provenance.provenance_id,
        )
        return SyntheticBundle(observation, provenance, evidence, event)

    def persist(self, staging: SyntheticStagingRecord, bundle: SyntheticBundle) -> None:
        persist_envelope_records(
            self.staging_path,
            model_type=SyntheticStagingRecord,
            id_field="source_version_id",
            records=(staging,),
            dataset_kind="staging",
            model_schema_version=STAGING_SCHEMA_VERSION,
        )
        self.store.persist(SourceObservation, (bundle.observation,))
        self.store.persist(Provenance, (bundle.provenance,))
        self.store.persist(EventEvidence, (bundle.evidence,))
        self.store.persist(Event, (bundle.event,))

    def ingest(
        self,
        raw_bytes: bytes,
        *,
        source_native_id: str,
        retrieved_at: datetime,
        observed_at: datetime,
        source_locator: str = "fixture://synthetic/persistence-event",
    ) -> SyntheticIngestionResult:
        manifest = self.capture(
            raw_bytes,
            source_native_id=source_native_id,
            retrieved_at=retrieved_at,
            observed_at=observed_at,
            source_locator=source_locator,
        )
        staging = self.normalize(raw_bytes, manifest)
        candidate = self.observation(staging, manifest)
        existing = {
            value.source_observation_id: value for value in self.store.load(SourceObservation)
        }.get(candidate.source_observation_id)
        observation = _accept_source_observation(existing, candidate)
        bundle = self.canonicalize(staging, observation)
        self.persist(staging, bundle)
        return SyntheticIngestionResult(manifest, staging, bundle)

    def load_staging(self) -> tuple[SyntheticStagingRecord, ...]:
        return load_envelope_records(
            self.staging_path,
            model_type=SyntheticStagingRecord,
            id_field="source_version_id",
            dataset_kind="staging",
            model_schema_version=STAGING_SCHEMA_VERSION,
        )


def _accept_source_observation(
    existing: SourceObservation | None,
    candidate: SourceObservation,
) -> SourceObservation:
    """Reuse first-seen state only when source-version semantics still agree.

    Retrieval time, observation time, and source locator are capture context. A later
    manifest preserves their newer values while the first canonical observation remains
    unchanged. Every other source-version semantic field must agree.
    """
    if existing is None:
        return candidate
    if existing.source_observation_id != candidate.source_observation_id:
        raise SourceObservationConflictError("source observation IDs do not match")
    conflicts = [
        field_name
        for field_name in _SOURCE_OBSERVATION_SEMANTIC_FIELDS
        if getattr(existing, field_name) != getattr(candidate, field_name)
    ]
    if conflicts:
        rendered = ", ".join(conflicts)
        raise SourceObservationConflictError(
            f"source observation {existing.source_observation_id} conflicts in: {rendered}"
        )
    return existing


def _day_value(raw_value: str) -> TemporalValue:
    parsed = datetime.strptime(raw_value, "%Y-%m-%d")
    partial = PartialDate(
        raw_value=raw_value,
        precision=TemporalPrecision.DAY,
        year=parsed.year,
        month=parsed.month,
        day=parsed.day,
    )
    return TemporalValue(
        raw_value=raw_value,
        precision=TemporalPrecision.DAY,
        partial_date=partial,
    )
