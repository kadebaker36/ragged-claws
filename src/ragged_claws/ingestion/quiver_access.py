"""Explicit future access/retention boundary; no entitlement is assumed by this project."""

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx
from pydantic import SecretStr

from ragged_claws.ingestion.quiver_models import Endpoint
from ragged_claws.ingestion.quiver_parser import PATHS, QuiverError
from ragged_claws.models.base import CanonicalModel, UtcDatetime
from ragged_claws.models.evidence import Sha256Hex


class QuiverAccessReview(CanonicalModel):
    """Operator's reviewed applicable agreement, not a software grant of permission."""

    agreement_sha256: Sha256Hex
    reviewed_at: UtcDatetime
    entitled_endpoints: tuple[Endpoint, ...]
    local_raw_retention_permitted: Literal[True]
    local_derived_retention_permitted: Literal[True]
    root_is_not_synced_or_shared: Literal[True]


MAX_BODY_BYTES = 5_000_000
MAX_HEADER_BYTES = 65_536


def _response_length(response: httpx.Response, cap: int) -> int | None:
    raw = response.headers.raw
    if sum(len(name) + len(value) for name, value in raw) > MAX_HEADER_BYTES:
        raise QuiverError("response headers exceed bounded capture size")
    lengths = [v.strip(b" \t") for k, v in raw if k.lower() == b"content-length"]
    if len(lengths) > 1 or (lengths and "transfer-encoding" in response.headers):
        raise QuiverError("ambiguous response length")
    if not lengths:
        return None
    value = lengths[0]
    if not value or not value.isdigit():
        raise QuiverError("invalid response length")
    significant = value.lstrip(b"0") or b"0"
    if len(significant) > 7 or int(significant) > cap:
        raise QuiverError("response exceeds bounded capture size")
    return int(significant)


def _decoded_token_echo(content: bytes, secret: str) -> bool:
    # Preserve duplicate keys/values for privacy inspection; canonical parsing is separate.
    def pairs(values: list[tuple[str, object]]) -> list[tuple[str, object]]:
        return values

    def constant(_: str) -> None:
        raise QuiverError("invalid JSON response")

    try:
        # Use the same encoding detection as json.loads(bytes), before numeric conversion.
        # Scalar lexemes must not disappear through Decimal/bool/null normalization.
        text = content.decode(json.detect_encoding(content), errors="surrogatepass")
        if secret in text:
            return True
        pending = [
            json.loads(
                text,
                object_pairs_hook=pairs,
                parse_int=Decimal,
                parse_float=Decimal,
                parse_constant=constant,
            )
        ]
        while pending:
            value = pending.pop()
            if isinstance(value, str) and secret in value:
                return True
            if isinstance(value, (list, tuple)):
                pending.extend(value)
    except (ValueError, UnicodeError, RecursionError):
        raise QuiverError("invalid JSON response") from None
    return False


def request_identity(url: str, endpoint: Endpoint) -> tuple[str, int]:
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.netloc != "api.quiverquant.com"
        or parts.fragment
        or parts.path != PATHS[endpoint]
    ):
        raise QuiverError("unsupported source locator")
    try:
        pairs = parse_qsl(parts.query, strict_parsing=True, keep_blank_values=True)
    except ValueError as exc:
        raise QuiverError("invalid request parameters") from exc
    parameters = dict(pairs)
    if len(parameters) != len(pairs):
        raise QuiverError("duplicate request parameter")
    if endpoint == "congress_v1":
        if parameters:
            raise QuiverError("unsupported V1 request parameters")
        return parts.path, 500
    expected = {"page", "page_size"} | ({"version"} if endpoint == "congress_v2" else set())
    if set(parameters) != expected or (endpoint == "congress_v2" and parameters["version"] != "V2"):
        raise QuiverError("explicit bounded page/version parameters required")
    if (
        not parameters["page"].isascii()
        or not parameters["page"].isdigit()
        or not parameters["page_size"].isascii()
        or not parameters["page_size"].isdigit()
        or int(parameters["page"]) < 1
        or not 1 <= int(parameters["page_size"]) <= 100
    ):
        raise QuiverError("invalid page bounds")
    return parts.path + "?" + urlencode(sorted(parameters.items())), int(parameters["page_size"])


def require_restricted_storage(
    root: Path, review: QuiverAccessReview | None, endpoint: Endpoint, at: datetime
) -> QuiverAccessReview:
    if review is None or endpoint not in review.entitled_endpoints or review.reviewed_at > at:
        raise QuiverError("applicable agreement, entitlement and retention review required")
    resolved = root.resolve()
    if resolved.anchor.startswith(("\\\\", "//")):
        raise QuiverError("restricted state must use local private storage")
    if any((parent / ".git").exists() for parent in (resolved, *resolved.parents)):
        raise QuiverError("restricted state must be outside all Git worktrees")
    if any(
        any(
            marker in part.casefold()
            for marker in ("onedrive", "dropbox", "icloud", "google drive")
        )
        for part in resolved.parts
    ):
        raise QuiverError("restricted state must be outside known sync locations")
    # Common-path checks are additional guards; the explicit non-sync attestation is mandatory.
    return review


def retrieve_quiver(
    client: httpx.Client,
    url: str,
    *,
    endpoint: Endpoint,
    token: SecretStr,
    review: QuiverAccessReview | None,
    storage_root: Path,
    at: datetime,
    opt_in: bool = False,
    max_body_bytes: int = MAX_BODY_BYTES,
) -> bytes:
    try:
        request_identity(url, endpoint)
    except (ValueError, KeyError):
        raise QuiverError("unsupported source locator") from None
    require_restricted_storage(storage_root, review, endpoint, at)
    if not opt_in or not token.get_secret_value().strip():
        raise QuiverError("explicit live opt-in and configured credentials required")
    if type(max_body_bytes) is not int or not 0 < max_body_bytes <= MAX_BODY_BYTES:
        raise QuiverError("invalid bounded capture size")
    if client.params:
        raise QuiverError("client default query parameters are not permitted")
    secret = token.get_secret_value()
    try:
        secret_bytes = secret.encode("utf8")
        with client.stream(
            "GET",
            url,
            headers={
                "Authorization": "Bearer " + secret,
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "User-Agent": "RaggedClaws-Quiver/0.1",
            },
            follow_redirects=False,
            auth=None,
            timeout=httpx.Timeout(30.0),
        ) as response:
            declared = _response_length(response, max_body_bytes)
            if (
                response.status_code != 200
                or response.headers.get("content-type", "").split(";")[0].strip(" \t").lower()
                != "application/json"
                or len(response.headers.get_list("content-type")) != 1
                or response.headers.get("content-encoding", "identity").strip(" \t").lower()
                != "identity"
                or len(response.headers.get_list("content-encoding")) > 1
            ):
                raise QuiverError("Quiver access unavailable; no retry or challenge handling")
            body = bytearray()
            tail = b""
            for chunk in response.iter_bytes():
                size = len(body) + len(chunk)
                if size > max_body_bytes:
                    raise QuiverError("response exceeds bounded capture size")
                if declared is not None and size > declared:
                    raise QuiverError("response length mismatch")
                if secret_bytes in tail + chunk:
                    raise QuiverError("credential echo rejected before capture")
                tail = (tail + chunk)[-(len(secret_bytes) - 1) :] if len(secret_bytes) > 1 else b""
                body.extend(chunk)
            if declared is not None and len(body) != declared:
                raise QuiverError("response length mismatch")
            content = bytes(body)
            if _decoded_token_echo(content, secret):
                raise QuiverError("credential echo rejected before capture")
        return content
    except QuiverError:
        raise QuiverError("Quiver response rejected before capture") from None
    except Exception:
        raise QuiverError("Quiver request failed; details withheld") from None
