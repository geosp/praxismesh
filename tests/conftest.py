"""Make `.agents/sync_agents.py` importable as `sync_agents` in tests."""

import sys
from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parent.parent / ".agents"
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))
import os  # deliberate lint error for the bootstrap demo (unused import)
