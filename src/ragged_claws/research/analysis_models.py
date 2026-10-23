"""Analysis artifacts v1: deliberately separate from frozen research/domain formats."""

from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from ragged_claws.models import PriceAdjustment
from ragged_claws.models.base import CanonicalModel, NonEmptyStr
from ragged_claws.models.evidence import Sha256Hex
from ragged_claws.research.models import FeatureName, Period, ResearchReport, ResearchRow


class AnalysisPlan(CanonicalModel):
    format_version: Literal["analysis-plan/1.0.0"] = "analysis-plan/1.0.0"
    status: Literal["proposal"] = "proposal"
    purpose: Literal["proposed_validation", "invented_engineering"]
    plan_id: NonEmptyStr
    version: NonEmptyStr
    protocol_sha256: Sha256Hex
    hypothesis_id: NonEmptyStr
    protocol_version: NonEmptyStr
    period: Period
    features: tuple[FeatureName, ...]
    source_families: tuple[str, ...]
    provider: NonEmptyStr
    feed: NonEmptyStr
    adjustment: PriceAdjustment
    benchmark: Literal["SPY"] = "SPY"
    primary_horizon: Literal[60] = 60
    secondary_horizons: tuple[Literal[20, 90], ...] = (20, 90)
    stock_round_trip_bps: tuple[Literal[10, 25, 50], ...] = (10, 25, 50)
    benchmark_round_trip_bps: Literal[0] = 0
    resamples: Literal[5000] = 5000
    seed: Literal[1729] = 1729
    algorithm: Literal["issuer-pairs-sha256-counter/1"] = "issuer-pairs-sha256-counter/1"
    arithmetic: Literal["rational-exact-decimal50-half-even/1"] = (
        "rational-exact-decimal50-half-even/1"
    )
    percentiles: tuple[Decimal, Decimal] = (Decimal("0.025"), Decimal("0.975"))
    maximum_missing_arm_fraction: Decimal = Decimal("0.01")
    minimum_complete_per_arm: int = Field(default=1000, ge=1)
    minimum_issuers_per_arm: int = Field(default=200, ge=1)
    minimum_coverage_per_arm: Decimal = Decimal("0.9")
    minimum_contrast_lower_exclusive: Literal[0] = 0
    minimum_purchase_net25_exclusive: Literal[0] = 0
    rationale: NonEmptyStr

    @model_validator(mode="after")
    def fixed_mechanics(self) -> Self:
        if (
            self.secondary_horizons != (20, 90)
            or self.stock_round_trip_bps != (10, 25, 50)
            or self.percentiles != (Decimal("0.025"), Decimal("0.975"))
            or self.maximum_missing_arm_fraction != Decimal("0.01")
            or self.minimum_coverage_per_arm != Decimal("0.9")
            or len(set(self.features)) != len(self.features)
        ):
            raise ValueError("unsupported analysis mechanics; a new format needs review")
        if self.purpose == "proposed_validation" and (
            self.minimum_complete_per_arm != 1000 or self.minimum_issuers_per_arm != 200
        ):
            raise ValueError("production proposal requires 1000 complete events / 200 issuers")
        return self


class AnalysisApproval(CanonicalModel):
    """Operator-reviewed attestation, not a signature or authority for dev to self-approve."""

    format_version: Literal["analysis-approval/1.0.0"] = "analysis-approval/1.0.0"
    supervisor_reference: NonEmptyStr
    protocol_sha256: Sha256Hex
    plan_sha256: Sha256Hex
    source_code_sha256: Sha256Hex
    dependency_lock_sha256: Sha256Hex
    origin_inventory_sha256: Sha256Hex
    snapshot_sha256: Sha256Hex
    result_scope_snapshot_id: UUID
    registry_path: NonEmptyStr
    preserved_history: dict[str, Sha256Hex]
    preserved_history_review_reference: NonEmptyStr
    reconciled_unpublished_inspections: Literal[True]
    execution_context: Literal["persistent_operator_workspace"]
    calendar_dependence_review: NonEmptyStr
    multiplicity_review: NonEmptyStr
    availability_and_coverage_review: NonEmptyStr


class CostRow(CanonicalModel):
    row: ResearchRow  # Original denominators, status/reason and every dependency survive.
    gross_stock: Decimal | None
    gross_spy: Decimal | None
    gross_excess: Decimal | None
    net_stock_by_bps: dict[str, Decimal | None]
    net_excess_by_bps: dict[str, Decimal | None]


class ArmSummary(CanonicalModel):
    selected: int
    selected_actionable: int
    complete: int
    distinct_complete_issuers: int
    complete_coverage: Decimal | None
    issuer_event_counts: dict[str, int]
    largest_issuer_fraction: Decimal | None
    gross_stock_mean: Decimal | None
    gross_spy_mean: Decimal | None
    gross_excess_mean: Decimal | None
    net_excess_means_by_bps: dict[str, Decimal | None]


class Bootstrap(CanonicalModel):
    clusters: int
    draws: int
    valid_draws: int
    missing_arm_draws: int
    missing_arm_fraction: Decimal
    contrast: Decimal | None
    lower: Decimal | None
    upper: Decimal | None
    draw_indices_sha256: Sha256Hex


Verdict = Literal["positive", "negative", "insufficient", "not_evaluated"]


class HorizonAnalysis(CanonicalModel):
    horizon: int
    arms: dict[str, ArmSummary]
    bootstrap: Bootstrap | None
    conditional_verdict: Verdict
    reasons: tuple[str, ...]
    # The identical contrast/interval is shared across equal stock-cost scenarios.
    equal_cost_contrast_by_bps: dict[str, Decimal | None]


class Evaluation(CanonicalModel):
    format_version: Literal["analysis-result/1.0.0"] = "analysis-result/1.0.0"
    evaluation_id: UUID
    snapshot_id: UUID
    snapshot_sha256: Sha256Hex
    result_sha256: Sha256Hex
    protocol_sha256: Sha256Hex
    plan_sha256: Sha256Hex
    plan: AnalysisPlan
    source_code_sha256: Sha256Hex
    dependency_lock_sha256: Sha256Hex
    runtime_versions: dict[str, str]
    approval_sha256: Sha256Hex | None
    original_report: ResearchReport
    rows: tuple[CostRow, ...]
    horizons: tuple[HorizonAnalysis, ...]
    conditional_verdict: Verdict
    investment_validation: Literal["not_evaluated"] = "not_evaluated"
    investment_validation_reason: Literal[
        "Separate methodological acceptance and production failure-audit gate #15 remain required."
    ] = "Separate methodological acceptance and production failure-audit gate #15 remain required."
