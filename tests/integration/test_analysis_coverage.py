"""Resealing cannot bypass the builder's completed-session timing precondition."""

import importlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ragged_claws.research.analysis import evaluate
from ragged_claws.research.analysis_demo import prepare_demo
from ragged_claws.research.models import BuildConfig, PriceInputs
from ragged_claws.research.snapshot import (
    ResearchError,
    digest,
    encoded,
    freeze,
    inventory_for,
    read_inputs,
)

PROPOSAL = Path(__file__).parents[2] / "research/hypotheses/sec-p-s-v2.json"


def prepared_scope(root: Path, coverage: date, as_of: datetime) -> None:
    prepare_demo(root / "prepared", PROPOSAL, "positive")
    path = root / "prepared/config.json"
    config = BuildConfig.model_validate_json(path.read_bytes())
    path.write_bytes(
        encoded(config.model_copy(update={"coverage_through": coverage, "as_of": as_of}))
    )
    prices_path = root / "prepared/prices.json"
    prices = PriceInputs.model_validate_json(prices_path.read_bytes())
    prices = prices.model_copy(
        update={
            "packets": tuple(
                packet.model_copy(
                    update={
                        "batch": packet.batch.model_copy(
                            update={
                                "bars": tuple(
                                    bar for bar in packet.batch.bars if bar.session_date <= coverage
                                ),
                            }
                        )
                    }
                )
                for packet in prices.packets
            )
        }
    )
    prices_path.write_bytes(encoded(prices))
    (root / "prepared/origins.json").write_bytes(
        encoded(
            inventory_for(
                read_inputs(root / "prepared"),
                "synthetic",
                "Invented completed-cutoff test support only.",
            )
        )
    )


def hashes(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): digest(p.read_bytes())
        for p in root.rglob("*")
        if p.is_file()
    }


@pytest.mark.parametrize(
    ("coverage", "as_of", "reason"),
    [
        (date(2024, 6, 28), datetime(2024, 1, 3, 15, tzinfo=UTC), "not completed"),
        (date(2024, 6, 28), datetime(2024, 6, 28, 19, 59, 59, tzinfo=UTC), "not completed"),
        # July 3 has an early regular-session close at 17:00 UTC, not the ordinary close.
        (date(2024, 7, 3), datetime(2024, 7, 3, 16, 59, 59, tzinfo=UTC), "not completed"),
        (date(2024, 6, 29), datetime(2024, 6, 30, 23, tzinfo=UTC), "regular session"),
    ],
)
def test_resealed_uncompleted_or_non_session_cutoff_rejected_and_journaled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    coverage: date,
    as_of: datetime,
    reason: str,
) -> None:
    prepared_scope(tmp_path, coverage, as_of)
    snapshot = freeze(tmp_path / "prepared", tmp_path / "frozen")
    builder = importlib.import_module("ragged_claws.research.build")
    with pytest.raises(ResearchError, match=reason):
        builder.build(tmp_path / "frozen", tmp_path / "proper", tmp_path / "proper-journal")
    # Only construction bypasses the one gate. Every other hash and semantic check
    # must pass, and evaluate is unmodified when it receives these invalid results.
    with monkeypatch.context() as context:
        context.setattr(builder, "completed_coverage", lambda _: None)
        report = builder.build(
            tmp_path / "frozen", tmp_path / "resealed", tmp_path / "construction-journal"
        )
    expected_status = "complete" if reason == "not completed" else "rejected"
    assert all(h.counts[expected_status] == 6 for h in report.horizons)
    result = tmp_path / "resealed" / str(snapshot.snapshot_id)
    before = hashes(result), hashes(tmp_path / "frozen")
    with pytest.raises(ResearchError, match=reason):
        evaluate(
            tmp_path / "frozen",
            result,
            tmp_path / "analysis-plan.json",
            tmp_path / "analyses",
            tmp_path / "analysis-journal",
        )
    assert (hashes(result), hashes(tmp_path / "frozen")) == before
    assert not (tmp_path / "analyses").exists()
    attempts = tmp_path / "analysis-journal/attempts"
    assert len(list(attempts.glob("*.started.json"))) == 1
    assert len(list(attempts.glob("*.analysis.json"))) == 1
    finished = json.loads(next(attempts.glob("*.finished.json")).read_bytes())
    assert finished["success"] is False and finished["outcome_inspection"] is False


@pytest.mark.parametrize(
    ("coverage", "as_of", "complete_horizons"),
    [
        # Exact completed-close boundary is allowed; no extra day or same-day ban.
        (date(2024, 6, 28), datetime(2024, 6, 28, 20, tzinfo=UTC), (20, 60, 90)),
        (date(2024, 7, 3), datetime(2024, 7, 3, 17, tzinfo=UTC), (20, 60, 90)),
        (date(2024, 2, 9), datetime(2024, 2, 9, 21, tzinfo=UTC), (20,)),
        (date(2024, 1, 3), datetime(2024, 1, 3, 21, tzinfo=UTC), ()),
    ],
)
def test_completed_cutoff_preserves_complete_and_censored_outcomes(
    tmp_path: Path,
    coverage: date,
    as_of: datetime,
    complete_horizons: tuple[int, ...],
) -> None:
    from ragged_claws.research.build import build

    prepared_scope(tmp_path, coverage, as_of)
    snapshot = freeze(tmp_path / "prepared", tmp_path / "frozen")
    build(tmp_path / "frozen", tmp_path / "research", tmp_path / "build-journal")
    result = tmp_path / "research" / str(snapshot.snapshot_id)
    before = hashes(result), hashes(tmp_path / "frozen")
    value = evaluate(
        tmp_path / "frozen",
        result,
        tmp_path / "analysis-plan.json",
        tmp_path / "analyses",
        tmp_path / "analysis-journal",
    )
    assert len(value.rows) == 18
    for row in value.rows:
        if row.row.horizon_sessions in complete_horizons:
            assert row.row.status == "complete" and row.gross_excess is not None
        else:
            assert row.row.status == "right_censored" and row.gross_excess is None
            assert set(row.net_excess_by_bps.values()) == {None}
    assert value.conditional_verdict == ("positive" if 60 in complete_horizons else "insufficient")
    assert value.investment_validation == "not_evaluated"
    assert (hashes(result), hashes(tmp_path / "frozen")) == before
