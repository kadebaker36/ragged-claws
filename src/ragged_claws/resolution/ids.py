"""Deterministic identity rules that use only strong, typed identifiers."""

import re
from uuid import UUID, uuid5

from ragged_claws.models import ExternalIdentifierType, IdentifierSubjectType

ENTITY_FROM_CIK_NAMESPACE = UUID("6763f0c3-47fd-5b77-b98d-0eb4cd614c48")
SECURITY_FROM_IDENTIFIER_NAMESPACE = UUID("8fc09b2d-e09e-5e2b-a9bf-b2d87d44b74c")
LISTING_FROM_FIGI_NAMESPACE = UUID("1d0c8bb1-4968-5f63-b9b8-f9169588c86d")
EXTERNAL_IDENTIFIER_NAMESPACE = UUID("302cadd4-82cb-54c2-9a65-58cf0aa6af3e")

_ALPHANUMERIC_PATTERNS: dict[ExternalIdentifierType, re.Pattern[str]] = {
    ExternalIdentifierType.LEI: re.compile(r"^[A-Z0-9]{20}$"),
    ExternalIdentifierType.FIGI_INSTRUMENT: re.compile(r"^[A-Z0-9]{12}$"),
    ExternalIdentifierType.FIGI_SHARE_CLASS: re.compile(r"^[A-Z0-9]{12}$"),
    ExternalIdentifierType.FIGI_COMPOSITE: re.compile(r"^[A-Z0-9]{12}$"),
    ExternalIdentifierType.ISIN: re.compile(r"^[A-Z0-9]{12}$"),
    ExternalIdentifierType.CUSIP: re.compile(r"^[A-Z0-9]{9}$"),
    ExternalIdentifierType.SEDOL: re.compile(r"^[A-Z0-9]{7}$"),
}


def normalize_cik(value: str) -> str:
    """Normalize an SEC CIK to its ten-digit representation without guessing."""
    candidate = value.strip()
    if not candidate.isascii() or not candidate.isdigit() or len(candidate) > 10:
        raise ValueError("SEC CIK must contain at most ten ASCII digits")
    normalized = candidate.zfill(10)
    if int(normalized) == 0:
        raise ValueError("SEC CIK must be non-zero")
    return normalized


def normalize_external_identifier(
    identifier_type: ExternalIdentifierType,
    value: str,
) -> str:
    """Return the conservative exact-match representation for a typed identifier."""
    if identifier_type is ExternalIdentifierType.SEC_CIK:
        return normalize_cik(value)
    candidate = value.strip().upper()
    pattern = _ALPHANUMERIC_PATTERNS.get(identifier_type)
    if pattern is None:
        if identifier_type is ExternalIdentifierType.OTHER:
            raise ValueError("OTHER identifiers require source-specific normalization")
        raise ValueError(f"unsupported identifier type: {identifier_type.value}")
    if pattern.fullmatch(candidate) is None:
        raise ValueError(f"invalid {identifier_type.value} representation")
    return candidate


def deterministic_entity_id_from_cik(cik: str) -> UUID:
    """Identify an issuer Entity from the immutable typed SEC CIK only."""
    return uuid5(ENTITY_FROM_CIK_NAMESPACE, f"sec_cik:{normalize_cik(cik)}")


def deterministic_security_id(
    identifier_type: ExternalIdentifierType,
    value: str,
    *,
    market_scope: str | None = None,
) -> UUID:
    """Identify a Security from a defensible security-level identifier."""
    allowed = {
        ExternalIdentifierType.FIGI_SHARE_CLASS,
        ExternalIdentifierType.FIGI_COMPOSITE,
        ExternalIdentifierType.ISIN,
        ExternalIdentifierType.CUSIP,
    }
    if identifier_type not in allowed:
        raise ValueError("identifier type cannot define Security identity")
    normalized = normalize_external_identifier(identifier_type, value)
    if identifier_type is ExternalIdentifierType.FIGI_COMPOSITE:
        if market_scope is None or not market_scope.strip():
            raise ValueError("composite FIGI identity requires explicit market_scope")
        scope = market_scope.strip().upper()
    elif market_scope is not None:
        raise ValueError("market_scope is only valid for composite FIGI identity")
    else:
        scope = ""
    return uuid5(
        SECURITY_FROM_IDENTIFIER_NAMESPACE,
        _encode(identifier_type.value, normalized, scope),
    )


def deterministic_listing_id_from_figi(figi: str) -> UUID:
    """Identify a venue-level Listing from an instrument FIGI only."""
    normalized = normalize_external_identifier(ExternalIdentifierType.FIGI_INSTRUMENT, figi)
    return uuid5(LISTING_FROM_FIGI_NAMESPACE, f"figi_instrument:{normalized}")


def deterministic_external_identifier_id(
    *,
    subject_type: IdentifierSubjectType,
    subject_id: UUID,
    identifier_type: ExternalIdentifierType,
    value: str,
    source_observation_id: UUID,
    market_scope: str | None = None,
) -> UUID:
    """Identify one source-backed typed identifier claim.

    Source observation is part of claim identity so independent evidence remains distinct.
    Mutable names, symbols, retrieval ordering, and response positions are excluded.
    """
    normalized = normalize_external_identifier(identifier_type, value)
    if identifier_type is ExternalIdentifierType.FIGI_COMPOSITE:
        if market_scope is None or not market_scope.strip():
            raise ValueError("composite FIGI claim identity requires market_scope")
        scope = market_scope.strip().upper()
    elif market_scope is not None:
        raise ValueError("market_scope is only valid for composite FIGI claim identity")
    else:
        scope = ""
    return uuid5(
        EXTERNAL_IDENTIFIER_NAMESPACE,
        _encode(
            subject_type.value,
            str(subject_id),
            identifier_type.value,
            normalized,
            scope,
            str(source_observation_id),
        ),
    )


def _encode(*components: str) -> str:
    return "".join(f"{len(component)}:{component}" for component in components)
