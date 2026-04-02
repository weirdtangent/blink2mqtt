#!/bin/bash
set -e

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

# If running as root, adjust appuser UID/GID and drop privileges
if [ "$(id -u)" = "0" ]; then
    CUR_UID=$(id -u appuser)
    CUR_GID=$(id -g appuser)

    if [ "$PGID" != "$CUR_GID" ]; then
        groupmod -o -g "$PGID" appuser
    fi
    if [ "$PUID" != "$CUR_UID" ]; then
        usermod -o -u "$PUID" appuser
    fi

    chown appuser:appuser /app /config /media

    exec gosu appuser "$@"
fi

# Already running as non-root (no PUID/PGID support)
exec "$@"
