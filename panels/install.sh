#!/usr/bin/env bash
# install.sh - install Home Deck on any Debian/Ubuntu machine, straight from this repo, and start the setup wizard.
#   sudo ./install.sh              install, or update the code (settings, token and layouts are kept)
#   sudo ./install.sh --onboard    also start the setup wizard again
# A fresh install knows nothing about any house: it installs the generic edition (friend/src), and the setup wizard
# (http://<machine>:8089) scans the network, connects Home Assistant and suggests the settings for you to confirm.
set -euo pipefail
REPO="$(cd "$(dirname "$0")" && pwd)"
ROOT=/opt/panel-wrapper
STATE=/var/lib/panel-wrapper
say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || die "run as root (sudo ./install.sh)"
FIRST=1; [ -f "$ROOT/homedeck.toml" ] && FIRST=0
. /etc/os-release; case "$ID" in debian|ubuntu) ;; *) die "Debian or Ubuntu needed (found $PRETTY_NAME)";; esac
say "System packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends python3 python3-venv curl ca-certificates iproute2 ieee-data >/dev/null

# the kit layout the edition's own installer expects: app/ editor/ bin/ systemd/
KIT=$(mktemp -d); trap 'rm -rf "$KIT"' EXIT
mkdir -p "$KIT/app" "$KIT/editor" "$KIT/bin" "$KIT/systemd"
cp -r "$REPO/friend/src/server.py" "$REPO/friend/src/homedeck" "$REPO/friend/src/www" "$REPO/friend/src/homedeck.toml" "$KIT/app/"
find "$KIT/app" -name __pycache__ -prune -exec rm -rf {} +
echo "repo-$(cd "$REPO" && git rev-parse --short HEAD 2>/dev/null || date +%Y.%m.%d)" > "$KIT/app/VERSION"
cp "$REPO/friend/editor/editor.py" "$REPO/friend/editor/editor.html" "$KIT/editor/"
python3 "$REPO/friend/kit/patch_editor.py" "$KIT/editor/editor.py" >/dev/null
cp "$REPO/friend/kit/homedeck-apply" "$REPO/friend/kit/homedeck-update" "$KIT/bin/"
cp "$REPO/friend/kit/panel-wrapper.service" "$REPO/friend/kit/deck-editor.service" "$KIT/systemd/"
cp "$REPO/friend/kit/install-homedeck.sh" "$KIT/"; chmod +x "$KIT/install-homedeck.sh" "$KIT/bin/"*

# the address is a placeholder: the wizard finds Home Assistant on the network and sets it
HOMEDECK_HA_URL="${HOMEDECK_HA_URL:-http://homeassistant.local:8123}" "$KIT/install-homedeck.sh" $([ "$FIRST" -eq 0 ] && echo --update)

say "Setup wizard"
"$ROOT/venv/bin/pip" install -q zeroconf
mkdir -p /opt/homedeck-onboard
cp "$REPO"/onboard/*.py "$REPO/onboard/onboard.html" /opt/homedeck-onboard/
install -m 755 "$REPO/infra/homedeck-onboard" /usr/local/sbin/homedeck-onboard
install -m 644 "$REPO/infra/homedeck-onboard.service" /etc/systemd/system/homedeck-onboard.service
systemctl daemon-reload
if [ "$FIRST" -eq 1 ] || [ "${1:-}" = "--onboard" ] || \
   ! python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("ha_token") else 1)' "$STATE/secrets.json" 2>/dev/null; then
  homedeck-onboard
else
  echo "  Settings, token and layouts were kept. Start the setup wizard again any time: sudo homedeck-onboard"
fi
