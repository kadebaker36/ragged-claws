"""Portable, hash-checked local inputs. DuckDB and global Outcomes are never inputs."""

import hashlib
import json
import os
import platform
import shutil
import tempfile
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID, uuid5

from ragged_claws.ingestion.littlesis_models import LittleSisBundle
from ragged_claws.ingestion.quiver_models import QuiverBundle
from ragged_claws.ingestion.sec_models import SecBundle, SecFiling
from ragged_claws.models import (
    Entity,
    Event,
    EventEvidence,
    ExternalIdentifier,
    Listing,
    ObservationRole,
    Provenance,
    Relationship,
    RetentionClass,
    Security,
    SourceObservation,
)
from ragged_claws.models.base import MODEL_SCHEMA_VERSION, CanonicalModel
from ragged_claws.research.models import (
    BuildConfig,
    Controls,
    InputFile,
    OriginInventory,
    PriceInputs,
    Protocol,
    Snapshot,
)
from ragged_claws.storage import (
    CanonicalConflictError,
    CanonicalParquetStore,
    DataLayout,
    load_envelope_records,
)
from ragged_claws.storage.raw import RawCaptureManifest, raw_object_path

VERSION = "research-build/1.0.0"
NAMESPACE = UUID("ee439b54-3da4-4427-8da2-d0b3ff49e7e7")
CORE = (
    (Entity, "entity_id"),
    (ExternalIdentifier, "external_identifier_id"),
    (Security, "security_id"),
    (Listing, "listing_id"),
    (Relationship, "relationship_id"),
    (Event, "event_id"),
    (EventEvidence, "event_evidence_id"),
    (Provenance, "provenance_id"),
    (SourceObservation, "source_observation_id"),
)
STAGING = (
    ("sec_ownership_mapping", SecBundle),
    ("sec_ownership", SecFiling),
    ("littlesis_snapshot_mapping", LittleSisBundle),
    ("quiver_snapshot_mapping", QuiverBundle),
)
REAL_PROVIDERS = {
    "sec.edgar",
    "littlesis.api",
    "quiver.api",
    "alpaca.market_data",
    "gleif.api",
    "openfigi.api",
}


def source_version(record: CanonicalModel) -> UUID:
    if isinstance(record, (SecBundle, SecFiling, LittleSisBundle, QuiverBundle)):
        return record.source_version_id
    raise ValueError("unsupported adapter record")


class ResearchError(ValueError):
    """Explicit rejected input/protocol; never an unavailable return fabricated as zero."""


def encoded(value: Any) -> bytes:
    if isinstance(value, CanonicalModel):
        value = value.model_dump(mode="json")
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def model_hash(value: CanonicalModel) -> str:
    return digest(encoded(value))


def write_once(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise CanonicalConflictError("immutable research file has different content")
        return
    with path.open("xb") as handle:
        handle.write(content)


def environment() -> tuple[str, str, dict[str, str]]:
    package = Path(__file__).resolve().parents[1]
    root = package.parents[1]
    lock = root / "uv.lock"
    if not lock.exists():
        raise ResearchError("research builds require the locked local project checkout")
    paths = sorted(
        (*package.rglob("*.py"), *(root / "schemas").glob("*.json"), root / "pyproject.toml")
    )
    source = digest(
        encoded({p.relative_to(root).as_posix(): digest(p.read_bytes()) for p in paths})
    )
    runtime = {
        name: version(name)
        for name in (
            "pydantic",
            "pyarrow",
            "duckdb",
            "exchange-calendars",
            "httpx",
            "typer",
            "pandas",
            "numpy",
            "tzdata",
        )
    }
    runtime["python"] = platform.python_version()
    runtime["research"] = VERSION
    return source, digest(lock.read_bytes()), runtime


def private_root(path: Path) -> None:
    resolved = path.resolve()
    if resolved.anchor.startswith(("\\\\", "//")) or any(
        (p / ".git").exists() for p in (resolved, *resolved.parents)
    ):
        raise ResearchError("restricted research must remain outside Git/shared locations")
    if any(
        any(
            marker in part.casefold()
            for marker in ("onedrive", "dropbox", "icloud", "google drive")
        )
        for part in resolved.parts
    ):
        raise ResearchError("restricted research must remain outside known sync locations")


def output_rights(
    config: BuildConfig, observations: tuple[SourceObservation, ...], target: Path
) -> None:
    restricted = any(
        o.retention_class in (RetentionClass.RESTRICTED, RetentionClass.UNKNOWN)
        for o in observations
    )
    if restricted and (
        config.output_rights != "private_only"
        or not config.restricted_raw_retention_permitted
        or not config.restricted_derivatives_permitted
        or not config.license_review_reference
    ):
        raise ResearchError(
            "reviewed upstream raw/derived retention and private output rights required"
        )
    if restricted or config.output_rights == "private_only":
        private_root(target)


def input_rights(root: Path, expected_config: BuildConfig | None = None) -> None:
    """Check the current input location before reading its raw/staging dependency graph.

    A portable snapshot retains its storage restrictions after copying or relocation.
    Only configuration and observation retention metadata are needed for this boundary.
    """
    if expected_config is not None and expected_config.output_rights == "private_only":
        private_root(root)
    config = BuildConfig.model_validate_json((root / "config.json").read_bytes())
    if expected_config is not None and config != expected_config:
        raise ResearchError("snapshot configuration mismatch")
    if config.output_rights == "private_only":
        private_root(root)
    observations = CanonicalParquetStore(DataLayout(root / "data"), read_only=True).load(
        SourceObservation
    )
    output_rights(config, observations, root)


def capture_files(root: Path, observations: tuple[SourceObservation, ...]) -> tuple[Path, ...]:
    matched: set[UUID] = set()
    paths: list[Path] = []
    forbidden = {
        "authorization",
        "apikey",
        "accesstoken",
        "token",
        "secret",
        "password",
        "apcaapikeyid",
        "apcaapisecretkey",
    }

    def secret_keys(value: object) -> bool:
        if isinstance(value, dict):
            return any(
                str(key).lower().replace("_", "").replace("-", "") in forbidden or secret_keys(item)
                for key, item in value.items()
            )
        return isinstance(value, list) and any(secret_keys(item) for item in value)

    for path in sorted((root / "data" / "raw" / "manifests").glob("*.json")):
        manifest = RawCaptureManifest.model_validate_json(path.read_bytes())
        supported = [
            obs
            for obs in observations
            if (
                obs.provider_namespace,
                obs.raw_content_hash,
                obs.adapter_version,
                obs.parser_version,
                obs.retention_class,
                obs.license_name,
            )
            == (
                manifest.provider_namespace,
                manifest.content_hash,
                manifest.adapter_version,
                manifest.parser_version,
                manifest.retention_class,
                manifest.license_name,
            )
        ]
        if not supported:
            continue
        parts = urlsplit(manifest.source_locator or "")
        if (
            parts.username
            or parts.password
            or secret_keys(manifest.request_parameters)
            or secret_keys(dict(parse_qsl(parts.query)))
        ):
            raise ResearchError(
                "credential-bearing capture metadata cannot enter a research snapshot"
            )
        paths.append(path)
        matched.update(obs.source_observation_id for obs in supported)
    if matched != {obs.source_observation_id for obs in observations}:
        raise ResearchError("source observation lacks a matching immutable capture manifest")
    return tuple(paths)


@dataclass
class Inputs:
    root: Path
    config: BuildConfig
    protocol: Protocol
    controls: Controls
    prices: PriceInputs
    origins: OriginInventory
    records: dict[str, tuple[CanonicalModel, ...]]

    def get[T: CanonicalModel](self, model: type[T]) -> tuple[T, ...]:
        return tuple(
            item for item in self.records.get(model.__name__, ()) if isinstance(item, model)
        )

    def inventory_rows(self) -> tuple[tuple[str, str, CanonicalModel], ...]:
        values: list[tuple[str, str, CanonicalModel]] = [
            (model.__name__, str(getattr(record, key)), record)
            for model, key in CORE
            for record in self.get(model)
        ]
        for name, _model in STAGING:
            values.extend(
                (name, str(source_version(record)), record) for record in self.records.get(name, ())
            )
        values.extend(
            ("price_packet", str(packet.packet_id), packet) for packet in self.prices.packets
        )
        values.extend(
            ("identity_binding", str(item.event_id), item) for item in self.controls.bindings
        )
        values.extend(("event_control", str(item.event_id), item) for item in self.controls.events)
        return tuple(sorted(values, key=lambda item: (item[0], item[1])))


def read_inputs(root: Path) -> Inputs:
    config = BuildConfig.model_validate_json((root / "config.json").read_bytes())
    protocol = Protocol.model_validate_json((root / "protocol.json").read_bytes())
    store = CanonicalParquetStore(DataLayout(root / "data"), read_only=True)
    records: dict[str, tuple[CanonicalModel, ...]] = {
        model.__name__: store.load(model) for model, _ in CORE
    }
    for name, model in STAGING:
        records[name] = load_envelope_records(
            root / "data" / "staging" / f"{name}.parquet",
            model_type=model,
            id_field="source_version_id",
            dataset_kind="staging",
            model_schema_version="1.0.0",
        )
    return Inputs(
        root,
        config,
        protocol,
        Controls.model_validate_json((root / "controls.json").read_bytes()),
        PriceInputs.model_validate_json((root / "prices.json").read_bytes()),
        OriginInventory.model_validate_json((root / "origins.json").read_bytes()),
        records,
    )


def inventory_for(inputs: Inputs, origin: str, basis: str) -> OriginInventory:
    """Preparation aid; declarations remain explicit review assertions, not proof of real data."""
    return OriginInventory.model_validate_json(
        encoded(
            {
                "records": [
                    {
                        "dataset": dataset,
                        "record_id": identity,
                        "payload_sha256": model_hash(record),
                        "origin": origin,
                        "basis": basis,
                    }
                    for dataset, identity, record in inputs.inventory_rows()
                ]
            }
        )
    )


def verify_graph(inputs: Inputs) -> None:
    declared = {(r.dataset, r.record_id): r for r in inputs.origins.records}
    required = {
        (dataset, identity): record for dataset, identity, record in inputs.inventory_rows()
    }
    if len(declared) != len(inputs.origins.records) or set(declared) != set(required):
        raise ResearchError("origin inventory must exactly cover the full dependency graph")
    for key, record in required.items():
        if declared[key].payload_sha256 != model_hash(record):
            raise ResearchError("origin assertion refers to a different record payload")
    if inputs.config.mode != "synthetic" and any(
        r.origin == "synthetic" for r in declared.values()
    ):
        raise ResearchError("synthetic support cannot enter a claimed real run")
    observed = {o.source_observation_id: o for o in inputs.get(SourceObservation)}
    capture_files(inputs.root, tuple(observed.values()))
    provenances = {p.provenance_id: p for p in inputs.get(Provenance)}
    subjects = {
        "entity": {e.entity_id for e in inputs.get(Entity)},
        "security": {s.security_id for s in inputs.get(Security)},
        "listing": {listing.listing_id for listing in inputs.get(Listing)},
    }

    def obs(identity: UUID) -> None:
        if identity not in observed:
            raise ResearchError("missing source observation dependency")

    def prov(identity: UUID) -> None:
        if identity not in provenances:
            raise ResearchError("missing provenance dependency")

    for observation in observed.values():
        raw = raw_object_path(DataLayout(inputs.root / "data"), observation.raw_content_hash.value)
        if not raw.exists() or digest(raw.read_bytes()) != observation.raw_content_hash.value:
            raise ResearchError("raw evidence missing or hash mismatch")
    for provenance in provenances.values():
        for identity in provenance.source_observation_ids:
            obs(identity)
        for identity in provenance.parent_provenance_ids:
            prov(identity)

    def walk(identity: UUID, ancestors: frozenset[UUID]) -> None:
        if identity in ancestors:
            raise ResearchError("cyclic provenance graph")
        for parent in provenances[identity].parent_provenance_ids:
            walk(parent, ancestors | {identity})

    for identity in provenances:
        walk(identity, frozenset())
    for entity in inputs.get(Entity):
        prov(entity.provenance_id)
        for alias in entity.aliases:
            obs(alias.source_observation_id)
            prov(alias.provenance_id)
        for claim in entity.external_identifiers:
            obs(claim.source_observation_id)
            prov(claim.provenance_id)
    for security in inputs.get(Security):
        if security.issuer_entity_id not in subjects["entity"]:
            raise ResearchError("security has no canonical issuer")
        prov(security.provenance_id)
        for claim in security.external_identifiers:
            obs(claim.source_observation_id)
            prov(claim.provenance_id)
    for listing in inputs.get(Listing):
        if listing.security_id not in subjects["security"]:
            raise ResearchError("listing has no canonical security")
        prov(listing.provenance_id)
        for claim in listing.external_identifiers:
            obs(claim.source_observation_id)
            prov(claim.provenance_id)
    for claim in inputs.get(ExternalIdentifier):
        if claim.subject_id not in subjects[claim.subject_type.value]:
            raise ResearchError("orphan identifier claim")
        obs(claim.source_observation_id)
        prov(claim.provenance_id)
    for relation in inputs.get(Relationship):
        for endpoint in (relation.source, relation.target):
            if endpoint.subject_id not in subjects[endpoint.subject_type.value]:
                raise ResearchError("orphan relationship endpoint")
        prov(relation.provenance_id)
        for identity in relation.source_observation_ids:
            obs(identity)
    events = {event.event_id: event for event in inputs.get(Event)}
    evidence = {item.event_evidence_id: item for item in inputs.get(EventEvidence)}
    for event in events.values():
        prov(event.provenance_id)
        for evidence_id in event.event_evidence_ids:
            if evidence_id not in evidence or evidence[evidence_id].event_id != event.event_id:
                raise ResearchError("event evidence is missing or references another event")
        for party in (*event.actors, *event.economic_units):
            if party.entity_id not in subjects["entity"]:
                raise ResearchError("event party has no canonical entity")
        for kind, reference_id in (
            ("entity", event.issuer_entity_id),
            ("security", event.security_id),
            ("listing", event.listing_id),
        ):
            if reference_id is not None and reference_id not in subjects[kind]:
                raise ResearchError("event has orphan identity reference")
    for evidence_record in evidence.values():
        if evidence_record.event_id not in events:
            raise ResearchError("evidence has no canonical event")
        prov(evidence_record.provenance_id)
        for identity in evidence_record.source_observation_ids:
            obs(identity)
    for packet in inputs.prices.packets:
        request = packet.request
        if request.feed != inputs.config.feed or request.adjustment != inputs.config.adjustment:
            raise ResearchError("price request differs from configured feed/adjustment")
        packet_listing = next(
            (item for item in inputs.get(Listing) if item.listing_id == request.listing_id), None
        )
        if packet_listing is None or packet_listing.security_id != request.security_id:
            raise ResearchError("price packet identity missing")
        expected = type(request).from_listing(
            packet_listing,
            start=request.start,
            end=request.end,
            provider_asof=request.symbols[0].provider_asof,
            adjustment=request.adjustment,
            feed=request.feed,
        )
        if expected != request:
            raise ResearchError("price request is not its canonical listing segment")
        for observation in packet.batch.observations:
            if inputs.config.mode != "synthetic" and (
                observation.provider_namespace != "alpaca.market_data"
                or observation.lineage.source_family != "alpaca.stock_bars"
                or observation.adapter_version != "alpaca-bars/1.0.0"
                or observation.parser_version != "alpaca-bars-json/1.0.0"
            ):
                raise ResearchError("real prices require the reviewed existing provider contract")
            if observed.get(observation.source_observation_id) != observation:
                raise ResearchError("price observation differs from frozen canonical evidence")
        for identity in packet.batch.capture_ids:
            manifest_path = inputs.root / "data" / "raw" / "manifests" / f"{identity}.json"
            if not manifest_path.exists() or RawCaptureManifest.model_validate_json(
                manifest_path.read_bytes()
            ).content_hash.value not in {
                o.raw_content_hash.value for o in packet.batch.observations
            }:
                raise ResearchError("price packet capture evidence missing or incompatible")
        for bar in packet.batch.bars:
            if bar.feed != request.feed or bar.adjustment != request.adjustment:
                raise ResearchError("bar differs from request feed/adjustment")
            if bar.source_observation_id not in {
                o.source_observation_id for o in packet.batch.observations
            }:
                raise ResearchError("price bar lacks packet evidence")
            if (
                bar.provider_namespace != observed[bar.source_observation_id].provider_namespace
                or bar.security_id != request.security_id
                or bar.listing_id != request.listing_id
            ):
                raise ResearchError("bar provider/identity disagrees with request/evidence")
            if (
                not request.start <= bar.session_date <= request.end
                or bar.session_date > inputs.config.coverage_through
            ):
                raise ResearchError("bar outside requested completed coverage")
    for binding in inputs.controls.bindings:
        if (
            binding.event_id not in events
            or binding.security_id not in subjects["security"]
            or binding.listing_id not in subjects["listing"]
        ):
            raise ResearchError("reviewed identity binding has orphan reference")
        for identity in binding.listing_history_ids:
            if identity not in subjects["listing"]:
                raise ResearchError("missing listing history segment")
        for identity in binding.provenance_ids:
            prov(identity)
    for control in inputs.controls.events:
        if control.event_id not in events:
            raise ResearchError("control refers to missing event")
        if control.terminal_observation_id is not None:
            obs(control.terminal_observation_id)
    if inputs.config.mode != "synthetic":
        if any(r.origin == "synthetic" for r in declared.values()):
            raise ResearchError("synthetic support cannot enter a claimed real run")
        if any(
            o.provider_namespace not in REAL_PROVIDERS
            or o.lineage.observation_role is ObservationRole.SYNTHETIC
            or o.retention_class is RetentionClass.INTERNAL
            for o in observed.values()
        ):
            raise ResearchError("unreviewed/synthetic provider dependency in real run")
        if any(
            isinstance(b, QuiverBundle) and b.synthetic
            for b in inputs.records.get("quiver_snapshot_mapping", ())
        ):
            raise ResearchError("synthetic vendor staging in real run")
        if inputs.config.mode in ("discovery", "validation") and any(
            r.origin == "unverified" for r in declared.values()
        ):
            raise ResearchError("unverified dependency cannot support real outcome evaluation")


def freeze(prepared: Path, target: Path) -> Snapshot:
    if target.is_symlink():
        raise ResearchError("snapshot target must not be a symlink")
    input_rights(prepared)
    inputs = read_inputs(prepared)
    output_rights(inputs.config, inputs.get(SourceObservation), target)
    verify_graph(inputs)
    paths = [
        prepared / name
        for name in ("config.json", "protocol.json", "controls.json", "prices.json", "origins.json")
    ]
    store = CanonicalParquetStore(DataLayout(prepared / "data"), read_only=True)
    paths.extend(p for model, _ in CORE if (p := store.path_for(model)).exists())
    paths.extend(
        p
        for name, _ in STAGING
        if (p := prepared / "data" / "staging" / f"{name}.parquet").exists()
    )
    paths.extend(
        raw_object_path(DataLayout(prepared / "data"), o.raw_content_hash.value)
        for o in inputs.get(SourceObservation)
    )
    paths.extend(capture_files(prepared, inputs.get(SourceObservation)))
    files = tuple(
        InputFile(path=p.relative_to(prepared).as_posix(), sha256=digest(p.read_bytes()))
        for p in sorted(set(paths))
    )
    source, lock, runtime = environment()
    provisional = Snapshot(
        snapshot_id=UUID(int=0),
        config=inputs.config,
        protocol_sha256=model_hash(inputs.protocol),
        source_code_sha256=source,
        dependency_lock_sha256=lock,
        canonical_schema_version=MODEL_SCHEMA_VERSION,
        runtime_versions=runtime,
        files=files,
    )
    snapshot = provisional.model_copy(
        update={"snapshot_id": uuid5(NAMESPACE, model_hash(provisional))}
    )
    if target.exists():
        verify_snapshot(target)
        if (target / "snapshot.json").read_bytes() != encoded(snapshot):
            raise CanonicalConflictError("snapshot target already contains different inputs")
        return snapshot
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as temp:
        staging = Path(temp) / "snapshot"
        staging.mkdir()
        assert staging.resolve().is_relative_to(target.parent.resolve())
        for item in files:
            destination = staging / item.path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(prepared / item.path, destination)
            if digest(destination.read_bytes()) != item.sha256:
                raise ResearchError("input changed during freeze")
        write_once(staging / "snapshot.json", encoded(snapshot))
        os.replace(staging, target)
    return snapshot


def verify_snapshot(root: Path) -> Snapshot:
    snapshot = Snapshot.model_validate_json((root / "snapshot.json").read_bytes())
    input_rights(root, snapshot.config)
    provisional = snapshot.model_copy(update={"snapshot_id": UUID(int=0)})
    if uuid5(NAMESPACE, model_hash(provisional)) != snapshot.snapshot_id:
        raise ResearchError("snapshot identity disagrees with manifest")
    source, lock, runtime = environment()
    if (source, lock, runtime) != (
        snapshot.source_code_sha256,
        snapshot.dependency_lock_sha256,
        snapshot.runtime_versions,
    ):
        raise ResearchError("code/dependency environment differs from frozen build")
    for item in snapshot.files:
        path = root / item.path
        if (
            not path.resolve().is_relative_to(root.resolve())
            or not path.is_file()
            or digest(path.read_bytes()) != item.sha256
        ):
            raise ResearchError("frozen input missing, unsafe or changed")
    inputs = read_inputs(root)
    if inputs.config != snapshot.config or model_hash(inputs.protocol) != snapshot.protocol_sha256:
        raise ResearchError("snapshot configuration/protocol mismatch")
    verify_graph(inputs)
    return snapshot
