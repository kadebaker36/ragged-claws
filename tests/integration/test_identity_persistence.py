"""Canonical identity products round-trip through authoritative Parquet."""

from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import pytest

from ragged_claws.models import (
    Entity,
    EntityType,
    ExternalIdentifier,
    ExternalIdentifierType,
    IdentifierSubjectType,
    Listing,
    Security,
    SecurityType,
)
from ragged_claws.resolution import (
    day_value,
    deterministic_entity_id_from_cik,
    deterministic_external_identifier_id,
)
from ragged_claws.storage import CanonicalConflictError, CanonicalParquetStore, DataLayout


def test_identity_records_roundtrip_idempotently_and_conflicts_remain_strict(
    tmp_path: Path,
) -> None:
    observation_id = UUID("11111111-1111-4111-8111-111111111111")
    provenance_id = UUID("22222222-2222-4222-8222-222222222222")
    entity_id = deterministic_entity_id_from_cik("1234567")
    security_id = UUID("33333333-3333-4333-8333-333333333333")
    listing_id = UUID("44444444-4444-4444-8444-444444444444")
    cik_claim = ExternalIdentifier(
        external_identifier_id=deterministic_external_identifier_id(
            subject_type=IdentifierSubjectType.ENTITY,
            subject_id=entity_id,
            identifier_type=ExternalIdentifierType.SEC_CIK,
            value="0001234567",
            source_observation_id=observation_id,
        ),
        subject_type=IdentifierSubjectType.ENTITY,
        subject_id=entity_id,
        identifier_type=ExternalIdentifierType.SEC_CIK,
        value="0001234567",
        source_observation_id=observation_id,
        provenance_id=provenance_id,
        known_from=day_value(date(2020, 1, 1)),
        observed_at=datetime(2020, 1, 2, tzinfo=UTC),
    )
    entity = Entity(
        entity_id=entity_id,
        entity_type=EntityType.ISSUER,
        display_name="Synthetic Issuer",
        external_identifiers=(cik_claim,),
        provenance_id=provenance_id,
    )
    security = Security(
        security_id=security_id,
        issuer_entity_id=entity_id,
        security_type=SecurityType.COMMON_STOCK,
        display_name="Synthetic Issuer Class A",
        share_class="A",
        provenance_id=provenance_id,
    )
    listing = Listing(
        listing_id=listing_id,
        security_id=security_id,
        symbol="SYN",
        exchange_mic="XNYS",
        effective_from=day_value(date(2020, 1, 1)),
        provenance_id=provenance_id,
    )
    store = CanonicalParquetStore(DataLayout(tmp_path))

    assert store.persist(Entity, (entity,))
    assert store.persist(ExternalIdentifier, (cik_claim,))
    assert store.persist(Security, (security,))
    assert store.persist(Listing, (listing,))
    assert not store.persist(Entity, (entity,))
    assert not store.persist(ExternalIdentifier, (cik_claim,))
    assert not store.persist(Security, (security,))
    assert not store.persist(Listing, (listing,))
    assert store.load(Entity) == (entity,)
    assert store.load(ExternalIdentifier) == (cik_claim,)
    assert store.load(Security) == (security,)
    assert store.load(Listing) == (listing,)

    conflicting = listing.model_copy(update={"symbol": "DIFFERENT"})
    with pytest.raises(CanonicalConflictError, match="different canonical payload"):
        store.persist(Listing, (conflicting,))
    assert store.load(Listing) == (listing,)
