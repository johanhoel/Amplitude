#!/usr/bin/env bash
# Install or update one project on a fresh Debian/Ubuntu machine, without questions.
# The Mac (.dmg) installer runs this inside its Linux machine; on a Linux box or a Pi, run it directly:
#   curl -fsSL https://raw.githubusercontent.com/johanhoel/amplitude/main/installers/linux/setup.sh | sudo bash -s camwatch
#   setup.sh camwatch | homedeck | dstreamer
# It keeps a copy of the repository in /opt/amplitude (updated on every run), then runs the project's own installer.
# At the end it writes /root/<project>-install.txt: the address and, for CamWatch, the login. The installers show it.
set -euo pipefail
PROJECT=${1:?usage: setup.sh camwatch|homedeck|dstreamer}
SRC=/opt/amplitude
REPO_URL=${AMPLITUDE_REPO:-https://github.com/johanhoel/amplitude.git}
say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || die "run as root"
. /etc/os-release
case "$ID" in debian|ubuntu) ;; *) die "Debian or Ubuntu needed (found $PRETTY_NAME)" ;; esac
export DEBIAN_FRONTEND=noninteractive

say "Base packages"
apt-get update -qq
apt-get install -y -qq git curl ca-certificates openssl >/dev/null

say "Code from GitHub"
if [ -d "$SRC/.git" ]; then
  git -C "$SRC" fetch -q origin && git -C "$SRC" reset -q --hard origin/main
else
  git clone -q "$REPO_URL" "$SRC"
fi

docker_install() {
  command -v docker >/dev/null && docker compose version >/dev/null 2>&1 && return
  say "Docker"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
  systemctl enable --now docker
}

host_ip() { hostname -I 2>/dev/null | awk '{print $1}'; }
secret() { openssl rand -base64 18 | tr -d '/+=' | cut -c1-20; }

case "$PROJECT" in
camwatch)
  docker_install
  say "Database (MariaDB) for the visit log"
  apt-get install -y -qq mariadb-server >/dev/null
  systemctl enable --now mariadb
  ENV=/opt/camwatch/.env
  if [ -f "$ENV" ]; then
    say "CamWatch is installed already: updating, settings stay"
  else
    say "First settings"
    db_pw=$(secret); web_pw=$(secret)
    mariadb -e "CREATE DATABASE IF NOT EXISTS camwatch; CREATE USER IF NOT EXISTS 'camwatch'@'localhost' IDENTIFIED BY '$db_pw'; ALTER USER 'camwatch'@'localhost' IDENTIFIED BY '$db_pw'; GRANT ALL ON camwatch.* TO 'camwatch'@'localhost';"
    tz=${HOST_TZ:-$(cat /etc/timezone 2>/dev/null || echo Etc/UTC)}
    mkdir -p /opt/camwatch
    # no camera yet: slot 1 waits until you add a camera in Settings -> Cameras
    sed -e "s#^RTSP_URL=.*#RTSP_URL=#" -e "s#^TZ=.*#TZ=$tz#" \
        -e "s#^RECORDINGS_PATH=.*#RECORDINGS_PATH=${CAMWATCH_RECORDINGS:-/srv/camwatch/recordings}#" \
        -e "s#^PHOTOS_PATH=.*#PHOTOS_PATH=/srv/camwatch/photos#" -e "s#^DATA_PATH=.*#DATA_PATH=/srv/camwatch/data#" \
        -e "s#^WEB_BASE_URL=.*#WEB_BASE_URL=#" -e "s#^WEB_PASSWORD=.*#WEB_PASSWORD=$web_pw#" \
        -e "s#^DB_PASSWORD=.*#DB_PASSWORD=$db_pw#" "$SRC/CamWatch/.env.example" > "$ENV"
    chmod 600 "$ENV"
    printf 'CamWatch login\nUser: admin\nPassword: %s\n(change it in /opt/camwatch/.env: WEB_PASSWORD)\n' "$web_pw" > /root/camwatch-login.txt
    chmod 600 /root/camwatch-login.txt
  fi
  say "CamWatch: build and start (the first time takes 5-15 minutes)"
  "$SRC/CamWatch/deploy.sh"
  port=$(grep -E '^WEB_PORT=' "$ENV" | cut -d= -f2-); port=${port:-8080}
  { echo "CamWatch runs."
    echo "Open: http://$(host_ip):$port"
    [ -f /root/camwatch-login.txt ] && sed -n 2,3p /root/camwatch-login.txt
    echo "Next: Settings -> Cameras -> Find, to add your cameras."; } > /root/camwatch-install.txt
  ;;
homedeck)
  say "Home Deck"
  bash "$SRC/panels/install.sh"
  { echo "Home Deck runs."
    echo "Setup wizard: http://$(host_ip):8089"
    echo "Panels: http://$(host_ip)/start"; } > /root/homedeck-install.txt
  ;;
dstreamer)
  docker_install
  say "DStreamer"
  cd "$SRC/dstreamer"
  [ -f .env ] || cp .env.example .env
  docker compose up -d --build
  { echo "DStreamer runs."
    echo "Control panel: http://127.0.0.1:8480 on this machine"
    echo "AirPlay name: see .env in $SRC/dstreamer"
    echo "Dante needs direct access to the network: in WSL or a virtual machine audio can drop out."; } > /root/dstreamer-install.txt
  ;;
*) die "unknown project: $PROJECT (camwatch, homedeck or dstreamer)" ;;
esac

say "Done"
cat "/root/$PROJECT-install.txt"
