"""Local-first raw, Parquet, and rebuildable catalog storage."""

from ragged_claws.storage.catalog import query_catalog, rebuild_catalog
from ragged_claws.storage.ids import deterministic_source_observation_id
from ragged_claws.storage.layout import DataLayout
from ragged_claws.storage.parquet import (
    CanonicalConflictError,
    CanonicalParquetStore,
    PersistenceError,
    load_envelope_records,
    parquet_metadata,
    persist_envelope_records,
)
from ragged_claws.storage.raw import (
    RawCaptureManifest,
    RawIntegrityError,
    capture_raw_bytes,
    load_manifest,
    raw_object_path,
)

__all__ = [
    "CanonicalConflictError",
    "CanonicalParquetStore",
    "DataLayout",
    "PersistenceError",
    "RawCaptureManifest",
    "RawIntegrityError",
    "capture_raw_bytes",
    "deterministic_source_observation_id",
    "load_envelope_records",
    "load_manifest",
    "parquet_metadata",
    "persist_envelope_records",
    "query_catalog",
    "raw_object_path",
    "rebuild_catalog",
]
