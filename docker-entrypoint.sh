#!/bin/sh
# Entrypoint (F62): fix ownership of the writable mounts, then drop privileges
# to PUID/PGID and exec the real command.
#
# The image deliberately has no USER directive — the container starts as root so
# this script can chown the bind-mounted data/ and intake.yaml, then it drops to
# PUID/PGID before the app process starts. The app never runs as root.

set -eu

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

# Ensure a matching group and user exist (idempotent; non-fatal if they can't be
# created — setpriv works with numeric ids regardless).
if ! getent group "$PGID" >/dev/null 2>&1; then
    groupadd -g "$PGID" ripcale 2>/dev/null || true
fi
if ! getent passwd "$PUID" >/dev/null 2>&1; then
    useradd -u "$PUID" -g "$PGID" -d /app -s /sbin/nologin ripcale 2>/dev/null || true
fi

# Make the writable mounts owned by the target uid/gid. This self-heals a legacy
# root-owned data/ on first boot (a no-op on later boots).
mkdir -p /app/data
chown -R "$PUID":"$PGID" /app/data
chown "$PUID":"$PGID" /app/intake.yaml 2>/dev/null || true

# Drop privileges and exec the app.
exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups "$@"
