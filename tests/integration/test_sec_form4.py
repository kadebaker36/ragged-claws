"""Recorded public SEC bytes plus explicitly invented edge-case variants; offline."""

import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from typer.testing import CliRunner

from ragged_claws.cli import app
from ragged_claws.ingestion.sec import SecForm4Adapter
from ragged_claws.ingestion.sec_models import SecBundle
from ragged_claws.ingestion.sec_parser import SecParseError, parse_acceptance
from ragged_claws.models import (
    DerivationKind,
    Entity,
    EntityType,
    Event,
    EventEvidence,
    ExternalIdentifier,
    ExternalIdentifierType,
    IdentifierSubjectType,
    ObservationRole,
    Provenance,
    RetentionClass,
    SourceLineage,
    SourceObservation,
)
from ragged_claws.resolution import deterministic_entity_id_from_cik
from ragged_claws.storage import (
    CanonicalConflictError,
    DataLayout,
    capture_raw_bytes,
    deterministic_source_observation_id,
    load_envelope_records,
    raw_object_path,
)
from ragged_claws.temporal import AvailabilityPolicy

FIXTURES = Path(__file__).parents[1] / "fixtures" / "sec"
ACCESSION = "0000950170-24-105263"
URL = f"https://www.sec.gov/Archives/edgar/data/70858/000095017024105263/{ACCESSION}.txt"
OBSERVED = datetime(2026, 10, 22, 22, tzinfo=UTC)


def _raw() -> bytes:
    return (FIXTURES / f"{ACCESSION}.txt").read_bytes()


def _ingest(adapter: SecForm4Adapter, content: bytes | None = None) -> SecBundle:
    return adapter.ingest(
        _raw() if content is None else content,
        accession=ACCESSION,
        retrieved_at=OBSERVED,
        source_locator=URL,
        acceptance_timezone="America/New_York",
    )


def test_recorded_sec_filing_end_to_end_and_exact_bytes(tmp_path: Path) -> None:
    raw = _raw()
    metadata = json.loads((FIXTURES / "provenance.json").read_text())
    assert hashlib.sha256(raw).hexdigest() == metadata["sha256"]
    assert len(raw) == metadata["size_bytes"] == 14338
    adapter = SecForm4Adapter(DataLayout(tmp_path))
    bundle = _ingest(adapter)
    filing = bundle.filing
    assert filing.accession == ACCESSION
    assert str(filing.filing_group_id) == "6e5a1807-1eb8-507e-b95b-8b0670adbf0f"
    assert str(bundle.events[0].event_id) == "671383fb-6186-5347-9c22-972546f9491c"
    assert filing.document_name == "ownership.xml"
    assert filing.issuer_cik == "0000070858"
    assert {owner.cik for owner in filing.owners} == {"0001067983", "0000315090"}
    assert all(owner.ten_percent_owner is True for owner in filing.owners)
    assert len(filing.footnotes) == 7
    assert len(bundle.events) == 3  # two owners do not turn three rows into six events
    assert len({event.event_id for event in bundle.events}) == 3
    assert [event.financial_values[0].value for event in bundle.events] == [
        Decimal("1081102"),
        Decimal("1721366"),
        Decimal("2994625"),
    ]
    prices = [
        next(a.value for a in e.attributes if a.name == "reported_price_per_share")
        for e in bundle.events
    ]
    assert prices == [Decimal("39.6682"), Decimal("39.5742"), Decimal("39.2978")]
    assert filing.filed_as_of == date(2024, 9, 10)
    assert filing.acceptance_raw == "20240910191316"
    assert filing.acceptance_time is not None
    assert filing.acceptance_time.timestamp == datetime(2024, 9, 10, 23, 13, 16, tzinfo=UTC)
    assert filing.acceptance_time.source_timezone == "America/New_York"
    assert bundle.observation.observed_at == OBSERVED
    assert bundle.actionability is not None
    assert bundle.actionability.availability.effective_availability_at == datetime(
        2024,
        9,
        10,
        23,
        18,
        16,
        tzinfo=UTC,
    )
    assert bundle.events[0].occurrence_time.partial_date is not None
    assert bundle.events[0].occurrence_time.partial_date.day == 6
    assert all(
        event.actionable_at == datetime(2024, 9, 11, 13, 30, tzinfo=UTC) for event in bundle.events
    )
    assert bundle.unresolved_owner_ciks == ("0000315090", "0001067983")
    # The XML identifies reporting owners, but does not establish their canonical entity types.
    assert all(not event.actors and not event.economic_units for event in bundle.events)
    assert all(event.security_id is None and event.listing_id is None for event in bundle.events)
    for event, evidence in zip(bundle.events, bundle.evidence, strict=True):
        assert event.event_evidence_ids == (evidence.event_evidence_id,)
        assert evidence.event_id == event.event_id
        assert evidence.source_observation_ids == (bundle.observation.source_observation_id,)
    assert adapter.store.load(Event) == tuple(sorted(bundle.events, key=lambda e: str(e.event_id)))
    assert adapter.store.load(SourceObservation) == (bundle.observation,)
    assert adapter.store.load(Provenance) == (bundle.provenance,)
    assert set(adapter.store.load(EventEvidence)) == set(bundle.evidence)
    assert adapter.store.load(Entity) == bundle.entities
    assert adapter.store.load(ExternalIdentifier) == bundle.identifier_claims
    assert adapter.load_staging() == (filing,)
    assert load_envelope_records(
        adapter.mapping_path,
        model_type=SecBundle,
        id_field="source_version_id",
        dataset_kind="staging",
        model_schema_version="1.0.0",
    ) == (bundle,)
    assert (
        raw_object_path(adapter.layout, bundle.observation.raw_content_hash.value).read_bytes()
        == raw
    )


def _seed_typed_owners(adapter: SecForm4Adapter) -> tuple[Entity, ...]:
    # Explicit invented pre-existing identity catalog, not type inference from the real filing.
    manifest = capture_raw_bytes(
        adapter.layout,
        b"invented typed identity catalog",
        provider_namespace="synthetic.identity",
        source_family="synthetic.identity",
        source_native_id="catalog/1",
        retrieved_at=OBSERVED,
        adapter_version="test/1",
        retention_class=RetentionClass.PUBLIC,
        license_name="synthetic-test-data",
    )
    observation = SourceObservation(
        source_observation_id=deterministic_source_observation_id(
            "synthetic.identity", "catalog/1", manifest.content_hash.value
        ),
        provider_namespace="synthetic.identity",
        source_native_id="catalog/1",
        lineage=SourceLineage(
            source_family="synthetic.identity", observation_role=ObservationRole.SYNTHETIC
        ),
        retrieved_at=OBSERVED,
        observed_at=OBSERVED,
        raw_content_hash=manifest.content_hash,
        adapter_version="test/1",
        retention_class=RetentionClass.PUBLIC,
        license_name="synthetic-test-data",
    )
    provenance = Provenance(
        provenance_id=UUID(int=90),
        source_observation_ids=(observation.source_observation_id,),
        derivation_kind=DerivationKind.SYNTHETIC_TEST,
        derived_at=OBSERVED,
        transform_version="test/1",
    )
    adapter.store.persist(SourceObservation, (observation,))
    adapter.store.persist(Provenance, (provenance,))
    entities = tuple(
        Entity(
            entity_id=deterministic_entity_id_from_cik(cik),
            entity_type=kind,
            display_name="Invented catalog label",
            provenance_id=UUID(int=90),
        )
        for cik, kind in (
            ("0000315090", EntityType.PERSON),
            ("0001067983", EntityType.ORGANIZATION),
        )
    )
    claims = tuple(
        ExternalIdentifier(
            external_identifier_id=UUID(int=100 + index),
            subject_type=IdentifierSubjectType.ENTITY,
            subject_id=e.entity_id,
            identifier_type=ExternalIdentifierType.SEC_CIK,
            value=cik,
            source_observation_id=observation.source_observation_id,
            provenance_id=UUID(int=90),
            observed_at=OBSERVED,
        )
        for index, (e, cik) in enumerate(zip(entities, ("0000315090", "0001067983"), strict=True))
    )
    adapter.store.persist(Entity, entities)
    adapter.store.persist(ExternalIdentifier, claims)
    return entities


def test_existing_typed_owner_identities_link_without_row_multiplication(tmp_path: Path) -> None:
    adapter = SecForm4Adapter(DataLayout(tmp_path))
    entities = _seed_typed_owners(adapter)
    bundle = _ingest(adapter)
    assert not bundle.unresolved_owner_ciks
    assert len(bundle.events) == 3
    assert all(
        {actor.entity_id for actor in event.actors} == {e.entity_id for e in entities}
        for event in bundle.events
    )
    assert all(not event.economic_units for event in bundle.events)


def test_duplicate_ingestion_preserves_first_seen_and_later_capture_history(tmp_path: Path) -> None:
    adapter = SecForm4Adapter(DataLayout(tmp_path))
    first = _ingest(adapter)
    before = {
        p: p.read_bytes()
        for p in (*tmp_path.glob("curated/*.parquet"), *tmp_path.glob("staging/*.parquet"))
    }
    second = adapter.ingest(
        _raw(),
        accession=ACCESSION,
        source_locator=URL,
        retrieved_at=OBSERVED + timedelta(days=1),
        acceptance_timezone="America/New_York",
    )
    assert first == second
    assert all(path.read_bytes() == content for path, content in before.items())
    assert len(tuple(adapter.layout.raw_manifests.glob("*.json"))) == 2


def test_two_accessions_reuse_subjects_and_preserve_additional_evidence(tmp_path: Path) -> None:
    adapter = SecForm4Adapter(DataLayout(tmp_path))
    owners = _seed_typed_owners(adapter)
    first = _ingest(adapter)
    original_entities = adapter.store.load(Entity)
    second_accession = "0000950170-24-105264"
    # Invented second accession, clearly distinct from the recorded fixture.
    second = adapter.ingest(
        _raw().replace(ACCESSION.encode(), second_accession.encode()),
        accession=second_accession,
        source_locator=f"fixture://invented-second-accession/{second_accession}",
        retrieved_at=OBSERVED + timedelta(days=1),
        acceptance_timezone="America/New_York",
    )
    assert adapter.store.load(Entity) == original_entities
    assert first.entities == second.entities
    assert first.filing.filing_group_id != second.filing.filing_group_id
    assert len(adapter.store.load(Event)) == 6
    assert len(adapter.store.load(SourceObservation)) == 3  # catalog and two filings
    assert len(adapter.store.load(Provenance)) == 3
    assert len(adapter.store.load(ExternalIdentifier)) == 8  # two initial + three per filing
    assert not ({e.event_id for e in first.events} & {e.event_id for e in second.events})
    assert all(
        {actor.entity_id for actor in event.actors} == {e.entity_id for e in owners}
        for event in (*first.events, *second.events)
    )
    assert first.observation.observed_at != second.observation.observed_at
    assert first.provenance.provenance_id != second.provenance.provenance_id
    for bundle in (first, second):
        assert all(
            link.source_observation_ids == (bundle.observation.source_observation_id,)
            for link in bundle.evidence
        )


def test_changed_payload_conflicts_before_curated_or_staging_publication(tmp_path: Path) -> None:
    adapter = SecForm4Adapter(DataLayout(tmp_path))
    _ingest(adapter)
    before = {
        p: p.read_bytes()
        for p in (*tmp_path.glob("curated/*.parquet"), *tmp_path.glob("staging/*.parquet"))
    }
    with pytest.raises(CanonicalConflictError):
        _ingest(adapter, _raw().replace(b"39.6682", b"39.6683"))
    assert all(path.read_bytes() == content for path, content in before.items())
    assert len(tuple(adapter.layout.raw_objects.glob("*/*"))) == 2


def _variants(*, first_row: bytes | None = None, extra: bytes = b"") -> bytes:
    """Invented alterations are produced in-memory and never labeled recorded SEC data."""
    raw = _raw()
    rows = re.findall(rb"<nonDerivativeTransaction>.*?</nonDerivativeTransaction>", raw, re.S)
    return raw.replace(rows[0], (first_row or rows[0]) + extra, 1)


def test_equal_valued_rows_are_distinct_and_missing_prices_stay_missing(tmp_path: Path) -> None:
    row = re.findall(rb"<nonDerivativeTransaction>.*?</nonDerivativeTransaction>", _raw(), re.S)[0]
    row = re.sub(rb"<value>39.6682</value>", b"", row)
    bundle = _ingest(SecForm4Adapter(DataLayout(tmp_path)), _variants(first_row=row, extra=row))
    assert len(bundle.events) == 4
    assert len({event.event_id for event in bundle.events}) == 4
    assert bundle.filing.rows[0].price is None
    assert bundle.filing.rows[0].footnote_ids
    assert not any(a.name == "reported_price_per_share" for a in bundle.events[0].attributes)


@pytest.mark.parametrize("form", ["3", "5", "4/A"])
def test_unsupported_forms_emit_no_canonical_transactions(tmp_path: Path, form: str) -> None:
    raw = _raw().replace(
        b"CONFORMED SUBMISSION TYPE:\t4", f"CONFORMED SUBMISSION TYPE:\t{form}".encode()
    )
    raw = raw.replace(b"<TYPE>4", f"<TYPE>{form}".encode())
    raw = raw.replace(
        b"<documentType>4</documentType>", f"<documentType>{form}</documentType>".encode()
    )
    bundle = _ingest(SecForm4Adapter(DataLayout(tmp_path)), raw)
    assert not bundle.events
    assert all(row.exclusion_reason == f"unsupported_form:{form}" for row in bundle.filing.rows)


@pytest.mark.parametrize("code", ["A", "M", "G", "F", "P/K"])
def test_other_transaction_codes_are_countably_excluded(tmp_path: Path, code: str) -> None:
    raw = _raw().replace(
        b"<transactionCode>S</transactionCode>",
        f"<transactionCode>{code}</transactionCode>".encode(),
    )
    bundle = _ingest(SecForm4Adapter(DataLayout(tmp_path)), raw)
    assert not bundle.events
    assert len(bundle.filing.rows) == 3
    assert all(row.exclusion_reason == f"unsupported_code:{code}" for row in bundle.filing.rows)


def test_derivatives_and_holdings_remain_outside_ps_population(tmp_path: Path) -> None:
    raw = _raw().replace(b"nonDerivativeTable", b"derivativeTable")
    raw = raw.replace(b"nonDerivativeTransaction", b"derivativeTransaction")
    bundle = _ingest(SecForm4Adapter(DataLayout(tmp_path / "derivatives")), raw)
    assert not bundle.events and len(bundle.filing.rows) == 3
    assert all(row.exclusion_reason == "derivative_table" for row in bundle.filing.rows)
    raw = _raw().replace(b"nonDerivativeTransaction", b"nonDerivativeHolding")
    bundle = _ingest(SecForm4Adapter(DataLayout(tmp_path / "holdings")), raw)
    assert not bundle.events
    assert all(row.exclusion_reason == "non_transaction_holding" for row in bundle.filing.rows)


@pytest.mark.parametrize("raw", [b"", b"bad", b"20240230120000"])
def test_missing_malformed_acceptance_never_uses_filing_or_transaction_date(
    tmp_path: Path,
    raw: bytes,
) -> None:
    content = _raw().replace(b"20240910191316", raw)
    bundle = _ingest(SecForm4Adapter(DataLayout(tmp_path)), content)
    assert bundle.filing.acceptance_time is None
    assert bundle.filing.acceptance_raw == raw.decode() or (
        not raw and bundle.filing.acceptance_raw == ""
    )
    assert bundle.filing.timing_reason
    assert all(event.public_time is None and event.actionable_at is None for event in bundle.events)
    assert bundle.filing.filed_as_of == date(2024, 9, 10)


@pytest.mark.parametrize(
    "raw,utc",
    [
        ("20240102160000", datetime(2024, 1, 2, 21, tzinfo=UTC)),
        ("20240703160000", datetime(2024, 7, 3, 20, tzinfo=UTC)),
        ("20240910213000", datetime(2024, 9, 11, 1, 30, tzinfo=UTC)),
    ],
)
def test_confirmed_eastern_acceptance_uses_dst_and_date_boundaries(raw: str, utc: datetime) -> None:
    parsed, reason = parse_acceptance(raw, timezone="America/New_York")
    assert reason is None and parsed is not None and parsed.timestamp == utc
    unconfirmed, reason = parse_acceptance(raw, timezone=None)
    assert unconfirmed is None and reason == "acceptance_timezone_unconfirmed"


@pytest.mark.parametrize("raw", ["20240310023000", "20241103013000"])
def test_ambiguous_nonexistent_eastern_clocks_fail_closed(raw: str) -> None:
    value, reason = parse_acceptance(raw, timezone="America/New_York")
    assert value is None and reason == "ambiguous_or_nonexistent_acceptance"


@pytest.mark.parametrize(
    "clock,expected",
    [
        ("20240703092000", datetime(2024, 7, 3, 13, 30, tzinfo=UTC)),
        ("20240703092500", datetime(2024, 7, 5, 13, 30, tzinfo=UTC)),
        ("20240703093000", datetime(2024, 7, 5, 13, 30, tzinfo=UTC)),
    ],
)
def test_shared_actionability_uses_delayed_availability_not_acceptance(
    tmp_path: Path,
    clock: str,
    expected: datetime,
) -> None:
    bundle = _ingest(
        SecForm4Adapter(DataLayout(tmp_path)), _raw().replace(b"20240910191316", clock.encode())
    )
    assert all(event.actionable_at == expected for event in bundle.events)


@pytest.mark.parametrize(
    "before,after",
    [
        (
            b"ACCESSION NUMBER:\t\t0000950170-24-105263",
            b"ACCESSION NUMBER:\t\t0000950170-24-105264",
        ),
        (b"<documentType>4</documentType>", b"<documentType>3</documentType>"),
        (b"<issuerCik>0000070858</issuerCik>", b"<issuerCik>0000070859</issuerCik>"),
        (b"<rptOwnerCik>0000315090</rptOwnerCik>", b"<rptOwnerCik>0000315091</rptOwnerCik>"),
        (b"<?xml version=", b"<!DOCTYPE x [<!ENTITY e 'bad'>]><?xml version="),
    ],
)
def test_contradictions_and_unsafe_xml_preserve_raw_without_partial_events(
    tmp_path: Path,
    before: bytes,
    after: bytes,
) -> None:
    raw = _raw()
    assert before in raw
    adapter = SecForm4Adapter(DataLayout(tmp_path))
    with pytest.raises(SecParseError):
        _ingest(adapter, raw.replace(before, after))
    assert not adapter.store.load(Event)
    assert tuple(adapter.layout.raw_objects.glob("*/*"))


def test_policy_change_conflicts_instead_of_overwriting_a_label(tmp_path: Path) -> None:
    adapter = SecForm4Adapter(DataLayout(tmp_path))
    bundle = _ingest(adapter)
    with pytest.raises(CanonicalConflictError):
        adapter.ingest(
            _raw(),
            accession=ACCESSION,
            source_locator=URL,
            retrieved_at=OBSERVED,
            acceptance_timezone="America/New_York",
            policy=AvailabilityPolicy(
                policy_id="different",
                policy_version="1.0.0",
                delay=timedelta(days=2),
                rationale="invented test policy",
            ),
        )
    assert set(adapter.store.load(Event)) == set(bundle.events)


def test_local_cli_exposes_counts_without_network(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "ingest-sec-form4",
            str(FIXTURES / f"{ACCESSION}.txt"),
            "--accession",
            ACCESSION,
            "--source-url",
            URL,
            "--data-dir",
            str(tmp_path),
            "--acceptance-timezone",
            "America/New_York",
        ],
    )
    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert summary["events"] == 3 and summary["reporting_owners"] == 2
    assert len(summary["unresolved_owner_ciks"]) == 2


def test_explicit_xml_path_retains_metadata_without_fabricating_missing_time(
    tmp_path: Path,
) -> None:
    xml = re.search(rb"<XML>\s*(.*?)\s*</XML>", _raw(), re.S)
    assert xml is not None
    adapter = SecForm4Adapter(DataLayout(tmp_path))
    bundle = adapter.ingest(
        xml[1],
        accession=ACCESSION,
        document_name="ownership.xml",
        form_type="4",
        filed_as_of=date(2024, 9, 10),
        source_locator="fixture://bare-xml",
        retrieved_at=OBSERVED,
    )
    assert len(bundle.events) == 3
    assert bundle.filing.timing_reason == "missing_acceptance"
    assert all(event.actionable_at is None for event in bundle.events)


def test_multiple_ownership_documents_fail_instead_of_selecting_first(tmp_path: Path) -> None:
    block = re.search(rb"<DOCUMENT>.*?</DOCUMENT>", _raw(), re.S)
    assert block is not None
    raw = _raw().replace(b"</SEC-DOCUMENT>", block[0] + b"</SEC-DOCUMENT>")
    with pytest.raises(SecParseError, match="exactly one"):
        _ingest(SecForm4Adapter(DataLayout(tmp_path)), raw)


def test_unrelated_exhibit_does_not_replace_ownership_document(tmp_path: Path) -> None:
    exhibit = (
        b"<DOCUMENT>\n<TYPE>EX-99\n<SEQUENCE>2\n<FILENAME>exhibit.htm\n"
        b"<TEXT><!DOCTYPE html><html>invented unrelated exhibit</html></TEXT>\n</DOCUMENT>\n"
    )
    bundle = _ingest(
        SecForm4Adapter(DataLayout(tmp_path)),
        _raw().replace(b"</SEC-DOCUMENT>", exhibit + b"</SEC-DOCUMENT>"),
    )
    assert bundle.filing.document_name == "ownership.xml" and len(bundle.events) == 3


@pytest.mark.parametrize("value", [b"NaN", b"1_000", b"-1"])
def test_malformed_financial_values_fail_explicitly(tmp_path: Path, value: bytes) -> None:
    with pytest.raises(SecParseError, match="numeric"):
        _ingest(SecForm4Adapter(DataLayout(tmp_path)), _raw().replace(b"39.6682", value))


def test_purchase_direct_ownership_and_precision_are_source_values(tmp_path: Path) -> None:
    raw = _raw().replace(
        b"<transactionCode>S</transactionCode>", b"<transactionCode>P</transactionCode>"
    )
    raw = raw.replace(b"<value>D</value>", b"<value>A</value>")
    raw = raw.replace(b"<value>I</value>", b"<value>D</value>")
    raw = raw.replace(b"39.6682", b"39.6682000000000000000000000001")
    bundle = _ingest(SecForm4Adapter(DataLayout(tmp_path)), raw)
    assert all(event.event_type == "equity_purchase" for event in bundle.events)
    assert all(row.direct_indirect == "D" for row in bundle.filing.rows)
    price = next(
        a.value for a in bundle.events[0].attributes if a.name == "reported_price_per_share"
    )
    assert price == Decimal("39.6682000000000000000000000001")
    assert all(not any(a.name == "execution_venue" for a in e.attributes) for e in bundle.events)
