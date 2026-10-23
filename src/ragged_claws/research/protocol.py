"""Explicit protocol registration and append-only inspection journal; proposals are not seals."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4, uuid5

import exchange_calendars as xcals  # type: ignore[import-untyped]

from ragged_claws.research.models import BuildConfig, Period, Protocol, Registration, Snapshot
from ragged_claws.research.snapshot import (
    NAMESPACE,
    ResearchError,
    digest,
    encoded,
    environment,
    model_hash,
    write_once,
)


def check_configuration(protocol: Protocol, config: BuildConfig) -> None:
    if protocol.discovery.end + timedelta(days=1) >= protocol.validation.start:
        raise ResearchError(
            "discovery/validation embargo is shorter than the declared outcome horizon"
        )
    calendar = xcals.get_calendar(
        "XNYS",
        start=protocol.discovery.end - timedelta(days=7),
        end=protocol.validation.start + timedelta(days=7),
    )
    gap = calendar.sessions_in_range(
        protocol.discovery.end + timedelta(days=1), protocol.validation.start - timedelta(days=1)
    )
    if len(gap) < max(protocol.horizons) + 1:
        raise ResearchError(
            "discovery/validation embargo is shorter than the declared outcome horizon"
        )
    if (
        config.hypothesis_id,
        config.protocol_version,
        set(config.features),
        set(config.horizons),
    ) != (protocol.hypothesis_id, protocol.version, set(protocol.features), set(protocol.horizons)):
        raise ResearchError("undeclared hypothesis/version/features/horizons")
    if config.mode in ("discovery", "validation"):
        period = protocol.discovery if config.mode == "discovery" else protocol.validation
        if config.period != period:
            raise ResearchError("evaluation period differs from declared protocol")


def registration_path(registry: Path, protocol_hash: str) -> Path:
    return registry / "registrations" / f"{protocol_hash}.json"


def register(
    protocol: Protocol,
    origins: Path,
    registry: Path,
    *,
    approval_reference: str,
    attest_uninspected: bool,
) -> Registration:
    if not attest_uninspected or not approval_reference.strip():
        raise ResearchError(
            "explicit supervisor approval reference and uninspected attestation required"
        )
    path = registration_path(registry, model_hash(protocol))
    source, _, _ = environment()
    if path.exists():
        previous = Registration.model_validate_json(path.read_bytes())
        if (
            previous.source_code_sha256 != source
            or previous.origin_inventory_sha256 != digest(origins.read_bytes())
            or previous.approval_reference != approval_reference
        ):
            raise ResearchError("registered protocol is immutable; amendment needs fresh review")
        return previous
    for started in sorted((registry / "attempts").glob("*.started.json")):
        import json

        record = json.loads(started.read_bytes())
        if record["mode"] not in ("discovery", "validation"):
            continue
        finished = started.with_name(started.name.replace(".started.json", ".finished.json"))
        if finished.exists() and not json.loads(finished.read_bytes())["outcome_inspection"]:
            continue
        finished_record = json.loads(finished.read_bytes()) if finished.exists() else {}
        period_data = finished_record.get("inspection_period", record["period"])
        if not finished.exists():
            period_data["end"] = max(
                period_data["end"], record.get("potential_coverage_end", period_data["end"])
            )
        period = Period.model_validate_json(encoded(period_data))
        if period.start <= protocol.validation.end and protocol.validation.start <= period.end:
            raise ResearchError(
                "validation window previously or potentially inspected; cannot claim untouched"
            )
    value = Registration(
        registration_id=uuid5(NAMESPACE, model_hash(protocol)),
        protocol_sha256=model_hash(protocol),
        source_code_sha256=source,
        origin_inventory_sha256=digest(origins.read_bytes()),
        approved_at=datetime.now(UTC),
        approval_reference=approval_reference,
        attested_uninspected=True,
    )
    write_once(path, encoded(value))
    return value


def require_registration(
    snapshot: Snapshot, protocol: Protocol, root: Path, registry: Path
) -> Registration:
    path = registration_path(registry, snapshot.protocol_sha256)
    if not path.is_file():
        raise ResearchError("validation disabled: proposal has not been reviewed and registered")
    value = Registration.model_validate_json(path.read_bytes())
    if (
        value.protocol_sha256 != model_hash(protocol)
        or value.source_code_sha256 != snapshot.source_code_sha256
        or value.origin_inventory_sha256 != digest((root / "origins.json").read_bytes())
    ):
        raise ResearchError(
            "registered protocol/code/input-origin review does not match this validation"
        )
    return value


def start_attempt(registry: Path, snapshot: Snapshot) -> Path:
    identity = uuid4()
    path = registry / "attempts" / f"{identity}.started.json"
    write_once(
        path,
        encoded(
            {
                "attempt_id": str(identity),
                "snapshot_id": str(snapshot.snapshot_id),
                "hypothesis_id": snapshot.config.hypothesis_id,
                "protocol_sha256": snapshot.protocol_sha256,
                "mode": snapshot.config.mode,
                "period": snapshot.config.period.model_dump(mode="json"),
                "potential_coverage_end": snapshot.config.coverage_through.isoformat(),
                "started_at": datetime.now(UTC).isoformat(),
            }
        ),
    )
    return path


def finish_attempt(
    path: Path, *, inspected: bool, success: bool, inspection_period: Period | None = None
) -> None:
    write_once(
        path.with_name(path.name.replace(".started.json", ".finished.json")),
        encoded(
            {
                "outcome_inspection": inspected,
                "success": success,
                "finished_at": datetime.now(UTC).isoformat(),
                **(
                    {"inspection_period": inspection_period.model_dump(mode="json")}
                    if inspection_period is not None
                    else {}
                ),
            }
        ),
    )
