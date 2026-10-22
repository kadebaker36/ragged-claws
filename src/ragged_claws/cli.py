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
