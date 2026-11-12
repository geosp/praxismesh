"""The `BlobStore` contract suite (spec storage/blob-store). Every adapter must pass
it: the in-memory fake in the unit run, the S3 adapter against SeaweedFS in the
`stack` job. A test module provides a `store` fixture and a `corrupt` fixture."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable

import pytest

from common.blob_store import BlobCorrupt, BlobNotFound, BlobStore
from common.schemas import BlobRef

Corrupt = Callable[[BlobRef], None]


def payload() -> bytes:
    return b"praxismesh contract " + os.urandom(16)


async def chunks(data: bytes, size: int = 7) -> AsyncIterator[bytes]:
    for i in range(0, len(data), size):
        yield data[i : i + size]


class BlobStoreContract:
    async def test_round_trip(self, store: BlobStore) -> None:
        data = payload()
        ref = await store.put(data, content_type="text/plain", retention="task")
        assert await store.get(ref) == data
        assert ref.bytes == len(data) and ref.content_type == "text/plain"
        assert ref.key.startswith("sha256/") and ref.checksum.startswith("sha256:")

    async def test_idempotent_put(self, store: BlobStore) -> None:
        data = payload()
        first = await store.put(data, retention="task")
        second = await store.put(data, retention="task")
        assert (first.key, first.checksum) == (second.key, second.checksum)

    async def test_stronger_retention_wins(self, store: BlobStore) -> None:
        data = payload()
        await store.put(data, retention="ephemeral")
        assert (await store.put(data, retention="audit")).retention_class == "audit"
        assert (await store.put(data, retention="task")).retention_class == "audit"
        ref = await store.put(data, retention="ephemeral")
        assert (await store.stat(ref)).retention_class == "audit"

    async def test_put_from_stream(self, store: BlobStore) -> None:
        data = payload() * 10
        ref = await store.put(chunks(data), retention="task")
        assert await store.get(ref) == data

    async def test_stream(self, store: BlobStore) -> None:
        data = payload() * 5000
        ref = await store.put(data, retention="task")
        assert b"".join([c async for c in store.stream(ref)]) == data

    async def test_stat(self, store: BlobStore) -> None:
        data = payload()
        ref = await store.put(data, content_type="application/json", retention="audit")
        stat = await store.stat(ref)
        assert stat.bytes == len(data)
        assert stat.content_type == "application/json"
        assert stat.retention_class == "audit"

    async def test_delete(self, store: BlobStore) -> None:
        ref = await store.put(payload(), retention="ephemeral")
        await store.delete(ref)
        with pytest.raises(BlobNotFound):
            await store.get(ref)
        await store.delete(ref)  # deleting again is not an error

    async def test_missing_is_not_found(self, store: BlobStore) -> None:
        ref = await store.put(payload(), retention="ephemeral")
        await store.delete(ref)
        with pytest.raises(BlobNotFound):
            await store.stat(ref)

    async def test_corrupt_is_detected(self, store: BlobStore, corrupt: Corrupt) -> None:
        ref = await store.put(payload(), retention="task")
        corrupt(ref)
        with pytest.raises(BlobCorrupt):
            await store.get(ref)
        with pytest.raises(BlobCorrupt):
            _ = [c async for c in store.stream(ref)]
