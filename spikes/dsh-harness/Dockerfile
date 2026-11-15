FROM python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39
ARG SPIKE_UID=1000
ARG SPIKE_GID=1000
RUN groupadd --gid "$SPIKE_GID" spike && useradd --uid "$SPIKE_UID" --gid "$SPIKE_GID" --create-home --shell /usr/sbin/nologin spike
USER spike
