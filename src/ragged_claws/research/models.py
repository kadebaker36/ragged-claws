"""Versioned research artifacts, separate from canonical domain/schema authority."""

from datetime import date
from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from ragged_claws.market_data import DailyBarRequest, MarketDataBatch
from ragged_claws.models import Event, FeatureValue, Outcome, PriceAdjustment
from ragged_claws.models.base import CanonicalModel, NonEmptyStr, Slug, UtcDatetime
from ragged_claws.models.evidence import Sha256Hex
from ragged_claws.temporal import AvailabilityPolicy

FeatureName = Literal["event_type", "reported_shares", "known_relationship_context"]
Mode = Literal["synthetic", "diagnostic", "discovery", "validation"]
Origin = Literal["synthetic", "recorded_public", "restricted_real", "unverified"]


class Period(CanonicalModel):
    start: date
    end: date

    @model_validator(mode="after")
    def valid_period(self) -> Self:
        if self.start > self.end:
            raise ValueError("period starts after its end")
        return self


class Protocol(CanonicalModel):
    protocol_format: Literal["1.0.0"] = "1.0.0"
    status: Literal["proposal"] = "proposal"
    hypothesis_id: Slug
    version: Slug
    population: NonEmptyStr
    event_types: tuple[Slug, ...]
    source_families: tuple[Slug, ...]
    features: tuple[FeatureName, ...]
    feature_definitions: dict[FeatureName, str]
    horizons: tuple[int, ...] = (20, 60, 90)
    benchmark: Literal["SPY"] = "SPY"
    discovery: Period
    validation: Period
    expected_direction: NonEmptyStr
    exclusions: NonEmptyStr
    decision_standard: NonEmptyStr
    dependence_and_inspection_policy: NonEmptyStr
    execution_and_costs: NonEmptyStr
    availability_policies: tuple[AvailabilityPolicy, ...]
    code_config_version: Literal["research-build/1.0.0"] = "research-build/1.0.0"

    @model_validator(mode="after")
    def valid_protocol(self) -> Self:
        if self.discovery.end >= self.validation.start:
            raise ValueError("discovery and validation overlap")
        if set(self.feature_definitions) != set(self.features):
            raise ValueError("feature definitions must exactly cover declared features")
        if not {20, 60, 90} <= set(self.horizons):
            raise ValueError("20/60/90-session benchmark results are mandatory")
        return self


class BuildConfig(CanonicalModel):
    config_version: Literal["1.0.0"] = "1.0.0"
    mode: Mode
    hypothesis_id: Slug
    protocol_version: Slug
    period: Period
    as_of: UtcDatetime
    coverage_through: date
    features: tuple[FeatureName, ...]
    horizons: tuple[int, ...] = (20, 60, 90)
    feed: Slug
    adjustment: PriceAdjustment
    benchmark_security_id: UUID | None = None
    benchmark_listing_id: UUID | None = None
    output_rights: Literal["public", "private_only"] = "public"
    restricted_raw_retention_permitted: bool = False
    restricted_derivatives_permitted: bool = False
    license_review_reference: str | None = None
    report_version: Literal["1.0.0"] = "1.0.0"

    @model_validator(mode="after")
    def valid_config(self) -> Self:
        if not {20, 60, 90} <= set(self.horizons) or set(self.horizons) - {5, 20, 60, 90, 120}:
            raise ValueError("unsupported or missing mandatory horizons")
        if len(set(self.horizons)) != len(self.horizons) or len(set(self.features)) != len(
            self.features
        ):
            raise ValueError("duplicate horizons/features")
        if (self.benchmark_security_id is None) != (self.benchmark_listing_id is None):
            raise ValueError("benchmark identity must resolve together")
        return self


class IdentityBinding(CanonicalModel):
    event_id: UUID
    security_id: UUID
    listing_id: UUID
    listing_history_ids: tuple[UUID, ...] = ()
    provenance_ids: tuple[UUID, ...] = Field(min_length=1)
    review_reference: NonEmptyStr


class EventControl(CanonicalModel):
    event_id: UUID
    exclusion_reason: str | None = None
    terminal_date: date | None = None
    terminal_observation_id: UUID | None = None
    review_reference: NonEmptyStr

    @model_validator(mode="after")
    def terminal_evidence(self) -> Self:
        if (self.terminal_date is None) != (self.terminal_observation_id is None):
            raise ValueError("terminal state requires explicit date and source evidence")
        return self


class Controls(CanonicalModel):
    bindings: tuple[IdentityBinding, ...] = ()
    events: tuple[EventControl, ...] = ()

    @model_validator(mode="after")
    def unique_controls(self) -> Self:
        if len({x.event_id for x in self.bindings}) != len(self.bindings) or len(
            {x.event_id for x in self.events}
        ) != len(self.events):
            raise ValueError("duplicate event controls/bindings")
        return self


class PricePacket(CanonicalModel):
    packet_id: UUID
    request: DailyBarRequest
    batch: MarketDataBatch


class PriceInputs(CanonicalModel):
    packets: tuple[PricePacket, ...] = ()


class OriginRecord(CanonicalModel):
    dataset: str
    record_id: str
    payload_sha256: Sha256Hex
    origin: Origin
    basis: NonEmptyStr


class OriginInventory(CanonicalModel):
    records: tuple[OriginRecord, ...]


class InputFile(CanonicalModel):
    path: str
    sha256: Sha256Hex


class Snapshot(CanonicalModel):
    format_version: Literal["1.0.0"] = "1.0.0"
    snapshot_id: UUID
    config: BuildConfig
    protocol_sha256: Sha256Hex
    source_code_sha256: Sha256Hex
    dependency_lock_sha256: Sha256Hex
    canonical_schema_version: str
    runtime_versions: dict[str, str]
    files: tuple[InputFile, ...]


class Registration(CanonicalModel):
    registration_id: UUID
    protocol_sha256: Sha256Hex
    source_code_sha256: Sha256Hex
    origin_inventory_sha256: Sha256Hex
    approved_at: UtcDatetime
    approval_reference: NonEmptyStr
    attested_uninspected: Literal[True]


class ResearchRow(CanonicalModel):
    row_id: UUID
    snapshot_id: UUID
    event: Event
    horizon_sessions: int
    selection: Literal["selected", "excluded", "unknown"]
    status: Literal[
        "complete",
        "right_censored",
        "unresolved_security",
        "missing_price",
        "terminal_delisted",
        "excluded",
        "rejected",
    ]
    reason: str | None
    timing_eligible: bool
    source_observation_ids: tuple[UUID, ...]
    event_evidence_ids: tuple[UUID, ...]
    primary_families: tuple[str, ...]
    normalized_vendor_observations: int
    features: tuple[FeatureValue, ...]
    unavailable_features: dict[str, str]
    listing_history_ids: tuple[UUID, ...]
    identity_provenance_ids: tuple[UUID, ...]
    outcome: Outcome | None

    @field_validator("features")
    @classmethod
    def restore_declared_feature_types(
        cls, features: tuple[FeatureValue, ...]
    ) -> tuple[FeatureValue, ...]:
        """The artifact's fixed feature contract disambiguates Decimal JSON strings."""
        restored = []
        for feature in features:
            if feature.name == "reported_shares":
                value = Decimal(feature.value) if isinstance(feature.value, str) else feature.value
                if not isinstance(value, Decimal) or not value.is_finite():
                    raise ValueError("reported_shares must be an exact Decimal")
                feature = feature.model_copy(update={"value": value})
            elif feature.name == "event_type":
                if not isinstance(feature.value, str):
                    raise ValueError("event_type must be a canonical code")
            elif feature.name == "known_relationship_context":
                if type(feature.value) is not int or feature.value < 1:
                    raise ValueError("known context is a positive count, never invented absence")
            else:
                raise ValueError("undeclared research feature")
            restored.append(feature)
        return tuple(restored)


class Distribution(CanonicalModel):
    n: int
    mean: Decimal | None = None
    median: Decimal | None = None
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    p10_nearest_rank: Decimal | None = None
    p90_nearest_rank: Decimal | None = None
    positive_fraction: Decimal | None = None


class HorizonReport(CanonicalModel):
    horizon_sessions: int
    denominator: int
    qualifying_denominator: int
    actionable_qualifying_denominator: int
    complete_coverage_fraction: Decimal | None
    counts: dict[str, int]
    reasons: dict[str, int]
    by_source: dict[str, dict[str, int]]
    security_return: Distribution
    spy_return: Distribution
    spy_excess: Distribution
    by_event_type_excess: dict[str, Distribution]


class ResearchReport(CanonicalModel):
    snapshot_id: UUID
    mode: Mode
    protocol_status: Literal["proposal_unregistered", "registered"]
    input_events: int
    qualifying_events: int
    unknown_selection_events: int
    distinct_known_issuers: int
    qualifying_distinct_issuers: int
    unknown_issuer_events: int
    issuer_event_counts: dict[str, int]
    primary_snapshot_event_counts: dict[str, int]
    distinct_explicit_economic_units: int
    unresolved_vendor_source_rows: int
    vendor_snapshot_versions: int
    possible_repeated_vendor_rows: int
    horizons: tuple[HorizonReport, ...]
    interpretation: str
