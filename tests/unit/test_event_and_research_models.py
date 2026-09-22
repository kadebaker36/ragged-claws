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
    EventAttribute,
    EventAttributeType,
    EventPartyReference,
    FeatureSnapshot,
    FeatureValue,
    FinancialValue,
    FinancialValueKind,
    Outcome,
    OutcomeMethodology,
    OutcomeStatus,
    TemporalPrecision,
)
from tests.model_helpers import (
    EVENT_ID,
    EVIDENCE_ID,
    ISSUER_ID,
    LISTING_ID,
    OBSERVATION_ID,
    PERSON_ID,
    PROVENANCE_ID,
    SECURITY_ID,
    outcome_methodology,
    partial_temporal,
)


def test_decimal_financial_values_and_disclosed_range_roundtrip_exactly() -> None:
    shares = FinancialValue(
        name="transaction_shares",
        kind=FinancialValueKind.QUANTITY,
        value=Decimal("125.000"),
        unit="shares",
    )
    price = FinancialValue(
        name="transaction_price",
        kind=FinancialValueKind.UNIT_PRICE,
        value=Decimal("42.10"),
        currency="USD",
        unit="share",
    )
    disclosed_range = DisclosedRange(
        name="transaction_value_range",
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
    assert restored_shares.name == "transaction_shares"
    assert restored_price.value == Decimal("42.10")
    assert restored_price.name == "transaction_price"
    assert restored_range.lower_bound == Decimal("1001")
    assert restored_range.upper_bound == Decimal("5000")
    assert restored_range.name == "transaction_value_range"
    assert "midpoint" not in DisclosedRange.model_json_schema()["properties"]


def test_binary_float_and_reversed_range_are_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialValue(
            name="transaction_shares",
            kind=FinancialValueKind.QUANTITY,
            value=cast(Decimal, 1.5),
            unit="shares",
        )

    with pytest.raises(ValidationError, match="cannot exceed"):
        DisclosedRange(
            name="transaction_value_range",
            raw_text="$5,000-$1,001",
            lower_bound=Decimal("5000"),
            upper_bound=Decimal("1001"),
            currency="USD",
        )


def test_event_serialization_preserves_separate_identity_and_evidence_links() -> None:
    event = Event(
        event_id=EVENT_ID,
        event_type="insider_transaction",
        actors=(EventPartyReference(entity_id=PERSON_ID, role="reporting_owner"),),
        economic_units=(
            EventPartyReference(entity_id=PERSON_ID, role="beneficial_owner"),
        ),
        issuer_entity_id=ISSUER_ID,
        security_id=SECURITY_ID,
        listing_id=LISTING_ID,
        occurrence_time=partial_temporal(
            "2024-05-03", TemporalPrecision.DAY, year=2024, month=5, day=3
        ),
        public_time=partial_temporal(
            "2024-05-06", TemporalPrecision.DAY, year=2024, month=5, day=6
        ),
        attributes=(
            EventAttribute(
                name="transaction_code",
                value_type=EventAttributeType.CODE,
                value="purchase",
                raw_value="P",
            ),
            EventAttribute(
                name="ownership_mode",
                value_type=EventAttributeType.CODE,
                value="direct",
                raw_value="D",
            ),
        ),
        event_evidence_ids=(EVIDENCE_ID,),
        provenance_id=PROVENANCE_ID,
    )

    assert Event.model_validate_json(event.model_dump_json()) == event
    assert event.actors[0].role == "reporting_owner"
    assert event.economic_units[0].role == "beneficial_owner"

    with pytest.raises(ValidationError, match="listing_id requires security_id"):
        Event(
            event_id=EVENT_ID,
            event_type="unresolved_event",
            listing_id=LISTING_ID,
            occurrence_time=partial_temporal("unknown", TemporalPrecision.UNKNOWN),
            event_evidence_ids=(EVIDENCE_ID,),
            provenance_id=PROVENANCE_ID,
        )


@pytest.mark.parametrize(
    ("value_type", "value"),
    [
        (EventAttributeType.CODE, "P"),
        (EventAttributeType.TEXT, "1.25"),
        (EventAttributeType.BOOLEAN, True),
        (EventAttributeType.INTEGER, 1),
        (EventAttributeType.DECIMAL, Decimal("1.2500")),
    ],
)
def test_event_attribute_types_roundtrip_without_semantic_coercion(
    value_type: EventAttributeType,
    value: str | bool | int | Decimal,
) -> None:
    attribute = EventAttribute(name="test_attribute", value_type=value_type, value=value)

    assert type(attribute.value) is type(value)

    restored = EventAttribute.model_validate_json(attribute.model_dump_json())

    assert restored == attribute
    assert type(restored.value) is type(value)
    if isinstance(value, Decimal):
        assert isinstance(restored.value, Decimal)
        assert restored.value.as_tuple() == value.as_tuple()


@pytest.mark.parametrize(
    ("value_type", "value"),
    [
        (EventAttributeType.CODE, 1),
        (EventAttributeType.TEXT, Decimal("1.25")),
        (EventAttributeType.BOOLEAN, 1),
        (EventAttributeType.INTEGER, True),
        (EventAttributeType.DECIMAL, "1.25"),
    ],
)
def test_event_attribute_rejects_mismatched_runtime_types(
    value_type: EventAttributeType,
    value: str | bool | int | Decimal,
) -> None:
    with pytest.raises(ValidationError, match="attribute requires"):
        EventAttribute(name="test_attribute", value_type=value_type, value=value)


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
        methodology=outcome_methodology(),
        provenance_id=PROVENANCE_ID,
    )

    assert Outcome.model_validate_json(complete.model_dump_json()) == complete

    complete_without_price_sources = complete.model_dump()
    complete_without_price_sources["methodology"] = outcome_methodology(())
    with pytest.raises(ValidationError, match="price state requires price source observations"):
        Outcome.model_validate(complete_without_price_sources)

    right_censored = Outcome(
        outcome_id=UUID("90000000-0000-4000-8000-000000000002"),
        event_id=EVENT_ID,
        security_id=SECURITY_ID,
        listing_id=LISTING_ID,
        actionable_at=actionable_at,
        entry_at=actionable_at,
        entry_price=Decimal("42.10"),
        benchmark_listing_id=UUID("30000000-0000-4000-8000-000000000099"),
        horizon_sessions=120,
        status=OutcomeStatus.RIGHT_CENSORED,
        methodology=outcome_methodology(),
        provenance_id=PROVENANCE_ID,
    )
    terminal = Outcome(
        outcome_id=UUID("90000000-0000-4000-8000-000000000003"),
        event_id=EVENT_ID,
        security_id=SECURITY_ID,
        listing_id=LISTING_ID,
        actionable_at=actionable_at,
        entry_at=actionable_at,
        entry_price=Decimal("42.10"),
        benchmark_listing_id=UUID("30000000-0000-4000-8000-000000000099"),
        horizon_sessions=60,
        status=OutcomeStatus.TERMINAL_DELISTED,
        methodology=outcome_methodology(),
        provenance_id=PROVENANCE_ID,
    )

    assert Outcome.model_validate_json(right_censored.model_dump_json()) == right_censored
    assert terminal.entry_price == Decimal("42.10")
    assert terminal.benchmark_listing_id is not None


@pytest.mark.parametrize(
    "status",
    [OutcomeStatus.RIGHT_CENSORED, OutcomeStatus.TERMINAL_DELISTED],
)
def test_partial_outcome_prices_require_source_provenance(status: OutcomeStatus) -> None:
    actionable_at = datetime(2024, 5, 7, 13, 30, tzinfo=UTC)

    def build_outcome(methodology: OutcomeMethodology) -> Outcome:
        return Outcome(
            outcome_id=UUID("90000000-0000-4000-8000-000000000006"),
            event_id=EVENT_ID,
            security_id=SECURITY_ID,
            listing_id=LISTING_ID,
            actionable_at=actionable_at,
            entry_at=actionable_at,
            entry_price=Decimal("42.10"),
            benchmark_listing_id=UUID("30000000-0000-4000-8000-000000000099"),
            horizon_sessions=120,
            status=status,
            methodology=methodology,
            provenance_id=PROVENANCE_ID,
        )

    with_provenance = build_outcome(outcome_methodology())
    assert with_provenance.entry_price == Decimal("42.10")

    with pytest.raises(ValidationError, match="price state requires price source observations"):
        build_outcome(outcome_methodology(()))


def test_outcome_without_observed_prices_does_not_invent_price_provenance() -> None:
    outcome = Outcome(
        outcome_id=UUID("90000000-0000-4000-8000-000000000007"),
        event_id=EVENT_ID,
        security_id=SECURITY_ID,
        listing_id=LISTING_ID,
        actionable_at=datetime(2024, 5, 7, 13, 30, tzinfo=UTC),
        benchmark_listing_id=UUID("30000000-0000-4000-8000-000000000099"),
        horizon_sessions=20,
        status=OutcomeStatus.MISSING_PRICE,
        methodology=outcome_methodology(()),
        provenance_id=PROVENANCE_ID,
    )

    assert outcome.methodology.price_source_observation_ids == ()


def test_incomplete_outcome_rejects_completed_return_fields() -> None:
    actionable_at = datetime(2024, 5, 7, 13, 30, tzinfo=UTC)
    with pytest.raises(ValidationError, match="cannot contain completed return fields"):
        Outcome(
            outcome_id=UUID("90000000-0000-4000-8000-000000000004"),
            event_id=EVENT_ID,
            security_id=SECURITY_ID,
            listing_id=LISTING_ID,
            actionable_at=actionable_at,
            entry_at=actionable_at,
            entry_price=Decimal("42.10"),
            security_return=Decimal("0.01"),
            horizon_sessions=20,
            status=OutcomeStatus.RIGHT_CENSORED,
            methodology=outcome_methodology(),
            provenance_id=PROVENANCE_ID,
        )


def test_unresolved_outcome_rejects_fabricated_security_state() -> None:
    with pytest.raises(ValidationError, match="cannot fabricate"):
        Outcome(
            outcome_id=UUID("90000000-0000-4000-8000-000000000005"),
            event_id=EVENT_ID,
            security_id=SECURITY_ID,
            actionable_at=datetime(2024, 5, 7, 13, 30, tzinfo=UTC),
            horizon_sessions=20,
            status=OutcomeStatus.UNRESOLVED_SECURITY,
            methodology=outcome_methodology(()),
            provenance_id=PROVENANCE_ID,
        )
