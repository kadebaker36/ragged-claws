"""Provider-neutral historical market-data boundary."""

from ragged_claws.market_data.alpaca import (
    ALPACA_ADAPTER_VERSION,
    AlpacaHistoricalBarsAdapter,
    AlpacaMarketDataError,
)
from ragged_claws.market_data.models import (
    DailyBar,
    DailyBarRequest,
    HistoricalSymbol,
    MarketDataBatch,
)
from ragged_claws.market_data.protocol import HistoricalDailyBarProvider

__all__ = [
    "ALPACA_ADAPTER_VERSION",
    "AlpacaHistoricalBarsAdapter",
    "AlpacaMarketDataError",
    "DailyBar",
    "DailyBarRequest",
    "HistoricalDailyBarProvider",
    "HistoricalSymbol",
    "MarketDataBatch",
]
