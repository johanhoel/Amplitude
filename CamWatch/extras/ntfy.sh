# Sourced by the host scripts (db-backup.sh, icloud-sync.sh) after .env: the ntfy settings saved on the web UI's
# Settings page (DATA_PATH/settings.json) replace the .env values, and ntfy_post sends with the token or login.
_settings="${DATA_PATH:-/srv/camwatch/data}/settings.json"
if [ -r "$_settings" ] && command -v python3 >/dev/null; then
    eval "$(python3 - "$_settings" <<'PY'
import json, shlex, sys
try:
    saved = json.load(open(sys.argv[1])).get("ntfy") or {}
except (OSError, ValueError):
    saved = {}
names = {"url": "NTFY_URL", "topic": "NTFY_TOPIC", "status_topic": "NTFY_STATUS_TOPIC", "token": "NTFY_TOKEN",
         "user": "NTFY_USER", "password": "NTFY_PASSWORD"}
for key, var in names.items():
    if key in saved:
        print(f"{var}={shlex.quote(str(saved[key]))}")
PY
)"
fi
[ "${NTFY_TOPIC:-}" = CHANGE_ME ] && NTFY_TOPIC=

ntfy_post() {   # topic title priority tags message
    [ -n "$1" ] || return 0
    local auth=()
    if [ -n "${NTFY_TOKEN:-}" ]; then
        auth=(-H "Authorization: Bearer $NTFY_TOKEN")
    elif [ -n "${NTFY_USER:-}" ]; then
        auth=(-H "Authorization: Basic $(printf '%s:%s' "$NTFY_USER" "${NTFY_PASSWORD:-}" | base64 -w0)")
    fi
    curl -s -m 10 "${auth[@]}" -H "Title: $2" -H "Priority: $3" -H "Tags: $4" \
         -d "$5" "${NTFY_URL:-https://ntfy.sh}/$1" >/dev/null || true
}
