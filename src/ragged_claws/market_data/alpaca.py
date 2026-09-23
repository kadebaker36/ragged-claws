"""Narrow Alpaca historical U.S. stock-bars adapter."""

import json
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx

from ragged_claws.market_data.models import (
    DailyBar,
    DailyBarRequest,
    HistoricalSymbol,
    MarketDataBatch,
)
from ragged_claws.models import (
    ObservationRole,
    PriceAdjustment,
    RetentionClass,
    SourceLineage,
    SourceObservation,
)
from ragged_claws.storage import DataLayout, capture_raw_bytes, deterministic_source_observation_id

ALPACA_PROVIDER = "alpaca.market_data"
ALPACA_SOURCE_FAMILY = "alpaca.stock_bars"
ALPACA_ADAPTER_VERSION = "alpaca-bars/1.0.0"
ALPACA_PARSER_VERSION = "alpaca-bars-json/1.0.0"
ALPACA_LICENSE = "alpaca-market-data-terms"
ALPACA_DATA_BASE_URL = "https://data.alpaca.markets"
MAX_ALPACA_PAGES = 100
ALPACA_ADJUSTMENTS = {
    PriceAdjustment.RAW: "raw",
    PriceAdjustment.SPLIT: "split",
    PriceAdjustment.DIVIDEND: "dividend",
    PriceAdjustment.SPINOFF: "spin-off",
    PriceAdjustment.ALL: "all",
}
NEW_YORK = ZoneInfo("America/New_York")


class AlpacaMarketDataError(RuntimeError):
    """Raised when Alpaca transport or response semantics cannot be defended."""


class AlpacaHistoricalBarsAdapter:
    """Retrieve explicit, paginated 1Day bars and preserve each raw response page."""

    def __init__(
        self,
        layout: DataLayout,
        *,
        api_key: str,
        api_secret: str,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key or not api_secret:
            raise ValueError("Alpaca API key and secret are required for live retrieval")
        self.layout = layout
        self._owns_client = client is None
        self.client = client or httpx.Client(base_url=ALPACA_DATA_BASE_URL, timeout=30.0)
        self.headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
        }

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def fetch(self, request: DailyBarRequest, *, retrieved_at: datetime) -> MarketDataBatch:
        if request.adjustment is PriceAdjustment.OTHER:
            raise AlpacaMarketDataError("Alpaca cannot map the canonical OTHER adjustment")
        bars: list[DailyBar] = []
        observations: list[SourceObservation] = []
        capture_ids: list[UUID] = []
        for segment in request.symbols:
            segment_start = max(request.start, segment.valid_from)
            segment_end = request.end
            if segment.valid_to is not None:
                segment_end = min(segment_end, segment.valid_to - timedelta(days=1))
            if segment_start > segment_end:
                continue
            page_bars, page_observations, page_captures = self._fetch_segment(
                request, segment, segment_start, segment_end, retrieved_at
            )
            bars.extend(page_bars)
            observations.extend(page_observations)
            capture_ids.extend(page_captures)
        by_session: dict[date, DailyBar] = {}
        for bar in bars:
            previous = by_session.get(bar.session_date)
            if previous is not None and previous != bar:
                raise AlpacaMarketDataError(
                    f"conflicting bars for canonical listing session {bar.session_date}"
                )
            by_session[bar.session_date] = bar
        return MarketDataBatch(
            bars=tuple(by_session[key] for key in sorted(by_session)),
            observations=tuple(observations),
            capture_ids=tuple(capture_ids),
        )

    def _fetch_segment(
        self,
        request: DailyBarRequest,
        segment: HistoricalSymbol,
        start: date,
        end: date,
        retrieved_at: datetime,
    ) -> tuple[list[DailyBar], list[SourceObservation], list[UUID]]:
        next_page_token: str | None = None
        page_number = 0
        bars: list[DailyBar] = []
        observations: list[SourceObservation] = []
        captures: list[UUID] = []
        seen_page_tokens: set[str] = set()
        while True:
            if page_number >= MAX_ALPACA_PAGES:
                raise AlpacaMarketDataError("Alpaca pagination exceeded the safety limit")
            parameters: dict[str, str | int] = {
                "symbols": segment.symbol,
                "timeframe": "1Day",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "adjustment": ALPACA_ADJUSTMENTS[request.adjustment],
                "feed": request.feed,
                "asof": segment.provider_asof.isoformat(),
                "limit": 10000,
            }
            if next_page_token is not None:
                parameters["page_token"] = next_page_token
            response = self.client.get(
                "/v2/stocks/bars", params=parameters, headers=self.headers
            )
            try:
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise AlpacaMarketDataError("Alpaca historical bars request failed") from exc

            page_number += 1
            request_identity = json.dumps(
                parameters, allow_nan=False, separators=(",", ":"), sort_keys=True
            )
            native_id = f"bars:{request.listing_id}:{request_identity}"
            manifest = capture_raw_bytes(
                self.layout,
                response.content,
                provider_namespace=ALPACA_PROVIDER,
                source_family=ALPACA_SOURCE_FAMILY,
                retrieved_at=retrieved_at,
                observed_at=retrieved_at,
                request_parameters=parameters,
                source_native_id=native_id,
                source_locator=str(response.request.url),
                adapter_version=ALPACA_ADAPTER_VERSION,
                parser_version=ALPACA_PARSER_VERSION,
                retention_class=RetentionClass.RESTRICTED,
                license_name=ALPACA_LICENSE,
            )
            observation = SourceObservation(
                source_observation_id=deterministic_source_observation_id(
                    ALPACA_PROVIDER, native_id, manifest.content_hash.value
                ),
                provider_namespace=ALPACA_PROVIDER,
                source_native_id=native_id,
                lineage=SourceLineage(
                    source_family=ALPACA_SOURCE_FAMILY,
                    observation_role=ObservationRole.VENDOR_NORMALIZED,
                ),
                retrieved_at=retrieved_at,
                observed_at=retrieved_at,
                raw_content_hash=manifest.content_hash,
                adapter_version=ALPACA_ADAPTER_VERSION,
                parser_version=ALPACA_PARSER_VERSION,
                source_locator=str(response.request.url),
                retention_class=RetentionClass.RESTRICTED,
                license_name=ALPACA_LICENSE,
            )
            payload = _parse_json_object(response.content)
            provider_bars = payload.get("bars")
            if not isinstance(provider_bars, dict):
                raise AlpacaMarketDataError("Alpaca response bars must be keyed by symbol")
            symbol_bars = provider_bars.get(segment.symbol, [])
            if not isinstance(symbol_bars, list):
                raise AlpacaMarketDataError("Alpaca symbol bars must be an array")
            for raw_bar in symbol_bars:
                bar = _normalize_bar(raw_bar, request, observation.source_observation_id)
                if not start <= bar.session_date <= end:
                    raise AlpacaMarketDataError(
                        "Alpaca returned a bar outside the requested historical-symbol interval"
                    )
                bars.append(bar)
            observations.append(observation)
            captures.append(manifest.capture_id)
            token = payload.get("next_page_token")
            if token is None:
                break
            if not isinstance(token, str) or not token:
                raise AlpacaMarketDataError("invalid Alpaca next_page_token")
            if token in seen_page_tokens:
                raise AlpacaMarketDataError("Alpaca repeated a pagination token")
            seen_page_tokens.add(token)
            next_page_token = token
        return bars, observations, captures


def _parse_json_object(content: bytes) -> dict[str, Any]:
    try:
        value = json.loads(
            content,
            parse_float=Decimal,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise AlpacaMarketDataError("Alpaca response is not valid JSON") from exc
    if not isinstance(value, dict):
        raise AlpacaMarketDataError("Alpaca response must be a JSON object")
    return value


def _normalize_bar(raw: object, request: DailyBarRequest, observation_id: UUID) -> DailyBar:
    if not isinstance(raw, dict):
        raise AlpacaMarketDataError("Alpaca bar must be a JSON object")
    try:
        timestamp = datetime.fromisoformat(str(raw["t"]).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError
        local_timestamp = timestamp.astimezone(NEW_YORK)
        if local_timestamp.timetz().replace(tzinfo=None) != datetime.min.time():
            raise ValueError
        session_date = local_timestamp.date()
        prices = {key: _exact_decimal(raw[key]) for key in ("o", "h", "l", "c")}
        volume_raw = raw.get("v")
        volume = _exact_integer(volume_raw) if volume_raw is not None else None
    except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
        raise AlpacaMarketDataError("invalid Alpaca bar payload") from exc
    return DailyBar(
        security_id=request.security_id,
        listing_id=request.listing_id,
        session_date=session_date,
        open=prices["o"],
        high=prices["h"],
        low=prices["l"],
        close=prices["c"],
        volume=volume,
        provider_namespace=ALPACA_PROVIDER,
        source_observation_id=observation_id,
        adjustment=request.adjustment,
        feed=request.feed,
    )


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _exact_decimal(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise ValueError("price must be a JSON number")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError("price must be finite")
    return result


def _exact_integer(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("volume must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value():
        return int(value)
    raise ValueError("volume must be an integer")
