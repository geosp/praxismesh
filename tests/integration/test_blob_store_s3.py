"""The `BlobStore` contract against SeaweedFS through the S3 adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from common.blob_store.s3 import S3BlobStore
from common.schemas import BlobRef
from tests.support.blob_contract import BlobStoreContract, Corrupt
from tests.support.stack import scratch_bucket

pytestmark = pytest.mark.integration


@pytest.fixture
async def store() -> AsyncIterator[S3BlobStore]:
    async with scratch_bucket("contract") as s3:
        yield s3


@pytest.fixture
def corrupt(store: S3BlobStore) -> Corrupt:
    def overwrite(ref: BlobRef) -> None:
        store.client.put_object(Bucket=store.bucket, Key=ref.key, Body=b"not the original bytes")

    return overwrite


class TestS3BlobStore(BlobStoreContract):
    pass


async def test_list_objects_names_every_object(store: S3BlobStore) -> None:
    refs = [await store.put(f"object {i}".encode(), retention="transcript") for i in range(3)]
    listing = await store.list_objects()
    assert set(listing) == {r.key for r in refs}
    assert all(listing[r.key].size == r.bytes for r in refs)


async def test_a_bucket_not_yet_created_lists_nothing() -> None:
    """The bucket is created on first use; until then reconcile and gc see an
    empty one (Phase 3A persistence plan phase 03)."""
    async with scratch_bucket("absent", create=False) as s3:
        assert await s3.list_objects() == {}
