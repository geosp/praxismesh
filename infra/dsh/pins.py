"""DSH runtime pins (DSH migration plan R17).

`requirements_digest` is the SHA-256 of the normalized hash-pinned requirements
(every `name==version` with its sorted allowed wheel hashes). The registry lock
records it (`registry/lock.py` computes the same value), and the launcher reports
it with an integrity result: every installed file of the pinned distributions must
match its wheel's RECORD hash, so a changed native binary is caught.

Standard library only; runs at image build (`python pins.py build`) and inside
the launcher.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import os
import re
import sys
from pathlib import Path

SITE = Path(os.environ.get("DSH_SITE", "/opt/dsh/site"))
PINS = Path(os.environ.get("DSH_PINS", "/opt/dsh/pins.json"))


def normalized_requirements(text: str) -> list[str]:
    """`name==version sha256:...` lines, sorted, from a uv-exported requirements file."""
    entries: dict[str, list[str]] = {}
    current = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip().rstrip("\\").strip()
        if not line:
            continue
        if not line.startswith("--hash="):
            current = line.split(";", 1)[0].strip().lower()
            entries[current] = []
        elif current is not None:
            entries[current].append(line.removeprefix("--hash="))
    return sorted(f"{name} {' '.join(sorted(hashes))}" for name, hashes in entries.items())


def requirements_digest(text: str) -> str:
    body = "\n".join(normalized_requirements(text)) + "\n"
    return "sha256:" + hashlib.sha256(body.encode()).hexdigest()


def _dist_infos(site: Path, names: list[str]) -> list[Path]:
    wanted = {re.sub(r"[-_.]+", "_", n.split("==")[0]).lower() for n in names}
    found = [
        d
        for d in site.glob("*.dist-info")
        if re.sub(r"[-_.]+", "_", d.name.removesuffix(".dist-info").rsplit("-", 1)[0]).lower()
        in wanted
    ]
    if len(found) != len(wanted):
        raise RuntimeError("pinned distribution missing from the image")
    return sorted(found)


def verify_installed(site: Path, names: list[str]) -> list[str]:
    """Files whose bytes differ from their RECORD hash (empty when intact)."""
    mismatches = []
    for info in _dist_infos(site, names):
        for row in csv.reader((info / "RECORD").read_text().splitlines()):
            if len(row) < 2 or not row[1]:
                continue  # RECORD itself, and files recorded without a hash
            algorithm, _, expected = row[1].partition("=")
            if algorithm != "sha256":
                mismatches.append(row[0])
                continue
            path = (site / row[0]).resolve()
            if not path.is_relative_to(site.resolve()):
                continue  # launcher scripts outside the site directory
            if not path.is_file():
                mismatches.append(row[0])
                continue
            digest = base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest())
            if digest.rstrip(b"=").decode() != expected:
                mismatches.append(row[0])
    return mismatches


def report() -> dict[str, object]:
    pins = json.loads(PINS.read_text())
    mismatches = verify_installed(SITE, pins["packages"])
    return {
        "requirements_digest": pins["requirements_digest"],
        "packages": pins["packages"],
        "integrity": "ok" if not mismatches else "mismatch",
        "mismatches": mismatches[:20],
    }


def build(requirements: Path) -> None:
    text = requirements.read_text()
    packages = [line.split()[0] for line in normalized_requirements(text)]
    if verify_installed(SITE, packages):
        raise SystemExit("installed files do not match their wheels")
    PINS.write_text(
        json.dumps(
            {"requirements_digest": requirements_digest(text), "packages": packages}, indent=2
        )
        + "\n"
    )


if __name__ == "__main__":
    build(Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/opt/dsh/requirements.txt"))
