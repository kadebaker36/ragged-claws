"""Identity -> segmented fixture prices -> exact outcomes -> canonical persistence."""

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from ragged_claws.market_data import AlpacaHistoricalBarsAdapter, DailyBar, DailyBarRequest
from ragged_claws.models import (
    Entity,
    EntityType,
    Listing,
    Outcome,
    OutcomeStatus,
    PartialDate,
    PriceAdjustment,
    Security,
    SourceObservation,
    TemporalPrecision,
    TemporalValue,
)
from ragged_claws.outcomes import OutcomeCalculationError
from ragged_claws.resolution import HistoricalListingRequest, IdentityCatalog, day_value
from ragged_claws.storage import CanonicalConflictError, CanonicalParquetStore, DataLayout
from tests.model_helpers import PROVENANCE_ID
from tests.unit.test_outcome_engine import _complete_bars, _engine, _event, _listing, _security


def _history() -> tuple[Listing, Listing]:
    old = _listing().model_copy(update={
        "symbol": "OLD", "effective_from": day_value(date(2020, 1, 1)),
        "effective_to": day_value(date(2024, 7, 9)),
    })
    new = old.model_copy(update={
        "listing_id": UUID(int=11), "symbol": "NEW",
        "effective_from": day_value(date(2024, 7, 9)), "effective_to": None,
    })
    return old, new


def _prices(new: Listing) -> tuple[list[DailyBar], list[DailyBar]]:
    bars, benchmark = _complete_bars()
    bars[1] = bars[1].model_copy(update={
        "listing_id": new.listing_id, "source_observation_id": UUID(int=12),
    })
    return bars, benchmark


def test_rename_spanning_resolution_adapter_outcome_and_storage(tmp_path: Path) -> None:
    old, new = _history()
    catalog = IdentityCatalog(securities=(_security(),), listings=(old, new))
    for listing, session in ((old, date(2024, 7, 3)), (new, date(2024, 7, 11))):
        result = catalog.resolve_listing(HistoricalListingRequest(
            security_id=listing.security_id, exchange_mic=listing.exchange_mic,
            symbol=listing.symbol, as_of=day_value(session),
        ))
        assert result.subject_id == listing.listing_id
        assert result.provenance_ids == (listing.provenance_id,)

    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        symbol = params["symbols"]
        if symbol == "OLD":
            assert (params["start"], params["end"]) == ("2024-07-03", "2024-07-08")
            stamp, opening, closing = "2024-07-03T04:00:00Z", 100, 101
        else:
            assert symbol == "NEW"
            assert (params["start"], params["end"]) == ("2024-07-09", "2024-07-11")
            stamp, opening, closing = "2024-07-11T04:00:00Z", 109, 110
        return httpx.Response(200, json={"bars": {symbol: [{
            "t": stamp, "o": opening, "h": closing, "l": opening, "c": closing,
        }]}, "next_page_token": None})

    layout = DataLayout(tmp_path / "data")
    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://fixture.test",
    ) as client:
        adapter = AlpacaHistoricalBarsAdapter(
            layout, api_key="fixture", api_secret="fixture", client=client,
        )
        batches = [adapter.fetch(DailyBarRequest.from_listing(
            listing, start=date(2024, 7, 3), end=date(2024, 7, 11),
            provider_asof=asof, adjustment=PriceAdjustment.ALL, feed="iex",
        ), retrieved_at=datetime(2026, 10, 22, tzinfo=UTC))
            for listing, asof in ((old, date(2024, 7, 3)), (new, date(2024, 7, 11)))]
    bars = tuple(bar for batch in batches for bar in batch.bars)
    observations = tuple(obs for batch in batches for obs in batch.observations)
    assert [bar.listing_id for bar in bars] == [old.listing_id, new.listing_id]
    for listing, batch in zip((old, new), batches, strict=True):
        assert str(listing.listing_id) in batch.observations[0].source_native_id
        assert batch.bars[0].source_observation_id == batch.observations[0].source_observation_id
    _, benchmark = _complete_bars()
    benchmark = [bar.model_copy(update={"provider_namespace": "alpaca.market_data"})
                 for bar in benchmark]
    outcome = _engine().calculate(
        event=_event(), horizon_sessions=5, security=_security(), listing=old,
        listing_history=(new,), security_bars=bars, benchmark_bars=benchmark,
        coverage_through=date(2024, 7, 11), provenance_id=PROVENANCE_ID,
    )
    assert outcome.status is OutcomeStatus.COMPLETE
    assert outcome.listing_id == old.listing_id
    assert (outcome.security_return, outcome.benchmark_return, outcome.excess_return) == (
        Decimal("0.1"), Decimal("0.01"), Decimal("0.09"),
    )
    assert {obs.source_observation_id for obs in observations} <= set(
        outcome.methodology.price_source_observation_ids,
    )
    store = CanonicalParquetStore(layout)
    issuer = Entity(entity_id=_security().issuer_entity_id, entity_type=EntityType.ISSUER,
                    display_name="Invented integration issuer", provenance_id=PROVENANCE_ID)
    assert store.persist(Entity, (issuer,))
    assert store.load(Entity) == (issuer,)
    assert store.persist(Security, (_security(),))
    assert store.load(Security) == (_security(),)
    assert store.persist(Listing, (old, new))
    assert set(store.load(Listing)) == {old, new}
    assert store.persist(SourceObservation, observations)
    assert set(store.load(SourceObservation)) == set(observations)
    assert store.persist(Outcome, (outcome,))
    assert store.load(Outcome) == (outcome,)
    assert not store.persist(Outcome, (outcome,))
    with pytest.raises(CanonicalConflictError):
        store.persist(Outcome, (outcome.model_copy(update={"provenance_id": UUID(int=13)}),))


@pytest.mark.parametrize("defect", ["overlap", "gap", "coarse", "reuse", "conflict", "venue"])
def test_listing_history_rejects_ambiguous_or_unsupported_bindings(defect: str) -> None:
    old, new = _history()
    if defect in {"overlap", "gap"}:
        new = new.model_copy(update={
            "effective_from": day_value(date(2024, 7, 8 if defect == "overlap" else 10)),
        })
    elif defect == "coarse":
        new = new.model_copy(update={"effective_from": TemporalValue(
            raw_value="2024-07", precision=TemporalPrecision.MONTH,
            partial_date=PartialDate(raw_value="2024-07", precision=TemporalPrecision.MONTH,
                                     year=2024, month=7),
        )})
    elif defect == "reuse":
        new = new.model_copy(update={"symbol": "OLD", "security_id": UUID(int=99)})
    elif defect == "conflict":
        new = old.model_copy(update={"symbol": "CONFLICT"})
    else:
        new = new.model_copy(update={"exchange_mic": "XNAS"})
    bars, benchmark = _prices(new)
    with pytest.raises(OutcomeCalculationError, match={
        "overlap": "overlapping", "gap": "coverage gap", "coarse": "day precision",
        "reuse": "another security", "conflict": "conflicting", "venue": "compatible venue",
    }[defect]):
        _engine().calculate(
            event=_event(), horizon_sessions=5, security=_security(), listing=old,
            listing_history=(new,), security_bars=bars, benchmark_bars=benchmark,
            coverage_through=date(2024, 7, 11), provenance_id=PROVENANCE_ID,
        )


@pytest.mark.parametrize(
    "defect", ["wrong_security", "unknown_listing", "old_after_end", "new_before_start"],
)
def test_each_bar_retains_and_validates_its_actual_listing(defect: str) -> None:
    old, new = _history()
    bars, benchmark = _prices(new)
    if defect == "wrong_security":
        bars[1] = bars[1].model_copy(update={"security_id": UUID(int=99)})
    elif defect == "unknown_listing":
        bars[1] = bars[1].model_copy(update={"listing_id": UUID(int=99)})
    elif defect == "old_after_end":
        bars[1] = bars[1].model_copy(update={"listing_id": old.listing_id})
    else:
        bars[0] = bars[0].model_copy(update={"listing_id": new.listing_id})
    with pytest.raises(OutcomeCalculationError, match="identity|interval"):
        _engine().calculate(
            event=_event(), horizon_sessions=5, security=_security(), listing=old,
            listing_history=(new,), security_bars=bars, benchmark_bars=benchmark,
            coverage_through=date(2024, 7, 11), provenance_id=PROVENANCE_ID,
        )


def test_one_request_cannot_relabel_two_symbols_with_one_listing() -> None:
    old, new = _history()
    requests = [DailyBarRequest.from_listing(
        listing, start=date(2024, 7, 3), end=date(2024, 7, 11), provider_asof=asof,
        adjustment=PriceAdjustment.ALL, feed="iex",
    ) for listing, asof in ((old, date(2024, 7, 3)), (new, date(2024, 7, 11)))]
    with pytest.raises(ValidationError, match="at most 1"):
        DailyBarRequest.model_validate({
            **requests[0].model_dump(), "symbols": tuple(r.symbols[0] for r in requests),
        })
    with pytest.raises(ValidationError, match="inside its canonical listing segment"):
        DailyBarRequest.model_validate({**requests[0].model_dump(), "end": date(2024, 7, 9)})


@pytest.mark.parametrize("censored", [True, False])
def test_listing_history_retains_honest_incomplete_outcomes(censored: bool) -> None:
    old, new = _history()
    bars, benchmark = _prices(new)
    outcome = _engine().calculate(
        event=_event(), horizon_sessions=5, security=_security(), listing=old,
        listing_history=() if censored else (new,),
        security_bars=bars[:1], benchmark_bars=benchmark[:1],
        coverage_through=date(2024, 7, 8) if censored else date(2024, 7, 11),
        provenance_id=PROVENANCE_ID,
    )
    assert outcome.status is (
        OutcomeStatus.RIGHT_CENSORED if censored else OutcomeStatus.MISSING_PRICE
    )
    assert outcome.listing_id == old.listing_id
    assert outcome.excess_return is None
    assert bars[0].source_observation_id in outcome.methodology.price_source_observation_ids
