"""Recorded candidate evidence never turns a name/ticker or unknown interval into a binding."""

import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from ragged_claws.models import (
    Entity,
    Event,
    ExternalIdentifier,
    ExternalIdentifierType,
    IdentifierSubjectType,
    Listing,
    PartialDate,
    Security,
    SecurityType,
    SourceObservation,
    TemporalPrecision,
    TemporalValue,
)
from ragged_claws.research.build import build
from ragged_claws.research.examples import prepare_sec
from ragged_claws.research.identity_evidence import (
    HASHES,
    REVIEWED_AT,
    import_identity_evidence,
    prepare_identity_diagnostic,
)
from ragged_claws.research.models import ResearchRow
from ragged_claws.research.snapshot import ResearchError, digest, freeze, read_inputs
from ragged_claws.resolution import (
    HistoricalListingRequest,
    IdentifierResolutionRequest,
    IdentityCatalog,
    ResolutionStatus,
    day_value,
)
from ragged_claws.storage import (
    CanonicalConflictError,
    CanonicalParquetStore,
    DataLayout,
    load_envelope_records,
)

ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "tests/fixtures/identity/sec-2024"
SEC = ROOT / "tests/fixtures/sec"
PROTOCOL = ROOT / "research/hypotheses/sec-p-s-v2.json"


@pytest.fixture(scope="module")
def prepared(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("recorded_identity")
    prepare_identity_diagnostic(root, FIXTURES, SEC, PROTOCOL)
    return root


def catalog_at(root: Path) -> IdentityCatalog:
    store = CanonicalParquetStore(DataLayout(root / "data"), read_only=True)
    return IdentityCatalog(
        entities=store.load(Entity),
        securities=store.load(Security),
        listings=store.load(Listing),
        external_identifiers=store.load(ExternalIdentifier),
    )


def test_exact_response_excerpt_hashes_and_claim_byte_spans() -> None:
    metadata = json.loads((FIXTURES / "evidence.json").read_bytes())
    for item in metadata["resources"]:
        raw = (FIXTURES / item["fixture_file"]).read_bytes()
        assert digest(raw) == HASHES[item["fixture_file"]]
        for claim in item["reviewed_claim_spans"]:
            assert raw[claim["start"] : claim["end_exclusive"]].decode() == claim["exact_text"]
        if "excerpt_sha256" in item:
            assert (
                item["representation"] == "exact_contiguous_parent_byte_excerpt_not_full_response"
            )
            assert item["parent_offset_start"] == 1445367
            assert item["parent_offset_end_exclusive"] == 1446566
            assert len(raw) == 1199 and item["size_bytes"] == 12861776
            assert digest(raw) != item["sha256"]


def test_cik_entity_only_and_recorded_cusip_candidate_not_event_binding(prepared: Path) -> None:
    catalog = catalog_at(prepared)
    entity = catalog.resolve_identifier(
        IdentifierResolutionRequest(
            subject_type=IdentifierSubjectType.ENTITY,
            identifier_type=ExternalIdentifierType.SEC_CIK,
            value="70858",
            known_at=datetime(2024, 9, 11, 13, 30, tzinfo=UTC),
        )
    )
    assert entity.status == ResolutionStatus.RESOLVED
    with pytest.raises(ValidationError):
        IdentifierResolutionRequest(
            subject_type=IdentifierSubjectType.SECURITY,
            identifier_type=ExternalIdentifierType.SEC_CIK,
            value="70858",
        )
    security = catalog.resolve_identifier(
        IdentifierResolutionRequest(
            subject_type=IdentifierSubjectType.SECURITY,
            identifier_type=ExternalIdentifierType.CUSIP,
            value="060505104",
            known_at=datetime(2024, 9, 11, 13, 30, tzinfo=UTC),
        )
    )
    assert security.status == ResolutionStatus.RESOLVED
    assert security.known_from == day_value(date(2024, 2, 13))
    assert security.observed_at is not None and security.observed_at.year == 2026
    assert security.valid_from is security.valid_to is None  # Never an open valid interval.
    store = CanonicalParquetStore(DataLayout(prepared / "data"), read_only=True)
    assert store.load(Security)[0].security_type == SecurityType.COMMON_STOCK
    assert not store.load(Listing) and not read_inputs(prepared).controls.bindings
    assert all(e.security_id is e.listing_id is None for e in store.load(Event))
    early = catalog.resolve_identifier(
        IdentifierResolutionRequest(
            subject_type=IdentifierSubjectType.SECURITY,
            identifier_type=ExternalIdentifierType.CUSIP,
            value="060505104",
            known_at=datetime(2024, 2, 13, 23, tzinfo=UTC),
        )
    )
    assert early.status == ResolutionStatus.UNRESOLVED  # Date-only not yet fully public.


def test_late_or_current_only_claims_cannot_backfill(prepared: Path) -> None:
    catalog = catalog_at(prepared)
    claim = next(
        c
        for c in catalog.external_identifiers.values()
        if c.identifier_type == ExternalIdentifierType.CUSIP
    )
    for known in (None, day_value(date(2026, 10, 23))):
        late = IdentityCatalog(
            securities=tuple(catalog.securities.values()),
            external_identifiers=(claim.model_copy(update={"known_from": known}),),
        )
        result = late.resolve_identifier(
            IdentifierResolutionRequest(
                subject_type=IdentifierSubjectType.SECURITY,
                identifier_type=ExternalIdentifierType.CUSIP,
                value=claim.value,
                known_at=datetime(2024, 9, 11, 13, 30, tzinfo=UTC),
            )
        )
        assert result.status == ResolutionStatus.UNRESOLVED


def test_unknown_intervals_multiple_listings_and_conflicting_identifiers(prepared: Path) -> None:
    catalog = catalog_at(prepared)
    security = next(iter(catalog.securities.values()))
    # Invented counterfactual candidates only; no real MIC/FIGI mapping is asserted.
    first = Listing(
        listing_id=UUID(int=9001),
        security_id=security.security_id,
        symbol="INVENTED",
        exchange_mic="XNYS",
        effective_from=TemporalValue(
            raw_value="unknown",
            precision=TemporalPrecision.UNKNOWN,
            partial_date=PartialDate(raw_value="unknown", precision=TemporalPrecision.UNKNOWN),
        ),
        provenance_id=security.provenance_id,
    )
    request = HistoricalListingRequest(
        security_id=security.security_id,
        symbol="INVENTED",
        exchange_mic="XNYS",
        as_of=day_value(date(2024, 9, 11)),
    )
    unknown = IdentityCatalog(securities=(security,), listings=(first,)).resolve_listing(request)
    assert unknown.status == ResolutionStatus.UNRESOLVED
    second = first.model_copy(update={"listing_id": UUID(int=9002)})
    for listings in ((first, second), (second, first)):
        result = IdentityCatalog(securities=(security,), listings=listings).resolve_listing(request)
        assert result.status == ResolutionStatus.AMBIGUOUS and len(result.candidate_ids) == 2
    claim = next(
        c
        for c in catalog.external_identifiers.values()
        if c.identifier_type == ExternalIdentifierType.CUSIP
    )
    preferred = security.model_copy(
        update={"security_id": UUID(int=9003), "security_type": SecurityType.PREFERRED_STOCK}
    )
    conflict = claim.model_copy(
        update={"external_identifier_id": UUID(int=9004), "subject_id": preferred.security_id}
    )
    result = IdentityCatalog(
        securities=(security, preferred), external_identifiers=(claim, conflict)
    ).resolve_identifier(
        IdentifierResolutionRequest(
            subject_type=IdentifierSubjectType.SECURITY,
            identifier_type=ExternalIdentifierType.CUSIP,
            value=claim.value,
        )
    )
    assert result.status == ResolutionStatus.CONFLICT  # Never select common/preferred by order.


def test_repeat_import_and_conflict_preserve_immutable_records(
    prepared: Path, tmp_path: Path
) -> None:
    target = tmp_path / "copy"
    shutil.copytree(prepared, target)
    before = {
        p.relative_to(target).as_posix(): digest(p.read_bytes())
        for p in target.rglob("*")
        if p.is_file()
    }
    security = import_identity_evidence(target, FIXTURES)
    assert before == {
        p.relative_to(target).as_posix(): digest(p.read_bytes())
        for p in target.rglob("*")
        if p.is_file()
    }
    store = CanonicalParquetStore(DataLayout(target / "data"))
    with pytest.raises(CanonicalConflictError):
        store.persist(
            Security, (security.model_copy(update={"security_type": SecurityType.PREFERRED_STOCK}),)
        )
    assert store.load(Security) == (security,)
    altered = tmp_path / "altered-fixture"
    shutil.copytree(FIXTURES, altered)
    path = altered / "0001104659-24-020016.txt"
    path.write_bytes(path.read_bytes().replace(b"Common Stock", b"Preferred Stock"))
    with pytest.raises(ResearchError, match="reviewed bytes"):
        import_identity_evidence(target, altered)


def test_original_three_events_unchanged_and_all_nine_outcomes_unavailable(
    prepared: Path,
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline"
    prepare_sec(
        baseline,
        SEC / "0000950170-24-105263.txt",
        SEC / "provenance.json",
        PROTOCOL,
        as_of=REVIEWED_AT,
    )
    original = CanonicalParquetStore(DataLayout(baseline / "data"), read_only=True).load(Event)
    assert original == CanonicalParquetStore(DataLayout(prepared / "data"), read_only=True).load(
        Event
    )
    snapshot = freeze(prepared, tmp_path / "frozen")
    report = build(tmp_path / "frozen", tmp_path / "output", tmp_path / "registry")
    assert report.input_events == report.qualifying_events == 3
    assert report.distinct_known_issuers == 1
    assert all(
        h.counts["unresolved_security"] == 3 and h.spy_excess.n == 0 for h in report.horizons
    )
    rows = load_envelope_records(
        tmp_path / "output" / str(snapshot.snapshot_id) / "research_rows.parquet",
        model_type=ResearchRow,
        id_field="row_id",
        dataset_kind="staging",
        model_schema_version="1.0.0",
    )
    assert len(rows) == 9 and all(r.outcome is None for r in rows)
    assert all(r.status == "unresolved_security" and r.reason for r in rows)
    frozen_store = CanonicalParquetStore(DataLayout(tmp_path / "frozen/data"), read_only=True)
    assert len(frozen_store.load(Security)) == 1 and not frozen_store.load(Listing)
    assert len(frozen_store.load(SourceObservation)) == 4
