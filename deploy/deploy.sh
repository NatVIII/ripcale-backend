#!/usr/bin/env bash
# Poll-based deploy: pull the latest commit and rebuild if anything changed.
#
# Safe to run on a schedule (systemd timer / cron) — it only rebuilds when HEAD
# actually moved, so a no-op poll costs almost nothing.
#
# Assumes the repo is cloned at /opt/ripcale-backend with the gitignored files
# (.env, config.yaml, intake.yaml) already in place, and that this script is
# run by a user in the `docker` group. Adjust REPO_DIR as needed.

set -euo pipefail

REPO_DIR="/opt/ripcale-backend"

cd "$REPO_DIR"

before="$(git rev-parse HEAD)"
git pull --ff-only
after="$(git rev-parse HEAD)"

if [ "$before" != "$after" ]; then
    echo "[deploy] new commit detected ($before -> $after); rebuilding"
    docker compose up -d --build
else
    echo "[deploy] up to date ($after)"
fi
