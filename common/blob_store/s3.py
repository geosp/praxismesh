"""The S3 `BlobStore` adapter, verified against SeaweedFS (plan §4.13).

boto3 is synchronous, so calls run in a worker thread. The retention class is
kept in the object's metadata as well as in `blob_objects`.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError

from common.blob_store.base import (
    BlobCorrupt,
    BlobError,
    BlobNotFound,
    BlobUnauthorized,
    BlobUnavailable,
    collect,
    content_key,
    make_ref,
    stronger,
)
from common.schemas import BlobRef, RetentionClass

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

NOT_FOUND = {"NoSuchKey", "404", "NotFound", "NoSuchBucket"}
UNAUTHORIZED = {"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch", "403"}
META = "retention"


def _translate(e: Exception, key: str) -> BlobError:
    if isinstance(e, ClientError):
        code = str(e.response.get("Error", {}).get("Code", ""))
        if code in NOT_FOUND:
            return BlobNotFound(key)
        if code in UNAUTHORIZED:
            return BlobUnauthorized(f"{key}: {code}")
        return BlobUnavailable(f"{key}: {code}")
    return BlobUnavailable(f"{key}: {e}")


class S3BlobStore:
    def __init__(self, client: S3Client, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    @classmethod
    def from_env(cls) -> S3BlobStore:
        """Configure from the environment that `make` loads from infra/.env."""
        client = boto3.client(
            "s3",
            endpoint_url=os.environ.get("S3_ENDPOINT")
            or f"http://127.0.0.1:{os.environ.get('S3_PORT', '8333')}",
            aws_access_key_id=os.environ["S3_ACCESS_KEY"],
            aws_secret_access_key=os.environ["S3_SECRET_KEY"],
            region_name="us-east-1",
            config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
        )
        return cls(client, os.environ["S3_BUCKET"])

    async def _call(self, key: str, fn: Any, **kwargs: Any) -> Any:
        try:
            return await asyncio.to_thread(fn, **kwargs)
        except (ClientError, BotoCoreError, EndpointConnectionError) as e:
            raise _translate(e, key) from e

    async def ensure_bucket(self) -> None:
        try:
            await self._call(self.bucket, self.client.head_bucket, Bucket=self.bucket)
        except BlobNotFound:
            await self._call(self.bucket, self.client.create_bucket, Bucket=self.bucket)

    async def put(
        self,
        data: bytes | AsyncIterator[bytes],
        *,
        content_type: str = "application/octet-stream",
        retention: RetentionClass,
    ) -> BlobRef:
        body = await collect(data)
        key, checksum = content_key(body)
        try:
            head = await self._call(key, self.client.head_object, Bucket=self.bucket, Key=key)
        except BlobNotFound:
            await self._call(
                key,
                self.client.put_object,
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
                Metadata={META: retention},
            )
            return await self.stat(
                make_ref(key, checksum, content_type, len(body), retention, datetime.now(UTC))
            )
        current = cast(RetentionClass, head.get("Metadata", {}).get(META, retention))
        wanted = stronger(current, retention)
        if wanted != current:
            await self._call(
                key,
                self.client.copy_object,
                Bucket=self.bucket,
                Key=key,
                CopySource={"Bucket": self.bucket, "Key": key},
                Metadata={META: wanted},
                MetadataDirective="REPLACE",
                ContentType=head.get("ContentType", content_type),
            )
        return make_ref(
            key,
            checksum,
            head.get("ContentType", content_type),
            len(body),
            wanted,
            head["LastModified"],
        )

    async def get(self, ref: BlobRef) -> bytes:
        obj = await self._call(ref.key, self.client.get_object, Bucket=self.bucket, Key=ref.key)
        data = cast(bytes, await asyncio.to_thread(obj["Body"].read))
        if content_key(data)[1] != ref.checksum:
            raise BlobCorrupt(ref.key)
        return data

    async def stream(self, ref: BlobRef) -> AsyncIterator[bytes]:
        # The checksum covers the whole object, so it is verified before yielding.
        data = await self.get(ref)
        for i in range(0, len(data), 64 * 1024):
            yield data[i : i + 64 * 1024]

    async def stat(self, ref: BlobRef) -> BlobRef:
        head = await self._call(ref.key, self.client.head_object, Bucket=self.bucket, Key=ref.key)
        return make_ref(
            ref.key,
            ref.checksum,
            head.get("ContentType", ref.content_type),
            int(head["ContentLength"]),
            cast(RetentionClass, head.get("Metadata", {}).get(META, ref.retention_class)),
            head["LastModified"],
        )

    async def delete(self, ref: BlobRef) -> None:
        await self._call(ref.key, self.client.delete_object, Bucket=self.bucket, Key=ref.key)
