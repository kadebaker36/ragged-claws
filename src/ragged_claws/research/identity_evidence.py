"""Fixed recorded SEC identity evidence; retrospective candidates, no guessed event bindings."""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid5

from pydantic import JsonValue

from ragged_claws.models import (
    DerivationKind,
    Entity,
    ExternalIdentifier,
    ExternalIdentifierType,
    IdentifierSubjectType,
    ObservationRole,
    Provenance,
    RetentionClass,
    Security,
    SecurityType,
    SourceLineage,
    SourceObservation,
)
from ragged_claws.research.examples import prepare_sec
from ragged_claws.research.snapshot import (
    ResearchError,
    digest,
    encoded,
    inventory_for,
    read_inputs,
)
from ragged_claws.resolution import (
    IdentifierResolutionRequest,
    IdentityCatalog,
    ResolutionStatus,
    day_value,
    deterministic_entity_id_from_cik,
    deterministic_external_identifier_id,
    deterministic_security_id,
)
from ragged_claws.storage import CanonicalParquetStore, DataLayout, capture_raw_bytes

VERSION = "recorded-sec-identity/1.0.0"
PARSER = "reviewed-byte-spans/1.0.0"
NAMESPACE = UUID("6995b62d-9d63-4e70-806e-2f037f5cdca0")
HASHES = {
    "0001104659-24-020016.txt": "252953852009256b2506304a8c213db7791243b5f6b524b4d271dda4897d6f71",
    "0000070858-24-000122-index.htm": (
        "b60ee0e1f1c2d8a5946f4e93466b8a8022af0650e60de56ac9fff6a865a84e14"
    ),
    "10k-common-cover-row.html": "e678e8624730ecfa12611b8a03fedd58027f45c79e0df7cecdfe75688fcbac1b",
}
REVIEWED_AT = datetime(2026, 10, 23, 13, 43, 14, tzinfo=UTC)


def import_identity_evidence(root: Path, fixtures: Path) -> Security:
    """Append exact recorded observations and one security candidate, never a Listing.

    Known-from is conservative public-day knowledge of the identifier assertion,
    not proof of uninterrupted validity or eligibility of a September event binding.
    Raw captures retain full/excerpt metadata and original retrieval time.
    """
    metadata = (fixtures / "evidence.json").read_bytes()
    if digest(metadata.replace(b"\r\n", b"\n")) != (
        "2f2db6e4f94d37164370aabf7948ed2bb7c9e5feee88c49a4e9b4f4590845f40"
    ):
        raise ResearchError("historical evidence metadata differs from reviewed declaration")
    meta = json.loads(metadata)
    if meta["adapter_version"] != VERSION or meta["parser_version"] != PARSER:
        raise ResearchError("unreviewed historical identity evidence version")
    resources = {item["fixture_file"]: item for item in meta["resources"]}
    if set(resources) != set(HASHES) or len(meta["resources"]) != 3:
        raise ResearchError("historical evidence must contain exactly the reviewed resources")
    layout = DataLayout(root / "data")
    store = CanonicalParquetStore(layout)
    issuer_id = deterministic_entity_id_from_cik("0000070858")
    catalog = IdentityCatalog(
        entities=store.load(Entity), external_identifiers=store.load(ExternalIdentifier)
    )
    resolved = catalog.resolve_identifier(
        IdentifierResolutionRequest(
            subject_type=IdentifierSubjectType.ENTITY,
            identifier_type=ExternalIdentifierType.SEC_CIK,
            value="70858",
        )
    )
    if resolved.status != ResolutionStatus.RESOLVED or resolved.subject_id != issuer_id:
        raise ResearchError("recorded evidence requires the existing exact SEC issuer entity")
    observations = []
    provenances = []
    for filename, expected in HASHES.items():
        content = (fixtures / filename).read_bytes()
        if digest(content) != expected:
            raise ResearchError("historical identity fixture differs from reviewed bytes")
        item = resources[filename]
        excerpt = filename == "10k-common-cover-row.html"
        if excerpt:
            if (
                item["excerpt_sha256"] != expected
                or item["parent_offset_end_exclusive"] - item["parent_offset_start"] != len(content)
                or item["sha256"]
                != "ae256da438e3a3311c38f5a80641e59e43f21cfe58b46d3f54a1a5794eeaa8da"
            ):
                raise ResearchError("invalid cover excerpt/parent declaration")
        elif item["sha256"] != expected or item["size_bytes"] != len(content):
            raise ResearchError("invalid full-response evidence declaration")
        if item["status"] != 200:
            raise ResearchError("unavailable evidence cannot support canonical claims")
        retrieved = datetime.fromisoformat(item["retrieved_at"])
        public = day_value(
            date(2024, 2, 13) if filename.endswith("020016.txt") else date(2024, 2, 20)
        )
        native = (
            "0001104659-24-020016"
            if filename.endswith("020016.txt")
            else (
                "0000070858-24-000122#common-cover-byte-excerpt"
                if excerpt
                else "0000070858-24-000122#index"
            )
        )
        parameters: dict[str, JsonValue] = {
            "representation": item["representation"],
            "requested_url": item["requested_url"],
            "canonical_url": item["canonical_url"],
            "http_status": 200,
            "parent_sha256": item["sha256"],
            "parent_size_bytes": item["size_bytes"],
            "parent_offset_start": item.get("parent_offset_start"),
            "parent_offset_end_exclusive": item.get("parent_offset_end_exclusive"),
            "reviewed_claim_spans": item.get("reviewed_claim_spans", []),
        }
        capture = capture_raw_bytes(
            layout,
            content,
            provider_namespace="sec.edgar",
            source_family="sec.identity",
            retrieved_at=retrieved,
            observed_at=retrieved,
            source_native_id=native,
            source_locator=item["canonical_url"],
            request_parameters=parameters,
            adapter_version=VERSION,
            parser_version=PARSER,
            retention_class=RetentionClass.PUBLIC,
            license_name="SEC public filing reuse",
        )
        observation_id = uuid5(NAMESPACE, f"observation:{native}:{expected}")
        observations.append(
            SourceObservation(
                source_observation_id=observation_id,
                provider_namespace="sec.edgar",
                source_native_id=native,
                lineage=SourceLineage(
                    source_family="sec.identity", observation_role=ObservationRole.PRIMARY_SOURCE
                ),
                retrieved_at=retrieved,
                observed_at=retrieved,
                public_time=public,
                raw_content_hash=capture.content_hash,
                adapter_version=VERSION,
                parser_version=PARSER,
                source_locator=item["canonical_url"],
                retention_class=RetentionClass.PUBLIC,
                license_name="SEC public filing reuse",
            )
        )
        provenances.append(
            Provenance(
                provenance_id=uuid5(NAMESPACE, f"review:{observation_id}"),
                source_observation_ids=(observation_id,),
                derivation_kind=DerivationKind.ENRICHMENT,
                derived_at=REVIEWED_AT,
                transform_version=VERSION,
            )
        )
    security_id = deterministic_security_id(ExternalIdentifierType.CUSIP, "060505104")
    observation = observations[0]
    provenance = provenances[0]
    claims = tuple(
        ExternalIdentifier(
            external_identifier_id=deterministic_external_identifier_id(
                subject_type=kind,
                subject_id=identity,
                identifier_type=identifier_type,
                value=value,
                source_observation_id=observation.source_observation_id,
            ),
            subject_type=kind,
            subject_id=identity,
            identifier_type=identifier_type,
            value=value,
            source_observation_id=observation.source_observation_id,
            provenance_id=provenance.provenance_id,
            known_from=observation.public_time,
            observed_at=observation.observed_at,
            # No inferred effective interval, especially not an open interval from 2023.
        )
        for kind, identity, identifier_type, value in (
            (IdentifierSubjectType.ENTITY, issuer_id, ExternalIdentifierType.SEC_CIK, "0000070858"),
            (
                IdentifierSubjectType.SECURITY,
                security_id,
                ExternalIdentifierType.CUSIP,
                "060505104",
            ),
        )
    )
    security = Security(
        security_id=security_id,
        issuer_entity_id=issuer_id,
        security_type=SecurityType.COMMON_STOCK,
        share_class="Common Stock",
        display_name="Bank of America common stock (recorded 13G/A CUSIP candidate)",
        provenance_id=provenance.provenance_id,
    )
    # All source records and claims are separate from the original Form4 Event payloads.
    store.persist(SourceObservation, observations)
    store.persist(Provenance, provenances)
    store.persist(Security, (security,))
    store.persist(ExternalIdentifier, claims)
    return security


def prepare_identity_diagnostic(
    root: Path, fixtures: Path, sec_fixtures: Path, protocol: Path
) -> None:
    """Offline diagnostic with original three events and unbound historical candidate."""
    prepare_sec(
        root,
        sec_fixtures / "0000950170-24-105263.txt",
        sec_fixtures / "provenance.json",
        protocol,
        as_of=REVIEWED_AT,
    )
    import_identity_evidence(root, fixtures)
    # Prepared metadata is a derivative. Frozen snapshots/raw captures are never rewritten.
    (root / "origins.json").write_bytes(
        encoded(
            inventory_for(
                read_inputs(root),
                "recorded_public",
                "Recorded SEC Form4 plus explicitly reviewed historical identity candidates; "
                "cover excerpt is labeled with full parent hash/byte offsets; "
                "no event/listing binding.",
            )
        )
    )
