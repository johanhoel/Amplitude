#!/bin/bash
# Run the repo's Home Deck on this machine, port 8099, with its own throw-away state. Real Home Assistant data,
# no presence loops, no notices, never touches production files. Stop with Ctrl+C.
set -euo pipefail
cd "$(dirname "$0")/.."
S=$PWD/.staging-state; mkdir -p "$S"
HA="${HOMEDECK_HA_URL:-}"
if [ "${HOMEDECK_STUB:-0}" = "1" ]; then
  # No Home Assistant and no token: tools/stub-ha.py answers with made-up rooms
  # and lights. Enough to render every page, which is all tests/smoke.py asks.
  HA=http://127.0.0.1:8123
  python3 "$PWD/tools/stub-ha.py" & STUB=$!; trap 'kill $STUB 2>/dev/null' EXIT
  sleep 1
  printf '{"ha_token": "stub-no-real-credential"}' > "$S/secrets.json"; chmod 600 "$S/secrets.json"
fi
# The template ships a placeholder, not an address: the installer fills it in
# from what you type at setup. Staging has nobody to ask, so it needs one here.
[ -n "$HA" ] || { echo "Set the Home Assistant address:  HOMEDECK_HA_URL=http://ADDRESS:8123 tools/staging.sh"
  echo "Or run against a stand-in with no Home Assistant at all:  HOMEDECK_STUB=1 tools/staging.sh"; exit 1; }
sed -e "s#^static_dir = .*#static_dir = \"$PWD/server/www\"#" \
    -e "s#^url = \"__HA_URL__\".*#url = \"$HA\"#" \
    server/homedeck.toml > "$S/homedeck.toml"
[ -f "$S/secrets.json" ] || { echo "First time: put a Home Assistant token for a separate HA user 'Home Deck staging'"
  echo "into $S/secrets.json as {\"ha_token\": \"...\"}   (type it yourself; never paste it into a coding agent)"
  echo "Or run without one:  HOMEDECK_STUB=1 tools/staging.sh"; exit 1; }
HOMEDECK_ROOT=$PWD/server HOMEDECK_CONFIG=$S/homedeck.toml STATE_DIRECTORY=$S \
HOMEDECK_READONLY=1 HOMEDECK_NO_BACKGROUND=1 HOMEDECK_PORT=${PORT:-8099} python3 server/server.py
