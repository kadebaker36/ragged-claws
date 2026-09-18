"""Canonical economic event representation."""

from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from ragged_claws.models.base import Slug, VersionedModel
from ragged_claws.models.financial import DisclosedRange, FinancialValue
from ragged_claws.models.temporal import TemporalValue


class Event(VersionedModel):
    """One canonical event, independent of the observations that reported it."""

    event_id: UUID
    event_type: Slug
    actor_entity_ids: tuple[UUID, ...] = ()
    issuer_entity_id: UUID | None = None
    security_id: UUID | None = None
    listing_id: UUID | None = None
    occurrence_time: TemporalValue
    public_time: TemporalValue | None = None
    actionable_at: AwareDatetime | None = None
    financial_values: tuple[FinancialValue, ...] = ()
    disclosed_ranges: tuple[DisclosedRange, ...] = ()
    event_evidence_ids: tuple[UUID, ...] = Field(min_length=1)
    provenance_id: UUID

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        if self.listing_id is not None and self.security_id is None:
            raise ValueError("listing_id requires security_id")
        if self.security_id is not None and self.issuer_entity_id is None:
            raise ValueError("security_id requires issuer_entity_id")
        if len(set(self.actor_entity_ids)) != len(self.actor_entity_ids):
            raise ValueError("actor_entity_ids must be unique")
        if len(set(self.event_evidence_ids)) != len(self.event_evidence_ids):
            raise ValueError("event_evidence_ids must be unique")
        return self
