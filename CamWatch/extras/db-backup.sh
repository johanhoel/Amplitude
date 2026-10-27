#!/bin/bash
# Nightly dump of the presence database into DATA_PATH/db-backup/, so a file-level / Proxmox backup of the
# data folder always contains a consistent copy (copying MariaDB's live files is not reliable).
# Keeps DB_BACKUP_KEEP_DAYS (default 14) daily dumps. Runs from extras/systemd/camwatch-db-backup.timer.
# Restore: gunzip -c <dump>.sql.gz | mariadb camwatch
set -uo pipefail
set -a; . /opt/camwatch/.env 2>/dev/null; set +a
DB=${DB_NAME:-camwatch}
DEST=${DATA_PATH:-/srv/camwatch/data}/db-backup
KEEP=${DB_BACKUP_KEEP_DAYS:-14}
FILE="$DEST/$DB-$(date +%F).sql.gz"
# ntfy settings from the web UI (extras/ntfy.sh); without it, no pushes
for f in /opt/camwatch/extras/ntfy.sh "$(dirname "$0")/ntfy.sh"; do [ -r "$f" ] && . "$f" && break; done
type ntfy_post >/dev/null 2>&1 || ntfy_post() { :; }

notify() {   # title, message
    ntfy_post "${NTFY_STATUS_TOPIC:-${NTFY_TOPIC:-}}" "$1" default status,warning "$2"
}

mkdir -p "$DEST" && chmod 700 "$DEST"
if ! mariadb-dump --single-transaction --routines --triggers --databases "$DB" | gzip > "$FILE.tmp" \
   || [ ! -s "$FILE.tmp" ]; then
    rm -f "$FILE.tmp"
    echo "database dump FAILED" >&2
    notify "camwatch: database backup failed" "The nightly dump of the presence database failed; check 'journalctl -u camwatch-db-backup'."
    exit 1
fi
mv "$FILE.tmp" "$FILE"
find "$DEST" -name "$DB-*.sql.gz" -mtime +"$KEEP" -delete
echo "dumped $(du -h "$FILE" | cut -f1) to $FILE"
