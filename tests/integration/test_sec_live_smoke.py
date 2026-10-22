"""Explicitly opt-in live retrieval; excluded from ordinary network-free runs."""

import os

import pytest

from ragged_claws.ingestion.sec_http import SecFilingClient


@pytest.mark.skipif(os.environ.get("SEC_LIVE_SMOKE") != "1", reason="live SEC smoke is opt-in")
def test_opt_in_sec_filing_retrieval() -> None:
    agent = os.environ.get("SEC_USER_AGENT")
    url = os.environ.get("SEC_LIVE_FILING_URL")
    if not agent or not url:
        pytest.fail("live SEC smoke requires configured contact and explicit filing URL")
    client = SecFilingClient(user_agent=agent)
    try:
        assert client.fetch(url).startswith(b"<SEC-DOCUMENT>")
    finally:
        client.close()
