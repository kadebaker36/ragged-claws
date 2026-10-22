"""Fixture-first Quiver observations; identity reconciliation is explicit and auditable."""

import hashlib
from collections.abc import Sequence
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid5

from ragged_claws.ingestion.observations import accept_source_observation
from ragged_claws.ingestion.quiver_access import (
    QuiverAccessReview,
    request_identity,
    require_restricted_storage,
)
from ragged_claws.ingestion.quiver_models import (
    Endpoint,
    QuiverBundle,
    QuiverMapping,
    QuiverRow,
    ReviewedRowLink,
)
from ragged_claws.ingestion.quiver_parser import (
    FAMILIES,
    PARSER_VERSION,
    SCHEMA_SHA256,
    QuiverError,
    load_json,
    parse_rows,
)
from ragged_claws.models import (
    DerivationKind,
    DisclosedRange,
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
    TemporalPrecision,
    TemporalValue,
)
from ragged_claws.models.base import CanonicalModel
from ragged_claws.storage import (
    CanonicalConflictError,
    CanonicalParquetStore,
    DataLayout,
    capture_raw_bytes,
    deterministic_source_observation_id,
    load_envelope_records,
    persist_envelope_records,
)
from ragged_claws.storage.raw import raw_object_path

ADAPTER_VERSION = "quiver/1.0.0"
TRANSFORM_VERSION = "quiver-context/1.0.0"
NAMESPACE = UUID("de013275-8f13-4aec-80b7-c1df56bfb1cc")
BIOGUIDE = "us.congress.bioguide"


def _check[T: CanonicalModel](existing: Sequence[T], incoming: Sequence[T], key: str) -> None:
    indexed = {getattr(item, key): item for item in existing}
    for item in incoming:
        identity = getattr(item, key)
        if identity in indexed and indexed[identity] != item:
            raise CanonicalConflictError("canonical record has a different payload")
        indexed[identity] = item


def _credential_fields(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).casefold().replace("_", "").replace("-", "")
            if normalized in {
                "authorization",
                "apikey",
                "accesstoken",
                "token",
                "password",
                "secret",
            }:
                return True
            if _credential_fields(item):
                return True
    elif isinstance(value, list):
        return any(_credential_fields(item) for item in value)
    return False


def _same_occurrence(left: TemporalValue, right: TemporalValue) -> bool:
    """Compare supported components; keep independent raw source representations."""
    if left.precision is not right.precision or left.precision is TemporalPrecision.UNKNOWN:
        return False
    if left.timestamp is not None and right.timestamp is not None:
        return left.timestamp == right.timestamp
    a, b = left.partial_date, right.partial_date
    if a is None or b is None:
        return False
    return (a.year, a.month, a.day) == (b.year, b.month, b.day)


def _same_range(left: DisclosedRange, right: DisclosedRange) -> bool:
    # Unknown bounds cannot be inferred from another source to manufacture a match.
    return (left.lower_bound is not None or left.upper_bound is not None) and (
        left.name,
        left.lower_bound,
        left.upper_bound,
        left.currency,
        left.unit,
    ) == (right.name, right.lower_bound, right.upper_bound, right.currency, right.unit)


class QuiverAdapter:
    def __init__(self, layout: DataLayout) -> None:
        self.layout = layout
        self.store = CanonicalParquetStore(layout)
        self.mapping_path = layout.staging / "quiver_snapshot_mapping.parquet"

    def load_mappings(self) -> tuple[QuiverBundle, ...]:
        return load_envelope_records(
            self.mapping_path,
            model_type=QuiverBundle,
            id_field="source_version_id",
            dataset_kind="staging",
            model_schema_version="1.0.0",
        )

    def _verified_observation(self, identity: UUID) -> SourceObservation:
        obs = next(
            (o for o in self.store.load(SourceObservation) if o.source_observation_id == identity),
            None,
        )
        if obs is None:
            raise QuiverError("required source observation missing")
        raw = raw_object_path(self.layout, obs.raw_content_hash.value)
        if (
            not raw.exists()
            or hashlib.sha256(raw.read_bytes()).hexdigest() != obs.raw_content_hash.value
        ):
            raise QuiverError("required immutable evidence missing or corrupt")
        return obs

    def _people(self) -> dict[str, Entity]:
        entities = {e.entity_id: e for e in self.store.load(Entity)}
        provenances = {p.provenance_id: p for p in self.store.load(Provenance)}
        result: dict[str, Entity] = {}
        claims = (
            *self.store.load(ExternalIdentifier),
            *(c for e in entities.values() for c in e.external_identifiers),
        )
        for claim in claims:
            if claim.namespace != BIOGUIDE:
                continue
            if (
                claim.identifier_type is not ExternalIdentifierType.OTHER
                or claim.subject_type is not IdentifierSubjectType.ENTITY
            ):
                raise QuiverError("incompatible identity binding")
            entity = entities.get(claim.subject_id)
            prov = provenances.get(claim.provenance_id)
            obs = self._verified_observation(claim.source_observation_id)
            if (
                entity is None
                or entity.entity_type is not EntityType.PERSON
                or prov is None
                or obs.source_observation_id not in prov.source_observation_ids
            ):
                raise QuiverError("identity binding lacks compatible subject/provenance")
            if claim.value in result and result[claim.value].entity_id != entity.entity_id:
                raise QuiverError("ambiguous identity binding")
            result[claim.value] = entity
        return result

    def _linked_event(
        self,
        link: ReviewedRowLink,
        row: QuiverRow,
        observation: SourceObservation,
        endpoint: Endpoint,
        synthetic: bool,
    ) -> Event:
        if link.raw_sha256 != observation.raw_content_hash.value:
            raise QuiverError("reviewed link has incompatible capture or review time")
        primary = self._verified_observation(link.primary_observation_id)
        if (
            primary.lineage.observation_role is not ObservationRole.PRIMARY_SOURCE
            or primary.lineage.source_family != FAMILIES[endpoint]
            or (not synthetic and primary.retention_class is RetentionClass.INTERNAL)
        ):
            raise QuiverError("reviewed link lacks matching primary source family")
        event = next((e for e in self.store.load(Event) if e.event_id == link.event_id), None)
        if event is None or not any(
            e.event_id == link.event_id
            and primary.source_observation_id in e.source_observation_ids
            for e in self.store.load(EventEvidence)
        ):
            raise QuiverError("reviewed link lacks existing primary event evidence")
        prov = next(
            (p for p in self.store.load(Provenance) if event.provenance_id == p.provenance_id), None
        )
        if prov is None or primary.source_observation_id not in prov.source_observation_ids:
            raise QuiverError("primary event provenance does not support reviewed link")
        if row.event_type != event.event_type:
            raise QuiverError("reviewed event type contradicts vendor facts")
        if row.occurrence_time is not None and not _same_occurrence(
            event.occurrence_time, row.occurrence_time
        ):
            raise QuiverError("reviewed event occurrence contradicts vendor facts")
        if any(value not in event.financial_values for value in row.financial_values) or any(
            not any(_same_range(value, primary_range) for primary_range in event.disclosed_ranges)
            for value in row.disclosed_ranges
        ):
            raise QuiverError("reviewed event financial facts contradict vendor facts")
        # This is an explicit reviewed match, not proof that dates/amounts uniquely identify rows.
        return event

    def canonicalize(
        self,
        rows: tuple[QuiverRow, ...],
        observation: SourceObservation,
        *,
        endpoint: Endpoint,
        links: tuple[ReviewedRowLink, ...],
        synthetic: bool,
        review: QuiverAccessReview | None,
    ) -> QuiverBundle:
        if len({link.row_index for link in links}) != len(links) or len(
            {link.event_id for link in links}
        ) != len(links):
            raise QuiverError("ambiguous repeated-row reconciliation")
        if any(link.row_index >= len(rows) for link in links):
            raise QuiverError("reviewed link outside captured response")
        provenance = Provenance(
            provenance_id=uuid5(NAMESPACE, f"provenance:{observation.source_observation_id}"),
            source_observation_ids=(observation.source_observation_id,),
            derivation_kind=DerivationKind.NORMALIZATION,
            derived_at=observation.observed_at,
            transform_version=TRANSFORM_VERSION,
        )
        people = self._people()
        names: dict[str, str] = {}
        for row in rows:
            if row.person_identifier is not None and row.person_name is not None:
                if (
                    row.person_identifier in names
                    and names[row.person_identifier] != row.person_name
                ):
                    raise QuiverError("conflicting names for one source identity in a response")
                names[row.person_identifier] = row.person_name
        catalog = {e.entity_id: e for e in self.store.load(Entity)}
        entities: dict[UUID, Entity] = {}
        claims: dict[UUID, ExternalIdentifier] = {}
        events: list[Event] = []
        evidence: list[EventEvidence] = []
        mappings: list[QuiverMapping] = []
        by_index = {link.row_index: link for link in links}
        for row in rows:
            person = None
            if row.person_identifier is not None and row.person_name is not None:
                identity = uuid5(NAMESPACE, f"bioguide:{row.person_identifier}")
                person = people.get(row.person_identifier)
                if person is None:
                    if identity in catalog:
                        raise QuiverError("entity exists without source-backed identity claim")
                    person = Entity(
                        entity_id=identity,
                        entity_type=EntityType.PERSON,
                        display_name=row.person_name,
                        provenance_id=provenance.provenance_id,
                    )
                    people[row.person_identifier] = person
                entities[person.entity_id] = person
                claim_id = uuid5(
                    NAMESPACE,
                    f"claim:{person.entity_id}:{row.person_identifier}:{observation.source_observation_id}",
                )
                claims[claim_id] = ExternalIdentifier(
                    external_identifier_id=claim_id,
                    subject_type=IdentifierSubjectType.ENTITY,
                    subject_id=person.entity_id,
                    identifier_type=ExternalIdentifierType.OTHER,
                    namespace=BIOGUIDE,
                    value=row.person_identifier,
                    source_observation_id=observation.source_observation_id,
                    provenance_id=provenance.provenance_id,
                    observed_at=observation.observed_at,
                    known_from=None,
                )
            event = None
            reason: str | None = row.reason or "underlying_event_identity_unresolved"
            status: Literal["linked", "excluded", "unresolved"] = (
                "excluded" if row.reason else "unresolved"
            )
            if row.row_index in by_index:
                if row.reason:
                    raise QuiverError("excluded row cannot be linked")
                event = self._linked_event(
                    by_index[row.row_index], row, observation, endpoint, synthetic
                )
                reporters = {
                    actor.entity_id for actor in event.actors if actor.role == "reporting_lawmaker"
                }
                if person is not None and reporters and person.entity_id not in reporters:
                    raise QuiverError(
                        "reviewed reporting lawmaker contradicts source-backed person binding"
                    )
                for previous in self.load_mappings():
                    for mapping in previous.mappings:
                        if (
                            previous.endpoint == endpoint
                            and mapping.event_id == event.event_id
                            and previous.rows[mapping.row_index].fact_hash != row.fact_hash
                        ):
                            raise CanonicalConflictError(
                                "changed linked vendor facts require reconciliation; raw retained"
                            )
                events.append(event)
                evidence.append(
                    EventEvidence(
                        event_evidence_id=uuid5(
                            NAMESPACE,
                            f"evidence:{event.event_id}:{observation.source_observation_id}",
                        ),
                        event_id=event.event_id,
                        source_observation_ids=(observation.source_observation_id,),
                        provenance_id=provenance.provenance_id,
                    )
                )
                status, reason = "linked", None
            mappings.append(
                QuiverMapping(
                    row_index=row.row_index,
                    event_id=event.event_id if event else None,
                    person_id=person.entity_id if person else None,
                    status=status,
                    reason=reason,
                )
            )
        provenance = provenance.model_copy(
            update={
                "source_observation_ids": (
                    observation.source_observation_id,
                    *sorted({link.primary_observation_id for link in links}, key=str),
                ),
                "parent_provenance_ids": tuple(sorted({e.provenance_id for e in events}, key=str)),
                "derived_at": max((observation.observed_at, *(link.reviewed_at for link in links))),
            }
        )
        return QuiverBundle(
            source_version_id=observation.source_observation_id,
            endpoint=endpoint,
            rows=rows,
            observation=observation,
            provenance=provenance,
            entities=tuple(sorted(entities.values(), key=lambda e: str(e.entity_id))),
            identifier_claims=tuple(
                sorted(claims.values(), key=lambda c: str(c.external_identifier_id))
            ),
            events=tuple(events),
            evidence=tuple(evidence),
            mappings=tuple(mappings),
            reviewed_links=links,
            synthetic=synthetic,
            license_review_sha256=review.agreement_sha256 if review else None,
            transform_version=TRANSFORM_VERSION,
            source_schema_sha256=SCHEMA_SHA256,
        )

    def persist(self, bundle: QuiverBundle, *, review: QuiverAccessReview | None = None) -> None:
        if not bundle.synthetic:
            verified_review = require_restricted_storage(
                self.layout.root, review, bundle.endpoint, bundle.observation.retrieved_at
            )
            if bundle.license_review_sha256 != verified_review.agreement_sha256:
                raise QuiverError("publication license review differs from captured mapping")
        raw = raw_object_path(self.layout, bundle.observation.raw_content_hash.value)
        if (
            not raw.exists()
            or hashlib.sha256(raw.read_bytes()).hexdigest()
            != bundle.observation.raw_content_hash.value
        ):
            raise QuiverError("publication requires verified immutable raw evidence")
        _check(self.load_mappings(), (bundle,), "source_version_id")
        _check(self.store.load(SourceObservation), (bundle.observation,), "source_observation_id")
        _check(self.store.load(Provenance), (bundle.provenance,), "provenance_id")
        _check(self.store.load(Entity), bundle.entities, "entity_id")
        _check(
            self.store.load(ExternalIdentifier), bundle.identifier_claims, "external_identifier_id"
        )
        _check(self.store.load(Event), bundle.events, "event_id")
        _check(self.store.load(EventEvidence), bundle.evidence, "event_evidence_id")
        persist_envelope_records(
            self.mapping_path,
            model_type=QuiverBundle,
            id_field="source_version_id",
            records=(bundle,),
            dataset_kind="staging",
            model_schema_version="1.0.0",
        )
        self.store.persist(SourceObservation, (bundle.observation,))
        self.store.persist(Provenance, (bundle.provenance,))
        self.store.persist(Entity, bundle.entities)
        self.store.persist(ExternalIdentifier, bundle.identifier_claims)
        self.store.persist(Event, bundle.events)
        self.store.persist(EventEvidence, bundle.evidence)

    def ingest(
        self,
        content: bytes,
        *,
        endpoint: Endpoint,
        source_locator: str,
        retrieved_at: datetime,
        synthetic: bool = False,
        review: QuiverAccessReview | None = None,
        links: tuple[ReviewedRowLink, ...] = (),
    ) -> QuiverBundle:
        native, limit = request_identity(source_locator, endpoint)
        links = tuple(sorted(links, key=lambda item: item.row_index))
        if not synthetic:
            review = require_restricted_storage(self.layout.root, review, endpoint, retrieved_at)
        try:
            parsed = load_json(content)
        except QuiverError:
            parsed = (
                None  # malformed source bytes remain capturable, without logging their contents
            )
        if _credential_fields(parsed):
            raise QuiverError("credential-bearing input rejected before capture")
        provider = "quiver.synthetic" if synthetic else "quiver.api"
        manifest = capture_raw_bytes(
            self.layout,
            content,
            provider_namespace=provider,
            source_family="quiver." + endpoint,
            retrieved_at=retrieved_at,
            observed_at=retrieved_at,
            source_native_id=native,
            source_locator=source_locator,
            adapter_version=ADAPTER_VERSION,
            parser_version=PARSER_VERSION,
            retention_class=RetentionClass.INTERNAL if synthetic else RetentionClass.RESTRICTED,
            license_name="invented-test-data"
            if synthetic
            else "quiver-reviewed-private-api-agreement",
        )
        rows = parse_rows(content, endpoint, limit=limit)
        identity = deterministic_source_observation_id(
            provider, native, manifest.content_hash.value
        )
        candidate = SourceObservation(
            source_observation_id=identity,
            provider_namespace=provider,
            source_native_id=native,
            lineage=SourceLineage(
                source_family="quiver." + endpoint,
                underlying_source_family=FAMILIES[endpoint],
                observation_role=ObservationRole.VENDOR_NORMALIZED,
            ),
            retrieved_at=manifest.retrieved_at,
            observed_at=manifest.retrieved_at,
            raw_content_hash=manifest.content_hash,
            adapter_version=ADAPTER_VERSION,
            parser_version=PARSER_VERSION,
            source_locator=source_locator,
            retention_class=manifest.retention_class,
            license_name=manifest.license_name,
        )
        prior = next((b for b in self.load_mappings() if b.source_version_id == identity), None)
        existing = next(
            (o for o in self.store.load(SourceObservation) if o.source_observation_id == identity),
            None,
        )
        observation = accept_source_observation(
            existing or (prior.observation if prior else None), candidate
        )
        if prior is not None:
            if (
                prior.rows != rows
                or prior.reviewed_links != links
                or prior.transform_version != TRANSFORM_VERSION
                or prior.source_schema_sha256 != SCHEMA_SHA256
                or prior.license_review_sha256 != (review.agreement_sha256 if review else None)
            ):
                raise CanonicalConflictError(
                    "accepted source version has different reconciliation semantics"
                )
            self.persist(prior, review=review)
            return prior
        bundle = self.canonicalize(
            rows, observation, endpoint=endpoint, links=links, synthetic=synthetic, review=review
        )
        self.persist(bundle, review=review)
        return bundle
