"""Representations consumed and produced by later research logic."""

from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, Field, PositiveInt, model_validator

from ragged_claws.models.base import JsonScalar, NonEmptyStr, Slug, VersionedModel
from ragged_claws.models.temporal import TemporalValue


class FeatureValue(VersionedModel):
    """One source-linked scalar feature; no historical filtering is performed here."""

    feature_value_id: UUID
    name: Slug
    value: JsonScalar
    known_from: TemporalValue | None = None
    source_observation_ids: tuple[UUID, ...] = Field(min_length=1)


class FeatureSnapshot(VersionedModel):
    """Immutable representation of features selected at a stated decision time."""

    feature_snapshot_id: UUID
    event_id: UUID
    snapshot_at: AwareDatetime
    feature_version: NonEmptyStr
    features: tuple[FeatureValue, ...]
    provenance_id: UUID


class OutcomeStatus(StrEnum):
    COMPLETE = "complete"
    RIGHT_CENSORED = "right_censored"
    MISSING_PRICE = "missing_price"
    UNRESOLVED_SECURITY = "unresolved_security"
    TERMINAL_DELISTED = "terminal_delisted"
    EXCLUDED = "excluded"


class PriceAdjustment(StrEnum):
    RAW = "raw"
    SPLIT = "split"
    DIVIDEND = "dividend"
    SPINOFF = "spinoff"
    ALL = "all"
    OTHER = "other"


class OutcomeMethodology(VersionedModel):
    """Versioned conventions and source lineage used to construct an Outcome.

    This value records methodology only; it does not implement calendar or return logic.
    """

    methodology_id: UUID
    methodology_version: NonEmptyStr
    calendar_id: Slug
    calendar_version: NonEmptyStr
    entry_convention: Slug
    exit_convention: Slug
    price_adjustment: PriceAdjustment
    price_source_observation_ids: tuple[UUID, ...] = ()

    @model_validator(mode="after")
    def validate_unique_price_sources(self) -> Self:
        if len(set(self.price_source_observation_ids)) != len(
            self.price_source_observation_ids
        ):
            raise ValueError("price_source_observation_ids must be unique")
        return self


class Outcome(VersionedModel):
    """Forward-result representation; this model performs no return calculation."""

    outcome_id: UUID
    event_id: UUID
    security_id: UUID | None = None
    listing_id: UUID | None = None
    actionable_at: AwareDatetime
    entry_at: AwareDatetime | None = None
    exit_at: AwareDatetime | None = None
    horizon_sessions: PositiveInt
    entry_price: Decimal | None = None
    exit_price: Decimal | None = None
    security_return: Decimal | None = None
    benchmark_listing_id: UUID | None = None
    benchmark_return: Decimal | None = None
    excess_return: Decimal | None = None
    status: OutcomeStatus
    methodology: OutcomeMethodology
    exclusion_reason: NonEmptyStr | None = None
    provenance_id: UUID

    @model_validator(mode="after")
    def validate_status_fields(self) -> Self:
        completion_fields = (
            self.security_return,
            self.benchmark_return,
            self.excess_return,
        )
        if self.status is OutcomeStatus.COMPLETE:
            if self.security_id is None or self.listing_id is None:
                raise ValueError("complete outcomes require resolved security and listing IDs")
            required_complete_fields = (
                self.entry_at,
                self.exit_at,
                self.entry_price,
                self.exit_price,
                self.benchmark_listing_id,
                *completion_fields,
            )
            if any(value is None for value in required_complete_fields):
                raise ValueError("complete outcomes require entry, exit, and return fields")
        elif any(value is not None for value in completion_fields):
            raise ValueError("incomplete outcomes cannot contain completed return fields")

        if self.listing_id is not None and self.security_id is None:
            raise ValueError("listing_id requires security_id")
        if (self.entry_at is None) != (self.entry_price is None):
            raise ValueError("entry_at and entry_price must be provided together")
        if (self.exit_at is None) != (self.exit_price is None):
            raise ValueError("exit_at and exit_price must be provided together")
        if (
            self.entry_price is not None or self.exit_price is not None
        ) and not self.methodology.price_source_observation_ids:
            raise ValueError("observed price state requires price source observations")
        if self.status is not OutcomeStatus.COMPLETE and (
            self.exit_at is not None or self.exit_price is not None
        ):
            raise ValueError("only complete outcomes may contain final exit fields")

        if self.status is OutcomeStatus.RIGHT_CENSORED:
            if self.security_id is None or self.listing_id is None:
                raise ValueError(
                    "right-censored outcomes require resolved security and listing IDs"
                )
            if self.entry_at is None or self.entry_price is None:
                raise ValueError("right-censored outcomes require valid entry-side state")
        if self.status is OutcomeStatus.UNRESOLVED_SECURITY:
            unavailable_state = (
                self.security_id,
                self.listing_id,
                self.entry_at,
                self.entry_price,
                self.exit_at,
                self.exit_price,
            )
            if any(value is not None for value in unavailable_state):
                raise ValueError(
                    "unresolved-security outcomes cannot fabricate resolved price state"
                )

        if self.status is OutcomeStatus.EXCLUDED and self.exclusion_reason is None:
            raise ValueError("excluded outcomes require exclusion_reason")
        if self.status is not OutcomeStatus.EXCLUDED and self.exclusion_reason is not None:
            raise ValueError("exclusion_reason is only valid for excluded outcomes")
        return self
