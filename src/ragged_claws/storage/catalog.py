"""Rebuildable DuckDB views over authoritative curated Parquet files."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb

from ragged_claws.storage.layout import DataLayout


def rebuild_catalog(layout: DataLayout, catalog_path: Path | None = None) -> Path:
    """Delete and recreate a DuckDB catalog containing external Parquet views only."""
    layout.create()
    target = catalog_path or layout.catalog
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    connection = duckdb.connect(str(target))
    try:
        for parquet_path in sorted(layout.curated.glob("*.parquet")):
            view_name = _quote_identifier(parquet_path.stem)
            parquet_literal = _quote_literal(parquet_path.resolve().as_posix())
            connection.execute(
                f"CREATE VIEW {view_name} AS SELECT * FROM read_parquet({parquet_literal})"
            )
    finally:
        connection.close()
    return target


def query_catalog(
    catalog_path: Path,
    query: str,
    parameters: Sequence[object] = (),
) -> list[tuple[Any, ...]]:
    """Run a read query with an explicitly closed connection."""
    connection = duckdb.connect(str(catalog_path), read_only=True)
    try:
        return connection.execute(query, parameters).fetchall()
    finally:
        connection.close()


def _quote_identifier(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def _quote_literal(value: str) -> str:
    return f"'{value.replace(chr(39), chr(39) * 2)}'"
