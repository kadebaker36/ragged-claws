"""Pinned offline accession/reference review; never acquisition or canonical event mapping."""

import argparse
import json
import platform
from collections import Counter
from dataclasses import asdict, fields
from importlib.metadata import version
from pathlib import Path
from typing import Any

from ragged_claws.ingestion.sec_audit import (
    AUDIT_VERSION,
    HEADER,
    INDEX_URLS,
    AuditError,
    IndexConflict,
    IndexRow,
    digest,
    encoded,
    load_scope,
    parse_index,
    read_object,
    validate_capture,
)

RULE_HASH = "d76f8ff1e41aa0b4ecf261b2dd87e13c50f7f431c271f2688cb44f4702410765"
FORMAT = "sec-accession-reference-review/2.0.0"


def review_index(content: bytes, day: str) -> dict[str, Any]:
    """Reuse v1 structural parsing, while applying only the separately declared v2 grouping."""
    try:
        rows, _ = parse_index(content, day)
        v1_result = "accepted_by_v1"
    except IndexConflict as exc:
        # IndexConflict occurs only after every physical row passed structural validation.
        # Other parse errors still raise; this does not relax unsafe/malformed inputs.
        keys = [f.name for f in fields(IndexRow)]
        rows = [IndexRow(**{k: ref[k] for k in keys}) for ref in exc.context["references"]]
        v1_result = str(exc)
    lines = content.decode("utf-8-sig").splitlines()
    offset = lines.index(HEADER) + 2
    physical = [(n + 1, line) for n, line in enumerate(lines[offset:], offset) if line.strip()]
    if len(physical) != len(rows):
        raise AuditError("physical reference lineage mismatch")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row, (line_number, raw) in zip(rows, physical, strict=True):
        grouped.setdefault(row.accession, []).append(
            {**asdict(row), "source_file_line": line_number, "raw_line": raw}
        )
    groups: list[dict[str, Any]] = []
    for accession, refs in sorted(grouped.items()):
        forms = sorted({r["form"] for r in refs})
        dates = sorted({r["filed"] for r in refs})
        reasons = []
        if len(forms) != 1:
            reasons.append("conflicting_form_type")
        if len(dates) != 1:
            reasons.append("conflicting_official_filing_date")
        # Paths/accessions/CIK bindings and index day were already validated by v1.
        variants = Counter(r["raw_line"] for r in refs)
        address = min((int(r["index_cik"]), r["filename"]) for r in refs)
        groups.append(
            {
                "accession": accession,
                "status": "rejected_reference_conflict"
                if reasons
                else "compatible_reference_group",
                "reasons": reasons,
                "forms": forms,
                "official_filing_dates": dates,
                "physical_rows": len(refs),
                "distinct_literal_references": len(variants),
                "exact_duplicate_rows": len(refs) - len(variants),
                "index_ciks": sorted({r["index_cik"] for r in refs}, key=lambda x: (int(x), x)),
                "names": sorted({r["index_name"] for r in refs}),
                "paths": sorted({r["filename"] for r in refs}),
                "references": refs,
                "exact_reference_multiplicity": dict(sorted(variants.items())),
                "proposed_locator": None
                if reasons
                else "https://www.sec.gov/Archives/" + address[1],
                "alias_byte_equivalence": "not_established",
                "issuer_or_owner_role": "not_inferred_from_index",
            }
        )
    conflicts = [g for g in groups if g["reasons"]]
    compatible = [g for g in groups if not g["reasons"]]
    candidates = (
        []
        if conflicts
        else [
            {
                "accession": g["accession"],
                "proposed_locator": g["proposed_locator"],
                "official_filing_date": g["official_filing_dates"][0],
                "status": "proposed_future_capture_only",
                "acquisition_authorized": False,
            }
            for g in compatible
            if g["forms"] == ["4"]
        ][:4]
    )
    raw_lines = [line for _, line in physical]
    return {
        "index_day": day,
        "v1_parser_result": v1_result,
        "counts": {
            "physical_rows": len(rows),
            "exact_duplicate_rows": len(rows) - len(set(raw_lines)),
            "distinct_literal_references": len(set(raw_lines)),
            "accession_groups": len(groups),
            "physical_rows_by_form": dict(sorted(Counter(r.form for r in rows).items())),
            "compatible_groups_by_form": dict(
                sorted(Counter(g["forms"][0] for g in compatible).items())
            ),
            "compatible_groups": len(compatible),
            "rejected_groups": len(conflicts),
            "permitted_variant_groups": sum(
                g["distinct_literal_references"] > 1 for g in compatible
            ),
            "multi_cik_compatible_groups": sum(len(g["index_ciks"]) > 1 for g in compatible),
            "conflict_reasons": dict(
                sorted(Counter(reason for g in conflicts for reason in g["reasons"]).items())
            ),
        },
        "groups": groups,
        "candidate_status": "blocked_by_reference_conflicts" if conflicts else "proposal_only",
        "proposed_first_four": candidates,
        "economic_event_count": None,
    }


def regenerate(rule_path: Path, scope_path: Path, captures: Path, output: Path) -> dict[str, Any]:
    """Review exactly the retained receipt/raw under a pinned proposal. No network/config reads."""
    rule_bytes = rule_path.read_bytes()
    if digest(rule_bytes) != RULE_HASH:
        raise AuditError("unknown or changed reference rule")
    rule: dict[str, Any] = json.loads(rule_bytes)
    if rule["format_version"] != "sec-accession-reference-rule/2.0.0":
        raise AuditError("unknown rule format")
    scope = load_scope(scope_path)
    receipt_bytes = (captures / "manifest.json").read_bytes()
    if digest(receipt_bytes) != rule["original_receipt_sha256"]:
        raise AuditError("receipt is not pinned original acquisition")
    receipt: dict[str, Any] = json.loads(receipt_bytes)
    if receipt["format_version"] != AUDIT_VERSION:
        raise AuditError("unknown original receipt format")
    if receipt["scope_sha256"] != rule["original_scope_sha256"]:
        raise AuditError("original scope mismatch")
    records = receipt["resources"]
    validate_capture(records, receipt, scope)
    if [r["url"] for r in records] != list(INDEX_URLS):
        raise AuditError("unexpected original resources")
    first, second = records
    if first["state"] != "captured" or second["state"] != "unattempted":
        raise AuditError("not the retained partial acquisition")
    raw = read_object(captures, first, scope["max_index_bytes"])
    if digest(raw) != rule["original_raw_sha256"]:
        raise AuditError("not the retained index bytes")
    if output.exists() or output.resolve().is_relative_to(captures.resolve()):
        raise AuditError("require fresh output outside source inputs")
    review = review_index(raw, rule["review_index_day"])
    package = Path(__file__).parents[1]
    result: dict[str, Any] = {
        "format_version": FORMAT,
        "operation": "offline_reinterpretation_not_acquisition",
        "rule": rule,
        "rule_sha256": RULE_HASH,
        "original_scope_sha256": digest(scope_path.read_bytes()),
        "original_receipt_sha256": digest(receipt_bytes),
        "original_receipt": receipt,
        "original_raw_sha256": digest(raw),
        "original_raw_size": len(raw),
        "original_v1_declaration_commit": receipt["declaration_commit"],
        "original_retrieved_at": first["retrieved_at"],
        "review": review,
        "second_index": {"url": second["url"], "state": second["state"], "population": None},
        "body_population": None,
        "economic_event_population": None,
        "issuer_owner_security_listing_population": None,
        "public_receipt_decision_population": None,
        "price_outcome_population": None,
        "holding_overlap_population": None,
        "actual_decisions_or_entries": None,
        "new_acquisition": False,
        "investment_validation": "not_evaluated",
        "funding_ready": False,
        "code_sha256": {
            p.relative_to(package).as_posix(): digest(p.read_bytes())
            for p in sorted(package.rglob("*.py"))
        },
        "lock_sha256": digest((package.parent.parent / "uv.lock").read_bytes()),
        "runtime": {"python": platform.python_version(), "pydantic": version("pydantic")},
        "next_dependency": "Independent rule/candidate review; no capture restart",
    }
    output.mkdir(parents=True)
    (output / "review.json").write_bytes(encoded(result))
    (output / "review.md").write_text(render(result), encoding="utf-8")
    (output / "output-hashes.json").write_bytes(
        encoded(
            {name: digest((output / name).read_bytes()) for name in ("review.json", "review.md")}
        )
    )
    return result


def render(result: dict[str, Any]) -> str:
    review = result["review"]
    return "\n".join(
        [
            "# Offline accession/reference review",
            "",
            "Proposal only. Original v1 receipt and rejection remain unchanged; no v2 acquisition.",
            "",
            "```json",
            json.dumps(review["counts"], indent=2),
            "```",
            "",
            f"Candidate status: {review['candidate_status']}. Proposed future addresses only:",
            "",
            "```json",
            json.dumps(review["proposed_first_four"], indent=2),
            "```",
            "",
            "All physical rows, duplicate multiplicities and grouped lineage are in review.json.",
            "",
            "September11 is unattempted. Body/event/identity/timing/price/overlap are unknown.",
            "Accession grouping does not prove alias byte equality or issuer/owner role.",
            "Biased archival subset, not census or representative sample. No funding readiness.",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rule", "scope", "captures", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    result = regenerate(args.rule, args.scope, args.captures, args.output)
    print(json.dumps(result["review"]["counts"], sort_keys=True))


if __name__ == "__main__":
    main()
