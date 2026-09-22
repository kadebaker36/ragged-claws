"""Append-only content-addressed raw capture and manifest storage."""

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid5

from pydantic import Field, JsonValue

from ragged_claws.models import ContentHash, RetentionClass
from ragged_claws.models.base import CanonicalModel, NonEmptyStr, Slug, UtcDatetime
from ragged_claws.storage.layout import DataLayout
from ragged_claws.temporal import normalize_utc

RAW_CAPTURE_NAMESPACE = UUID("f708657d-2145-5be8-9f8d-7dc2219cd860")


class RawCaptureError(RuntimeError):
    """Base error for immutable raw-capture failures."""


class RawIntegrityError(RawCaptureError):
    """Raised when existing content-addressed state fails verification."""


class RawCaptureManifest(CanonicalModel):
    """One retrieval/capture, distinct from its immutable content object."""

    manifest_version: Literal["1.0.0"] = "1.0.0"
    capture_id: UUID
    provider_namespace: Slug
    source_family: Slug
    retrieved_at: UtcDatetime
    observed_at: UtcDatetime | None = None
    request_parameters: dict[str, JsonValue] = Field(default_factory=dict)
    source_native_id: NonEmptyStr | None = None
    source_locator: NonEmptyStr | None = None
    etag: NonEmptyStr | None = None
    last_modified: NonEmptyStr | None = None
    content_hash: ContentHash
    adapter_version: NonEmptyStr
    parser_version: NonEmptyStr | None = None
    retention_class: RetentionClass
    license_name: NonEmptyStr | None = None


def capture_raw_bytes(
    layout: DataLayout,
    content: bytes,
    *,
    provider_namespace: str,
    source_family: str,
    retrieved_at: datetime,
    adapter_version: str,
    retention_class: RetentionClass,
    observed_at: datetime | None = None,
    request_parameters: Mapping[str, JsonValue] | None = None,
    source_native_id: str | None = None,
    source_locator: str | None = None,
    etag: str | None = None,
    last_modified: str | None = None,
    parser_version: str | None = None,
    license_name: str | None = None,
) -> RawCaptureManifest:
    """Store exact bytes once and append an inspectable deterministic manifest."""
    digest = hashlib.sha256(content).hexdigest()
    parameters = dict(sorted((request_parameters or {}).items()))
    normalized_retrieved_at = normalize_utc(retrieved_at)
    normalized_observed_at = normalize_utc(observed_at) if observed_at is not None else None
    provisional = RawCaptureManifest(
        capture_id=UUID(int=0),
        provider_namespace=provider_namespace,
        source_family=source_family,
        retrieved_at=normalized_retrieved_at,
        observed_at=normalized_observed_at,
        request_parameters=parameters,
        source_native_id=source_native_id,
        source_locator=source_locator,
        etag=etag,
        last_modified=last_modified,
        content_hash=ContentHash(value=digest),
        adapter_version=adapter_version,
        parser_version=parser_version,
        retention_class=retention_class,
        license_name=license_name,
    )
    identity = provisional.model_dump(mode="json", exclude={"capture_id"})
    identity_json = json.dumps(
        identity, allow_nan=False, separators=(",", ":"), sort_keys=True
    )
    manifest = provisional.model_copy(
        update={"capture_id": uuid5(RAW_CAPTURE_NAMESPACE, identity_json)}
    )

    layout.create()
    object_path = raw_object_path(layout, digest)
    object_path.parent.mkdir(parents=True, exist_ok=True)
    if object_path.exists():
        existing = object_path.read_bytes()
        if hashlib.sha256(existing).hexdigest() != digest or existing != content:
            raise RawIntegrityError(f"raw object failed content verification: {digest}")
    else:
        _atomic_write(object_path, content)

    manifest_path = layout.raw_manifests / f"{manifest.capture_id}.json"
    manifest_bytes = _canonical_model_json(manifest)
    if manifest_path.exists():
        if manifest_path.read_bytes() != manifest_bytes:
            raise RawIntegrityError(f"capture manifest conflicts with {manifest.capture_id}")
    else:
        _atomic_write(manifest_path, manifest_bytes)
    return manifest


def raw_object_path(layout: DataLayout, content_sha256: str) -> Path:
    """Return the documented two-character-sharded content-object path."""
    return layout.raw_objects / content_sha256[:2] / content_sha256


def load_manifest(layout: DataLayout, capture_id: UUID) -> RawCaptureManifest:
    """Load and validate one capture manifest."""
    path = layout.raw_manifests / f"{capture_id}.json"
    return RawCaptureManifest.model_validate_json(path.read_bytes())


def _canonical_model_json(model: CanonicalModel) -> bytes:
    payload = json.loads(model.model_dump_json())
    return (
        json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode()


def _atomic_write(path: Path, content: bytes) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            raise RawIntegrityError(f"refusing to replace existing raw path: {path.name}")
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
