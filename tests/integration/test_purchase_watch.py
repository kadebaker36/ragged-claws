"""Invented forward purchases built through the existing Form 4 adapter; no network."""

import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from uuid import UUID

import pytest
from typer.testing import CliRunner

from ragged_claws.cli import app
from ragged_claws.ingestion.sec import SecForm4Adapter
from ragged_claws.models import (
    DisclosedRange,
    Entity,
    Event,
    EventAttribute,
    EventAttributeType,
    EventEvidence,
    ObservationRole,
    Provenance,
    Security,
    SecurityType,
    SourceLineage,
    SourceObservation,
)
from ragged_claws.models.identity import Listing
from ragged_claws.resolution import day_value
from ragged_claws.storage import CanonicalParquetStore, DataLayout
from ragged_claws.watch.ledger import build_report, encoded, render_markdown, write_report

FIXTURE = Path(__file__).parents[1] / "fixtures/sec/0000950170-24-105263.txt"
ACCESSION = "0000950170-24-105263"
OBSERVED = datetime(2024, 9, 11, 12, tzinfo=UTC)
ACTIONABLE = datetime(2024, 9, 11, 13, 30, tzinfo=UTC)
AS_OF = ACTIONABLE + timedelta(minutes=1)


def purchase_bytes(
    *, code: str = "P", accession: str = ACCESSION, owner: str | None = None, price: bool = True
) -> bytes:
    """Invented alterations of an attributed public fixture; never a real purchase claim."""
    raw = FIXTURE.read_bytes().replace(ACCESSION.encode(), accession.encode())
    raw = raw.replace(
        b"<transactionCode>S</transactionCode>",
        f"<transactionCode>{code}</transactionCode>".encode(),
    )
    if code == "P":
        raw = raw.replace(b"<value>D</value>", b"<value>A</value>")
    # Keep source-backed row coordinates, explicitly remove footnotes for exact-price examples.
    raw = re.sub(rb"<footnoteId[^>]*/>", b"", raw)
    if not price:
        raw = re.sub(
            rb"<transactionPricePerShare>.*?</transactionPricePerShare>", b"", raw, flags=re.S
        )
    if owner:
        raw = raw.replace(b"0000315090", owner.encode())
    return raw


def ingest(layout: DataLayout, **kwargs: object) -> CanonicalParquetStore:
    raw = kwargs.pop("raw", purchase_bytes())
    observed = kwargs.pop("observed", OBSERVED)
    accession = kwargs.pop("accession", ACCESSION)
    assert isinstance(raw, bytes) and isinstance(observed, datetime) and isinstance(accession, str)
    assert not kwargs
    adapter = SecForm4Adapter(layout)
    adapter.ingest(
        raw,
        accession=accession,
        retrieved_at=observed,
        source_locator=f"fixture://invented/{accession}",
        acceptance_timezone="America/New_York",
    )
    return adapter.store


def bind(
    layout: DataLayout, *, listing: bool = True, kind: SecurityType = SecurityType.COMMON_STOCK
) -> CanonicalParquetStore:
    """Explicit invented canonical identity, never resolution from fixture ticker/title."""
    store = CanonicalParquetStore(layout)
    events = store.load(Event)
    issuer = events[0].issuer_entity_id
    assert issuer is not None
    provenance = events[0].provenance_id
    security = Security(
        security_id=UUID(int=800),
        issuer_entity_id=issuer,
        security_type=kind,
        display_name="Invented class",
        provenance_id=provenance,
    )
    venue = Listing(
        listing_id=UUID(int=801),
        security_id=security.security_id,
        symbol="INVENTED",
        exchange_mic="XNYS",
        effective_from=day_value(OBSERVED.date()),
        provenance_id=provenance,
    )
    store.persist(Security, (security,))
    if listing:
        store.persist(Listing, (venue,))
    # This fixture constructs a fresh canonical input snapshot, not an in-place production repair.
    store.path_for(Event).unlink()
    store.persist(
        Event,
        tuple(
            e.model_copy(
                update={
                    "security_id": security.security_id,
                    "listing_id": venue.listing_id if listing else None,
                }
            )
            for e in events
        ),
    )
    return store


def test_p_purchase_multirow_exact_decimal_and_source_references(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    ingest(layout)
    bind(layout)
    with localcontext() as context:
        context.prec = 3
        report = build_report(layout, as_of=AS_OF)
    assert len(report.candidates) == 3
    assert len({c.event_id for c in report.candidates}) == 3
    event_map = {e.event_id: e for e in CanonicalParquetStore(layout).load(Event)}
    for candidate in report.candidates:
        event = event_map[candidate.event_id]
        assert candidate.shares is not None and candidate.reported_price_per_share is not None
        with localcontext() as context:
            context.prec = 100
            assert candidate.exact_transaction_value == (
                candidate.shares * candidate.reported_price_per_share
            )
        assert candidate.status == "qualifying_common_stock"
        assert candidate.currency is None
        assert candidate.public_time == event.public_time
        assert candidate.actionable_at == ACTIONABLE
        assert candidate.evidence_ids == event.event_evidence_ids
        assert candidate.source_observation_ids and candidate.provenance_ids
        assert candidate.underlying_source_families == ("sec.ownership",)
        assert len(candidate.actors) == 2
    assert report.clusters[0].purchase_event_count == 3
    assert report.clusters[0].distinct_reporting_actor_count == 2
    assert report.clusters[0].filing_count == 1


@pytest.mark.parametrize("code", ["S", "A", "G", "M", "F", "P/K"])
def test_sales_and_non_p_rows_are_excluded(tmp_path: Path, code: str) -> None:
    layout = DataLayout(tmp_path)
    ingest(layout, raw=purchase_bytes(code=code))
    assert not build_report(layout, as_of=AS_OF).candidates


def test_derivative_rows_are_not_purchases(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    ingest(
        layout,
        raw=purchase_bytes()
        .replace(b"nonDerivativeTable", b"derivativeTable")
        .replace(b"nonDerivativeTransaction", b"derivativeTransaction"),
    )
    assert not build_report(layout, as_of=AS_OF).candidates


def test_actionability_and_later_collection_do_not_leak_backward(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path / "early")
    ingest(layout)
    bind(layout)
    assert not build_report(layout, as_of=ACTIONABLE - timedelta(microseconds=1)).candidates
    assert len(build_report(layout, as_of=ACTIONABLE).candidates) == 3
    late = DataLayout(tmp_path / "late")
    ingest(late, observed=OBSERVED + timedelta(days=1))
    assert not build_report(late, as_of=AS_OF).candidates
    assert len(build_report(late, as_of=AS_OF + timedelta(days=1)).candidates) == 3


def test_unresolved_security_and_listing_survive_without_ticker_fallback(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    ingest(layout)
    report = build_report(layout, as_of=AS_OF)
    assert len(report.candidates) == 3
    assert all(
        c.status == "unresolved"
        and c.security_id is None
        and c.listing_id is None
        and set(c.unresolved_reasons) == {"unresolved_security", "unresolved_listing"}
        for c in report.candidates
    )
    assert not report.clusters
    # A known catalog symbol never resolves an unbound Event.
    store = bind(layout, listing=False)
    report = build_report(layout, as_of=AS_OF)
    assert all(
        c.status == "qualifying_common_stock" and c.listing_status == "unresolved"
        for c in report.candidates
    )
    assert all(c.unresolved_reasons == ("unresolved_listing",) for c in report.candidates)
    assert store.load(Security)


def test_resolved_preferred_stock_is_not_a_candidate(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    ingest(layout)
    bind(layout, kind=SecurityType.PREFERRED_STOCK)
    assert not build_report(layout, as_of=AS_OF).candidates


def test_missing_price_ranges_and_footnotes_never_invent_values(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path / "missing")
    ingest(layout, raw=purchase_bytes(price=False))
    report = build_report(layout, as_of=AS_OF)
    assert all(
        c.exact_transaction_value is None
        and c.reported_price_per_share is None
        and c.value_unknown_reason == "missing_exact_price"
        for c in report.candidates
    )
    ranged = DataLayout(tmp_path / "range")
    store = ingest(ranged)
    events = store.load(Event)
    store.path_for(Event).unlink()
    store.persist(
        Event,
        tuple(
            e.model_copy(
                update={
                    "disclosed_ranges": (
                        DisclosedRange(
                            name="transaction_value",
                            raw_text="$1,001-$15,000",
                            lower_bound=Decimal("1001"),
                            upper_bound=Decimal("15000"),
                        ),
                    )
                }
            )
            for e in events
        ),
    )
    assert all(
        c.exact_transaction_value is None for c in build_report(ranged, as_of=AS_OF).candidates
    )
    footnotes = DataLayout(tmp_path / "notes")
    raw = FIXTURE.read_bytes().replace(
        b"<transactionCode>S</transactionCode>", b"<transactionCode>P</transactionCode>"
    )
    raw = raw.replace(b"<value>D</value>", b"<value>A</value>")
    ingest(footnotes, raw=raw)
    assert all(
        c.exact_transaction_value is None for c in build_report(footnotes, as_of=AS_OF).candidates
    )


def add_vendor_copy(store: CanonicalParquetStore, *, observed: datetime) -> None:
    observation = store.load(SourceObservation)[0]
    provenance = store.load(Provenance)[0]
    vendor = observation.model_copy(
        update={
            "source_observation_id": UUID(int=900),
            "provider_namespace": "invented.vendor",
            "lineage": SourceLineage(
                source_family="invented.vendor",
                underlying_source_family="sec.ownership",
                observation_role=ObservationRole.VENDOR_NORMALIZED,
            ),
            "observed_at": observed,
            "retrieved_at": observed,
        }
    )
    derived = provenance.model_copy(
        update={
            "provenance_id": UUID(int=901),
            "source_observation_ids": (UUID(int=900),),
            "derived_at": observed,
        }
    )
    store.persist(SourceObservation, (vendor,))
    store.persist(Provenance, (derived,))
    events = store.load(Event)
    links = tuple(
        EventEvidence(
            event_evidence_id=UUID(int=910 + i),
            event_id=e.event_id,
            source_observation_ids=(UUID(int=900),),
            provenance_id=UUID(int=901),
        )
        for i, e in enumerate(events)
    )
    store.persist(EventEvidence, links)
    store.path_for(Event).unlink()
    store.persist(
        Event,
        tuple(
            e.model_copy(
                update={
                    "event_evidence_ids": (*e.event_evidence_ids, link.event_evidence_id),
                }
            )
            for e, link in zip(events, links, strict=True)
        ),
    )


def test_duplicate_vendor_evidence_and_late_observations_do_not_add_events_or_actors(
    tmp_path: Path,
) -> None:
    layout = DataLayout(tmp_path)
    ingest(layout)
    store = bind(layout)
    before = build_report(layout, as_of=AS_OF)
    add_vendor_copy(store, observed=AS_OF + timedelta(seconds=1))
    assert encoded(before) == encoded(build_report(layout, as_of=AS_OF))
    later = build_report(layout, as_of=AS_OF + timedelta(seconds=2))
    assert len(later.candidates) == 3
    assert later.clusters == before.clusters
    assert all(
        len(c.source_observation_ids) == 2
        and len(c.evidence_ids) == 2
        and c.underlying_source_families == ("sec.ownership",)
        for c in later.candidates
    )


def test_multiple_insiders_multiple_filings_create_descriptive_facts(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    ingest(layout)
    second = "0000950170-24-105264"
    ingest(layout, raw=purchase_bytes(accession=second, owner="0000315091"), accession=second)
    bind(layout)
    report = build_report(layout, as_of=AS_OF)
    assert len(report.candidates) == 6
    cluster = report.clusters[0]
    assert cluster.purchase_event_count == 6
    assert cluster.distinct_reporting_actor_count == 3
    assert cluster.filing_count == 2 and cluster.multiple_filings
    assert cluster.first_actionable_at == cluster.latest_actionable_at == ACTIONABLE


def test_output_determinism_timezone_and_portable_paths(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path / "data with spaces")
    ingest(layout)
    a = build_report(layout, as_of=AS_OF)
    equivalent = datetime.fromisoformat("2024-09-11T09:31:00-04:00")
    b = build_report(layout, as_of=equivalent)
    assert encoded(a) == encoded(b)
    assert render_markdown(a) == render_markdown(b)
    output = tmp_path / "output with spaces"
    write_report(a, output)
    write_report(b, output)
    assert (output / "watch.json").read_bytes() == encoded(a)
    result = CliRunner().invoke(
        app,
        [
            "watch-insider-purchases",
            "--data-dir",
            str(layout.root),
            "--as-of",
            AS_OF.isoformat(),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads((output / "watch.json").read_bytes())["as_of"].endswith("Z")
    assert (
        CliRunner()
        .invoke(
            app,
            [
                "watch-insider-purchases",
                "--data-dir",
                str(layout.root),
                "--as-of",
                "2024-09-11T13:31:00",
                "--output",
                str(output),
            ],
        )
        .exit_code
        == 2
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        build_report(layout, as_of=datetime(2024, 9, 11))


def test_missing_public_time_is_not_filled_from_occurrence_or_filing_date(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    ingest(layout, raw=purchase_bytes().replace(b"20240910191316", b""))
    assert not build_report(layout, as_of=AS_OF).candidates


def test_short_window_excludes_old_events_and_future_identity_does_not_leak(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    ingest(layout)
    store = bind(layout)
    assert not build_report(layout, as_of=AS_OF + timedelta(days=7), lookback_sessions=1).candidates
    security = store.load(Security)[0]
    prov = store.load(Provenance)[0]
    late = prov.model_copy(
        update={"provenance_id": UUID(int=999), "derived_at": AS_OF + timedelta(days=1)}
    )
    store.persist(Provenance, (late,))
    store.path_for(Security).unlink()
    store.persist(Security, (security.model_copy(update={"provenance_id": late.provenance_id}),))
    report = build_report(layout, as_of=AS_OF)
    assert all(c.status == "unresolved" for c in report.candidates)
    assert not report.clusters


def test_canonical_code_and_coordinate_guards(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    store = ingest(layout)
    events = store.load(Event)
    store.path_for(Event).unlink()
    store.persist(
        Event,
        tuple(
            e.model_copy(
                update={
                    "attributes": tuple(
                        EventAttribute(name=a.name, value_type=EventAttributeType.TEXT, value="G")
                        if a.name == "transaction_code"
                        else a
                        for a in e.attributes
                    )
                }
            )
            for e in events
        ),
    )
    assert not build_report(layout, as_of=AS_OF).candidates


def test_resolved_entity_contradictions_fail_explicitly(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    ingest(layout)
    store = bind(layout)
    security = store.load(Security)[0]
    store.path_for(Security).unlink()
    store.persist(Security, (security.model_copy(update={"issuer_entity_id": UUID(int=123)}),))
    with pytest.raises(ValueError, match="issuer contradiction"):
        build_report(layout, as_of=AS_OF)
    assert store.load(Entity)


def test_actor_entities_are_exposed_only_from_canonical_reporting_roles(tmp_path: Path) -> None:
    from ragged_claws.models import EventPartyReference, ExternalIdentifier
    from ragged_claws.models.identity import (
        EntityType,
        ExternalIdentifierType,
        IdentifierSubjectType,
    )

    layout = DataLayout(tmp_path)
    store = ingest(layout)
    event = store.load(Event)[0]
    entity = Entity(
        entity_id=UUID(int=500),
        entity_type=EntityType.PERSON,
        display_name="Invented resolved person",
        provenance_id=event.provenance_id,
    )
    claim = ExternalIdentifier(
        external_identifier_id=UUID(int=501),
        subject_type=IdentifierSubjectType.ENTITY,
        subject_id=entity.entity_id,
        identifier_type=ExternalIdentifierType.SEC_CIK,
        value="0000315090",
        source_observation_id=store.load(SourceObservation)[0].source_observation_id,
        provenance_id=event.provenance_id,
        observed_at=OBSERVED,
    )
    store.persist(Entity, (entity,))
    store.persist(ExternalIdentifier, (claim,))
    # A catalog identity alone cannot add a reporting role.
    before = build_report(layout, as_of=AS_OF)
    assert all(a.entity_id is None for c in before.candidates for a in c.actors)
    events = store.load(Event)
    store.path_for(Event).unlink()
    store.persist(
        Event,
        tuple(
            e.model_copy(
                update={
                    "actors": (
                        EventPartyReference(entity_id=entity.entity_id, role="reporting_owner"),
                    )
                }
            )
            for e in events
        ),
    )
    after = build_report(layout, as_of=AS_OF)
    linked = [a for c in after.candidates for a in c.actors if a.reference == "sec_cik:0000315090"]
    assert all(
        a.entity_id == entity.entity_id and a.entity_resolution_status == "resolved" for a in linked
    )


def test_catalog_ticker_never_supplies_an_event_binding(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    store = ingest(layout)
    original = store.load(Event)
    bind(layout)
    store.path_for(Event).unlink()
    store.persist(Event, original)
    report = build_report(layout, as_of=AS_OF)
    assert store.load(Listing)
    assert store.load(Security)
    assert all(
        c.security_id is None and c.listing_id is None and c.status == "unresolved"
        for c in report.candidates
    )


def test_long_exact_price_product_ignores_ambient_decimal_precision(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    price = Decimal("39.6682000000000000000000000001")
    ingest(layout, raw=purchase_bytes().replace(b"39.6682", str(price).encode()))
    with localcontext() as context:
        context.prec = 3
        report = build_report(layout, as_of=AS_OF)
    candidate = next(c for c in report.candidates if c.reported_price_per_share == price)
    assert candidate.shares is not None
    with localcontext() as context:
        context.prec = 100
        assert candidate.exact_transaction_value == candidate.shares * price


def test_entire_later_filing_cannot_change_any_earlier_report_bytes(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    ingest(layout)
    before = build_report(layout, as_of=AS_OF)
    second = "0000950170-24-105264"
    ingest(
        layout,
        raw=purchase_bytes(accession=second),
        accession=second,
        observed=OBSERVED + timedelta(days=1),
    )
    assert encoded(build_report(layout, as_of=AS_OF)) == encoded(before)
    assert render_markdown(build_report(layout, as_of=AS_OF)) == render_markdown(before)


def test_later_identity_record_is_indistinguishable_from_absence_as_of_t(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    ingest(layout)
    store = bind(layout)
    securities = store.load(Security)
    listings = store.load(Listing)
    store.path_for(Security).unlink()
    store.path_for(Listing).unlink()
    before = build_report(layout, as_of=AS_OF)
    late = store.load(Provenance)[0].model_copy(
        update={
            "provenance_id": UUID(int=999),
            "derived_at": AS_OF + timedelta(days=1),
        }
    )
    store.persist(Provenance, (late,))
    store.persist(
        Security,
        tuple(s.model_copy(update={"provenance_id": late.provenance_id}) for s in securities),
    )
    store.persist(
        Listing, tuple(s.model_copy(update={"provenance_id": late.provenance_id}) for s in listings)
    )
    assert encoded(build_report(layout, as_of=AS_OF)) == encoded(before)
