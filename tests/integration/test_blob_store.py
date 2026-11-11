"""S3 round trip against SeaweedFS (blob-store spec)."""

from __future__ import annotations

import pytest

from tests.support.stack import run_id, s3_client

pytestmark = pytest.mark.integration


def test_s3_round_trip() -> None:
    s3 = s3_client()
    bucket = f"phase0-smoke-{run_id()}"
    body = b"praxismesh phase 0"
    s3.create_bucket(Bucket=bucket)
    try:
        s3.put_object(Bucket=bucket, Key="hello.txt", Body=body)
        assert s3.get_object(Bucket=bucket, Key="hello.txt")["Body"].read() == body
        s3.delete_object(Bucket=bucket, Key="hello.txt")
        assert s3.list_objects_v2(Bucket=bucket).get("KeyCount", 0) == 0
    finally:
        s3.delete_bucket(Bucket=bucket)
