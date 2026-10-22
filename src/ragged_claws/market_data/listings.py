"""Conservative daily-bar interpretation of canonical listing validity."""

from datetime import date

from ragged_claws.models import Listing, TemporalPrecision, TemporalValue


def listing_bounds(listing: Listing) -> tuple[date | None, date | None]:
    """Return half-open day bounds; never invent precision for daily bars."""
    start = _day_boundary(listing.effective_from)
    end = _day_boundary(listing.effective_to)
    if start is not None and end is not None and end <= start:
        raise ValueError("listing interval must have positive duration")
    return start, end


def _day_boundary(value: TemporalValue | None) -> date | None:
    if value is None:
        return None
    partial = value.partial_date
    if (
        value.precision is not TemporalPrecision.DAY
        or partial is None or partial.year is None
        or partial.month is None or partial.day is None
    ):
        raise ValueError("daily listing boundaries require day precision")
    return date(partial.year, partial.month, partial.day)
