"""Calendar-backed V0 conversion from effective availability to market actionability."""

from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from importlib.metadata import version
from typing import Protocol, cast

import exchange_calendars as xcals  # type: ignore[import-untyped]
from pydantic import model_validator

from ragged_claws.models.base import CanonicalModel, NonEmptyStr, Slug, UtcDatetime
from ragged_claws.temporal.availability import AvailabilityResult, AvailabilityStatus
from ragged_claws.temporal.normalization import normalize_utc


class ActionableTimeError(RuntimeError):
    """Raised when a reviewed calendar cannot establish an actionable session."""


class ActionabilityStatus(StrEnum):
    ACTIONABLE = "actionable"
    UNSUPPORTED_PRECISION = "unsupported_precision"


class ActionabilityResult(CanonicalModel):
    """Auditable result of applying the versioned daily-bar convention."""

    availability: AvailabilityResult
    status: ActionabilityStatus
    actionable_at: UtcDatetime | None = None
    session_date: date | None = None
    calendar_name: NonEmptyStr
    calendar_version: NonEmptyStr
    convention_id: Slug
    convention_version: NonEmptyStr

    @model_validator(mode="after")
    def validate_representation(self) -> "ActionabilityResult":
        actual_presence = (
            self.actionable_at is not None,
            self.session_date is not None,
        )
        expected_presence = (
            (True, True)
            if self.status is ActionabilityStatus.ACTIONABLE
            else (False, False)
        )
        if actual_presence != expected_presence:
            raise ValueError("actionable fields do not match actionability status")
        return self


class _PandasTimestamp(Protocol):
    def to_pydatetime(self) -> datetime: ...


class ActionableTimeResolver:
    """Resolve the conservative V0 entry time from effective availability."""

    def __init__(
        self,
        calendar_name: str = "XNYS",
        *,
        convention_id: str = "v0_daily_bar_open",
        convention_version: str = "1.0.0",
    ) -> None:
        self.calendar_name = calendar_name
        self.convention_id = convention_id
        self.convention_version = convention_version
        self.calendar_version = version("exchange-calendars")

    def resolve(self, availability: AvailabilityResult) -> ActionabilityResult:
        """Return an explicit non-actionable result for unsupported coarse precision."""
        if availability.status is AvailabilityStatus.UNSUPPORTED_PRECISION:
            return ActionabilityResult(
                availability=availability,
                status=ActionabilityStatus.UNSUPPORTED_PRECISION,
                calendar_name=self.calendar_name,
                calendar_version=self.calendar_version,
                convention_id=self.convention_id,
                convention_version=self.convention_version,
            )

        probe_date = self._probe_date(availability)
        try:
            calendar = xcals.get_calendar(
                self.calendar_name,
                start=probe_date - timedelta(days=7),
                end=probe_date + timedelta(days=31),
            )
            if availability.status is AvailabilityStatus.DATE_ONLY:
                session = calendar.date_to_session(
                    probe_date + timedelta(days=1), direction="next"
                )
            else:
                effective = availability.effective_availability_at
                if effective is None:
                    raise ActionableTimeError("exact availability is missing its timestamp")
                local_date = normalize_utc(effective).astimezone(calendar.tz).date()
                if calendar.is_session(local_date):
                    session = calendar.date_to_session(local_date)
                    session_open = self._as_utc(calendar.session_open(session))
                    if normalize_utc(effective) >= session_open:
                        session = calendar.next_session(session)
                else:
                    session = calendar.date_to_session(local_date, direction="next")

            actionable_at = self._as_utc(calendar.session_open(session))
            session_date = actionable_at.astimezone(calendar.tz).date()
        except ActionableTimeError:
            raise
        except Exception as exc:
            raise ActionableTimeError(
                f"calendar {self.calendar_name!r} could not resolve actionability"
            ) from exc

        return ActionabilityResult(
            availability=availability,
            status=ActionabilityStatus.ACTIONABLE,
            actionable_at=actionable_at,
            session_date=session_date,
            calendar_name=self.calendar_name,
            calendar_version=self.calendar_version,
            convention_id=self.convention_id,
            convention_version=self.convention_version,
        )

    @staticmethod
    def _probe_date(availability: AvailabilityResult) -> date:
        if availability.effective_availability_date is not None:
            return availability.effective_availability_date
        if availability.effective_availability_at is not None:
            return normalize_utc(availability.effective_availability_at).date()
        raise ActionableTimeError("effective availability has no actionable precision")

    @staticmethod
    def _as_utc(value: object) -> datetime:
        timestamp = cast(_PandasTimestamp, value).to_pydatetime()
        return normalize_utc(timestamp).astimezone(UTC)
