"""Parquet-first persistence using an exact canonical-JSON M0 envelope."""

import json
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeVar

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from pydantic import BaseModel

from ragged_claws.models import (
    Event,
    EventEvidence,
    FeatureValue,
    Provenance,
    SourceObservation,
)
from ragged_claws.models.base import MODEL_SCHEMA_VERSION
from ragged_claws.storage.layout import DataLayout

STORAGE_FORMAT = "ragged_claws.canonical_json_envelope"
STORAGE_VERSION = "1.0.0"
CODEC = "pydantic_json"
CODEC_VERSION = "1.0.0"
DatasetKind = Literal["staging", "curated"]
ModelT = TypeVar("ModelT", bound=BaseModel)


class PersistenceError(RuntimeError):
    """Base error for invalid or conflicting persisted state."""


class CanonicalConflictError(PersistenceError):
    """Raised when one canonical ID is presented with two different payloads."""


@dataclass(frozen=True)
class DatasetSpec:
    filename: str
    id_field: str


_CURATED_SPECS: dict[type[BaseModel], DatasetSpec] = {
    SourceObservation: DatasetSpec("source_observation.parquet", "source_observation_id"),
    Provenance: DatasetSpec("provenance.parquet", "provenance_id"),
    EventEvidence: DatasetSpec("event_evidence.parquet", "event_evidence_id"),
    Event: DatasetSpec("event.parquet", "event_id"),
    FeatureValue: DatasetSpec("feature_value.parquet", "feature_value_id"),
}


class CanonicalParquetStore:
    """Persist supported canonical records with strict ID conflict semantics."""

    def __init__(self, layout: DataLayout) -> None:
        self.layout = layout
        self.layout.create()

    def path_for(self, model_type: type[BaseModel]) -> Path:
        return self.layout.curated / _curated_spec(model_type).filename

    def persist(self, model_type: type[ModelT], records: Iterable[ModelT]) -> bool:
        """Return whether authoritative state changed; identical IDs/payloads are no-ops."""
        spec = _curated_spec(model_type)
        return persist_envelope_records(
            self.path_for(model_type),
            model_type=model_type,
            id_field=spec.id_field,
            records=records,
            dataset_kind="curated",
            model_schema_version=MODEL_SCHEMA_VERSION,
        )

    def load(self, model_type: type[ModelT]) -> tuple[ModelT, ...]:
        spec = _curated_spec(model_type)
        return load_envelope_records(
            self.path_for(model_type),
            model_type=model_type,
            id_field=spec.id_field,
            dataset_kind="curated",
            model_schema_version=MODEL_SCHEMA_VERSION,
        )


def persist_envelope_records[EnvelopeModelT: BaseModel](
    path: Path,
    *,
    model_type: type[EnvelopeModelT],
    id_field: str,
    records: Iterable[EnvelopeModelT],
    dataset_kind: DatasetKind,
    model_schema_version: str,
) -> bool:
    """Persist exact model JSON in a deterministic, metadata-bearing Parquet envelope."""
    incoming: dict[str, str] = {}
    for record in records:
        if not isinstance(record, model_type):
            raise TypeError(f"expected {model_type.__name__}, got {type(record).__name__}")
        record_id = _record_id(record, id_field)
        payload = _canonical_json(record)
        previous = incoming.get(record_id)
        if previous is not None and previous != payload:
            raise CanonicalConflictError(
                f"{model_type.__name__} ID {record_id} has a different canonical payload"
            )
        incoming[record_id] = payload
    if not incoming:
        return False

    existing: dict[str, str] = {}
    if path.exists():
        _validate_metadata(
            path,
            model_type=model_type,
            dataset_kind=dataset_kind,
            model_schema_version=model_schema_version,
        )
        existing = {
            record_id: payload
            for record_id, (payload, _) in _read_validated_rows(
                path,
                model_type=model_type,
                id_field=id_field,
            ).items()
        }

    changed = False
    for record_id, payload in incoming.items():
        previous = existing.get(record_id)
        if previous is None:
            existing[record_id] = payload
            changed = True
        elif previous != payload:
            raise CanonicalConflictError(
                f"{model_type.__name__} ID {record_id} has a different canonical payload"
            )
    if not changed:
        return False

    _write_rows(
        path,
        existing,
        model_type=model_type,
        dataset_kind=dataset_kind,
        model_schema_version=model_schema_version,
    )
    return True


def load_envelope_records[EnvelopeModelT: BaseModel](
    path: Path,
    *,
    model_type: type[EnvelopeModelT],
    id_field: str,
    dataset_kind: DatasetKind,
    model_schema_version: str,
) -> tuple[EnvelopeModelT, ...]:
    """Reload every envelope payload through its authoritative Pydantic model."""
    if not path.exists():
        return ()
    _validate_metadata(
        path,
        model_type=model_type,
        dataset_kind=dataset_kind,
        model_schema_version=model_schema_version,
    )
    validated = _read_validated_rows(
        path,
        model_type=model_type,
        id_field=id_field,
    )
    return tuple(record for _, record in (validated[key] for key in sorted(validated)))


def parquet_metadata(path: Path) -> dict[str, str]:
    """Return decoded file metadata for inspection and tests."""
    raw = pq.read_metadata(path).metadata or {}
    return {key.decode(): value.decode() for key, value in raw.items()}


def _curated_spec(model_type: type[BaseModel]) -> DatasetSpec:
    try:
        return _CURATED_SPECS[model_type]
    except KeyError:
        raise ValueError(f"unsupported curated model: {model_type.__name__}") from None


def _record_id(record: BaseModel, id_field: str) -> str:
    value = getattr(record, id_field, None)
    if value is None:
        raise ValueError(f"{type(record).__name__} has no {id_field}")
    return str(value)


def _canonical_json(record: BaseModel) -> str:
    payload = json.loads(record.model_dump_json())
    return json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _read_rows(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for row in pq.read_table(path, columns=["record_id", "payload_json"]).to_pylist():
        record_id = str(row["record_id"])
        payload = str(row["payload_json"])
        if record_id in rows:
            raise PersistenceError(f"duplicate record ID in {path.name}: {record_id}")
        rows[record_id] = payload
    return rows


def _read_validated_rows[EnvelopeModelT: BaseModel](
    path: Path,
    *,
    model_type: type[EnvelopeModelT],
    id_field: str,
) -> dict[str, tuple[str, EnvelopeModelT]]:
    validated: dict[str, tuple[str, EnvelopeModelT]] = {}
    for record_id, payload in _read_rows(path).items():
        try:
            record = model_type.model_validate_json(payload)
            canonical_id = _record_id(record, id_field)
        except (TypeError, ValueError) as exc:
            raise PersistenceError(
                f"invalid {model_type.__name__} payload for envelope record {record_id}"
            ) from exc
        if canonical_id != record_id:
            raise PersistenceError(
                f"record ID column disagrees with {model_type.__name__} payload: {record_id}"
            )
        validated[record_id] = (payload, record)
    return validated


def _write_rows(
    path: Path,
    rows: dict[str, str],
    *,
    model_type: type[BaseModel],
    dataset_kind: DatasetKind,
    model_schema_version: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows.items())
    metadata = {
        b"storage_format": STORAGE_FORMAT.encode(),
        b"storage_version": STORAGE_VERSION.encode(),
        b"dataset_kind": dataset_kind.encode(),
        b"canonical_model": model_type.__name__.encode(),
        b"canonical_schema_version": model_schema_version.encode(),
        b"codec": CODEC.encode(),
        b"codec_version": CODEC_VERSION.encode(),
    }
    schema = pa.schema(
        [
            pa.field("record_id", pa.string(), nullable=False),
            pa.field("payload_json", pa.string(), nullable=False),
        ],
        metadata=metadata,
    )
    table = pa.Table.from_arrays(
        [
            pa.array([record_id for record_id, _ in ordered], type=pa.string()),
            pa.array([payload for _, payload in ordered], type=pa.string()),
        ],
        schema=schema,
    )
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
        pq.write_table(table, temporary, compression="zstd")
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _validate_metadata(
    path: Path,
    *,
    model_type: type[BaseModel],
    dataset_kind: DatasetKind,
    model_schema_version: str,
) -> None:
    expected = {
        "storage_format": STORAGE_FORMAT,
        "storage_version": STORAGE_VERSION,
        "dataset_kind": dataset_kind,
        "canonical_model": model_type.__name__,
        "canonical_schema_version": model_schema_version,
        "codec": CODEC,
        "codec_version": CODEC_VERSION,
    }
    actual = parquet_metadata(path)
    for key, value in expected.items():
        if actual.get(key) != value:
            raise PersistenceError(f"invalid {key} metadata in {path.name}")
