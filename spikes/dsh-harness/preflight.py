"""Verify staged bytes without importing or executing the candidate SDK."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(site: Path | None = None) -> dict:
    manifest = json.loads((HERE / "artifacts.json").read_text())
    if (
        sys.version_info[:2] != (3, 11)
        or platform.system() != "Linux"
        or platform.machine() != "x86_64"
    ):
        raise RuntimeError("blocked: this probe requires Linux x86_64 and Python 3.11")
    site = site or HERE / ".venv/lib/python3.11/site-packages"
    for name, expected in manifest["installed_sha256"].items():
        path = site / name
        if not path.is_file() or digest(path) != expected:
            raise RuntimeError("blocked: missing or mismatched artifact: " + name)
    return {
        "artifact_manifest_sha256": digest(HERE / "artifacts.json"),
        "lock_sha256": digest(HERE / "uv.lock"),
        "composition_sha256": digest(HERE / "composition.yaml"),
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
