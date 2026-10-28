#!/usr/bin/env bash
# Install the host helper behind Settings -> Updates for one camwatch folder. deploy.sh and release.sh run this.
#   install-updater.sh /opt/camwatch            -> camwatch-update.path / .service
#   install-updater.sh /opt/camwatch-staging    -> camwatch-staging-update.path / .service
# The web UI writes DATA_PATH/update/request.json; the path unit sees it and starts extras/update.py.
set -euo pipefail
dir=${1:?usage: install-updater.sh <camwatch folder>}
command -v systemctl >/dev/null || { echo "no systemd: the update button stays off" >&2; exit 0; }
command -v python3 >/dev/null || { echo "no python3: the update button stays off" >&2; exit 0; }
data=$(grep -E '^DATA_PATH=' "$dir/.env" | tail -1 | cut -d= -f2- || true)
data=${data:-/mnt/hdd/camwatch/data}
name=$(basename "$dir")-update
mkdir -p "$data/update"

cat > "/etc/systemd/system/$name.path" <<EOF
[Unit]
Description=camwatch update button ($dir)

[Path]
PathExists=$data/update/request.json

[Install]
WantedBy=multi-user.target
EOF

cat > "/etc/systemd/system/$name.service" <<EOF
[Unit]
Description=camwatch update ($dir)
After=docker.service

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 $dir/extras/update.py $dir
TimeoutStartSec=90min
EOF

systemctl daemon-reload
systemctl enable --now "$name.path" >/dev/null 2>&1
python3 "$dir/extras/update.py" "$dir" --hello
echo ">> update button ready ($name.path)"
