"""UTC normalization and explicit effective-availability policy tests."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ragged_claws.models import PartialDate, TemporalPrecision, TemporalValue
from ragged_claws.temporal import (
    AvailabilityPolicy,
    AvailabilityPolicyError,
    AvailabilityStatus,
    apply_availability_policy,
    normalize_utc,
)


def exact_public_time(raw_value: str) -> TemporalValue:
    return TemporalValue(
        raw_value=raw_value,
        precision=TemporalPrecision.SECOND,
        timestamp=datetime.fromisoformat(raw_value),
        source_timezone="America/New_York",
    )


def policy(delay: timedelta = timedelta(0)) -> AvailabilityPolicy:
    return AvailabilityPolicy(
        policy_id="documented_source_availability",
        policy_version="1.0.0",
        delay=delay,
        rationale="Synthetic policy used to prove explicit availability semantics.",
        source_family="public_disclosure",
    )


def test_exact_timestamp_normalizes_to_utc_while_preserving_raw_evidence() -> None:
    source = exact_public_time("2024-05-06T08:15:00-04:00")

    assert source.timestamp == datetime(2024, 5, 6, 12, 15, tzinfo=UTC)
    assert source.raw_value == "2024-05-06T08:15:00-04:00"
    assert source.source_timezone == "America/New_York"
    assert '"timestamp":"2024-05-06T12:15:00Z"' in source.model_dump_json()


def test_timezone_equivalent_inputs_normalize_to_the_same_instant() -> None:
    eastern = normalize_utc(datetime.fromisoformat("2024-05-06T08:15:00-04:00"))
    central_europe = normalize_utc(datetime.fromisoformat("2024-05-06T14:15:00+02:00"))

    assert eastern == central_europe == datetime(2024, 5, 6, 12, 15, tzinfo=UTC)


def test_naive_exact_timestamps_fail() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_utc(datetime(2024, 5, 6, 12, 15))

    with pytest.raises(ValidationError):
        TemporalValue(
            raw_value="2024-05-06T12:15:00",
            precision=TemporalPrecision.SECOND,
            timestamp=datetime(2024, 5, 6, 12, 15),
        )


def test_zero_delay_preserves_source_public_time_separately() -> None:
    source = exact_public_time("2024-05-06T08:15:00-04:00")
    result = apply_availability_policy(source, policy())

    assert result.source_public_time == source
    assert result.status is AvailabilityStatus.EXACT
    assert result.effective_availability_at == source.timestamp
    assert result.policy.policy_id == "documented_source_availability"
    assert result.policy.policy_version == "1.0.0"


def test_positive_delay_is_explicit_and_roundtrips_with_policy_metadata() -> None:
    source = exact_public_time("2024-05-06T08:15:00-04:00")
    result = apply_availability_policy(source, policy(timedelta(minutes=10)))
    restored = type(result).model_validate_json(result.model_dump_json())

    assert restored == result
    assert restored.source_public_time.raw_value == source.raw_value
    assert restored.effective_availability_at == datetime(2024, 5, 6, 12, 25, tzinfo=UTC)
    assert restored.policy.delay == timedelta(minutes=10)


def test_date_only_remains_coarse_and_accepts_only_zero_delay() -> None:
    source = TemporalValue(
        raw_value="2024-05-06",
        precision=TemporalPrecision.DAY,
        partial_date=PartialDate(
            raw_value="2024-05-06",
            precision=TemporalPrecision.DAY,
            year=2024,
            month=5,
            day=6,
        ),
    )
    result = apply_availability_policy(source, policy())

    assert result.status is AvailabilityStatus.DATE_ONLY
    assert result.effective_availability_at is None
    assert result.effective_availability_date is not None

    with pytest.raises(AvailabilityPolicyError, match="require an exact"):
        apply_availability_policy(source, policy(timedelta(seconds=1)))


@pytest.mark.parametrize(
    ("raw_value", "precision", "year", "month"),
    [
        ("unknown", TemporalPrecision.UNKNOWN, None, None),
        ("2024", TemporalPrecision.YEAR, 2024, None),
        ("2024-05", TemporalPrecision.MONTH, 2024, 5),
    ],
)
def test_partial_public_dates_fail_closed_as_unsupported_availability(
    raw_value: str,
    precision: TemporalPrecision,
    year: int | None,
    month: int | None,
) -> None:
    source = TemporalValue(
        raw_value=raw_value,
        precision=precision,
        partial_date=PartialDate(
            raw_value=raw_value,
            precision=precision,
            year=year,
            month=month,
        ),
    )

    result = apply_availability_policy(source, policy())

    assert result.status is AvailabilityStatus.UNSUPPORTED_PRECISION
    assert result.effective_availability_at is None
    assert result.effective_availability_date is None


def test_negative_policy_delay_is_rejected() -> None:
    with pytest.raises(ValidationError):
        policy(timedelta(seconds=-1))

    with pytest.raises(ValidationError, match="whole-second"):
        policy(timedelta(microseconds=1))
