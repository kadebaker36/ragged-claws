"""Canonical economic event representation."""

from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from ragged_claws.models.base import CanonicalModel, NonEmptyStr, Slug, VersionedModel
from ragged_claws.models.financial import DisclosedRange, FinancialValue
from ragged_claws.models.temporal import TemporalValue


class EventAttributeType(StrEnum):
    """Runtime type of a normalized, source-independent event attribute."""

    CODE = "code"
    TEXT = "text"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    DECIMAL = "decimal"


class EventPartyReference(CanonicalModel):
    """An entity participating in an event in a stated semantic role."""

    entity_id: UUID
    role: Slug


class EventAttribute(CanonicalModel):
    """A typed normalized event attribute, optionally retaining its raw source code."""

    name: Slug
    value_type: EventAttributeType
    value: str | bool | int | Decimal
    raw_value: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_value_type(self) -> Self:
        expected_types: dict[EventAttributeType, type[object]] = {
            EventAttributeType.CODE: str,
            EventAttributeType.TEXT: str,
            EventAttributeType.BOOLEAN: bool,
            EventAttributeType.INTEGER: int,
            EventAttributeType.DECIMAL: Decimal,
        }
        expected = expected_types[self.value_type]
        if type(self.value) is not expected:
            raise ValueError(f"{self.value_type.value} attribute requires {expected.__name__}")
        return self


class Event(VersionedModel):
    """One canonical event, independent of the observations that reported it."""

    event_id: UUID
    event_type: Slug
    actors: tuple[EventPartyReference, ...] = ()
    economic_units: tuple[EventPartyReference, ...] = ()
    issuer_entity_id: UUID | None = None
    security_id: UUID | None = None
    listing_id: UUID | None = None
    occurrence_time: TemporalValue
    public_time: TemporalValue | None = None
    actionable_at: AwareDatetime | None = None
    financial_values: tuple[FinancialValue, ...] = ()
    disclosed_ranges: tuple[DisclosedRange, ...] = ()
    attributes: tuple[EventAttribute, ...] = ()
    event_evidence_ids: tuple[UUID, ...] = Field(min_length=1)
    provenance_id: UUID

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        if self.listing_id is not None and self.security_id is None:
            raise ValueError("listing_id requires security_id")
        if self.security_id is not None and self.issuer_entity_id is None:
            raise ValueError("security_id requires issuer_entity_id")
        for field_name, parties in (
            ("actors", self.actors),
            ("economic_units", self.economic_units),
        ):
            party_keys = {(party.entity_id, party.role) for party in parties}
            if len(party_keys) != len(parties):
                raise ValueError(f"{field_name} must not contain duplicate entity/role pairs")
        semantic_names = [value.name for value in self.financial_values]
        semantic_names.extend(value.name for value in self.disclosed_ranges)
        semantic_names.extend(attribute.name for attribute in self.attributes)
        if len(set(semantic_names)) != len(semantic_names):
            raise ValueError("event financial and attribute names must be unique")
        if len(set(self.event_evidence_ids)) != len(self.event_evidence_ids):
            raise ValueError("event_evidence_ids must be unique")
        return self
