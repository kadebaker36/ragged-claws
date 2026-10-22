"""Fixture-first OpenFIGI/GLEIF enrichment boundaries with non-destructive failure."""

import json
from collections.abc import Callable
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel

from ragged_claws.models import (
    ExternalIdentifier,
    ExternalIdentifierType,
    IdentifierSubjectType,
    TemporalValue,
)
from ragged_claws.models.base import CanonicalModel, NonEmptyStr, UtcDatetime
from ragged_claws.resolution.ids import (
    deterministic_external_identifier_id,
    normalize_external_identifier,
)


class EnrichmentUnavailable(RuntimeError):
    """Expected provider/network failure that must not destroy canonical state."""


class OpenFigiResponseError(EnrichmentUnavailable):
    """OpenFIGI returned an explicit job error rather than a valid no-result warning."""


class EnrichmentStatus(StrEnum):
    APPLIED = "applied"
    NO_RESULT = "no_result"
    UNAVAILABLE = "unavailable"


class EnrichmentAttempt[AttemptRecordT: BaseModel](CanonicalModel):
    status: EnrichmentStatus
    records: tuple[AttemptRecordT, ...]
    message: NonEmptyStr | None = None


class ClaimEvidence(CanonicalModel):
    source_observation_id: UUID
    provenance_id: UUID
    known_from: TemporalValue | None = None
    observed_at: UtcDatetime
    valid_from: TemporalValue | None = None
    valid_to: TemporalValue | None = None


class OpenFigiCandidate(CanonicalModel):
    instrument_figi: NonEmptyStr
    share_class_figi: NonEmptyStr | None = None
    composite_figi: NonEmptyStr | None = None
    ticker: NonEmptyStr | None = None
    exchange_code: NonEmptyStr | None = None


class GleifMatchKind(StrEnum):
    EXACT_LEI = "exact_lei"
    NAME_CANDIDATE = "name_candidate"


class GleifCandidate(CanonicalModel):
    lei: NonEmptyStr
    legal_name: NonEmptyStr
    match_kind: GleifMatchKind


def parse_openfigi_mapping_response(payload: bytes) -> tuple[OpenFigiCandidate, ...]:
    """Parse one invented/recorded v3 mapping response without resolving identity."""
    document = json.loads(payload)
    if not isinstance(document, list) or len(document) != 1:
        raise ValueError("OpenFIGI mapping response must contain exactly one job result")
    job = document[0]
    if not isinstance(job, dict):
        raise ValueError("OpenFIGI job result must be an object")
    data = job.get("data")
    if data is None:
        if "warning" in job:
            return ()
        if "error" in job:
            raise OpenFigiResponseError(str(job["error"]))
        raise ValueError("OpenFIGI job result has no data, warning, or error")
    if not isinstance(data, list):
        raise ValueError("OpenFIGI data must be an array")
    candidates: list[OpenFigiCandidate] = []
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get("figi"), str):
            raise ValueError("OpenFIGI result requires an instrument figi")
        candidates.append(
            OpenFigiCandidate(
                instrument_figi=item["figi"],
                share_class_figi=_optional_string(item.get("shareClassFIGI")),
                composite_figi=_optional_string(item.get("compositeFIGI")),
                ticker=_optional_string(item.get("ticker")),
                exchange_code=_optional_string(item.get("exchCode")),
            )
        )
    return tuple(sorted(candidates, key=lambda item: item.instrument_figi))


def openfigi_identifier_claims(
    candidate: OpenFigiCandidate,
    *,
    security_id: UUID,
    listing_id: UUID,
    evidence: ClaimEvidence,
    composite_market_scope: str | None = None,
) -> tuple[ExternalIdentifier, ...]:
    """Map each OpenFIGI identifier to its correct canonical identity layer.

    Composite FIGI is omitted unless the caller has defensible explicit market scope.
    """
    specifications: list[
        tuple[IdentifierSubjectType, UUID, ExternalIdentifierType, str, str | None]
    ] = [
        (
            IdentifierSubjectType.LISTING,
            listing_id,
            ExternalIdentifierType.FIGI_INSTRUMENT,
            candidate.instrument_figi,
            None,
        )
    ]
    if candidate.share_class_figi is not None:
        specifications.append(
            (
                IdentifierSubjectType.SECURITY,
                security_id,
                ExternalIdentifierType.FIGI_SHARE_CLASS,
                candidate.share_class_figi,
                None,
            )
        )
    if candidate.composite_figi is not None and composite_market_scope is not None:
        specifications.append(
            (
                IdentifierSubjectType.SECURITY,
                security_id,
                ExternalIdentifierType.FIGI_COMPOSITE,
                candidate.composite_figi,
                composite_market_scope,
            )
        )
    return tuple(
        _claim(
            subject_type=subject_type,
            subject_id=subject_id,
            identifier_type=identifier_type,
            value=value,
            evidence=evidence,
            market_scope=market_scope,
        )
        for subject_type, subject_id, identifier_type, value, market_scope in specifications
    )


def parse_gleif_response(
    payload: bytes,
    *,
    match_kind: GleifMatchKind,
    expected_lei: str | None = None,
) -> tuple[GleifCandidate, ...]:
    """Parse GLEIF JSON:API results as exact identifiers or non-binding name candidates."""
    document = json.loads(payload)
    data = document.get("data") if isinstance(document, dict) else None
    if not isinstance(data, list):
        raise ValueError("GLEIF response data must be an array")
    if match_kind is GleifMatchKind.EXACT_LEI:
        if expected_lei is None:
            raise ValueError("exact GLEIF lookup requires expected_lei")
        normalized_expected = normalize_external_identifier(
            ExternalIdentifierType.LEI, expected_lei
        )
    elif expected_lei is not None:
        raise ValueError("expected_lei is only valid for exact GLEIF lookup")
    else:
        normalized_expected = None
    candidates: list[GleifCandidate] = []
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("GLEIF result requires an LEI id")
        attributes = item.get("attributes")
        entity = attributes.get("entity") if isinstance(attributes, dict) else None
        legal_name = entity.get("legalName") if isinstance(entity, dict) else None
        name = legal_name.get("name") if isinstance(legal_name, dict) else None
        if not isinstance(name, str):
            raise ValueError("GLEIF result requires an entity legal name")
        normalized_lei = normalize_external_identifier(ExternalIdentifierType.LEI, item["id"])
        if normalized_expected is not None and normalized_lei != normalized_expected:
            raise ValueError("GLEIF exact lookup returned a different LEI")
        candidates.append(
            GleifCandidate(lei=normalized_lei, legal_name=name, match_kind=match_kind)
        )
    if match_kind is GleifMatchKind.EXACT_LEI and len(candidates) > 1:
        raise ValueError("GLEIF exact lookup returned multiple records")
    return tuple(sorted(candidates, key=lambda item: item.lei))


def gleif_lei_claim(
    candidate: GleifCandidate,
    *,
    entity_id: UUID,
    evidence: ClaimEvidence,
) -> ExternalIdentifier:
    """Create an Entity-level LEI claim only from an exact LEI lookup."""
    if candidate.match_kind is not GleifMatchKind.EXACT_LEI:
        raise ValueError("fuzzy/name GLEIF candidates cannot canonicalize an Entity")
    return _claim(
        subject_type=IdentifierSubjectType.ENTITY,
        subject_id=entity_id,
        identifier_type=ExternalIdentifierType.LEI,
        value=candidate.lei,
        evidence=evidence,
    )


def attempt_optional_enrichment[AttemptRecordT: BaseModel](
    existing: tuple[AttemptRecordT, ...],
    operation: Callable[[], tuple[AttemptRecordT, ...]],
) -> EnrichmentAttempt[AttemptRecordT]:
    """Apply optional enrichment while preserving existing records on expected failure."""
    try:
        additions = operation()
    except EnrichmentUnavailable as exc:
        return EnrichmentAttempt(
            status=EnrichmentStatus.UNAVAILABLE,
            records=existing,
            message=str(exc) or "enrichment unavailable",
        )
    if not additions:
        return EnrichmentAttempt(status=EnrichmentStatus.NO_RESULT, records=existing)
    return EnrichmentAttempt(status=EnrichmentStatus.APPLIED, records=(*existing, *additions))


def _claim(
    *,
    subject_type: IdentifierSubjectType,
    subject_id: UUID,
    identifier_type: ExternalIdentifierType,
    value: str,
    evidence: ClaimEvidence,
    market_scope: str | None = None,
) -> ExternalIdentifier:
    normalized = normalize_external_identifier(identifier_type, value)
    normalized_scope = market_scope.strip().upper() if market_scope is not None else None
    return ExternalIdentifier(
        external_identifier_id=deterministic_external_identifier_id(
            subject_type=subject_type,
            subject_id=subject_id,
            identifier_type=identifier_type,
            value=normalized,
            source_observation_id=evidence.source_observation_id,
            market_scope=normalized_scope,
        ),
        subject_type=subject_type,
        subject_id=subject_id,
        identifier_type=identifier_type,
        value=normalized,
        market_scope=normalized_scope,
        source_observation_id=evidence.source_observation_id,
        provenance_id=evidence.provenance_id,
        valid_from=evidence.valid_from,
        valid_to=evidence.valid_to,
        known_from=evidence.known_from,
        observed_at=evidence.observed_at,
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
