#!/usr/bin/env bash
# Local dependency vulnerability report (F58.01).
#
# Runs osv-scanner against the project's uv.lock with the same config the Docker
# build uses. Informational — prints the severity-sorted table. Extra args (e.g.
# --format json) are forwarded to osv-scanner.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

exec docker run --rm \
  -v "${REPO_DIR}:/src" \
  -w /src \
  ghcr.io/google/osv-scanner:latest \
  scan source -L uv.lock --config osv-scanner.toml "$@"
