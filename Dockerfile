# syntax=docker/dockerfile:1.7
FROM python:3-slim

# Work inside /app
WORKDIR /app

# Copy lock and project metadata first for dependency caching
COPY pyproject.toml uv.lock ./

# Install uv and dependencies (excluding dev)
RUN pip install uv
RUN uv sync --frozen --no-dev

# Copy source excluding .git
COPY --exclude=.git . .

# ---- Version injection support ----
# Allows CI (e.g., semantic-release) to pass a version:
# docker build --build-arg VERSION=1.2.3 ...
ARG VERSION
ENV BLINK2MQTT_VERSION=${VERSION}

# Install our package properly so setuptools-scm resolves the version
RUN uv pip install .

# ---- Runtime ----
ENV SERVICE=blink2mqtt
ENTRYPOINT ["blink2mqtt"]
CMD ["-c", "/config"]
