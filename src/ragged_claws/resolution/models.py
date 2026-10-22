"""Typed requests and auditable outcomes for conservative identity resolution."""

from datetime import date
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from ragged_claws.models import ExternalIdentifierType, IdentifierSubjectType, TemporalValue
from ragged_claws.models.base import CanonicalModel, NonEmptyStr, UtcDatetime


class ResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"
    CONFLICT = "conflict"


class ResolutionMethod(StrEnum):
    EXACT_IDENTIFIER = "exact_identifier"
    HISTORICAL_LISTING = "historical_listing"
    NONE = "none"


class ResolutionReason(StrEnum):
    EXACT_TYPED_IDENTIFIER = "exact_typed_identifier"
    UNIQUE_VALID_LISTING = "unique_valid_listing"
    NO_MATCH = "no_match"
    MULTIPLE_MATCHES = "multiple_matches"
    IDENTIFIER_CONFLICT = "identifier_conflict"
    COARSE_VALIDITY = "coarse_validity"
    NOT_KNOWN_AT_TIME = "not_known_at_time"


class ResolutionConfidence(StrEnum):
    """Deterministic evidence class, not an invented probability."""

    EXACT = "exact"


class IdentifierResolutionRequest(CanonicalModel):
    subject_type: IdentifierSubjectType
    identifier_type: ExternalIdentifierType
    value: NonEmptyStr
    market_scope: NonEmptyStr | None = None
    known_at: UtcDatetime | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        allowed_subjects: dict[ExternalIdentifierType, set[IdentifierSubjectType]] = {
            ExternalIdentifierType.SEC_CIK: {IdentifierSubjectType.ENTITY},
            ExternalIdentifierType.LEI: {IdentifierSubjectType.ENTITY},
            ExternalIdentifierType.FIGI_SHARE_CLASS: {IdentifierSubjectType.SECURITY},
            ExternalIdentifierType.FIGI_COMPOSITE: {IdentifierSubjectType.SECURITY},
            ExternalIdentifierType.FIGI_INSTRUMENT: {IdentifierSubjectType.LISTING},
            ExternalIdentifierType.ISIN: {IdentifierSubjectType.SECURITY},
            ExternalIdentifierType.CUSIP: {IdentifierSubjectType.SECURITY},
            ExternalIdentifierType.SEDOL: {
                IdentifierSubjectType.SECURITY,
                IdentifierSubjectType.LISTING,
            },
            ExternalIdentifierType.OTHER: set(IdentifierSubjectType),
        }
        if self.identifier_type is ExternalIdentifierType.OTHER:
            raise ValueError("OTHER identifiers require a source-specific resolver")
        if self.subject_type not in allowed_subjects[self.identifier_type]:
            raise ValueError(
                f"{self.identifier_type.value} cannot resolve {self.subject_type.value}"
            )
        if self.identifier_type is ExternalIdentifierType.FIGI_COMPOSITE:
            if self.market_scope is None:
                raise ValueError("composite FIGI requests require market_scope")
        elif self.market_scope is not None:
            raise ValueError("market_scope is only valid for composite FIGI requests")
        return self


class HistoricalListingRequest(CanonicalModel):
    security_id: UUID
    exchange_mic: str = Field(pattern=r"^[A-Z0-9]{4}$")
    symbol: NonEmptyStr
    as_of: TemporalValue
    known_at: UtcDatetime | None = None


class ResolutionResult(CanonicalModel):
    status: ResolutionStatus
    subject_type: IdentifierSubjectType
    subject_id: UUID | None = None
    method: ResolutionMethod
    reason: ResolutionReason
    confidence: ResolutionConfidence | None = None
    supporting_external_identifier_ids: tuple[UUID, ...] = ()
    source_observation_ids: tuple[UUID, ...] = ()
    provenance_ids: tuple[UUID, ...] = ()
    candidate_ids: tuple[UUID, ...] = ()
    valid_from: TemporalValue | None = None
    valid_to: TemporalValue | None = None
    known_from: TemporalValue | None = None
    observed_at: UtcDatetime | None = None

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.status is ResolutionStatus.RESOLVED:
            if self.subject_id is None or self.confidence is not ResolutionConfidence.EXACT:
                raise ValueError("resolved results require one subject and exact confidence")
            if self.candidate_ids:
                raise ValueError("resolved results cannot retain ambiguous candidates")
        else:
            if self.subject_id is not None or self.confidence is not None:
                raise ValueError("non-resolved results cannot claim a subject or confidence")
        if (
            self.status in {ResolutionStatus.AMBIGUOUS, ResolutionStatus.CONFLICT}
            and len(self.candidate_ids) < 2
        ):
            raise ValueError("ambiguous/conflict results require at least two candidates")
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError("candidate IDs must be unique")
        for field_name in (
            "supporting_external_identifier_ids",
            "source_observation_ids",
            "provenance_ids",
        ):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must be unique")
        return self


def day_value(value: date) -> TemporalValue:
    """Construct an exact day-precision request without inventing a timestamp."""
    from ragged_claws.models import PartialDate, TemporalPrecision

    raw = value.isoformat()
    return TemporalValue(
        raw_value=raw,
        precision=TemporalPrecision.DAY,
        partial_date=PartialDate(
            raw_value=raw,
            precision=TemporalPrecision.DAY,
            year=value.year,
            month=value.month,
            day=value.day,
        ),
    )
