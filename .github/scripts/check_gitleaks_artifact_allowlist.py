"""Exercise the exact artifact-digest exception without suppressing other keys."""

from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gitleaks", type=Path, required=True)
    args = parser.parse_args()
    scanner = args.gitleaks.resolve()
    root = Path(__file__).resolve().parents[2]
    artifact_path = "spikes/dsh-harness/artifacts.json"
    artifact = json.loads((root / artifact_path).read_text())
    module_path = "deepseek_harness/api.py"
    digest = artifact["installed_sha256"][module_path]
    line = "    " + json.dumps(module_path) + ": " + json.dumps(digest) + ","
    changed = ("0" if digest[0] != "0" else "1") + digest[1:]
    key_line = 'api_key = "' + secrets.token_urlsafe(32) + '"'
    with tempfile.TemporaryDirectory(prefix="gitleaks-artifact-canary-") as scratch:
        directory = Path(scratch)
        target = directory / artifact_path
        target.parent.mkdir(parents=True)
        target.write_text(
            "\n".join((line, key_line, line + " " + key_line, line.replace(digest, changed))) + "\n"
        )
        other = directory / "other/notes.md"
        other.parent.mkdir()
        other.write_text(line + "\n")
        sibling_path = "spikes/dsh-harness/notes.md"
        (directory / sibling_path).write_text(line + "\n")
        report = directory / "report.json"
        result = subprocess.run(
            [
                str(scanner),
                "dir",
                "--config",
                str(root / ".gitleaks.toml"),
                "--redact",
                "--report-format",
                "json",
                "--report-path",
                str(report),
                ".",
            ],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 1 or not report.is_file():
            raise SystemExit("artifact canary failed: scanner did not report expected findings")
        observed = {
            (row["File"], row["StartLine"], row["RuleID"]) for row in json.loads(report.read_text())
        }
        expected = {(artifact_path, number, "generic-api-key") for number in (2, 3, 4)}
        expected.add(("other/notes.md", 1, "generic-api-key"))
        expected.add((sibling_path, 1, "generic-api-key"))
        if observed != expected:
            raise SystemExit("artifact canary failed: exact path/line/digest restrictions changed")
    print(
        "artifact canary passed: exact digest suppressed; "
        "changed digest, added keys and other path detected"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
