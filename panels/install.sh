#!/usr/bin/env bash
# install.sh - install or update Home Deck on a fresh Debian/Ubuntu machine, straight from this repo.
#   sudo ./install.sh              install (first time) or update the code; settings, token and layouts are kept
#   sudo ./install.sh --onboard    also start the setup wizard (first install does that by itself)
# After the first install, open the wizard address it prints: it scans the network, connects Home Assistant,
# suggests every setting and you confirm. homedeck.toml from this repo is the starting point.
set -euo pipefail
REPO="$(cd "$(dirname "$0")" && pwd)"
ROOT=/opt/panel-wrapper
STATE=/var/lib/panel-wrapper
say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || die "run as root (sudo ./install.sh)"
. /etc/os-release; case "$ID" in debian|ubuntu) ;; *) die "Debian or Ubuntu needed (found $PRETTY_NAME)";; esac
FIRST=1; [ -f "$ROOT/homedeck.toml" ] && FIRST=0

say "System packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends python3 python3-venv curl ca-certificates iproute2 ieee-data psmisc >/dev/null

say "Home Deck code and pages -> $ROOT"
mkdir -p "$ROOT/.snapshots"
[ "$FIRST" -eq 0 ] && tar czf "$ROOT/.snapshots/preinstall-$(date +%Y%m%d-%H%M%S).tgz" -C "$ROOT" homedeck www server.py homedeck.toml 2>/dev/null || true
cp -r "$REPO/server/homedeck" "$REPO/server/www" "$REPO/server/server.py" "$ROOT/"
find "$ROOT" -name __pycache__ -prune -exec rm -rf {} +
if [ "$FIRST" -eq 1 ]; then
  cp "$REPO/server/homedeck.toml" "$ROOT/homedeck.toml"         # starting point; the wizard changes what you confirm
  TZ_HOST=$(cat /etc/timezone 2>/dev/null || timedatectl show -p Timezone --value 2>/dev/null || true)
  [ -n "$TZ_HOST" ] && [ -f "/usr/share/zoneinfo/$TZ_HOST" ] && sed -i "s#^timezone = \".*\"#timezone = \"$TZ_HOST\"#" "$ROOT/homedeck.toml"
fi
chmod -R a+rX "$ROOT"

say "Python environment"
[ -d "$ROOT/venv" ] || python3 -m venv "$ROOT/venv"
"$ROOT/venv/bin/pip" install -q --upgrade netaudio zeroconf
grep -q '^netaudio = ' "$ROOT/homedeck.toml" && sed -i "s#^netaudio = \".*\"#netaudio = \"$ROOT/venv/bin/netaudio\"#" "$ROOT/homedeck.toml"

say "Services and commands"
install -m 755 "$REPO/infra/homedeck-apply" /usr/local/sbin/homedeck-apply
install -m 755 "$REPO/infra/homedeck-onboard" /usr/local/sbin/homedeck-onboard
install -m 644 "$REPO/infra/panel-wrapper.service" /etc/systemd/system/panel-wrapper.service
install -m 644 "$REPO/infra/homedeck-onboard.service" /etc/systemd/system/homedeck-onboard.service
mkdir -p /opt/homedeck-onboard
cp "$REPO"/onboard/*.py "$REPO/onboard/onboard.html" /opt/homedeck-onboard/
systemctl daemon-reload
systemctl enable panel-wrapper >/dev/null 2>&1

say "Starting Home Deck (checked restart, rolls back by itself)"
homedeck-apply || die "Home Deck did not start - see above"

IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')
echo
printf '\033[1mHome Deck is running:\033[0m  http://%s/start\n' "${IP:-THIS-ADDRESS}"
if [ "$FIRST" -eq 1 ] || [ "${1:-}" = "--onboard" ] || ! python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("ha_token") else 1)' "$STATE/secrets.json" 2>/dev/null; then
  homedeck-onboard
else
  echo "  Settings, Home Assistant token and layouts were kept. Run the setup wizard again any time: homedeck-onboard"
fi
