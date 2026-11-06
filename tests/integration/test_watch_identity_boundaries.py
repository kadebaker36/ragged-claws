"""Review regressions for canonical known-time and historical identity projections."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from ragged_claws.models import (
    Entity,
    EntityType,
    Event,
    EventEvidence,
    EventPartyReference,
    ExternalIdentifier,
    ExternalIdentifierType,
    IdentifierSubjectType,
    Listing,
    Provenance,
    Security,
    SourceObservation,
    TemporalPrecision,
    TemporalValue,
)
from ragged_claws.resolution import day_value
from ragged_claws.storage import CanonicalParquetStore, DataLayout
from ragged_claws.temporal import evaluate_eligibility
from ragged_claws.watch.ledger import CanonicalWatch, build_report, encoded, render_markdown
from tests.integration.test_purchase_watch import AS_OF, OBSERVED, add_vendor_copy, bind, ingest
from tests.model_helpers import partial_temporal


def exact(instant: datetime) -> TemporalValue:
    return TemporalValue(
        raw_value=instant.isoformat(), precision=TemporalPrecision.SECOND, timestamp=instant
    )


def actor_catalog(
    layout: DataLayout, *, known_from: TemporalValue | None
) -> tuple[CanonicalParquetStore, ExternalIdentifier]:
    store = ingest(layout)
    events = store.load(Event)
    entity = Entity(
        entity_id=UUID(int=500),
        entity_type=EntityType.PERSON,
        display_name="Invented resolved person",
        provenance_id=events[0].provenance_id,
    )
    claim = ExternalIdentifier(
        external_identifier_id=UUID(int=501),
        subject_type=IdentifierSubjectType.ENTITY,
        subject_id=entity.entity_id,
        identifier_type=ExternalIdentifierType.SEC_CIK,
        value="0000315090",
        source_observation_id=store.load(SourceObservation)[0].source_observation_id,
        provenance_id=events[0].provenance_id,
        observed_at=OBSERVED,
        known_from=known_from,
    )
    store.persist(Entity, (entity,))
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
    return store, claim


@pytest.mark.parametrize(
    "known_from",
    [
        exact(OBSERVED),
        exact(AS_OF),
        None,
        exact(AS_OF + timedelta(seconds=1)),
        partial_temporal("2024-09-11", TemporalPrecision.DAY, year=2024, month=9, day=11),
        partial_temporal("2024-09", TemporalPrecision.MONTH, year=2024, month=9),
        partial_temporal("2024", TemporalPrecision.YEAR, year=2024),
        partial_temporal("unknown", TemporalPrecision.UNKNOWN),
    ],
)
@pytest.mark.parametrize("nested", [False, True])
def test_actor_claim_requires_temporal_helper_eligibility(
    tmp_path: Path,
    known_from: TemporalValue | None,
    nested: bool,
) -> None:
    layout = DataLayout(tmp_path)
    store, claim = actor_catalog(layout, known_from=known_from)
    if nested:
        entity = next(e for e in store.load(Entity) if e.entity_id == claim.subject_id)
        entities = store.load(Entity)
        store.path_for(Entity).unlink()
        store.persist(
            Entity,
            tuple(
                e.model_copy(update={"external_identifiers": (claim,)}) if e == entity else e
                for e in entities
            ),
        )
    else:
        store.persist(ExternalIdentifier, (claim,))
    expected = evaluate_eligibility(
        snapshot_at=AS_OF, known_from=claim.known_from, observed_at=claim.observed_at
    ).eligible
    report = build_report(layout, as_of=AS_OF)
    assert len(report.candidates) == 3
    for candidate in report.candidates:
        actor = next(a for a in candidate.actors if a.reference == "sec_cik:0000315090")
        assert actor.entity_id == (claim.subject_id if expected else None)
        assert actor.entity_resolution_status == (
            "resolved" if expected else "source_reference_only"
        )


@pytest.mark.parametrize(
    "known_from,boundary",
    [
        (
            partial_temporal("2024-09-11", TemporalPrecision.DAY, year=2024, month=9, day=11),
            datetime(2024, 9, 12, tzinfo=UTC),
        ),
        (
            partial_temporal("2024-09", TemporalPrecision.MONTH, year=2024, month=9),
            datetime(2024, 10, 1, tzinfo=UTC),
        ),
        (
            partial_temporal("2024", TemporalPrecision.YEAR, year=2024),
            datetime(2025, 1, 1, tzinfo=UTC),
        ),
    ],
)
def test_coarse_actor_knowledge_uses_shared_eligibility_boundaries(
    tmp_path: Path,
    known_from: TemporalValue,
    boundary: datetime,
) -> None:
    store, claim = actor_catalog(DataLayout(tmp_path), known_from=known_from)
    store.persist(ExternalIdentifier, (claim,))
    watch = CanonicalWatch(store)
    for instant in (boundary - timedelta(microseconds=1), boundary):
        candidate, _ = watch.candidate(watch.events[0], instant)
        assert candidate is not None
        actor = next(a for a in candidate.actors if a.reference == "sec_cik:0000315090")
        expected = evaluate_eligibility(snapshot_at=instant, known_from=known_from).eligible
        assert actor.entity_id == (claim.subject_id if expected else None)


@pytest.mark.parametrize("observation_state", ["missing", "observed_late", "retrieved_late"])
def test_claim_needs_its_own_visible_observation(
    tmp_path: Path,
    observation_state: str,
) -> None:
    layout = DataLayout(tmp_path)
    store, claim = actor_catalog(layout, known_from=exact(OBSERVED))
    before = build_report(layout, as_of=AS_OF)
    observation = store.load(SourceObservation)[0].model_copy(
        update={
            "source_observation_id": UUID(int=502),
            "observed_at": AS_OF + timedelta(seconds=1)
            if observation_state == "observed_late"
            else OBSERVED,
            "retrieved_at": AS_OF + timedelta(seconds=1)
            if observation_state == "retrieved_late"
            else OBSERVED,
        }
    )
    if observation_state != "missing":
        store.persist(SourceObservation, (observation,))
    # Provenance is intentionally early but the claim's separately referenced observation is not.
    store.persist(
        ExternalIdentifier,
        (
            claim.model_copy(
                update={
                    "source_observation_id": observation.source_observation_id,
                }
            ),
        ),
    )
    after = build_report(layout, as_of=AS_OF)
    assert encoded(after) == encoded(before)
    assert render_markdown(after) == render_markdown(before)


def test_later_added_eligible_claim_cannot_change_earlier_report(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    store, claim = actor_catalog(layout, known_from=exact(OBSERVED))
    before = build_report(layout, as_of=AS_OF)
    store.persist(
        ExternalIdentifier,
        (
            claim.model_copy(
                update={
                    "observed_at": AS_OF + timedelta(seconds=1),
                }
            ),
        ),
    )
    assert encoded(build_report(layout, as_of=AS_OF)) == encoded(before)
    assert render_markdown(build_report(layout, as_of=AS_OF)) == render_markdown(before)


@pytest.mark.parametrize(
    "security_late,listing_late", [(False, True), (True, False), (False, False)]
)
def test_security_listing_projection_dependencies(
    tmp_path: Path,
    security_late: bool,
    listing_late: bool,
) -> None:
    layout = DataLayout(tmp_path)
    ingest(layout)
    store = bind(layout)
    security = store.load(Security)[0]
    listing = store.load(Listing)[0]
    late = store.load(Provenance)[0].model_copy(
        update={
            "provenance_id": UUID(int=999),
            "derived_at": AS_OF + timedelta(days=1),
        }
    )
    store.persist(Provenance, (late,))
    if security_late:
        store.path_for(Security).unlink()
        store.persist(
            Security, (security.model_copy(update={"provenance_id": late.provenance_id}),)
        )
    if listing_late:
        store.path_for(Listing).unlink()
        store.persist(Listing, (listing.model_copy(update={"provenance_id": late.provenance_id}),))
    canonical_before = store.load(Event)
    report = build_report(layout, as_of=AS_OF)
    for candidate in report.candidates:
        assert candidate.security_id == (None if security_late else security.security_id)
        assert candidate.listing_id == (
            None if security_late or listing_late else listing.listing_id
        )
        assert candidate.identity_status == (
            "unresolved" if security_late else "resolved_common_stock"
        )
        assert candidate.listing_status == (
            "unresolved" if security_late or listing_late else "resolved"
        )
        assert late.provenance_id not in candidate.provenance_ids
    assert store.load(Event) == canonical_before


@pytest.mark.parametrize("boundary", ["missing", "future", "ended", "coarse"])
def test_invalid_listing_validity_never_resolves_listing(tmp_path: Path, boundary: str) -> None:
    layout = DataLayout(tmp_path)
    ingest(layout)
    store = bind(layout)
    listing = store.load(Listing)[0]
    if boundary == "missing":
        listing = listing.model_copy(update={"effective_from": None})
    elif boundary == "future":
        listing = listing.model_copy(
            update={"effective_from": day_value((AS_OF + timedelta(days=1)).date())}
        )
    elif boundary == "ended":
        listing = listing.model_copy(update={"effective_to": listing.effective_from})
    else:
        listing = listing.model_copy(
            update={
                "effective_from": partial_temporal(
                    "2024-09", TemporalPrecision.MONTH, year=2024, month=9
                )
            }
        )
    store.path_for(Listing).unlink()
    store.persist(Listing, (listing,))
    report = build_report(layout, as_of=AS_OF)
    assert all(
        c.security_id is not None
        and c.listing_id is None
        and c.listing_status == "unresolved"
        and c.unresolved_reasons == ("listing_validity_not_supported_at_actionability",)
        for c in report.candidates
    )


def test_visible_listing_security_contradiction_still_raises(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    ingest(layout)
    store = bind(layout)
    listing = store.load(Listing)[0]
    store.path_for(Listing).unlink()
    store.persist(Listing, (listing.model_copy(update={"security_id": UUID(int=123)}),))
    with pytest.raises(ValueError, match="listing security contradiction"):
        build_report(layout, as_of=AS_OF)


def test_late_issuer_id_behaves_like_absent_issuer(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    store = ingest(layout)
    entities = store.load(Entity)
    events = store.load(Event)
    # A genuinely unbound baseline with the same economic Events and filing evidence.
    store.path_for(Entity).unlink()
    store.path_for(Event).unlink()
    store.persist(Event, tuple(e.model_copy(update={"issuer_entity_id": None}) for e in events))
    before = build_report(layout, as_of=AS_OF)
    late = store.load(Provenance)[0].model_copy(
        update={
            "provenance_id": UUID(int=999),
            "derived_at": AS_OF + timedelta(days=1),
        }
    )
    store.persist(Provenance, (late,))
    store.persist(
        Entity, tuple(e.model_copy(update={"provenance_id": late.provenance_id}) for e in entities)
    )
    store.path_for(Event).unlink()
    store.persist(Event, events)
    after = build_report(layout, as_of=AS_OF)
    assert all(c.issuer_entity_id is None for c in after.candidates)
    assert encoded(after) == encoded(before)
    assert render_markdown(after) == render_markdown(before)


def test_evidence_with_late_observation_cannot_leak_through_early_provenance(
    tmp_path: Path,
) -> None:
    layout = DataLayout(tmp_path)
    store = ingest(layout)
    before = build_report(layout, as_of=AS_OF)
    add_vendor_copy(store, observed=AS_OF + timedelta(seconds=1))
    links = store.load(EventEvidence)
    original_provenance = store.load(Event)[0].provenance_id
    store.path_for(EventEvidence).unlink()
    store.persist(
        EventEvidence,
        tuple(
            e.model_copy(update={"provenance_id": original_provenance})
            if len(e.source_observation_ids) == 1 and e.source_observation_ids[0] == UUID(int=900)
            else e
            for e in links
        ),
    )
    after = build_report(layout, as_of=AS_OF)
    assert encoded(after) == encoded(before)
    assert render_markdown(after) == render_markdown(before)
