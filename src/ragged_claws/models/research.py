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
    price_adjustment: PriceAdjustment
    price_source_observation_ids: tuple[UUID, ...] = ()
    exclusion_reason: NonEmptyStr | None = None
    provenance_id: UUID

    @model_validator(mode="after")
    def validate_status_fields(self) -> Self:
        result_fields = (
            self.entry_at,
            self.exit_at,
            self.entry_price,
            self.exit_price,
            self.security_return,
            self.benchmark_listing_id,
            self.benchmark_return,
            self.excess_return,
        )
        if self.status is OutcomeStatus.COMPLETE:
            if self.security_id is None or self.listing_id is None:
                raise ValueError("complete outcomes require resolved security and listing IDs")
            if any(value is None for value in result_fields):
                raise ValueError("complete outcomes require entry, exit, and return fields")
            if not self.price_source_observation_ids:
                raise ValueError("complete outcomes require price source observations")
        elif any(value is not None for value in result_fields):
            raise ValueError("incomplete outcomes cannot contain completed result fields")

        if self.status is OutcomeStatus.EXCLUDED and self.exclusion_reason is None:
            raise ValueError("excluded outcomes require exclusion_reason")
        if self.status is not OutcomeStatus.EXCLUDED and self.exclusion_reason is not None:
            raise ValueError("exclusion_reason is only valid for excluded outcomes")
        if len(set(self.price_source_observation_ids)) != len(
            self.price_source_observation_ids
        ):
            raise ValueError("price_source_observation_ids must be unique")
        return self
