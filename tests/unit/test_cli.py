"""CLI smoke tests."""

from typer.testing import CliRunner

from ragged_claws import __version__
from ragged_claws.cli import app


def test_version_command_imports_and_reports_package_version() -> None:
    result = CliRunner().invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__
