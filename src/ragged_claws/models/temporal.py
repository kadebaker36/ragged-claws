"""Temporal values that preserve source precision without manufacturing dates."""

import re
from datetime import date, datetime
from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, Field, model_validator

from ragged_claws.models.base import CanonicalModel, NonEmptyStr


class TemporalPrecision(StrEnum):
    """Precision actually supported by the source value."""

    UNKNOWN = "unknown"
    YEAR = "year"
    MONTH = "month"
    DAY = "day"
    MINUTE = "minute"
    SECOND = "second"


class PartialDate(CanonicalModel):
    """A date-like source value with only its defensible components populated."""

    raw_value: NonEmptyStr
    precision: TemporalPrecision
    year: int | None = Field(default=None, ge=1, le=9999)
    month: int | None = Field(default=None, ge=1, le=12)
    day: int | None = Field(default=None, ge=1, le=31)

    @model_validator(mode="after")
    def validate_components(self) -> Self:
        expected_presence = {
            TemporalPrecision.UNKNOWN: (False, False, False),
            TemporalPrecision.YEAR: (True, False, False),
            TemporalPrecision.MONTH: (True, True, False),
            TemporalPrecision.DAY: (True, True, True),
        }
        if self.precision not in expected_presence:
            raise ValueError("partial dates only support unknown, year, month, or day precision")

        actual_presence = (self.year is not None, self.month is not None, self.day is not None)
        if actual_presence != expected_presence[self.precision]:
            raise ValueError(f"components do not match {self.precision.value} precision")

        if self.precision is TemporalPrecision.DAY:
            if self.year is None or self.month is None or self.day is None:
                raise ValueError("day precision requires year, month, and day")
            date(self.year, self.month, self.day)

        self._validate_iso_like_raw_value()
        return self

    def _validate_iso_like_raw_value(self) -> None:
        match = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", self.raw_value)
        if match is None:
            return

        raw_year = int(match.group(1))
        raw_month = int(match.group(2)) if match.group(2) is not None else None
        raw_day = int(match.group(3)) if match.group(3) is not None else None
        normalized_month = raw_month or None
        normalized_day = raw_day or None
        if normalized_day is not None:
            raw_precision = TemporalPrecision.DAY
        elif normalized_month is not None:
            raw_precision = TemporalPrecision.MONTH
        else:
            raw_precision = TemporalPrecision.YEAR

        if self.precision is not raw_precision:
            raise ValueError("declared precision conflicts with the ISO-like raw value")
        if (self.year, self.month, self.day) != (raw_year, normalized_month, normalized_day):
            raise ValueError("parsed components conflict with the ISO-like raw value")


class TemporalValue(CanonicalModel):
    """A raw temporal value represented as a partial date or aware timestamp."""

    raw_value: NonEmptyStr
    precision: TemporalPrecision
    partial_date: PartialDate | None = None
    timestamp: AwareDatetime | None = None
    source_timezone: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_representation(self) -> Self:
        date_precisions = {
            TemporalPrecision.UNKNOWN,
            TemporalPrecision.YEAR,
            TemporalPrecision.MONTH,
            TemporalPrecision.DAY,
        }
        timestamp_precisions = {TemporalPrecision.MINUTE, TemporalPrecision.SECOND}

        if self.precision in date_precisions:
            if self.partial_date is None or self.timestamp is not None:
                raise ValueError("date precision requires partial_date and forbids timestamp")
            if self.partial_date.precision is not self.precision:
                raise ValueError("partial_date precision must match temporal precision")
            if self.partial_date.raw_value != self.raw_value:
                raise ValueError("partial_date raw value must match temporal raw value")
            if self.source_timezone is not None:
                raise ValueError("date-only values cannot claim a source timezone")
            return self

        if self.precision in timestamp_precisions:
            if self.timestamp is None or self.partial_date is not None:
                raise ValueError("timestamp precision requires timestamp and forbids partial_date")
            timestamp: datetime = self.timestamp
            if timestamp.microsecond != 0:
                raise ValueError("sub-second precision is not represented by this model")
            if self.precision is TemporalPrecision.MINUTE and timestamp.second != 0:
                raise ValueError("minute precision cannot contain non-zero seconds")
            return self

        raise ValueError(f"unsupported temporal precision: {self.precision}")
