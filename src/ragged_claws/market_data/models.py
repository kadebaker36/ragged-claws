"""Provider-neutral daily-bar request and normalized response values."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from ragged_claws.market_data.listings import listing_bounds
from ragged_claws.models import Listing, PriceAdjustment, SourceObservation
from ragged_claws.models.base import CanonicalModel, NonEmptyStr, Slug


class HistoricalSymbol(CanonicalModel):
    """A provider symbol and the canonical historical interval it represents."""

    symbol: NonEmptyStr
    valid_from: date
    valid_to: date | None = None
    provider_asof: date

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("historical symbol interval ends before it begins")
        if self.provider_asof < self.valid_from or (
            self.valid_to is not None and self.provider_asof >= self.valid_to
        ):
            raise ValueError("provider_asof must fall inside the historical symbol interval")
        return self


class DailyBarRequest(CanonicalModel):
    """Explicit historical coverage request anchored to canonical identities."""

    security_id: UUID
    listing_id: UUID
    start: date
    end: date
    symbols: tuple[HistoricalSymbol, ...] = Field(min_length=1, max_length=1)
    adjustment: PriceAdjustment
    feed: Slug

    @classmethod
    def from_listing(
        cls, listing: Listing, *, start: date, end: date, provider_asof: date,
        adjustment: PriceAdjustment, feed: str,
    ) -> Self:
        """Clip one request to one canonical listing; fetch renames separately."""
        lower, upper = listing_bounds(listing)
        return cls(
            security_id=listing.security_id,
            listing_id=listing.listing_id,
            start=max(start, lower) if lower is not None else start,
            end=min(end, upper - timedelta(days=1)) if upper is not None else end,
            symbols=(HistoricalSymbol(
                symbol=listing.symbol, valid_from=lower or start, valid_to=upper,
                provider_asof=provider_asof,
            ),),
            adjustment=adjustment, feed=feed,
        )

    @model_validator(mode="after")
    def validate_coverage(self) -> Self:
        if self.end < self.start:
            raise ValueError("request end precedes start")
        segment = self.symbols[0]
        if self.start < segment.valid_from or (
            segment.valid_to is not None and self.end >= segment.valid_to
        ):
            raise ValueError("request must stay inside its canonical listing segment")
        return self


class DailyBar(CanonicalModel):
    """One normalized regular-session bar with exact prices and source lineage."""

    security_id: UUID
    listing_id: UUID
    session_date: date
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: int | None = Field(default=None, ge=0)
    provider_namespace: Slug
    source_observation_id: UUID
    adjustment: PriceAdjustment
    feed: Slug

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("bar high is below another price")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("bar low is above another price")
        return self


class MarketDataBatch(CanonicalModel):
    """Normalized bars plus the page-level observations that support them."""

    bars: tuple[DailyBar, ...]
    observations: tuple[SourceObservation, ...]
    capture_ids: tuple[UUID, ...]
