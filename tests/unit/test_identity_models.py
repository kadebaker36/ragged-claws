"""Canonical identity-separation and temporal-axis tests."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from ragged_claws.models import (
    AliasType,
    Entity,
    EntityAlias,
    EntityType,
    ExternalIdentifier,
    ExternalIdentifierType,
    IdentifierSubjectType,
    Listing,
    Relationship,
    Security,
    SecurityType,
    SubjectReference,
    SubjectType,
    TemporalPrecision,
)
from tests.model_helpers import (
    ISSUER_ID,
    LISTING_ID,
    OBSERVATION_ID,
    OBSERVED_AT,
    PERSON_ID,
    PROVENANCE_ID,
    SECURITY_ID,
    partial_temporal,
)


def identifier(
    identifier_id: UUID,
    subject_type: IdentifierSubjectType,
    subject_id: UUID,
    identifier_type: ExternalIdentifierType,
    value: str,
    *,
    market_scope: str | None = None,
) -> ExternalIdentifier:
    return ExternalIdentifier(
        external_identifier_id=identifier_id,
        subject_type=subject_type,
        subject_id=subject_id,
        identifier_type=identifier_type,
        value=value,
        market_scope=market_scope,
        source_observation_id=OBSERVATION_ID,
        provenance_id=PROVENANCE_ID,
        observed_at=OBSERVED_AT,
    )


def test_entity_security_and_multiple_listings_remain_distinct() -> None:
    cik = identifier(
        UUID("40000000-0000-4000-8000-000000000001"),
        IdentifierSubjectType.ENTITY,
        ISSUER_ID,
        ExternalIdentifierType.SEC_CIK,
        "0000000001",
    )
    alias = EntityAlias(
        entity_alias_id=UUID("50000000-0000-4000-8000-000000000001"),
        entity_id=ISSUER_ID,
        value="Example Robotics Corp.",
        alias_type=AliasType.SOURCE_REPORTED,
        source_observation_id=OBSERVATION_ID,
        provenance_id=PROVENANCE_ID,
        observed_at=OBSERVED_AT,
    )
    issuer = Entity(
        entity_id=ISSUER_ID,
        entity_type=EntityType.ISSUER,
        display_name="Example Robotics Corporation",
        aliases=(alias,),
        external_identifiers=(cik,),
        provenance_id=PROVENANCE_ID,
    )
    class_a_id = SECURITY_ID
    class_b_id = UUID("20000000-0000-4000-8000-000000000002")
    share_class_figi = identifier(
        UUID("40000000-0000-4000-8000-000000000002"),
        IdentifierSubjectType.SECURITY,
        class_a_id,
        ExternalIdentifierType.FIGI_SHARE_CLASS,
        "BBG000000002",
    )
    composite_figi = identifier(
        UUID("40000000-0000-4000-8000-000000000003"),
        IdentifierSubjectType.SECURITY,
        class_a_id,
        ExternalIdentifierType.FIGI_COMPOSITE,
        "BBG000000003",
        market_scope="US",
    )
    class_a = Security(
        security_id=class_a_id,
        issuer_entity_id=issuer.entity_id,
        security_type=SecurityType.COMMON_STOCK,
        display_name="Example Robotics Class A Common Stock",
        share_class="Class A",
        external_identifiers=(share_class_figi, composite_figi),
        provenance_id=PROVENANCE_ID,
    )
    class_b = Security(
        security_id=class_b_id,
        issuer_entity_id=issuer.entity_id,
        security_type=SecurityType.COMMON_STOCK,
        display_name="Example Robotics Class B Common Stock",
        share_class="Class B",
        provenance_id=PROVENANCE_ID,
    )
    historical_listing = Listing(
        listing_id=UUID("30000000-0000-4000-8000-000000000002"),
        security_id=class_a.security_id,
        symbol="OLDX",
        exchange_mic="XNYS",
        effective_to=partial_temporal(
            "2019-12-31", TemporalPrecision.DAY, year=2019, month=12, day=31
        ),
        provenance_id=PROVENANCE_ID,
    )
    venue_figi = identifier(
        UUID("40000000-0000-4000-8000-000000000004"),
        IdentifierSubjectType.LISTING,
        LISTING_ID,
        ExternalIdentifierType.FIGI_INSTRUMENT,
        "BBG000000004",
    )
    current_listing = Listing(
        listing_id=LISTING_ID,
        security_id=class_a.security_id,
        symbol="EXRA",
        exchange_mic="XNAS",
        effective_from=partial_temporal(
            "2020-01-02", TemporalPrecision.DAY, year=2020, month=1, day=2
        ),
        external_identifiers=(venue_figi,),
        provenance_id=PROVENANCE_ID,
    )

    assert issuer.entity_id not in {class_a.security_id, current_listing.listing_id}
    assert class_a.issuer_entity_id == class_b.issuer_entity_id == issuer.entity_id
    assert historical_listing.security_id == current_listing.security_id == class_a.security_id
    assert {historical_listing.symbol, current_listing.symbol} == {"OLDX", "EXRA"}
    assert {item.identifier_type for item in class_a.external_identifiers} == {
        ExternalIdentifierType.FIGI_SHARE_CLASS,
        ExternalIdentifierType.FIGI_COMPOSITE,
    }
    assert current_listing.external_identifiers[0].identifier_type is (
        ExternalIdentifierType.FIGI_INSTRUMENT
    )
    assert composite_figi.market_scope == "US"
    assert "symbol" not in Security.model_json_schema()["properties"]


@pytest.mark.parametrize(
    ("identifier_type", "subject_type", "subject_id", "market_scope"),
    [
        (ExternalIdentifierType.SEC_CIK, IdentifierSubjectType.SECURITY, SECURITY_ID, None),
        (ExternalIdentifierType.LEI, IdentifierSubjectType.LISTING, LISTING_ID, None),
        (ExternalIdentifierType.FIGI_SHARE_CLASS, IdentifierSubjectType.ENTITY, ISSUER_ID, None),
        (ExternalIdentifierType.FIGI_INSTRUMENT, IdentifierSubjectType.ENTITY, ISSUER_ID, None),
        (
            ExternalIdentifierType.FIGI_COMPOSITE,
            IdentifierSubjectType.LISTING,
            LISTING_ID,
            "US",
        ),
    ],
)
def test_invalid_identifier_subject_mappings_fail_loudly(
    identifier_type: ExternalIdentifierType,
    subject_type: IdentifierSubjectType,
    subject_id: UUID,
    market_scope: str | None,
) -> None:
    with pytest.raises(ValidationError, match="cannot identify"):
        identifier(
            UUID("40000000-0000-4000-8000-000000000010"),
            subject_type,
            subject_id,
            identifier_type,
            "INVALIDSUBJ1",
            market_scope=market_scope,
        )


def test_composite_figi_requires_market_scope() -> None:
    with pytest.raises(ValidationError, match="requires market_scope"):
        identifier(
            UUID("40000000-0000-4000-8000-000000000011"),
            IdentifierSubjectType.SECURITY,
            SECURITY_ID,
            ExternalIdentifierType.FIGI_COMPOSITE,
            "BBG000000011",
        )


def test_identifier_subject_mismatch_and_ambiguous_namespace_fail() -> None:
    mismatched = identifier(
        UUID("40000000-0000-4000-8000-000000000012"),
        IdentifierSubjectType.SECURITY,
        UUID("20000000-0000-4000-8000-000000000099"),
        ExternalIdentifierType.FIGI_SHARE_CLASS,
        "BBG000000099",
    )
    with pytest.raises(ValidationError, match="must match"):
        Security(
            security_id=SECURITY_ID,
            issuer_entity_id=ISSUER_ID,
            security_type=SecurityType.COMMON_STOCK,
            display_name="Example security",
            external_identifiers=(mismatched,),
            provenance_id=PROVENANCE_ID,
        )

    with pytest.raises(ValidationError, match="explicit namespace"):
        ExternalIdentifier(
            external_identifier_id=UUID("40000000-0000-4000-8000-000000000013"),
            subject_type=IdentifierSubjectType.ENTITY,
            subject_id=ISSUER_ID,
            identifier_type=ExternalIdentifierType.OTHER,
            value="custom-1",
            source_observation_id=OBSERVATION_ID,
            provenance_id=PROVENANCE_ID,
            observed_at=OBSERVED_AT,
        )


def test_relationship_keeps_valid_known_and_observed_axes_separate() -> None:
    relationship = Relationship(
        relationship_id=UUID("60000000-0000-4000-8000-000000000001"),
        relationship_type="director_of",
        source=SubjectReference(subject_type=SubjectType.ENTITY, subject_id=PERSON_ID),
        target=SubjectReference(subject_type=SubjectType.ENTITY, subject_id=ISSUER_ID),
        valid_from=partial_temporal("1856-00-00", TemporalPrecision.YEAR, year=1856),
        known_from=partial_temporal(
            "2024-06-01", TemporalPrecision.DAY, year=2024, month=6, day=1
        ),
        observed_at=datetime(2024, 6, 2, 9, 30, tzinfo=UTC),
        confidence=Decimal("0.75"),
        source_observation_ids=(OBSERVATION_ID,),
        provenance_id=PROVENANCE_ID,
    )

    restored = Relationship.model_validate_json(relationship.model_dump_json())

    assert restored.valid_from != restored.known_from
    assert restored.observed_at > datetime(2024, 6, 1, tzinfo=UTC)
