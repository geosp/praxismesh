"""Make the repository's tooling scripts importable in tests.

`.agents/sync_agents.py` imports as `sync_agents`; `.github/scripts/ci_gate.py`
imports as `ci_gate`.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for script_dir in (ROOT / ".agents", ROOT / ".github" / "scripts"):
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
