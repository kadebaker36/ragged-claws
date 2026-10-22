"""Bounded LittleSis context snapshots; no historical-publication inference."""

import hashlib
import re
from collections.abc import Sequence
from datetime import datetime
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit
from uuid import UUID, uuid5

import httpx

from ragged_claws.ingestion.littlesis_models import (
    LittleSisBundle,
    LittleSisMapping,
    LittleSisSnapshot,
)
from ragged_claws.ingestion.littlesis_parser import (
    LICENSE_URL,
    LittleSisError,
    load_json,
    parse_snapshot,
    source_id,
)
from ragged_claws.ingestion.observations import accept_source_observation
from ragged_claws.models import (
    DerivationKind,
    Entity,
    EntityType,
    ExternalIdentifier,
    ExternalIdentifierType,
    IdentifierSubjectType,
    ObservationRole,
    Provenance,
    Relationship,
    RetentionClass,
    SourceLineage,
    SourceObservation,
    SubjectReference,
    SubjectType,
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

PROVIDER = "littlesis.api"
SOURCE_FAMILY = "littlesis.relationships"
ADAPTER_VERSION = "littlesis/1.0.0"
PARSER_VERSION = "littlesis-json/1.0.0"
TRANSFORM_VERSION = "littlesis-context/1.0.0"
IDENTIFIER_NAMESPACE = "littlesis.entity"
NAMESPACE = UUID("5b5beb54-0d6d-4c10-afb5-a6ceeadc84f1")
CATEGORIES = {
    1: "position",
    2: "education",
    3: "membership",
    4: "family",
    5: "donation",
    6: "transaction",
    7: "lobbying",
    8: "social",
    9: "professional",
    10: "ownership",
    11: "hierarchy",
    12: "generic",
}


def request_identity(url: str) -> str:
    """Only documented, explicit single resources or bounded entity relationship pages."""
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.netloc != "littlesis.org"
        or parts.fragment
        or not re.fullmatch(
            r"/api/(?:relationships/[1-9][0-9]*|entities/[1-9][0-9]*(?:/relationships)?)",
            parts.path,
        )
    ):
        raise LittleSisError("unsupported LittleSis API locator")
    try:
        parameters = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise LittleSisError("malformed request parameters") from exc
    if len(dict(parameters)) != len(parameters):
        raise LittleSisError("duplicate request parameter")
    if parts.path.endswith("/relationships"):
        params = dict(parameters)
        if set(params) - {"category_id", "per_page", "page"} or "per_page" not in params:
            raise LittleSisError("relationship lists require an explicit bounded per_page")
        if not 1 <= source_id(params["per_page"]) <= 20:
            raise LittleSisError("per_page exceeds the narrow collection limit")
        for key in ("category_id", "page"):
            if key in params:
                source_id(params[key])
        if "category_id" in params and int(params["category_id"]) not in CATEGORIES:
            raise LittleSisError("unsupported requested category filter")
    elif parameters:
        raise LittleSisError("single resource query parameters are unsupported")
    return parts.path + ("?" + urlencode(sorted(parameters)) if parameters else "")


def retrieve_snapshot(client: httpx.Client, url: str) -> bytes:
    """One explicit request, no pagination, retries, authentication or challenge handling."""
    request_identity(url)
    response = client.get(
        url,
        follow_redirects=False,
        headers={"User-Agent": "RaggedClaws-LittleSis/0.1", "Accept": "application/json"},
    )
    if (
        response.status_code != 200
        or response.headers.get("content-type", "").split(";")[0] != "application/json"
    ):
        raise LittleSisError("LittleSis access unavailable; no retry or challenge handling")
    if len(response.content) > 5_000_000:
        raise LittleSisError("response exceeds the narrow collection limit")
    load_json(response.content)
    return response.content


def _check[RecordT: CanonicalModel](
    existing: Sequence[RecordT], incoming: Sequence[RecordT], key: str
) -> None:
    indexed = {getattr(record, key): record for record in existing}
    for record in incoming:
        identity = getattr(record, key)
        if identity in indexed and indexed[identity] != record:
            raise CanonicalConflictError(f"{type(record).__name__} has a different payload")
        indexed[identity] = record


class LittleSisAdapter:
    def __init__(self, layout: DataLayout) -> None:
        self.layout = layout
        self.store = CanonicalParquetStore(layout)
        self.mapping_path = layout.staging / "littlesis_snapshot_mapping.parquet"

    def load_mappings(self) -> tuple[LittleSisBundle, ...]:
        return load_envelope_records(
            self.mapping_path,
            model_type=LittleSisBundle,
            id_field="source_version_id",
            dataset_kind="staging",
            model_schema_version="1.0.0",
        )

    def _bindings(self) -> dict[int, Entity]:
        entities = {e.entity_id: e for e in self.store.load(Entity)}
        observations = {o.source_observation_id: o for o in self.store.load(SourceObservation)}
        provenance = {p.provenance_id: p for p in self.store.load(Provenance)}
        bindings: dict[int, Entity] = {}
        claims = (
            *self.store.load(ExternalIdentifier),
            *(claim for e in entities.values() for claim in e.external_identifiers),
        )
        for claim in claims:
            if claim.namespace != IDENTIFIER_NAMESPACE:
                continue
            if (
                claim.identifier_type is not ExternalIdentifierType.OTHER
                or claim.subject_type is not IdentifierSubjectType.ENTITY
            ):
                raise LittleSisError("incompatible LittleSis identifier subject")
            identity = source_id(claim.value)
            entity = entities.get(claim.subject_id)
            obs = observations.get(claim.source_observation_id)
            prov = provenance.get(claim.provenance_id)
            if (
                entity is None
                or obs is None
                or prov is None
                or obs.source_observation_id not in prov.source_observation_ids
            ):
                raise LittleSisError("LittleSis identity binding lacks persisted subject/evidence")
            raw = raw_object_path(self.layout, obs.raw_content_hash.value)
            if (
                not raw.exists()
                or hashlib.sha256(raw.read_bytes()).hexdigest() != obs.raw_content_hash.value
            ):
                raise LittleSisError("LittleSis identity binding lacks verified raw evidence")
            if identity in bindings and bindings[identity].entity_id != entity.entity_id:
                raise LittleSisError("ambiguous LittleSis identity binding")
            bindings[identity] = entity
        return bindings

    def canonicalize(
        self, snapshot: LittleSisSnapshot, observation: SourceObservation
    ) -> LittleSisBundle:
        provenance = Provenance(
            provenance_id=uuid5(
                NAMESPACE, f"provenance:{snapshot.source_version_id}:{TRANSFORM_VERSION}"
            ),
            source_observation_ids=(snapshot.source_version_id,),
            derivation_kind=DerivationKind.ENRICHMENT,
            derived_at=observation.observed_at,
            transform_version=TRANSFORM_VERSION,
        )
        bindings = self._bindings()
        catalog = {entity.entity_id: entity for entity in self.store.load(Entity)}
        entities: dict[UUID, Entity] = {}
        resolved: dict[int, Entity] = {}
        claims: list[ExternalIdentifier] = []
        mappings: list[LittleSisMapping] = []
        for resource in snapshot.resources:
            if resource.source_type != "entities":
                continue
            attributes = load_json(resource.payload_json)["attributes"]
            kind = attributes.get("primary_ext")
            if kind not in ("Person", "Org"):
                mappings.append(
                    LittleSisMapping(
                        source_type="entities",
                        source_id=resource.source_id,
                        canonical_id=None,
                        status="unresolved",
                        reason="unsupported_source_entity_type",
                    )
                )
                continue
            entity = bindings.get(resource.source_id)
            if entity is None:
                identity = uuid5(NAMESPACE, f"entity:{resource.source_id}")
                entity = catalog.get(identity)
                if entity is not None:
                    raise LittleSisError("canonical entity exists without a source-backed binding")
                entity = Entity(
                    entity_id=identity,
                    entity_type=EntityType.PERSON if kind == "Person" else EntityType.ORGANIZATION,
                    display_name=attributes["name"],
                    provenance_id=provenance.provenance_id,
                )
                status: Literal["imported", "reused"] = "imported"
            else:
                compatible = (
                    entity.entity_type is EntityType.PERSON
                    if kind == "Person"
                    else entity.entity_type not in (EntityType.PERSON, EntityType.HOUSEHOLD)
                )
                if not compatible:
                    raise LittleSisError("source entity type contradicts existing identity")
                status = "reused"
            entities[entity.entity_id] = entity
            resolved[resource.source_id] = entity
            mappings.append(
                LittleSisMapping(
                    source_type="entities",
                    source_id=resource.source_id,
                    canonical_id=entity.entity_id,
                    status=status,
                )
            )
            claims.append(
                ExternalIdentifier(
                    external_identifier_id=uuid5(
                        NAMESPACE,
                        f"claim:{resource.source_id}:{entity.entity_id}:{snapshot.source_version_id}",
                    ),
                    subject_type=IdentifierSubjectType.ENTITY,
                    subject_id=entity.entity_id,
                    identifier_type=ExternalIdentifierType.OTHER,
                    namespace=IDENTIFIER_NAMESPACE,
                    value=str(resource.source_id),
                    source_observation_id=snapshot.source_version_id,
                    provenance_id=provenance.provenance_id,
                    observed_at=observation.observed_at,
                )
            )
        previous: dict[int, tuple[str, Relationship]] = {}
        for bundle in self.load_mappings():
            relations = {r.relationship_id: r for r in bundle.relationships}
            resources = {
                r.source_id: r
                for r in bundle.snapshot.resources
                if r.source_type == "relationships"
            }
            for mapping in bundle.mappings:
                if mapping.source_type == "relationships" and mapping.canonical_id is not None:
                    candidate = (
                        resources[mapping.source_id].semantic_hash,
                        relations[mapping.canonical_id],
                    )
                    if mapping.source_id in previous and previous[mapping.source_id] != candidate:
                        raise CanonicalConflictError(
                            "inconsistent accepted LittleSis source history"
                        )
                    previous[mapping.source_id] = candidate
        relationships: list[Relationship] = []
        for resource in snapshot.resources:
            if resource.source_type != "relationships":
                continue
            attributes = load_json(resource.payload_json)["attributes"]
            prior = previous.get(resource.source_id)
            if prior is not None:
                if prior[0] != resource.semantic_hash:
                    raise CanonicalConflictError(
                        "changed LittleSis relationship requires reconciliation; raw retained"
                    )
                relation = prior[1]
                status = "reused"
            else:
                category = CATEGORIES.get(attributes["category_id"])
                if category is None:
                    mappings.append(
                        LittleSisMapping(
                            source_type="relationships",
                            source_id=resource.source_id,
                            canonical_id=None,
                            status="excluded",
                            reason="unsupported_relationship_category",
                        )
                    )
                    continue
                endpoints = [
                    resolved.get(source_id(attributes[key]))
                    or bindings.get(source_id(attributes[key]))
                    for key in ("entity1_id", "entity2_id")
                ]
                if any(endpoint is None for endpoint in endpoints):
                    mappings.append(
                        LittleSisMapping(
                            source_type="relationships",
                            source_id=resource.source_id,
                            canonical_id=None,
                            status="unresolved",
                            reason="unresolved_endpoint",
                        )
                    )
                    continue
                source, target = endpoints
                assert source is not None and target is not None
                entities.update({source.entity_id: source, target.entity_id: target})
                relation = Relationship(
                    relationship_id=uuid5(NAMESPACE, f"relationship:{resource.source_id}"),
                    relationship_type=category,
                    source=SubjectReference(
                        subject_type=SubjectType.ENTITY, subject_id=source.entity_id
                    ),
                    target=SubjectReference(
                        subject_type=SubjectType.ENTITY, subject_id=target.entity_id
                    ),
                    valid_from=resource.valid_from,
                    valid_to=resource.valid_to,
                    observed_at=observation.observed_at,
                    source_observation_ids=(snapshot.source_version_id,),
                    provenance_id=provenance.provenance_id,
                )
                status = "imported"
            relationships.append(relation)
            mappings.append(
                LittleSisMapping(
                    source_type="relationships",
                    source_id=resource.source_id,
                    canonical_id=relation.relationship_id,
                    status=status,
                )
            )
        return LittleSisBundle(
            snapshot=snapshot,
            observation=observation,
            provenance=provenance,
            entities=tuple(sorted(entities.values(), key=lambda e: str(e.entity_id))),
            identifier_claims=tuple(claims),
            relationships=tuple(relationships),
            mappings=tuple(mappings),
            attribution=(
                f"LittleSis / Public Accountability Initiative; {snapshot.copyright}; "
                f"{snapshot.license_url}"
            ),
            change_notice=(
                "Normalized resource IDs, dates and categories; raw source bytes retained. "
                "No primary-document verification."
            ),
            transform_version=TRANSFORM_VERSION,
        )

    def persist(self, bundle: LittleSisBundle) -> None:
        _check(self.load_mappings(), (bundle,), "source_version_id")
        # Preflight every dataset before the first analytical write. Single-writer only;
        # individual files are atomic, publication across files is recoverable, not atomic.
        _check(self.store.load(SourceObservation), (bundle.observation,), "source_observation_id")
        _check(self.store.load(Provenance), (bundle.provenance,), "provenance_id")
        _check(self.store.load(Entity), bundle.entities, "entity_id")
        _check(
            self.store.load(ExternalIdentifier), bundle.identifier_claims, "external_identifier_id"
        )
        _check(self.store.load(Relationship), bundle.relationships, "relationship_id")
        persist_envelope_records(
            self.mapping_path,
            model_type=LittleSisBundle,
            id_field="source_version_id",
            records=(bundle,),
            dataset_kind="staging",
            model_schema_version="1.0.0",
        )
        self.store.persist(SourceObservation, (bundle.observation,))
        self.store.persist(Provenance, (bundle.provenance,))
        self.store.persist(Entity, bundle.entities)
        self.store.persist(ExternalIdentifier, bundle.identifier_claims)
        self.store.persist(Relationship, bundle.relationships)

    def ingest(
        self, content: bytes, *, source_locator: str, retrieved_at: datetime
    ) -> LittleSisBundle:
        native = request_identity(source_locator)
        # Invalid/unlicensed input is still retained, without falsely declaring it public/CC.
        licensed = False
        try:
            metadata = load_json(content).get("meta", {})
            licensed = isinstance(metadata, dict) and metadata.get("license") == LICENSE_URL
        except (LittleSisError, AttributeError):
            pass
        manifest = capture_raw_bytes(
            self.layout,
            content,
            provider_namespace=PROVIDER,
            source_family=SOURCE_FAMILY,
            source_native_id=native,
            source_locator=source_locator,
            retrieved_at=retrieved_at,
            observed_at=retrieved_at,
            adapter_version=ADAPTER_VERSION,
            parser_version=PARSER_VERSION,
            retention_class=RetentionClass.PUBLIC if licensed else RetentionClass.UNKNOWN,
            license_name="CC-BY-SA-4.0" if licensed else None,
        )
        identity = deterministic_source_observation_id(
            PROVIDER, native, manifest.content_hash.value
        )
        snapshot = parse_snapshot(content, observation_id=identity)
        payload = load_json(content)
        if not native.split("?")[0].endswith("/relationships"):
            data = payload["data"]
            kind, requested_id = native.split("/")[-2:]
            if (
                not isinstance(data, dict)
                or data.get("type") != kind
                or source_id(data.get("id")) != int(requested_id)
            ):
                raise LittleSisError("response resource contradicts requested locator")
        else:
            data = payload["data"]
            parameters = dict(parse_qsl(urlsplit(source_locator).query))
            requested_entity = int(urlsplit(source_locator).path.split("/")[-2])
            if not isinstance(data, list) or len(data) > int(parameters["per_page"]):
                raise LittleSisError("response exceeds requested page scope")
            page_meta = payload["meta"]
            current, count = page_meta.get("currentPage"), page_meta.get("pageCount")
            if (
                type(current) is not int
                or current != int(parameters.get("page", "1"))
                or type(count) is not int
                or count < 0
                or (data and current > count)
            ):
                raise LittleSisError("response pagination contradicts requested page")
            for item in data:
                attrs = item["attributes"]
                if (
                    item["type"] != "relationships"
                    or requested_entity
                    not in (source_id(attrs["entity1_id"]), source_id(attrs["entity2_id"]))
                    or (
                        "category_id" in parameters
                        and attrs["category_id"] != int(parameters["category_id"])
                    )
                ):
                    raise LittleSisError("response relationship contradicts requested page scope")
        candidate = SourceObservation(
            source_observation_id=identity,
            provider_namespace=PROVIDER,
            source_native_id=native,
            lineage=SourceLineage(
                source_family=SOURCE_FAMILY, observation_role=ObservationRole.ENRICHMENT
            ),
            retrieved_at=manifest.retrieved_at,
            observed_at=manifest.retrieved_at,
            raw_content_hash=manifest.content_hash,
            adapter_version=ADAPTER_VERSION,
            parser_version=PARSER_VERSION,
            source_locator=source_locator,
            retention_class=RetentionClass.PUBLIC,
            license_name="CC-BY-SA-4.0",
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
                prior.snapshot != snapshot
                or prior.observation != observation
                or prior.transform_version != TRANSFORM_VERSION
            ):
                raise CanonicalConflictError(
                    "LittleSis source version has different mapping semantics"
                )
            self.persist(prior)
            return prior
        bundle = self.canonicalize(snapshot, observation)
        self.persist(bundle)
        return bundle
