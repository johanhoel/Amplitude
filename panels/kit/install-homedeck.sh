#!/usr/bin/env bash
# install-homedeck.sh - installs or updates Home Deck (panels for Home Assistant) on this Debian/Ubuntu machine.
# Run as root from the unpacked kit folder:
#     ./install-homedeck.sh                      first install: asks for the Home Assistant address
#     ./install-homedeck.sh --update             update: keeps settings, token, layouts and your own edits
#     HOMEDECK_HA_URL=http://192.168.1.20:8123 ./install-homedeck.sh     (no question)
#
# Your own edits survive updates: every release records a checksum per file (/opt/panel-wrapper/.release).
# A file you changed is kept; the new version is saved next to it as <file>.new-<version> and listed at the end.
set -euo pipefail
KIT="$(cd "$(dirname "$0")" && pwd)"
ROOT=/opt/panel-wrapper
STATE=/var/lib/panel-wrapper
HD_VERSION="$(cat "$KIT/app/VERSION")"
UPDATE=0; [ "${1:-}" = "--update" ] && UPDATE=1
say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || die "run as root"
. /etc/os-release; case "$ID" in debian|ubuntu) ;; *) die "Debian or Ubuntu needed (found $PRETTY_NAME)";; esac
[ -f "$ROOT/homedeck.toml" ] && [ "$UPDATE" -eq 0 ] && { say "Home Deck is already installed: updating instead"; UPDATE=1; }

# ---- packages
say "System packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends python3 python3-venv curl ca-certificates iproute2 >/dev/null

# ---- Home Assistant address (first install only)
HA_URL="${HOMEDECK_HA_URL:-}"
if [ "$UPDATE" -eq 0 ] && [ -z "$HA_URL" ]; then
  echo
  echo "Home Deck needs the address of your Home Assistant, as this server reaches it,"
  echo "for example  http://192.168.1.20:8123  or  https://homeassistant.local:8123"
  while :; do
    read -r -p "Home Assistant address: " HA_URL
    HA_URL="${HA_URL%/}"
    [[ $HA_URL =~ ^https?://[^[:space:]/]+$ ]] || { warn "Format: http://ADDRESS:8123"; continue; }
    if curl -fsk -m 6 -o /dev/null "$HA_URL/manifest.json"; then echo "OK: Home Assistant answers."; break; fi
    warn "No answer from $HA_URL/manifest.json."
    read -r -p "Use it anyway? [y/N]: " a; [[ ${a:-n} =~ ^[Yy] ]] && break
  done
fi

# ---- files (code + pages): replace what you did not change, keep what you did
say "Installing Home Deck $HD_VERSION"
mkdir -p "$ROOT"
declare -a KEPT=()
manifest_old="$ROOT/.release"
sum_of() { if [ -f "$1" ]; then sha256sum "$1" | cut -c1-64; fi; }
old_sum() { [ -f "$manifest_old" ] && awk -v f="$1" '$2==f{print $1}' "$manifest_old" || true; }
newman=$(mktemp)
cd "$KIT/app"
while IFS= read -r -d '' f; do
  rel="${f#./}"
  [ "$rel" = "homedeck.toml" ] && continue                 # settings: written once, never replaced
  dest="$ROOT/$rel"; new=$(sum_of "$f"); cur=$(sum_of "$dest"); was=$(old_sum "$rel")
  mkdir -p "$(dirname "$dest")"
  if [ -n "$cur" ] && [ -n "$was" ] && [ "$cur" != "$was" ] && [ "$cur" != "$new" ]; then
    cp "$f" "$dest.new-$HD_VERSION"; KEPT+=("$rel")          # you edited it: keep yours, put the new one next to it
  elif [ -n "$cur" ] && [ -z "$was" ] && [ "$UPDATE" -eq 1 ] && [ "$cur" != "$new" ]; then
    cp "$f" "$dest.new-$HD_VERSION"; KEPT+=("$rel")          # unknown state (no record): be safe, keep it
  else
    cp "$f" "$dest"
  fi
  echo "$new  $rel" >> "$newman"
done < <(find . -type f ! -name '*.pyc' -print0)
mv "$newman" "$manifest_old"
chmod -R a+rX "$ROOT"

if [ ! -f "$ROOT/homedeck.toml" ]; then
  sed "s#__HA_URL__#${HA_URL}#" "$KIT/app/homedeck.toml" > "$ROOT/homedeck.toml"
  TZ_HOST=$(cat /etc/timezone 2>/dev/null || timedatectl show -p Timezone --value 2>/dev/null || true)
  [ -n "$TZ_HOST" ] && [ -f "/usr/share/zoneinfo/$TZ_HOST" ] && sed -i "s#^timezone = \".*\"#timezone = \"$TZ_HOST\"#" "$ROOT/homedeck.toml"
fi
[ -d "$ROOT/venv" ] || python3 -m venv "$ROOT/venv"

# ---- editor + helper commands + services
mkdir -p /opt/deck-editor
cp "$KIT/editor/editor.py" "$KIT/editor/editor.html" /opt/deck-editor/
install -m 755 "$KIT/bin/homedeck-apply" /usr/local/sbin/homedeck-apply
install -m 755 "$KIT/bin/homedeck-update" /usr/local/sbin/homedeck-update
install -m 755 "$KIT/bin/homedeck-install-tree" /usr/local/sbin/homedeck-install-tree
install -m 644 "$KIT/systemd/panel-wrapper.service" /etc/systemd/system/panel-wrapper.service
install -m 644 "$KIT/systemd/deck-editor.service" /etc/systemd/system/deck-editor.service
install -m 644 "$KIT/systemd/homedeck-update.path" "$KIT/systemd/homedeck-update.service" /etc/systemd/system/   # the update card
systemctl daemon-reload
systemctl enable panel-wrapper deck-editor >/dev/null 2>&1
systemctl enable --now homedeck-update.path >/dev/null 2>&1

# ---- first start (creates the private state folder), then the notice topic
if [ "$UPDATE" -eq 0 ] || ! systemctl is-active -q panel-wrapper; then systemctl restart panel-wrapper; sleep 2; fi
if [ -d "$STATE" ] && ! grep -q ntfy_topic "$STATE/secrets.json" 2>/dev/null; then
  topic="homedeck-$(tr -dc 'a-z0-9' </dev/urandom | head -c 16 || true)"
  python3 - "$STATE/secrets.json" "$topic" <<'PY'
import json, os, sys
p, topic = sys.argv[1], sys.argv[2]
try: d = json.load(open(p))
except Exception: d = {}
d['ntfy_topic'] = topic
json.dump(d, open(p + '.tmp', 'w')); os.chmod(p + '.tmp', 0o600); os.replace(p + '.tmp', p)
PY
  chown --reference="$(readlink -f "$STATE")" "$STATE/secrets.json"
fi
systemctl restart deck-editor

# ---- safe restart: check -> restart -> health -> automatic rollback
say "Starting Home Deck"
homedeck-apply || die "Home Deck did not start - see above"

IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')
echo
printf '\033[1mHome Deck %s is running.\033[0m\n' "$HD_VERSION"
if [ "$UPDATE" -eq 0 ]; then
  echo "  1. Open  http://${IP:-THIS-ADDRESS}/  in a browser: the setup page asks for a Home Assistant token."
  echo "  2. Panels:  http://${IP:-THIS-ADDRESS}/start   (add it to the home screen of phones and tablets)"
  echo "  3. Editor:  http://${IP:-THIS-ADDRESS}:8088   (choose a password on the first visit)"
else
  echo "  Panels: http://${IP:-THIS-ADDRESS}/start   Settings, token, layouts and edits were kept."
fi
if [ ${#KEPT[@]} -gt 0 ]; then
  echo
  warn "You had edited these files, so your version was kept. The new version is next to each as .new-$HD_VERSION:"
  printf '     %s\n' "${KEPT[@]}"
  echo "     Compare them in the editor (History) or with: diff FILE FILE.new-$HD_VERSION"
fi
