# Local data

This directory is reserved for local research data and follows the planned layout:

```text
data/
├── raw/          # immutable source captures and manifests
├── staging/      # source-normalized datasets
├── curated/      # canonical persisted datasets
├── research/     # reproducible derived outputs
├── snapshots/    # frozen, versioned research states
└── cache/        # disposable, rebuildable files
```

All contents under `data/` except this README are ignored by Git. Do not commit secrets,
credentials, database files, bulk data, or restricted vendor payloads.

`ragged_claws.storage.DataLayout` creates these paths below a caller-selected root. Tests always use
pytest temporary directories rather than this repository directory. Raw content objects use
`raw/objects/<sha-prefix>/<sha256>` and capture metadata uses `raw/manifests/<capture-id>.json`.

Parquet under `curated/` is the authoritative canonical analytical state. The default DuckDB file
is disposable `cache/catalog.duckdb` and is rebuilt as views over curated Parquet. See
`docs/11-storage-and-idempotency.md` for identity, metadata, conflict, and rebuild rules.
