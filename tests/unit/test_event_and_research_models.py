"""Exact-value, event, snapshot, and outcome representation tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest
from pydantic import ValidationError

from ragged_claws.models import (
    DisclosedRange,
    Event,
    FeatureSnapshot,
    FeatureValue,
    FinancialValue,
    FinancialValueKind,
    Outcome,
    OutcomeStatus,
    PriceAdjustment,
    TemporalPrecision,
)
from tests.model_helpers import (
    EVENT_ID,
    EVIDENCE_ID,
    ISSUER_ID,
    LISTING_ID,
    OBSERVATION_ID,
    PROVENANCE_ID,
    SECURITY_ID,
    partial_temporal,
)


def test_decimal_financial_values_and_disclosed_range_roundtrip_exactly() -> None:
    shares = FinancialValue(
        financial_value_id=UUID("70000000-0000-4000-8000-000000000001"),
        kind=FinancialValueKind.QUANTITY,
        value=Decimal("125.000"),
        unit="shares",
    )
    price = FinancialValue(
        financial_value_id=UUID("70000000-0000-4000-8000-000000000002"),
        kind=FinancialValueKind.UNIT_PRICE,
        value=Decimal("42.10"),
        currency="USD",
        unit="share",
    )
    disclosed_range = DisclosedRange(
        disclosed_range_id=UUID("70000000-0000-4000-8000-000000000003"),
        raw_text="$1,001-$5,000",
        lower_bound=Decimal("1001"),
        upper_bound=Decimal("5000"),
        currency="USD",
        parser_version="synthetic-parser/1",
    )

    restored_shares = FinancialValue.model_validate_json(shares.model_dump_json())
    restored_price = FinancialValue.model_validate_json(price.model_dump_json())
    restored_range = DisclosedRange.model_validate_json(disclosed_range.model_dump_json())

    assert restored_shares.value == Decimal("125.000")
    assert restored_price.value == Decimal("42.10")
    assert restored_range.lower_bound == Decimal("1001")
    assert restored_range.upper_bound == Decimal("5000")
    assert "midpoint" not in DisclosedRange.model_json_schema()["properties"]


def test_binary_float_and_reversed_range_are_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialValue(
            financial_value_id=UUID("70000000-0000-4000-8000-000000000004"),
            kind=FinancialValueKind.QUANTITY,
            value=cast(Decimal, 1.5),
            unit="shares",
        )

    with pytest.raises(ValidationError, match="cannot exceed"):
        DisclosedRange(
            disclosed_range_id=UUID("70000000-0000-4000-8000-000000000005"),
            raw_text="$5,000-$1,001",
            lower_bound=Decimal("5000"),
            upper_bound=Decimal("1001"),
            currency="USD",
        )


def test_event_serialization_preserves_separate_identity_and_evidence_links() -> None:
    event = Event(
        event_id=EVENT_ID,
        event_type="insider_transaction",
        issuer_entity_id=ISSUER_ID,
        security_id=SECURITY_ID,
        listing_id=LISTING_ID,
        occurrence_time=partial_temporal(
            "2024-05-03", TemporalPrecision.DAY, year=2024, month=5, day=3
        ),
        public_time=partial_temporal(
            "2024-05-06", TemporalPrecision.DAY, year=2024, month=5, day=6
        ),
        event_evidence_ids=(EVIDENCE_ID,),
        provenance_id=PROVENANCE_ID,
    )

    assert Event.model_validate_json(event.model_dump_json()) == event

    with pytest.raises(ValidationError, match="listing_id requires security_id"):
        Event(
            event_id=EVENT_ID,
            event_type="unresolved_event",
            listing_id=LISTING_ID,
            occurrence_time=partial_temporal("unknown", TemporalPrecision.UNKNOWN),
            event_evidence_ids=(EVIDENCE_ID,),
            provenance_id=PROVENANCE_ID,
        )


def test_feature_snapshot_is_representational_and_rejects_float_values() -> None:
    feature = FeatureValue(
        feature_value_id=UUID("80000000-0000-4000-8000-000000000001"),
        name="transaction_value",
        value=Decimal("5262.5000"),
        known_from=partial_temporal(
            "2024-05-06", TemporalPrecision.DAY, year=2024, month=5, day=6
        ),
        source_observation_ids=(OBSERVATION_ID,),
    )
    snapshot = FeatureSnapshot(
        feature_snapshot_id=UUID("80000000-0000-4000-8000-000000000002"),
        event_id=EVENT_ID,
        snapshot_at=datetime(2024, 5, 7, 13, 30, tzinfo=UTC),
        feature_version="features/1",
        features=(feature,),
        provenance_id=PROVENANCE_ID,
    )

    assert FeatureSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot

    with pytest.raises(ValidationError):
        FeatureValue(
            feature_value_id=UUID("80000000-0000-4000-8000-000000000003"),
            name="unsafe_float",
            value=cast(Decimal, 0.1),
            source_observation_ids=(OBSERVATION_ID,),
        )


def test_outcome_validates_complete_and_incomplete_representations() -> None:
    actionable_at = datetime(2024, 5, 7, 13, 30, tzinfo=UTC)
    complete = Outcome(
        outcome_id=UUID("90000000-0000-4000-8000-000000000001"),
        event_id=EVENT_ID,
        security_id=SECURITY_ID,
        listing_id=LISTING_ID,
        actionable_at=actionable_at,
        entry_at=actionable_at,
        exit_at=actionable_at + timedelta(days=30),
        horizon_sessions=20,
        entry_price=Decimal("42.10"),
        exit_price=Decimal("45.00"),
        security_return=Decimal("0.06888361045130641330166270784"),
        benchmark_listing_id=UUID("30000000-0000-4000-8000-000000000099"),
        benchmark_return=Decimal("0.0200"),
        excess_return=Decimal("0.04888361045130641330166270784"),
        status=OutcomeStatus.COMPLETE,
        price_adjustment=PriceAdjustment.ALL,
        price_source_observation_ids=(OBSERVATION_ID,),
        provenance_id=PROVENANCE_ID,
    )

    assert Outcome.model_validate_json(complete.model_dump_json()) == complete

    with pytest.raises(ValidationError, match="cannot contain completed result fields"):
        Outcome(
            outcome_id=UUID("90000000-0000-4000-8000-000000000002"),
            event_id=EVENT_ID,
            actionable_at=actionable_at,
            entry_at=actionable_at,
            horizon_sessions=20,
            status=OutcomeStatus.RIGHT_CENSORED,
            price_adjustment=PriceAdjustment.ALL,
            provenance_id=PROVENANCE_ID,
        )
