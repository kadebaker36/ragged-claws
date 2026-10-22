"""Offline recorded-data contract and adversarial LittleSis snapshot regression tests."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from typer.testing import CliRunner

from ragged_claws.cli import app
from ragged_claws.ingestion.littlesis import (
    IDENTIFIER_NAMESPACE,
    LittleSisAdapter,
    request_identity,
    retrieve_snapshot,
)
from ragged_claws.ingestion.littlesis_models import LittleSisBundle
from ragged_claws.ingestion.littlesis_parser import LittleSisError, parse_snapshot, partial_date
from ragged_claws.models import (
    Entity,
    EntityType,
    ExternalIdentifier,
    FeatureSnapshot,
    FeatureValue,
    Provenance,
    Relationship,
    SourceObservation,
    TemporalPrecision,
)
from ragged_claws.storage import CanonicalConflictError, DataLayout, capture_raw_bytes
from ragged_claws.storage.catalog import query_catalog, rebuild_catalog
from ragged_claws.storage.raw import raw_object_path
from ragged_claws.temporal import (
    PointInTimeViolation,
    evaluate_eligibility,
    validate_feature_snapshot,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "littlesis"
URL = "https://littlesis.org/api/relationships/1565630"
COLLECTED = datetime(2026, 10, 22, 21, 56, 18, 664182, tzinfo=UTC)


def recorded() -> bytes:
    return (FIXTURES / "recorded-1565630.json").read_bytes()


def payload() -> dict[str, Any]:
    result: dict[str, Any] = json.loads(recorded())
    return result


def ingest(adapter: LittleSisAdapter, value: dict[str, Any] | None = None) -> LittleSisBundle:
    return adapter.ingest(
        recorded() if value is None else json.dumps(value).encode(),
        source_locator=URL,
        retrieved_at=COLLECTED,
    )


def test_recorded_person_company_provenance_and_no_historical_leak(tmp_path: Path) -> None:
    adapter = LittleSisAdapter(DataLayout(tmp_path))
    bundle = ingest(adapter)
    relation = bundle.relationships[0]
    by_id = {e.entity_id: e for e in bundle.entities}
    assert by_id[relation.source.subject_id].display_name == "Robert Mercer"
    assert by_id[relation.source.subject_id].entity_type is EntityType.PERSON
    assert by_id[relation.target.subject_id].display_name == "Renaissance Technologies LLC"
    assert by_id[relation.target.subject_id].entity_type is EntityType.ORGANIZATION
    assert relation.relationship_type == "position"
    assert relation.valid_from is not None and relation.valid_from.partial_date is not None
    assert relation.valid_from.raw_value == "2010-01-00"
    assert relation.valid_from.precision is TemporalPrecision.MONTH
    assert relation.valid_from.partial_date.day is None
    assert relation.valid_to is relation.known_from is relation.known_to is None
    assert relation.observed_at == COLLECTED
    assert bundle.observation.public_time is None
    assert bundle.observation.raw_content_hash.value == hashlib.sha256(recorded()).hexdigest()
    assert (
        raw_object_path(adapter.layout, bundle.observation.raw_content_hash.value).read_bytes()
        == recorded()
    )
    resource = next(r for r in bundle.snapshot.resources if r.source_type == "relationships")
    assert resource.curated_at == datetime(2019, 7, 8, 21, 33, 58, tzinfo=UTC)
    assert json.loads(resource.payload_json)["attributes"]["is_current"] is None
    assert "https://littlesis.org/relationships/1565630" in resource.source_urls
    for year in (2010, 2019, 2026, 2027):
        assert not evaluate_eligibility(
            snapshot_at=datetime(year, 12, 1, tzinfo=UTC),
            known_from=relation.known_from,
            observed_at=relation.observed_at,
            valid_from=relation.valid_from,
        ).eligible
    assert adapter.store.load(Relationship) == bundle.relationships
    assert bundle.provenance.source_observation_ids == relation.source_observation_ids
    assert bundle.observation.license_name == "CC-BY-SA-4.0"
    assert (
        "LittleSis" in bundle.attribution
        and "No primary-document verification" in bundle.change_notice
    )
    assert all(
        c.namespace == IDENTIFIER_NAMESPACE and c.known_from is None
        for c in bundle.identifier_claims
    )
    feature = FeatureValue(
        feature_value_id=uuid4(),
        name="relationship_context",
        value=True,
        known_from=relation.known_from,
        source_observation_ids=relation.source_observation_ids,
    )
    snapshot = FeatureSnapshot(
        feature_snapshot_id=uuid4(),
        event_id=uuid4(),
        snapshot_at=datetime(2020, 1, 1, tzinfo=UTC),
        feature_version="test/1.0.0",
        features=(feature,),
        provenance_id=bundle.provenance.provenance_id,
    )
    with pytest.raises(PointInTimeViolation):
        validate_feature_snapshot(snapshot)
    catalog = rebuild_catalog(adapter.layout)
    assert query_catalog(catalog, "SELECT count(*) FROM relationship") == [(1,)]
    assert rebuild_catalog(adapter.layout) == catalog
    assert query_catalog(catalog, "SELECT count(*) FROM relationship") == [(1,)]


def test_recorded_hashes_and_license() -> None:
    for name, metadata_name, hash_key in (
        ("recorded-1565630.json", "recorded-1565630-provenance.json", "sha256"),
        ("recorded-297069.json", "recorded-provenance.json", "response_sha256"),
        ("recorded-position-page.json", "recorded-position-page-provenance.json", "sha256"),
    ):
        content = (FIXTURES / name).read_bytes()
        metadata = json.loads((FIXTURES / metadata_name).read_bytes())
        assert hashlib.sha256(content).hexdigest() == metadata[hash_key]
        snapshot = parse_snapshot(content, observation_id=uuid4())
        assert snapshot.license_url == "https://creativecommons.org/licenses/by-sa/4.0/"
        assert metadata["url"].startswith("https://littlesis.org/api/")


def test_recorded_donation_and_bounded_page_unresolved(tmp_path: Path) -> None:
    adapter = LittleSisAdapter(DataLayout(tmp_path))
    donation = adapter.ingest(
        (FIXTURES / "recorded-297069.json").read_bytes(),
        source_locator="https://littlesis.org/api/relationships/297069",
        retrieved_at=COLLECTED,
    )
    assert donation.relationships[0].valid_from is not None
    assert donation.relationships[0].valid_from.precision is TemporalPrecision.YEAR
    assert donation.relationships[0].valid_to is not None
    assert donation.relationships[0].valid_to.raw_value == "2017-05-09"
    # Page has no included entities; an existing person alone cannot resolve its company.
    page = adapter.ingest(
        (FIXTURES / "recorded-position-page.json").read_bytes(),
        source_locator="https://littlesis.org/api/entities/72489/relationships?category_id=1&per_page=1",
        retrieved_at=COLLECTED,
    )
    assert not page.relationships
    assert page.mappings[0].reason == "unresolved_endpoint"


@pytest.mark.parametrize(
    ("raw", "precision"),
    [
        ("2010", TemporalPrecision.YEAR),
        ("2010-00-00", TemporalPrecision.YEAR),
        ("2010-01", TemporalPrecision.MONTH),
        ("2010-01-00", TemporalPrecision.MONTH),
        ("2012-02-29", TemporalPrecision.DAY),
    ],
)
def test_partial_dates(raw: str, precision: TemporalPrecision) -> None:
    value = partial_date(raw)
    assert value is not None and value.precision is precision and value.raw_value == raw
    assert value.timestamp is None


@pytest.mark.parametrize(
    "raw", ["2010-00-02", "2010-13-00", "2011-02-29", "unknown", "0000", 2010, True]
)
def test_invalid_dates(raw: Any) -> None:
    with pytest.raises(LittleSisError):
        partial_date(raw)


def test_unknown_and_inverted_dates(tmp_path: Path) -> None:
    assert partial_date(None) is partial_date("") is None
    value = payload()
    value["data"]["attributes"].update(start_date="2020-00-00", end_date="2010-00-00")
    with pytest.raises(LittleSisError, match="provably"):
        ingest(LittleSisAdapter(DataLayout(tmp_path)), value)


def test_idempotent_first_seen_and_restore(tmp_path: Path) -> None:
    adapter = LittleSisAdapter(DataLayout(tmp_path))
    first = ingest(adapter)
    later = adapter.ingest(
        recorded(), source_locator=URL, retrieved_at=COLLECTED + timedelta(days=1)
    )
    assert later == first and len(adapter.load_mappings()) == 1
    for model in (SourceObservation, Provenance, Entity, ExternalIdentifier, Relationship):
        adapter.store.path_for(model).unlink()
    assert ingest(adapter) == first
    assert adapter.store.load(Entity) == first.entities
    assert adapter.store.load(Relationship) == first.relationships


def test_unrelated_changes_and_curation_reuse_exact_relationship(tmp_path: Path) -> None:
    adapter = LittleSisAdapter(DataLayout(tmp_path))
    first = ingest(adapter)
    value = payload()
    value["included"][0]["attributes"].update(
        name="Changed source display", blurb="Changed profile"
    )
    value["data"]["attributes"]["updated_at"] = "2026-10-22T20:00:00Z"
    value["included"].reverse()
    later = ingest(adapter, value)
    assert later.source_version_id != first.source_version_id
    assert later.relationships == first.relationships
    assert later.entities == first.entities
    assert later.provenance != first.provenance
    assert len(adapter.store.load(Relationship)) == 1
    assert len(adapter.load_mappings()) == 2
    assert next(m for m in later.mappings if m.source_type == "relationships").status == "reused"
    assert first.relationships[0].source_observation_ids == (first.source_version_id,)


def test_recorded_page_adds_evidence_without_duplicate_fact(tmp_path: Path) -> None:
    adapter = LittleSisAdapter(DataLayout(tmp_path))
    first = ingest(adapter)
    url = "https://littlesis.org/api/entities/72489/relationships?category_id=1&per_page=1"
    later = adapter.ingest(
        (FIXTURES / "recorded-position-page.json").read_bytes(),
        source_locator=url,
        retrieved_at=COLLECTED + timedelta(days=1),
    )
    assert later.relationships == first.relationships
    assert later.observation.source_observation_id != first.observation.source_observation_id
    assert len(adapter.store.load(Relationship)) == 1
    assert later.mappings[0].status == "reused"


def test_frozen_unresolved_replay_survives_later_identity_enrichment(tmp_path: Path) -> None:
    adapter = LittleSisAdapter(DataLayout(tmp_path))
    content = (FIXTURES / "recorded-position-page.json").read_bytes()
    url = "https://littlesis.org/api/entities/72489/relationships?category_id=1&per_page=1"
    first = adapter.ingest(content, source_locator=url, retrieved_at=COLLECTED)
    assert not first.relationships
    ingest(adapter)
    replay = adapter.ingest(content, source_locator=url, retrieved_at=COLLECTED + timedelta(days=1))
    assert replay == first and replay.mappings[0].status == "unresolved"


def test_canonical_conflict_preflight_does_not_partially_publish(tmp_path: Path) -> None:
    prior = ingest(LittleSisAdapter(DataLayout(tmp_path / "prior")))
    adapter = LittleSisAdapter(DataLayout(tmp_path / "target"))
    conflicting = prior.relationships[0].model_copy(update={"relationship_type": "other"})
    adapter.store.persist(Relationship, (conflicting,))
    original = adapter.store.path_for(Relationship).read_bytes()
    with pytest.raises(CanonicalConflictError):
        ingest(adapter)
    assert adapter.store.path_for(Relationship).read_bytes() == original
    assert not adapter.load_mappings()
    assert not adapter.store.load(SourceObservation) and not adapter.store.load(Entity)


def test_material_revision_keeps_raw_and_rejects_before_publication(tmp_path: Path) -> None:
    adapter = LittleSisAdapter(DataLayout(tmp_path))
    first = ingest(adapter)
    before = {
        p: p.read_bytes() for p in (*adapter.layout.curated.glob("*.parquet"), adapter.mapping_path)
    }
    value = payload()
    value["data"]["attributes"]["description1"] = "different assertion"
    content = json.dumps(value).encode()
    with pytest.raises(CanonicalConflictError, match="reconciliation"):
        ingest(adapter, value)
    assert (
        raw_object_path(adapter.layout, hashlib.sha256(content).hexdigest()).read_bytes() == content
    )
    assert all(path.read_bytes() == old for path, old in before.items())
    assert adapter.store.load(Relationship) == first.relationships


def test_names_not_identity_and_distinct_source_edges(tmp_path: Path) -> None:
    adapter = LittleSisAdapter(DataLayout(tmp_path))
    value = payload()
    value["included"][1]["attributes"]["name"] = value["included"][0]["attributes"]["name"]
    first = ingest(adapter, value)
    assert len({e.entity_id for e in first.entities}) == 2
    value["data"]["id"] = value["data"]["attributes"]["id"] = 1565631
    second = adapter.ingest(
        json.dumps(value).encode(),
        source_locator=URL.replace("1565630", "1565631"),
        retrieved_at=COLLECTED,
    )
    assert second.relationships[0].relationship_id != first.relationships[0].relationship_id
    assert len(adapter.store.load(Relationship)) == 2


@pytest.mark.parametrize("mutation", ["missing", "unknown_type", "category"])
def test_unresolved_excluded_no_orphans(tmp_path: Path, mutation: str) -> None:
    value = payload()
    if mutation == "missing":
        value["included"].pop()
    elif mutation == "unknown_type":
        value["included"][1]["attributes"]["primary_ext"] = "Unknown"
    else:
        value["data"]["attributes"]["category_id"] = 999
    bundle = ingest(LittleSisAdapter(DataLayout(tmp_path)), value)
    assert not bundle.relationships
    mapping = next(m for m in bundle.mappings if m.source_type == "relationships")
    assert mapping.status == ("excluded" if mutation == "category" else "unresolved")


@pytest.mark.parametrize("mutation", ["id", "license", "api", "current", "naive", "duplicate"])
def test_malformed_snapshot_no_curated_publication(tmp_path: Path, mutation: str) -> None:
    value = payload()
    if mutation == "id":
        value["data"]["attributes"]["id"] = 42
    elif mutation == "license":
        value["meta"]["license"] = "unknown"
    elif mutation == "api":
        value["meta"]["apiVersion"] = "3.0"
    elif mutation == "current":
        value["data"]["attributes"]["is_current"] = "false"
    elif mutation == "naive":
        value["data"]["attributes"]["updated_at"] = "2020-01-01T12:00:00"
    else:
        other = json.loads(json.dumps(value["included"][0]))
        other["attributes"]["name"] = "contradictory duplicate"
        value["included"].append(other)
    adapter = LittleSisAdapter(DataLayout(tmp_path))
    with pytest.raises(LittleSisError):
        ingest(adapter, value)
    assert not list(adapter.layout.curated.glob("*.parquet"))
    assert not adapter.load_mappings()


def test_duplicate_json_keys() -> None:
    with pytest.raises(LittleSisError):
        parse_snapshot(b'{"data":{},"data":[]}', observation_id=uuid4())


@pytest.mark.parametrize(
    "problem", ["entity", "category", "type", "count", "page", "bad_page_count"]
)
def test_list_request_body_agreement(tmp_path: Path, problem: str) -> None:
    value = json.loads((FIXTURES / "recorded-position-page.json").read_bytes())
    url = "https://littlesis.org/api/entities/72489/relationships?category_id=1&per_page=1"
    if problem == "entity":
        url = url.replace("72489", "999999")
    elif problem == "category":
        value["data"][0]["attributes"]["category_id"] = 5
    elif problem == "type":
        value["data"] = [payload()["included"][0]]
    elif problem == "count":
        value["data"] *= 2
    elif problem == "page":
        value["meta"]["currentPage"] = 2
    else:
        value["meta"]["pageCount"] = -1
    adapter = LittleSisAdapter(DataLayout(tmp_path))
    content = json.dumps(value).encode()
    with pytest.raises(LittleSisError):
        adapter.ingest(content, source_locator=url, retrieved_at=COLLECTED)
    assert not adapter.load_mappings() and not adapter.store.load(SourceObservation)
    assert raw_object_path(adapter.layout, hashlib.sha256(content).hexdigest()).exists()


def test_list_allows_either_endpoint_and_included_context(tmp_path: Path) -> None:
    value = json.loads((FIXTURES / "recorded-position-page.json").read_bytes())
    value["included"] = payload()["included"]
    url = "https://littlesis.org/api/entities/102097/relationships?category_id=1&per_page=1"
    bundle = LittleSisAdapter(DataLayout(tmp_path)).ingest(
        json.dumps(value).encode(), source_locator=url, retrieved_at=COLLECTED
    )
    assert len(bundle.relationships) == 1


def test_valid_empty_page_is_retained(tmp_path: Path) -> None:
    value = json.loads((FIXTURES / "recorded-position-page.json").read_bytes())
    value["data"] = []
    value["meta"]["pageCount"] = 0
    url = "https://littlesis.org/api/entities/72489/relationships?per_page=1"
    adapter = LittleSisAdapter(DataLayout(tmp_path))
    result = adapter.ingest(json.dumps(value).encode(), source_locator=url, retrieved_at=COLLECTED)
    assert not result.relationships and not result.mappings
    assert len(adapter.store.load(SourceObservation)) == 1


def seed_identity_catalog(
    adapter: LittleSisAdapter,
    bundle: LittleSisBundle,
    entities: tuple[Entity, ...],
    claims: tuple[ExternalIdentifier, ...],
) -> None:
    obs = bundle.observation
    capture_raw_bytes(
        adapter.layout,
        recorded(),
        provider_namespace=obs.provider_namespace,
        source_family=obs.lineage.source_family,
        retrieved_at=obs.retrieved_at,
        adapter_version=obs.adapter_version,
        retention_class=obs.retention_class,
    )
    adapter.store.persist(SourceObservation, (obs,))
    adapter.store.persist(Provenance, (bundle.provenance,))
    adapter.store.persist(Entity, entities)
    adapter.store.persist(ExternalIdentifier, claims)


def test_source_backed_binding_preserves_stronger_identity(tmp_path: Path) -> None:
    prior = ingest(LittleSisAdapter(DataLayout(tmp_path / "prior")))
    adapter = LittleSisAdapter(DataLayout(tmp_path / "target"))
    company = next(e for e in prior.entities if e.entity_type is EntityType.ORGANIZATION)
    primary = company.model_copy(
        update={
            "entity_id": uuid4(),
            "entity_type": EntityType.ISSUER,
            "display_name": "Primary issuer name",
        }
    )
    claim = next(c for c in prior.identifier_claims if c.subject_id == company.entity_id)
    claim = claim.model_copy(
        update={"external_identifier_id": uuid4(), "subject_id": primary.entity_id}
    )
    seed_identity_catalog(adapter, prior, (primary,), (claim,))
    result = ingest(adapter)
    assert result.relationships[0].target.subject_id == primary.entity_id
    assert primary in result.entities
    assert (
        next(e for e in adapter.store.load(Entity) if e.entity_id == primary.entity_id) == primary
    )
    assert len(adapter.store.load(ExternalIdentifier)) == 3


@pytest.mark.parametrize(
    "problem", ["ambiguous", "missing_subject", "missing_evidence", "wrong_kind", "corrupt_raw"]
)
def test_invalid_existing_bindings_fail_explicitly(tmp_path: Path, problem: str) -> None:
    prior = ingest(LittleSisAdapter(DataLayout(tmp_path / "prior")))
    adapter = LittleSisAdapter(DataLayout(tmp_path / "target"))
    person = next(e for e in prior.entities if e.entity_type is EntityType.PERSON)
    claim = next(c for c in prior.identifier_claims if c.subject_id == person.entity_id)
    entities: tuple[Entity, ...] = (person,)
    claims: tuple[ExternalIdentifier, ...] = (claim,)
    if problem == "ambiguous":
        other = person.model_copy(update={"entity_id": uuid4()})
        entities += (other,)
        claims += (
            claim.model_copy(
                update={"external_identifier_id": uuid4(), "subject_id": other.entity_id}
            ),
        )
    elif problem == "missing_subject":
        entities = ()
    elif problem == "missing_evidence":
        claims = (claim.model_copy(update={"source_observation_id": uuid4()}),)
    elif problem == "wrong_kind":
        entities = (person.model_copy(update={"entity_type": EntityType.HOUSEHOLD}),)
    seed_identity_catalog(adapter, prior, entities, claims)
    if problem == "corrupt_raw":
        raw_object_path(adapter.layout, prior.observation.raw_content_hash.value).write_bytes(
            b"corrupt"
        )
    with pytest.raises((LittleSisError, RuntimeError)):
        ingest(adapter)
    assert not adapter.store.load(Relationship)
    assert not adapter.load_mappings()


@pytest.mark.parametrize("current", [True, False, None])
def test_current_status_does_not_invent_end_or_knowledge(
    tmp_path: Path, current: bool | None
) -> None:
    value = payload()
    value["data"]["attributes"]["is_current"] = current
    relation = ingest(LittleSisAdapter(DataLayout(tmp_path)), value).relationships[0]
    assert relation.valid_to is relation.known_from is None


def test_same_day_effective_dates_not_rejected(tmp_path: Path) -> None:
    value = payload()
    value["data"]["attributes"].update(
        start_date="2011-08-15", end_date="2011-08-15", is_current=False
    )
    relation = ingest(LittleSisAdapter(DataLayout(tmp_path)), value).relationships[0]
    assert relation.valid_from == relation.valid_to


@pytest.mark.parametrize(
    ("status", "content_type", "body"),
    [
        (403, "text/html", b"denied"),
        (200, "text/html", b"challenge"),
        (302, "application/json", b"{}"),
        (429, "application/json", b"{}"),
    ],
)
def test_access_stops_after_one_request(status: int, content_type: str, body: bytes) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert "sec" not in request.headers["User-Agent"].lower()
        return httpx.Response(status, headers={"content-type": content_type}, content=body)

    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as client,
        pytest.raises(LittleSisError, match="access unavailable"),
    ):
        retrieve_snapshot(client, URL)
    assert len(requests) == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://littlesis.org/api",
        "http://littlesis.org/api/entities/1",
        "https://littlesis.org/api/entities/1/relationships",
        "https://littlesis.org/api/entities/1/relationships?per_page=100",
        "https://littlesis.org/api/entities/1?token=secret",
        "https://example.com/api/entities/1",
    ],
)
def test_bounded_locators(url: str) -> None:
    with pytest.raises(LittleSisError):
        request_identity(url)


def test_cli_reports_counts_and_rejections(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "ingest-littlesis",
            str(FIXTURES / "recorded-1565630.json"),
            "--source-url",
            URL,
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert summary["counts"]["imported"] == 3
    assert summary["pit_ineligible_relationships"] == 1
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    result = CliRunner().invoke(
        app, ["ingest-littlesis", str(bad), "--source-url", URL, "--data-dir", str(tmp_path)]
    )
    assert result.exit_code == 2
    assert json.loads(result.output)["rejected_snapshots"] == 1
