"""Exact identifier, enrichment, and historical listing resolution tests."""

from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from ragged_claws.models import (
    Entity,
    EntityType,
    ExternalIdentifier,
    ExternalIdentifierType,
    IdentifierSubjectType,
    Security,
    SecurityType,
    TemporalValue,
)
from ragged_claws.resolution import (
    ClaimEvidence,
    EnrichmentStatus,
    EnrichmentUnavailable,
    GleifMatchKind,
    IdentifierResolutionRequest,
    IdentityCatalog,
    OpenFigiResponseError,
    ResolutionStatus,
    attempt_optional_enrichment,
    day_value,
    deterministic_entity_id_from_cik,
    deterministic_external_identifier_id,
    deterministic_listing_id_from_figi,
    deterministic_security_id,
    gleif_lei_claim,
    normalize_cik,
    openfigi_identifier_claims,
    parse_gleif_response,
    parse_openfigi_mapping_response,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "synthetic"
OBSERVATION_ID = UUID("11111111-1111-4111-8111-111111111111")
PROVENANCE_ID = UUID("22222222-2222-4222-8222-222222222222")
ISSUER_ID = deterministic_entity_id_from_cik("1234567")
SECURITY_A_ID = UUID("30000000-0000-4000-8000-000000000001")
SECURITY_B_ID = UUID("30000000-0000-4000-8000-000000000002")
LISTING_OLD_ID = UUID("40000000-0000-4000-8000-000000000001")
LISTING_NEW_ID = UUID("40000000-0000-4000-8000-000000000002")
OBSERVED_AT = datetime(2024, 1, 2, 12, tzinfo=UTC)


def test_cik_normalization_and_deterministic_identity_vector() -> None:
    assert normalize_cik(" 1234567 ") == "0001234567"
    assert deterministic_entity_id_from_cik("1234567") == ISSUER_ID
    assert str(ISSUER_ID) == "297857ea-76c6-5752-a900-facd0fe6537f"
    with pytest.raises(ValueError, match="ASCII digits"):
        normalize_cik("issuer name")


def test_strong_security_and_listing_id_rules_reject_ticker_identity() -> None:
    security_id = deterministic_security_id(
        ExternalIdentifierType.FIGI_SHARE_CLASS, "BBG00TESTSC1"
    )
    listing_id = deterministic_listing_id_from_figi("BBG000TESTL1")

    assert str(security_id) == "10db49ae-d8d0-5224-bda7-c06c72427848"
    assert str(listing_id) == "db1ce997-e990-55a6-81a8-0e0fe2aa5777"
    with pytest.raises(ValueError, match="cannot define Security"):
        deterministic_security_id(ExternalIdentifierType.SEC_CIK, "1234567")


def test_exact_typed_cik_resolves_issuer_and_duplicate_mapping_conflicts() -> None:
    claim = _claim(
        subject_type=IdentifierSubjectType.ENTITY,
        subject_id=ISSUER_ID,
        identifier_type=ExternalIdentifierType.SEC_CIK,
        value="0001234567",
    )
    issuer = _entity(ISSUER_ID, "Synthetic Issuer", claim)
    request = IdentifierResolutionRequest(
        subject_type=IdentifierSubjectType.ENTITY,
        identifier_type=ExternalIdentifierType.SEC_CIK,
        value="1234567",
    )

    resolved = IdentityCatalog(entities=(issuer,)).resolve_identifier(request)

    assert resolved.status is ResolutionStatus.RESOLVED
    assert resolved.subject_id == ISSUER_ID
    assert resolved.source_observation_ids == (OBSERVATION_ID,)
    assert resolved.known_from == claim.known_from
    assert resolved.valid_from == claim.valid_from

    other_id = UUID("10000000-0000-4000-8000-000000000099")
    conflict_claim = _claim(
        subject_type=IdentifierSubjectType.ENTITY,
        subject_id=other_id,
        identifier_type=ExternalIdentifierType.SEC_CIK,
        value="0001234567",
        observation_id=UUID("11111111-1111-4111-8111-111111111199"),
    )
    conflict = IdentityCatalog(
        entities=(issuer, _entity(other_id, "Other Issuer", conflict_claim))
    ).resolve_identifier(request)
    assert conflict.status is ResolutionStatus.CONFLICT
    assert set(conflict.candidate_ids) == {ISSUER_ID, other_id}


def test_claim_without_canonical_subject_does_not_resolve() -> None:
    orphan = _claim(
        subject_type=IdentifierSubjectType.ENTITY,
        subject_id=ISSUER_ID,
        identifier_type=ExternalIdentifierType.SEC_CIK,
        value="0001234567",
    )
    result = IdentityCatalog(external_identifiers=(orphan,)).resolve_identifier(
        IdentifierResolutionRequest(
            subject_type=IdentifierSubjectType.ENTITY,
            identifier_type=ExternalIdentifierType.SEC_CIK,
            value="1234567",
        )
    )
    assert result.status is ResolutionStatus.UNRESOLVED


def test_multi_class_securities_resolve_independently_under_one_issuer() -> None:
    claim_a = _claim(
        subject_type=IdentifierSubjectType.SECURITY,
        subject_id=SECURITY_A_ID,
        identifier_type=ExternalIdentifierType.FIGI_SHARE_CLASS,
        value="BBG00TESTSC1",
    )
    claim_b = _claim(
        subject_type=IdentifierSubjectType.SECURITY,
        subject_id=SECURITY_B_ID,
        identifier_type=ExternalIdentifierType.FIGI_SHARE_CLASS,
        value="BBG00TESTSC2",
        observation_id=UUID("11111111-1111-4111-8111-111111111112"),
    )
    catalog = IdentityCatalog(
        securities=(
            _security(SECURITY_A_ID, "Class A", claim_a),
            _security(SECURITY_B_ID, "Class B", claim_b),
        )
    )

    first = catalog.resolve_identifier(
        IdentifierResolutionRequest(
            subject_type=IdentifierSubjectType.SECURITY,
            identifier_type=ExternalIdentifierType.FIGI_SHARE_CLASS,
            value="BBG00TESTSC1",
        )
    )
    second = catalog.resolve_identifier(
        IdentifierResolutionRequest(
            subject_type=IdentifierSubjectType.SECURITY,
            identifier_type=ExternalIdentifierType.FIGI_SHARE_CLASS,
            value="BBG00TESTSC2",
        )
    )
    assert first.subject_id == SECURITY_A_ID
    assert second.subject_id == SECURITY_B_ID


def test_identifier_request_enforces_composite_market_scope() -> None:
    with pytest.raises(ValidationError, match="require market_scope"):
        IdentifierResolutionRequest(
            subject_type=IdentifierSubjectType.SECURITY,
            identifier_type=ExternalIdentifierType.FIGI_COMPOSITE,
            value="BBG00TESTCO1",
        )
    with pytest.raises(ValidationError, match="only valid"):
        IdentifierResolutionRequest(
            subject_type=IdentifierSubjectType.SECURITY,
            identifier_type=ExternalIdentifierType.FIGI_SHARE_CLASS,
            value="BBG00TESTSC1",
            market_scope="US",
        )
    with pytest.raises(ValidationError, match="cannot resolve security"):
        IdentifierResolutionRequest(
            subject_type=IdentifierSubjectType.SECURITY,
            identifier_type=ExternalIdentifierType.SEC_CIK,
            value="1234567",
        )


def test_openfigi_mapping_preserves_identifier_levels_and_requires_composite_scope() -> None:
    candidate = parse_openfigi_mapping_response(
        (FIXTURES / "openfigi_mapping.json").read_bytes()
    )[0]
    evidence = _evidence()

    unscoped = openfigi_identifier_claims(
        candidate,
        security_id=SECURITY_A_ID,
        listing_id=LISTING_NEW_ID,
        evidence=evidence,
    )
    assert [(item.identifier_type, item.subject_type) for item in unscoped] == [
        (ExternalIdentifierType.FIGI_INSTRUMENT, IdentifierSubjectType.LISTING),
        (ExternalIdentifierType.FIGI_SHARE_CLASS, IdentifierSubjectType.SECURITY),
    ]

    scoped = openfigi_identifier_claims(
        candidate,
        security_id=SECURITY_A_ID,
        listing_id=LISTING_NEW_ID,
        evidence=evidence,
        composite_market_scope="US",
    )
    composite = scoped[-1]
    assert composite.identifier_type is ExternalIdentifierType.FIGI_COMPOSITE
    assert composite.subject_type is IdentifierSubjectType.SECURITY
    assert composite.market_scope == "US"


def test_openfigi_warning_is_no_result_but_error_is_unavailable() -> None:
    assert parse_openfigi_mapping_response(b'[{"warning":"No identifier found."}]') == ()
    with pytest.raises(OpenFigiResponseError, match="unexpected provider failure"):
        parse_openfigi_mapping_response(b'[{"error":"unexpected provider failure"}]')


def test_gleif_exact_lei_enriches_entity_but_fuzzy_results_remain_candidates() -> None:
    exact = parse_gleif_response(
        (FIXTURES / "gleif_exact.json").read_bytes(),
        match_kind=GleifMatchKind.EXACT_LEI,
        expected_lei="529900SYNTHETIC00001",
    )[0]
    claim = gleif_lei_claim(exact, entity_id=ISSUER_ID, evidence=_evidence())
    assert claim.subject_type is IdentifierSubjectType.ENTITY
    assert claim.identifier_type is ExternalIdentifierType.LEI

    fuzzy = parse_gleif_response(
        (FIXTURES / "gleif_candidates.json").read_bytes(),
        match_kind=GleifMatchKind.NAME_CANDIDATE,
    )
    assert [item.lei for item in fuzzy] == [
        "529900SYNTHETIC00001",
        "529900SYNTHETIC00002",
    ]
    with pytest.raises(ValueError, match="cannot canonicalize"):
        gleif_lei_claim(fuzzy[0], entity_id=ISSUER_ID, evidence=_evidence())
    with pytest.raises(ValueError, match="different LEI"):
        parse_gleif_response(
            (FIXTURES / "gleif_exact.json").read_bytes(),
            match_kind=GleifMatchKind.EXACT_LEI,
            expected_lei="529900SYNTHETIC00002",
        )


def test_optional_enrichment_failure_and_no_result_preserve_existing_records() -> None:
    existing = (_entity(ISSUER_ID, "Existing Issuer"),)

    def unavailable() -> tuple[Entity, ...]:
        raise EnrichmentUnavailable("provider offline")

    failed = attempt_optional_enrichment(existing, unavailable)
    empty = attempt_optional_enrichment(existing, lambda: ())

    assert failed.status is EnrichmentStatus.UNAVAILABLE
    assert failed.records == existing
    assert empty.status is EnrichmentStatus.NO_RESULT
    assert empty.records == existing


def test_catalog_rejects_same_canonical_id_with_different_payload() -> None:
    first = _entity(ISSUER_ID, "First Name")
    second = _entity(ISSUER_ID, "Different Name")
    with pytest.raises(ValueError, match="conflicting duplicate canonical ID"):
        IdentityCatalog(entities=(first, second))


def _entity(
    entity_id: UUID,
    name: str,
    claim: ExternalIdentifier | None = None,
) -> Entity:
    return Entity(
        entity_id=entity_id,
        entity_type=EntityType.ISSUER,
        display_name=name,
        external_identifiers=(claim,) if claim is not None else (),
        provenance_id=PROVENANCE_ID,
    )


def _security(
    security_id: UUID,
    share_class: str,
    claim: ExternalIdentifier,
) -> Security:
    return Security(
        security_id=security_id,
        issuer_entity_id=ISSUER_ID,
        security_type=SecurityType.COMMON_STOCK,
        display_name=f"Synthetic Issuer {share_class}",
        share_class=share_class,
        external_identifiers=(claim,),
        provenance_id=PROVENANCE_ID,
    )


def _claim(
    *,
    subject_type: IdentifierSubjectType,
    subject_id: UUID,
    identifier_type: ExternalIdentifierType,
    value: str,
    observation_id: UUID = OBSERVATION_ID,
    known_from: TemporalValue | None = None,
) -> ExternalIdentifier:
    known = known_from or day_value(date(2020, 1, 1))
    return ExternalIdentifier(
        external_identifier_id=deterministic_external_identifier_id(
            subject_type=subject_type,
            subject_id=subject_id,
            identifier_type=identifier_type,
            value=value,
            source_observation_id=observation_id,
        ),
        subject_type=subject_type,
        subject_id=subject_id,
        identifier_type=identifier_type,
        value=value,
        source_observation_id=observation_id,
        provenance_id=PROVENANCE_ID,
        valid_from=day_value(date(2019, 1, 1)),
        known_from=known,
        observed_at=OBSERVED_AT,
    )


def _evidence() -> ClaimEvidence:
    return ClaimEvidence(
        source_observation_id=OBSERVATION_ID,
        provenance_id=PROVENANCE_ID,
        known_from=day_value(date(2020, 1, 1)),
        observed_at=OBSERVED_AT,
    )
