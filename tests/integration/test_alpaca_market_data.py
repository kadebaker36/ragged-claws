"""Fixture-only Alpaca adapter tests; no default test performs network I/O."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx
import pytest

import ragged_claws.market_data.alpaca as alpaca_module
from ragged_claws.market_data import (
    AlpacaHistoricalBarsAdapter,
    AlpacaMarketDataError,
    DailyBarRequest,
    HistoricalSymbol,
)
from ragged_claws.market_data.alpaca import ALPACA_ADJUSTMENTS
from ragged_claws.models import PriceAdjustment
from ragged_claws.storage import DataLayout, raw_object_path

SECURITY_ID = UUID("20000000-0000-4000-8000-000000000020")
LISTING_ID = UUID("30000000-0000-4000-8000-000000000020")


def test_alpaca_adjustment_spelling_is_explicit() -> None:
    assert ALPACA_ADJUSTMENTS[PriceAdjustment.SPINOFF] == "spin-off"


def test_alpaca_adapter_is_explicit_paginated_and_historical_symbol_safe(
    tmp_path: Path,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        params = request.url.params
        symbol = params["symbols"]
        assert params["timeframe"] == "1Day"
        assert params["adjustment"] == "split"
        assert params["feed"] == "iex"
        assert "asof" in params
        assert params["limit"] == "10000"
        assert params["end"] == ("2024-03-11" if symbol == "OLD" else "2024-03-12")
        if symbol == "OLD" and "page_token" not in params:
            payload: dict[str, object] = {
                "bars": {
                    "OLD": [
                        {
                            "t": "2024-03-08T05:00:00Z",
                            "o": 10,
                            "h": 11,
                            "l": 9,
                            "c": 10.5,
                            "v": 100,
                        }
                    ]
                },
                "next_page_token": "next-old",
            }
        elif symbol == "OLD":
            assert params["page_token"] == "next-old"
            payload = {
                "bars": {
                    "OLD": [
                        {
                            "t": "2024-03-11T04:00:00Z",
                            "o": 10.5,
                            "h": 12,
                            "l": 10,
                            "c": 11,
                            "v": 110,
                        }
                    ]
                },
                "next_page_token": None,
            }
        else:
            assert symbol == "NEW"
            payload = {
                "bars": {
                    "NEW": [
                        {
                            "t": "2024-03-12T04:00:00Z",
                            "o": 11,
                            "h": 12,
                            "l": 10,
                            "c": 11.5,
                            "v": 120,
                        }
                    ]
                },
                "next_page_token": None,
            }
        content = json.dumps(payload, separators=(",", ":")).encode()
        if symbol == "OLD" and "page_token" not in params:
            content = content.replace(
                b'"c":10.5', b'"c":10.123456789012345678901'
            )
        return httpx.Response(200, content=content, request=request)

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://data.alpaca.markets"
    )
    layout = DataLayout(tmp_path / "data")
    adapter = AlpacaHistoricalBarsAdapter(
        layout, api_key="fixture-key", api_secret="fixture-secret", client=client
    )
    request = DailyBarRequest(
        security_id=SECURITY_ID,
        listing_id=LISTING_ID,
        start=date(2024, 3, 8),
        end=date(2024, 3, 12),
        symbols=(
            HistoricalSymbol(
                symbol="OLD",
                valid_from=date(2020, 1, 1),
                valid_to=date(2024, 3, 12),
                provider_asof=date(2024, 3, 8),
            ),
            HistoricalSymbol(
                symbol="NEW",
                valid_from=date(2024, 3, 12),
                provider_asof=date(2024, 3, 12),
            ),
        ),
        adjustment=PriceAdjustment.SPLIT,
        feed="iex",
    )

    batch = adapter.fetch(
        request, retrieved_at=datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    )

    assert [bar.session_date for bar in batch.bars] == [
        date(2024, 3, 8),
        date(2024, 3, 11),
        date(2024, 3, 12),
    ]
    assert all(bar.listing_id == LISTING_ID for bar in batch.bars)
    assert batch.bars[0].close == Decimal("10.123456789012345678901")
    assert len(batch.observations) == 3
    assert len(batch.capture_ids) == 3
    assert [request.url.params["symbols"] for request in requests] == ["OLD", "OLD", "NEW"]
    assert requests[0].url.params["asof"] == "2024-03-08"
    assert requests[2].url.params["asof"] == "2024-03-12"
    # The fixture straddles the U.S. DST change: both 05:00Z and 04:00Z daily stamps work.
    for observation in batch.observations:
        path = raw_object_path(layout, observation.raw_content_hash.value)
        assert path.exists()
        assert path.read_bytes().startswith(b'{"bars"')
    assert "fixture-key" not in str(requests[0].url)
    assert "fixture-secret" not in str(requests[0].url)


def test_alpaca_rejects_fractional_volume_without_truncation(tmp_path: Path) -> None:
    content = (
        b'{"bars":{"SYN":[{"t":"2024-03-11T04:00:00Z","o":10,'
        b'"h":11,"l":9,"c":10.5,"v":1.2}]},"next_page_token":null}'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content, request=request)

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://data.alpaca.markets"
    )
    adapter = AlpacaHistoricalBarsAdapter(
        DataLayout(tmp_path / "data"),
        api_key="fixture-key",
        api_secret="fixture-secret",
        client=client,
    )
    request = DailyBarRequest(
        security_id=SECURITY_ID,
        listing_id=LISTING_ID,
        start=date(2024, 3, 11),
        end=date(2024, 3, 11),
        symbols=(
            HistoricalSymbol(
                symbol="SYN",
                valid_from=date(2024, 3, 11),
                provider_asof=date(2024, 3, 11),
            ),
        ),
        adjustment=PriceAdjustment.RAW,
        feed="iex",
    )
    with pytest.raises(AlpacaMarketDataError, match="invalid Alpaca bar"):
        adapter.fetch(
            request, retrieved_at=datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
        )


def test_alpaca_observation_identity_includes_request_semantics(tmp_path: Path) -> None:
    content = (
        b'{"bars":{"SYN":[{"t":"2024-03-11T04:00:00Z","o":10,'
        b'"h":11,"l":9,"c":10.5,"v":100}]},"next_page_token":null}'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content, request=request)

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://data.alpaca.markets"
    )
    adapter = AlpacaHistoricalBarsAdapter(
        DataLayout(tmp_path / "data"),
        api_key="fixture-key",
        api_secret="fixture-secret",
        client=client,
    )
    base_request = DailyBarRequest(
        security_id=SECURITY_ID,
        listing_id=LISTING_ID,
        start=date(2024, 3, 11),
        end=date(2024, 3, 11),
        symbols=(
            HistoricalSymbol(
                symbol="SYN",
                valid_from=date(2024, 3, 11),
                provider_asof=date(2024, 3, 11),
            ),
        ),
        adjustment=PriceAdjustment.RAW,
        feed="iex",
    )

    raw = adapter.fetch(
        base_request, retrieved_at=datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    )
    split = adapter.fetch(
        base_request.model_copy(update={"adjustment": PriceAdjustment.SPLIT}),
        retrieved_at=datetime(2026, 9, 22, 12, 0, tzinfo=UTC),
    )

    assert raw.observations[0].raw_content_hash == split.observations[0].raw_content_hash
    assert raw.observations[0].source_native_id != split.observations[0].source_native_id
    assert (
        raw.observations[0].source_observation_id
        != split.observations[0].source_observation_id
    )


def test_alpaca_rejects_out_of_interval_bars(tmp_path: Path) -> None:
    content = (
        b'{"bars":{"OLD":[{"t":"2024-03-12T04:00:00Z","o":10,'
        b'"h":11,"l":9,"c":10.5,"v":100}]},"next_page_token":null}'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content, request=request)

    adapter = AlpacaHistoricalBarsAdapter(
        DataLayout(tmp_path / "data"),
        api_key="fixture-key",
        api_secret="fixture-secret",
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://data.alpaca.markets",
        ),
    )
    request = DailyBarRequest(
        security_id=SECURITY_ID,
        listing_id=LISTING_ID,
        start=date(2024, 3, 11),
        end=date(2024, 3, 11),
        symbols=(
            HistoricalSymbol(
                symbol="OLD",
                valid_from=date(2024, 3, 11),
                valid_to=date(2024, 3, 12),
                provider_asof=date(2024, 3, 11),
            ),
        ),
        adjustment=PriceAdjustment.RAW,
        feed="iex",
    )

    with pytest.raises(AlpacaMarketDataError, match="outside the requested"):
        adapter.fetch(
            request, retrieved_at=datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
        )


def test_alpaca_pagination_has_a_hard_safety_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        content = json.dumps(
            {"bars": {"SYN": []}, "next_page_token": f"page-{request_count}"}
        ).encode()
        return httpx.Response(200, content=content, request=request)

    monkeypatch.setattr(alpaca_module, "MAX_ALPACA_PAGES", 2)
    adapter = AlpacaHistoricalBarsAdapter(
        DataLayout(tmp_path / "data"),
        api_key="fixture-key",
        api_secret="fixture-secret",
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://data.alpaca.markets",
        ),
    )
    request = DailyBarRequest(
        security_id=SECURITY_ID,
        listing_id=LISTING_ID,
        start=date(2024, 3, 11),
        end=date(2024, 3, 11),
        symbols=(
            HistoricalSymbol(
                symbol="SYN",
                valid_from=date(2024, 3, 11),
                provider_asof=date(2024, 3, 11),
            ),
        ),
        adjustment=PriceAdjustment.RAW,
        feed="iex",
    )

    with pytest.raises(AlpacaMarketDataError, match="safety limit"):
        adapter.fetch(
            request, retrieved_at=datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
        )
    assert request_count == 2
