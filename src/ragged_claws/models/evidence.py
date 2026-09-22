"""Source observations, canonical provenance, and event evidence links."""

from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from ragged_claws.models.base import CanonicalModel, NonEmptyStr, Slug, VersionedModel
from ragged_claws.models.temporal import TemporalValue

Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class ObservationRole(StrEnum):
    """How an observation relates to its underlying information source."""

    PRIMARY_SOURCE = "primary_source"
    VENDOR_NORMALIZED = "vendor_normalized"
    ENRICHMENT = "enrichment"
    SYNTHETIC = "synthetic"


class RetentionClass(StrEnum):
    """Repository-safe retention classification for captured material."""

    PUBLIC = "public"
    RESTRICTED = "restricted"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


class DerivationKind(StrEnum):
    """Source-independent category of canonical derivation."""

    DIRECT_MAPPING = "direct_mapping"
    NORMALIZATION = "normalization"
    ENRICHMENT = "enrichment"
    SYNTHETIC_TEST = "synthetic_test"


class SourceLineage(CanonicalModel):
    """Immediate source family and, when known, its underlying primary family."""

    source_family: Slug
    underlying_source_family: Slug | None = None
    observation_role: ObservationRole


class ContentHash(CanonicalModel):
    """Hash of the immutable raw object that produced an observation."""

    algorithm: Literal["sha256"] = "sha256"
    value: Sha256Hex


class SourceObservation(VersionedModel):
    """One captured source-native observation, distinct from a canonical event."""

    source_observation_id: UUID
    provider_namespace: Slug
    source_native_id: NonEmptyStr
    lineage: SourceLineage
    retrieved_at: AwareDatetime
    observed_at: AwareDatetime
    public_time: TemporalValue | None = None
    raw_content_hash: ContentHash
    adapter_version: NonEmptyStr
    parser_version: NonEmptyStr | None = None
    source_locator: NonEmptyStr | None = None
    retention_class: RetentionClass
    license_name: NonEmptyStr | None = None


class Provenance(VersionedModel):
    """Canonical derivation metadata, not a replacement for source observations.

    A SourceObservation describes captured source material. Provenance records how
    canonical data was derived from one or more observations. EventEvidence links
    those observations to a particular canonical event.
    """

    provenance_id: UUID
    source_observation_ids: tuple[UUID, ...] = Field(min_length=1)
    parent_provenance_ids: tuple[UUID, ...] = ()
    derivation_kind: DerivationKind
    derived_at: AwareDatetime
    transform_version: NonEmptyStr

    @model_validator(mode="after")
    def validate_unique_ids(self) -> Self:
        if len(set(self.source_observation_ids)) != len(self.source_observation_ids):
            raise ValueError("source_observation_ids must be unique")
        if len(set(self.parent_provenance_ids)) != len(self.parent_provenance_ids):
            raise ValueError("parent_provenance_ids must be unique")
        return self


class EventEvidence(VersionedModel):
    """Links one canonical event to all observations supporting that event."""

    event_evidence_id: UUID
    event_id: UUID
    source_observation_ids: tuple[UUID, ...] = Field(min_length=1)
    provenance_id: UUID

    @model_validator(mode="after")
    def validate_unique_observations(self) -> Self:
        if len(set(self.source_observation_ids)) != len(self.source_observation_ids):
            raise ValueError("source_observation_ids must be unique")
        return self
