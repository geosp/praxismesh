"""An in-memory `BlobStore` for unit tests. Same contract as the S3 adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

from common.blob_store.base import (
    BlobCorrupt,
    BlobNotFound,
    collect,
    content_key,
    make_ref,
    stronger,
)
from common.schemas import BlobRef, RetentionClass

CHUNK = 64 * 1024


@dataclass
class _Object:
    data: bytes
    content_type: str
    retention: RetentionClass
    created_at: datetime


class MemoryBlobStore:
    def __init__(self) -> None:
        self.objects: dict[str, _Object] = {}

    async def put(
        self,
        data: bytes | AsyncIterator[bytes],
        *,
        content_type: str = "application/octet-stream",
        retention: RetentionClass,
    ) -> BlobRef:
        body = await collect(data)
        key, checksum = content_key(body)
        existing = self.objects.get(key)
        if existing is None:
            existing = _Object(body, content_type, retention, datetime.now(UTC))
            self.objects[key] = existing
        else:
            existing.retention = stronger(existing.retention, retention)
        return make_ref(
            key, checksum, existing.content_type, len(body), existing.retention, existing.created_at
        )

    def _object(self, ref: BlobRef) -> _Object:
        obj = self.objects.get(ref.key)
        if obj is None:
            raise BlobNotFound(ref.key)
        return obj

    async def get(self, ref: BlobRef) -> bytes:
        data = self._object(ref).data
        if content_key(data)[1] != ref.checksum:
            raise BlobCorrupt(ref.key)
        return data

    async def stream(self, ref: BlobRef) -> AsyncIterator[bytes]:
        data = await self.get(ref)
        for i in range(0, len(data), CHUNK):
            yield data[i : i + CHUNK]

    async def stat(self, ref: BlobRef) -> BlobRef:
        obj = self._object(ref)
        key, checksum = content_key(obj.data)
        return make_ref(
            key, checksum, obj.content_type, len(obj.data), obj.retention, obj.created_at
        )

    async def delete(self, ref: BlobRef) -> None:
        self.objects.pop(ref.key, None)

    def corrupt(self, ref: BlobRef) -> None:
        """Test hook: change the stored bytes without changing the key."""
        self.objects[ref.key].data += b"\0"
