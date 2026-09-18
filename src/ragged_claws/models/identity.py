"""Canonical entity, security, listing, and relationship representations."""

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from ragged_claws.models.base import CanonicalModel, NonEmptyStr, Slug, VersionedModel
from ragged_claws.models.temporal import TemporalValue

Mic = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9]{4}$")]


class EntityType(StrEnum):
    PERSON = "person"
    HOUSEHOLD = "household"
    ISSUER = "issuer"
    ORGANIZATION = "organization"
    FUND = "fund"
    GOVERNMENT_BODY = "government_body"
    NONPROFIT = "nonprofit"
    LEGAL_ENTITY = "legal_entity"


class AliasType(StrEnum):
    LEGAL_NAME = "legal_name"
    TRADE_NAME = "trade_name"
    FORMER_NAME = "former_name"
    SOURCE_REPORTED = "source_reported"
    OTHER = "other"


class IdentifierSubjectType(StrEnum):
    ENTITY = "entity"
    SECURITY = "security"
    LISTING = "listing"


class ExternalIdentifierType(StrEnum):
    SEC_CIK = "sec_cik"
    LEI = "lei"
    FIGI_INSTRUMENT = "figi_instrument"
    FIGI_SHARE_CLASS = "figi_share_class"
    FIGI_COMPOSITE = "figi_composite"
    ISIN = "isin"
    CUSIP = "cusip"
    SEDOL = "sedol"
    OTHER = "other"


class SecurityType(StrEnum):
    COMMON_STOCK = "common_stock"
    PREFERRED_STOCK = "preferred_stock"
    DEPOSITARY_RECEIPT = "depositary_receipt"
    FUND_SHARE = "fund_share"
    OTHER = "other"


class SubjectType(StrEnum):
    ENTITY = "entity"
    SECURITY = "security"
    LISTING = "listing"


class EntityAlias(VersionedModel):
    """A source-backed alias claim; aliases never define canonical identity."""

    entity_alias_id: UUID
    entity_id: UUID
    value: NonEmptyStr
    alias_type: AliasType
    source_observation_id: UUID
    provenance_id: UUID
    valid_from: TemporalValue | None = None
    valid_to: TemporalValue | None = None
    known_from: TemporalValue | None = None
    observed_at: AwareDatetime


class ExternalIdentifier(VersionedModel):
    """A typed, source-backed identifier claim for a canonical subject."""

    external_identifier_id: UUID
    subject_type: IdentifierSubjectType
    subject_id: UUID
    identifier_type: ExternalIdentifierType
    value: NonEmptyStr
    namespace: Slug | None = None
    source_observation_id: UUID
    provenance_id: UUID
    valid_from: TemporalValue | None = None
    valid_to: TemporalValue | None = None
    known_from: TemporalValue | None = None
    observed_at: AwareDatetime

    @model_validator(mode="after")
    def validate_namespace(self) -> Self:
        if self.identifier_type is ExternalIdentifierType.OTHER and self.namespace is None:
            raise ValueError("OTHER identifiers require an explicit namespace")
        if self.identifier_type is not ExternalIdentifierType.OTHER and self.namespace is not None:
            raise ValueError("known identifier types must not override their namespace")
        return self


class Entity(VersionedModel):
    """Opaque canonical identity for a person, household, issuer, or organization."""

    entity_id: UUID
    entity_type: EntityType
    display_name: NonEmptyStr
    aliases: tuple[EntityAlias, ...] = ()
    external_identifiers: tuple[ExternalIdentifier, ...] = ()
    provenance_id: UUID

    @model_validator(mode="after")
    def validate_claim_subjects(self) -> Self:
        for alias in self.aliases:
            if alias.entity_id != self.entity_id:
                raise ValueError("alias entity_id must match its containing Entity")
        _validate_identifier_subjects(
            self.external_identifiers, IdentifierSubjectType.ENTITY, self.entity_id
        )
        return self


class Security(VersionedModel):
    """An issued instrument or share class, separate from issuer and listing."""

    security_id: UUID
    issuer_entity_id: UUID
    security_type: SecurityType
    display_name: NonEmptyStr
    share_class: NonEmptyStr | None = None
    external_identifiers: tuple[ExternalIdentifier, ...] = ()
    provenance_id: UUID

    @model_validator(mode="after")
    def validate_identifier_subjects(self) -> Self:
        _validate_identifier_subjects(
            self.external_identifiers, IdentifierSubjectType.SECURITY, self.security_id
        )
        return self


class Listing(VersionedModel):
    """A venue-specific, effective-dated symbol for one security."""

    listing_id: UUID
    security_id: UUID
    symbol: NonEmptyStr
    exchange_mic: Mic
    effective_from: TemporalValue | None = None
    effective_to: TemporalValue | None = None
    external_identifiers: tuple[ExternalIdentifier, ...] = ()
    provenance_id: UUID

    @model_validator(mode="after")
    def validate_identifier_subjects(self) -> Self:
        _validate_identifier_subjects(
            self.external_identifiers, IdentifierSubjectType.LISTING, self.listing_id
        )
        return self


class SubjectReference(CanonicalModel):
    """Typed reference used by relationships without conflating graph subjects."""

    subject_type: SubjectType
    subject_id: UUID


class Relationship(VersionedModel):
    """A sourced connection with separate valid, known, and observed time axes."""

    relationship_id: UUID
    relationship_type: Slug
    source: SubjectReference
    target: SubjectReference
    valid_from: TemporalValue | None = None
    valid_to: TemporalValue | None = None
    known_from: TemporalValue | None = None
    known_to: TemporalValue | None = None
    observed_at: AwareDatetime
    confidence: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"))
    source_observation_ids: tuple[UUID, ...] = Field(min_length=1)
    provenance_id: UUID

    @model_validator(mode="after")
    def validate_unique_observations(self) -> Self:
        if len(set(self.source_observation_ids)) != len(self.source_observation_ids):
            raise ValueError("source_observation_ids must be unique")
        return self


def _validate_identifier_subjects(
    identifiers: tuple[ExternalIdentifier, ...],
    expected_type: IdentifierSubjectType,
    expected_id: UUID,
) -> None:
    identifier_ids = set()
    for identifier in identifiers:
        if identifier.subject_type is not expected_type or identifier.subject_id != expected_id:
            raise ValueError("external identifier subject must match its containing record")
        if identifier.external_identifier_id in identifier_ids:
            raise ValueError("external identifier IDs must be unique")
        identifier_ids.add(identifier.external_identifier_id)
