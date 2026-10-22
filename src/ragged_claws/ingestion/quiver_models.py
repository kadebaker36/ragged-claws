"""Adapter staging only: unresolved rows are not invented canonical events."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from ragged_claws.models import (
    DisclosedRange,
    Entity,
    Event,
    EventAttribute,
    EventEvidence,
    ExternalIdentifier,
    FinancialValue,
    Provenance,
    SourceObservation,
    TemporalValue,
)
from ragged_claws.models.base import CanonicalModel, NonEmptyStr, UtcDatetime
from ragged_claws.temporal import ActionabilityResult

Endpoint = Literal["congress_v1", "congress_v2", "contracts", "lobbying"]


class QuiverRow(CanonicalModel):
    # A capture coordinate, never a vendor/native or permanent event ID.
    row_index: int = Field(ge=0)
    fact_hash: str
    event_type: str | None
    occurrence_time: TemporalValue | None
    reported_time: TemporalValue | None
    public_time: None = None
    known_from: None = None
    uploaded_time: TemporalValue | None
    modified_time: TemporalValue | None
    actionability: ActionabilityResult | None
    person_identifier: str | None
    person_name: str | None
    ticker_hint: str | None
    ownership: Literal["unknown"] = "unknown"
    subholding_assertion: str | None
    financial_values: tuple[FinancialValue, ...]
    disclosed_ranges: tuple[DisclosedRange, ...]
    vendor_assertions: tuple[EventAttribute, ...]
    quarantined_json: str
    normalization_notes: tuple[str, ...]
    reason: str | None


class ReviewedRowLink(CanonicalModel):
    """Explicit human-reviewed reconciliation; no matching by dates/names/tickers alone."""

    raw_sha256: str
    row_index: int = Field(ge=0)
    event_id: UUID
    primary_observation_id: UUID
    reviewed_at: UtcDatetime
    review_reference: NonEmptyStr


class QuiverMapping(CanonicalModel):
    row_index: int
    event_id: UUID | None
    person_id: UUID | None
    status: Literal["linked", "unresolved", "excluded"]
    reason: str | None


class QuiverBundle(CanonicalModel):
    source_version_id: UUID
    endpoint: Endpoint
    rows: tuple[QuiverRow, ...]
    observation: SourceObservation
    provenance: Provenance
    entities: tuple[Entity, ...]
    identifier_claims: tuple[ExternalIdentifier, ...]
    events: tuple[Event, ...]
    evidence: tuple[EventEvidence, ...]
    mappings: tuple[QuiverMapping, ...]
    reviewed_links: tuple[ReviewedRowLink, ...]
    synthetic: bool
    license_review_sha256: str | None
    transform_version: str
    source_schema_sha256: str
