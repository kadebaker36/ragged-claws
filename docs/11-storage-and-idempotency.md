# Storage and Idempotency

Issue #4 implements the M0 local persistence vertical slice. It deliberately does not implement a
production source adapter, entity resolution, source correction reconciliation, market data, or
research computation.

## Authority and directories

There is one authoritative analytical state:

- `raw/` contains append-only source bytes and capture manifests;
- `staging/` contains source-normalized Parquet;
- `curated/` contains authoritative canonical Parquet;
- `research/` contains reproducible derived analytical output;
- `snapshots/` contains intentionally frozen/versioned research state;
- `cache/` is disposable and contains the rebuildable DuckDB catalog by default.

DuckDB never receives an independent canonical insert. Its catalog consists of views over curated
Parquet and may be deleted and rebuilt without loss.

## Raw objects and capture manifests

Exact source bytes are stored at `raw/objects/<first-two-sha256-characters>/<sha256>`. Existing
objects are read back and verified before reuse. Source bytes are never parsed and rewritten as a
storage convenience.

A separate JSON manifest under `raw/manifests/<capture-uuid>.json` records retrieval metadata,
including the provider/source family, UTC retrieval and optional distinct observation times,
canonical request parameters, source-native ID/locator, HTTP validators when supplied, content
SHA-256, adapter/parser versions, retention/license metadata, and manifest version. A later
retrieval can therefore add a manifest while reusing an identical content object. A changed payload
gets another content hash/object and cannot overwrite the earlier bytes.

Manifest identity is UUIDv5 over deterministic, sorted JSON metadata. Request-parameter keys are
sorted, and timestamps are normalized to UTC before identity calculation.

## SourceObservation identity

`deterministic_source_observation_id` is the sole M0 rule. It uses UUIDv5 namespace
`da099230-b255-5fc4-a40f-58ef2408a9a1`. The UUID name is the concatenation of these trimmed,
length-prefixed strings, encoded as UTF-8 by UUIDv5:

1. provider namespace;
2. stable source-native ID;
3. `sha256:<64 lowercase hexadecimal content hash>`.

Each component is encoded as `<character-count>:<value>`, with no mutable name, ticker, local path,
retrieval order, or retrieval timestamp. Identical source-native versions therefore retain one
canonical observation ID across later retrievals; changed bytes create a different version ID.

Capture history remains separate. When the synthetic pipeline sees an already-persisted observation
ID, it reuses the first persisted `SourceObservation` rather than replacing its original retrieval
or observation state with a later capture time. The later capture manifest remains available.

## Canonical Parquet envelope

M0 uses a deliberately small Parquet envelope rather than inventing parallel flattened schemas.
Each row contains a stable record ID and deterministic canonical Pydantic JSON. Reload always passes
the JSON through the current authoritative Pydantic model, preserving UUIDs, exact Decimal strings,
enums, tuples, nested models, UTC timestamps, partial dates, and evidence/provenance references.

Every Parquet file records deterministic metadata:

- storage format and version;
- dataset kind (`staging` or `curated`);
- model name;
- canonical/staging schema version;
- serialization codec and version.

The envelope is an M0 representation, not a claim that later analytical schemas are solved.

## Idempotency and safe writes

For both an existing dataset and one persistence batch:

- same record ID plus identical canonical payload is an idempotent no-op;
- same record ID plus a different canonical payload raises `CanonicalConflictError`;
- no overwrite, last-write-wins, field merge, or silent discard occurs.

Mutable staging/curated files are written to a temporary file in the destination directory and then
atomically replaced. Failed writes remove their temporary file and leave prior state intact.
Concurrent multi-process ingestion and file locking are deliberately deferred.

## DuckDB rebuild

`rebuild_catalog` deletes the selected DuckDB file and recreates external views for every curated
Parquet file. Connections are always explicitly closed, including query connections, so Windows
does not retain file locks. Deleting DuckDB does not delete or alter authoritative Parquet.

## Synthetic adapter limits

`SyntheticAdapter` exposes capture, normalization, observation, canonical mapping, persistence, and
reload as separate phases. Its committed fixtures contain invented IDs and values. The explicit
fixture UUIDs are test-only canonical choices; production canonical resolution is deferred.

The changed-version regression stops at raw objects and versioned `SourceObservation` records.
Where both versions would map materially different payloads to the same canonical event ID, M0's
strict conflict rule rejects the change rather than pretending source-specific correction semantics
exist.

All default tests use local synthetic fixtures and temporary directories. No network or live-source
smoke test is included.

## Quality commands

```text
uv sync --frozen
uv run python -m ragged_claws.schema_generation
uv run python -m ragged_claws.schema_generation --check
uv run pytest
uv run ruff check .
uv run mypy src tests
uv run ragged-claws version
```
