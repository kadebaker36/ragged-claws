"""One-shot fixed four-resource acquisition; no discovery/config loading or live CLI."""

import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from ragged_claws.ingestion.sec_audit import AuditError, digest, encoded
from ragged_claws.ingestion.sec_body_audit import (
    DECLARATION_COMMIT,
    DECLARATION_HASH,
    FORMAT,
    checked_filing,
    load_inputs,
)
from ragged_claws.ingestion.sec_http import SecFilingClient, SecThrottle
from ragged_claws.ingestion.sec_parser import SecParseError


def acquire(
    declaration: Path,
    context: Path,
    output: Path,
    *,
    user_agent: str | None,
    client: httpx.Client | None = None,
    throttle: SecThrottle | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    d, _ = load_inputs(declaration, context)
    if output.exists():
        raise AuditError("fresh acquisition path required; no retry/resume")
    limiter = throttle or SecThrottle(interval=1)
    if limiter.interval < 1:
        raise AuditError("four-body request interval below one second")
    m: dict[str, Any] = {
        "format_version": FORMAT,
        "declaration_sha256": DECLARATION_HASH,
        "declaration_commit": DECLARATION_COMMIT,
        "declared_budget": d["budget"],
        "resources": [{**r, "state": "unattempted"} for r in d["resources"]],
        "requests_attempted": 0,
        "bytes_retained": 0,
        "stop_reason": None,
        "transport": "serial bounded httpx entity bytes, one attempt, no redirects",
    }
    output.mkdir(parents=True)
    (output / "objects").mkdir()

    def checkpoint() -> None:
        temp = output / "manifest.pending"
        temp.write_bytes(encoded(m))
        temp.replace(output / "manifest.json")

    if not user_agent:
        m["stop_reason"] = "missing_sec_user_agent"
        checkpoint()
        return m
    validator = SecFilingClient(user_agent=user_agent, client=client, max_attempts=1)
    checkpoint()
    try:
        for record in m["resources"]:
            if m["stop_reason"] is not None:
                break
            limiter.acquire()
            record.update(state="interrupted", attempted_at=now().isoformat())
            m["requests_attempted"] += 1
            checkpoint()
            content = bytearray()
            status = None
            state = "captured"
            limit = min(
                d["budget"]["maximum_resource_bytes"],
                d["budget"]["maximum_total_bytes"] - m["bytes_retained"],
            )
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
                        state = "denied" if status in {401, 403, 429} else "non200"
                    elif re.search(
                        rb"(?i)^\s*(?:<html|<!doctype html)|captcha|request rate threshold",
                        content[:2048],
                    ):
                        state = "challenge"
            except httpx.TransportError:
                state = "transport_error"
            raw = bytes(content)
            at = now()
            contact = user_agent.rsplit(" ", 1)[-1].lower().encode()
            reflected = contact in raw.lower() or user_agent.encode() in raw
            if reflected:
                state = "privacy_blocked"
            complete = len(raw) < limit and state != "transport_error"
            if state == "captured":
                try:
                    checked_filing(raw, record, at)
                except SecParseError as exc:
                    state = "malformed"
                    record["parse_reason"] = str(exc)
            sha = digest(raw)
            target = output / "objects" / sha
            if target.exists() and target.read_bytes() != raw:
                raise AuditError("raw object conflict")
            if not target.exists():
                target.write_bytes(raw)
            record.update(
                state=state,
                http_status=status,
                complete_body=complete,
                retrieved_at=at.isoformat(),
                sha256=sha,
                size_bytes=len(raw),
                private_contact_reflected=reflected,
            )
            m["bytes_retained"] += len(raw)
            if state != "captured":
                m["stop_reason"] = state
            checkpoint()
    finally:
        if any(r["state"] == "interrupted" for r in m["resources"]):
            m["stop_reason"] = "interrupted"
        checkpoint()
        validator.close()
    return m
