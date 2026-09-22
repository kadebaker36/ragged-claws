"""Hand-calculated tests for the V0 forward-outcome convention."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from ragged_claws.market_data import DailyBar
from ragged_claws.models import (
    Event,
    Listing,
    OutcomeStatus,
    PartialDate,
    PriceAdjustment,
    Security,
    SecurityType,
    TemporalPrecision,
    TemporalValue,
)
from ragged_claws.outcomes import (
    OUTCOME_NAMESPACE,
    ForwardOutcomeEngine,
    OutcomeCalculationError,
    build_survivorship_audit,
)
from tests.model_helpers import EVIDENCE_ID, ISSUER_ID, PROVENANCE_ID

SECURITY_ID = UUID("20000000-0000-4000-8000-000000000010")
LISTING_ID = UUID("30000000-0000-4000-8000-000000000010")
SPY_SECURITY_ID = UUID("20000000-0000-4000-8000-000000000099")
SPY_LISTING_ID = UUID("30000000-0000-4000-8000-000000000099")
EVENT_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee6")
METHOD_ID = UUID("99999999-9999-4999-8999-999999999996")
SECURITY_OBSERVATION = UUID("11111111-1111-4111-8111-111111111116")
BENCHMARK_OBSERVATION = UUID("11111111-1111-4111-8111-111111111117")
ENTRY_AT = datetime(2024, 7, 3, 13, 30, tzinfo=UTC)
EXIT_AT = datetime(2024, 7, 11, 20, 0, tzinfo=UTC)


def _security() -> Security:
    return Security(
        security_id=SECURITY_ID,
        issuer_entity_id=ISSUER_ID,
        security_type=SecurityType.COMMON_STOCK,
        display_name="Synthetic Class A",
        provenance_id=PROVENANCE_ID,
    )


def _listing() -> Listing:
    return Listing(
        listing_id=LISTING_ID,
        security_id=SECURITY_ID,
        symbol="SYN",
        exchange_mic="XNYS",
        provenance_id=PROVENANCE_ID,
    )


def _benchmark_security() -> Security:
    return Security(
        security_id=SPY_SECURITY_ID,
        issuer_entity_id=UUID("10000000-0000-4000-8000-000000000099"),
        security_type=SecurityType.FUND_SHARE,
        display_name="Synthetic SPY benchmark",
        provenance_id=PROVENANCE_ID,
    )


def _benchmark_listing() -> Listing:
    return Listing(
        listing_id=SPY_LISTING_ID,
        security_id=SPY_SECURITY_ID,
        symbol="SPY",
        exchange_mic="ARCX",
        provenance_id=PROVENANCE_ID,
    )


def _event(actionable_at: datetime = ENTRY_AT) -> Event:
    return Event(
        event_id=EVENT_ID,
        event_type="synthetic_outcome_event",
        issuer_entity_id=ISSUER_ID,
        security_id=SECURITY_ID,
        listing_id=LISTING_ID,
        occurrence_time=TemporalValue(
            raw_value="2024-07-02",
            precision=TemporalPrecision.DAY,
            partial_date=PartialDate(
                raw_value="2024-07-02",
                precision=TemporalPrecision.DAY,
                year=2024,
                month=7,
                day=2,
            ),
        ),
        actionable_at=actionable_at,
        event_evidence_ids=(EVIDENCE_ID,),
        provenance_id=PROVENANCE_ID,
    )


def _bar(
    listing_id: UUID,
    security_id: UUID,
    session: date,
    open_price: str,
    close_price: str,
    observation_id: UUID,
    *,
    adjustment: PriceAdjustment = PriceAdjustment.ALL,
    feed: str = "iex",
) -> DailyBar:
    opening = Decimal(open_price)
    closing = Decimal(close_price)
    return DailyBar(
        security_id=security_id,
        listing_id=listing_id,
        session_date=session,
        open=opening,
        high=max(opening, closing),
        low=min(opening, closing),
        close=closing,
        volume=100,
        provider_namespace="synthetic.market_data",
        source_observation_id=observation_id,
        adjustment=adjustment,
        feed=feed,
    )


def _engine(adjustment: PriceAdjustment = PriceAdjustment.ALL) -> ForwardOutcomeEngine:
    return ForwardOutcomeEngine(
        methodology_id=METHOD_ID,
        methodology_version="v0/1.0.0",
        adjustment=adjustment,
        benchmark_security=_benchmark_security(),
        benchmark_listing=_benchmark_listing(),
        feed="iex",
    )


def _complete_bars() -> tuple[list[DailyBar], list[DailyBar]]:
    security_bars = [
        _bar(LISTING_ID, SECURITY_ID, date(2024, 7, 3), "100", "101", SECURITY_OBSERVATION),
        _bar(LISTING_ID, SECURITY_ID, date(2024, 7, 11), "109", "110", SECURITY_OBSERVATION),
    ]
    benchmark_bars = [
        _bar(
            SPY_LISTING_ID,
            SPY_SECURITY_ID,
            date(2024, 7, 3),
            "500",
            "501",
            BENCHMARK_OBSERVATION,
        ),
        _bar(
            SPY_LISTING_ID,
            SPY_SECURITY_ID,
            date(2024, 7, 11),
            "504",
            "505",
            BENCHMARK_OBSERVATION,
        ),
    ]
    return security_bars, benchmark_bars


def test_complete_five_session_spy_relative_result_uses_exact_decimal_math() -> None:
    security_bars, benchmark_bars = _complete_bars()
    outcome = _engine().calculate(
        event=_event(),
        horizon_sessions=5,
        security=_security(),
        listing=_listing(),
        security_bars=security_bars,
        benchmark_bars=benchmark_bars,
        coverage_through=date(2024, 7, 11),
        provenance_id=PROVENANCE_ID,
    )

    assert outcome.status is OutcomeStatus.COMPLETE
    assert outcome.entry_at == ENTRY_AT
    assert outcome.exit_at == EXIT_AT
    assert outcome.security_return == Decimal("0.1")
    assert outcome.benchmark_return == Decimal("0.01")
    assert outcome.excess_return == Decimal("0.09")
    assert outcome.methodology.price_adjustment is PriceAdjustment.ALL
    assert set(outcome.methodology.price_source_observation_ids) == {
        SECURITY_OBSERVATION,
        BENCHMARK_OBSERVATION,
    }
    # July 4 is a holiday and July 6-7 are a weekend: session 5 is July 11.
    assert outcome.exit_at.date() == date(2024, 7, 11)


def test_repeating_decimal_division_has_deterministic_unquantized_context() -> None:
    security_bars = [
        _bar(LISTING_ID, SECURITY_ID, date(2024, 7, 3), "3", "3", SECURITY_OBSERVATION),
        _bar(LISTING_ID, SECURITY_ID, date(2024, 7, 11), "4", "4", SECURITY_OBSERVATION),
    ]
    benchmark_bars = [
        _bar(
            SPY_LISTING_ID,
            SPY_SECURITY_ID,
            date(2024, 7, 3),
            "3",
            "3",
            BENCHMARK_OBSERVATION,
        ),
        _bar(
            SPY_LISTING_ID,
            SPY_SECURITY_ID,
            date(2024, 7, 11),
            "3",
            "3",
            BENCHMARK_OBSERVATION,
        ),
    ]
    outcome = _engine().calculate(
        event=_event(),
        horizon_sessions=5,
        security=_security(),
        listing=_listing(),
        security_bars=security_bars,
        benchmark_bars=benchmark_bars,
        coverage_through=date(2024, 7, 11),
        provenance_id=PROVENANCE_ID,
    )
    assert str(outcome.security_return) == "0.3333333333333333333333333333333333333333333333333"


@pytest.mark.parametrize("missing", ["entry", "exit"])
def test_missing_required_bar_is_explicit(missing: str) -> None:
    security_bars, benchmark_bars = _complete_bars()
    target = date(2024, 7, 3) if missing == "entry" else date(2024, 7, 11)
    security_bars = [bar for bar in security_bars if bar.session_date != target]
    outcome = _engine().calculate(
        event=_event(),
        horizon_sessions=5,
        security=_security(),
        listing=_listing(),
        security_bars=security_bars,
        benchmark_bars=benchmark_bars,
        coverage_through=date(2024, 7, 11),
        provenance_id=PROVENANCE_ID,
    )
    assert outcome.status is OutcomeStatus.MISSING_PRICE


def test_future_exit_is_right_censored_only_after_valid_entry() -> None:
    security_bars, benchmark_bars = _complete_bars()
    outcome = _engine().calculate(
        event=_event(),
        horizon_sessions=5,
        security=_security(),
        listing=_listing(),
        security_bars=security_bars[:1],
        benchmark_bars=benchmark_bars[:1],
        coverage_through=date(2024, 7, 10),
        provenance_id=PROVENANCE_ID,
    )
    assert outcome.status is OutcomeStatus.RIGHT_CENSORED
    assert outcome.entry_price == Decimal("100")


def test_unresolved_and_explicit_terminal_states_do_not_guess() -> None:
    unresolved = _engine().calculate(
        event=_event(),
        horizon_sessions=5,
        security=None,
        listing=None,
        security_bars=(),
        benchmark_bars=(),
        coverage_through=date(2024, 7, 11),
        provenance_id=PROVENANCE_ID,
    )
    terminal = _engine().calculate(
        event=_event(),
        horizon_sessions=5,
        security=_security(),
        listing=_listing(),
        security_bars=(),
        benchmark_bars=(),
        coverage_through=date(2024, 7, 11),
        provenance_id=PROVENANCE_ID,
        terminal_delisted=True,
    )
    assert unresolved.status is OutcomeStatus.UNRESOLVED_SECURITY
    assert terminal.status is OutcomeStatus.TERMINAL_DELISTED


def test_adjustment_or_feed_mismatch_fails_explicitly() -> None:
    security_bars, benchmark_bars = _complete_bars()
    security_bars[0] = security_bars[0].model_copy(
        update={"adjustment": PriceAdjustment.RAW}
    )
    with pytest.raises(OutcomeCalculationError, match="adjustment and feed"):
        _engine().calculate(
            event=_event(),
            horizon_sessions=5,
            security=_security(),
            listing=_listing(),
            security_bars=security_bars,
            benchmark_bars=benchmark_bars,
            coverage_through=date(2024, 7, 11),
            provenance_id=PROVENANCE_ID,
        )


def test_outcome_id_is_stable_and_never_uses_symbol_text() -> None:
    security_bars, benchmark_bars = _complete_bars()
    first = _engine().calculate(
        event=_event(),
        horizon_sessions=5,
        security=_security(),
        listing=_listing(),
        security_bars=security_bars,
        benchmark_bars=benchmark_bars,
        coverage_through=date(2024, 7, 11),
        provenance_id=PROVENANCE_ID,
    )
    changed_symbol = _listing().model_copy(update={"symbol": "RENAMED"})
    second = _engine().calculate(
        event=_event(),
        horizon_sessions=5,
        security=_security(),
        listing=changed_symbol,
        security_bars=security_bars,
        benchmark_bars=benchmark_bars,
        coverage_through=date(2024, 7, 11),
        provenance_id=PROVENANCE_ID,
    )
    assert first.outcome_id == second.outcome_id
    assert first.outcome_id == UUID("fa55c397-105c-5f04-80a3-60aef08fb32e")
    assert OUTCOME_NAMESPACE.version == 5


@pytest.mark.parametrize("horizon", [5, 20, 60, 90, 120])
def test_every_required_horizon_uses_following_sessions(horizon: int) -> None:
    security_bars, benchmark_bars = _complete_bars()
    outcome = _engine().calculate(
        event=_event(),
        horizon_sessions=horizon,
        security=_security(),
        listing=_listing(),
        security_bars=security_bars[:1],
        benchmark_bars=benchmark_bars[:1],
        coverage_through=date(2024, 7, 3),
        provenance_id=PROVENANCE_ID,
    )
    assert outcome.status is OutcomeStatus.RIGHT_CENSORED


def test_raw_adjustment_is_supported_when_both_series_match() -> None:
    security_bars, benchmark_bars = _complete_bars()
    security_bars = [
        value.model_copy(update={"adjustment": PriceAdjustment.RAW})
        for value in security_bars
    ]
    benchmark_bars = [
        value.model_copy(update={"adjustment": PriceAdjustment.RAW})
        for value in benchmark_bars
    ]
    outcome = _engine(PriceAdjustment.RAW).calculate(
        event=_event(),
        horizon_sessions=5,
        security=_security(),
        listing=_listing(),
        security_bars=security_bars,
        benchmark_bars=benchmark_bars,
        coverage_through=date(2024, 7, 11),
        provenance_id=PROVENANCE_ID,
    )
    assert outcome.status is OutcomeStatus.COMPLETE
    assert outcome.methodology.price_adjustment is PriceAdjustment.RAW



def test_survivorship_audit_counts_every_status_and_distinct_identity() -> None:
    security_bars, benchmark_bars = _complete_bars()
    complete = _engine().calculate(
        event=_event(),
        horizon_sessions=5,
        security=_security(),
        listing=_listing(),
        security_bars=security_bars,
        benchmark_bars=benchmark_bars,
        coverage_through=date(2024, 7, 11),
        provenance_id=PROVENANCE_ID,
    )
    unresolved = _engine().calculate(
        event=_event(),
        horizon_sessions=20,
        security=None,
        listing=None,
        security_bars=(),
        benchmark_bars=(),
        coverage_through=date(2024, 7, 11),
        provenance_id=PROVENANCE_ID,
    )
    audit = build_survivorship_audit(
        (complete, unresolved), issuer_by_event={EVENT_ID: ISSUER_ID}
    )
    assert audit.qualifying_events == 1
    assert audit.outcome_rows == 2
    assert audit.complete == 1
    assert audit.unresolved_security == 1
    assert audit.distinct_security_count == 1
    assert audit.distinct_issuer_count == 1
