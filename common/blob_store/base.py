"""The `BlobStore` contract (plan §4.13, §5; RFC Phase 1, BlobStore contract).

Keys are content-addressed (`sha256/<hex>`), so `put` is idempotent: storing the
same bytes again returns the same `BlobRef`. If the repeat names a stronger
retention class, the stronger class wins (`ephemeral` < `checkpoint` <
`transcript` < `artifact` < `audit`). The old class `task` ranks as `transcript`,
and `stronger` never returns it (Phase 3A persistence plan D3).
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from common.errors import PraxisError
from common.schemas import BlobRef, RetentionClass

RETENTION_ORDER: dict[RetentionClass, int] = {
    "ephemeral": 0,
    "checkpoint": 1,
    "transcript": 2,
    "task": 2,  # the Phase 1-2 class, read as transcript
    "artifact": 3,
    "audit": 4,
}


@dataclass(frozen=True)
class BucketObject:
    """One object of a bucket listing (reconciliation reads these)."""

    key: str
    size: int
    last_modified: datetime


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


class BlobExpired(BlobError):
    """The blob was removed by GC or a delete; its removal is recorded (Phase 3A
    persistence plan R9, D6). Raised before the bucket is asked."""

    def __init__(self, key: str, removed_at: datetime) -> None:
        super().__init__(f"blob {key} expired: removed on {removed_at:%Y-%m-%d %H:%M} UTC")
        self.key = key
        self.removed_at = removed_at


def current_class(c: RetentionClass) -> RetentionClass:
    """The class to write for `c`: `task` is read as `transcript`."""
    return "transcript" if c == "task" else c


def stronger(a: RetentionClass, b: RetentionClass) -> RetentionClass:
    a, b = current_class(a), current_class(b)
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
        task_id: str | None = None,
    ) -> BlobRef:
        """Store `data`. `task_id` names the task the upload is made for; a store
        that records references holds the blob for it (Phase 3A persistence plan
        D2); the others ignore it."""
        ...

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
