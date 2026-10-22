"""Source ingestion and shared observation acceptance contracts."""

from ragged_claws.ingestion.observations import SourceObservationConflictError
from ragged_claws.ingestion.synthetic import (
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
