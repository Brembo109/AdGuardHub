#!/bin/sh
# Align /data's ownership with the host before dropping privileges.
#
# A bind mount replaces the image's /data with the host directory, ownership and
# all, so anything the Dockerfile chowned at build time is irrelevant at runtime.
# Starting as root and fixing it here is what makes `-v ./data:/data` work without
# the operator having to chown anything first.
set -e

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"
DATA_DIR="${ADGUARDHUB_DATA_DIR:-/data}"

if [ "$(id -u)" = "0" ]; then
    mkdir -p "$DATA_DIR"
    # Only chown when it isn't already right: on a large or network-backed share a
    # recursive chown every start is slow, and on some remote filesystems it fails.
    if [ "$(stat -c '%u:%g' "$DATA_DIR")" != "$PUID:$PGID" ]; then
        chown -R "$PUID:$PGID" "$DATA_DIR" || echo "adguardhub: could not chown $DATA_DIR — continuing" >&2
    fi
    exec gosu "$PUID:$PGID" "$@"
fi

# Already unprivileged (e.g. compose `user:` or Podman rootless): run as we are and
# let the app's own startup check report a permission problem in plain language.
exec "$@"
