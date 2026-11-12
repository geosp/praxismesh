"""`BlobRef`: a backend-independent reference to stored bytes (plan §5)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from common.schemas.base import RetentionClass, Strict


class BlobRef(Strict):
    schema_version: Literal[1] = 1
    id: str
    key: str
    checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    content_type: str
    bytes: int = Field(ge=0)
    retention_class: RetentionClass
    created_at: datetime
