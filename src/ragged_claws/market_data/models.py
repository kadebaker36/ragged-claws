"""Provider-neutral daily-bar request and normalized response values."""

from datetime import date
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from ragged_claws.models import PriceAdjustment, SourceObservation
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
    symbols: tuple[HistoricalSymbol, ...] = Field(min_length=1)
    adjustment: PriceAdjustment
    feed: Slug

    @model_validator(mode="after")
    def validate_coverage(self) -> Self:
        if self.end < self.start:
            raise ValueError("request end precedes start")
        ordered = sorted(self.symbols, key=lambda value: value.valid_from)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if previous.valid_to is None or current.valid_from < previous.valid_to:
                raise ValueError("historical symbol intervals must not overlap")
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
