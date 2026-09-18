"""Generate deterministic JSON Schema artifacts from authoritative Pydantic models."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

from ragged_claws.models import (
    DisclosedRange,
    Entity,
    EntityAlias,
    Event,
    EventEvidence,
    ExternalIdentifier,
    FeatureSnapshot,
    FinancialValue,
    Listing,
    Outcome,
    PartialDate,
    Provenance,
    Relationship,
    Security,
    SourceObservation,
    TemporalValue,
)

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "disclosed_range.schema.json": DisclosedRange,
    "entity.schema.json": Entity,
    "entity_alias.schema.json": EntityAlias,
    "event.schema.json": Event,
    "event_evidence.schema.json": EventEvidence,
    "external_identifier.schema.json": ExternalIdentifier,
    "feature_snapshot.schema.json": FeatureSnapshot,
    "financial_value.schema.json": FinancialValue,
    "listing.schema.json": Listing,
    "outcome.schema.json": Outcome,
    "partial_date.schema.json": PartialDate,
    "provenance.schema.json": Provenance,
    "relationship.schema.json": Relationship,
    "security.schema.json": Security,
    "source_observation.schema.json": SourceObservation,
    "temporal_value.schema.json": TemporalValue,
}


def render_schemas() -> dict[str, str]:
    """Return stable filenames and deterministically formatted schema content."""
    return {
        filename: json.dumps(
            model.model_json_schema(mode="serialization"),
            indent=2,
            sort_keys=True,
        )
        + "\n"
        for filename, model in sorted(SCHEMA_MODELS.items())
    }


def write_schemas(output_dir: Path) -> None:
    """Write all generated schemas, removing stale generated schema files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = render_schemas()
    for stale_path in set(output_dir.glob("*.schema.json")) - {
        output_dir / filename for filename in expected
    }:
        stale_path.unlink()
    for filename, content in expected.items():
        (output_dir / filename).write_text(content, encoding="utf-8", newline="\n")


def schema_drift(output_dir: Path) -> list[str]:
    """Describe missing, stale, or changed generated schemas."""
    expected = render_schemas()
    problems: list[str] = []
    actual_names = {path.name for path in output_dir.glob("*.schema.json")}
    expected_names = set(expected)

    for filename in sorted(expected_names - actual_names):
        problems.append(f"missing schema: {filename}")
    for filename in sorted(actual_names - expected_names):
        problems.append(f"unexpected schema: {filename}")
    for filename in sorted(actual_names & expected_names):
        actual = (output_dir / filename).read_text(encoding="utf-8")
        if actual != expected[filename]:
            problems.append(f"outdated schema: {filename}")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    """Generate schemas, or return non-zero when checked-in artifacts have drifted."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("schemas"),
        help="schema output directory (default: ./schemas)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="check checked-in schemas without modifying them",
    )
    args = parser.parse_args(argv)
    output_dir: Path = args.output_dir

    if args.check:
        problems = schema_drift(output_dir)
        if problems:
            for problem in problems:
                print(problem)
            return 1
        print(f"{len(SCHEMA_MODELS)} generated schemas are current")
        return 0

    write_schemas(output_dir)
    print(f"generated {len(SCHEMA_MODELS)} schemas in {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
