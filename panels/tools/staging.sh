#!/bin/bash
# Run the repo's Home Deck on this machine, port 8099, with its own throw-away state. Real Home Assistant data,
# no presence loops, no notices, never touches production files. Stop with Ctrl+C.
set -euo pipefail
cd "$(dirname "$0")/.."
S=$PWD/.staging-state; mkdir -p "$S"
sed "s#^static_dir = .*#static_dir = \"$PWD/server/www\"#" server/homedeck.toml > "$S/homedeck.toml"
[ -f "$S/secrets.json" ] || { echo "First time: put a Home Assistant token for a separate HA user 'Home Deck staging'"
  echo "into $S/secrets.json as {\"ha_token\": \"...\"}   (type it yourself; never paste it into a coding agent)"; exit 1; }
HOMEDECK_ROOT=$PWD/server HOMEDECK_CONFIG=$S/homedeck.toml STATE_DIRECTORY=$S \
HOMEDECK_READONLY=1 HOMEDECK_NO_BACKGROUND=1 HOMEDECK_PORT=${PORT:-8099} python3 server/server.py
