"""Failed price-reading phases cannot erase discovery inspection history."""

import importlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid5

import pytest

from ragged_claws.research.analysis_demo import prepare_demo
from ragged_claws.research.analysis_models import AnalysisPlan
from ragged_claws.research.models import Period, PriceInputs, Protocol, Snapshot
from ragged_claws.research.protocol import register, registration_path
from ragged_claws.research.snapshot import (
    NAMESPACE,
    Inputs,
    ResearchError,
    digest,
    encoded,
    freeze,
    model_hash,
    read_inputs,
)

PROPOSAL = Path(__file__).parents[2] / "research/hypotheses/sec-p-s-v2.json"


def invented_request(
    root: Path,
    *,
    mode: Literal["discovery", "validation"],
    phase: str,
) -> tuple[Path, Snapshot, Protocol]:
    prepare_demo(root / "prepared", PROPOSAL, "positive")
    frozen = root / "frozen"
    snapshot = freeze(root / "prepared", frozen)
    protocol = Protocol.model_validate_json((frozen / "protocol.json").read_bytes())
    config = snapshot.config.model_copy(
        update={
            "mode": mode,
            "period": protocol.discovery if mode == "discovery" else protocol.validation,
            "as_of": datetime(2024, 6, 28, 19, tzinfo=UTC)
            if phase == "coverage"
            else snapshot.config.as_of,
        }
    )
    # Intentionally invalid resealed requests over invented support, never a claimed
    # real dataset. No raw source bytes or preexisting user artifacts are changed.
    (frozen / "config.json").write_bytes(encoded(config))
    files = tuple(
        item.model_copy(update={"sha256": digest((frozen / item.path).read_bytes())})
        if item.path == "config.json"
        else item
        for item in snapshot.files
    )
    provisional = snapshot.model_copy(
        update={
            "snapshot_id": UUID(int=0),
            "config": config,
            "files": files,
            "protocol_sha256": "a" * 64 if phase == "protocol" else snapshot.protocol_sha256,
        }
    )
    snapshot = provisional.model_copy(
        update={"snapshot_id": uuid5(NAMESPACE, model_hash(provisional))}
    )
    (frozen / "snapshot.json").write_bytes(encoded(snapshot))
    return frozen, snapshot, protocol


@pytest.mark.parametrize(
    ("phase", "reason"),
    [
        ("protocol", "configuration/protocol mismatch"),
        ("graph", "synthetic support cannot enter"),
        ("contract", "price provider differs"),
        ("coverage", "not completed"),
    ],
)
def test_discovery_failure_preserves_parsed_prices_and_blocks_renamed_registration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    reason: str,
) -> None:
    frozen, snapshot, protocol = invented_request(tmp_path, mode="discovery", phase=phase)
    builder = importlib.import_module("ragged_claws.research.build")
    source = importlib.import_module("ragged_claws.research.snapshot")
    original_read = read_inputs
    parsed: list[PriceInputs] = []

    def observed_read(path: Path) -> Inputs:
        inputs = original_read(path)
        parsed.append(inputs.prices)
        return inputs

    monkeypatch.setattr(source, "read_inputs", observed_read)
    monkeypatch.setattr(builder, "read_inputs", observed_read)
    if phase in ("contract", "coverage"):
        # Isolate later failure phases without pretending invented source support is
        # valid real evidence. Only this prior verifier is replaced; actual parsing,
        # contract/coverage gates and journal/registration logic remain in use.
        # The protocol/graph cases above exercise the actual verifier unchanged.
        monkeypatch.setattr(builder, "verify_snapshot", lambda _: snapshot)
    plan = AnalysisPlan.model_validate_json((tmp_path / "analysis-plan.json").read_bytes())
    if phase == "contract":
        plan = plan.model_copy(update={"provider": "alpaca.market_data"})
    registry = tmp_path / "registry"
    with pytest.raises(ResearchError, match=reason):
        builder.build(
            frozen,
            tmp_path / "output",
            registry,
            analysis_plan=plan if phase == "contract" else None,
        )
    assert len(parsed) == 1 and len(parsed[0].packets) == 5
    days = [bar.session_date for packet in parsed[0].packets for bar in packet.batch.bars]
    assert days and min(days) == date(2024, 1, 3)
    started_path = next((registry / "attempts").glob("*.started.json"))
    finished_path = next((registry / "attempts").glob("*.finished.json"))
    before = started_path.read_bytes(), finished_path.read_bytes()
    finished = json.loads(before[1])
    assert finished["outcome_inspection"] is True and finished["success"] is False
    period = Period.model_validate_json(encoded(finished["inspection_period"]))
    assert period.start == protocol.discovery.start
    assert period.end == snapshot.config.coverage_through
    assert all(period.start <= day <= period.end for day in days)
    assert not (tmp_path / "output").exists()
    # Renaming or changing the version cannot recover an untouched overlapping window.
    for name, version in (
        ("invented-renamed", protocol.version),
        (protocol.hypothesis_id, "invented-amendment"),
    ):
        candidate = protocol.model_copy(
            update={
                "hypothesis_id": name,
                "version": version,
                "validation": Period(start=date(2024, 1, 1), end=date(2024, 12, 31)),
            }
        )
        with pytest.raises(ResearchError, match="previously or potentially inspected"):
            register(
                candidate,
                frozen / "origins.json",
                registry,
                approval_reference="fixture://INVENTED-NOT-A-REAL-APPROVAL",
                attest_uninspected=True,
            )
        assert not registration_path(registry, model_hash(candidate)).exists()
    assert (started_path.read_bytes(), finished_path.read_bytes()) == before


def test_genuine_validation_authorization_denial_reads_no_prices_and_is_uninspected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen, _, protocol = invented_request(tmp_path, mode="validation", phase="authorization")
    builder = importlib.import_module("ragged_claws.research.build")
    source = importlib.import_module("ragged_claws.research.snapshot")

    def forbidden_read(_path: Path) -> Inputs:
        pytest.fail("a pre-price authorization denial must not invoke the price parser")

    monkeypatch.setattr(source, "read_inputs", forbidden_read)
    monkeypatch.setattr(builder, "read_inputs", forbidden_read)
    registry = tmp_path / "registry"
    with pytest.raises(ResearchError, match="not been reviewed and registered"):
        builder.build(frozen, tmp_path / "output", registry)
    finished = json.loads(next((registry / "attempts").glob("*.finished.json")).read_bytes())
    assert finished["outcome_inspection"] is False and finished["success"] is False
    assert "inspection_period" not in finished and not (tmp_path / "output").exists()
    # A true no-read denial does not falsely consume an untouched window.
    candidate = protocol.model_copy(
        update={
            "hypothesis_id": "invented-after-no-read-denial",
            "validation": Period(start=date(2024, 1, 1), end=date(2024, 12, 31)),
        }
    )
    value = register(
        candidate,
        frozen / "origins.json",
        registry,
        approval_reference="fixture://INVENTED-NOT-A-REAL-APPROVAL",
        attest_uninspected=True,
    )
    assert value.protocol_sha256 == model_hash(candidate)
