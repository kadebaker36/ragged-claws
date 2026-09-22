"""Source ingestion implementations; M0 contains only a synthetic test adapter."""

from ragged_claws.ingestion.synthetic import (
    SyntheticAdapter,
    SyntheticBundle,
    SyntheticIngestionResult,
    SyntheticStagingRecord,
)

__all__ = [
    "SyntheticAdapter",
    "SyntheticBundle",
    "SyntheticIngestionResult",
    "SyntheticStagingRecord",
]
