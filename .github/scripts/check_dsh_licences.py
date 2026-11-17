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


def shown(path: Path) -> str:
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def read_pins(requirements: Path = REQUIREMENTS) -> tuple[list[str], list[str]]:
    """`<name>-<version>` for each pinned distribution (names normalised), and
    the requirement lines that are not `name==version` pins. Indented lines are
    hash and `# via` continuations of the pin above them."""
    found, unreadable = [], []
    for line in requirements.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith((" ", "\t", "#")):
            continue
        if match := PIN.match(line):
            found.append(f"{normalise(match[1])}-{match[2]}")
        else:
            unreadable.append(line.rstrip(" \\"))
    return sorted(found), unreadable


def pinned(requirements: Path = REQUIREMENTS) -> list[str]:
    """`<name>-<version>` for each pinned distribution, names normalised."""
    return read_pins(requirements)[0]


def check(requirements: Path = REQUIREMENTS, notices: Path = NOTICES) -> list[str]:
    """Problems found; empty when every pin has notices and nothing is stale."""
    wanted, unreadable = read_pins(requirements)
    errors = [
        f"{line}: not a name==version pin, so its notices cannot be checked" for line in unreadable
    ]
    if not wanted:
        return [*errors, f"{requirements} pins no distribution"]
    have = {p.name for p in notices.iterdir() if p.is_dir()} if notices.is_dir() else set()
    for dist in wanted:
        directory = notices / dist
        if dist not in have:
            errors.append(f"{dist}: no licence notices in {shown(directory)}")
        elif not any(f.is_file() and f.stat().st_size for f in directory.rglob("*")):
            errors.append(f"{dist}: {shown(directory)} has no notice file")
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
        replace_notices(Path(tmp) / Path(SITE).name)
    print(f"exported notices for {len(pinned())} distributions to {NOTICES.relative_to(ROOT)}")


def replace_notices(site: Path, requirements: Path = REQUIREMENTS, notices: Path = NOTICES) -> None:
    """Replace `notices` with each pin's licence files from `site`, an installed
    site-packages tree. Nothing changes unless every pin has them."""
    infos = {}
    for d in site.glob("*.dist-info"):
        name, version = d.name.removesuffix(".dist-info").split("-", 1)
        infos[f"{normalise(name)}-{version}"] = d
    missing = [
        d for d in pinned(requirements) if d not in infos or not (infos[d] / "licenses").is_dir()
    ]
    if missing:
        raise SystemExit(f"no dist-info/licenses in the DSH image for: {', '.join(missing)}")
    staging = notices.with_name(notices.name + ".new")
    shutil.rmtree(staging, ignore_errors=True)
    for dist in pinned(requirements):
        shutil.copytree(infos[dist] / "licenses", staging / dist)
    shutil.rmtree(notices, ignore_errors=True)
    staging.rename(notices)


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
