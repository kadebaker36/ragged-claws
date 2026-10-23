"""Entirely invented offline inputs. No vendor record, entitlement or research validation."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr
from typer.testing import CliRunner

from ragged_claws.cli import app
from ragged_claws.ingestion.quiver import BIOGUIDE, QuiverAdapter
from ragged_claws.ingestion.quiver_access import (
    QuiverAccessReview,
    request_identity,
    retrieve_quiver,
)
from ragged_claws.ingestion.quiver_models import Endpoint, QuiverBundle, ReviewedRowLink
from ragged_claws.ingestion.quiver_parser import (
    FAMILIES,
    PATHS,
    QuiverError,
    exact_json,
    load_json,
    parse_rows,
)
from ragged_claws.lineage import independent_primary_families
from ragged_claws.models import (
    DerivationKind,
    DisclosedRange,
    Entity,
    EntityType,
    Event,
    EventEvidence,
    EventPartyReference,
    ExternalIdentifier,
    ExternalIdentifierType,
    FeatureSnapshot,
    FeatureValue,
    FinancialValue,
    FinancialValueKind,
    IdentifierSubjectType,
    ObservationRole,
    PartialDate,
    Provenance,
    RetentionClass,
    SourceLineage,
    SourceObservation,
    TemporalPrecision,
    TemporalValue,
)
from ragged_claws.storage import CanonicalConflictError, DataLayout, capture_raw_bytes
from ragged_claws.storage.catalog import query_catalog, rebuild_catalog
from ragged_claws.storage.raw import raw_object_path
from ragged_claws.temporal import PointInTimeViolation, validate_feature_snapshot

FIXTURES = Path(__file__).parents[1] / "fixtures" / "quiver"
NOW = datetime(2024, 5, 10, 18, tzinfo=UTC)


def content(endpoint: Endpoint) -> bytes:
    names = {
        "congress_v1": "congress-v1",
        "congress_v2": "congress-v2",
        "contracts": "contracts",
        "lobbying": "lobbying",
    }
    return (FIXTURES / f"invented-{names[endpoint]}.json").read_bytes()


def url(endpoint: Endpoint, page: int = 1) -> str:
    query = "" if endpoint == "congress_v1" else f"?page={page}&page_size=20"
    if endpoint == "congress_v2":
        query += "&version=V2"
    return "https://api.quiverquant.com" + PATHS[endpoint] + query


def ingest(
    adapter: QuiverAdapter,
    endpoint: Endpoint = "contracts",
    data: bytes | None = None,
    links: tuple[ReviewedRowLink, ...] = (),
) -> QuiverBundle:
    return adapter.ingest(
        content(endpoint) if data is None else data,
        endpoint=endpoint,
        source_locator=url(endpoint),
        retrieved_at=NOW,
        synthetic=True,
        links=links,
    )


@pytest.mark.parametrize("endpoint", ["congress_v1", "congress_v2", "contracts", "lobbying"])
def test_offline_roundtrip_and_honest_unresolved_counts(tmp_path: Path, endpoint: Endpoint) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    first = ingest(adapter, endpoint)
    assert adapter.load_mappings() == (first,)
    assert first.observation.retention_class is RetentionClass.INTERNAL
    assert first.observation.lineage.observation_role is ObservationRole.VENDOR_NORMALIZED
    assert first.observation.lineage.underlying_source_family == FAMILIES[endpoint]
    assert (
        first.observation.public_time is None
    )  # response may contain different row disclosure dates
    assert raw_object_path(
        adapter.layout, first.observation.raw_content_hash.value
    ).read_bytes() == content(endpoint)
    assert not first.events and not first.evidence
    assert all(m.status == "unresolved" and m.event_id is None for m in first.mappings)
    assert all(row.ownership == "unknown" for row in first.rows)
    assert ingest(adapter, endpoint) == first
    later = adapter.ingest(
        content(endpoint),
        endpoint=endpoint,
        source_locator=url(endpoint),
        retrieved_at=NOW + timedelta(days=1),
        synthetic=True,
    )
    assert later == first


def test_date_semantics_precision_and_actionability() -> None:
    v1 = parse_rows(content("congress_v1"), "congress_v1", limit=20)[0]
    assert v1.occurrence_time is not None and v1.occurrence_time.raw_value == "2024-05-01"
    assert v1.reported_time is not None and v1.reported_time.raw_value == "2024-05-06"
    assert (
        v1.reported_time.precision is TemporalPrecision.DAY and v1.reported_time.timestamp is None
    )
    assert v1.actionability is None
    assert "public_availability_requires_primary_evidence" in v1.normalization_notes
    v2 = parse_rows(content("congress_v2"), "congress_v2", limit=20)[0]
    assert v2.uploaded_time is not None and v2.uploaded_time.timestamp == datetime(
        2024, 5, 7, 16, 23, 45, tzinfo=UTC
    )
    assert v2.modified_time is not None and v2.modified_time.precision is TemporalPrecision.UNKNOWN
    contract = parse_rows(content("contracts"), "contracts", limit=20)[0]
    assert (
        contract.reported_time == v1.reported_time
        and contract.occurrence_time == v1.occurrence_time
    )
    lobbying = parse_rows(content("lobbying"), "lobbying", limit=20)[0]
    assert lobbying.occurrence_time is None  # no report period or underlying activity date supplied
    assert lobbying.reported_time == v1.reported_time


def test_no_utc_midnight_manufactured_from_naive_vendor_date() -> None:
    value = load_json(content("congress_v1"))
    value[0]["ReportDate"] = "2024-05-06T00:00:00"
    row = parse_rows(exact_json(value).encode(), "congress_v1", limit=20)[0]
    assert row.reported_time is not None and row.reported_time.timestamp is None
    assert row.reported_time.raw_value == "2024-05-06T00:00:00"
    assert row.reported_time.precision is TemporalPrecision.DAY


def test_exact_amounts_ranges_and_no_midpoint() -> None:
    row = parse_rows(content("contracts"), "contracts", limit=20)[0]
    assert row.financial_values[0].value == Decimal("123456.7890123456789")
    v1 = parse_rows(content("congress_v1"), "congress_v1", limit=20)[0]
    assert v1.disclosed_ranges[0].lower_bound == Decimal("1001")
    assert v1.disclosed_ranges[0].upper_bound == Decimal("15000")
    v2 = parse_rows(content("congress_v2"), "congress_v2", limit=20)[0]
    assert v2.disclosed_ranges[0].lower_bound == Decimal("1001.00")
    assert v2.disclosed_ranges[0].upper_bound is None


def test_performance_unknown_fields_quarantined_by_allowlist() -> None:
    value = load_json(content("congress_v1"))
    value[0].update(
        NewPreviouslyUnknownFutureMetric="999",
        Owner="Spouse",
        PrimaryURL="https://example.invalid/not-reviewed",
    )
    row = parse_rows(exact_json(value).encode(), "congress_v1", limit=20)[0]
    quarantine = json.loads(row.quarantined_json)
    assert set(quarantine) == {
        "ExcessReturn",
        "PriceChange",
        "SPYChange",
        "NewPreviouslyUnknownFutureMetric",
        "Owner",
        "PrimaryURL",
    }
    canonical = json.dumps(
        {
            "values": [x.model_dump(mode="json") for x in row.financial_values],
            "ranges": [x.model_dump(mode="json") for x in row.disclosed_ranges],
            "assertions": [x.model_dump(mode="json") for x in row.vendor_assertions],
        }
    )
    assert all(key not in canonical for key in quarantine)
    assert row.ownership == "unknown"


def test_source_subholding_assertions_do_not_merge_owners(tmp_path: Path) -> None:
    result = ingest(QuiverAdapter(DataLayout(tmp_path)), "congress_v2")
    assert [r.subholding_assertion for r in result.rows] == ["Spouse", "Joint"]
    assert all(r.ownership == "unknown" for r in result.rows)
    assert len(result.entities) == 1 and not result.events
    for row in result.rows:
        assert (
            next(a for a in row.vendor_assertions if a.name == "quiver_subholding").value
            == row.subholding_assertion
        )


def seed_primary(
    adapter: QuiverAdapter,
    *,
    event_id: UUID | None = None,
    endpoint: Endpoint = "contracts",
    primary_range: DisclosedRange | None = None,
    primary_values: tuple[FinancialValue, ...] | None = None,
    primary_occurrence: TemporalValue | None = None,
    primary_actors: tuple[EventPartyReference, ...] = (),
) -> tuple[Event, SourceObservation]:
    row = parse_rows(content(endpoint), endpoint, limit=20)[0]
    assert row.occurrence_time is not None and row.reported_time is not None
    manifest = capture_raw_bytes(
        adapter.layout,
        b"INVENTED PRIMARY GOVERNMENT DISCLOSURE; NOT A REAL RECORD",
        provider_namespace="invented.government",
        source_family=FAMILIES[endpoint],
        source_native_id="INVENTED-AWARD-01-ACTION-01",
        source_locator="fixture://invented/government-award-01",
        retrieved_at=NOW - timedelta(days=1),
        adapter_version="invented/1.0.0",
        retention_class=RetentionClass.INTERNAL,
    )
    obs = SourceObservation(
        source_observation_id=uuid4(),
        provider_namespace="invented.government",
        source_native_id="INVENTED-AWARD-01-ACTION-01",
        source_locator=manifest.source_locator,
        lineage=SourceLineage(
            source_family=FAMILIES[endpoint], observation_role=ObservationRole.PRIMARY_SOURCE
        ),
        retrieved_at=manifest.retrieved_at,
        observed_at=manifest.retrieved_at,
        public_time=row.reported_time,
        raw_content_hash=manifest.content_hash,
        adapter_version="invented/1.0.0",
        retention_class=RetentionClass.INTERNAL,
    )
    prov = Provenance(
        provenance_id=uuid4(),
        source_observation_ids=(obs.source_observation_id,),
        derivation_kind=DerivationKind.SYNTHETIC_TEST,
        derived_at=NOW,
        transform_version="invented-primary/1.0.0",
    )
    identity = event_id or uuid4()
    evidence = EventEvidence(
        event_evidence_id=uuid4(),
        event_id=identity,
        source_observation_ids=(obs.source_observation_id,),
        provenance_id=prov.provenance_id,
    )
    event = Event(
        event_id=identity,
        event_type=row.event_type or "unsupported",
        actors=primary_actors,
        occurrence_time=primary_occurrence or row.occurrence_time,
        public_time=row.reported_time,
        actionable_at=datetime(2024, 5, 7, 13, 30, tzinfo=UTC),
        financial_values=primary_values if primary_values is not None else row.financial_values,
        disclosed_ranges=(primary_range,) if primary_range is not None else row.disclosed_ranges,
        event_evidence_ids=(evidence.event_evidence_id,),
        provenance_id=prov.provenance_id,
    )
    adapter.store.persist(SourceObservation, (obs,))
    adapter.store.persist(Provenance, (prov,))
    adapter.store.persist(EventEvidence, (evidence,))
    adapter.store.persist(Event, (event,))
    return event, obs


def link(data: bytes, event: Event, primary: SourceObservation, index: int = 0) -> ReviewedRowLink:
    return ReviewedRowLink(
        raw_sha256=hashlib.sha256(data).hexdigest(),
        row_index=index,
        event_id=event.event_id,
        primary_observation_id=primary.source_observation_id,
        reviewed_at=NOW,
        review_reference="fixture://invented/manual-reconciliation-01",
    )


def test_primary_government_plus_vendor_copy_end_to_end(tmp_path: Path) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    event, primary = seed_primary(adapter)
    first = ingest(adapter, links=(link(content("contracts"), event, primary),))
    assert first.events == (event,) and first.mappings[0].status == "linked"
    assert adapter.store.load(Event) == (event,)  # stronger primary payload untouched
    assert len(adapter.store.load(EventEvidence)) == 2
    assert independent_primary_families(
        event.event_id, adapter.store.load(EventEvidence), adapter.store.load(SourceObservation)
    ) == (FAMILIES["contracts"],)
    assert first.evidence[0].source_observation_ids == (first.source_version_id,)
    assert primary.source_observation_id in first.provenance.source_observation_ids
    catalog = rebuild_catalog(adapter.layout)
    assert query_catalog(catalog, "SELECT count(*) FROM event") == [(1,)]


def test_unknown_public_timing_does_not_enter_predictive_snapshot(tmp_path: Path) -> None:
    result = ingest(QuiverAdapter(DataLayout(tmp_path)), "congress_v2")
    row = result.rows[0]
    assert row.reported_time is not None and row.uploaded_time is not None
    assert row.known_from is row.public_time is row.actionability is None
    feature = FeatureValue(
        feature_value_id=uuid4(),
        name="disclosed_transaction_amount_lower_bound",
        value=row.disclosed_ranges[0].lower_bound,
        known_from=row.known_from,
        source_observation_ids=(result.source_version_id,),
    )
    snapshot = FeatureSnapshot(
        feature_snapshot_id=uuid4(),
        event_id=uuid4(),
        snapshot_at=datetime(2024, 5, 7, 13, 30, tzinfo=UTC),
        feature_version="invented-test/1",
        features=(feature,),
        provenance_id=result.provenance.provenance_id,
    )
    with pytest.raises(PointInTimeViolation):
        validate_feature_snapshot(snapshot)


@pytest.mark.parametrize("role", ["transaction_owner", "economic_owner", "unspecified_filer"])
def test_reporting_lawmaker_does_not_replace_separate_primary_owner(
    tmp_path: Path, role: str
) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    owner_id = uuid4()
    event, primary = seed_primary(
        adapter,
        endpoint="congress_v2",
        primary_actors=(EventPartyReference(entity_id=owner_id, role=role),),
    )
    owner = Entity(
        entity_id=owner_id,
        entity_type=EntityType.PERSON,
        display_name="Invented separately sourced owner",
        provenance_id=event.provenance_id,
    )
    adapter.store.persist(Entity, (owner,))
    result = ingest(adapter, "congress_v2", links=(link(content("congress_v2"), event, primary),))
    assert result.events == (event,) and result.events[0].actors[0].entity_id == owner_id
    assert result.mappings[0].person_id != owner_id
    assert result.rows[0].ownership == "unknown" and result.rows[0].subholding_assertion == "Spouse"
    assert adapter.store.load(Event) == (event,)


def test_genuinely_conflicting_primary_reporting_lawmaker_fails(tmp_path: Path) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    reporter_id = uuid4()
    event, primary = seed_primary(
        adapter,
        endpoint="congress_v2",
        primary_actors=(EventPartyReference(entity_id=reporter_id, role="reporting_lawmaker"),),
    )
    reporter = Entity(
        entity_id=reporter_id,
        entity_type=EntityType.PERSON,
        display_name="Invented different primary reporter",
        provenance_id=event.provenance_id,
    )
    claim = ExternalIdentifier(
        external_identifier_id=uuid4(),
        subject_type=IdentifierSubjectType.ENTITY,
        subject_id=reporter_id,
        identifier_type=ExternalIdentifierType.OTHER,
        namespace=BIOGUIDE,
        value="X999992",
        source_observation_id=primary.source_observation_id,
        provenance_id=event.provenance_id,
        observed_at=NOW,
    )
    adapter.store.persist(Entity, (reporter,))
    adapter.store.persist(ExternalIdentifier, (claim,))
    with pytest.raises(QuiverError, match="reporting lawmaker"):
        ingest(adapter, "congress_v2", links=(link(content("congress_v2"), event, primary),))
    assert not adapter.load_mappings() and adapter.store.load(Event) == (event,)


def test_reviewed_semantic_date_and_range_equivalence_preserve_raw_sources(tmp_path: Path) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    original_range = parse_rows(content("congress_v1"), "congress_v1", limit=20)[
        0
    ].disclosed_ranges[0]
    primary_range = original_range.model_copy(
        update={"raw_text": "$1001-$15000", "parser_version": "invented-primary/2"}
    )
    event, primary = seed_primary(adapter, endpoint="congress_v1", primary_range=primary_range)
    value = load_json(content("congress_v1"))
    value[0]["TransactionDate"] = "2024-05-01T00:00:00"
    data = exact_json(value).encode()
    result = ingest(adapter, "congress_v1", data, links=(link(data, event, primary),))
    assert result.events == (event,)
    assert result.rows[0].occurrence_time is not None
    assert result.rows[0].occurrence_time.raw_value == "2024-05-01T00:00:00"
    assert event.occurrence_time.raw_value == "2024-05-01"
    assert event.disclosed_ranges[0].raw_text != result.rows[0].disclosed_ranges[0].raw_text
    assert event.actionable_at == datetime(2024, 5, 7, 13, 30, tzinfo=UTC)
    assert result.rows[0].actionability is None


@pytest.mark.parametrize(
    "field,changed",
    [
        ("lower_bound", Decimal("1002")),
        ("upper_bound", Decimal("15001")),
        ("currency", "EUR"),
        ("lower_bound", None),
        ("name", "different_financial_role"),
    ],
)
def test_reviewed_range_contradictions_fail_without_invented_bounds(
    tmp_path: Path, field: str, changed: object
) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    primary_range = parse_rows(content("congress_v1"), "congress_v1", limit=20)[0].disclosed_ranges[
        0
    ]
    event, primary = seed_primary(
        adapter,
        endpoint="congress_v1",
        primary_range=primary_range.model_copy(update={field: changed}),
    )
    with pytest.raises(QuiverError, match="financial facts"):
        ingest(adapter, "congress_v1", links=(link(content("congress_v1"), event, primary),))
    assert not adapter.load_mappings() and adapter.store.load(Event) == (event,)


@pytest.mark.parametrize("problem", ["date", "unknown_precision", "amount", "currency", "type"])
def test_reviewed_date_and_financial_contradictions_fail(tmp_path: Path, problem: str) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    row = parse_rows(content("contracts"), "contracts", limit=20)[0]
    occurrence = row.occurrence_time
    values = row.financial_values
    if problem == "date":
        from ragged_claws.ingestion.quiver_parser import day

        occurrence = day("2024-05-02")
    elif problem == "unknown_precision":
        occurrence = TemporalValue(
            raw_value="not available",
            precision=TemporalPrecision.UNKNOWN,
            partial_date=PartialDate(
                raw_value="not available", precision=TemporalPrecision.UNKNOWN
            ),
        )
    elif problem == "amount":
        values = (values[0].model_copy(update={"value": Decimal("1")}),)
    elif problem == "currency":
        values = (values[0].model_copy(update={"currency": "EUR"}),)
    else:
        values = (
            FinancialValue(
                name=values[0].name,
                kind=FinancialValueKind.QUANTITY,
                value=values[0].value,
                unit="contracts",
            ),
        )
    event, primary = seed_primary(adapter, primary_values=values, primary_occurrence=occurrence)
    with pytest.raises(QuiverError, match="contradicts|contradict"):
        ingest(adapter, links=(link(content("contracts"), event, primary),))
    assert adapter.store.load(Event) == (event,) and not adapter.load_mappings()


def test_identical_rows_preserved_and_no_automatic_primary_match(tmp_path: Path) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    event, primary = seed_primary(adapter)
    result = ingest(adapter)  # even exact date/amount match does not create an automatic link
    assert result.mappings[0].status == "unresolved"
    assert adapter.store.load(Event) == (event,)
    assert not result.evidence
    trades = ingest(adapter, "congress_v1")
    assert len(trades.rows) == len(trades.mappings) == 2
    assert trades.rows[0].fact_hash == trades.rows[1].fact_hash
    assert trades.rows[0].row_index != trades.rows[1].row_index
    assert all(m.event_id is None for m in trades.mappings)
    assert primary.source_observation_id not in result.provenance.source_observation_ids


def test_reorder_pages_do_not_create_or_collapse_events(tmp_path: Path) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    first = ingest(adapter, "congress_v2")
    value = list(reversed(load_json(content("congress_v2"))))
    second = ingest(adapter, "congress_v2", exact_json(value).encode())
    third = adapter.ingest(
        content("congress_v2"),
        endpoint="congress_v2",
        source_locator=url("congress_v2", 2),
        retrieved_at=NOW,
        synthetic=True,
    )
    assert {r.fact_hash for r in first.rows} == {r.fact_hash for r in second.rows}
    assert len({first.source_version_id, second.source_version_id, third.source_version_id}) == 3
    assert not adapter.store.load(Event) and len(adapter.store.load(Entity)) == 1


def test_material_linked_revision_keeps_raw_and_stops_publication(tmp_path: Path) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    event, primary = seed_primary(adapter)
    ingest(adapter, links=(link(content("contracts"), event, primary),))
    value = load_json(content("contracts"))
    value[0]["Description"] = "Invented corrected assertion"
    # Decimal-aware serializer avoids binary precision changes in this test correction.
    from ragged_claws.ingestion.quiver_parser import exact_json

    changed = exact_json(value).encode()
    before = {p: p.read_bytes() for p in adapter.layout.curated.glob("*.parquet")}
    with pytest.raises(CanonicalConflictError, match="reconciliation"):
        ingest(adapter, data=changed, links=(link(changed, event, primary),))
    assert all(p.read_bytes() == old for p, old in before.items())
    assert (
        raw_object_path(adapter.layout, hashlib.sha256(changed).hexdigest()).read_bytes() == changed
    )
    assert len(adapter.load_mappings()) == 1


def test_new_performance_fields_add_evidence_without_rewriting_primary(tmp_path: Path) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    event, primary = seed_primary(adapter)
    first = ingest(adapter, links=(link(content("contracts"), event, primary),))
    value = load_json(content("contracts"))
    value[0]["FutureMetricNeverSeenBefore"] = {"return": "999.123"}
    changed = exact_json(value).encode()
    second = ingest(adapter, data=changed, links=(link(changed, event, primary),))
    assert second.events == first.events == (event,)
    assert second.rows[0].fact_hash == first.rows[0].fact_hash
    assert len(adapter.store.load(Event)) == 1
    assert independent_primary_families(
        event.event_id, adapter.store.load(EventEvidence), adapter.store.load(SourceObservation)
    ) == (FAMILIES["contracts"],)


@pytest.mark.parametrize(
    "field,value",
    [
        ("Date", "2024-00-00"),
        ("action_date", "unknown"),
        ("Date", "2024-02-30"),
        ("action_date", "2025-01-01"),
        ("Amount", "NaN"),
    ],
)
def test_invalid_or_contradictory_dates_amounts_preserve_raw(
    tmp_path: Path, field: str, value: str
) -> None:
    changed = load_json(content("contracts"))
    changed[0][field] = value
    data = exact_json(changed).encode()
    adapter = QuiverAdapter(DataLayout(tmp_path))
    with pytest.raises(QuiverError):
        ingest(adapter, data=data)
    assert raw_object_path(adapter.layout, hashlib.sha256(data).hexdigest()).exists()
    assert not adapter.load_mappings()


def test_missing_dates_and_unsupported_transaction_remain_countable(tmp_path: Path) -> None:
    value = load_json(content("congress_v1"))
    value[0].update(
        ReportDate=None, TransactionDate=None, Transaction="Undocumented transaction type"
    )
    result = ingest(QuiverAdapter(DataLayout(tmp_path)), "congress_v1", exact_json(value).encode())
    assert len(result.rows) == 2 and result.rows[0].reported_time is None
    assert result.rows[0].occurrence_time is None and result.rows[0].actionability is None
    assert result.mappings[0].status == "excluded"
    assert "reported_date_not_supplied" in result.rows[0].normalization_notes


@pytest.mark.parametrize("range_text", ["$15,000 - $1,001", "$2,000 - $15,000"])
def test_range_contradictions_fail(range_text: str) -> None:
    value = load_json(content("congress_v1"))
    value[0]["Range"] = range_text
    with pytest.raises(QuiverError):
        parse_rows(exact_json(value).encode(), "congress_v1", limit=20)


def test_unparsed_range_never_manufactures_bound_or_midpoint() -> None:
    value = load_json(content("congress_v1"))
    value[0].update(Range="Invented unrecognized range notation", Amount=None)
    row = parse_rows(exact_json(value).encode(), "congress_v1", limit=20)[0]
    assert row.disclosed_ranges[0].lower_bound is row.disclosed_ranges[0].upper_bound is None
    assert "range_text_not_parsed" in row.normalization_notes


def test_captured_row_coordinates_cannot_be_rebound_on_replay(tmp_path: Path) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    event, primary = seed_primary(adapter)
    first = ingest(adapter)
    with pytest.raises(CanonicalConflictError, match="semantics"):
        ingest(adapter, links=(link(content("contracts"), event, primary),))
    assert adapter.load_mappings() == (first,)


def test_frozen_person_mapping_recovers_own_missing_datasets(tmp_path: Path) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    first = ingest(adapter, "congress_v2")
    for model in (SourceObservation, Provenance, Entity, ExternalIdentifier):
        adapter.store.path_for(model).unlink()
    assert ingest(adapter, "congress_v2") == first
    assert adapter.store.load(Entity) == first.entities


def test_person_name_is_not_identity_and_existing_provenance_is_preserved(tmp_path: Path) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    first = ingest(adapter, "congress_v2")
    value = load_json(content("congress_v2"))
    for row in value:
        row["Name"] = "Invented updated source display"
    second = ingest(adapter, "congress_v2", exact_json(value).encode())
    assert second.entities == first.entities
    value[0]["BioGuideID"] = "X999992"
    third = ingest(adapter, "congress_v2", exact_json(value).encode())
    assert len(third.entities) == 2
    assert len({entity.entity_id for entity in third.entities}) == 2
    assert all(entity.entity_type is EntityType.PERSON for entity in third.entities)


def test_source_backed_primary_person_is_enriched_without_replacement(tmp_path: Path) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    manifest = capture_raw_bytes(
        adapter.layout,
        b'{"fixture":"INVENTED PRIMARY IDENTITY","id":"X999991","name":"Invented primary name"}',
        provider_namespace="invented.bioguide",
        source_family=BIOGUIDE,
        source_native_id="X999991",
        retrieved_at=NOW - timedelta(days=1),
        adapter_version="invented-primary/1",
        retention_class=RetentionClass.INTERNAL,
    )
    obs = SourceObservation(
        source_observation_id=uuid4(),
        provider_namespace="invented.bioguide",
        source_native_id="X999991",
        lineage=SourceLineage(
            source_family=BIOGUIDE, observation_role=ObservationRole.PRIMARY_SOURCE
        ),
        retrieved_at=manifest.retrieved_at,
        observed_at=manifest.retrieved_at,
        raw_content_hash=manifest.content_hash,
        adapter_version="invented-primary/1",
        retention_class=RetentionClass.INTERNAL,
    )
    provenance = Provenance(
        provenance_id=uuid4(),
        source_observation_ids=(obs.source_observation_id,),
        derivation_kind=DerivationKind.SYNTHETIC_TEST,
        derived_at=NOW,
        transform_version="invented-primary/1",
    )
    person = Entity(
        entity_id=uuid4(),
        entity_type=EntityType.PERSON,
        display_name="Invented primary name",
        provenance_id=provenance.provenance_id,
    )
    claim = ExternalIdentifier(
        external_identifier_id=uuid4(),
        subject_type=IdentifierSubjectType.ENTITY,
        subject_id=person.entity_id,
        identifier_type=ExternalIdentifierType.OTHER,
        namespace=BIOGUIDE,
        value="X999991",
        source_observation_id=obs.source_observation_id,
        provenance_id=provenance.provenance_id,
        observed_at=NOW,
    )
    adapter.store.persist(SourceObservation, (obs,))
    adapter.store.persist(Provenance, (provenance,))
    adapter.store.persist(Entity, (person,))
    adapter.store.persist(ExternalIdentifier, (claim,))
    result = ingest(adapter, "congress_v2")
    assert result.entities == (person,)
    assert all(m.person_id == person.entity_id for m in result.mappings)
    assert adapter.store.load(Entity) == (person,)
    assert claim in adapter.store.load(ExternalIdentifier)


def test_distinct_equal_valued_primary_transactions_remain_distinct(tmp_path: Path) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    first, first_obs = seed_primary(adapter, endpoint="congress_v1")
    second, second_obs = seed_primary(adapter, endpoint="congress_v1")
    data = content("congress_v1")
    result = ingest(
        adapter,
        "congress_v1",
        links=(link(data, second, second_obs, 1), link(data, first, first_obs, 0)),
    )
    assert len(result.events) == 2 and {e.event_id for e in result.events} == {
        first.event_id,
        second.event_id,
    }
    assert [reviewed.row_index for reviewed in result.reviewed_links] == [0, 1]
    assert result.rows[0].fact_hash == result.rows[1].fact_hash
    assert len(adapter.store.load(Event)) == 2


def test_valid_empty_page_retains_observation_without_phantom_rows(tmp_path: Path) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    result = ingest(adapter, data=b"[]")
    assert not result.rows and not result.events and not result.entities
    assert len(adapter.store.load(SourceObservation)) == 1


def test_mocked_live_success_keeps_credentials_out_of_capture(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer INVENTED-SECRET"
        return httpx.Response(
            200, headers={"content-type": "application/json"}, content=content("contracts")
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        data = retrieve_quiver(
            client,
            url("contracts"),
            endpoint="contracts",
            token=SecretStr("INVENTED-SECRET"),
            review=review(),
            storage_root=tmp_path,
            at=NOW,
            opt_in=True,
        )
    adapter = QuiverAdapter(DataLayout(tmp_path))
    adapter.ingest(
        data,
        endpoint="contracts",
        source_locator=url("contracts"),
        retrieved_at=NOW,
        review=review(),
    )
    assert len(requests) == 1
    for file in (
        *adapter.layout.raw_objects.glob("*/*"),
        *adapter.layout.raw_manifests.glob("*.json"),
    ):
        assert b"INVENTED-SECRET" not in file.read_bytes()


def test_ambiguous_existing_person_bindings_fail(tmp_path: Path) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    first = ingest(adapter, "congress_v2")
    other = first.entities[0].model_copy(update={"entity_id": uuid4()})
    claim = first.identifier_claims[0].model_copy(
        update={"external_identifier_id": uuid4(), "subject_id": other.entity_id}
    )
    adapter.store.persist(Entity, (other,))
    adapter.store.persist(ExternalIdentifier, (claim,))
    data = content("congress_v2") + b" "
    with pytest.raises(QuiverError, match="ambiguous"):
        ingest(adapter, "congress_v2", data)


def test_conflicting_source_names_do_not_choose_first_row(tmp_path: Path) -> None:
    value = load_json(content("congress_v2"))
    value[0]["Name"] = "Different invented name for same ID"
    adapter = QuiverAdapter(DataLayout(tmp_path))
    with pytest.raises(QuiverError, match="conflicting names"):
        ingest(adapter, "congress_v2", exact_json(value).encode())
    assert not adapter.store.load(Entity)


def test_credential_fields_not_captured(tmp_path: Path) -> None:
    value = load_json(content("contracts"))
    value[0]["api_key"] = "INVENTED-SECRET"
    adapter = QuiverAdapter(DataLayout(tmp_path))
    with pytest.raises(QuiverError, match="before capture") as error:
        ingest(adapter, data=exact_json(value).encode())
    assert "INVENTED-SECRET" not in str(error.value)
    assert not tuple(adapter.layout.raw_objects.glob("*/*"))


def test_cli_only_accepts_explicit_invented_fixture(tmp_path: Path) -> None:
    args = [
        "ingest-quiver-fixture",
        str(FIXTURES / "invented-contracts.json"),
        "--endpoint",
        "contracts",
        "--source-url",
        url("contracts"),
        "--data-dir",
        str(tmp_path),
    ]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2
    assert json.loads(result.output)["rejected_snapshots"] == 1
    result = CliRunner().invoke(app, [*args, "--synthetic"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["counts"] == {"linked": 0, "unresolved": 1, "excluded": 0}
    assert report["unresolved_security_rows"] == 1 and report["predictive_features_emitted"] == 0
    assert report["synthetic"] is True


@pytest.mark.parametrize(
    "problem",
    ["wrong_hash", "wrong_primary", "wrong_family", "no_event", "duplicate_link", "bad_coordinate"],
)
def test_invalid_reviewed_links_no_analytical_publication(tmp_path: Path, problem: str) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    event, primary = seed_primary(adapter)
    reviewed = link(content("contracts"), event, primary)
    if problem == "wrong_hash":
        reviewed = reviewed.model_copy(update={"raw_sha256": "0" * 64})
    elif problem == "wrong_primary":
        reviewed = reviewed.model_copy(update={"primary_observation_id": uuid4()})
    elif problem == "wrong_family":
        other = primary.model_copy(
            update={
                "source_observation_id": uuid4(),
                "lineage": SourceLineage(
                    source_family="wrong.family", observation_role=ObservationRole.PRIMARY_SOURCE
                ),
            }
        )
        adapter.store.persist(SourceObservation, (other,))
        reviewed = reviewed.model_copy(
            update={"primary_observation_id": other.source_observation_id}
        )
    elif problem == "no_event":
        reviewed = reviewed.model_copy(update={"event_id": uuid4()})
    elif problem == "bad_coordinate":
        reviewed = reviewed.model_copy(update={"row_index": 9})
    reviews = (reviewed, reviewed) if problem == "duplicate_link" else (reviewed,)
    with pytest.raises(QuiverError):
        ingest(adapter, links=reviews)
    assert not adapter.load_mappings()
    assert adapter.store.load(Event) == (event,)


def test_unknown_rows_frozen_after_later_primary_catalog_enrichment(tmp_path: Path) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    first = ingest(adapter)
    seed_primary(adapter)
    assert ingest(adapter) == first
    assert first.mappings[0].status == "unresolved"


@pytest.mark.parametrize(
    "bad",
    [b'{"error":"invented error"}', b'[{"Ticker":"x","Ticker":"y"}]', b"[NaN]", b"[] trailing"],
)
def test_malformed_input_fails_after_raw_capture(tmp_path: Path, bad: bytes) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    with pytest.raises(QuiverError):
        ingest(adapter, data=bad)
    assert not adapter.load_mappings() and not adapter.store.load(SourceObservation)
    assert raw_object_path(adapter.layout, hashlib.sha256(bad).hexdigest()).exists()


def review(endpoint: Endpoint = "contracts") -> QuiverAccessReview:
    return QuiverAccessReview(
        agreement_sha256="a" * 64,
        reviewed_at=NOW - timedelta(days=1),
        entitled_endpoints=(endpoint,),
        local_raw_retention_permitted=True,
        local_derived_retention_permitted=True,
        root_is_not_synced_or_shared=True,
    )


def test_real_ingestion_requires_review_before_any_raw_capture(tmp_path: Path) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path))
    with pytest.raises(QuiverError, match="review required"):
        adapter.ingest(
            content("contracts"),
            endpoint="contracts",
            source_locator=url("contracts"),
            retrieved_at=NOW,
        )
    assert not tuple(adapter.layout.raw_objects.glob("*/*"))


def test_restricted_retention_and_no_cloud_git_state(tmp_path: Path) -> None:
    adapter = QuiverAdapter(DataLayout(tmp_path / "private"))
    result = adapter.ingest(
        content("contracts"),
        endpoint="contracts",
        source_locator=url("contracts"),
        retrieved_at=NOW,
        review=review(),
    )
    assert result.observation.retention_class is RetentionClass.RESTRICTED
    assert result.license_review_sha256 == "a" * 64
    for root in (tmp_path / "OneDrive" / "data", tmp_path / "gitrepo" / "data"):
        if "gitrepo" in str(root):
            (root.parent / ".git").mkdir(parents=True)
        target = QuiverAdapter(DataLayout(root))
        with pytest.raises(QuiverError):
            target.ingest(
                content("contracts"),
                endpoint="contracts",
                source_locator=url("contracts"),
                retrieved_at=NOW,
                review=review(),
            )
        assert not tuple(target.layout.raw_objects.glob("*/*"))
        with pytest.raises(QuiverError):
            target.persist(result, review=review())
        assert not target.load_mappings()


@pytest.mark.parametrize(
    "problem", ["no_review", "no_token", "no_optin", "denied", "redirect", "challenge", "network"]
)
def test_live_boundary_offline_and_redacted(tmp_path: Path, problem: str) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer INVENTED-SECRET"
        if problem == "network":
            raise httpx.ConnectError("INVENTED-SECRET", request=request)
        status = 403 if problem == "denied" else 302 if problem == "redirect" else 200
        return httpx.Response(
            status, headers={"content-type": "text/html"}, content=b"invented challenge"
        )

    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as client,
        pytest.raises(QuiverError) as error,
    ):
        retrieve_quiver(
            client,
            url("contracts"),
            endpoint="contracts",
            token=SecretStr("" if problem == "no_token" else "INVENTED-SECRET"),
            review=None if problem == "no_review" else review(),
            storage_root=tmp_path,
            at=NOW,
            opt_in=problem != "no_optin",
        )
    assert "INVENTED-SECRET" not in str(error.value)
    assert len(requests) == (0 if problem in ("no_review", "no_token", "no_optin") else 1)


@pytest.mark.parametrize(
    "locator",
    [
        "https://api.quiverquant.com/beta/live/govcontractsall?token=INVENTED-SECRET",
        "https://evil.invalid/beta/live/govcontractsall",
        "https://api.quiverquant.com/beta/live/govcontractsall?page=1&page_size=101",
        "https://api.quiverquant.com/beta/live/govcontractsall?page=0&page_size=20",
    ],
)
def test_request_allowlist_rejects_secrets_and_scope(locator: str) -> None:
    with pytest.raises(QuiverError) as error:
        request_identity(locator, "contracts")
    assert "INVENTED-SECRET" not in str(error.value)
