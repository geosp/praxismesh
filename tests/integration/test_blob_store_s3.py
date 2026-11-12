"""The `BlobStore` contract against SeaweedFS through the S3 adapter."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest

from common.blob_store.s3 import S3BlobStore
from common.schemas import BlobRef
from tests.support.blob_contract import BlobStoreContract, Corrupt
from tests.support.stack import run_id

pytestmark = pytest.mark.integration


@pytest.fixture
async def store() -> AsyncIterator[S3BlobStore]:
    os.environ.setdefault("S3_BUCKET", "praxismesh")
    s3 = S3BlobStore.from_env()
    s3.bucket = f"contract-{run_id()}"
    await s3.ensure_bucket()
    yield s3
    for obj in s3.client.list_objects_v2(Bucket=s3.bucket).get("Contents", []):
        s3.client.delete_object(Bucket=s3.bucket, Key=obj["Key"])
    s3.client.delete_bucket(Bucket=s3.bucket)


@pytest.fixture
def corrupt(store: S3BlobStore) -> Corrupt:
    def overwrite(ref: BlobRef) -> None:
        store.client.put_object(Bucket=store.bucket, Key=ref.key, Body=b"not the original bytes")

    return overwrite


class TestS3BlobStore(BlobStoreContract):
    pass
