#!/bin/bash
set -e

# DStreamer Entrypoint - Start all services

echo "=== DStreamer Startup ==="

# Load environment or use defaults
DANTE_LOG_LEVEL=${DANTE_LOG_LEVEL:-info}
AIRPLAY_ENABLED=${AIRPLAY_ENABLED:-true}
CHROMECAST_ENABLED=${CHROMECAST_ENABLED:-false}

# Names (set in .env, see .env.example)
DEVICE_NAME=${DEVICE_NAME:-DStreamer}
AIRPLAY_NAME=${AIRPLAY_NAME:-$DEVICE_NAME}
TX_CHANNEL_NAMES=${TX_CHANNEL_NAMES:-}
RX_CHANNEL_NAMES=${RX_CHANNEL_NAMES:-}
# Remote access (set in .env): a password turns on the panel and API for
# other computers, e.g. the DStreamer desktop apps. Empty = no change.
REMOTE_PASSWORD=${REMOTE_PASSWORD:-}

VIRGIL_CONF=/app/data/virgil.conf
SHAIRPORT_CONF=/run/shairport-sync.conf

fail() {
    echo "[!] $*" >&2
    exit 1
}

# Turn on remote access with REMOTE_PASSWORD: rewrite remote_access and
# remote_password in [device]. awk reads the password from the environment,
# so characters like / & \ need no escaping.
set_remote_password() {
    [ -n "$REMOTE_PASSWORD" ] || return 0
    [ ${#REMOTE_PASSWORD} -ge 8 ] || fail "REMOTE_PASSWORD must be at least 8 characters"
    [[ "$REMOTE_PASSWORD" =~ [[:space:]\"] ]] && fail "REMOTE_PASSWORD may not contain spaces or \""
    awk '
        function put() { print "remote_access = true"; print "remote_password = " ENVIRON["REMOTE_PASSWORD"]; done = 1 }
        /^\[/ { if (dev && !done) put(); dev = ($0 == "[device]") }
        dev && /^#?[ \t]*remote_(access|password)[ \t]*=/ { if (!done) put(); next }
        { print }
        END { if (!done) { if (!dev) print "[device]"; put() } }
    ' "$VIRGIL_CONF" > "$VIRGIL_CONF.new" && mv "$VIRGIL_CONF.new" "$VIRGIL_CONF"
}

# Write channel names into [channel_names]: $1 = tx|rx, $2 = "Name 1,Name 2,..."
set_channel_names() {
    local dir=$1 list=$2 i name
    local -a names

    [ -n "$list" ] || return 0
    IFS=',' read -ra names <<< "$list"
    for i in "${!names[@]}"; do
        name=$(echo "${names[$i]}" | sed 's/^ *//; s/ *$//')
        [ ${#name} -le 31 ] || fail "${dir} channel name \"$name\" is longer than 31 characters"
        [[ "$name" =~ [=.@\"\\] ]] && fail "${dir} channel name \"$name\" contains = . @ \" or \\"
        names[$i]=$name
    done
    dupes=$(printf '%s\n' "${names[@]}" | grep -v '^$' | sort | uniq -d)
    [ -z "$dupes" ] || fail "duplicate ${dir} channel names: $dupes"

    grep -q '^\[channel_names\]' "$VIRGIL_CONF" || printf '\n[channel_names]\n' >> "$VIRGIL_CONF"
    sed -i "/^\[channel_names\]/,/^\[/{/^${dir}[0-9]* = /d}" "$VIRGIL_CONF"
    # Insert last-to-first, each right under the header, so they end up in order
    for (( i = ${#names[@]} - 1; i >= 0; i-- )); do
        [ -n "${names[$i]}" ] || continue
        sed -i "/^\[channel_names\]/a ${dir}$((i + 1)) = ${names[$i]}" "$VIRGIL_CONF"
    done
}

# Dante device names: letters, digits, '-', '_' and spaces, at most 31
[[ "$DEVICE_NAME" =~ ^[A-Za-z0-9_\ -]{1,31}$ ]] ||
    fail "DEVICE_NAME \"$DEVICE_NAME\" may only use letters, digits, '-', '_' and spaces (max 31)"
[[ "$AIRPLAY_NAME" =~ [\"\\\|\&] ]] && fail "AIRPLAY_NAME may not contain \" \\ | or &"

# Create log directory
mkdir -p /var/log/dstreamer
chown -R dante:dante /var/log/dstreamer

# Virgil config: start from the template once, then Virgil owns data/virgil.conf
mkdir -p /app/data
[ -f "$VIRGIL_CONF" ] || cp /app/virgil.conf.default "$VIRGIL_CONF"
sed -i "s/^name = .*/name = $DEVICE_NAME/" "$VIRGIL_CONF"
set_channel_names tx "$TX_CHANNEL_NAMES"
set_channel_names rx "$RX_CHANNEL_NAMES"
set_remote_password
[ -z "$REMOTE_PASSWORD" ] || echo "[*] Remote access on: control panel and API at http://<this-host>:8480/"
echo "[*] Dante name: $DEVICE_NAME, AirPlay name: $AIRPLAY_NAME"

# AirPlay name
sed "s|^\(\s*name = \).*;|\1\"$AIRPLAY_NAME\";|" /app/shairport-sync.conf > "$SHAIRPORT_CONF"

# Start D-Bus (Avahi and Shairport-sync talk to each other over it)
echo "[*] Starting D-Bus..."
mkdir -p /run/dbus
rm -f /run/dbus/pid
dbus-daemon --system --fork

# Start Avahi daemon (mDNS, needed for AirPlay discovery)
echo "[*] Starting Avahi (mDNS)..."
rm -f /run/avahi-daemon/pid
avahi-daemon --daemonize --no-drop-root

# Start Virgil Dante engine first: the ALSA "virgil" device needs it running
echo "[*] Starting Virgil Dante engine..."
/app/virgild -c "$VIRGIL_CONF" &
VIRGILD_PID=$!

for _ in $(seq 1 30); do
    curl -fs http://127.0.0.1:8480/api/status >/dev/null && break
    sleep 1
done

# Start Shairport-sync (AirPlay receiver) if enabled
if [ "$AIRPLAY_ENABLED" = "true" ]; then
    echo "[*] Starting Shairport-sync (AirPlay receiver)..."
    shairport-sync -c "$SHAIRPORT_CONF" 2>&1 | tee -a /var/log/dstreamer/shairport.log &
fi

# Start Snapserver (Snapcast) if enabled
if [ "$CHROMECAST_ENABLED" = "true" ]; then
    echo "[*] Starting Snapserver..."
    snapserver -c /app/snapserver.conf 2>&1 | tee -a /var/log/dstreamer/snapserver.log &
fi

# The container lives as long as the Dante engine does
wait $VIRGILD_PID
