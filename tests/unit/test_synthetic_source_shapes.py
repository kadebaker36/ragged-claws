"""Test-only mappings from invented source shapes into canonical representations."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TypedDict, cast
from uuid import UUID

from ragged_claws.models import (
    ContentHash,
    DisclosedRange,
    Event,
    EventAttribute,
    EventAttributeType,
    EventEvidence,
    EventPartyReference,
    FinancialValue,
    FinancialValueKind,
    ObservationRole,
    PartialDate,
    Provenance,
    Relationship,
    RetentionClass,
    SourceLineage,
    SourceObservation,
    SubjectReference,
    SubjectType,
    TemporalPrecision,
    TemporalValue,
)
from ragged_claws.models.evidence import DerivationKind
from tests.model_helpers import (
    EVENT_ID,
    EVIDENCE_ID,
    ISSUER_ID,
    OBSERVATION_ID,
    PERSON_ID,
    PROVENANCE_ID,
)

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "synthetic"


class SecParty(TypedDict):
    cik: str
    name: str


class SecTransaction(TypedDict):
    code: str
    ownership_mode: str
    shares: str
    price: str
    post_transaction_shares: str


class SecFixture(TypedDict):
    fixture_notice: str
    accession_number: str
    accepted_at: str
    transaction_date: str
    issuer: SecParty
    reporting_owner: SecParty
    transaction: SecTransaction
    content_sha256: str


class AmountRangeFixture(TypedDict):
    raw: str
    lower: str
    upper: str
    currency: str


class QuiverFixture(TypedDict):
    fixture_notice: str
    normalized_record_id: str
    underlying_public_source_family: str
    published_date: str
    actor_name: str
    issuer_name: str
    amount_range: AmountRangeFixture
    content_sha256: str


class LittleSisFixture(TypedDict):
    fixture_notice: str
    relationship_record_id: str
    source_person_id: str
    target_organization_id: str
    relationship_type: str
    start_date: str
    record_updated_at: str
    content_sha256: str


def load_fixture(name: str) -> object:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_sec_shaped_fixture_maps_to_observation_event_and_exact_values() -> None:
    payload = cast(SecFixture, load_fixture("sec_form4.json"))
    accepted_at = datetime.fromisoformat(payload["accepted_at"])
    transaction_date = datetime.fromisoformat(payload["transaction_date"]).date()
    public_time = TemporalValue(
        raw_value=payload["accepted_at"],
        precision=TemporalPrecision.SECOND,
        timestamp=accepted_at,
        source_timezone="America/New_York",
    )
    observation = SourceObservation(
        source_observation_id=OBSERVATION_ID,
        provider_namespace="sec.edgar",
        source_native_id=payload["accession_number"],
        lineage=SourceLineage(
            source_family="sec.edgar.form4",
            observation_role=ObservationRole.PRIMARY_SOURCE,
        ),
        retrieved_at=datetime(2024, 5, 6, 21, tzinfo=UTC),
        observed_at=datetime(2024, 5, 6, 21, tzinfo=UTC),
        public_time=public_time,
        raw_content_hash=ContentHash(value=payload["content_sha256"]),
        adapter_version="synthetic-sec-map/1",
        parser_version="synthetic-sec-parser/1",
        source_locator=f"synthetic://sec/{payload['accession_number']}",
        retention_class=RetentionClass.PUBLIC,
        license_name="synthetic-test-data",
    )
    provenance = Provenance(
        provenance_id=PROVENANCE_ID,
        source_observation_ids=(observation.source_observation_id,),
        derivation_kind=DerivationKind.SYNTHETIC_TEST,
        derived_at=datetime(2024, 5, 6, 21, tzinfo=UTC),
        transform_version="synthetic-sec-map/1",
    )
    evidence = EventEvidence(
        event_evidence_id=EVIDENCE_ID,
        event_id=EVENT_ID,
        source_observation_ids=(observation.source_observation_id,),
        provenance_id=provenance.provenance_id,
    )
    event = Event(
        event_id=EVENT_ID,
        event_type="insider_transaction",
        actors=(EventPartyReference(entity_id=PERSON_ID, role="reporting_owner"),),
        economic_units=(
            EventPartyReference(entity_id=PERSON_ID, role="beneficial_owner"),
        ),
        issuer_entity_id=ISSUER_ID,
        occurrence_time=TemporalValue(
            raw_value=payload["transaction_date"],
            precision=TemporalPrecision.DAY,
            partial_date=PartialDate(
                raw_value=payload["transaction_date"],
                precision=TemporalPrecision.DAY,
                year=transaction_date.year,
                month=transaction_date.month,
                day=transaction_date.day,
            ),
        ),
        public_time=public_time,
        financial_values=(
            FinancialValue(
                name="transaction_shares",
                kind=FinancialValueKind.QUANTITY,
                value=Decimal(payload["transaction"]["shares"]),
                unit="shares",
            ),
            FinancialValue(
                name="transaction_price",
                kind=FinancialValueKind.UNIT_PRICE,
                value=Decimal(payload["transaction"]["price"]),
                currency="USD",
                unit="share",
            ),
            FinancialValue(
                name="post_transaction_shares",
                kind=FinancialValueKind.QUANTITY,
                value=Decimal(payload["transaction"]["post_transaction_shares"]),
                unit="shares",
            ),
        ),
        attributes=(
            EventAttribute(
                name="transaction_code",
                value_type=EventAttributeType.CODE,
                value="purchase",
                raw_value=payload["transaction"]["code"],
            ),
            EventAttribute(
                name="ownership_mode",
                value_type=EventAttributeType.CODE,
                value="direct",
                raw_value=payload["transaction"]["ownership_mode"],
            ),
        ),
        event_evidence_ids=(evidence.event_evidence_id,),
        provenance_id=provenance.provenance_id,
    )

    assert event.financial_values[0].value == Decimal("125.000")
    assert event.financial_values[0].name == "transaction_shares"
    assert event.financial_values[2].name == "post_transaction_shares"
    assert event.actors[0].entity_id == PERSON_ID
    assert event.economic_units[0].entity_id == PERSON_ID
    assert {attribute.name: attribute.value for attribute in event.attributes} == {
        "transaction_code": "purchase",
        "ownership_mode": "direct",
    }
    assert event.attributes[0].raw_value == "P"
    assert event.attributes[1].raw_value == "D"
    assert event.event_evidence_ids == (evidence.event_evidence_id,)
    assert evidence.provenance_id == provenance.provenance_id
    assert event.public_time == observation.public_time
    assert payload["fixture_notice"].startswith("Invented")


def test_quiver_shaped_fixture_preserves_underlying_public_lineage_and_range() -> None:
    payload = cast(QuiverFixture, load_fixture("quiver_disclosure.json"))
    publication_date = datetime.fromisoformat(payload["published_date"]).date()
    observation_id = UUID("22222222-2222-4222-8222-222222222222")
    observation = SourceObservation(
        source_observation_id=observation_id,
        provider_namespace="quiver",
        source_native_id=payload["normalized_record_id"],
        lineage=SourceLineage(
            source_family="vendor.political_disclosure",
            underlying_source_family=payload["underlying_public_source_family"],
            observation_role=ObservationRole.VENDOR_NORMALIZED,
        ),
        retrieved_at=datetime(2024, 5, 8, 1, tzinfo=UTC),
        observed_at=datetime(2024, 5, 8, 1, tzinfo=UTC),
        public_time=TemporalValue(
            raw_value=payload["published_date"],
            precision=TemporalPrecision.DAY,
            partial_date=PartialDate(
                raw_value=payload["published_date"],
                precision=TemporalPrecision.DAY,
                year=publication_date.year,
                month=publication_date.month,
                day=publication_date.day,
            ),
        ),
        raw_content_hash=ContentHash(value=payload["content_sha256"]),
        adapter_version="synthetic-quiver-map/1",
        source_locator="synthetic://quiver/disclosure/1",
        retention_class=RetentionClass.RESTRICTED,
        license_name="synthetic-test-data",
    )
    disclosed_range = DisclosedRange(
        name="transaction_value_range",
        raw_text=payload["amount_range"]["raw"],
        lower_bound=Decimal(payload["amount_range"]["lower"]),
        upper_bound=Decimal(payload["amount_range"]["upper"]),
        currency=payload["amount_range"]["currency"],
        parser_version="synthetic-quiver-map/1",
    )

    assert observation.lineage.underlying_source_family == "public.political_disclosure"
    assert observation.lineage.observation_role is ObservationRole.VENDOR_NORMALIZED
    assert disclosed_range.raw_text == "$1,001-$5,000"
    assert disclosed_range.lower_bound == Decimal("1001")


def test_littlesis_shaped_fixture_preserves_partial_date_and_three_time_axes() -> None:
    payload = cast(LittleSisFixture, load_fixture("littlesis_relationship.json"))
    observation_id = UUID("33333333-3333-4333-8333-333333333333")
    observed_at = datetime.fromisoformat(payload["record_updated_at"])
    observation = SourceObservation(
        source_observation_id=observation_id,
        provider_namespace="littlesis",
        source_native_id=payload["relationship_record_id"],
        lineage=SourceLineage(
            source_family="relationship_database",
            observation_role=ObservationRole.ENRICHMENT,
        ),
        retrieved_at=observed_at,
        observed_at=observed_at,
        raw_content_hash=ContentHash(value=payload["content_sha256"]),
        adapter_version="synthetic-littlesis-map/1",
        source_locator="synthetic://littlesis/relationship/1",
        retention_class=RetentionClass.PUBLIC,
        license_name="synthetic-test-data",
    )
    valid_from = TemporalValue(
        raw_value=payload["start_date"],
        precision=TemporalPrecision.YEAR,
        partial_date=PartialDate(
            raw_value=payload["start_date"],
            precision=TemporalPrecision.YEAR,
            year=1856,
        ),
    )
    relationship = Relationship(
        relationship_id=UUID("60000000-0000-4000-8000-000000000002"),
        relationship_type=payload["relationship_type"],
        source=SubjectReference(subject_type=SubjectType.ENTITY, subject_id=PERSON_ID),
        target=SubjectReference(subject_type=SubjectType.ENTITY, subject_id=ISSUER_ID),
        valid_from=valid_from,
        known_from=None,
        observed_at=observation.observed_at,
        source_observation_ids=(observation.source_observation_id,),
        provenance_id=PROVENANCE_ID,
    )

    restored = Relationship.model_validate_json(relationship.model_dump_json())

    assert restored.valid_from is not None
    assert restored.valid_from.raw_value == "1856-00-00"
    assert restored.known_from is None
    assert restored.observed_at == observed_at
