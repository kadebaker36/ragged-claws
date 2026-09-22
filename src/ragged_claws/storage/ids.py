"""Central deterministic identity rules for source observations."""

import re
from uuid import UUID, uuid5

SOURCE_OBSERVATION_NAMESPACE = UUID("da099230-b255-5fc4-a40f-58ef2408a9a1")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def deterministic_source_observation_id(
    provider_namespace: str,
    source_native_id: str,
    content_sha256: str,
) -> UUID:
    """Identify one immutable source-native version with UUIDv5.

    The exact UUIDv5 name is the UTF-8 encoding of three length-prefixed values:
    provider namespace, source-native ID, and ``sha256:<lowercase hex>``.
    Length prefixes avoid delimiter ambiguity while excluding mutable labels and paths.
    """
    provider = provider_namespace.strip()
    native_id = source_native_id.strip()
    digest = content_sha256.strip()
    if not provider or not native_id:
        raise ValueError("provider namespace and source-native ID must be non-empty")
    if _SHA256.fullmatch(digest) is None:
        raise ValueError("content SHA-256 must be 64 lowercase hexadecimal characters")
    components = (provider, native_id, f"sha256:{digest}")
    name = "".join(f"{len(value)}:{value}" for value in components)
    return uuid5(SOURCE_OBSERVATION_NAMESPACE, name)
