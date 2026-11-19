"""Run the fake model as a process (for worker containers)."""

from __future__ import annotations

import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path

from tests.support.fake_model import FakeModelState, _handler, load_scripts

parser = argparse.ArgumentParser()
parser.add_argument("--script", required=True)
parser.add_argument("--host", default="0.0.0.0")
parser.add_argument("--port", type=int, default=8765)
args = parser.parse_args()
state = FakeModelState(load_scripts(Path(args.script)))
server = ThreadingHTTPServer((args.host, args.port), _handler(state))
server.daemon_threads = True
server.serve_forever()
