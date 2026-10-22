"""SEC staging values; source fields are not a second canonical schema authority."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from ragged_claws.models import (
    Entity,
    Event,
    EventEvidence,
    ExternalIdentifier,
    Provenance,
    SourceObservation,
    TemporalValue,
)
from ragged_claws.models.base import CanonicalModel, NonEmptyStr
from ragged_claws.temporal import ActionabilityResult, AvailabilityPolicy


class ReportingOwner(CanonicalModel):
    cik: str
    name: NonEmptyStr
    director: bool | None = None
    officer: bool | None = None
    ten_percent_owner: bool | None = None
    other: bool | None = None
    officer_title: str | None = None
    other_text: str | None = None


class OwnershipRow(CanonicalModel):
    coordinate: str
    table: str
    kind: str
    code: str | None = None
    security_title: str | None = None
    transaction_date: date | None = None
    shares: Decimal | None = None
    price: Decimal | None = None
    acquired_disposed: str | None = None
    direct_indirect: str | None = None
    nature_of_ownership: str | None = None
    footnote_ids: tuple[str, ...] = ()
    exclusion_reason: str | None = None


class SecFiling(CanonicalModel):
    """One normalized source version, including excluded rows and unresolved timing."""

    source_version_id: UUID
    filing_group_id: UUID
    accession: str
    document_name: str
    document_sequence: str
    form_type: str
    exclusion_reason: str | None
    filed_as_of: date | None
    acceptance_raw: str | None
    acceptance_time: TemporalValue | None
    timing_reason: str | None
    issuer_cik: str
    issuer_name: str
    issuer_symbol: str | None
    owners: tuple[ReportingOwner, ...]
    rows: tuple[OwnershipRow, ...]
    footnotes: dict[str, str]


class SecBundle(CanonicalModel):
    filing: SecFiling
    observation: SourceObservation
    provenance: Provenance
    entities: tuple[Entity, ...]
    identifier_claims: tuple[ExternalIdentifier, ...]
    evidence: tuple[EventEvidence, ...]
    events: tuple[Event, ...]
    unresolved_owner_ciks: tuple[str, ...]
    availability_policy: AvailabilityPolicy
    actionability: ActionabilityResult | None

    @property
    def source_version_id(self) -> UUID:
        return self.filing.source_version_id
