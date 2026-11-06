"""Versioned watch artifacts; these are not canonical schema additions."""

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from ragged_claws.models import TemporalValue
from ragged_claws.models.base import CanonicalModel, UtcDatetime


class ActorReference(CanonicalModel):
    reference: str
    name: str | None = None
    entity_id: UUID | None = None
    entity_resolution_status: str = "source_reference_only"
    director: bool | None = None
    officer: bool | None = None
    ten_percent_owner: bool | None = None
    officer_title: str | None = None


class PurchaseCandidate(CanonicalModel):
    event_id: UUID
    issuer_entity_id: UUID | None
    issuer_name: str | None
    security_id: UUID | None
    listing_id: UUID | None
    actors: tuple[ActorReference, ...]
    occurrence_time: TemporalValue
    public_time: TemporalValue
    actionable_at: UtcDatetime
    first_observed_at: UtcDatetime
    shares: Decimal | None
    reported_price_per_share: Decimal | None
    exact_transaction_value: Decimal | None
    currency: str | None = None
    value_unknown_reason: str | None
    status: Literal["qualifying_common_stock", "unresolved"]
    identity_status: str
    listing_status: str
    unresolved_reasons: tuple[str, ...]
    source_observation_ids: tuple[UUID, ...]
    evidence_ids: tuple[UUID, ...]
    provenance_ids: tuple[UUID, ...]
    underlying_source_families: tuple[str, ...]
    filing_references: tuple[str, ...]
    attribution: str = "filing_reporting_owners_not_row_allocation"
    venue: str = "unknown_p_includes_open_market_or_private"


class PurchaseCluster(CanonicalModel):
    issuer_entity_id: UUID
    event_ids: tuple[UUID, ...]
    purchase_event_count: int
    distinct_reporting_actor_count: int
    actor_references: tuple[str, ...]
    first_actionable_at: UtcDatetime
    latest_actionable_at: UtcDatetime
    filing_count: int
    multiple_filings: bool


class DiscoveryCompleteness(CanonicalModel):
    index_day: date
    capture_id: UUID
    discovered_form4_count: int
    processed_filing_count: int
    remaining_unprocessed_count: int
    rejected_count: int
    successfully_ingested_count: int
    qualifying_p_event_count: int
    unresolved_p_event_count: int
    cursor: int
    index_processing_complete: bool
    market_coverage: Literal["unknown"] = "unknown"


class WatchReport(CanonicalModel):
    format_version: Literal["forward-purchase-watch/1.0.0"] = "forward-purchase-watch/1.0.0"
    as_of: UtcDatetime
    lookback_sessions: int
    window_start: UtcDatetime
    calendar: str = "XNYS"
    calendar_version: str
    candidates: tuple[PurchaseCandidate, ...]
    clusters: tuple[PurchaseCluster, ...]
    excluded_counts: dict[str, int]
    discovery: tuple[DiscoveryCompleteness, ...] = ()
    discovery_status: str = "not_supplied_market_coverage_unknown"
    interpretation: str = (
        "Source-backed evidence feed; no recommendation or investment validation. "
        "SEC acceptance plus five minutes remains an assumption, not measured dissemination. "
        "Broad market drawdowns are external market context. They do not change which actor "
        "behavior qualifies as a Ragged Claws signal."
    )
