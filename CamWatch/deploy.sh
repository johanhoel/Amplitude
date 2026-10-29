#!/usr/bin/env bash
# Run on the Debian LXC from the copied camwatch folder:  sudo ./deploy.sh
set -euo pipefail
cd "$(dirname "$0")"
INSTALL_DIR=/opt/camwatch

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo ./deploy.sh" >&2
  exit 1
fi

if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  echo ">> Installing Docker"
  apt-get update
  apt-get install -y ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  . /etc/os-release                 # Docker has a package source per system: debian or ubuntu
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
fi

if ! docker run --rm hello-world >/dev/null 2>&1; then
  echo "Docker cannot start containers. In Proxmox enable nesting (and keyctl for unprivileged):" >&2
  echo "  pct set <CTID> --features nesting=1,keyctl=1 && pct reboot <CTID>" >&2
  exit 1
fi

echo ">> Copying files to $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -r Dockerfile docker-compose.yml docker-compose.gpu-intel.yml docker-compose.gpu-nvidia.yml requirements.txt .env.example README.md HANDOVER.md deploy.sh app models extras "$INSTALL_DIR"/
[ -f .env ] && [ ! -f "$INSTALL_DIR/.env" ] && cp .env "$INSTALL_DIR/.env"
# A git clone has no commit in app/BUILD (only `git archive` fills it in); without it the update check can't tell versions apart
if grep -q '^\$Format' "$INSTALL_DIR/app/BUILD" 2>/dev/null; then
  git log -1 --format='%h %cs' > "$INSTALL_DIR/app/BUILD" 2>/dev/null || true
fi
if [ ! -f "$INSTALL_DIR/.env" ]; then
  cp .env.example "$INSTALL_DIR/.env"
  chmod 600 "$INSTALL_DIR/.env"
  echo "Created $INSTALL_DIR/.env - edit it (RTSP_URL, NTFY_TOPIC, paths), then re-run sudo ./deploy.sh" >&2
  exit 1
fi
chmod 600 "$INSTALL_DIR/.env"
cd "$INSTALL_DIR"

if grep -qE '^RTSP_URL=.*CHANGE_ME' .env; then
  echo "Edit RTSP_URL in $INSTALL_DIR/.env first (notifications can be set later on the web UI's Settings page)" >&2
  exit 1
fi

setting() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }
for var in RECORDINGS_PATH PHOTOS_PATH DATA_PATH; do
  dir="$(setting "$var")"
  if [ -n "$dir" ]; then
    mkdir -p "$dir"
  fi
done

# cameras are set on the Settings page now; drop the short-lived cameras.sh setup
sed -i '/^COMPOSE_FILE=docker-compose.yml:docker-compose.cameras.yml$/d' .env
rm -rf cameras.sh docker-compose.cameras.yml
[ -f "$(setting DATA_PATH)/settings.json" ] && chmod 600 "$(setting DATA_PATH)/settings.json"

echo ">> Building and starting"
docker compose up -d --build --remove-orphans
docker compose ps
bash extras/install-updater.sh "$INSTALL_DIR" || echo "The update button helper did not install (Settings -> Updates)" >&2
echo
echo "Follow logs with:  cd $INSTALL_DIR && sudo docker compose logs -f"
