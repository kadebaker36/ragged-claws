"""Explicit future access/retention boundary; no entitlement is assumed by this project."""

from datetime import datetime
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
) -> bytes:
    request_identity(url, endpoint)
    require_restricted_storage(storage_root, review, endpoint, at)
    if not opt_in or not token.get_secret_value().strip():
        raise QuiverError("explicit live opt-in and configured credentials required")
    try:
        response = client.get(
            url,
            headers={
                "Authorization": "Bearer " + token.get_secret_value(),
                "Accept": "application/json",
                "User-Agent": "RaggedClaws-Quiver/0.1",
            },
            follow_redirects=False,
        )
    except httpx.HTTPError:
        raise QuiverError("Quiver request failed; details withheld") from None
    if (
        response.status_code != 200
        or response.headers.get("content-type", "").split(";")[0] != "application/json"
    ):
        raise QuiverError("Quiver access unavailable; no retry or challenge handling")
    if len(response.content) > 5_000_000:
        raise QuiverError("response exceeds bounded capture size")
    if token.get_secret_value().encode() in response.content:
        raise QuiverError("credential echo rejected before capture")
    return response.content
