"""SDK request contract and bounded, sanitized failures. Stubber prevents all network calls."""

import os
from io import BytesIO
from pathlib import Path
from typing import Any

import boto3  # type: ignore[import-untyped]
import pytest
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.response import StreamingBody  # type: ignore[import-untyped]
from botocore.stub import Stubber  # type: ignore[import-untyped]

from ragged_claws.durable.models import MAX_FILE, DurableError
from ragged_claws.durable.objects import (
    ConditionalConflict,
    IndeterminateWrite,
    LocalObjects,
    MemoryObjects,
    MissingObject,
    S3Objects,
    isolated_live_objects,
)


@pytest.fixture(autouse=True)
def isolated_sdk_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_CONFIG_FILE", os.devnull)
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", os.devnull)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.delenv("AWS_PROFILE", raising=False)


def client() -> Any:
    return boto3.client(
        "s3",
        endpoint_url="https://example.invalid",
        region_name="auto",
        aws_access_key_id="INVENTED-NOT-A-KEY",
        aws_secret_access_key="INVENTED-NOT-A-SECRET",
        config=Config(retries={"total_max_attempts": 1}),
    )


def test_sdk_conditional_create_and_opaque_etag_replace_contract() -> None:
    sdk = client()
    with Stubber(sdk) as stub:
        stub.add_response(
            "put_object",
            {"ETag": '"opaque-first"'},
            {
                "Bucket": "invented",
                "Key": "isolated/x",
                "Body": b"abc",
                "IfNoneMatch": "*",
            },
        )
        stub.add_response(
            "put_object",
            {"ETag": '"opaque-second"'},
            {
                "Bucket": "invented",
                "Key": "isolated/x",
                "Body": b"xyz",
                "IfMatch": '"opaque-first"',
            },
        )
        store = S3Objects(sdk, bucket="invented", prefix="isolated")
        etag = store.put("x", b"abc", expected_etag=None)
        assert etag == '"opaque-first"'
        assert store.put("x", b"xyz", expected_etag=etag) == '"opaque-second"'
        stub.assert_no_pending_responses()


@pytest.mark.parametrize("status", [409, 412, 403, 500])
def test_sdk_write_failure_is_sanitized_and_not_automatically_retried(status: int) -> None:
    sdk = client()
    with Stubber(sdk) as stub:
        stub.add_client_error(
            "put_object",
            service_error_code="PreconditionFailed",
            service_message="INVENTED-PRIVATE-PAYLOAD",
            http_status_code=status,
            expected_params={
                "Bucket": "invented",
                "Key": "isolated/x",
                "Body": b"abc",
                "IfNoneMatch": "*",
            },
        )
        store = S3Objects(sdk, bucket="invented", prefix="isolated")
        expected = ConditionalConflict if status in (409, 412) else IndeterminateWrite
        with pytest.raises(expected) as error:
            store.put("x", b"abc", expected_etag=None)
        assert "INVENTED-PRIVATE-PAYLOAD" not in str(error.value)
        stub.assert_no_pending_responses()


def test_sdk_read_exact_bytes_and_always_close_body() -> None:
    sdk = client()
    stream = BytesIO(b"abc")
    with Stubber(sdk) as stub:
        stub.add_response(
            "get_object",
            {"Body": StreamingBody(stream, 3), "ContentLength": 3, "ETag": '"opaque"'},
            {"Bucket": "invented", "Key": "isolated/x"},
        )
        result = S3Objects(sdk, bucket="invented", prefix="isolated").get("x", limit=3)
        assert result.content == b"abc" and result.etag == '"opaque"' and stream.closed


@pytest.mark.parametrize("declared", [2, 4])
def test_sdk_truncated_or_oversized_body_rejected(declared: int) -> None:
    sdk = client()
    stream = BytesIO(b"abc")
    with Stubber(sdk) as stub:
        stub.add_response(
            "get_object",
            {"Body": StreamingBody(stream, 3), "ContentLength": declared, "ETag": '"opaque"'},
            {"Bucket": "invented", "Key": "isolated/x"},
        )
        with pytest.raises(DurableError):
            S3Objects(sdk, bucket="invented", prefix="isolated").get("x", limit=3)
        assert stream.closed


def test_only_no_such_key_is_absence_not_access_denied() -> None:
    sdk = client()
    with Stubber(sdk) as stub:
        for code, status in (("NoSuchKey", 404), ("AccessDenied", 403), ("NoSuchBucket", 404)):
            stub.add_client_error(
                "get_object",
                service_error_code=code,
                http_status_code=status,
                service_message="INVENTED-PRIVATE-PAYLOAD",
            )
        store = S3Objects(sdk, bucket="invented", prefix="isolated")
        with pytest.raises(MissingObject):
            store.get("x", limit=3)
        for _ in range(2):
            with pytest.raises(DurableError, match="read_failed") as error:
                store.get("x", limit=3)
            assert "INVENTED-PRIVATE-PAYLOAD" not in str(error.value)


def test_live_factory_stays_off_before_reading_any_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RAGGED_CLAWS_DURABLE_LIVE", raising=False)
    with pytest.raises(DurableError, match="not_explicitly_authorized"):
        isolated_live_objects()


@pytest.mark.parametrize("disk", [False, True])
def test_fake_conditional_semantics_and_read_write_bounds(tmp_path: Path, disk: bool) -> None:
    store = LocalObjects(tmp_path / "objects") if disk else MemoryObjects()
    with pytest.raises(MissingObject):
        store.get("a", limit=3)
    tag = store.put("a", b"abc", expected_etag=None)
    with pytest.raises(ConditionalConflict):
        store.put("a", b"abc", expected_etag=None)
    with pytest.raises(ConditionalConflict):
        store.put("a", b"def", expected_etag='"stale"')
    assert store.put("a", b"def", expected_etag=tag) != tag
    with pytest.raises(DurableError, match="read_bound"):
        store.get("a", limit=2)
    with pytest.raises(DurableError, match="too_large"):
        store.put("b", b"x" * (MAX_FILE + 1), expected_etag=None)
