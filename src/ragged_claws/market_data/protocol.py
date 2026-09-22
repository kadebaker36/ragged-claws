"""Small provider boundary for historical regular-session daily bars."""

from datetime import datetime
from typing import Protocol

from ragged_claws.market_data.models import DailyBarRequest, MarketDataBatch


class HistoricalDailyBarProvider(Protocol):
    """Retrieve normalized bars without exposing provider response objects."""

    def fetch(self, request: DailyBarRequest, *, retrieved_at: datetime) -> MarketDataBatch: ...
