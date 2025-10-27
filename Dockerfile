# syntax=docker/dockerfile:1.7-labs
FROM python:3-slim
WORKDIR /app

COPY pyproject.toml uv.lock ./

# ---- Version injection support ----
ARG VERSION
ENV BLINK2MQTT_VERSION=${VERSION}
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_BLINK2MQTT=${VERSION}

# Install uv and git - and get updates too
RUN pip install uv
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

RUN apt-get update && \
    apt-get install -y git && \
    apt-get upgrade -y && \
    rm -rf /var/lib/apt/lists/*

# copy source 
COPY --exclude=.git . .

# Install dependencies (uses setup info, now src exists)
RUN uv sync --frozen --no-dev

# Install the package (if needed)
RUN uv pip install .

# Default build arguments (can be overridden at build time)
ARG USER_ID=1000
ARG GROUP_ID=1000

# Create the app user and group
RUN groupadd --gid "${GROUP_ID}" appuser && \
    useradd --uid "${USER_ID}" --gid "${GROUP_ID}" --create-home --shell /bin/bash appuser

# Ensure /config exists and is writable
RUN mkdir -p /config && chown -R appuser:appuser /config

# Optional: fix perms if files already copied there (won’t break if empty)
RUN find /config -type f -exec chmod 0664 {} + || true

# Ensure /app is owned by the app user
RUN chown -R appuser:appuser /app

# Drop privileges
USER appuser

# ---- Runtime ----
ENV SERVICE=blink2mqtt
ENTRYPOINT ["/app/.venv/bin/blink2mqtt"]
CMD ["-c", "/config"]

