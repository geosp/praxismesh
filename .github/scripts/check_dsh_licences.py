"""Check that every distribution pinned for the DSH container has its licence
notices in the repository (DSH migration plan R20, ADR-0005 condition 1).

    uv run .github/scripts/check_dsh_licences.py            # the CI check
    uv run .github/scripts/check_dsh_licences.py export     # refresh after a pin change

Each `name==version` in infra/dsh/requirements.txt needs a non-empty directory
docs/licences/dsh/<name>-<version>/ holding the licence files its wheel ships
(`*.dist-info/licenses/`). A directory for a distribution no longer pinned is
an error too, so notices follow the pins. `export` copies the files out of the
built DSH image (needs docker).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ROOT / "infra" / "dsh" / "requirements.txt"
NOTICES = ROOT / "docs" / "licences" / "dsh"
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s\\;]+)")
SITE = "/opt/dsh/site"


def normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def pinned(requirements: Path = REQUIREMENTS) -> list[str]:
    """`<name>-<version>` for each pinned distribution, names normalised."""
    found = []
    for line in requirements.read_text(encoding="utf-8").splitlines():
        if match := PIN.match(line):
            found.append(f"{normalise(match[1])}-{match[2]}")
    return sorted(found)


def check(requirements: Path = REQUIREMENTS, notices: Path = NOTICES) -> list[str]:
    """Problems found; empty when every pin has notices and nothing is stale."""
    wanted = pinned(requirements)
    if not wanted:
        return [f"{requirements} pins no distribution"]
    have = {p.name for p in notices.iterdir() if p.is_dir()} if notices.is_dir() else set()
    errors = []
    for dist in wanted:
        directory = notices / dist
        if dist not in have:
            errors.append(f"{dist}: no licence notices in {directory.relative_to(ROOT)}")
        elif not any(f.is_file() and f.stat().st_size for f in directory.rglob("*")):
            errors.append(f"{dist}: {directory.relative_to(ROOT)} has no notice file")
    for stale in sorted(have - set(wanted)):
        errors.append(f"{stale}: notices for a distribution that is no longer pinned")
    return errors


def export() -> None:
    """Replace docs/licences/dsh/ with the licence files from the DSH image."""
    image = subprocess.run(
        ["docker", "build", "-q", "-f", "infra/dsh/Dockerfile", "infra/dsh"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    with tempfile.TemporaryDirectory() as tmp:
        container = subprocess.run(
            ["docker", "create", image], capture_output=True, text=True, check=True
        ).stdout.strip()
        try:
            subprocess.run(["docker", "cp", f"{container}:{SITE}", tmp], check=True)
        finally:
            subprocess.run(["docker", "rm", container], capture_output=True, check=False)
        site = Path(tmp) / Path(SITE).name
        shutil.rmtree(NOTICES, ignore_errors=True)
        infos = {}
        for d in site.glob("*.dist-info"):
            name, version = d.name.removesuffix(".dist-info").split("-", 1)
            infos[f"{normalise(name)}-{version}"] = d
        for dist in pinned():
            info = infos.get(dist)
            if info is None or not (info / "licenses").is_dir():
                raise SystemExit(f"{dist}: no dist-info/licenses in the DSH image")
            shutil.copytree(info / "licenses", NOTICES / dist)
    print(f"exported notices for {len(pinned())} distributions to {NOTICES.relative_to(ROOT)}")


def main(argv: list[str]) -> int:
    if argv == ["export"]:
        export()
    elif argv:
        print(__doc__, file=sys.stderr)
        return 2
    errors = check()
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        print("refresh with: uv run .github/scripts/check_dsh_licences.py export", file=sys.stderr)
        return 1
    print(f"licence notices present for {len(pinned())} pinned DSH distributions")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
