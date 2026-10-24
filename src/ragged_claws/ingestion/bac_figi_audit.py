"""Pinned BAC candidate evidence only; no canonical identity application or network replay."""

import argparse
import hashlib
import json
import platform
import re
from collections import Counter
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any
from uuid import UUID

from ragged_claws.models import (
    ContentHash,
    ExternalIdentifierType,
    ObservationRole,
    RetentionClass,
    SourceLineage,
    SourceObservation,
)
from ragged_claws.research.snapshot import private_root
from ragged_claws.resolution import normalize_external_identifier, parse_openfigi_mapping_response
from ragged_claws.resolution.enrichment import OpenFigiResponseError
from ragged_claws.storage import (
    DataLayout,
    deterministic_source_observation_id,
    load_manifest,
    raw_object_path,
)

VERSION = "bac-figi-capture/1.0.0"
FORMAT = "bac-figi-receipt/1.0.0"
DECLARATION_HASH = "e307471485149f17e3f507e46eb62d23a495c3545498916a0a6af445b2b59344"
DECLARATION_COMMIT = "52fb96c8cc97ff0c721d0933d659db68d8f8b0ab"
FIELDS = (
    "figi",
    "shareClassFIGI",
    "compositeFIGI",
    "ticker",
    "name",
    "exchCode",
    "securityType",
    "securityType2",
    "marketSector",
    "securityDescription",
)
LEVELS = {
    "figi": ExternalIdentifierType.FIGI_INSTRUMENT,
    "shareClassFIGI": ExternalIdentifierType.FIGI_SHARE_CLASS,
    "compositeFIGI": ExternalIdentifierType.FIGI_COMPOSITE,
}


class FigiAuditError(RuntimeError):
    """Fixed nonsensitive evidence-boundary failure."""


def encoded(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def clock(value: Any) -> datetime:
    try:
        at = datetime.fromisoformat(value)
        if at.tzinfo is None:
            raise ValueError
        return at.astimezone(UTC)
    except (TypeError, ValueError):
        raise FigiAuditError("invalid aware evidence clock") from None


def declared_input(repo: Path, name: str, expected: str) -> bytes:
    """Recover only the exact pinned metadata bytes from its recognized Git LF form.

    Source-response objects are never normalized. Both hashes and the post-reconstruction
    hash are required; no semantic JSON equivalence or arbitrary newline variant suffices.
    """
    raw = (repo / name).read_bytes()
    if digest(raw) == expected:
        return raw
    if (
        name == "tests/fixtures/identity/sec-2024/evidence.json"
        and expected == "e3bc2c08aeaa36cbe557725cca22d1bfd98fa15236d048a23b7f764aca782742"
        and digest(raw) == "2f2db6e4f94d37164370aabf7948ed2bb7c9e5feee88c49a4e9b4f4590845f40"
    ):
        original = raw.replace(b"\n", b"\r\n")
        if digest(original) == expected:
            return original
    raise FigiAuditError("changed source input")


def _load_declaration(path: Path, repo: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if digest(raw) != DECLARATION_HASH:
        raise FigiAuditError("unknown declaration hash/version")
    d: dict[str, Any] = json.loads(raw)
    if (
        d["format_version"] != "bac-figi-acquisition/1.0.0"
        or d["implementation_version"] != VERSION
    ):
        raise FigiAuditError("unknown implementation version")
    for reference in (d["proposal"], d["coverage_card"]):
        if digest((repo / reference["path"]).read_bytes()) != reference["sha256"]:
            raise FigiAuditError("changed proposal/card")
    for name, sha in d["input_paths_sha256"].items():
        declared_input(repo, name, sha)
    p = json.loads((repo / d["proposal"]["path"]).read_bytes())
    c = json.loads((repo / d["coverage_card"]["path"]).read_bytes())
    if p["acquisition_authorized"] is not False or c["acquisition_authorized"] is not False:
        raise FigiAuditError("old proposal authorization changed")
    raw_source = (repo / "tests/fixtures/identity/sec-2024/0001104659-24-020016.txt").read_bytes()
    evidence_name = "tests/fixtures/identity/sec-2024/evidence.json"
    evidence = json.loads(
        declared_input(repo, evidence_name, d["input_paths_sha256"][evidence_name])
    )
    for span in evidence["resources"][0]["reviewed_claim_spans"]:
        if raw_source[span["start"] : span["end_exclusive"]].decode() != span["exact_text"]:
            raise FigiAuditError("source claim span contradiction")
    if evidence["reviewed_claims"]["13ga_subject_cik"] != "0000070858":
        raise FigiAuditError("source issuer contradiction")
    body = d["request"]["body_utf8_exact_no_newline"].encode("ascii")
    if len(body) != 76 or digest(body) != d["request"]["body_sha256"]:
        raise FigiAuditError("request body contradiction")
    return d


def load_declaration(path: Path, repo: Path) -> dict[str, Any]:
    try:
        return _load_declaration(path, repo)
    except (OSError, ValueError, KeyError, TypeError):
        raise FigiAuditError("missing or invalid pinned input") from None


def private_path(path: Path) -> None:
    try:
        private_root(path)
    except ValueError:
        raise FigiAuditError("private non-sync local path required") from None


def privacy_blocked(raw: bytes) -> bool:
    email = b"@" in raw and re.search(
        rb"(?i)[a-z0-9._%+-]{1,64}@[a-z0-9.-]{1,253}\.[a-z]{2,63}", raw
    )
    secret_key = re.search(
        rb'(?i)"(?:authorization|cookie|set-cookie|x-openfigi-apikey|api[_ -]?key)"\s*:', raw
    )
    return bool(email or secret_key)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def analyze(raw: bytes) -> tuple[str, dict[str, Any]]:
    """Validate the envelope before the existing sorting parser; retain source row order."""
    try:
        document = json.loads(raw.decode("utf8"), object_pairs_hook=_pairs)
    except (ValueError, UnicodeError, RecursionError):
        return "invalid_json", {}
    if not isinstance(document, list) or len(document) != 1 or not isinstance(document[0], dict):
        return "invalid_shape", {}
    job = document[0]
    if len(job) != 1 or next(iter(job), None) not in {"data", "warning", "error"}:
        return "invalid_shape", {}
    key = next(iter(job))
    if key != "data":
        if not isinstance(job[key], str) or not job[key].strip():
            return "invalid_shape", {}
        try:
            parse_openfigi_mapping_response(raw)
        except OpenFigiResponseError:
            return "provider_error", {"provider_state": "error", "raw_pointer": "/0/error"}
        return "no_result", {"provider_state": "warning", "raw_pointer": "/0/warning"}
    rows = job[key]
    if not isinstance(rows, list):
        return "invalid_shape", {}
    if any(
        not isinstance(row, dict)
        or set(row) - set(FIELDS)
        or any(v is not None and not isinstance(v, str) for v in row.values())
        for row in rows
    ):
        return "invalid_shape", {}
    try:
        parsed = parse_openfigi_mapping_response(raw)
        source_rows = []
        for i, row in enumerate(rows):
            normalized = {
                field: normalize_external_identifier(kind, row[field])
                for field, kind in LEVELS.items()
                if row.get(field) is not None
            }
            source_rows.append(
                {
                    "json_pointer": f"/0/data/{i}",
                    "provider_fields": row,
                    "missing_fields": [f for f in FIELDS if f not in row],
                    "null_fields": [f for f in FIELDS if f in row and row[f] is None],
                    "empty_fields": [
                        f for f in FIELDS if isinstance(row.get(f), str) and not row[f].strip()
                    ],
                    "normalized_identifiers": normalized,
                }
            )
    except (ValueError, TypeError):
        return "invalid_identifier", {}
    if len(parsed) != len(rows):
        return "invalid_shape", {}
    counts = {
        field: len(
            {
                r["normalized_identifiers"][field]
                for r in source_rows
                if field in r["normalized_identifiers"]
            }
        )
        for field in LEVELS
    }
    groups: dict[str, dict[str, list[str]]] = {"shareClassFIGI": {}, "compositeFIGI": {}}
    for row in source_rows:
        for field, by_identifier in groups.items():
            value = row["normalized_identifiers"].get(field)
            if value is not None:
                by_identifier.setdefault(value, []).append(row["json_pointer"])
    row_hashes = Counter(digest(encoded(row)) for row in rows)
    return ("captured" if rows else "no_result"), {
        "provider_state": "data" if rows else "empty_data",
        "source_rows": source_rows,
        "candidate_occurrences": len(rows),
        "distinct_identifiers_by_provider_field": counts,
        "duplicate_row_excess": sum(n - 1 for n in row_hashes.values()),
        "groups": groups,
        "partial_metadata": any(
            r["missing_fields"] or r["null_fields"] or r["empty_fields"] for r in source_rows
        ),
        "identity_resolution": "not attempted; candidates only, even for one identifier",
        "multiple_primary_identifiers": counts["figi"] > 1,
        "venue_identity": "unverified; figi parser label does not authenticate venue level",
        "parser_sorting": "parser sorts instrument_figi; source_rows retain source order",
    }


def response_state(raw: bytes, m: dict[str, Any], d: dict[str, Any]) -> str:
    if m["privacy_blocked"] or privacy_blocked(raw):
        return "privacy_blocked"
    if m["header_bytes"] > d["budget"]["maximum_response_header_bytes_total"]:
        if raw or m["complete_body"]:
            raise FigiAuditError("header stop claims body processing")
        return "header_oversize"
    if m["failure"] in {"timeout", "transport_error"}:
        return str(m["failure"])
    if len(raw) >= d["budget"]["maximum_response_entity_bytes_total"]:
        if m["complete_body"]:
            raise FigiAuditError("entity cap claims complete body")
        return "oversize"
    if not m["complete_body"]:
        raise FigiAuditError("incomplete response lacks failure evidence")
    if m["http_status"] in {401, 403, 429}:
        return "denied"
    if m["http_status"] != 200:
        return "non200"
    if re.search(rb"(?i)^\s*(?:<html|<!doctype html)|captcha", raw[:2048]):
        return "challenge"
    if not m["identity_encoding"]:
        return "unsupported_encoding"
    return analyze(raw)[0]


def receipt_file(root: Path) -> Path:
    for name in ("receipt.json", "checkpoint-interrupted.json", "checkpoint-unattempted.json"):
        if (root / name).exists():
            return root / name
    raise FigiAuditError("missing acquisition receipt/checkpoint")


def _verify_receipt(d: dict[str, Any], root: Path) -> tuple[dict[str, Any], bytes | None, Any]:
    receipt_path = receipt_file(root)
    if receipt_path.stat().st_size > d["budget"]["maximum_receipt_bytes"]:
        raise FigiAuditError("receipt exceeds bound")
    m: dict[str, Any] = json.loads(receipt_path.read_bytes())
    if (
        m.get("format_version") != FORMAT
        or m.get("declaration_sha256") != DECLARATION_HASH
        or m.get("declaration_commit") != DECLARATION_COMMIT
        or m.get("implementation_version") != VERSION
        or encoded(m.get("request")) != encoded(d["request"])
        or encoded(m.get("budget")) != encoded(d["budget"])
    ):
        raise FigiAuditError("receipt reference/version/budget mismatch")
    if m.get("state") in {"privacy_blocked"} or m.get("privacy_blocked") is True:
        raise FigiAuditError("private blocked receipt cannot be replayed")
    if m.get("stop_reason") != m.get("state"):
        raise FigiAuditError("stop reason contradicts state")
    state = m["state"]
    base_fields = {
        "format_version",
        "implementation_version",
        "declaration_sha256",
        "declaration_commit",
        "request",
        "budget",
        "requests_attempted",
        "bytes_retained",
        "state",
        "stop_reason",
    }
    additional = set() if state == "unattempted" else {"attempted_at"}
    if state not in {"unattempted", "interrupted"}:
        additional |= {
            "finished_at",
            "http_status",
            "complete_body",
            "header_bytes",
            "identity_encoding",
            "failure",
            "privacy_blocked",
            "raw_sha256",
            "capture_id",
            "manifest_sha256",
        }
    if set(m) != base_fields | additional:
        raise FigiAuditError("missing or unknown receipt fields")
    if any(type(m[k]) is not int or m[k] < 0 for k in ("requests_attempted", "bytes_retained")):
        raise FigiAuditError("invalid attempt/byte totals")
    if state in {"unattempted", "interrupted"}:
        if m.get("requests_attempted") != (state == "interrupted") or m.get("bytes_retained") != 0:
            raise FigiAuditError("checkpoint attempt/byte contradiction")
        if any(k in m for k in ("finished_at", "capture_id", "raw_sha256", "http_status")):
            raise FigiAuditError("checkpoint claims completed evidence")
        if state == "interrupted":
            clock(m.get("attempted_at"))
        elif "attempted_at" in m:
            raise FigiAuditError("unattempted checkpoint has attempt clock")
        return m, None, None
    if type(m.get("requests_attempted")) is not int or m["requests_attempted"] != 1:
        raise FigiAuditError("require exactly one attempted response")
    start, finish = clock(m.get("attempted_at")), clock(m.get("finished_at"))
    if finish < start:
        raise FigiAuditError("finish precedes attempt")
    for k in ("complete_body", "privacy_blocked", "identity_encoding"):
        if type(m.get(k)) is not bool:
            raise FigiAuditError("missing boolean response evidence")
    if type(m.get("header_bytes")) is not int or m["header_bytes"] < 0:
        raise FigiAuditError("invalid parsed header count")
    if m.get("failure") not in {None, "timeout", "transport_error"}:
        raise FigiAuditError("unknown transport failure")
    status = m.get("http_status")
    if not (type(status) is int and 100 <= status <= 599) and not (
        status is None and m["failure"] in {"timeout", "transport_error"}
    ):
        raise FigiAuditError("invalid response status")
    if m["failure"] is not None and m["complete_body"]:
        raise FigiAuditError("transport failure claims complete response")
    try:
        capture_id = UUID(m["capture_id"])
        layout = DataLayout(root / "data")
        manifest_path = layout.raw_manifests / f"{capture_id}.json"
        if (
            manifest_path.stat().st_size > 16384
            or digest(manifest_path.read_bytes()) != m["manifest_sha256"]
        ):
            raise FigiAuditError("raw manifest hash/size mismatch")
        manifest = load_manifest(layout, capture_id)
        sha = manifest.content_hash.value
        path = raw_object_path(layout, sha)
        if path.stat().st_size > d["budget"]["maximum_response_entity_bytes_total"]:
            raise FigiAuditError("raw object exceeds bound")
        raw = path.read_bytes()
    except (OSError, KeyError, ValueError):
        raise FigiAuditError("missing or invalid raw evidence") from None
    if (
        digest(raw) != sha
        or sha != m["raw_sha256"]
        or type(m.get("bytes_retained")) is not int
        or len(raw) != m["bytes_retained"]
        or manifest.retention_class != RetentionClass.RESTRICTED
        or manifest.retrieved_at != finish
        or manifest.source_locator != d["request"]["url"]
        or manifest.source_native_id != d["request"]["body_sha256"]
        or manifest.provider_namespace != "openfigi"
        or manifest.source_family != "openfigi.mapping"
        or manifest.adapter_version != VERSION
        or manifest.parser_version != "openfigi-mapping/1.0.0"
        or manifest.capture_id != capture_id
        or manifest.observed_at is not None
        or manifest.license_name != "openfigi-private-reviewed-candidate-evidence"
        or manifest.request_parameters
        != {
            "request_body_sha256": d["request"]["body_sha256"],
            "declaration_sha256": DECLARATION_HASH,
        }
    ):
        raise FigiAuditError("raw/reference/lineage contradiction")
    if response_state(raw, m, d) != state:
        raise FigiAuditError("response contradicts receipt state")
    if (
        sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
        > d["budget"]["maximum_retained_entity_plus_receipt_bytes"]
    ):
        raise FigiAuditError("retained acquisition evidence exceeds total bound")
    return m, raw, manifest


def verify_receipt(d: dict[str, Any], root: Path) -> tuple[dict[str, Any], bytes | None, Any]:
    try:
        return _verify_receipt(d, root)
    except (OSError, ValueError, KeyError, TypeError):
        raise FigiAuditError("missing or invalid receipt evidence") from None


def regenerate(declaration: Path, repo: Path, captures: Path, output: Path) -> dict[str, Any]:
    d = load_declaration(declaration, repo)
    private_path(captures)
    private_path(output)
    m, raw, manifest = verify_receipt(d, captures)
    if output.exists() or output.resolve().is_relative_to(captures.resolve()):
        raise FigiAuditError("fresh private output outside capture root required")
    observation = None
    if manifest is not None and m["http_status"] is not None:
        observation = SourceObservation(
            source_observation_id=deterministic_source_observation_id(
                "openfigi", d["request"]["body_sha256"], manifest.content_hash.value
            ),
            provider_namespace="openfigi",
            source_native_id=d["request"]["body_sha256"],
            lineage=SourceLineage(
                source_family="openfigi.mapping", observation_role=ObservationRole.ENRICHMENT
            ),
            retrieved_at=clock(m["finished_at"]),
            observed_at=clock(m["finished_at"]),
            raw_content_hash=ContentHash(value=manifest.content_hash.value),
            adapter_version=VERSION,
            parser_version="openfigi-mapping/1.0.0",
            source_locator=d["request"]["url"],
            retention_class=RetentionClass.RESTRICTED,
            license_name="openfigi-private-reviewed-candidate-evidence",
        ).model_dump(mode="json")
    details = (
        analyze(raw)[1]
        if raw is not None and m["state"] in {"captured", "no_result", "provider_error"}
        else {}
    )
    result = {
        "format_version": "bac-figi-candidate-diagnostic/1.0.0",
        "receipt": m,
        "receipt_phase": "checkpoint_only"
        if m["state"] in {"unattempted", "interrupted"}
        else "completed_response",
        "retained_capture_directory_bytes": sum(
            p.stat().st_size for p in captures.rglob("*") if p.is_file()
        ),
        "checkpoint_retention_note": (
            "Checkpoint byte count is its last known state, not proof of absent orphan raw. "
            "No completed response or candidates are inferred from orphan capture files."
        ),
        "receipt_sha256": digest(receipt_file(captures).read_bytes()),
        "declaration_sha256": DECLARATION_HASH,
        "declaration_commit": DECLARATION_COMMIT,
        "declaration": d,
        "source_observation": observation,
        "raw_capture_manifest": manifest.model_dump(mode="json") if manifest else None,
        "candidate_diagnostic": details,
        "canonical_identity_records_created": 0,
        "event_bindings_created": 0,
        "historical_valid_from": None,
        "historical_known_from": None,
        "authenticated_issuer_association": None,
        "venue_mic": None,
        "terminal_date": None,
        "BAC_events_separate": 3,
        "newer9_event_bindings": "unresolved",
        "SPY": "unresolved",
        "code_sha256": {
            p.relative_to(repo).as_posix(): digest(p.read_bytes())
            for p in sorted((repo / "src").rglob("*.py"))
        },
        "lock_sha256": digest((repo / "uv.lock").read_bytes()),
        "runtime": {
            "python": platform.python_version(),
            "httpx": version("httpx"),
            "pydantic": version("pydantic"),
        },
        "limits": (
            "Current provider assertions only; no historical interval, class/venue proof, "
            "CIK authentication, prices, outcomes, forward evidence or funding acceptance."
        ),
    }
    markdown = (
        "# Private BAC FIGI candidate diagnostic\n\nState: "
        + m["state"]
        + "\n\n```json\n"
        + json.dumps({k: v for k, v in details.items() if k != "source_rows"}, indent=2)
        + "\n```\n\n"
        + result["limits"]
        + "\n"
    ).encode()
    files = {"report.json": encoded(result), "report.md": markdown}
    inventory = encoded({name: digest(content) for name, content in files.items()})
    if sum(map(len, files.values())) + len(inventory) > d["maximum_derivative_report_bytes"]:
        result["candidate_diagnostic"] = {
            "status": "report_unavailable",
            "reason": "derivative_bound",
            "candidate_occurrences": None,
        }
        files = {
            "report.json": encoded(result),
            "report.md": (
                b"# Private diagnostic unavailable\n\nDerivative bound exceeded; "
                b"original raw retained. No cropped candidate claim.\n"
            ),
        }
        inventory = encoded({name: digest(content) for name, content in files.items()})
    if sum(map(len, files.values())) + len(inventory) > d["maximum_derivative_report_bytes"]:
        raise FigiAuditError("bounded unavailable diagnostic exceeds limit")
    output.mkdir(parents=True)
    for name, content in {**files, "output-hashes.json": inventory}.items():
        (output / name).write_bytes(content)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("declaration", "repo", "captures", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    regenerate(args.declaration, args.repo, args.captures, args.output)
    print("Private offline diagnostic written; candidate-only, no canonical application.")


if __name__ == "__main__":
    main()
