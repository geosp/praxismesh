# DSH container image (DSH migration plan D3, D4, R17; ADR-0006).
# The launcher runs as root with SYS_ADMIN granted at run time; the DSH runtime
# runs as uid 1000 and commands as uid 4242, both in group 4243.
FROM python:3.11-slim-bookworm@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39

# Template cli_tools: python3, wc, git, sh. git comes from the base image's own
# Debian snapshot, so its version is fixed.
RUN rm /etc/apt/sources.list.d/debian.sources \
 && printf '%s\n' \
    'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/20261104T212339Z bookworm main' \
    'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/20261104T212339Z bookworm-security main' \
    > /etc/apt/sources.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends git=1:2.39.5-0+deb12u3 \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --gid 4243 dsh-shared \
 && useradd --uid 1000 --gid 4243 --no-create-home --shell /usr/sbin/nologin dsh-runtime \
 && useradd --uid 4242 --gid 4243 --no-create-home --shell /usr/sbin/nologin dsh-command \
 && mkdir -p /opt/dsh /work /attempts

COPY requirements.txt /opt/dsh/requirements.txt
RUN pip install --no-cache-dir --no-deps --require-hashes --target /opt/dsh/site \
    -r /opt/dsh/requirements.txt
COPY pins.py launcher.py /opt/dsh/
RUN python /opt/dsh/pins.py build /opt/dsh/requirements.txt

ENV PYTHONPATH=/opt/dsh/site PYTHONDONTWRITEBYTECODE=1
CMD ["python", "/opt/dsh/launcher.py"]
