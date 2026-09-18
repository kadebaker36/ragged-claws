"""Generated-schema determinism and drift tests."""

from pathlib import Path

from ragged_claws.schema_generation import SCHEMA_MODELS, schema_drift, write_schemas


def test_checked_in_schemas_match_authoritative_models() -> None:
    assert schema_drift(Path("schemas")) == []


def test_schema_generation_is_deterministic_and_removes_stale_files(tmp_path: Path) -> None:
    write_schemas(tmp_path)
    first_pass = {path.name: path.read_bytes() for path in tmp_path.glob("*.schema.json")}
    (tmp_path / "stale.schema.json").write_text("{}", encoding="utf-8")

    write_schemas(tmp_path)
    second_pass = {path.name: path.read_bytes() for path in tmp_path.glob("*.schema.json")}

    assert first_pass == second_pass
    assert len(second_pass) == len(SCHEMA_MODELS)
