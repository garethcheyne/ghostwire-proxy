#!/usr/bin/env bash
set -euo pipefail

# upgradeGhostWireProxy.sh
# Wrapper for ghostwire-proxy/scripts/upgrade.sh on production servers.
# Usage:
#   ./upgradeGhostWireProxy.sh            # upgrade ghostwire-proxy to latest tagged release
#   ./upgradeGhostWireProxy.sh v2026.04.05.1200
#   ./upgradeGhostWireProxy.sh --force

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROXY_DIR="$SCRIPT_DIR"
UPGRADE_SCRIPT="./scripts/upgrade.sh"

if [ ! -d "$PROXY_DIR" ]; then
  echo "[error] ghostwire-proxy directory not found at: $PROXY_DIR" >&2
  exit 1
fi

cd "$PROXY_DIR"

if [ ! -f "$UPGRADE_SCRIPT" ]; then
  echo "[error] ghostwire-proxy upgrade helper not found: $PROXY_DIR/$UPGRADE_SCRIPT" >&2
  exit 1
fi

if [ ! -x "$UPGRADE_SCRIPT" ]; then
  chmod +x "$UPGRADE_SCRIPT" || true
fi

echo "[info] Running ghostwire-proxy upgrade helper in: $PROXY_DIR"
if [ "$#" -eq 0 ]; then
  exec "$UPGRADE_SCRIPT"
else
  exec "$UPGRADE_SCRIPT" "$@"
fi
