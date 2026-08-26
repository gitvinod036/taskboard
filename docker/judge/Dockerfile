# TaskFlow judge image — the ONLY environment where user code runs.
#
# Build once per host:
#     docker build -t taskflow-judge:latest .
#
# Reproducible: pinned base image + pinned toolchain versions.
# Runtime hardening (no network, non-root, caps dropped, rlimits) is applied
# by taskflow/execution/sandbox.py at invocation time, NOT in this file, so
# it can never drift out of sync with what the app enforces.

FROM debian:12-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3=3.11.* \
        nodejs=18.* \
        g++=4:12.* \
        default-jdk-headless=2:1.17-* \
        time \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root account used for every execution (--user is also forced by the
# sandbox; this keeps interactive runs safe too).
RUN useradd --create-home --uid 10001 judge
USER judge

WORKDIR /sandbox
