"""Adapter-owned LittleSis snapshot envelopes; canonical models remain authoritative."""

from typing import Literal
from uuid import UUID

from ragged_claws.models import (
    Entity,
    ExternalIdentifier,
    Provenance,
    Relationship,
    SourceObservation,
    TemporalValue,
)
from ragged_claws.models.base import CanonicalModel, UtcDatetime


class LittleSisResource(CanonicalModel):
    source_type: Literal["entities", "relationships"]
    source_id: int
    payload_json: str
    semantic_hash: str
    valid_from: TemporalValue | None
    valid_to: TemporalValue | None
    updated_at_raw: str | None
    curated_at: UtcDatetime | None
    source_urls: tuple[str, ...]


class LittleSisSnapshot(CanonicalModel):
    source_version_id: UUID
    resources: tuple[LittleSisResource, ...]
    copyright: str
    license_url: str
    api_version: str
    # Preserve pagination, source metadata and unknown fields without claiming a complete graph.
    metadata_json: str


class LittleSisMapping(CanonicalModel):
    source_type: Literal["entities", "relationships"]
    source_id: int
    canonical_id: UUID | None
    status: Literal["imported", "reused", "unresolved", "excluded"]
    reason: str | None = None


class LittleSisBundle(CanonicalModel):
    snapshot: LittleSisSnapshot
    observation: SourceObservation
    provenance: Provenance
    entities: tuple[Entity, ...]
    identifier_claims: tuple[ExternalIdentifier, ...]
    relationships: tuple[Relationship, ...]
    mappings: tuple[LittleSisMapping, ...]
    attribution: str
    change_notice: str
    transform_version: str

    @property
    def source_version_id(self) -> UUID:
        return self.snapshot.source_version_id
