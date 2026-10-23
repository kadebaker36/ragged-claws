"""Only bounded GET and conditional PUT. Local stores are isolated single-writer test boundaries."""

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Protocol
from urllib.parse import urlsplit

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from ragged_claws.durable.models import MAX_FILE, DurableError, safe_path


class MissingObject(DurableError):
    def __init__(self) -> None:
        super().__init__("object_missing")


class ConditionalConflict(DurableError):
    def __init__(self) -> None:
        super().__init__("conditional_write_rejected")


class IndeterminateWrite(DurableError):
    def __init__(self) -> None:
        super().__init__("write_outcome_unknown_stop_and_reconcile")


@dataclass(frozen=True)
class ObjectValue:
    content: bytes
    etag: str


class ObjectStore(Protocol):
    def get(self, key: str, *, limit: int) -> ObjectValue: ...
    def put(self, key: str, content: bytes, *, expected_etag: str | None) -> str:
        """None means If-None-Match:*; otherwise If-Match with the opaque observed ETag."""
        ...


class MemoryObjects:
    """Atomic in-process fake; not an implementation of distributed coordination."""

    def __init__(self) -> None:
        self.values: dict[str, ObjectValue] = {}
        self.lock = RLock()

    def get(self, key: str, *, limit: int) -> ObjectValue:
        safe_path(key)
        with self.lock:
            if key not in self.values:
                raise MissingObject()
            result = self.values[key]
            if len(result.content) > limit:
                raise DurableError("object_exceeds_read_bound")
            return result

    def put(self, key: str, content: bytes, *, expected_etag: str | None) -> str:
        safe_path(key)
        if len(content) > MAX_FILE:
            raise DurableError("object_too_large")
        with self.lock:
            old = self.values.get(key)
            if (old.etag if old else None) != expected_etag:
                raise ConditionalConflict()
            tag = '"' + hashlib.sha256(content).hexdigest() + '"'
            self.values[key] = ObjectValue(content, tag)
            return tag


class LocalObjects:
    """Disk fake for offline demonstrations; caller must serialize all processes/writers."""

    def __init__(self, root: Path) -> None:
        if root.is_symlink():
            raise DurableError("unsafe_object_root")
        self.root = root.resolve()
        self.lock = RLock()

    def path(self, key: str) -> Path:
        safe_path(key)
        path = self.root / key
        if not path.resolve().is_relative_to(self.root) or any(
            p.is_symlink() for p in (path, *path.parents) if p != self.root.parent
        ):
            raise DurableError("unsafe_object_path")
        return path

    def get(self, key: str, *, limit: int) -> ObjectValue:
        path = self.path(key)
        with self.lock:
            if not path.exists():
                raise MissingObject()
            if not path.is_file() or path.stat().st_size > limit:
                raise DurableError("object_exceeds_read_bound")
            with path.open("rb") as handle:
                content = handle.read(limit + 1)
            if len(content) > limit:
                raise DurableError("object_exceeds_read_bound")
            return ObjectValue(content, '"' + hashlib.sha256(content).hexdigest() + '"')

    def put(self, key: str, content: bytes, *, expected_etag: str | None) -> str:
        path = self.path(key)
        if len(content) > MAX_FILE:
            raise DurableError("object_too_large")
        with self.lock:
            try:
                current = self.get(key, limit=MAX_FILE).etag
            except MissingObject:
                current = None
            if current != expected_etag:
                raise ConditionalConflict()
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
                    temporary = Path(handle.name)
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            return '"' + hashlib.sha256(content).hexdigest() + '"'


class S3Objects:
    """Thin SDK transport; credentials/client creation are separate, explicit and opt-in."""

    def __init__(self, client: Any, *, bucket: str, prefix: str) -> None:
        safe_path(prefix)
        self.client, self.bucket, self.prefix = client, bucket, prefix

    def key(self, key: str) -> str:
        return self.prefix + "/" + safe_path(key)

    def get(self, key: str, *, limit: int) -> ObjectValue:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self.key(key))
            body = response["Body"]
            try:
                if not 0 <= response["ContentLength"] <= limit:
                    raise DurableError("object_exceeds_read_bound")
                content = body.read(limit + 1)
                if len(content) != response["ContentLength"] or len(content) > limit:
                    raise DurableError("truncated_or_oversized_object")
                return ObjectValue(content, str(response["ETag"]))
            finally:
                body.close()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "NoSuchKey":
                raise MissingObject() from None
            raise DurableError("object_read_failed") from None
        except (BotoCoreError, OSError, KeyError, TypeError):
            raise DurableError("object_read_failed") from None

    def put(self, key: str, content: bytes, *, expected_etag: str | None) -> str:
        if len(content) > MAX_FILE:
            raise DurableError("object_too_large")
        condition = {"IfNoneMatch": "*"} if expected_etag is None else {"IfMatch": expected_etag}
        try:
            response = self.client.put_object(
                Bucket=self.bucket, Key=self.key(key), Body=content, **condition
            )
            return str(response["ETag"])
        except ClientError as exc:
            if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") in (409, 412):
                raise ConditionalConflict() from None
            raise IndeterminateWrite() from None
        except (BotoCoreError, OSError, KeyError, TypeError):
            raise IndeterminateWrite() from None


def isolated_live_objects() -> S3Objects:
    """Never called by default CLI/runtime. No implicit credential chain or automatic retry."""
    if (
        os.environ.get("RAGGED_CLAWS_DURABLE_LIVE") != "1"
        or os.environ.get("RAGGED_CLAWS_R2_ISOLATED_ACK") != "NON_PRODUCTION_ONLY"
    ):
        raise DurableError("live_storage_not_explicitly_authorized")
    endpoint = os.environ.get("RAGGED_CLAWS_R2_ENDPOINT", "")
    bucket = os.environ.get("RAGGED_CLAWS_R2_BUCKET", "")
    prefix = os.environ.get("RAGGED_CLAWS_R2_PREFIX", "")
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or not (parsed.hostname or "").endswith(".r2.cloudflarestorage.com")
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
        or not bucket.startswith("ragged-claws-smoke-")
        or not prefix.startswith("isolated-smoke-")
    ):
        raise DurableError("isolated_live_configuration_required")
    key = os.environ.get("AWS_ACCESS_KEY_ID")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
    if not key or not secret:
        raise DurableError("explicit_live_credentials_missing")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="auto",
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        config=Config(
            signature_version="s3v4",
            connect_timeout=10,
            read_timeout=10,
            retries={"total_max_attempts": 1},
        ),
    )
    return S3Objects(client, bucket=bucket, prefix=prefix)
