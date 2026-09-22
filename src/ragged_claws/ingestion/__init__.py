"""Source ingestion implementations; M0 contains only a synthetic test adapter."""

from ragged_claws.ingestion.synthetic import (
    SourceObservationConflictError,
    SyntheticAdapter,
    SyntheticBundle,
    SyntheticIngestionResult,
    SyntheticStagingRecord,
)

__all__ = [
    "SourceObservationConflictError",
    "SyntheticAdapter",
    "SyntheticBundle",
    "SyntheticIngestionResult",
    "SyntheticStagingRecord",
]
