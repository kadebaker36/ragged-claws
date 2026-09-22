"""Explainable exact-identifier and historical-listing resolution."""

from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import datetime
from uuid import UUID

from ragged_claws.models import (
    Entity,
    ExternalIdentifier,
    IdentifierSubjectType,
    Listing,
    Security,
    TemporalPrecision,
    TemporalValue,
)
from ragged_claws.resolution.ids import normalize_external_identifier
from ragged_claws.resolution.models import (
    HistoricalListingRequest,
    IdentifierResolutionRequest,
    ResolutionConfidence,
    ResolutionMethod,
    ResolutionReason,
    ResolutionResult,
    ResolutionStatus,
)
from ragged_claws.temporal import evaluate_eligibility


class IdentityCatalog:
    """An immutable-in-use in-memory index over canonical identity records."""

    def __init__(
        self,
        *,
        entities: tuple[Entity, ...] = (),
        securities: tuple[Security, ...] = (),
        listings: tuple[Listing, ...] = (),
        external_identifiers: tuple[ExternalIdentifier, ...] = (),
    ) -> None:
        self.entities = _unique_records(entities, lambda item: item.entity_id)
        self.securities = _unique_records(securities, lambda item: item.security_id)
        self.listings = _unique_records(listings, lambda item: item.listing_id)
        nested_list: list[ExternalIdentifier] = []
        for entity in entities:
            nested_list.extend(entity.external_identifiers)
        for security in securities:
            nested_list.extend(security.external_identifiers)
        for listing in listings:
            nested_list.extend(listing.external_identifiers)
        nested = tuple(nested_list)
        claims = (*external_identifiers, *nested)
        self.external_identifiers = _unique_records(
            claims, lambda item: item.external_identifier_id
        )
        self._identifier_index: dict[
            tuple[IdentifierSubjectType, str, str, str], list[ExternalIdentifier]
        ] = defaultdict(list)
        for claim in self.external_identifiers.values():
            normalized = normalize_external_identifier(claim.identifier_type, claim.value)
            scope = claim.market_scope.upper() if claim.market_scope is not None else ""
            key = (claim.subject_type, claim.identifier_type.value, normalized, scope)
            self._identifier_index[key].append(claim)

    def resolve_identifier(self, request: IdentifierResolutionRequest) -> ResolutionResult:
        normalized = normalize_external_identifier(request.identifier_type, request.value)
        scope = request.market_scope.upper() if request.market_scope is not None else ""
        key = (request.subject_type, request.identifier_type.value, normalized, scope)
        claims = tuple(self._identifier_index.get(key, ()))
        if request.known_at is not None:
            claims = tuple(claim for claim in claims if _known_at(claim, request.known_at))
        claimed_subject_ids = tuple(sorted({claim.subject_id for claim in claims}, key=str))
        if not claimed_subject_ids:
            reason = (
                ResolutionReason.NOT_KNOWN_AT_TIME
                if self._identifier_index.get(key) and request.known_at is not None
                else ResolutionReason.NO_MATCH
            )
            return _empty_result(request.subject_type, reason)
        if len(claimed_subject_ids) > 1:
            claim_ids, observation_ids, provenance_ids = _evidence_fields(claims)
            return ResolutionResult(
                status=ResolutionStatus.CONFLICT,
                subject_type=request.subject_type,
                method=ResolutionMethod.EXACT_IDENTIFIER,
                reason=ResolutionReason.IDENTIFIER_CONFLICT,
                candidate_ids=claimed_subject_ids,
                supporting_external_identifier_ids=claim_ids,
                source_observation_ids=observation_ids,
                provenance_ids=provenance_ids,
            )
        subject_id = claimed_subject_ids[0]
        if not self._has_subject(request.subject_type, subject_id):
            return _empty_result(request.subject_type, ResolutionReason.NO_MATCH)
        subject_claims = tuple(claim for claim in claims if claim.subject_id == subject_id)
        return _resolved_from_claims(
            subject_type=request.subject_type,
            subject_id=subject_id,
            method=ResolutionMethod.EXACT_IDENTIFIER,
            reason=ResolutionReason.EXACT_TYPED_IDENTIFIER,
            claims=subject_claims,
        )

    def _has_subject(self, subject_type: IdentifierSubjectType, subject_id: UUID) -> bool:
        if subject_type is IdentifierSubjectType.ENTITY:
            return subject_id in self.entities
        if subject_type is IdentifierSubjectType.SECURITY:
            return subject_id in self.securities
        return subject_id in self.listings

    def resolve_listing(self, request: HistoricalListingRequest) -> ResolutionResult:
        if request.security_id not in self.securities:
            return _empty_result(
                IdentifierSubjectType.LISTING,
                ResolutionReason.NO_MATCH,
                method=ResolutionMethod.HISTORICAL_LISTING,
            )
        matching = tuple(
            listing
            for listing in self.listings.values()
            if listing.security_id == request.security_id
            and listing.exchange_mic == request.exchange_mic
            and listing.symbol == request.symbol
        )
        certain: list[Listing] = []
        uncertain: list[Listing] = []
        for listing in matching:
            validity = _contains(listing, request.as_of)
            if validity is None:
                uncertain.append(listing)
            elif validity:
                certain.append(listing)
        if request.known_at is not None:
            known = [
                listing
                for listing in certain
                if any(_known_at(claim, request.known_at) for claim in listing.external_identifiers)
            ]
            if certain and not known:
                return _empty_result(
                    IdentifierSubjectType.LISTING,
                    ResolutionReason.NOT_KNOWN_AT_TIME,
                    method=ResolutionMethod.HISTORICAL_LISTING,
                )
            certain = known
        if len(certain) == 1 and not uncertain:
            listing = certain[0]
            return _resolved_from_claims(
                subject_type=IdentifierSubjectType.LISTING,
                subject_id=listing.listing_id,
                method=ResolutionMethod.HISTORICAL_LISTING,
                reason=ResolutionReason.UNIQUE_VALID_LISTING,
                claims=listing.external_identifiers,
                valid_from=listing.effective_from,
                valid_to=listing.effective_to,
            )
        candidates = tuple(
            sorted({listing.listing_id for listing in (*certain, *uncertain)}, key=str)
        )
        if len(candidates) > 1:
            claim_ids, observation_ids, provenance_ids = _evidence_fields(
                tuple(
                    claim
                    for listing in (*certain, *uncertain)
                    for claim in listing.external_identifiers
                )
            )
            return ResolutionResult(
                status=ResolutionStatus.AMBIGUOUS,
                subject_type=IdentifierSubjectType.LISTING,
                method=ResolutionMethod.HISTORICAL_LISTING,
                reason=(
                    ResolutionReason.COARSE_VALIDITY
                    if uncertain
                    else ResolutionReason.MULTIPLE_MATCHES
                ),
                candidate_ids=candidates,
                supporting_external_identifier_ids=claim_ids,
                source_observation_ids=observation_ids,
                provenance_ids=provenance_ids,
            )
        if uncertain:
            listing = uncertain[0]
            claim_ids, observation_ids, provenance_ids = _evidence_fields(
                listing.external_identifiers
            )
            return ResolutionResult(
                status=ResolutionStatus.UNRESOLVED,
                subject_type=IdentifierSubjectType.LISTING,
                method=ResolutionMethod.HISTORICAL_LISTING,
                reason=ResolutionReason.COARSE_VALIDITY,
                candidate_ids=(listing.listing_id,),
                supporting_external_identifier_ids=claim_ids,
                source_observation_ids=observation_ids,
                provenance_ids=provenance_ids,
            )
        return _empty_result(
            IdentifierSubjectType.LISTING,
            ResolutionReason.NO_MATCH,
            method=ResolutionMethod.HISTORICAL_LISTING,
        )


def _contains(listing: Listing, as_of: TemporalValue) -> bool | None:
    lower = _compare(as_of, listing.effective_from) if listing.effective_from else 1
    upper = _compare(as_of, listing.effective_to) if listing.effective_to else -1
    if lower is None or upper is None:
        return None
    return lower >= 0 and upper < 0


def _compare(left: TemporalValue, right: TemporalValue) -> int | None:
    if left.precision is TemporalPrecision.DAY and right.precision is TemporalPrecision.DAY:
        left_date = left.partial_date
        right_date = right.partial_date
        if left_date is None or right_date is None:
            return None
        left_key = (left_date.year, left_date.month, left_date.day)
        right_key = (right_date.year, right_date.month, right_date.day)
        return (left_key > right_key) - (left_key < right_key)
    timestamp_precisions = {TemporalPrecision.MINUTE, TemporalPrecision.SECOND}
    if left.precision in timestamp_precisions and right.precision in timestamp_precisions:
        if left.timestamp is None or right.timestamp is None:
            return None
        return (left.timestamp > right.timestamp) - (left.timestamp < right.timestamp)
    return None


def _known_at(claim: ExternalIdentifier, known_at: datetime) -> bool:
    return evaluate_eligibility(
        snapshot_at=known_at,
        known_from=claim.known_from,
        observed_at=claim.observed_at,
    ).eligible


def _resolved_from_claims(
    *,
    subject_type: IdentifierSubjectType,
    subject_id: UUID,
    method: ResolutionMethod,
    reason: ResolutionReason,
    claims: tuple[ExternalIdentifier, ...],
    valid_from: TemporalValue | None = None,
    valid_to: TemporalValue | None = None,
) -> ResolutionResult:
    ordered = tuple(sorted(claims, key=lambda claim: str(claim.external_identifier_id)))
    known_values = [claim.known_from for claim in ordered if claim.known_from is not None]
    observed_values = [claim.observed_at for claim in ordered]
    return ResolutionResult(
        status=ResolutionStatus.RESOLVED,
        subject_type=subject_type,
        subject_id=subject_id,
        method=method,
        reason=reason,
        confidence=ResolutionConfidence.EXACT,
        supporting_external_identifier_ids=tuple(
            claim.external_identifier_id for claim in ordered
        ),
        source_observation_ids=tuple(
            sorted({claim.source_observation_id for claim in ordered}, key=str)
        ),
        provenance_ids=tuple(sorted({claim.provenance_id for claim in ordered}, key=str)),
        valid_from=valid_from,
        valid_to=valid_to,
        known_from=known_values[0] if len(set(known_values)) == 1 else None,
        observed_at=min(observed_values) if observed_values else None,
    )


def _evidence_fields(
    claims: tuple[ExternalIdentifier, ...],
) -> tuple[tuple[UUID, ...], tuple[UUID, ...], tuple[UUID, ...]]:
    return (
        tuple(
            sorted({claim.external_identifier_id for claim in claims}, key=str)
        ),
        tuple(
            sorted({claim.source_observation_id for claim in claims}, key=str)
        ),
        tuple(sorted({claim.provenance_id for claim in claims}, key=str)),
    )


def _empty_result(
    subject_type: IdentifierSubjectType,
    reason: ResolutionReason,
    *,
    method: ResolutionMethod = ResolutionMethod.NONE,
) -> ResolutionResult:
    return ResolutionResult(
        status=ResolutionStatus.UNRESOLVED,
        subject_type=subject_type,
        method=method,
        reason=reason,
    )


def _unique_records[RecordT](
    records: Iterable[RecordT], id_getter: Callable[[RecordT], UUID]
) -> dict[UUID, RecordT]:
    unique: dict[UUID, RecordT] = {}
    for record in records:
        record_id = id_getter(record)
        existing = unique.get(record_id)
        if existing is not None and existing != record:
            raise ValueError(f"conflicting duplicate canonical ID: {record_id}")
        unique[record_id] = record
    return unique
