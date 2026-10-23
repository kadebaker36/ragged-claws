"""Explicit isolated non-production R2 smoke only; never part of the offline execution path."""

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ragged_claws.durable.models import CloudPolicy
from ragged_claws.durable.objects import isolated_live_objects
from ragged_claws.durable.sync import head, restore, run_pipeline
from ragged_claws.ingestion.synthetic import SyntheticAdapter
from ragged_claws.storage import DataLayout


@pytest.mark.skipif(
    os.environ.get("RAGGED_CLAWS_DURABLE_LIVE") != "1",
    reason="isolated non-production storage credentials/approval required",
)
def test_isolated_r2_recovery_smoke() -> None:
    objects = isolated_live_objects()
    assert head(objects) is None, "isolated smoke prefix must have no existing authoritative state"

    def operation(layout: DataLayout) -> None:
        SyntheticAdapter(layout).ingest(
            (
                Path(__file__).parents[2] / "tests/fixtures/synthetic/persistence_event_v1.json"
            ).read_bytes(),
            source_native_id="invented-record-001",
            retrieved_at=datetime.now(UTC),
            observed_at=datetime.now(UTC),
        )

    result = run_pipeline(
        objects,
        expected_parent=None,
        operation=operation,
        policy=CloudPolicy(
            scope="invented_engineering",
            invented_attestation=True,
            review_reference="operator-approved-isolated-smoke",
        ),
    )
    with restore(objects, result.generation.generation_id) as recovered:
        assert recovered.validated.record_counts["Event"] == 1
