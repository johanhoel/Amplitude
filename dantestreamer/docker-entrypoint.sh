#!/bin/bash
set -e

# DanteStreamer Entrypoint - Start all services

echo "=== DanteStreamer Startup ==="

# Load environment or use defaults
DANTE_LOG_LEVEL=${DANTE_LOG_LEVEL:-info}
AIRPLAY_ENABLED=${AIRPLAY_ENABLED:-true}
CHROMECAST_ENABLED=${CHROMECAST_ENABLED:-false}

# Create log directory
mkdir -p /var/log/dantestreamer
chown -R dante:dante /var/log/dantestreamer

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
/app/virgild -c /app/virgil.conf &
VIRGILD_PID=$!

for _ in $(seq 1 30); do
    curl -fs http://127.0.0.1:8480/api/status >/dev/null && break
    sleep 1
done

# Start Shairport-sync (AirPlay receiver) if enabled
if [ "$AIRPLAY_ENABLED" = "true" ]; then
    echo "[*] Starting Shairport-sync (AirPlay receiver)..."
    shairport-sync -c /app/shairport-sync.conf 2>&1 | tee -a /var/log/dantestreamer/shairport.log &
fi

# Start Snapserver (Snapcast) if enabled
if [ "$CHROMECAST_ENABLED" = "true" ]; then
    echo "[*] Starting Snapserver..."
    snapserver -c /app/snapserver.conf 2>&1 | tee -a /var/log/dantestreamer/snapserver.log &
fi

# The container lives as long as the Dante engine does
wait $VIRGILD_PID
