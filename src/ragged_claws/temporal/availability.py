"""Explicit policies for deriving effective availability from source-public evidence."""

from datetime import date, timedelta
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from ragged_claws.models.base import CanonicalModel, NonEmptyStr, Slug, UtcDatetime
from ragged_claws.models.temporal import TemporalPrecision, TemporalValue
from ragged_claws.temporal.normalization import normalize_utc


class AvailabilityPolicyError(ValueError):
    """Raised when a policy would manufacture unavailable temporal precision."""


class AvailabilityStatus(StrEnum):
    """Precision of the effective availability that a policy could establish."""

    EXACT = "exact"
    DATE_ONLY = "date_only"
    UNSUPPORTED_PRECISION = "unsupported_precision"


class AvailabilityPolicy(CanonicalModel):
    """Named, versioned, and inspectable source-availability assumption."""

    policy_id: Slug
    policy_version: NonEmptyStr
    delay: timedelta = Field(default=timedelta(0), ge=timedelta(0))
    rationale: NonEmptyStr
    source_family: Slug | None = None

    @model_validator(mode="after")
    def validate_delay_precision(self) -> Self:
        if self.delay.microseconds != 0:
            raise ValueError("availability delay must use whole-second precision")
        return self


class AvailabilityResult(CanonicalModel):
    """Source-public evidence and the separately derived effective availability."""

    source_public_time: TemporalValue
    policy: AvailabilityPolicy
    status: AvailabilityStatus
    effective_availability_at: UtcDatetime | None = None
    effective_availability_date: date | None = None

    @model_validator(mode="after")
    def validate_representation(self) -> Self:
        has_timestamp = self.effective_availability_at is not None
        has_date = self.effective_availability_date is not None
        expected = {
            AvailabilityStatus.EXACT: (True, False),
            AvailabilityStatus.DATE_ONLY: (False, True),
            AvailabilityStatus.UNSUPPORTED_PRECISION: (False, False),
        }
        if (has_timestamp, has_date) != expected[self.status]:
            raise ValueError("effective availability fields do not match status")

        source = self.source_public_time
        if self.status is AvailabilityStatus.EXACT:
            if source.timestamp is None:
                raise ValueError("exact availability requires exact source-public time")
            expected_timestamp = normalize_utc(source.timestamp) + self.policy.delay
            if self.effective_availability_at != expected_timestamp:
                raise ValueError(
                    "effective timestamp must equal source-public time plus policy delay"
                )
        elif self.status is AvailabilityStatus.DATE_ONLY:
            if source.precision is not TemporalPrecision.DAY or source.partial_date is None:
                raise ValueError("date-only availability requires day-precision source-public time")
            if self.policy.delay != timedelta(0):
                raise ValueError("date-only availability requires a zero-delay policy")
            partial = source.partial_date
            if partial.year is None or partial.month is None or partial.day is None:
                raise ValueError("day precision requires complete date components")
            if self.effective_availability_date != date(
                partial.year, partial.month, partial.day
            ):
                raise ValueError("effective date must preserve the source-public calendar date")
        else:
            if source.timestamp is not None or source.precision is TemporalPrecision.DAY:
                raise ValueError("supported source precision cannot be marked unsupported")
            if self.policy.delay != timedelta(0):
                raise ValueError("coarse availability requires a zero-delay policy")
        return self


def apply_availability_policy(
    source_public_time: TemporalValue,
    policy: AvailabilityPolicy,
) -> AvailabilityResult:
    """Apply only the policy's explicit delay without mutating source-public evidence."""
    if source_public_time.timestamp is not None:
        effective = normalize_utc(source_public_time.timestamp) + policy.delay
        return AvailabilityResult(
            source_public_time=source_public_time,
            policy=policy,
            status=AvailabilityStatus.EXACT,
            effective_availability_at=effective,
        )

    if policy.delay != timedelta(0):
        raise AvailabilityPolicyError(
            "positive availability delays require an exact source-public timestamp"
        )

    partial = source_public_time.partial_date
    if source_public_time.precision is TemporalPrecision.DAY and partial is not None:
        if partial.year is None or partial.month is None or partial.day is None:
            raise AvailabilityPolicyError("day precision requires complete date components")
        return AvailabilityResult(
            source_public_time=source_public_time,
            policy=policy,
            status=AvailabilityStatus.DATE_ONLY,
            effective_availability_date=date(partial.year, partial.month, partial.day),
        )

    return AvailabilityResult(
        source_public_time=source_public_time,
        policy=policy,
        status=AvailabilityStatus.UNSUPPORTED_PRECISION,
    )
