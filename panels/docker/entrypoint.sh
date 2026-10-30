#!/usr/bin/env bash
# Home Deck's container: seed the settings on first run, open the setup wizard
# until it has been through once, then serve the panels.
#
# There is no systemd here, so the two things it did are done differently:
# a restart is the container restarting (homedeck-apply stops this process and
# the restart policy brings it back), and an update is a new image.
set -euo pipefail

# Paths the image fixes, overridable so the script can be run outside it.
TEMPLATE=${HOMEDECK_TEMPLATE:-/opt/homedeck-template.toml}
ONBOARD_DIR=${HOMEDECK_ONBOARD_DIR:-/opt/homedeck-onboard}
ROOT=${HOMEDECK_ROOT:-/opt/panel-wrapper}
CONFIG=${HOMEDECK_CONFIG:-/data/homedeck.toml}
STATE=${STATE_DIRECTORY:-/state}
CODE_FILE=${ONBOARD_CODE_FILE:-$STATE/onboard.code}
DONE=$STATE/.onboard-done

mkdir -p "$(dirname "$CONFIG")" "$STATE"

# First run: the shipped settings, with the placeholder address the wizard replaces.
# A fresh install knows nothing about any house, exactly as install.sh leaves it.
# Written through a temporary file: a redirect makes the target even when the
# command fails, and an empty homedeck.toml would look like a configured house
# on the next start, so the panels would never come up again.
if [ ! -s "$CONFIG" ]; then
  tmp="$CONFIG.new-$$"
  if ! sed "s#__HA_URL__#${HOMEDECK_HA_URL:-http://homeassistant.local:8123}#" "$TEMPLATE" > "$tmp"; then
    rm -f "$tmp"; echo "entrypoint: cannot read the settings template at $TEMPLATE" >&2; exit 1
  fi
  if [ -n "${TZ:-}" ] && [ -f "/usr/share/zoneinfo/$TZ" ]; then
    sed -i "s#^timezone = \".*\"#timezone = \"$TZ\"#" "$tmp"
  fi
  [ -s "$tmp" ] || { rm -f "$tmp"; echo "entrypoint: the settings template is empty" >&2; exit 1; }
  mv "$tmp" "$CONFIG"
  echo "entrypoint: wrote $CONFIG from the template"
fi

# The wizard runs until it has saved once. After that it stays off unless you
# ask for it: docker compose run --rm -e HOMEDECK_ONBOARD=1 homedeck
if [ ! -f "$DONE" ] || [ "${HOMEDECK_ONBOARD:-0}" = "1" ]; then
  rm -f "$DONE"
  code=$(printf '%03d-%03d' $((RANDOM % 1000)) $((RANDOM % 1000)))
  umask 077; printf '%s\n' "$code" > "$CODE_FILE"
  echo
  echo "  Setup wizard:  http://<this-host>:${ONBOARD_PORT:-8089}"
  echo "  Setup code:    $code"
  echo "  It scans the network, connects Home Assistant and suggests every setting; you confirm."
  echo
  python3 "$ONBOARD_DIR/onboard.py" &
fi

# The panels. exec so signals reach it and docker stop is not a kill.
echo "entrypoint: starting Home Deck on port ${HOMEDECK_PORT:-80}"
exec python3 "$ROOT/server.py"
