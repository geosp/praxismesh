"""The `BlobStore` contract (plan §4.13, §5; RFC Phase 1, BlobStore contract).

Keys are content-addressed (`sha256/<hex>`), so `put` is idempotent: storing the
same bytes again returns the same `BlobRef`. If the repeat names a stronger
retention class, the stronger class wins (`ephemeral` < `task` < `audit`).
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Protocol

from common.errors import PraxisError
from common.schemas import BlobRef, RetentionClass

RETENTION_ORDER: dict[RetentionClass, int] = {"ephemeral": 0, "task": 1, "audit": 2}


class BlobError(PraxisError):
    """Base class for storage errors. Adapters raise only its subclasses."""


class BlobNotFound(BlobError):
    pass


class BlobCorrupt(BlobError):
    """The stored bytes no longer match the checksum."""


class BlobUnauthorized(BlobError):
    pass


class BlobUnavailable(BlobError):
    """The backend cannot be reached; retrying may succeed."""


def stronger(a: RetentionClass, b: RetentionClass) -> RetentionClass:
    return a if RETENTION_ORDER[a] >= RETENTION_ORDER[b] else b


def content_key(data: bytes) -> tuple[str, str]:
    """Return the object key and checksum for `data`."""
    hexdigest = hashlib.sha256(data).hexdigest()
    return f"sha256/{hexdigest}", f"sha256:{hexdigest}"


def make_ref(
    key: str,
    checksum: str,
    content_type: str,
    size: int,
    retention: RetentionClass,
    created_at: datetime,
) -> BlobRef:
    return BlobRef(
        id=f"blob:{checksum.removeprefix('sha256:')}",
        key=key,
        checksum=checksum,
        content_type=content_type,
        bytes=size,
        retention_class=retention,
        created_at=created_at,
    )


class BlobStore(Protocol):
    async def put(
        self,
        data: bytes | AsyncIterator[bytes],
        *,
        content_type: str = "application/octet-stream",
        retention: RetentionClass,
    ) -> BlobRef: ...

    async def get(self, ref: BlobRef) -> bytes: ...

    def stream(self, ref: BlobRef) -> AsyncIterator[bytes]: ...

    async def stat(self, ref: BlobRef) -> BlobRef: ...

    async def delete(self, ref: BlobRef) -> None:
        """Delete the object. Deleting a missing object is not an error."""
        ...


async def collect(data: bytes | AsyncIterator[bytes]) -> bytes:
    if isinstance(data, bytes):
        return data
    return b"".join([chunk async for chunk in data])
