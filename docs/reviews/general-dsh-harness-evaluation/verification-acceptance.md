# Independent Phase 01 acceptance verification

Verdict: **PASS for Phase 01 acceptance and demo in the frozen checkout.** Initial environmental restrictions and ancillary scope/helper failures remain recorded below; they are not converted into successful first attempts. No Phase 02 recovery, cancellation, token-admission, result-contract or benchmark acceptance is established.

Frozen code: `65d03f0fdb56d8939e99d67156ddea398185a21f`. Checkout: `/tmp/praxismesh-dsh-verify-65d03f0`. Executed 2026-11-15 UTC (host local date 2026-11-14). Requirements read: AGENTS.md, PROJECT_PLAN.md, contract plan/notes/Phase 01, spike README. Front-matter review metadata was disclose-only. Earlier reports, result records and transcripts were not consulted.

Environment: Linux x86_64, glibc 2.43, uv 0.13.5, Docker 29.9.3; locked root and spike environments selected CPython 3.11.17 despite system Python 3.14.10. `UV_CACHE_DIR=/tmp/praxismesh-skill-audit-cache` applied to every recorded command. Candidate imports/native startup ran in the documented disposable Docker environment.

## Requirement results

| Requirement | Result | Observed evidence |
| --- | --- | --- |
| R1 / task 1.1 | PASS | Locked setup and complete preflight hashes; startup initialized; private snapshot manifests identify frozen source/image/digests. |
| R2 / task 1.2 | PASS | First local attempt: 2 HTTP 200 spark requests, skill body observed, lookup_price and lookup_stock admitted, quote_matches true. |
| R3 / task 1.2 | PASS | Poison invisible in every boundary request; introduced forbidden operation rejected; denied tool and native-shaped text each produced denial with zero fixture executions and unchanged policy/catalog. |
| R10 / task 1.3 execution scope | PASS | Manifest inventory disables delegation/jobs/title/compaction/resource/image paths; bounded controlled probe, no Temporal Activity launched or production orchestration changed. Full accounting remains Phase 02. |

Root checks passed: 165 selected pytest tests, lint, formatting, mypy, agent sync and plan validation. Spike tests passed 30/30 after authorized socket access. Actionlint, frozen-ancestry secret scan, artifact/scoped canaries and committed Markdown link checks passed. 91 integration tests are intentionally deselected by root configuration; no production stack deployment was run for this isolated Phase 01 scope. GitHub hosted dependency-review is not reproduced by these local checks.

## Failure, diagnostic and recovery record

- Initial Docker pull returned `permission denied ... unix:///var/run/docker.sock`; authorized daemon access resolved this prerequisite. Initial spike regression produced 28 passes and two `PermissionError: [Errno 1] Operation not permitted` socket failures. Authorized rerun passed all 30.
- Initial root pytest stopped making progress at test_hello_replay under restricted sandbox. After 122.2 seconds the verifier sent SIGINT then SIGTERM to exact owned PID 1104437; exit 143, captured output preserved. The isolated replay diagnostic outside sandbox passed in 0.18s; the authorized complete root suite then passed 165 tests in 32.02s. This is an environment differential, not evidence that the first run passed.
- Initial gitleaks default scan visited 163 commits across local references and found one redacted historical finding at .github/workflows/ci.yml:161 in commit bc7fe4889d85cf3059f2a5a9676fb1ccb5738c3c. The exact frozen ancestry scan visited 60 commits and found none; contract-base..frozen scan visited 13 and found none. No secret value is needed for this scope diagnosis.
- The documented offline link glob was run while startup held its private dependency snapshot; it included ignored .runs third-party notices and failed 21 missing upstream paths. Committed Markdown check passed 0 errors. The initial glob failure is retained as a reproducibility caveat for checking during active probes.
- Scratch canary observer initially compared duplicate findings without the CI unique normalization. Correcting only .verify/acceptance-canaries to deduplicate exactly as CI specifies passed the canaries. Scratch cleanup observer initially matched its own enclosing shell text. Correcting only .verify/acceptance-cleanup to match executable arguments yielded no remaining owned processes. Both failed verifier-helper observations are preserved.
- No source, test or documentation files were modified. No source failure path was temporarily altered. Docker image ID output was moved from the README global /tmp path to .verify/acceptance-image-id to avoid collision; command otherwise unchanged. No service teardown required forced recovery; documented normal controller cleanup succeeded for every demo.

## Exact automated commands and observations

### environment: PASS

Command: `git rev-parse HEAD; uname -sm; getconf GNU_LIBC_VERSION; uv --version; python3 --version; docker --version`

Expected: Frozen SHA 65d03f0fdb56d8939e99d67156ddea398185a21f; Linux x86_64, glibc >=2.28; uv and Docker available. Python 3.11 selected by locked setup.

Observed: exit **0**, 0.017 seconds, 2026-11-15T02:51:31.919541+00:00.

```text
65d03f0fdb56d8939e99d67156ddea398185a21f
Linux x86_64
glibc 2.43
uv 0.13.5 (x86_64-unknown-linux-gnu)
Python 3.14.10
Docker version 29.9.3, build 5457199
```

Raw: `raw/acceptance-environment.json`.

### root-sync: PASS

Command: `uv sync --locked`

Expected: Exit 0; locked production dependency environment resolves.

Observed: exit **0**, 0.054 seconds, 2026-11-15T02:51:31.991040+00:00.

```text
Using CPython 3.11.17 interpreter at: /home/geo/.local/bin/python3.11
Creating virtual environment at: .venv
Resolved 90 packages in 1ms
Installed 86 packages in 31ms
 + alembic==1.20.1
 + annotated-types==0.8.0
 + anyio==4.16.0
 + ast-serialize==0.13.1
 + asyncpg==0.32.0
 + attrs==26.1.0
 + boto3==1.44.0
 + boto3-stubs==1.44.0
 + botocore==1.44.0
 + botocore-stubs==1.43.126
 + certifi==2026.10.23
 + cffi==2.1.1
 + charset-normalizer==3.5.2
 + click==8.5.1
 + cryptography==50.0.2
 + googleapis-common-protos==1.76.0
 + greenlet==3.5.6
 + griffelib==2.4.1
 + grpcio==1.85.1
 + h11==0.16.0
 + httpcore==1.0.9
 + httpcore2==2.16.0
 + httpx==0.28.1
 + httpx2==2.16.0
 + idna==3.20
 + iniconfig==2.3.1
 + jiter==0.19.0
 + jmespath==1.1.0
 + jsonschema==4.26.0
 + jsonschema-specifications==2025.9.1
 + librt==0.16.0
 + mako==1.4.3
 + markupsafe==3.0.4
 + mcp==2.3.0
 + mcp-types==2.3.0
 + mypy==2.4.1
 + mypy-boto3-s3==1.44.0
 + mypy-extensions==1.2.0
 + nexus-rpc==1.5.0
 + openai==3.49.0
 + openai-agents==0.24.0
 + opentelemetry-api==1.45.2
 + opentelemetry-exporter-http-transport==0.66b2
 + opentelemetry-exporter-otlp==1.45.2
 + opentelemetry-exporter-otlp-common==0.66b2
 + opentelemetry-exporter-otlp-proto-common==1.45.2
 + opentelemetry-exporter-otlp-proto-grpc==1.45.2
 + opentelemetry-exporter-otlp-proto-http==1.45.2
 + opentelemetry-proto==1.45.2
 + opentelemetry-sdk==1.45.2
 + opentelemetry-semantic-conventions==0.66b2
 + packaging==26.3
 + pathspec==1.1.1
 + pluggy==1.7.0
 + prometheus-client==0.26.0
 + protobuf==7.36.2
 + pycparser==3.12
 + pydantic==2.14.3
 + pydantic-core==2.50.4
 + pygments==2.21.0
 + pyjwt==2.15.1
 + pytest==9.2.0
 + pytest-asyncio==1.4.1.post1
 + python-dateutil==2.9.0.post0
 + python-multipart==0.0.33
 + pyyaml==6.0.3
 + referencing==0.37.0
 + requests==2.34.2
 + rpds-py==2026.9.1
 + ruff==0.17.4
 + s3transfer==0.19.3
 + six==1.17.0
 + sniffio==1.3.1
 + sqlalchemy==2.1.8
 + sse-starlette==3.7.0
 + starlette==1.10.0
 + temporalio==1.36.0
 + truststore==0.10.5
 + types-protobuf==7.35.1.20260906
 + types-pyyaml==6.0.12.20261103
 + types-s3transfer==0.19.3
 + typing-extensions==4.16.0
 + typing-inspection==0.4.5
 + urllib3==2.8.0
 + uvicorn==0.54.0
 + websockets==16.1.1
```

Raw: `raw/acceptance-root-sync.json`.

### spike-sync: PASS

Command: `uv sync --project spikes/dsh-harness --locked --python 3.11`

Expected: Exit 0; separate Python 3.11 locked SDK/runtime environment resolves.

Observed: exit **0**, 0.015 seconds, 2026-11-15T02:51:32.025748+00:00.

```text
Using CPython 3.11.17 interpreter at: /home/geo/.local/bin/python3.11
Creating virtual environment at: spikes/dsh-harness/.venv
Resolved 15 packages in 1ms
Installed 13 packages in 4ms
 + annotated-types==0.8.0
 + deepseek-harness-runtime-bin==0.2.2rc2
 + deepseek-harness-sdk==0.2.2rc2
 + iniconfig==2.3.1
 + packaging==26.3
 + pluggy==1.7.0
 + pydantic==2.14.3
 + pydantic-core==2.50.4
 + pygments==2.21.0
 + pytest==9.2.0
 + pyyaml==6.0.3
 + typing-extensions==4.16.0
 + typing-inspection==0.4.5
```

Raw: `raw/acceptance-spike-sync.json`.

### preflight: PASS

Command: `spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/preflight.py`

Expected: Exit 0; complete artifact/environment/composition/lock hashes reported without mismatch.

Observed: exit **0**, 0.372 seconds, 2026-11-15T02:51:38.075088+00:00.

```text
{
  "artifact_manifest_sha256": "881c464387a3e872c98a96eed4e018e6ced6c709a3206f1a13322dc727f61730",
  "lock_sha256": "f82a3f6bacf9f1aaace9cd4d97ec8638bd7ab2ab9403c444abae14b62b807597",
  "composition_sha256": "8609f86ba37530e145f9e8efe8103748ed9bc2856d213f83bcb945fcf18e8dad",
  "environment_sha256": "c581df47358cb4972ea951c6ffe715b5d0218a702c5c9311d93d9ab47f2fa421"
}
```

Raw: `raw/acceptance-preflight.json`.

### root-ruff: PASS

Command: `uv run ruff check .`

Expected: Exit 0; no lint errors.

Observed: exit **0**, 0.101 seconds, 2026-11-15T02:51:37.806279+00:00.

```text
All checks passed!
```

Raw: `raw/acceptance-root-ruff.json`.

### root-format: PASS

Command: `uv run ruff format --check .`

Expected: Exit 0; all files formatted.

Observed: exit **0**, 0.087 seconds, 2026-11-15T02:51:37.766200+00:00.

```text
258 files already formatted
```

Raw: `raw/acceptance-root-format.json`.

### root-mypy: PASS

Command: `uv run mypy`

Expected: Exit 0; no typing issues.

Observed: exit **0**, 11.316 seconds, 2026-11-15T02:51:49.011027+00:00.

```text
Success: no issues found in 90 source files
```

Raw: `raw/acceptance-root-mypy.json`.

### root-pytest: BLOCKED (sandbox replay stall; interrupted after 122.2s)

Command: `uv run pytest`

Expected: Exit 0; all 165 selected root tests pass.

Observed: exit **143**, 122.2 seconds, 2026-11-15T02:53:39.879000+00:00.

```text
============================= test session starts ==============================
platform linux -- Python 3.11.17, pytest-9.2.0, pluggy-1.7.0
rootdir: /tmp/praxismesh-dsh-verify-65d03f0
configfile: pyproject.toml
testpaths: tests
plugins: asyncio-1.4.1.post1, anyio-4.16.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collected 256 items / 91 deselected / 165 selected

tests/test_benchmark_report.py ..                                        [  1%]
tests/test_blob_store_memory.py .........                                [  6%]
tests/test_ci_gate.py .................................................  [ 36%]
tests/test_cli.py .                                                      [ 36%]
tests/test_hello_replay.py
```

Raw: `raw/acceptance-root-pytest.json`.

### root-replay-diagnostic: PASS

Command: `timeout 30 uv run pytest tests/test_hello_replay.py -vv -s`

Expected: Exit 0 within 30 seconds; scoped replay diagnostic establishes execution outside sandbox restrictions.

Observed: exit **0**, 0.363 seconds, 2026-11-15T02:53:59.935265+00:00.

```text
============================= test session starts ==============================
platform linux -- Python 3.11.17, pytest-9.2.0, pluggy-1.7.0 -- /tmp/praxismesh-dsh-verify-65d03f0/.venv/bin/python
cachedir: .pytest_cache
rootdir: /tmp/praxismesh-dsh-verify-65d03f0
configfile: pyproject.toml
plugins: asyncio-1.4.1.post1, anyio-4.16.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 1 item

tests/test_hello_replay.py::test_hello_replay PASSED

============================== 1 passed in 0.18s ===============================
```

Raw: `raw/acceptance-root-replay-diagnostic.json`.

### root-pytest-authorized: PASS

Command: `uv run pytest`

Expected: Exit 0; all selected root tests pass.

Observed: exit **0**, 32.926 seconds, 2026-11-15T02:54:39.853312+00:00.

```text
============================= test session starts ==============================
platform linux -- Python 3.11.17, pytest-9.2.0, pluggy-1.7.0
rootdir: /tmp/praxismesh-dsh-verify-65d03f0
configfile: pyproject.toml
testpaths: tests
plugins: asyncio-1.4.1.post1, anyio-4.16.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collected 256 items / 91 deselected / 165 selected

tests/test_benchmark_report.py ..                                        [  1%]
tests/test_blob_store_memory.py .........                                [  6%]
tests/test_ci_gate.py .................................................  [ 36%]
tests/test_cli.py .                                                      [ 36%]
tests/test_hello_replay.py .                                             [ 37%]
tests/test_observability.py ...                                          [ 39%]
tests/test_plans.py .........                                            [ 44%]
tests/test_registry.py ...................                               [ 56%]
tests/test_runner_conformance.py ..................                      [ 67%]
tests/test_submit.py ....                                                [ 69%]
tests/test_sync_agents.py ................................               [ 89%]
tests/test_task_workflow.py .............                                [ 96%]
tests/test_tool_pins.py .                                                [ 97%]
tests/test_workspace.py ....                                             [100%]

===================== 165 passed, 91 deselected in 32.02s ======================
```

Raw: `raw/acceptance-root-pytest-authorized.json`.

### root-sync-agents: PASS

Command: `uv run .agents/sync_agents.py --check`

Expected: Exit 0; generated agent files current.

Observed: exit **0**, 0.128 seconds, 2026-11-15T02:51:37.829661+00:00.

```text
Installed 1 package in 2ms
ok: 3 generated agent file(s) up to date
```

Raw: `raw/acceptance-root-sync-agents.json`.

### root-plans: PASS

Command: `uv run .github/scripts/check_plans.py`

Expected: Exit 0; implementation plans validate.

Observed: exit **0**, 0.14 seconds, 2026-11-15T02:51:37.827549+00:00.

```text
Validated 3 implementation plan(s); 0 error(s)
```

Raw: `raw/acceptance-root-plans.json`.

### spike-tests: BLOCKED (sandbox sockets; 28 passed, two permission errors)

Command: `spikes/dsh-harness/.venv/bin/python -m pytest -c spikes/dsh-harness/pyproject.toml spikes/dsh-harness/test_probe.py spikes/dsh-harness/test_corrections.py spikes/dsh-harness/test_final_corrections.py -q`

Expected: Exit 0; all isolated automated acceptance/regression tests pass.

Observed: exit **1**, 1.356 seconds, 2026-11-15T02:51:39.061034+00:00.

```text
..............F.....F.........                                           [100%]
=================================== FAILURES ===================================
_____ test_gateway_rejects_alternate_routes_and_enforces_admission_ceiling _____

tmp_path = PosixPath('/tmp/pytest-of-geo/pytest-91/test_gateway_rejects_alternate0')

    def test_gateway_rejects_alternate_routes_and_enforces_admission_ceiling(tmp_path):
>       boundary = Boundary(tmp_path / "model.sock", "catalog")
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

spikes/dsh-harness/test_probe.py:121: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
spikes/dsh-harness/model_gateway.py:221: in __init__
    self.server = Server(str(path), Handler)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^
/home/geo/.local/share/uv/python/cpython-3.11.17-linux-x86_64-gnu/lib/python3.11/socketserver.py:456: in __init__
    self.server_bind()
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <model_gateway.Boundary.__init__.<locals>.Server object at 0x7fd9916cfa10>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

/home/geo/.local/share/uv/python/cpython-3.11.17-linux-x86_64-gnu/lib/python3.11/socketserver.py:472: PermissionError
_____________ test_gateway_shutdown_joins_stalled_provider_handler _____________

tmp_path = PosixPath('/tmp/pytest-of-geo/pytest-91/test_gateway_shutdown_joins_st0')

    def test_gateway_shutdown_joins_stalled_provider_handler(tmp_path):
        import http.server
    
        entered = threading.Event()
        release = threading.Event()
    
        class Stalled(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                entered.set()
                release.wait(5)
    
            def log_message(self, *args):
                pass
    
>       provider = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Stalled)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

spikes/dsh-harness/test_corrections.py:107: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/home/geo/.local/share/uv/python/cpython-3.11.17-linux-x86_64-gnu/lib/python3.11/socketserver.py:452: in __init__
    self.socket = socket.socket(self.address_family,
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <socket.socket fd=-1, family=0, type=0, proto=0>
family = <AddressFamily.AF_INET: 2>, type = <SocketKind.SOCK_STREAM: 1>
proto = 0, fileno = None

    def __init__(self, family=-1, type=-1, proto=-1, fileno=None):
        # For user code address family and type values are IntEnum members, but
        # for the underlying _socket.socket they're just integers. The
        # constructor of _socket.socket converts the given argument to an
        # integer automatically.
        if fileno is None:
            if family == -1:
                family = AF_INET
            if type == -1:
                type = SOCK_STREAM
            if proto == -1:
                proto = 0
>       _socket.socket.__init__(self, family, type, proto, fileno)
E       PermissionError: [Errno 1] Operation not permitted

/home/geo/.local/share/uv/python/cpython-3.11.17-linux-x86_64-gnu/lib/python3.11/socket.py:232: PermissionError
=========================== short test summary info ============================
FAILED spikes/dsh-harness/test_probe.py::test_gateway_rejects_alternate_routes_and_enforces_admission_ceiling
FAILED spikes/dsh-harness/test_corrections.py::test_gateway_shutdown_joins_stalled_provider_handler
2 failed, 28 passed in 1.04s
```

Raw: `raw/acceptance-spike-tests.json`.

### spike-tests-authorized: PASS

Command: `spikes/dsh-harness/.venv/bin/python -m pytest -c spikes/dsh-harness/pyproject.toml spikes/dsh-harness/test_probe.py spikes/dsh-harness/test_corrections.py spikes/dsh-harness/test_final_corrections.py -q`

Expected: Exit 0; all 30 isolated automated tests pass.

Observed: exit **0**, 2.067 seconds, 2026-11-15T02:52:12.158964+00:00.

```text
..............................                                           [100%]
30 passed in 1.97s
```

Raw: `raw/acceptance-spike-tests-authorized.json`.

### spike-ruff: PASS

Command: `uv run ruff check --no-respect-gitignore --exclude '' spikes/dsh-harness/*.py`

Expected: Exit 0; isolated spike lint clean.

Observed: exit **0**, 0.084 seconds, 2026-11-15T02:51:37.768105+00:00.

```text
All checks passed!
```

Raw: `raw/acceptance-spike-ruff.json`.

### spike-format: PASS

Command: `uv run ruff format --check --no-respect-gitignore --exclude '' spikes/dsh-harness/*.py`

Expected: Exit 0; isolated spike formatting clean.

Observed: exit **0**, 0.091 seconds, 2026-11-15T02:51:37.789517+00:00.

```text
8 files already formatted
```

Raw: `raw/acceptance-spike-format.json`.

### docker-pull: BLOCKED (sandbox Docker socket)

Command: `docker pull python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39`

Expected: Exit 0; pinned base image available.

Observed: exit **1**, 0.019 seconds, 2026-11-15T02:51:41.646628+00:00.

```text
permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
```

Raw: `raw/acceptance-docker-pull.json`.

### docker-pull-authorized: PASS

Command: `docker pull python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39`

Expected: Exit 0; pinned base image available.

Observed: exit **0**, 0.75 seconds, 2026-11-15T02:51:48.702277+00:00.

```text
docker.io/library/python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39: Pulling from library/python
Digest: sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39
Status: Image is up to date for python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39
docker.io/library/python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39
```

Raw: `raw/acceptance-docker-pull-authorized.json`.

### docker-build: PASS

Command: `docker build --network none --build-arg SPIKE_UID="$(id -u)" --build-arg SPIKE_GID="$(id -g)" --iidfile .verify/acceptance-image-id spikes/dsh-harness`

Expected: Exit 0; isolated image built offline for unprivileged current UID/GID.

Observed: exit **0**, 0.195 seconds, 2026-11-15T02:51:57.810405+00:00.

```text
#0 building with "default" instance using docker driver

#1 [internal] load build definition from Dockerfile
#1 transferring dockerfile: 363B done
#1 DONE 0.0s

#2 [internal] load metadata for docker.io/library/python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39
#2 DONE 0.0s

#3 [internal] load .dockerignore
#3 transferring context: 2B done
#3 DONE 0.0s

#4 [1/2] FROM docker.io/library/python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39
#4 resolve docker.io/library/python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39 done
#4 DONE 0.0s

#5 [2/2] RUN groupadd --gid "1000" spike && useradd --uid "1000" --gid "1000" --create-home --shell /usr/sbin/nologin spike
#5 CACHED

#6 exporting to image
#6 exporting layers done
#6 exporting manifest sha256:3793b42db9ab9d0316dc70b6262c5e17d5940e0f53dda93179523aa762b45901 done
#6 exporting config sha256:c4303acca235a814081abc7078ef36e295b57284851aec7fe4ef3d3e3c37d2f5 done
#6 exporting attestation manifest sha256:6093b1c1b2a7b67c7edcf07ea6f2409eefc066b2303e5669b17dda14c0aaf2cf done
#6 exporting manifest list sha256:2c3b7f62f7757863ae2d75fdf05d751b32ba24cb06a5aea5251b2d79067f7f2d done
#6 naming to moby-dangling@sha256:2c3b7f62f7757863ae2d75fdf05d751b32ba24cb06a5aea5251b2d79067f7f2d done
#6 unpacking to moby-dangling@sha256:2c3b7f62f7757863ae2d75fdf05d751b32ba24cb06a5aea5251b2d79067f7f2d done
#6 DONE 0.0s
```

Raw: `raw/acceptance-docker-build.json`.

### actionlint: PASS

Command: `/tmp/praxismesh-migration-tools/actionlint -no-color`

Expected: Exit 0; GitHub workflows validate.

Observed: exit **0**, 0.005 seconds, 2026-11-15T02:52:20.240455+00:00.

```text
(no output)
```

Raw: `raw/acceptance-actionlint.json`.

### artifact-canary: PASS

Command: `uv run python .github/scripts/check_gitleaks_artifact_allowlist.py --gitleaks /tmp/praxismesh-migration-tools/gitleaks`

Expected: Exit 0; exact digest allowed, altered digest and unrelated keys detected.

Observed: exit **0**, 0.315 seconds, 2026-11-15T02:52:20.576651+00:00.

```text
artifact canary passed: exact digest suppressed; changed digest, added keys and other path detected
```

Raw: `raw/acceptance-artifact-canary.json`.

### gitleaks: FAIL in initial broader local-reference scope; frozen ancestry separately passes

Command: `/tmp/praxismesh-migration-tools/gitleaks git --config .gitleaks.toml --redact .`

Expected: Exit 0; no findings in all scanned local history. This initial default scope includes unrelated references.

Observed: exit **1**, 0.481 seconds, 2026-11-15T02:52:21.076484+00:00.

```text

    ○
    │╲
    │ ○
    ○ ░
    ░    gitleaks

9:52PM INF 163 commits scanned.
9:52PM INF scanned ~6047590 bytes (6.05 MB) in 310ms
9:52PM WRN leaks found: 1
```

Raw: `raw/acceptance-gitleaks.json`.

### gitleaks-diagnostic: DIAGNOSTIC

Command: `/tmp/praxismesh-migration-tools/gitleaks git --config .gitleaks.toml --redact --report-format json --report-path .verify/raw/acceptance-gitleaks-findings.json .`

Expected: Locate metadata of initial all-reference finding while redacting content.

Observed: exit **1**, 0.424 seconds, 2026-11-15T02:53:24.816410+00:00.

```text

    ○
    │╲
    │ ○
    ○ ░
    ░    gitleaks

9:53PM INF 163 commits scanned.
9:53PM INF scanned ~6047590 bytes (6.05 MB) in 253ms
9:53PM WRN leaks found: 1
```

Raw: `raw/acceptance-gitleaks-diagnostic.json`.

### gitleaks-range: PASS

Command: `/tmp/praxismesh-migration-tools/gitleaks git --config .gitleaks.toml --redact --log-opts=952d01e097332905ba56d6c26e1e342431f8f394..65d03f0fdb56d8939e99d67156ddea398185a21f .`

Expected: Exit 0; no findings in contract-base..frozen range.

Observed: exit **0**, 0.27 seconds, 2026-11-15T02:53:25.103912+00:00.

```text

    ○
    │╲
    │ ○
    ○ ░
    ░    gitleaks

9:53PM INF 13 commits scanned.
9:53PM INF scanned ~437042 bytes (437.04 KB) in 117ms
9:53PM INF no leaks found
```

Raw: `raw/acceptance-gitleaks-range.json`.

### gitleaks-frozen: PASS

Command: `/tmp/praxismesh-migration-tools/gitleaks git --config .gitleaks.toml --redact --log-opts=65d03f0fdb56d8939e99d67156ddea398185a21f .`

Expected: Exit 0; no findings in exact frozen commit ancestry.

Observed: exit **0**, 0.384 seconds, 2026-11-15T02:54:00.339179+00:00.

```text

    ○
    │╲
    │ ○
    ○ ░
    ░    gitleaks

9:54PM INF 60 commits scanned.
9:54PM INF scanned ~3392896 bytes (3.39 MB) in 203ms
9:54PM INF no leaks found
```

Raw: `raw/acceptance-gitleaks-frozen.json`.

### links: FAIL (generated .runs dependency notices included)

Command: `/tmp/praxismesh-migration-tools/lychee --offline --no-progress --include-fragments --hidden --exclude-path '\.claude/skills' --exclude-path '\.git/' --exclude-path '\.venv' './**/*.md'`

Expected: Exit 0; README/Markdown offline links and fragments resolve using documented glob.

Observed: exit **2**, 0.041 seconds, 2026-11-15T02:52:21.137253+00:00.

```text
Issues found in 1 input. Find details below.

[spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/THIRD_PARTY_NOTICES.md]:
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/.agents/notes/implemented/architecture/2026-09-14-independent-libreoffice-kit.md (at 199:392) | File not found. Check if file exists and path is correct
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/packages/experimental/inspector/assets/devtools/LICENSE (at 176:390) | File not found. Check if file exists and path is correct
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/patches/@botiverse__oar@0.67.0.patch (at 161:29) | File not found. Check if file exists and path is correct
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/patches/@earendil-works__pi-ai@1.3.0.patch (at 162:35) | File not found. Check if file exists and path is correct
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/patches/@electron__osx-sign@1.3.3.patch (at 163:32) | File not found. Check if file exists and path is correct
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/patches/@fortune-sheet__core@1.0.4.patch (at 164:33) | File not found. Check if file exists and path is correct
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/patches/@fortune-sheet__react@1.0.4.patch (at 165:34) | File not found. Check if file exists and path is correct
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/patches/@yao-pkg__pkg@6.21.0.patch (at 166:27) | File not found. Check if file exists and path is correct
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/pnpm-lock.yaml (at 10:123) | File not found. Check if file exists and path is correct
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/python/sdk/uv.lock (at 10:247) | File not found. Check if file exists and path is correct
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/scripts/primary-runtime/lock.json (at 303:5) | File not found. Check if file exists and path is correct
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/vendor/cordis (at 20:38) | File not found. Check if file exists and path is correct
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/vendor/cosmokit (at 18:42) | File not found. Check if file exists and path is correct
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/vendor/group (at 23:67) | File not found. Check if file exists and path is correct
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/vendor/hmr (at 25:63) | File not found. Check if file exists and path is correct
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/vendor/include (at 22:71) | File not found. Check if file exists and path is correct
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/vendor/loader (at 21:69) | File not found. Check if file exists and path is correct
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/vendor/logger-console (at 26:85) | File not found. Check if file exists and path is correct
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/vendor/README.md (at 14:310) | File not found. Check if file exists and path is correct
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/vendor/schemastery (at 19:48) | File not found. Check if file exists and path is correct
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58/environment/deepseek_harness_runtime_bin-0.2.2rc2.dist-info/licenses/vendor/timer (at 24:67) | File not found. Check if file exists and path is correct

🔍 642 Total (in 35ms) 🔗 433 Unique ✅ 314 OK 🚫 21 Errors 👻 307 Excluded
```

Raw: `raw/acceptance-links.json`.

### links-tracked: PASS

Command: `/tmp/praxismesh-migration-tools/lychee --offline --no-progress --include-fragments --hidden --exclude-path '\.claude/skills' --exclude-path '\.git/' --exclude-path '\.venv' $(git ls-files '*.md')`

Expected: Exit 0; committed Markdown offline links and fragments resolve, excluding generated private dependency snapshots.

Observed: exit **0**, 0.011 seconds, 2026-11-15T02:53:25.134084+00:00.

```text
🔍 384 Total (in 4ms) 🔗 226 Unique ✅ 313 OK 🚫 0 Errors 👻 71 Excluded
```

Raw: `raw/acceptance-links-tracked.json`.

### canaries: FAIL in verifier helper (missing unique normalization)

Command: `python3 .verify/acceptance-canaries`

Expected: Gitleaks must detect the exact three unique path/line/rule tuples; lychee must return exit 2 on a broken link.

Observed: exit **1**, 0.353 seconds, 2026-11-15T02:54:23.315574+00:00.

```text
scanner exit: 1 observed: [('docs/plan/schemas.md', 2, 'generic-api-key'), ('docs/roadmap/schemas.md', 2, 'generic-api-key'), ('other/notes.md', 1, 'generic-api-key'), ('other/notes.md', 1, 'generic-api-key')]
Traceback (most recent call last):
  File "/tmp/praxismesh-dsh-verify-65d03f0/.verify/acceptance-canaries", line 13, in <module>
    assert p.returncode==1 and observed==expected
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError
```

Raw: `raw/acceptance-canaries.json`.

### canaries-corrected: PASS

Command: `python3 .verify/acceptance-canaries`

Expected: Gitleaks must detect the exact three unique path/line/rule tuples; lychee must return exit 2 on a broken link.

Observed: exit **0**, 0.315 seconds, 2026-11-15T02:54:34.176054+00:00.

```text
scanner exit: 1 observed: [('docs/plan/schemas.md', 2, 'generic-api-key'), ('docs/roadmap/schemas.md', 2, 'generic-api-key'), ('other/notes.md', 1, 'generic-api-key')]
canary passed: both schema paths bounded; ordinary file detected
lychee canary exit: 2
Issues found in 1 input. Find details below.

[/tmp/praxismesh-dsh-verify-65d03f0/.verify/raw/acceptance-canary/link.md]:
[ERROR] file:///tmp/praxismesh-dsh-verify-65d03f0/.verify/raw/acceptance-canary/does-not-exist.md (at 1:1) | File not found. Check if file exists and path is correct

🔍 1 Total (in 0s) 🔗 1 Unique ✅ 0 OK 🚫 1 Error
```

Raw: `raw/acceptance-canaries-corrected.json`.

### cleanup: FAIL in verifier observer (self-matched enclosing shell)

Command: `python3 .verify/acceptance-cleanup`

Expected: Every owned named container absent (successful Docker listing); scratch directories absent; no owned gateway/probe processes.

Observed: exit **1**, 0.191 seconds, 2026-11-15T02:55:00.507783+00:00.

```text
capability praxis-dsh-6ad062897be1 docker_exit=0 listing='' scratch_exists=False
catalog praxis-dsh-5f675bc7026c docker_exit=0 listing='' scratch_exists=False
denied-tool praxis-dsh-edff2d92c9c4 docker_exit=0 listing='' scratch_exists=False
local praxis-dsh-c0910549ecc5 docker_exit=0 listing='' scratch_exists=False
native-text praxis-dsh-12e851ea2c6f docker_exit=0 listing='' scratch_exists=False
poison praxis-dsh-4efc7a9260af docker_exit=0 listing='' scratch_exists=False
startup praxis-dsh-add23ab3cc58 docker_exit=0 listing='' scratch_exists=False
remaining_owned_gateway_or_probe_processes=[{"pid": "1123911", "cmd": "/usr/bin/sh -c cat > .verify/acceptance-cleanup <<'PY'\nimport json,pathlib,subprocess,os\nroot=pathlib.Path.cwd(); rows=json.loads((root/'.verify/raw/acceptance-owned-manifests.json').read_text())\nfor row in sorted(rows,key=lambda r:r['case']):\n m=row['manifest']; name=m['run_id'];p=subprocess.run(['docker','ps','-a','--filter','name=^/'+name+'$','--format','{{.Names}}'],capture_output=True,text=True)\n print(row['case'],name,'docker_exit='+str(p.returncode),'listing='+repr(p.stdout),'scratch_exists='+str(pathlib.Path(m['scratch_directory']).exists()))\n assert p.returncode==0 and not p.stdout.strip() and not pathlib.Path(m['scratch_directory']).exists()\nours=[]\nfor entry in pathlib.Path('/proc').iterdir():\n if not entry.name.isdigit():continue\n try:\n  cmd=(entry/'cmdline').read_bytes().replace(b'\\0',b' ').decode(errors='replace')\n  cwd=os.readlink(entry/'cwd')\n except (OSError,PermissionError):continue\n if cwd==str(root) and ('run_probe.py' in cmd or 'model_gateway.py' in cmd):ours.append({'pid':entry.name,'cmd':cmd})\nprint('remaining_owned_gateway_or_probe_processes='+json.dumps(ours));assert not ours\nprint('PASS all seven named containers absent; disposable directories absent; no owned gateway/probe processes')\nPY\npython3 .verify/acceptance-run cleanup 'python3 .verify/acceptance-cleanup'\npython3 .verify/acceptance-run source-clean 'git status --short --untracked-files=no; git diff --exit-code; git diff --cached --exit-code' "}]
Traceback (most recent call last):
  File "/tmp/praxismesh-dsh-verify-65d03f0/.verify/acceptance-cleanup", line 15, in <module>
    print('remaining_owned_gateway_or_probe_processes='+json.dumps(ours));assert not ours
                                                                                 ^^^^^^^^
AssertionError
```

Raw: `raw/acceptance-cleanup.json`.

### cleanup-final: PASS

Command: `python3 .verify/acceptance-cleanup`

Expected: Every owned named container absent (successful Docker listing); scratch directories absent; no owned gateway/probe processes.

Observed: exit **0**, 0.108 seconds, 2026-11-15T02:55:14.848951+00:00.

```text
capability praxis-dsh-6ad062897be1 docker_exit=0 listing='' scratch_exists=False
catalog praxis-dsh-5f675bc7026c docker_exit=0 listing='' scratch_exists=False
denied-tool praxis-dsh-edff2d92c9c4 docker_exit=0 listing='' scratch_exists=False
local praxis-dsh-c0910549ecc5 docker_exit=0 listing='' scratch_exists=False
native-text praxis-dsh-12e851ea2c6f docker_exit=0 listing='' scratch_exists=False
poison praxis-dsh-4efc7a9260af docker_exit=0 listing='' scratch_exists=False
startup praxis-dsh-add23ab3cc58 docker_exit=0 listing='' scratch_exists=False
remaining_owned_gateway_or_probe_processes=[]
PASS all seven named containers absent; disposable directories absent; no owned gateway/probe processes
```

Raw: `raw/acceptance-cleanup-final.json`.

### source-clean: PASS

Command: `git status --short --untracked-files=no; git diff --exit-code; git diff --cached --exit-code`

Expected: Exit 0; no tracked modifications in working tree or index.

Observed: exit **0**, 0.013 seconds, 2026-11-15T02:55:00.542103+00:00.

```text
(no output)
```

Raw: `raw/acceptance-source-clean.json`.
