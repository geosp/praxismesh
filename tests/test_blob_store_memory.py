"""The `BlobStore` contract against the in-memory fake."""

from __future__ import annotations

import pytest

from common.blob_store import MemoryBlobStore
from tests.support.blob_contract import BlobStoreContract, Corrupt


@pytest.fixture
def memory_store() -> MemoryBlobStore:
    return MemoryBlobStore()


@pytest.fixture
def store(memory_store: MemoryBlobStore) -> MemoryBlobStore:
    return memory_store


@pytest.fixture
def corrupt(memory_store: MemoryBlobStore) -> Corrupt:
    return memory_store.corrupt


class TestMemoryBlobStore(BlobStoreContract):
    pass
