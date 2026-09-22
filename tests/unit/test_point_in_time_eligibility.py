"""Regression tests for bitemporal eligibility and historical feature leakage."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from ragged_claws.models import (
    AliasType,
    EntityAlias,
    ExternalIdentifier,
    ExternalIdentifierType,
    FeatureSnapshot,
    FeatureValue,
    IdentifierSubjectType,
    Relationship,
    SubjectReference,
    SubjectType,
    TemporalPrecision,
    TemporalValue,
)
from ragged_claws.temporal import (
    EligibilityDecision,
    EligibilityReason,
    PointInTimeViolation,
    eligible_features_at,
    evaluate_eligibility,
    validate_feature_snapshot,
)
from tests.model_helpers import (
    EVENT_ID,
    ISSUER_ID,
    OBSERVATION_ID,
    OBSERVED_AT,
    PERSON_ID,
    PROVENANCE_ID,
    partial_temporal,
)

SNAPSHOT_2020 = datetime(2020, 6, 1, tzinfo=UTC)


@pytest.mark.parametrize("reason", list(EligibilityReason))
def test_eligibility_decision_requires_flag_to_match_reason(
    reason: EligibilityReason,
) -> None:
    expected = reason is EligibilityReason.ELIGIBLE

    assert EligibilityDecision(eligible=expected, reason=reason).eligible is expected
    with pytest.raises(ValidationError, match="eligible flag"):
        EligibilityDecision(eligible=not expected, reason=reason)


def exact_time(value: str) -> TemporalValue:
    return TemporalValue(
        raw_value=value,
        precision=TemporalPrecision.SECOND,
        timestamp=datetime.fromisoformat(value),
    )


def relationship(known_from: TemporalValue | None) -> Relationship:
    return Relationship(
        relationship_id=UUID("60000000-0000-4000-8000-000000000010"),
        relationship_type="director_of",
        source=SubjectReference(subject_type=SubjectType.ENTITY, subject_id=PERSON_ID),
        target=SubjectReference(subject_type=SubjectType.ENTITY, subject_id=ISSUER_ID),
        valid_from=partial_temporal("2018-01-01", TemporalPrecision.DAY, year=2018, month=1, day=1),
        known_from=known_from,
        observed_at=datetime(2024, 6, 1, tzinfo=UTC),
        source_observation_ids=(OBSERVATION_ID,),
        provenance_id=PROVENANCE_ID,
    )


def test_old_valid_date_with_later_knowledge_cannot_leak_backward() -> None:
    record = relationship(exact_time("2024-01-01T00:00:00+00:00"))

    decision = evaluate_eligibility(
        snapshot_at=SNAPSHOT_2020,
        known_from=record.known_from,
        known_to=record.known_to,
        valid_at=SNAPSHOT_2020,
        valid_from=record.valid_from,
        valid_to=record.valid_to,
        observed_at=record.observed_at,
    )

    assert not decision.eligible
    assert decision.reason is EligibilityReason.KNOWN_AFTER_SNAPSHOT


def test_valid_and_known_before_snapshot_is_eligible() -> None:
    record = relationship(exact_time("2018-02-01T00:00:00+00:00"))

    decision = evaluate_eligibility(
        snapshot_at=SNAPSHOT_2020,
        known_from=record.known_from,
        valid_at=SNAPSHOT_2020,
        valid_from=record.valid_from,
        observed_at=record.observed_at,
    )

    assert decision.eligible
    assert decision.reason is EligibilityReason.ELIGIBLE


def test_observed_time_cannot_substitute_for_missing_known_time() -> None:
    record = relationship(None)

    decision = evaluate_eligibility(
        snapshot_at=SNAPSHOT_2020,
        known_from=record.known_from,
        observed_at=record.observed_at,
    )

    assert not decision.eligible
    assert decision.reason is EligibilityReason.MISSING_KNOWN_FROM


def test_known_interval_is_half_open() -> None:
    known_from = exact_time("2019-01-01T00:00:00+00:00")
    known_to = exact_time("2020-06-01T00:00:00+00:00")

    before_end = evaluate_eligibility(
        snapshot_at=datetime(2020, 5, 31, 23, 59, 59, tzinfo=UTC),
        known_from=known_from,
        known_to=known_to,
    )
    at_end = evaluate_eligibility(
        snapshot_at=SNAPSHOT_2020,
        known_from=known_from,
        known_to=known_to,
    )

    assert before_end.eligible
    assert at_end.reason is EligibilityReason.KNOWN_INTERVAL_ENDED


def test_valid_interval_is_evaluated_independently_from_knowledge_interval() -> None:
    decision = evaluate_eligibility(
        snapshot_at=SNAPSHOT_2020,
        known_from=exact_time("2018-01-01T00:00:00+00:00"),
        valid_at=SNAPSHOT_2020,
        valid_from=exact_time("2021-01-01T00:00:00+00:00"),
    )

    assert not decision.eligible
    assert decision.reason is EligibilityReason.OUTSIDE_VALID_INTERVAL


def test_later_known_alias_and_identifier_claims_are_excluded() -> None:
    known_later = exact_time("2024-01-01T00:00:00+00:00")
    alias = EntityAlias(
        entity_alias_id=UUID("50000000-0000-4000-8000-000000000010"),
        entity_id=ISSUER_ID,
        value="Later Alias",
        alias_type=AliasType.SOURCE_REPORTED,
        source_observation_id=OBSERVATION_ID,
        provenance_id=PROVENANCE_ID,
        known_from=known_later,
        observed_at=OBSERVED_AT,
    )
    identifier = ExternalIdentifier(
        external_identifier_id=UUID("40000000-0000-4000-8000-000000000020"),
        subject_type=IdentifierSubjectType.ENTITY,
        subject_id=ISSUER_ID,
        identifier_type=ExternalIdentifierType.SEC_CIK,
        value="0000000001",
        source_observation_id=OBSERVATION_ID,
        provenance_id=PROVENANCE_ID,
        known_from=known_later,
        observed_at=OBSERVED_AT,
    )

    alias_decision = evaluate_eligibility(
        snapshot_at=SNAPSHOT_2020,
        known_from=alias.known_from,
        observed_at=alias.observed_at,
    )
    identifier_decision = evaluate_eligibility(
        snapshot_at=SNAPSHOT_2020,
        known_from=identifier.known_from,
        observed_at=identifier.observed_at,
    )

    assert alias_decision.reason is EligibilityReason.KNOWN_AFTER_SNAPSHOT
    assert identifier_decision.reason is EligibilityReason.KNOWN_AFTER_SNAPSHOT


def test_feature_filter_excludes_later_unknown_and_post_event_metrics() -> None:
    historically_known = FeatureValue(
        feature_value_id=UUID("80000000-0000-4000-8000-000000000010"),
        name="transaction_size",
        value=Decimal("1000"),
        known_from=exact_time("2020-05-01T00:00:00+00:00"),
        source_observation_ids=(OBSERVATION_ID,),
    )
    later_known = FeatureValue(
        feature_value_id=UUID("80000000-0000-4000-8000-000000000011"),
        name="later_relationship_context",
        value=True,
        known_from=exact_time("2024-01-01T00:00:00+00:00"),
        source_observation_ids=(OBSERVATION_ID,),
    )
    unknown_knowledge = FeatureValue(
        feature_value_id=UUID("80000000-0000-4000-8000-000000000012"),
        name="current_graph_state",
        value=True,
        source_observation_ids=(OBSERVATION_ID,),
    )
    post_event_metric = FeatureValue(
        feature_value_id=UUID("80000000-0000-4000-8000-000000000013"),
        name="vendor_excess_return",
        value=Decimal("0.12"),
        known_from=exact_time("2020-07-01T00:00:00+00:00"),
        source_observation_ids=(OBSERVATION_ID,),
    )
    features = (historically_known, later_known, unknown_knowledge, post_event_metric)

    selected = eligible_features_at(features, SNAPSHOT_2020)

    assert selected == (historically_known,)

    snapshot = FeatureSnapshot(
        feature_snapshot_id=UUID("80000000-0000-4000-8000-000000000020"),
        event_id=EVENT_ID,
        snapshot_at=SNAPSHOT_2020,
        feature_version="features/1",
        features=features,
        provenance_id=PROVENANCE_ID,
    )
    with pytest.raises(PointInTimeViolation, match="historically ineligible"):
        validate_feature_snapshot(snapshot)


def test_coarse_known_from_uses_conservative_end_of_period() -> None:
    known_month = partial_temporal(
        "2020-05", TemporalPrecision.MONTH, year=2020, month=5
    )

    during_month = evaluate_eligibility(
        snapshot_at=datetime(2020, 5, 31, 23, 59, 59, tzinfo=UTC),
        known_from=known_month,
    )
    after_month = evaluate_eligibility(
        snapshot_at=datetime(2020, 6, 1, tzinfo=UTC),
        known_from=known_month,
    )

    assert during_month.reason is EligibilityReason.KNOWN_AFTER_SNAPSHOT
    assert after_month.eligible
