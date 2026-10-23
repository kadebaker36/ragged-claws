"""Command-line interface for Ragged Claws."""

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from ragged_claws import __version__
from ragged_claws.research.snapshot import ResearchError
from ragged_claws.storage import PersistenceError

app = typer.Typer(
    add_completion=False,
    help="Ragged Claws research infrastructure.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)


def research_failure(exc: Exception, key: str) -> None:
    # Model/IO errors can embed private payloads; only our curated rejection text is public.
    reason = str(exc) if isinstance(exc, ResearchError) else "invalid research input or persistence"
    typer.echo(json.dumps({key: 1, "reason": reason}))
    raise typer.Exit(2) from exc


@app.callback()
def main() -> None:
    """Run Ragged Claws commands."""


@app.command()
def version() -> None:
    """Print the installed package version."""
    typer.echo(__version__)


@app.command("research-prepare-sec")
def research_prepare_sec(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    metadata: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    protocol: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option()],
) -> None:
    """Prepare the exact recorded public SEC fixture with unresolved identity/prices; offline."""
    from ragged_claws.research.examples import prepare_sec

    try:
        prepare_sec(output, source, metadata, protocol, as_of=datetime.now(UTC))
    except (ValueError, OSError, PersistenceError) as exc:
        research_failure(exc, "preparation_rejected")
    typer.echo("Recorded SEC diagnostic inputs prepared; no price access or validation performed.")


@app.command("durable-offline-demo")
def durable_offline_demo(output: Annotated[Path, typer.Option()]) -> None:
    """Public SEC recovery/failure rehearsal using local fake objects; no R2 or source requests."""
    from ragged_claws.durable.demo import recovery_demo
    from ragged_claws.durable.models import DurableError

    try:
        result = recovery_demo(output)
    except (ValueError, OSError, PersistenceError) as exc:
        reasons = exc.reasons if isinstance(exc, DurableError) else {"invalid_durable_input": 1}
        typer.echo(json.dumps({"rejected": 1, "reasons": reasons}))
        raise typer.Exit(2) from None
    typer.echo(
        json.dumps(
            {
                "boundary": result["boundary"],
                "generation": result["authoritative_generation"],
                "events": result["restored_event_count"],
                "report": str(output / "recovery.json"),
            }
        )
    )


@app.command("durable-local-inspect")
def durable_local_inspect(
    objects: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    generation: Annotated[str, typer.Option()],
) -> None:
    """Verify one pinned local-fake generation in an owned temporary layout."""
    from ragged_claws.durable.models import DurableError
    from ragged_claws.durable.objects import LocalObjects
    from ragged_claws.durable.sync import restore

    try:
        with restore(LocalObjects(objects), generation) as value:
            typer.echo(
                json.dumps(
                    {
                        "boundary": "LOCAL_FAKE_OBJECTS_NOT_REAL_R2",
                        "generation": value.generation.generation_id,
                        "parent": value.generation.parent_id,
                        "records": value.validated.record_counts,
                    }
                )
            )
    except (ValueError, OSError, PersistenceError) as exc:
        reasons = exc.reasons if isinstance(exc, DurableError) else {"invalid_durable_input": 1}
        typer.echo(json.dumps({"rejected": 1, "reasons": reasons}))
        raise typer.Exit(2) from None


@app.command("research-prepare-synthetic")
def research_prepare_synthetic(
    protocol: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option()],
) -> None:
    """Prepare invented engineering inputs and prices; no network or real research result."""
    from ragged_claws.research.examples import prepare_synthetic

    try:
        prepare_synthetic(output, protocol)
    except (ValueError, OSError, PersistenceError) as exc:
        research_failure(exc, "preparation_rejected")
    typer.echo("INVENTED engineering inputs prepared; not investment evidence.")


@app.command("research-freeze")
def research_freeze(
    prepared: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    output: Annotated[Path, typer.Option()],
) -> None:
    """Hash and freeze explicit local canonical inputs, protocol, prices and origin inventory."""
    from ragged_claws.research.snapshot import freeze

    try:
        result = freeze(prepared, output)
    except (ValueError, OSError, PersistenceError) as exc:
        research_failure(exc, "freeze_rejected")
        return
    typer.echo(str(result.snapshot_id))


@app.command("research-build")
def research_build(
    snapshot: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    output: Annotated[Path, typer.Option()],
    registry: Annotated[Path, typer.Option()],
    analysis_plan: Annotated[Path | None, typer.Option()] = None,
    analysis_approval: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Build version-scoped research Parquet/report; validation requires a matching registration."""
    from ragged_claws.research.analysis_models import AnalysisApproval, AnalysisPlan
    from ragged_claws.research.build import build

    try:
        report = build(
            snapshot,
            output,
            registry,
            analysis_plan=AnalysisPlan.model_validate_json(analysis_plan.read_bytes())
            if analysis_plan
            else None,
            analysis_approval=AnalysisApproval.model_validate_json(analysis_approval.read_bytes())
            if analysis_approval
            else None,
        )
    except (ValueError, OSError, PersistenceError) as exc:
        research_failure(exc, "rejected_build")
        return
    typer.echo(
        json.dumps(
            {
                "snapshot_id": str(report.snapshot_id),
                "mode": report.mode,
                "events": report.input_events,
                "protocol_status": report.protocol_status,
                "report": str(output / str(report.snapshot_id) / "report.json"),
            }
        )
    )


@app.command("research-evaluate")
def research_evaluate(
    snapshot: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    result: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    plan: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option()],
    registry: Annotated[Path, typer.Option()],
    approval: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Evaluate a sealed research result under an explicit proposal; no investment verdict."""
    from ragged_claws.research.analysis import evaluate

    try:
        value = evaluate(snapshot, result, plan, output, registry, approval)
    except (ValueError, OSError, PersistenceError) as exc:
        research_failure(exc, "analysis_rejected")
        return
    typer.echo(
        json.dumps(
            {
                "evaluation_id": str(value.evaluation_id),
                "conditional_verdict": value.conditional_verdict,
                "investment_validation": value.investment_validation,
            }
        )
    )


@app.command("analysis-offline-demo")
def analysis_offline_demo(
    output: Annotated[Path, typer.Option()],
    proposal: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
) -> None:
    """Build/evaluate four invented cases; 5000 issuer resamples, no network or approval."""
    from ragged_claws.research.analysis import evaluate
    from ragged_claws.research.analysis_demo import Case, prepare_demo
    from ragged_claws.research.build import build
    from ragged_claws.research.snapshot import freeze

    cases: tuple[Case, ...] = ("positive", "negative", "one_arm_missing", "no_complete")
    try:
        results = {}
        for case in cases:
            target = output / case
            prepare_demo(target / "prepared", proposal, case)
            snapshot = freeze(target / "prepared", target / "frozen")
            build(target / "frozen", target / "research", target / "registry")
            value = evaluate(
                target / "frozen",
                target / "research" / str(snapshot.snapshot_id),
                target / "analysis-plan.json",
                target / "analyses",
                target / "registry",
            )
            results[case] = {
                "conditional_verdict": value.conditional_verdict,
                "evaluation_id": str(value.evaluation_id),
                "investment_validation": value.investment_validation,
            }
    except (ValueError, OSError, PersistenceError) as exc:
        research_failure(exc, "analysis_demo_rejected")
        return
    typer.echo(json.dumps({"boundary": "INVENTED_ENGINEERING_ONLY", "cases": results}))


@app.command("research-register")
def research_register(
    protocol: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    origins: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    registry: Annotated[Path, typer.Option()],
    approval_reference: Annotated[str, typer.Option()],
    attest_uninspected: Annotated[bool, typer.Option()] = False,
) -> None:
    """Seal an accepted protocol only after explicit separate supervisor review; not automatic."""
    from ragged_claws.research.models import Protocol
    from ragged_claws.research.protocol import register

    try:
        value = register(
            Protocol.model_validate_json(protocol.read_bytes()),
            origins,
            registry,
            approval_reference=approval_reference,
            attest_uninspected=attest_uninspected,
        )
    except (ValueError, OSError, PersistenceError) as exc:
        research_failure(exc, "registration_rejected")
        return
    typer.echo(str(value.registration_id))


@app.command("ingest-quiver-fixture")
def ingest_quiver_fixture(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    endpoint: Annotated[str, typer.Option()],
    source_url: Annotated[str, typer.Option()],
    synthetic: Annotated[
        bool, typer.Option(help="Attest this file contains invented test data.")
    ] = False,
    data_dir: Annotated[Path, typer.Option()] = Path("data"),
) -> None:
    """Ingest invented Quiver-shaped fixtures only; no network or licensed vendor records."""
    from ragged_claws.ingestion.quiver import QuiverAdapter
    from ragged_claws.ingestion.quiver_parser import PATHS, QuiverError
    from ragged_claws.storage import DataLayout, PersistenceError

    try:
        if not synthetic or endpoint not in PATHS:
            raise QuiverError(
                "explicit invented-fixture attestation and supported endpoint required"
            )
        bundle = QuiverAdapter(DataLayout(data_dir)).ingest(
            source.read_bytes(),
            endpoint=endpoint,
            source_locator=source_url,
            retrieved_at=datetime.now(UTC),
            synthetic=True,
        )
    except (QuiverError, PersistenceError) as exc:
        typer.echo(json.dumps({"rejected_snapshots": 1, "reason": str(exc)}, sort_keys=True))
        raise typer.Exit(2) from exc
    events = {e.event_id: e for e in bundle.events}
    typer.echo(
        json.dumps(
            {
                "snapshot_id": str(bundle.source_version_id),
                "synthetic": True,
                "rows": len(bundle.rows),
                "counts": {
                    status: sum(m.status == status for m in bundle.mappings)
                    for status in ("linked", "unresolved", "excluded")
                },
                "unresolved_person_rows": sum(m.person_id is None for m in bundle.mappings),
                "unresolved_security_rows": sum(
                    m.event_id is None or events[m.event_id].security_id is None
                    for m in bundle.mappings
                ),
                "missing_reported_date_rows": sum(r.reported_time is None for r in bundle.rows),
                "ownership_unknown_rows": len(bundle.rows),
                "predictive_features_emitted": 0,
                "reasons": dict(Counter(m.reason for m in bundle.mappings if m.reason)),
            },
            sort_keys=True,
        )
    )


@app.command("ingest-littlesis")
def ingest_littlesis(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    source_url: Annotated[str, typer.Option()],
    data_dir: Annotated[Path, typer.Option()] = Path("data"),
) -> None:
    """Ingest one local API-v2 response as context; makes no network request."""
    from ragged_claws.ingestion.littlesis import LittleSisAdapter
    from ragged_claws.ingestion.littlesis_parser import LittleSisError
    from ragged_claws.storage import DataLayout, PersistenceError

    try:
        bundle = LittleSisAdapter(DataLayout(data_dir)).ingest(
            source.read_bytes(), source_locator=source_url, retrieved_at=datetime.now(UTC)
        )
    except (LittleSisError, PersistenceError) as exc:
        typer.echo(json.dumps({"rejected_snapshots": 1, "reason": str(exc)}, sort_keys=True))
        raise typer.Exit(2) from exc
    typer.echo(
        json.dumps(
            {
                "snapshot_id": str(bundle.source_version_id),
                "counts": {
                    status: sum(m.status == status for m in bundle.mappings)
                    for status in ("imported", "reused", "unresolved", "excluded")
                },
                "reasons": dict(Counter(m.reason for m in bundle.mappings if m.reason)),
                "snapshot_observed_at": bundle.observation.observed_at.isoformat(),
                "relationships": len(bundle.relationships),
                "pit_ineligible_relationships": sum(
                    r.known_from is None for r in bundle.relationships
                ),
                "attribution": bundle.attribution,
            },
            sort_keys=True,
        )
    )


@app.command("ingest-sec-form4")
def ingest_sec_form4(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    accession: Annotated[str, typer.Option()],
    source_url: Annotated[str, typer.Option()],
    data_dir: Annotated[Path, typer.Option()] = Path("data"),
    acceptance_timezone: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Ingest one local complete SEC submission; makes no network request."""
    from ragged_claws.ingestion.sec import SecForm4Adapter
    from ragged_claws.storage import DataLayout

    bundle = SecForm4Adapter(DataLayout(data_dir)).ingest(
        source.read_bytes(),
        accession=accession,
        retrieved_at=datetime.now(UTC),
        source_locator=source_url,
        acceptance_timezone=acceptance_timezone,
    )
    typer.echo(
        json.dumps(
            {
                "accession": bundle.filing.accession,
                "filing_group_id": str(bundle.filing.filing_group_id),
                "events": len(bundle.events),
                "reporting_owners": len(bundle.filing.owners),
                "unresolved_owner_ciks": bundle.unresolved_owner_ciks,
                "timing_reason": bundle.filing.timing_reason,
                "filing_exclusion_reason": bundle.filing.exclusion_reason,
                "excluded_rows": dict(
                    Counter(
                        row.exclusion_reason
                        for row in bundle.filing.rows
                        if row.exclusion_reason is not None
                    )
                ),
            },
            sort_keys=True,
        )
    )
