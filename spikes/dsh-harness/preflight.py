"""Verify staged bytes without importing or executing the candidate SDK."""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def environment_digest(site: Path) -> str:
    entries = []
    for path in sorted(site.rglob("*")):
        if path.is_symlink():
            raise RuntimeError("blocked: environment contains a symlink")
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.is_file():
            if path.name == "RECORD" and path.parent.name.endswith(".dist-info"):
                # uv records hashes of launcher shebangs outside site-packages.
                # Those launchers are never mounted. Retain every in-tree row;
                # independently hash all executable in-tree bytes below/above.
                rows = [
                    row
                    for row in csv.reader(path.read_text().splitlines())
                    if row and not row[0].startswith("../")
                ]
                value = hashlib.sha256(json.dumps(sorted(rows)).encode()).hexdigest()
            else:
                value = digest(path)
            entries.append([path.relative_to(site).as_posix(), value])
    return hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode()).hexdigest()


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
    actual_environment = environment_digest(site)
    if actual_environment != manifest["environment_sha256"]:
        raise RuntimeError("blocked: executable dependency environment mismatch")
    return {
        "artifact_manifest_sha256": digest(HERE / "artifacts.json"),
        "lock_sha256": digest(HERE / "uv.lock"),
        "composition_sha256": digest(HERE / "composition.yaml"),
        "environment_sha256": actual_environment,
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
