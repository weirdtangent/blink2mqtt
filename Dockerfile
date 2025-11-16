# syntax=docker/dockerfile:1.7-labs
FROM python:3.14-slim

# ===== Project Variables =====
ARG APP_NAME=blink2mqtt
ENV APP_NAME=${APP_NAME}
ARG SERVICE_DESC="Publishes Blink camera data to MQTT for Home Assistant"
ARG VERSION=0.0.0
ENV APP_VERSION=${VERSION}
ARG USER_ID=1000
ARG GROUP_ID=1000

# ===== Base Setup =====
WORKDIR /app
ENV DEBIAN_FRONTEND=noninteractive

# Generic pretend version variables (used by setuptools-scm)
# No uppercase substitution; just define a safe fallback
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION}
ENV APP_PRETEND_VERSION=${VERSION}

# ===== System Dependencies =====
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    apt-get upgrade -y && \
    pip install --no-cache-dir uv && \
    rm -rf /var/lib/apt/lists/*

# ===== Copy Source and Metadata =====
COPY pyproject.toml uv.lock ./
COPY . .

# ===== Build & Install =====
# 1. Create isolated virtual environment
RUN uv venv

# 2. Export locked dependencies (with pretend version active)
RUN SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION} uv export --no-dev --format=requirements-txt > /tmp/reqs.all.txt

# 3. Strip the local project from deps list so setuptools-scm isn’t triggered during deps install
RUN grep -v -E "(^-e\s+file://|^file://|/app)" /tmp/reqs.all.txt > /tmp/reqs.deps.txt || true

# 4. Install dependencies
RUN uv pip install --no-cache-dir -r /tmp/reqs.deps.txt

# 5. Install the app itself (pretend version visible, no deps)
RUN SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION} uv pip install --no-cache-dir . --no-deps

# 6. Cleanup
RUN rm -f /tmp/reqs.all.txt /tmp/reqs.deps.txt .git || true

# ===== Non-root Runtime User =====
RUN groupadd -g "${GROUP_ID}" appuser && \
    useradd -u "${USER_ID}" -g "${GROUP_ID}" --create-home --shell /bin/bash appuser && \
    mkdir -p /config && chown -R appuser:appuser /app /config

USER appuser

# ===== Runtime =====
ENV SERVICE=${APP_NAME}
LABEL org.opencontainers.image.title=${APP_NAME} \
      org.opencontainers.image.description=${SERVICE_DESC} \
      org.opencontainers.image.version=${VERSION}

ENTRYPOINT ["/bin/sh", "-c", "/app/.venv/bin/python -m $APP_NAME \"$@\"", "sh"]
CMD ["-c", "/config"]
