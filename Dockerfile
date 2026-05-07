# syntax=docker/dockerfile:1.7-labs
FROM python:3.14-alpine

# ===== Project Variables =====
ARG APP_NAME=blink2mqtt
ENV APP_NAME=${APP_NAME}
ENV READY_FILE=/tmp/${APP_NAME}.ready
ARG SERVICE_DESC="Publishes Blink camera data to MQTT for Home Assistant"
ARG VERSION=0.0.0
ENV APP_VERSION=${VERSION}
ARG USER_ID=1000
ARG GROUP_ID=1000

# ===== Base Setup =====
WORKDIR /app

# Generic pretend version variables (used by setuptools-scm)
# No uppercase substitution; just define a safe fallback
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION}
ENV APP_PRETEND_VERSION=${VERSION}

# ===== System Dependencies =====
# git: build-only (setuptools-scm); removed at end
# su-exec: drop privileges in entrypoint (replaces gosu, ~22KB C binary)
# shadow: runtime usermod/groupmod for PUID/PGID overrides
# build-base, libffi-dev, openssl-dev: needed to build any C-extension wheels
#   that don't ship musl wheels; removed at end
RUN apk add --no-cache \
        git \
        su-exec \
        shadow \
        build-base \
        libffi-dev \
        openssl-dev && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir uv

# ===== Copy Project Metadata =====
COPY pyproject.toml uv.lock ./

# ===== Build & Install =====
# 1. Create isolated virtual environment
RUN uv venv
ENV PATH="/app/.venv/bin:${PATH}"

# 2. Export locked dependencies (with pretend version active)
RUN mkdir -p src && \
    SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION} uv export --no-dev --format=requirements-txt > /tmp/reqs.all.txt && \
    rm -rf src

# 3. Strip the local project from deps list so setuptools-scm isn’t triggered during deps install
RUN grep -v -E "(^-e\s+(\.|file://)|@\s+file://|^file://|/app)" /tmp/reqs.all.txt > /tmp/reqs.deps.txt || true

# 4. Install dependencies
RUN uv pip install --no-cache-dir -r /tmp/reqs.deps.txt

# ===== Copy Application Source =====
COPY . .

# 5. Install the app itself (pretend version visible, no deps)
RUN SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION} uv pip install --no-cache-dir . --no-deps

# 6. Cleanup — remove build-only packages, keep su-exec + shadow for runtime
RUN /usr/local/bin/pip uninstall -y uv && \
    apk del git build-base libffi-dev openssl-dev && \
    (rm -rf /tmp/reqs.all.txt /tmp/reqs.deps.txt .git || true)

# ===== Non-root Runtime User =====
RUN addgroup -g "${GROUP_ID}" appuser && \
    adduser -D -u "${USER_ID}" -G appuser -s /bin/sh appuser && \
    mkdir -p /config /media && chown -R appuser:appuser /app /config /media

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# ===== Runtime =====
ENV SERVICE=${APP_NAME}
LABEL org.opencontainers.image.title=${APP_NAME} \
      org.opencontainers.image.description=${SERVICE_DESC} \
      org.opencontainers.image.version=${VERSION}

ENTRYPOINT ["/entrypoint.sh", "python", "-m", "blink2mqtt"]
CMD ["-c", "/config"]
