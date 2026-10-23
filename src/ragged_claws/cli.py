"""Command-line interface for Ragged Claws."""

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from ragged_claws import __version__

app = typer.Typer(
    add_completion=False,
    help="Ragged Claws research infrastructure.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Run Ragged Claws commands."""


@app.command()
def version() -> None:
    """Print the installed package version."""
    typer.echo(__version__)


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
