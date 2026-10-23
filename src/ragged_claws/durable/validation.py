"""Fail-closed full-generation validation. No source-label-only or extension-only permission."""

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import pyarrow.parquet as pq  # type: ignore[import-untyped]
from pydantic import BaseModel

from ragged_claws.durable.models import (
    MAX_FILE,
    MAX_FILES,
    MAX_TOTAL,
    ROOTS,
    CloudPolicy,
    DurableError,
    FileEntry,
    safe_path,
)
from ragged_claws.ingestion.littlesis_models import LittleSisBundle
from ragged_claws.ingestion.littlesis_parser import LICENSE_URL
from ragged_claws.ingestion.sec import ADAPTER_VERSION as SEC_ADAPTER_VERSION
from ragged_claws.ingestion.sec import PARSER_VERSION as SEC_PARSER_VERSION
from ragged_claws.ingestion.synthetic import SyntheticStagingRecord
from ragged_claws.models import (
    Entity,
    Event,
    EventEvidence,
    ExternalIdentifier,
    FeatureValue,
    Listing,
    Outcome,
    Provenance,
    RetentionClass,
    Security,
    SourceObservation,
    SubjectReference,
)
from ragged_claws.models.base import CanonicalModel
from ragged_claws.research.build import markdown
from ragged_claws.research.models import (
    Registration,
    ResearchReport,
    ResearchRow,
    Snapshot,
)
from ragged_claws.research.snapshot import (
    CORE,
    STAGING,
    digest,
    encoded,
    input_rights,
    model_hash,
    read_inputs,
    verify_graph,
)
from ragged_claws.storage import (
    CanonicalParquetStore,
    DataLayout,
    PersistenceError,
    load_envelope_records,
)
from ragged_claws.storage.raw import RAW_CAPTURE_NAMESPACE, RawCaptureManifest

CANONICAL = (*CORE, (FeatureValue, "feature_value_id"), (Outcome, "outcome_id"))
STAGED: dict[str, type[CanonicalModel]] = {
    **{name + ".parquet": model for name, model in STAGING},
    "synthetic_event.parquet": SyntheticStagingRecord,
}


def json_value(content: bytes) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise DurableError("duplicate_json_key")
            value[key] = item
        return value

    return json.loads(content, object_pairs_hook=unique)


def metadata_secrets(value: Any) -> None:
    """Reject rather than redact authoritative bytes; never print a rejected key/value."""
    forbidden = {
        "apikey",
        "accesstoken",
        "authorization",
        "password",
        "secret",
        "secretkey",
        "awsaccesskeyid",
        "awssecretaccesskey",
        "apcaapikeyid",
        "apcaapisecretkey",
        "token",
    }
    if isinstance(value, dict):
        if any(str(k).casefold().replace("_", "").replace("-", "") in forbidden for k in value):
            raise DurableError("credential_metadata_forbidden")
        for item in value.values():
            metadata_secrets(item)
    elif isinstance(value, list):
        for item in value:
            metadata_secrets(item)
    elif isinstance(value, str) and "://" in value:
        from urllib.parse import parse_qsl, urlsplit

        parsed = urlsplit(value)
        if parsed.username or parsed.password:
            raise DurableError("credential_metadata_forbidden")
        metadata_secrets(dict(parse_qsl(parsed.query)))


def read_local(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_FILE:
        raise DurableError("unsafe_or_oversized_input")
    with path.open("rb") as handle:
        content = handle.read(MAX_FILE + 1)
    if len(content) > MAX_FILE:
        raise DurableError("unsafe_or_oversized_input")
    return content


def capture_layout(root: Path) -> dict[str, bytes]:
    if root.is_symlink() or not root.is_dir():
        raise DurableError("unsafe_layout_root")
    result: dict[str, bytes] = {}
    total = 0
    for scope in sorted(ROOTS):
        parent = root / scope
        if not parent.exists():
            continue
        if parent.is_symlink() or not parent.is_dir():
            raise DurableError("unsafe_layout_path")
        for directory, dirs, names in os.walk(parent, followlinks=False):
            for name in (*dirs, *names):
                path = Path(directory) / name
                relative = safe_path(path.relative_to(root).as_posix())
                if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                    raise DurableError("unsafe_layout_path")
                if path.is_dir():
                    continue
                content = read_local(path)
                total += len(content)
                if len(result) >= MAX_FILES or total > MAX_TOTAL:
                    raise DurableError("generation_too_large")
                result[relative] = content
    if len({p.casefold() for p in result}) != len(result):
        raise DurableError("case_colliding_paths")
    return dict(sorted(result.items()))


@dataclass
class Validated:
    files: dict[str, bytes]
    # Typed record identity/payload maps used for parent/candidate monotonic conflict checks.
    envelopes: dict[str, dict[str, str]]
    notices: tuple[str, ...]
    record_counts: dict[str, int]


@dataclass
class EvidenceContext:
    """Dependencies visible to one normal filesystem loader, not a generation-wide union."""

    records: dict[type[BaseModel], dict[str, BaseModel]] = field(
        default_factory=lambda: {model: {} for model, _ in CANONICAL}
    )
    models: list[BaseModel] = field(default_factory=list)
    manifests: list[RawCaptureManifest] = field(default_factory=list)
    raw_hashes: set[str] = field(default_factory=set)
    bundles: list[LittleSisBundle] = field(default_factory=list)


def _evidence_scope(parts: tuple[str, ...]) -> str:
    if parts[0] == "snapshots":
        UUID(parts[1])
        return "/".join(parts[:3])  # snapshots/UUID/data
    if parts[0] == "research":
        UUID(parts[1])
        return "/".join(parts[:2])  # research/UUID (registry is handled separately)
    return ""


def _scoped_research(frozen: EvidenceContext, result: EvidenceContext) -> EvidenceContext:
    """Only a result's explicit matching frozen inputs may supply its external dependencies."""
    return EvidenceContext(
        records={
            model: {**frozen.records[model], **result.records[model]} for model, _ in CANONICAL
        },
        models=[*frozen.models, *result.models],
        manifests=[*frozen.manifests, *result.manifests],
        raw_hashes=frozen.raw_hashes | result.raw_hashes,
        bundles=[*frozen.bundles, *result.bundles],
    )


def _parquet_expansion(path: Path) -> int:
    meta = pq.read_metadata(path)
    expanded = sum(
        meta.row_group(i).column(j).total_uncompressed_size
        for i in range(meta.num_row_groups)
        for j in range(meta.num_columns)
    )
    if meta.num_rows > 50000 or expanded > 64 * 1024 * 1024:
        raise DurableError("parquet_expansion_bound_exceeded")
    return int(expanded)


def _read_parquet(path: Path, model: type[BaseModel], key: str, kind: str) -> tuple[BaseModel, ...]:
    _parquet_expansion(path)
    return load_envelope_records(
        path,
        model_type=model,
        id_field=key,
        dataset_kind=kind,  # type: ignore[arg-type]
        model_schema_version="1.0.0",
    )


def _canonical_location(parts: tuple[str, ...]) -> bool:
    return (
        (len(parts) == 2 and parts[0] == "curated")
        or (len(parts) == 5 and parts[0] == "snapshots" and parts[2:4] == ("data", "curated"))
        or (len(parts) == 4 and parts[0] == "research" and parts[2] == "curated")
    )


def validate_layout(root: Path, policy: CloudPolicy) -> Validated:
    try:
        return _validate_layout(root, policy)
    except DurableError:
        raise
    except (ValueError, PersistenceError, OSError, KeyError, TypeError):
        raise DurableError("invalid_or_unsupported_durable_state") from None


def _validate_layout(root: Path, policy: CloudPolicy) -> Validated:
    metadata_secrets(policy.model_dump(mode="json"))
    # Inspect only retention/configuration metadata before traversing raw/research payloads.
    frozen_parent = root / "snapshots"
    data_roots = [root]
    if frozen_parent.exists():
        if frozen_parent.is_symlink():
            raise DurableError("unsafe_layout_path")
        for child in frozen_parent.iterdir():
            if child.is_symlink() or not child.resolve().is_relative_to(root.resolve()):
                raise DurableError("unsafe_layout_path")
            if child.is_dir():
                input_rights(child)
                data_roots.append(child / "data")
    forbidden = 0
    manifest_count = 0
    for data_root in data_roots:
        observation_path = data_root / "curated" / "source_observation.parquet"
        if observation_path.exists():
            if not observation_path.resolve().is_relative_to(root.resolve()):
                raise DurableError("unsafe_layout_path")
            read_local(observation_path)
            for observation in _read_parquet(
                observation_path, SourceObservation, "source_observation_id", "curated"
            ):
                assert isinstance(observation, SourceObservation)
                forbidden += observation.retention_class in (
                    RetentionClass.RESTRICTED,
                    RetentionClass.UNKNOWN,
                )
        manifest_root = data_root / "raw" / "manifests"
        if manifest_root.is_symlink() or not manifest_root.resolve().is_relative_to(root.resolve()):
            raise DurableError("unsafe_layout_path")
        for path in manifest_root.glob("*.json"):
            manifest_count += 1
            if manifest_count > MAX_FILES:
                raise DurableError("generation_too_large")
            value = RawCaptureManifest.model_validate_json(read_local(path))
            forbidden += value.retention_class in (
                RetentionClass.RESTRICTED,
                RetentionClass.UNKNOWN,
            )
    if forbidden:
        raise DurableError("cloud_retention_or_source_not_approved", forbidden)
    files = capture_layout(root)
    if sum(_parquet_expansion(root / p) for p in files if p.endswith(".parquet")) > MAX_TOTAL:
        raise DurableError("aggregate_parquet_expansion_bound_exceeded")
    store = CanonicalParquetStore(DataLayout(root), read_only=True)
    curated_specs = {store.path_for(m).name: (m, key) for m, key in CANONICAL}
    records: dict[type[BaseModel], dict[str, BaseModel]] = {m: {} for m, _ in CANONICAL}
    # The union remains useful for identity conflicts/counts, never dependency closure.
    contexts = {"": EvidenceContext()}
    envelopes: dict[str, dict[str, str]] = {}
    bundles: list[LittleSisBundle] = []
    frozen: set[Path] = set()
    reports: set[Path] = set()
    journals: dict[str, dict[str, Any]] = {}
    for name, content in files.items():
        parts = tuple(name.split("/"))
        path = root / name
        model: type[BaseModel] | None = None
        key = "source_version_id"
        kind = "staging"
        if _canonical_location(parts):
            if parts[-1] not in curated_specs:
                raise DurableError("unsupported_canonical_dataset")
            model, key = curated_specs[parts[-1]]
            kind = "curated"
        elif (len(parts) == 2 and parts[0] == "staging") or (
            len(parts) == 5 and parts[0] == "snapshots" and parts[2:4] == ("data", "staging")
        ):
            model = STAGED.get(parts[-1])
            if model is None:
                raise DurableError("unsupported_staging_dataset")
        elif len(parts) == 3 and parts[0] == "research" and parts[-1] == "research_rows.parquet":
            model, key = ResearchRow, "row_id"
        if model is not None:
            scope = _evidence_scope(parts)
            context = contexts.setdefault(scope, EvidenceContext())
            if scope.startswith("research/"):
                reports.add(root / scope)
            loaded = _read_parquet(path, model, key, kind)
            envelopes[name] = {str(getattr(r, key)): r.model_dump_json() for r in loaded}
            context.models.extend(loaded)
            if kind == "curated":
                for record in loaded:
                    identity = str(getattr(record, key))
                    old = records[model].get(identity)
                    if old is not None and old != record:
                        raise DurableError("canonical_identity_payload_conflict")
                    records[model][identity] = record
                    context.records[model][identity] = record
            bundles.extend(r for r in loaded if isinstance(r, LittleSisBundle))
            context.bundles.extend(r for r in loaded if isinstance(r, LittleSisBundle))
            continue
        raw_parts = parts[3:] if parts[:1] == ("snapshots",) and parts[2:3] == ("data",) else parts
        if raw_parts[:2] == ("raw", "objects") and len(raw_parts) == 4:
            if raw_parts[2] != raw_parts[3][:2] or digest(content) != raw_parts[3]:
                raise DurableError("raw_content_address_mismatch")
            contexts.setdefault(_evidence_scope(parts), EvidenceContext()).raw_hashes.add(
                raw_parts[3]
            )
            if content.lstrip()[:1] in (b"{", b"["):
                metadata_secrets(json_value(content))
            continue
        if raw_parts[:2] == ("raw", "manifests") and len(raw_parts) == 3:
            value = json_value(content)
            metadata_secrets(value)
            manifest = RawCaptureManifest.model_validate_json(content)
            provisional = manifest.model_dump(mode="json", exclude={"capture_id"})
            manifest_id = uuid5(RAW_CAPTURE_NAMESPACE, encoded(provisional).decode().rstrip("\n"))
            if raw_parts[-1] != f"{manifest.capture_id}.json" or manifest_id != manifest.capture_id:
                raise DurableError("raw_manifest_identity_mismatch")
            contexts.setdefault(_evidence_scope(parts), EvidenceContext()).manifests.append(
                manifest
            )
            continue
        if len(parts) >= 3 and parts[0] == "snapshots":
            UUID(parts[1])
            if len(parts) != 3 or parts[-1] not in {
                "snapshot.json",
                "config.json",
                "protocol.json",
                "controls.json",
                "prices.json",
                "origins.json",
            }:
                raise DurableError("unsupported_frozen_file")
            metadata_secrets(json_value(content))
            frozen.add(root / "snapshots" / parts[1])
            continue
        if len(parts) == 3 and parts[0] == "research" and parts[1] != "registry":
            UUID(parts[1])
            if parts[-1] not in {"report.json", "report.md", "result.json", "snapshot.json"}:
                raise DurableError("unsupported_research_file")
            if parts[-1].endswith(".json"):
                metadata_secrets(json_value(content))
            reports.add(path.parent)
            continue
        if len(parts) == 4 and parts[:2] == ("research", "registry"):
            value = json_value(content)
            metadata_secrets(value)
            if parts[2] == "registrations":
                registration = Registration.model_validate_json(content)
                if parts[-1] != f"{registration.protocol_sha256}.json":
                    raise DurableError("registration_identity_mismatch")
            elif parts[2] == "attempts":
                journals[parts[-1]] = value
            else:
                raise DurableError("unsupported_journal_file")
            continue
        raise DurableError("file_not_in_validated_allowlist")
    _validate_context(contexts[""], policy)
    for parent in frozen:
        scope = parent.relative_to(root).as_posix() + "/data"
        _validate_context(contexts.setdefault(scope, EvidenceContext()), policy)
        _historical_snapshot(parent)
    for parent in reports:
        _research_result(parent, frozen)
        scope = parent.relative_to(root).as_posix()
        frozen_scope = f"snapshots/{parent.name}/data"
        _validate_context(
            _scoped_research(contexts[frozen_scope], contexts.setdefault(scope, EvidenceContext())),
            policy,
        )
    _journals(journals)
    # Re-read after parsing: upload bytes must be precisely the validated stable input.
    if files != capture_layout(root):
        raise DurableError("candidate_changed_during_validation")
    notices = tuple(
        sorted(
            {
                f"{b.attribution}\n{b.snapshot.copyright}\n{b.snapshot.license_url}\n{b.change_notice}"
                for b in bundles
            }
        )
    )
    return Validated(files, envelopes, notices, {m.__name__: len(v) for m, v in records.items()})


def _validate_context(context: EvidenceContext, policy: CloudPolicy) -> None:
    observed = [
        o for o in context.records[SourceObservation].values() if isinstance(o, SourceObservation)
    ]
    _rights(policy, observed, context.manifests, context.bundles)
    for manifest in context.manifests:
        if manifest.content_hash.value not in context.raw_hashes:
            raise DurableError("manifest_raw_dependency_missing")
    if context.raw_hashes != {m.content_hash.value for m in context.manifests}:
        raise DurableError("raw_object_without_retention_manifest")
    for observation in observed:
        if observation.raw_content_hash.value not in context.raw_hashes or not any(
            m.content_hash == observation.raw_content_hash
            and m.provider_namespace == observation.provider_namespace
            and m.source_family == observation.lineage.source_family
            and m.adapter_version == observation.adapter_version
            and m.parser_version == observation.parser_version
            and m.retention_class == observation.retention_class
            and m.license_name == observation.license_name
            for m in context.manifests
        ):
            raise DurableError("observation_raw_manifest_dependency_missing")
    _lineage(context.records, context.models)


def _rights(
    policy: CloudPolicy,
    observations: list[SourceObservation],
    manifests: list[RawCaptureManifest],
    bundles: list[LittleSisBundle],
) -> None:
    blocked = 0
    values: list[SourceObservation | RawCaptureManifest] = [*observations, *manifests]
    allowed = {("sec.edgar", "sec.ownership")}
    if policy.allow_littlesis:
        allowed.add(("littlesis.api", "littlesis.relationships"))
    for value in values:
        metadata_secrets(value.model_dump(mode="json"))
        if value.retention_class in (RetentionClass.RESTRICTED, RetentionClass.UNKNOWN):
            blocked += 1
            continue
        if policy.scope == "invented_engineering":
            if not value.provider_namespace.startswith("synthetic."):
                blocked += 1
        elif value.retention_class is not RetentionClass.PUBLIC or (
            (
                value.provider_namespace,
                value.lineage.source_family
                if isinstance(value, SourceObservation)
                else value.source_family,
            )
            not in allowed
        ):
            blocked += 1
        elif value.provider_namespace == "sec.edgar":
            from urllib.parse import urlsplit

            locator = urlsplit(value.source_locator or "")
            if (
                value.license_name != "sec-public-filings"
                or value.adapter_version != SEC_ADAPTER_VERSION
                or value.parser_version != SEC_PARSER_VERSION
                or locator.scheme != "https"
                or locator.hostname != "www.sec.gov"
                or not locator.path.startswith("/Archives/edgar/data/")
                or locator.query
                or locator.fragment
                or (
                    isinstance(value, SourceObservation)
                    and value.lineage.observation_role.value != "primary_source"
                )
            ):
                blocked += 1
    if blocked:
        raise DurableError("cloud_retention_or_source_not_approved", blocked)
    little = [o for o in observations if o.provider_namespace == "littlesis.api"]
    if little and (
        not policy.allow_littlesis
        or any(
            not any(
                b.observation == o
                and b.snapshot.license_url == LICENSE_URL
                and b.attribution
                and b.change_notice
                and b.snapshot.copyright
                for b in bundles
            )
            for o in little
        )
    ):
        raise DurableError("share_alike_evidence_or_notices_missing", len(little))


def _lineage(records: dict[type[BaseModel], dict[str, BaseModel]], models: list[BaseModel]) -> None:
    ids = {m: set(v) for m, v in records.items()}
    inline_features: dict[str, str] = {}
    subjects: dict[str, type[BaseModel]] = {
        "entity": Entity,
        "security": Security,
        "listing": Listing,
    }
    fields: dict[str, type[BaseModel]] = {
        "provenance_id": Provenance,
        "parent_provenance_ids": Provenance,
        "source_observation_id": SourceObservation,
        "source_observation_ids": SourceObservation,
        "price_source_observation_ids": SourceObservation,
        "terminal_observation_id": SourceObservation,
        "issuer_entity_id": Entity,
        "entity_id": Entity,
        "security_id": Security,
        "listing_id": Listing,
        "benchmark_listing_id": Listing,
        "listing_history_ids": Listing,
        "event_id": Event,
        "event_evidence_ids": EventEvidence,
    }

    def walk(value: Any) -> None:
        if isinstance(value, BaseModel):
            if isinstance(value, FeatureValue):
                identity = str(value.feature_value_id)
                payload = value.model_dump_json()
                if inline_features.get(identity, payload) != payload:
                    raise DurableError("inline_feature_identity_conflict")
                inline_features[identity] = payload
            for canonical_model, canonical_key in CANONICAL:
                if isinstance(value, FeatureValue) and not records[FeatureValue].get(
                    str(value.feature_value_id)
                ):
                    # ResearchRows own inline features; no global FeatureValue file is required.
                    continue
                if isinstance(value, canonical_model) and (
                    (stored := records[canonical_model].get(str(getattr(value, canonical_key))))
                    is None
                    or stored.model_dump_json() != value.model_dump_json()
                ):
                    raise DurableError("embedded_canonical_payload_conflict")
            if (
                isinstance(value, (SubjectReference, ExternalIdentifier))
                and str(value.subject_id) not in ids[subjects[value.subject_type.value]]
            ):
                raise DurableError("orphan_subject_reference")
            for field in type(value).model_fields:
                item = getattr(value, field)
                if item is not None and field in fields:
                    references = item if isinstance(item, tuple) else (item,)
                    if any(str(ref) not in ids[fields[field]] for ref in references):
                        raise DurableError("orphan_canonical_evidence_reference")
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)

    for model in models:
        walk(model)
    provenances = records[Provenance]
    completed: set[str] = set()

    def visit(identity: str, trail: frozenset[str]) -> None:
        if identity in trail:
            raise DurableError("cyclic_provenance")
        if identity in completed:
            return
        if len(trail) >= 128:
            raise DurableError("provenance_depth_bound_exceeded")
        value = provenances[identity]
        assert isinstance(value, Provenance)
        for parent in value.parent_provenance_ids:
            visit(str(parent), trail | {identity})
        completed.add(identity)

    for identity in provenances:
        visit(identity, frozenset())
    for value in records[EventEvidence].values():
        assert isinstance(value, EventEvidence)
        event = records[Event][str(value.event_id)]
        assert isinstance(event, Event)
        for evidence_id in event.event_evidence_ids:
            evidence = records[EventEvidence][str(evidence_id)]
            assert isinstance(evidence, EventEvidence)
            if evidence.event_id != event.event_id:
                raise DurableError("evidence_event_mismatch")


def _historical_snapshot(root: Path) -> None:
    snapshot = Snapshot.model_validate_json(read_local(root / "snapshot.json"))
    if (
        str(snapshot.snapshot_id) != root.name
        or uuid5(
            UUID("ee439b54-3da4-4427-8da2-d0b3ff49e7e7"),
            model_hash(snapshot.model_copy(update={"snapshot_id": UUID(int=0)})),
        )
        != snapshot.snapshot_id
    ):
        raise DurableError("historical_snapshot_identity_mismatch")
    seen = set()
    for entry in snapshot.files:
        safe_path(entry.path)
        path = root / entry.path
        if (
            not path.resolve().is_relative_to(root.resolve())
            or digest(read_local(path)) != entry.sha256
        ):
            raise DurableError("historical_snapshot_file_mismatch")
        if entry.path.casefold() in seen:
            raise DurableError("historical_snapshot_duplicate_file")
        seen.add(entry.path.casefold())
    actual = {
        p.relative_to(root).as_posix().casefold()
        for p in root.rglob("*")
        if p.is_file() and p.name != "snapshot.json"
    }
    if actual != seen:
        raise DurableError("historical_snapshot_inventory_mismatch")
    input_rights(root, snapshot.config)
    inputs = read_inputs(root)
    if model_hash(inputs.protocol) != snapshot.protocol_sha256:
        raise DurableError("historical_protocol_mismatch")
    # Validate content/lineage without executing or rewriting historical code fingerprints.
    verify_graph(inputs)


def _research_result(root: Path, frozen: set[Path]) -> None:
    snapshot = Snapshot.model_validate_json(read_local(root / "snapshot.json"))
    matching = [p for p in frozen if p.name == str(snapshot.snapshot_id)]
    if len(matching) != 1 or read_local(matching[0] / "snapshot.json") != read_local(
        root / "snapshot.json"
    ):
        raise DurableError("research_frozen_dependency_missing")
    report = ResearchReport.model_validate_json(read_local(root / "report.json"))
    if str(report.snapshot_id) != root.name or report.mode != snapshot.config.mode:
        raise DurableError("research_report_identity_mismatch")
    if read_local(root / "report.md") != markdown(report):
        raise DurableError("unsupported_research_report_rendering")
    result = json_value(read_local(root / "result.json"))
    actual = {
        p.relative_to(root).as_posix(): digest(read_local(p))
        for p in root.rglob("*")
        if p.is_file() and p.name != "result.json"
    }
    if result != {"snapshot_id": str(snapshot.snapshot_id), "files": actual}:
        raise DurableError("research_result_manifest_mismatch")
    rows = _read_parquet(root / "research_rows.parquet", ResearchRow, "row_id", "staging")
    for summary in report.horizons:
        selected = [
            r
            for r in rows
            if isinstance(r, ResearchRow) and r.horizon_sessions == summary.horizon_sessions
        ]
        if summary.denominator != len(selected) or any(
            summary.counts[status] != count
            for status, count in Counter(r.status for r in selected).items()
        ):
            raise DurableError("research_report_denominator_mismatch")


def _journals(records: dict[str, dict[str, Any]]) -> None:
    from datetime import datetime

    from ragged_claws.research.models import Period

    for name, value in records.items():
        if name.endswith(".started.json"):
            identity = str(UUID(name.removesuffix(".started.json")))
            if (
                set(value)
                != {
                    "attempt_id",
                    "snapshot_id",
                    "hypothesis_id",
                    "protocol_sha256",
                    "mode",
                    "period",
                    "potential_coverage_end",
                    "started_at",
                }
                or value["attempt_id"] != identity
            ):
                raise DurableError("invalid_inspection_journal_start")
            UUID(value["snapshot_id"])
            Period.model_validate_json(encoded(value["period"]))
            datetime.fromisoformat(value["started_at"])
            if value["mode"] not in {"synthetic", "diagnostic", "discovery", "validation"}:
                raise DurableError("invalid_inspection_journal_mode")
        elif name.endswith(".finished.json"):
            if name.replace(".finished.json", ".started.json") not in records or set(value) - {
                "outcome_inspection",
                "success",
                "finished_at",
                "inspection_period",
            }:
                raise DurableError("invalid_inspection_journal_finish")
            if not isinstance(value.get("outcome_inspection"), bool) or not isinstance(
                value.get("success"), bool
            ):
                raise DurableError("invalid_inspection_journal_finish")
            datetime.fromisoformat(value["finished_at"])
            if "inspection_period" in value:
                Period.model_validate_json(encoded(value["inspection_period"]))
        else:
            raise DurableError("unsupported_inspection_journal_file")


def compare_parent(parent: Validated, candidate: Validated) -> None:
    for name, old in parent.files.items():
        if name not in candidate.files:
            raise DurableError("parent_state_removed")
        if old == candidate.files[name]:
            continue
        if (
            name.startswith(("curated/", "staging/"))
            and name in parent.envelopes
            and name in candidate.envelopes
        ):
            current = candidate.envelopes[name]
            if any(
                current.get(identity) != payload
                for identity, payload in parent.envelopes[name].items()
            ):
                raise DurableError("canonical_or_staging_identity_conflict")
        else:
            raise DurableError("immutable_history_conflict")


def entries(validated: Validated) -> tuple[FileEntry, ...]:
    return tuple(
        FileEntry(path=p, sha256=digest(b), size=len(b)) for p, b in validated.files.items()
    )
