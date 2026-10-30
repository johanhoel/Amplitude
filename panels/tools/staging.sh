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
if [ "${HOMEDECK_STUB:-0}" = "1" ]; then
  # The shipped settings are empty, as a fresh install's are, so against the
  # stand-in every page would be an empty state. These point the settings at
  # what tools/stub-ha.py serves, which is what the screenshots are shot on.
  # Addresses are 192.0.2.x (the documentation range): nothing to reach.
  python3 - "$S/homedeck.toml" <<'EOF'
import re, sys
p = sys.argv[1]
t = open(p, encoding="utf-8").read()
for key, val in (("lock", '"lock.front"'), ("vacuum", '"vacuum.robot"'), ("charger", '"switch.charger"'),
                 ("charger_power_prefix", '"sensor.charger_"'), ("cam_detect", '"input_boolean.cameras"'),
                 ("weather", '"weather.home"'), ("spotify", '"media_player.m"'), ("tv", '"media_player.tv"')):
    t = re.sub(rf'^{key} = ""', f'{key} = {val}', t, count=1, flags=re.M)
t = re.sub(r'^players = \[\]$', '[[players]]\\nentity = "media_player.m"\\nlabel = "Living room"', t, count=1, flags=re.M)
t = re.sub(r'^pc = ""', 'pc = "192.0.2.10:8765"', t, count=1, flags=re.M)
t = re.sub(r'^genelecs = \[\]', 'genelecs = ["192.0.2.20", "192.0.2.21"]', t, count=1, flags=re.M)
t = re.sub(r'^buttons_panel = ""', 'buttons_panel = "http://192.0.2.30:4440/device/demo"', t, count=1, flags=re.M)
t = re.sub(r'^\[links\.extra\].*$', '[links.extra]\\nrouter = "http://192.0.2.1/"\\nnvr = "http://192.0.2.40/"', t, count=1, flags=re.M)
open(p, "w", encoding="utf-8").write(t)
EOF
fi
[ -f "$S/secrets.json" ] || { echo "First time: put a Home Assistant token for a separate HA user 'Home Deck staging'"
  echo "into $S/secrets.json as {\"ha_token\": \"...\"}   (type it yourself; never paste it into a coding agent)"
  echo "Or run without one:  HOMEDECK_STUB=1 tools/staging.sh"; exit 1; }
HOMEDECK_ROOT=$PWD/server HOMEDECK_CONFIG=$S/homedeck.toml STATE_DIRECTORY=$S \
HOMEDECK_READONLY=1 HOMEDECK_NO_BACKGROUND=1 HOMEDECK_PORT=${PORT:-8099} python3 server/server.py
