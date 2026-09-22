"""Reusable bitemporal eligibility decisions and FeatureSnapshot leakage guards."""

from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import model_validator

from ragged_claws.models.base import CanonicalModel
from ragged_claws.models.research import FeatureSnapshot, FeatureValue
from ragged_claws.models.temporal import TemporalPrecision, TemporalValue
from ragged_claws.temporal.normalization import normalize_utc


class PointInTimeViolation(ValueError):
    """Raised when a historical snapshot contains ineligible information."""


class EligibilityReason(StrEnum):
    ELIGIBLE = "eligible"
    MISSING_KNOWN_FROM = "missing_known_from"
    UNSUPPORTED_KNOWN_PRECISION = "unsupported_known_precision"
    KNOWN_AFTER_SNAPSHOT = "known_after_snapshot"
    KNOWN_INTERVAL_ENDED = "known_interval_ended"
    OUTSIDE_VALID_INTERVAL = "outside_valid_interval"


class EligibilityDecision(CanonicalModel):
    """Explain whether a datum may enter a historical predictive state."""

    eligible: bool
    reason: EligibilityReason

    @model_validator(mode="after")
    def validate_representation(self) -> "EligibilityDecision":
        if self.eligible != (self.reason is EligibilityReason.ELIGIBLE):
            raise ValueError("eligible flag does not match eligibility reason")
        return self


def evaluate_eligibility(
    *,
    snapshot_at: datetime,
    known_from: TemporalValue | None,
    known_to: TemporalValue | None = None,
    valid_at: datetime | None = None,
    valid_from: TemporalValue | None = None,
    valid_to: TemporalValue | None = None,
    observed_at: datetime | None = None,
) -> EligibilityDecision:
    """Apply knowledge and optional validity intervals without using observed time as public time.

    Intervals are half-open. Coarse starts become usable only after their whole period;
    coarse ends stop eligibility at the beginning of their stated period. ``observed_at``
    is accepted for an explicit audit trail but never substitutes for ``known_from``.
    """
    normalize_utc(snapshot_at)
    if observed_at is not None:
        normalize_utc(observed_at)

    if known_from is None:
        return EligibilityDecision(
            eligible=False,
            reason=EligibilityReason.MISSING_KNOWN_FROM,
        )

    known_start = _conservative_start(known_from)
    if known_start is None:
        return EligibilityDecision(
            eligible=False,
            reason=EligibilityReason.UNSUPPORTED_KNOWN_PRECISION,
        )
    if normalize_utc(snapshot_at) < known_start:
        return EligibilityDecision(
            eligible=False,
            reason=EligibilityReason.KNOWN_AFTER_SNAPSHOT,
        )

    if known_to is not None:
        known_end = _conservative_end(known_to)
        if known_end is None:
            return EligibilityDecision(
                eligible=False,
                reason=EligibilityReason.UNSUPPORTED_KNOWN_PRECISION,
            )
        if normalize_utc(snapshot_at) >= known_end:
            return EligibilityDecision(
                eligible=False,
                reason=EligibilityReason.KNOWN_INTERVAL_ENDED,
            )

    if valid_at is not None:
        normalized_valid_at = normalize_utc(valid_at)
        if valid_from is not None:
            valid_start = _conservative_start(valid_from)
            if valid_start is None or normalized_valid_at < valid_start:
                return EligibilityDecision(
                    eligible=False,
                    reason=EligibilityReason.OUTSIDE_VALID_INTERVAL,
                )
        if valid_to is not None:
            valid_end = _conservative_end(valid_to)
            if valid_end is None or normalized_valid_at >= valid_end:
                return EligibilityDecision(
                    eligible=False,
                    reason=EligibilityReason.OUTSIDE_VALID_INTERVAL,
                )

    return EligibilityDecision(eligible=True, reason=EligibilityReason.ELIGIBLE)


def eligible_features_at(
    features: tuple[FeatureValue, ...], snapshot_at: datetime
) -> tuple[FeatureValue, ...]:
    """Return only features whose public/known timing permits historical use."""
    return tuple(
        feature
        for feature in features
        if evaluate_eligibility(
            snapshot_at=snapshot_at,
            known_from=feature.known_from,
        ).eligible
    )


def validate_feature_snapshot(snapshot: FeatureSnapshot) -> FeatureSnapshot:
    """Reject a represented snapshot if any feature was not historically knowable."""
    eligible = eligible_features_at(snapshot.features, snapshot.snapshot_at)
    if len(eligible) != len(snapshot.features):
        rejected_ids = {feature.feature_value_id for feature in snapshot.features} - {
            feature.feature_value_id for feature in eligible
        }
        rendered_ids = ", ".join(str(value) for value in sorted(rejected_ids, key=str))
        raise PointInTimeViolation(
            f"feature snapshot contains historically ineligible features: {rendered_ids}"
        )
    return snapshot


def _conservative_start(value: TemporalValue) -> datetime | None:
    if value.timestamp is not None:
        return normalize_utc(value.timestamp)
    partial = value.partial_date
    if partial is None or value.precision is TemporalPrecision.UNKNOWN:
        return None
    if partial.year is None:
        return None
    if value.precision is TemporalPrecision.YEAR:
        return datetime(partial.year + 1, 1, 1, tzinfo=UTC)
    if partial.month is None:
        return None
    if value.precision is TemporalPrecision.MONTH:
        if partial.month == 12:
            return datetime(partial.year + 1, 1, 1, tzinfo=UTC)
        return datetime(partial.year, partial.month + 1, 1, tzinfo=UTC)
    if value.precision is TemporalPrecision.DAY and partial.day is not None:
        current = date(partial.year, partial.month, partial.day)
        next_day = current.fromordinal(current.toordinal() + 1)
        return datetime(next_day.year, next_day.month, next_day.day, tzinfo=UTC)
    return None


def _conservative_end(value: TemporalValue) -> datetime | None:
    if value.timestamp is not None:
        return normalize_utc(value.timestamp)
    partial = value.partial_date
    if partial is None or value.precision is TemporalPrecision.UNKNOWN:
        return None
    if partial.year is None:
        return None
    if value.precision is TemporalPrecision.YEAR:
        return datetime(partial.year, 1, 1, tzinfo=UTC)
    if partial.month is None:
        return None
    if value.precision is TemporalPrecision.MONTH:
        return datetime(partial.year, partial.month, 1, tzinfo=UTC)
    if value.precision is TemporalPrecision.DAY and partial.day is not None:
        return datetime(partial.year, partial.month, partial.day, tzinfo=UTC)
    return None
