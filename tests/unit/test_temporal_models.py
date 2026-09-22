"""Temporal precision and corruption-guard tests."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ragged_claws.models import PartialDate, TemporalPrecision, TemporalValue
from tests.model_helpers import partial_temporal


def test_partial_legacy_date_roundtrips_without_fabricated_components() -> None:
    value = partial_temporal("1856-00-00", TemporalPrecision.YEAR, year=1856)

    restored = TemporalValue.model_validate_json(value.model_dump_json())

    assert restored == value
    assert restored.raw_value == "1856-00-00"
    assert restored.partial_date is not None
    assert restored.partial_date.year == 1856
    assert restored.partial_date.month is None
    assert restored.partial_date.day is None


def test_exact_timestamp_preserves_offset_and_raw_value() -> None:
    timestamp = datetime(2024, 5, 6, 16, 42, 15, tzinfo=UTC)
    value = TemporalValue(
        raw_value="2024-05-06T16:42:15Z",
        precision=TemporalPrecision.SECOND,
        timestamp=timestamp,
        source_timezone="UTC",
    )

    restored = TemporalValue.model_validate_json(value.model_dump_json())

    assert restored.timestamp == timestamp
    assert restored.raw_value == "2024-05-06T16:42:15Z"


@pytest.mark.parametrize(
    ("raw_value", "precision", "timestamp"),
    [
        (
            "2024-05-06T12:42:15-04:00",
            TemporalPrecision.SECOND,
            datetime(2024, 5, 6, 16, 42, 15, tzinfo=UTC),
        ),
        (
            "2024-05-06T18:42:15+02:00",
            TemporalPrecision.SECOND,
            datetime(2024, 5, 6, 16, 42, 15, tzinfo=UTC),
        ),
        (
            "2024-05-06T16:42:15Z",
            TemporalPrecision.SECOND,
            datetime(2024, 5, 6, 16, 42, 15, tzinfo=UTC),
        ),
        (
            "2024-05-06T12:42-04:00",
            TemporalPrecision.MINUTE,
            datetime(2024, 5, 6, 16, 42, tzinfo=UTC),
        ),
    ],
)
def test_iso_timestamp_raw_value_must_describe_canonical_instant(
    raw_value: str,
    precision: TemporalPrecision,
    timestamp: datetime,
) -> None:
    value = TemporalValue(
        raw_value=raw_value,
        precision=precision,
        timestamp=timestamp,
    )

    assert value.timestamp == timestamp


def test_iso_timestamp_raw_value_cannot_contradict_canonical_instant() -> None:
    with pytest.raises(ValidationError, match="conflicts with the ISO-like raw value"):
        TemporalValue(
            raw_value="2024-05-06T12:42:15-04:00",
            precision=TemporalPrecision.SECOND,
            timestamp=datetime(2024, 5, 6, 17, 42, 15, tzinfo=UTC),
        )


def test_non_iso_timestamp_raw_value_remains_representable() -> None:
    timestamp = datetime(2024, 5, 6, 16, 42, 15, tzinfo=UTC)

    value = TemporalValue(
        raw_value="06-MAY-2024 12:42:15 EDT",
        precision=TemporalPrecision.SECOND,
        timestamp=timestamp,
    )

    assert value.raw_value == "06-MAY-2024 12:42:15 EDT"
    assert value.timestamp == timestamp


@pytest.mark.parametrize(
    ("raw_value", "precision", "year", "month", "day"),
    [
        ("2024-13-01", TemporalPrecision.DAY, 2024, 12, 1),
        ("2024-02-30", TemporalPrecision.DAY, 2024, 2, 30),
        ("2024-05", TemporalPrecision.YEAR, 2024, None, None),
        ("1856-00-00", TemporalPrecision.DAY, 1856, None, None),
    ],
)
def test_invalid_partial_date_combinations_fail(
    raw_value: str,
    precision: TemporalPrecision,
    year: int | None,
    month: int | None,
    day: int | None,
) -> None:
    with pytest.raises((ValidationError, ValueError)):
        PartialDate(
            raw_value=raw_value,
            precision=precision,
            year=year,
            month=month,
            day=day,
        )


def test_timestamp_requires_timezone_and_declared_precision() -> None:
    with pytest.raises(ValidationError):
        TemporalValue(
            raw_value="2024-05-06T16:42:15",
            precision=TemporalPrecision.SECOND,
            timestamp=datetime(2024, 5, 6, 16, 42, 15),
        )

    with pytest.raises(ValidationError):
        TemporalValue(
            raw_value="2024-05-06T16:42:15Z",
            precision=TemporalPrecision.MINUTE,
            timestamp=datetime(2024, 5, 6, 16, 42, 15, tzinfo=UTC),
        )
