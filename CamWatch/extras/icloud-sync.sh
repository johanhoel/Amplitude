#!/bin/bash
# camwatch -> iCloud Drive: copies every STARRED clip (recordings/<day>/<stem>.star) to an SMB share
# that is the iCloudDrive\Camwatch folder on a Windows PC (iCloud for Windows uploads it).
# Runs every 2 min from extras/systemd/icloud-sync.timer.
#  - Each clip is sent once (state file); unstarring later does NOT delete it from iCloud.
#  - PC off / share unreachable: nothing is lost, it retries on the next run.
#  - Names: Camwatch/2026-10/2026-10-18 10.34.34 camera1.mp4 (+ .jpg snapshot)
# Settings in /opt/camwatch/.env:
#   ICLOUD_SHARE  //<pc-ip>/<share>   required; the script does nothing without it
#   ICLOUD_CRED   smbclient auth file (default /etc/camwatch-icloud.cred, mode 600, lines
#                 "username = ..." and "password = ...")
#   RECORDINGS_PATH / DATA_PATH       same values as used by docker compose
set -u
set -a; . /opt/camwatch/.env 2>/dev/null; set +a
REC=${RECORDINGS_PATH:-/srv/camwatch/recordings}
DATA=${DATA_PATH:-/srv/camwatch/data}
STATE=$DATA/icloud-uploaded.txt
FAILING=$DATA/icloud-failing-since
CRED=${ICLOUD_CRED:-/etc/camwatch-icloud.cred}
SHARE=${ICLOUD_SHARE:-}
[ -n "$SHARE" ] || exit 0
LOCK=/run/icloud-sync.lock
exec 9>"$LOCK"; flock -n 9 || exit 0
touch "$STATE"

# ntfy settings from the web UI (extras/ntfy.sh); without it, no pushes
for f in /opt/camwatch/extras/ntfy.sh "$(dirname "$0")/ntfy.sh"; do [ -r "$f" ] && . "$f" && break; done
type ntfy_post >/dev/null 2>&1 || ntfy_post() { :; }
notify() {   # title, message, priority
    ntfy_post "${NTFY_TOPIC:-}" "$1" "${3:-low}" cloud "$2"
}

mapfile -t STARS < <(find "$REC" -mindepth 2 -maxdepth 2 -name '*.star' | sort)
[ ${#STARS[@]} -eq 0 ] && exit 0

for star in "${STARS[@]}"; do
    day=$(basename "$(dirname "$star")"); stem=$(basename "$star" .star)
    key="$day/$stem"
    grep -qxF "$key" "$STATE" && continue
    mp4="$REC/$day/$stem.mp4"; jpg="$REC/$day/$stem.jpg"
    if [ ! -f "$mp4" ]; then echo "skip $key: no mp4"; continue; fi
    cam=${stem%_*}; t=${stem##*_}
    name="$day ${t:0:2}.${t:2:2}.${t:4:2} $cam"
    month=${day:0:7}
    cmds="mkdir \"$month\"; cd \"$month\"; put \"$mp4\" \"$name.mp4\""
    [ -f "$jpg" ] && cmds="$cmds; put \"$jpg\" \"$name.jpg\""
    out=$(smbclient "$SHARE" -A "$CRED" -m SMB3 -t 60 -c "$cmds" 2>&1)
    # "mkdir" fails harmlessly when the month folder exists; check the puts
    if echo "$out" | grep -qE "NT_STATUS_(ACCESS_DENIED|LOGON_FAILURE|BAD_NETWORK_NAME|OBJECT_PATH_NOT_FOUND|DISK_FULL|HOST_UNREACHABLE|IO_TIMEOUT|CONNECTION_REFUSED|NETWORK_UNREACHABLE)|Connection to .* failed|failed to connect|Unable to connect"; then
        echo "$(date '+%F %T') FAILED $key: $(echo "$out" | grep -m1 -E 'NT_STATUS|Connection|connect')"
        # remember the first failure time; warn once after 24 h of failures
        [ -f "$FAILING" ] || date +%s > "$FAILING"
        if [ $(( $(date +%s) - $(cat "$FAILING") )) -gt 86400 ] && [ ! -f "$FAILING.notified" ]; then
            notify "iCloud copy failing" "Starred clips have not reached the PC share for 24 h (PC off or share changed). They are kept and will be sent later." default
            touch "$FAILING.notified"
        fi
        exit 1
    fi
    echo "$key" >> "$STATE"
    rm -f "$FAILING" "$FAILING.notified"
    echo "$(date '+%F %T') sent $key -> Camwatch/$month/$name.mp4"
    notify "Clip saved to iCloud" "$name ($(du -h "$mp4" | cut -f1))"
done
