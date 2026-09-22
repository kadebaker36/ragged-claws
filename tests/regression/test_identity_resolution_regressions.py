"""Regressions against ticker history, reuse, ambiguity, and PIT leakage."""

from datetime import UTC, date, datetime
from uuid import UUID

from ragged_claws.models import (
    ExternalIdentifier,
    ExternalIdentifierType,
    IdentifierSubjectType,
    Listing,
    PartialDate,
    Security,
    SecurityType,
    TemporalPrecision,
    TemporalValue,
)
from ragged_claws.resolution import (
    HistoricalListingRequest,
    IdentityCatalog,
    ResolutionReason,
    ResolutionStatus,
    day_value,
    deterministic_external_identifier_id,
)

ISSUER_A = UUID("10000000-0000-4000-8000-000000000001")
ISSUER_B = UUID("10000000-0000-4000-8000-000000000002")
SECURITY_A = UUID("20000000-0000-4000-8000-000000000001")
SECURITY_B = UUID("20000000-0000-4000-8000-000000000002")
LISTING_OLD = UUID("30000000-0000-4000-8000-000000000001")
LISTING_NEW = UUID("30000000-0000-4000-8000-000000000002")
LISTING_REUSE = UUID("30000000-0000-4000-8000-000000000003")
PROVENANCE = UUID("40000000-0000-4000-8000-000000000001")
OBSERVED = datetime(2024, 1, 2, tzinfo=UTC)


def test_ticker_change_uses_half_open_historical_intervals() -> None:
    catalog = _catalog(
        _listing(
            LISTING_OLD,
            SECURITY_A,
            "OLD",
            from_date=date(2018, 1, 1),
            to_date=date(2021, 1, 1),
            figi="BBG000OLD001",
        ),
        _listing(
            LISTING_NEW,
            SECURITY_A,
            "NEW",
            from_date=date(2021, 1, 1),
            to_date=None,
            figi="BBG000NEW001",
        ),
    )

    old = catalog.resolve_listing(_request(SECURITY_A, "OLD", date(2020, 12, 31)))
    old_at_end = catalog.resolve_listing(_request(SECURITY_A, "OLD", date(2021, 1, 1)))
    new_at_start = catalog.resolve_listing(_request(SECURITY_A, "NEW", date(2021, 1, 1)))

    assert old.subject_id == LISTING_OLD
    assert old_at_end.status is ResolutionStatus.UNRESOLVED
    assert new_at_start.subject_id == LISTING_NEW


def test_same_ticker_reuse_never_merges_distinct_securities() -> None:
    first = _listing(
        LISTING_OLD,
        SECURITY_A,
        "REUSE",
        from_date=date(2018, 1, 1),
        to_date=date(2020, 1, 1),
        figi="BBG00REUSE01",
    )
    second = _listing(
        LISTING_REUSE,
        SECURITY_B,
        "REUSE",
        from_date=date(2022, 1, 1),
        to_date=None,
        figi="BBG00REUSE02",
    )
    catalog = _catalog(first, second)

    historical = catalog.resolve_listing(_request(SECURITY_A, "REUSE", date(2019, 6, 1)))
    later = catalog.resolve_listing(_request(SECURITY_B, "REUSE", date(2023, 6, 1)))
    wrong_security = catalog.resolve_listing(_request(SECURITY_A, "REUSE", date(2023, 6, 1)))

    assert historical.subject_id == LISTING_OLD
    assert later.subject_id == LISTING_REUSE
    assert wrong_security.status is ResolutionStatus.UNRESOLVED


def test_overlapping_listing_evidence_is_ambiguous_independent_of_input_order() -> None:
    first = _listing(
        LISTING_OLD,
        SECURITY_A,
        "DUP",
        from_date=date(2020, 1, 1),
        to_date=None,
        figi="BBG000DUP001",
    )
    second = _listing(
        LISTING_NEW,
        SECURITY_A,
        "DUP",
        from_date=date(2020, 1, 1),
        to_date=None,
        figi="BBG000DUP002",
    )
    request = _request(SECURITY_A, "DUP", date(2021, 1, 1))

    forward = _catalog(first, second).resolve_listing(request)
    reverse = _catalog(second, first).resolve_listing(request)

    assert forward == reverse
    assert forward.status is ResolutionStatus.AMBIGUOUS
    assert forward.reason is ResolutionReason.MULTIPLE_MATCHES
    assert set(forward.candidate_ids) == {LISTING_OLD, LISTING_NEW}


def test_coarse_or_mixed_listing_boundaries_fail_closed() -> None:
    coarse_start = TemporalValue(
        raw_value="2020-01",
        precision=TemporalPrecision.MONTH,
        partial_date=_month_value(2020, 1),
    )
    listing = _listing(
        LISTING_OLD,
        SECURITY_A,
        "COARSE",
        from_date=None,
        to_date=None,
        figi="BBG0COARSE01",
    ).model_copy(update={"effective_from": coarse_start})

    result = _catalog(listing).resolve_listing(
        _request(SECURITY_A, "COARSE", date(2020, 1, 15))
    )

    assert result.status is ResolutionStatus.UNRESOLVED
    assert result.reason is ResolutionReason.COARSE_VALIDITY
    assert result.candidate_ids == (LISTING_OLD,)
    assert result.source_observation_ids


def test_later_discovered_mapping_does_not_leak_into_historical_resolution() -> None:
    known_in_2024 = day_value(date(2024, 1, 1))
    listing = _listing(
        LISTING_OLD,
        SECURITY_A,
        "PIT",
        from_date=date(2020, 1, 1),
        to_date=None,
        figi="BBG000PIT001",
        known_from=known_in_2024,
    )
    catalog = _catalog(listing)
    request = _request(SECURITY_A, "PIT", date(2021, 1, 1))

    retrospective = catalog.resolve_listing(request)
    point_in_time = catalog.resolve_listing(
        request.model_copy(update={"known_at": datetime(2021, 1, 1, tzinfo=UTC)})
    )

    assert retrospective.status is ResolutionStatus.RESOLVED
    assert retrospective.known_from == known_in_2024
    assert retrospective.observed_at == OBSERVED
    assert point_in_time.status is ResolutionStatus.UNRESOLVED
    assert point_in_time.reason is ResolutionReason.NOT_KNOWN_AT_TIME


def _catalog(*listings: Listing) -> IdentityCatalog:
    securities = (
        Security(
            security_id=SECURITY_A,
            issuer_entity_id=ISSUER_A,
            security_type=SecurityType.COMMON_STOCK,
            display_name="Synthetic A",
            provenance_id=PROVENANCE,
        ),
        Security(
            security_id=SECURITY_B,
            issuer_entity_id=ISSUER_B,
            security_type=SecurityType.COMMON_STOCK,
            display_name="Synthetic B",
            provenance_id=PROVENANCE,
        ),
    )
    return IdentityCatalog(securities=securities, listings=tuple(listings))


def _listing(
    listing_id: UUID,
    security_id: UUID,
    symbol: str,
    *,
    from_date: date | None,
    to_date: date | None,
    figi: str,
    known_from: TemporalValue | None = None,
) -> Listing:
    observation_id = UUID(int=listing_id.int + 0x10000000000000000000000000000000)
    claim = ExternalIdentifier(
        external_identifier_id=deterministic_external_identifier_id(
            subject_type=IdentifierSubjectType.LISTING,
            subject_id=listing_id,
            identifier_type=ExternalIdentifierType.FIGI_INSTRUMENT,
            value=figi,
            source_observation_id=observation_id,
        ),
        subject_type=IdentifierSubjectType.LISTING,
        subject_id=listing_id,
        identifier_type=ExternalIdentifierType.FIGI_INSTRUMENT,
        value=figi,
        source_observation_id=observation_id,
        provenance_id=PROVENANCE,
        known_from=known_from or day_value(date(2017, 1, 1)),
        observed_at=OBSERVED,
    )
    return Listing(
        listing_id=listing_id,
        security_id=security_id,
        symbol=symbol,
        exchange_mic="XNYS",
        effective_from=day_value(from_date) if from_date is not None else None,
        effective_to=day_value(to_date) if to_date is not None else None,
        external_identifiers=(claim,),
        provenance_id=PROVENANCE,
    )


def _request(security_id: UUID, symbol: str, as_of: date) -> HistoricalListingRequest:
    return HistoricalListingRequest(
        security_id=security_id,
        exchange_mic="XNYS",
        symbol=symbol,
        as_of=day_value(as_of),
    )


def _month_value(year: int, month: int) -> PartialDate:
    return PartialDate(
        raw_value=f"{year:04d}-{month:02d}",
        precision=TemporalPrecision.MONTH,
        year=year,
        month=month,
    )
