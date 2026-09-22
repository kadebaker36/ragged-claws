"""Reviewed-calendar tests for the conservative V0 daily-bar convention."""

from datetime import UTC, datetime, timedelta

import pytest

from ragged_claws.models import PartialDate, TemporalPrecision, TemporalValue
from ragged_claws.temporal import (
    ActionabilityStatus,
    ActionableTimeError,
    ActionableTimeResolver,
    AvailabilityPolicy,
    apply_availability_policy,
)

ZERO_DELAY = AvailabilityPolicy(
    policy_id="zero_delay",
    policy_version="1.0.0",
    delay=timedelta(0),
    rationale="Use source-public time without an added dissemination delay.",
)


def resolve_exact(raw_value: str) -> datetime | None:
    source = TemporalValue(
        raw_value=raw_value,
        precision=TemporalPrecision.SECOND,
        timestamp=datetime.fromisoformat(raw_value),
        source_timezone="America/New_York",
    )
    result = ActionableTimeResolver().resolve(apply_availability_policy(source, ZERO_DELAY))
    return result.actionable_at


@pytest.mark.parametrize(
    ("source_time", "expected_open"),
    [
        ("2024-05-06T08:00:00-04:00", datetime(2024, 5, 6, 13, 30, tzinfo=UTC)),
        ("2024-05-06T09:29:59-04:00", datetime(2024, 5, 6, 13, 30, tzinfo=UTC)),
        ("2024-05-06T09:30:00-04:00", datetime(2024, 5, 7, 13, 30, tzinfo=UTC)),
        ("2024-05-06T09:30:01-04:00", datetime(2024, 5, 7, 13, 30, tzinfo=UTC)),
        ("2024-05-06T12:00:00-04:00", datetime(2024, 5, 7, 13, 30, tzinfo=UTC)),
        ("2024-05-06T18:00:00-04:00", datetime(2024, 5, 7, 13, 30, tzinfo=UTC)),
        ("2024-05-03T18:00:00-04:00", datetime(2024, 5, 6, 13, 30, tzinfo=UTC)),
        ("2024-05-04T12:00:00-04:00", datetime(2024, 5, 6, 13, 30, tzinfo=UTC)),
        ("2024-07-04T08:00:00-04:00", datetime(2024, 7, 5, 13, 30, tzinfo=UTC)),
        ("2024-07-03T10:00:00-04:00", datetime(2024, 7, 5, 13, 30, tzinfo=UTC)),
        ("2024-11-29T13:01:00-05:00", datetime(2024, 12, 2, 14, 30, tzinfo=UTC)),
        ("2024-03-08T09:29:59-05:00", datetime(2024, 3, 8, 14, 30, tzinfo=UTC)),
        ("2024-03-11T09:29:59-04:00", datetime(2024, 3, 11, 13, 30, tzinfo=UTC)),
    ],
)
def test_precise_availability_uses_reviewed_regular_sessions(
    source_time: str,
    expected_open: datetime,
) -> None:
    assert resolve_exact(source_time) == expected_open


def test_timezone_equivalent_source_offsets_produce_same_actionable_open() -> None:
    eastern = resolve_exact("2024-05-06T08:00:00-04:00")
    central_europe = resolve_exact("2024-05-06T14:00:00+02:00")

    assert eastern == central_europe == datetime(2024, 5, 6, 13, 30, tzinfo=UTC)


def test_effective_availability_delay_controls_actionability_not_source_public_time() -> None:
    source = TemporalValue(
        raw_value="2024-05-06T09:25:00-04:00",
        precision=TemporalPrecision.SECOND,
        timestamp=datetime.fromisoformat("2024-05-06T09:25:00-04:00"),
    )
    delayed_policy = AvailabilityPolicy(
        policy_id="documented_delay",
        policy_version="1.0.0",
        delay=timedelta(minutes=10),
        rationale="Synthetic dissemination delay crossing the regular-session open.",
    )

    result = ActionableTimeResolver().resolve(
        apply_availability_policy(source, delayed_policy)
    )

    assert result.availability.source_public_time.timestamp == datetime(
        2024, 5, 6, 13, 25, tzinfo=UTC
    )
    assert result.availability.effective_availability_at == datetime(
        2024, 5, 6, 13, 35, tzinfo=UTC
    )
    assert result.actionable_at == datetime(2024, 5, 7, 13, 30, tzinfo=UTC)


def test_date_only_disclosure_uses_next_session_after_calendar_date() -> None:
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
    result = ActionableTimeResolver().resolve(apply_availability_policy(source, ZERO_DELAY))
    restored = type(result).model_validate_json(result.model_dump_json())

    assert restored == result
    assert result.actionable_at == datetime(2024, 5, 7, 13, 30, tzinfo=UTC)
    assert result.availability.source_public_time == source
    assert result.convention_id == "v0_daily_bar_open"
    assert result.convention_version == "1.0.0"
    assert result.calendar_name == "XNYS"


def test_partial_date_is_explicitly_non_actionable() -> None:
    source = TemporalValue(
        raw_value="1856-00-00",
        precision=TemporalPrecision.YEAR,
        partial_date=PartialDate(
            raw_value="1856-00-00",
            precision=TemporalPrecision.YEAR,
            year=1856,
        ),
    )
    result = ActionableTimeResolver().resolve(apply_availability_policy(source, ZERO_DELAY))

    assert result.status is ActionabilityStatus.UNSUPPORTED_PRECISION
    assert result.actionable_at is None


def test_calendar_lookup_failure_does_not_invent_actionability() -> None:
    source = TemporalValue(
        raw_value="2024-05-06T08:00:00-04:00",
        precision=TemporalPrecision.SECOND,
        timestamp=datetime.fromisoformat("2024-05-06T08:00:00-04:00"),
    )
    availability = apply_availability_policy(source, ZERO_DELAY)

    with pytest.raises(ActionableTimeError, match="could not resolve"):
        ActionableTimeResolver(calendar_name="NOT_A_CALENDAR").resolve(availability)
