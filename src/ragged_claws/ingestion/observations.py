"""Shared first-seen observation and immutable source-version acceptance rules."""

from ragged_claws.models import SourceObservation

_SOURCE_OBSERVATION_SEMANTIC_FIELDS = (
    "schema_version",
    "provider_namespace",
    "source_native_id",
    "lineage",
    "public_time",
    "raw_content_hash",
    "adapter_version",
    "parser_version",
    "retention_class",
    "license_name",
)


class SourceObservationConflictError(RuntimeError):
    """Raised when one deterministic observation ID has conflicting semantics."""


def accept_source_observation(
    existing: SourceObservation | None,
    candidate: SourceObservation,
) -> SourceObservation:
    """Reuse first-seen state only when source-version semantics still agree.

    Retrieval time, observation time, and source locator are capture context. A later
    manifest preserves their newer values while the first canonical observation remains
    unchanged. Every other source-version semantic field must agree.
    """
    if existing is None:
        return candidate
    if existing.source_observation_id != candidate.source_observation_id:
        raise SourceObservationConflictError("source observation IDs do not match")
    conflicts = [
        field_name
        for field_name in _SOURCE_OBSERVATION_SEMANTIC_FIELDS
        if getattr(existing, field_name) != getattr(candidate, field_name)
    ]
    if conflicts:
        rendered = ", ".join(conflicts)
        raise SourceObservationConflictError(
            f"source observation {existing.source_observation_id} conflicts in: {rendered}"
        )
    return existing
