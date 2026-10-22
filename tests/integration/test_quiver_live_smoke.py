"""Never runs by default; requires separately established entitlement and reviewed retention."""

import os
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from ragged_claws.ingestion.quiver import QuiverAdapter
from ragged_claws.ingestion.quiver_access import QuiverAccessReview, retrieve_quiver
from ragged_claws.storage import DataLayout


@pytest.mark.skipif(
    os.environ.get("RAGGED_CLAWS_QUIVER_LIVE") != "1", reason="opt-in Quiver live smoke"
)
def test_quiver_explicitly_authorized_live_smoke() -> None:
    names = ("QUIVER_API_TOKEN", "QUIVER_AGREEMENT_REVIEW_PATH", "QUIVER_PRIVATE_DATA_ROOT")
    if not all(os.environ.get(name) for name in names):
        pytest.skip(
            "requires user-established credentials, entitlement, review and private storage"
        )
    review = QuiverAccessReview.model_validate_json(Path(os.environ[names[1]]).read_bytes())
    root = Path(os.environ[names[2]])
    now = datetime.now(UTC)
    url = "https://api.quiverquant.com/beta/live/congresstrading"
    with httpx.Client(timeout=30) as client:
        content = retrieve_quiver(
            client,
            url,
            endpoint="congress_v1",
            token=SecretStr(os.environ[names[0]]),
            review=review,
            storage_root=root,
            at=now,
            opt_in=True,
        )
    bundle = QuiverAdapter(DataLayout(root)).ingest(
        content, endpoint="congress_v1", source_locator=url, retrieved_at=now, review=review
    )
    assert not bundle.synthetic
