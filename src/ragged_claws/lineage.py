"""Canonical-only source support: normalized vendor coverage cannot add primary votes."""

from uuid import UUID

from ragged_claws.models import EventEvidence, ObservationRole, SourceObservation


def independent_primary_families(
    event_id: UUID, evidence: tuple[EventEvidence, ...], observations: tuple[SourceObservation, ...]
) -> tuple[str, ...]:
    indexed = {o.source_observation_id: o for o in observations}
    support = {
        identity
        for item in evidence
        if item.event_id == event_id
        for identity in item.source_observation_ids
    }
    if support - indexed.keys():
        raise ValueError("event evidence references missing observations")
    return tuple(
        sorted(
            {
                indexed[identity].lineage.source_family
                for identity in support
                if indexed[identity].lineage.observation_role is ObservationRole.PRIMARY_SOURCE
            }
        )
    )
