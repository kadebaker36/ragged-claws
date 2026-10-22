"""Outcome Parquet persistence remains strict and idempotent."""

from datetime import date
from pathlib import Path

import pytest

from ragged_claws.models import Outcome
from ragged_claws.storage import CanonicalConflictError, CanonicalParquetStore, DataLayout
from tests.model_helpers import PROVENANCE_ID
from tests.unit import test_outcome_engine as fixtures


def test_outcome_roundtrip_is_idempotent_and_conflicts_fail(tmp_path: Path) -> None:
    security_bars, benchmark_bars = fixtures._complete_bars()
    outcome = fixtures._engine().calculate(
        event=fixtures._event(),
        horizon_sessions=5,
        security=fixtures._security(),
        listing=fixtures._listing(),
        security_bars=security_bars,
        benchmark_bars=benchmark_bars,
        coverage_through=date(2024, 7, 11),
        provenance_id=PROVENANCE_ID,
    )
    store = CanonicalParquetStore(DataLayout(tmp_path / "data"))
    assert store.persist(Outcome, (outcome,))
    path = store.path_for(Outcome)
    original_bytes = path.read_bytes()
    assert not store.persist(Outcome, (outcome,))
    assert path.read_bytes() == original_bytes
    assert store.load(Outcome) == (outcome,)

    conflicting = outcome.model_copy(
        update={"methodology": outcome.methodology.model_copy(update={"calendar_version": "x"})}
    )
    with pytest.raises(CanonicalConflictError):
        store.persist(Outcome, (conflicting,))
    assert path.read_bytes() == original_bytes

    # Explicit benchmark fixtures are canonical identities, not an engine hard-coded UUID.
    assert (
        fixtures._benchmark_listing().security_id
        == fixtures._benchmark_security().security_id
    )
