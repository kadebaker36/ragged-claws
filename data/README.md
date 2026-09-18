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

This bootstrap does not implement storage or create these directories. Their persistence and
authority rules belong to later M0 issues.
