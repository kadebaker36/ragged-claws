"""Explicit one-shot anonymous POST; no environment/config or default live command."""

import ssl
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import certifi
import httpx

from ragged_claws.ingestion.bac_figi_audit import (
    DECLARATION_COMMIT,
    DECLARATION_HASH,
    FORMAT,
    VERSION,
    FigiAuditError,
    digest,
    encoded,
    load_declaration,
    privacy_blocked,
    private_path,
    response_state,
)
from ragged_claws.models import RetentionClass
from ragged_claws.storage import DataLayout, capture_raw_bytes


def acquire(
    declaration: Path,
    repo: Path,
    output: Path,
    *,
    transport: httpx.BaseTransport | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    d = load_declaration(declaration, repo)
    private_path(output)
    if output.exists():
        raise FigiAuditError("fresh private capture path required; no retry/resume")
    m: dict[str, Any] = {
        "format_version": FORMAT,
        "implementation_version": VERSION,
        "declaration_sha256": DECLARATION_HASH,
        "declaration_commit": DECLARATION_COMMIT,
        "request": d["request"],
        "budget": d["budget"],
        "requests_attempted": 0,
        "bytes_retained": 0,
        "state": "unattempted",
        "stop_reason": "unattempted",
    }
    output.mkdir(parents=True)

    def checkpoint(name: str) -> None:
        content = encoded(m)
        metadata_bytes = sum(p.stat().st_size for p in output.rglob("*.json") if p.is_file())
        if len(content) + metadata_bytes > d["budget"]["maximum_receipt_bytes"]:
            raise FigiAuditError("receipt evidence exceeds bound")
        target = output / name
        if target.exists():
            raise FigiAuditError("immutable receipt already exists")
        target.write_bytes(content)

    checkpoint("checkpoint-unattempted.json")
    # SSLContext avoids create_default_context's ambient SSLKEYLOGFILE discovery.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=certifi.where())
    wire = transport or httpx.HTTPTransport(verify=context, retries=0, trust_env=False)
    with httpx.Client(
        transport=wire,
        trust_env=False,
        auth=None,
        timeout=30,
        follow_redirects=False,
    ) as client:
        request = httpx.Request(
            "POST",
            d["request"]["url"],
            headers=d["request"]["headers"],
            content=d["request"]["body_utf8_exact_no_newline"].encode("ascii"),
        )
        expected = {k.lower(): v for k, v in d["request"]["headers"].items()}
        expected.update(host="api.openfigi.com", **{"content-length": "76"})
        if dict(request.headers) != expected:
            raise FigiAuditError("anonymous request headers contradict declaration")
        m.update(
            requests_attempted=1,
            attempted_at=now().isoformat(),
            state="interrupted",
            stop_reason="interrupted",
        )
        checkpoint("checkpoint-interrupted.json")
        raw = bytearray()
        complete = False
        status = None
        header_bytes = 0
        identity = True
        failure = None
        begin = monotonic()
        try:
            response = client.send(request, stream=True, auth=None, follow_redirects=False)
            try:
                status = response.status_code
                header_bytes = sum(len(k) + len(v) for k, v in response.headers.raw)
                identity = (
                    response.headers.get("content-encoding", "identity").lower() == "identity"
                )
                if header_bytes <= d["budget"]["maximum_response_header_bytes_total"]:
                    limit = d["budget"]["maximum_response_entity_bytes_total"]
                    for chunk in response.iter_raw():
                        if monotonic() - begin >= 30:
                            failure = "timeout"
                            break
                        raw.extend(chunk[: limit - len(raw)])
                        if len(raw) >= limit:
                            break
                    else:
                        complete = True
                    if monotonic() - begin >= 30:
                        failure, complete = "timeout", False
            finally:
                response.close()
        except httpx.TimeoutException:
            failure = "timeout"
        except httpx.TransportError:
            failure = "transport_error"
        at = now()
        body = bytes(raw)
        m.update(
            finished_at=at.isoformat(),
            http_status=status,
            complete_body=complete,
            header_bytes=header_bytes,
            identity_encoding=identity,
            failure=failure,
            privacy_blocked=privacy_blocked(body),
            bytes_retained=len(body),
            raw_sha256=digest(body),
        )
        manifest = capture_raw_bytes(
            DataLayout(output / "data"),
            body,
            provider_namespace="openfigi",
            source_family="openfigi.mapping",
            retrieved_at=at,
            adapter_version=VERSION,
            parser_version="openfigi-mapping/1.0.0",
            retention_class=RetentionClass.RESTRICTED,
            source_native_id=d["request"]["body_sha256"],
            source_locator=d["request"]["url"],
            request_parameters={
                "request_body_sha256": d["request"]["body_sha256"],
                "declaration_sha256": DECLARATION_HASH,
            },
            license_name="openfigi-private-reviewed-candidate-evidence",
        )
        m["capture_id"] = str(manifest.capture_id)
        m["manifest_sha256"] = digest(
            (DataLayout(output / "data").raw_manifests / f"{manifest.capture_id}.json").read_bytes()
        )
        m["state"] = response_state(body, m, d)
        m["stop_reason"] = m["state"]
        checkpoint("receipt.json")
    return m
