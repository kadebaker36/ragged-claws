"""Command-line interface for Ragged Claws."""

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
