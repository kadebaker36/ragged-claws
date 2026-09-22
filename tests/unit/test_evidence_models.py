"""Evidence-lineage and strict-validation tests."""

import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from ragged_claws.models import EventEvidence, ObservationRole, Provenance, SourceObservation
from tests.model_helpers import EVENT_ID, EVIDENCE_ID, PROVENANCE_ID, provenance, source_observation


def test_multiple_observations_support_one_event_without_duplicate_events() -> None:
    sec = source_observation()
    quiver = source_observation(
        UUID("22222222-2222-4222-8222-222222222222"),
        provider_namespace="normalized_vendor",
        source_native_id="synthetic-record-1",
        source_family="vendor.political_disclosure",
        underlying_source_family="sec.edgar.form4",
        role=ObservationRole.VENDOR_NORMALIZED,
    )
    observations = (sec.source_observation_id, quiver.source_observation_id)
    derivation = provenance(*observations)
    evidence = EventEvidence(
        event_evidence_id=EVIDENCE_ID,
        event_id=EVENT_ID,
        source_observation_ids=observations,
        provenance_id=derivation.provenance_id,
    )

    restored = EventEvidence.model_validate_json(evidence.model_dump_json())

    assert restored.event_id == EVENT_ID
    assert restored.source_observation_ids == observations
    assert quiver.lineage.underlying_source_family == "sec.edgar.form4"


def test_source_observation_and_provenance_json_roundtrip() -> None:
    observation = source_observation()
    derivation = provenance(observation.source_observation_id)

    assert SourceObservation.model_validate_json(observation.model_dump_json()) == observation
    assert Provenance.model_validate_json(derivation.model_dump_json()) == derivation


def test_precise_observation_timestamps_normalize_to_utc_and_reject_naive_values() -> None:
    payload = source_observation().model_dump()
    payload["retrieved_at"] = datetime.fromisoformat("2024-05-06T16:00:00-04:00")
    payload["observed_at"] = datetime.fromisoformat("2024-05-06T17:00:00-04:00")

    observation = SourceObservation.model_validate(payload)

    assert observation.retrieved_at == datetime(2024, 5, 6, 20, tzinfo=UTC)
    assert observation.observed_at == datetime(2024, 5, 6, 21, tzinfo=UTC)
    assert '"retrieved_at":"2024-05-06T20:00:00Z"' in observation.model_dump_json()

    payload["retrieved_at"] = datetime(2024, 5, 6, 20)
    with pytest.raises(ValidationError):
        SourceObservation.model_validate(payload)


def test_duplicate_evidence_links_fail_loudly() -> None:
    observation_id = source_observation().source_observation_id

    with pytest.raises(ValidationError, match="must be unique"):
        EventEvidence(
            event_evidence_id=EVIDENCE_ID,
            event_id=EVENT_ID,
            source_observation_ids=(observation_id, observation_id),
            provenance_id=PROVENANCE_ID,
        )


def test_models_reject_extra_vendor_fields_and_non_uuid_canonical_ids() -> None:
    payload = source_observation().model_dump()
    payload["vendor_return"] = "0.42"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SourceObservation.model_validate(payload)

    payload = source_observation().model_dump()
    payload["source_observation_id"] = "name-derived-identifier"
    with pytest.raises(ValidationError):
        SourceObservation.model_validate(payload)


def test_unknown_enum_value_fails_loudly() -> None:
    payload = source_observation().model_dump(mode="json")
    lineage = payload["lineage"]
    assert isinstance(lineage, dict)
    lineage["observation_role"] = "invented_role"

    with pytest.raises(ValidationError, match="Input should be"):
        SourceObservation.model_validate_json(json.dumps(payload))
