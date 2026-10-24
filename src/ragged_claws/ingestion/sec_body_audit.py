"""Pinned four-body diagnostic; existing SEC parser/adapter and calendar only, no outcomes."""

import argparse
import json
import platform
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ragged_claws.ingestion.sec import PARSER_VERSION, PROVIDER, SecForm4Adapter
from ragged_claws.ingestion.sec_audit import (
    AuditError,
    digest,
    encoded,
    overlap,
    potential_interval,
    read_object,
    timestamp,
)
from ragged_claws.ingestion.sec_models import SecFiling
from ragged_claws.ingestion.sec_parser import SecParseError, parse_filing
from ragged_claws.storage import DataLayout, deterministic_source_observation_id

DECLARATION_HASH = "c7a9025b8560d3119c95fae6068ccd0b909e3fb49e467018f416292f51825890"
DECLARATION_COMMIT = "1e5d80583cc8549530cb5f34609d2c602c73ec57"
FORMAT = "sec-four-body-capture/1.0.0"


def load_inputs(declaration: Path, context: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = declaration.read_bytes()
    if digest(raw) != DECLARATION_HASH:
        raise AuditError("unknown or changed four-body declaration")
    d: dict[str, Any] = json.loads(raw)
    review_raw = context.read_bytes()
    if digest(review_raw) != d["reference_context_sha256"]:
        raise AuditError("reference-review context hash mismatch")
    c: dict[str, Any] = json.loads(review_raw)
    if (
        d["format_version"] != "sec-four-body-declaration/1.0.0"
        or c["format_version"] != "sec-four-body-reference-context/1.0.0"
    ):
        raise AuditError("unsupported declaration/review format")
    return d, c


def checked_filing(raw: bytes, resource: dict[str, Any], retrieved: datetime) -> SecFiling:
    filing = parse_filing(
        raw,
        accession=resource["accession"],
        source_version_id=deterministic_source_observation_id(
            PROVIDER, resource["accession"], digest(raw)
        ),
        form_type=resource["form"],
        filed_as_of=date.fromisoformat(resource["filed_as_of"]),
        acceptance_timezone="America/New_York",
    )
    if (
        filing.acceptance_time
        and filing.acceptance_time.timestamp
        and filing.acceptance_time.timestamp > retrieved
    ):
        raise SecParseError("acceptance follows capture clock")
    return filing


def verify_receipt(d: dict[str, Any], m: dict[str, Any], root: Path) -> dict[str, bytes]:
    """State-specific immutable evidence checks; no v1 global pin or policy override."""
    if (
        m.get("format_version") != FORMAT
        or m.get("declaration_sha256") != DECLARATION_HASH
        or m.get("declaration_commit") != DECLARATION_COMMIT
        or encoded(m.get("declared_budget")) != encoded(d["budget"])
    ):
        raise AuditError("four-body receipt declaration/budget mismatch")
    records = m.get("resources")
    if not isinstance(records, list) or len(records) != 4:
        raise AuditError("require exact four resource states")
    if any(type(m.get(k)) is not int or m[k] < 0 for k in ("requests_attempted", "bytes_retained")):
        raise AuditError("invalid receipt totals")
    if "stop_reason" not in m:
        raise AuditError("missing stop context")
    responses: dict[str, bytes] = {}
    attempted = retained = 0
    stopped = False
    previous: datetime | None = None
    terminal = {
        "captured",
        "denied",
        "non200",
        "challenge",
        "transport_error",
        "oversize",
        "malformed",
        "privacy_blocked",
    }
    response_keys = ("sha256", "size_bytes", "retrieved_at", "http_status", "complete_body")
    for record, resource in zip(records, d["resources"], strict=True):
        if any(record.get(k) != v for k, v in resource.items()):
            raise AuditError("resource order/identity mismatch")
        state = record.get("state")
        if state == "unattempted":
            if any(k in record for k in (*response_keys, "attempted_at")):
                raise AuditError("unattempted resource claims response")
            stopped = True
            continue
        if stopped or state not in terminal | {"interrupted"}:
            raise AuditError("unknown state or attempt after sequence stop")
        start = timestamp(record.get("attempted_at"))
        if previous and (start - previous).total_seconds() < 1:
            raise AuditError("request interval below declared limit")
        previous = start
        attempted += 1
        if state == "interrupted":
            if any(k in record for k in response_keys):
                raise AuditError("interrupted checkpoint claims response")
            stopped = True
            continue
        if any(k not in record for k in response_keys):
            raise AuditError("missing completed-response evidence")
        if type(record.get("private_contact_reflected")) is not bool:
            raise AuditError("missing privacy capture review")
        if record["private_contact_reflected"] and state != "privacy_blocked":
            raise AuditError("private response cannot be treated as public capture")
        size, status = record["size_bytes"], record["http_status"]
        if type(size) is not int or not 0 <= size <= d["budget"]["maximum_resource_bytes"]:
            raise AuditError("invalid response size")
        if type(record["complete_body"]) is not bool:
            raise AuditError("invalid response completeness")
        if not (type(status) is int and 100 <= status <= 599) and not (
            state == "transport_error" and status is None
        ):
            raise AuditError("invalid HTTP status")
        retrieved = timestamp(record["retrieved_at"])
        if retrieved < start:
            raise AuditError("retrieval precedes attempt")
        if state in {"captured", "malformed", "challenge"} and status != 200:
            raise AuditError("body state requires HTTP200")
        if state in {"captured", "malformed"} and record["complete_body"] is not True:
            raise AuditError("parsed response is incomplete")
        if state == "denied" and status not in {401, 403, 429}:
            raise AuditError("invalid denial status")
        if state == "non200" and status in {None, 200}:
            raise AuditError("invalid non200 state")
        if state == "transport_error" and record["complete_body"]:
            raise AuditError("partial transport cannot be complete")
        raw = read_object(root, record, d["budget"]["maximum_resource_bytes"])
        responses[resource["url"]] = raw
        retained += size
        if state in {"captured", "malformed"}:
            try:
                checked_filing(raw, resource, retrieved)
            except SecParseError:
                if state == "captured":
                    raise AuditError("captured body contradicts declared reference") from None
            else:
                if state == "malformed":
                    raise AuditError("malformed receipt contradicts valid source body")
        stopped = state != "captured"
    if attempted != m["requests_attempted"] or retained != m["bytes_retained"]:
        raise AuditError("request/byte total mismatch")
    if retained > d["budget"]["maximum_total_bytes"]:
        raise AuditError("total byte budget exceeded")
    failed = any(r["state"] not in {"captured", "unattempted"} for r in records)
    if failed and m["stop_reason"] is None:
        raise AuditError("incomplete acquisition lacks stop reason")
    if m["stop_reason"] not in terminal | {None, "interrupted", "missing_sec_user_agent"}:
        raise AuditError("unknown stop reason")
    failures = [r["state"] for r in records if r["state"] not in {"captured", "unattempted"}]
    if failures and m["stop_reason"] != failures[-1]:
        raise AuditError("stop reason contradicts resource failure")
    if not failures and m["stop_reason"] not in {None, "missing_sec_user_agent"}:
        raise AuditError("stop reason lacks supporting resource state")
    if m["stop_reason"] == "missing_sec_user_agent" and attempted:
        raise AuditError("missing configuration claims request")
    return responses


def regenerate(declaration: Path, context: Path, captures: Path, output: Path) -> dict[str, Any]:
    d, review = load_inputs(declaration, context)
    receipt_bytes = (captures / "manifest.json").read_bytes()
    if len(receipt_bytes) > 1024**2:
        raise AuditError("receipt exceeds bound")
    m: dict[str, Any] = json.loads(receipt_bytes)
    raw = verify_receipt(d, m, captures)  # Verify all bodies before any canonical output.
    if output.exists() or output.resolve().is_relative_to(captures.resolve()):
        raise AuditError("require fresh output outside captures")
    output.mkdir(parents=True)
    adapter = SecForm4Adapter(DataLayout(output / "data"))
    filings: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for record in m["resources"]:
        item: dict[str, Any] = {
            "source_reference": record,
            "event_count": None,
            "parse_state": "unavailable",
        }
        if record["url"] in raw:
            adapter.capture(
                raw[record["url"]],
                accession=record["accession"],
                source_locator=record["url"],
                retrieved_at=timestamp(record["retrieved_at"]),
            )
        if record["state"] == "captured":
            bundle = adapter.ingest(
                raw[record["url"]],
                accession=record["accession"],
                source_locator=record["url"],
                retrieved_at=timestamp(record["retrieved_at"]),
                form_type="4",
                filed_as_of=date.fromisoformat(record["filed_as_of"]),
                acceptance_timezone="America/New_York",
            )
            item.update(
                parse_state="parsed",
                event_count=len(bundle.events),
                no_qualifying_events=not bundle.events,
                bundle=bundle.model_dump(mode="json"),
            )
            for event in bundle.events:
                attrs = {a.name: a.value for a in event.attributes}
                events.append(
                    {
                        "event": event.model_dump(mode="json"),
                        "event_id": str(event.event_id),
                        "issuer": str(event.issuer_entity_id),
                        "code": attrs["transaction_code"],
                        "filed_as_of": record["filed_as_of"],
                        "accession": record["accession"],
                        "capture_at": record["retrieved_at"],
                        "first_ever_public_at": None,
                        "first_ever_collector_receipt": None,
                        "historical_decision_availability": "unknown",
                        "actual_decision": None,
                        "actual_policy_entry": None,
                        "security_status": "unresolved",
                        "listing_status": "unresolved",
                        **potential_interval(event.actionable_at),
                    }
                )
        filings.append(item)
    if len({e["event_id"] for e in events}) != len(events):
        raise AuditError("duplicate canonical event identity")
    parsed = [f for f in filings if f["parse_state"] == "parsed"]
    result: dict[str, Any] = {
        "format_version": "sec-four-body-diagnostic/1.0.0",
        "declaration": d,
        "declaration_commit": DECLARATION_COMMIT,
        "declaration_sha256": DECLARATION_HASH,
        "reference_context": review,
        "receipt": m,
        "receipt_sha256": digest(receipt_bytes),
        "filings": filings,
        "events": events,
        "counts": {
            "form4_reference_groups": 490,
            "predeclared_candidates": 4,
            "unselected_uncollected_groups": 486,
            "body_states": dict(
                sorted(Counter(f["source_reference"]["state"] for f in filings).items())
            ),
            "parsed_filings": len(parsed),
            "parsed_no_events": sum(f["no_qualifying_events"] for f in parsed),
            "unique_observed_ps_events": len(events),
            "observed_events_by_code": {
                code: sum(e["code"] == code for e in events) for code in ("P", "S")
            },
            "distinct_observed_event_issuers": len({e["issuer"] for e in events}),
            "events_by_code_date_issuer": dict(
                sorted(
                    Counter(f"{e['code']}|{e['filed_as_of']}|{e['issuer']}" for e in events).items()
                )
            ),
            "reporting_owner_occurrences": sum(
                len(f["bundle"]["filing"]["owners"]) for f in parsed
            ),
            "unresolved_owner_occurrences": sum(
                len(f["bundle"]["unresolved_owner_ciks"]) for f in parsed
            ),
            "unresolved_security_events": len(events),
            "unresolved_listing_events": len(events),
            "row_exclusions": dict(
                sorted(
                    Counter(
                        r["exclusion_reason"]
                        for f in parsed
                        for r in f["bundle"]["filing"]["rows"]
                        if r["exclusion_reason"]
                    ).items()
                )
            ),
        },
        "potential_supports": overlap(events),
        "population_overlap": None,
        "second_index_population": None,
        "uncollected_group_events": None,
        "complete_declared_capture": m["stop_reason"] is None
        and all(r["state"] == "captured" for r in m["resources"]),
        "investment_validation": "not_evaluated",
        "funding_ready": False,
        "parser_version": PARSER_VERSION,
        "runtime": {"python": platform.python_version()},
        "code_sha256": {
            p.relative_to(Path(__file__).parents[1]).as_posix(): digest(p.read_bytes())
            for p in sorted(Path(__file__).parents[1].rglob("*.py"))
        },
        "lock_sha256": digest((Path(__file__).parents[3] / "uv.lock").read_bytes()),
        "limits": [
            "Biased lexical archival subset, not census or representative sample",
            "Uncaptured and unselected bodies have unknown events, never observed zeros",
            "Acceptance+5min and source-label intervals are assumptions, not actual policy entries",
            "No prices/outcomes, alias equality, affordability, independence, power or readiness",
        ],
    }
    (output / "report.json").write_bytes(encoded(result))
    details = "\n".join(
        f"| {f['source_reference']['accession']} | {f['source_reference']['state']} | "
        f"{f['event_count'] if f['event_count'] is not None else 'unknown'} |"
        for f in filings
    )
    (output / "report.md").write_text(
        "# Four-body outcome-blind diagnostic\n\n"
        + "```json\n"
        + json.dumps(result["counts"], indent=2)
        + "\n```\n\n"
        + "| Accession | Body state | Observed P/S events |\n| --- | --- | ---: |\n"
        + details
        + "\n\nHypothetical public-label supports only:\n\n```json\n"
        + json.dumps(result["potential_supports"], indent=2)
        + "\n```\n\n"
        + "No actual decision or policy entry; 486 unselected groups remain uncollected.\n\n"
        + "\n".join("- " + s for s in result["limits"])
        + "\n",
        encoding="utf8",
    )
    (output / "output-hashes.json").write_bytes(
        encoded(
            {
                p.relative_to(output).as_posix(): digest(p.read_bytes())
                for p in sorted(output.rglob("*"))
                if p.is_file()
            }
        )
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("declaration", "context", "captures", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = regenerate(args.declaration, args.context, args.captures, args.output)
    print(json.dumps(result["counts"], sort_keys=True))


if __name__ == "__main__":
    main()
