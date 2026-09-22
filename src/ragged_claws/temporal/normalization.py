"""Timezone normalization that never guesses a timezone for naive values."""

from datetime import UTC, datetime


def normalize_utc(value: datetime) -> datetime:
    """Return an aware UTC datetime, rejecting naive or invalid timezone values."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("exact timestamps must be timezone-aware")
    return value.astimezone(UTC)
