"""Explicit bounded audit acquisition; callable only, no live/default CLI or config discovery."""

import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from ragged_claws.ingestion.sec_audit import (
    AUDIT_VERSION,
    DECLARATION_COMMIT,
    INDEX_URLS,
    SCOPE_SHA256,
    AuditError,
    digest,
    encoded,
    load_scope,
    parse_index,
    select_four,
)
from ragged_claws.ingestion.sec_http import SecFilingClient, SecThrottle


def acquire(
    scope: Path,
    output: Path,
    *,
    user_agent: str,
    client: httpx.Client | None = None,
    throttle: SecThrottle | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    """One serial attempt/resource; stop globally, checkpoint every status. Never log contact."""
    declaration = load_scope(scope)
    if output.exists():
        raise AuditError("capture output must be fresh; no retries/resume")
    # Reuse the established contact/placeholder validation, without its retry/fetch path.
    validator = SecFilingClient(user_agent=user_agent, client=client, max_attempts=1)
    resources: list[dict[str, Any]] = [
        {"url": u, "kind": "index", "state": "unattempted"} for u in INDEX_URLS
    ]
    manifest: dict[str, Any] = {
        "format_version": AUDIT_VERSION,
        "scope_sha256": SCOPE_SHA256,
        "declaration_commit": DECLARATION_COMMIT,
        "representation": "exact_response_entity_bytes",
        "source": "SEC EDGAR public archives",
        "resources": resources,
        "stop_reason": None,
        "requests_attempted": 0,
        "bytes_retained": 0,
        "declared_budget": {
            k: declaration[k]
            for k in (
                "max_index_gets",
                "max_submission_gets",
                "max_index_bytes",
                "max_submission_bytes",
                "minimum_request_interval_seconds",
                "attempts_per_resource",
                "redirects",
            )
        },
    }
    output.mkdir(parents=True)
    (output / "objects").mkdir()
    limiter = throttle or SecThrottle(interval=1)
    if limiter.interval < 1:
        raise AuditError("audit interval must be at least one second")

    def checkpoint() -> None:
        target = output / "manifest.json"
        temp = output / "manifest.pending"
        temp.write_bytes(encoded(manifest))
        temp.replace(target)

    def fetch(record: dict[str, Any]) -> bytes | None:
        limit = declaration[
            "max_index_bytes" if record["kind"] == "index" else "max_submission_bytes"
        ]
        limiter.acquire()
        record.update(state="interrupted", attempted_at=now().isoformat())
        manifest["requests_attempted"] += 1
        checkpoint()  # An interrupted attempt is retained, never silently retried.
        content = bytearray()
        state = "captured"
        status = None
        try:
            with validator.client.stream(
                "GET",
                record["url"],
                headers={"User-Agent": user_agent, "Accept-Encoding": "identity"},
                follow_redirects=False,
            ) as response:
                status = response.status_code
                for chunk in response.iter_raw(chunk_size=8192):
                    content.extend(chunk[: limit - len(content)])
                    if len(content) >= limit:
                        state = "oversize"
                        break
                if status != 200:
                    state = "denied" if status in (401, 403, 429) else "non200"
                elif re.search(
                    rb"(?i)^\s*(?:<html|<!doctype html)|request rate threshold|captcha",
                    content[:2048],
                ):
                    state = "challenge"
        except httpx.TransportError:
            state = "transport_error"  # Exception text/headers may contain private context.
        raw = bytes(content)
        sha = digest(raw)
        target = output / "objects" / sha
        if target.exists() and target.read_bytes() != raw:
            raise AuditError("raw hash conflict")
        if not target.exists():
            target.write_bytes(raw)
        record.update(
            state=state,
            http_status=status,
            retrieved_at=now().isoformat(),
            sha256=sha,
            size_bytes=len(raw),
            complete_body=len(raw) < limit and state != "transport_error",
        )
        manifest["bytes_retained"] += len(raw)
        if state != "captured":
            manifest["stop_reason"] = state
        checkpoint()
        return raw if state == "captured" else None

    checkpoint()
    seen_accessions: set[str] = set()
    try:
        for record, day in zip(list(resources), declaration["index_dates"], strict=True):
            if manifest["stop_reason"] is not None:
                break
            content = fetch(record)
            if content is not None:
                try:
                    rows, _ = parse_index(content, day)
                    accessions = {r.accession for r in rows}
                    if seen_accessions & accessions:
                        raise AuditError("cross-index accession conflict")
                    seen_accessions.update(accessions)
                    for row in select_four(rows):
                        resources.append(
                            {
                                "url": row.url,
                                "kind": "submission",
                                "state": "unattempted",
                                "accession": row.accession,
                                "index_day": day,
                                "index_filename": row.filename,
                            }
                        )
                except AuditError as exc:
                    record["index_parse_error"] = str(exc)
                    manifest["stop_reason"] = "invalid_index"
                    checkpoint()
        for record in resources:
            if record["kind"] == "submission" and manifest["stop_reason"] is None:
                fetch(record)
    finally:
        if any(r["state"] == "interrupted" for r in resources):
            manifest["stop_reason"] = "interrupted"
        checkpoint()
        validator.close()
    return manifest


def missing_configuration(scope: Path, output: Path) -> None:
    """Offline missing-fact receipt; no contact discovery or network."""
    load_scope(scope)
    if output.exists():
        raise AuditError("capture output must be fresh")
    output.mkdir(parents=True)
    manifest = {
        "format_version": AUDIT_VERSION,
        "scope_sha256": SCOPE_SHA256,
        "declaration_commit": DECLARATION_COMMIT,
        "stop_reason": "missing_sec_user_agent",
        "requests_attempted": 0,
        "bytes_retained": 0,
        "resources": [{"url": u, "kind": "index", "state": "unattempted"} for u in INDEX_URLS],
    }
    (output / "manifest.json").write_bytes(encoded(manifest))
