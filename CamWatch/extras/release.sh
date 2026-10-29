#!/usr/bin/env bash
# Install a new camwatch version with automatic rollback. Reads the code as a tar archive on stdin:
#   git archive HEAD | ssh root@<host> "bash /tmp/camwatch-release.sh staging"      (dev/release.ps1 does this)
#   release.sh <staging|production> [--force]
# staging    = /opt/camwatch-staging: fake camera, port 8090, own data, no pushes (created on first use)
# production = /opt/camwatch
# Steps: refuse while someone is mid-setup in Settings -> back up the running code (last 5 kept in .releases/) ->
# install, build, start -> wait until every container is healthy -> if not within 5 min, put the backup back.
set -euo pipefail
target=${1:?usage: release.sh staging|production [--force]  (code as tar on stdin)}
force=${2:-}
case $target in
  production) dir=/opt/camwatch ;;
  staging) dir=/opt/camwatch-staging ;;
  *) echo "unknown target: $target" >&2; exit 2 ;;
esac
CODE="app extras models tests Dockerfile docker-compose.yml docker-compose.staging.yml docker-compose.gpu-intel.yml docker-compose.gpu-nvidia.yml requirements.txt deploy.sh README.md HANDOVER.md AGENTS.md"

new=$(mktemp -d)
trap 'rm -rf "$new"' EXIT
tar xf - -C "$new"
if [ ! -f "$new/docker-compose.yml" ] || [ ! -d "$new/app" ]; then
  echo "the archive on stdin is not camwatch" >&2; exit 2
fi
mkdir -p "$dir"
cd "$dir"

if [ "$target" = staging ] && [ ! -f .env ]; then
  cp "$new/extras/staging.env.example" .env
  pw=$(head -c 18 /dev/urandom | base64 | tr -d '/+=')
  sed -i "s/^WEB_PASSWORD=.*/WEB_PASSWORD=$pw/" .env
  host_ip=$(hostname -I | awk '{print $1}')
  sed -i "s#^WEB_BASE_URL=.*#WEB_BASE_URL=http://$host_ip:8090#" .env
  chmod 600 .env
  mkdir -p /srv/camwatch/staging/recordings /srv/camwatch/staging/photos /srv/camwatch/staging/data
  echo ">> new staging: http://$host_ip:8090  login admin / $pw  (in $dir/.env)"
fi
[ -f .env ] || { echo "$dir/.env is missing - set up $target first (deploy.sh)" >&2; exit 2; }

# A restart in the middle of a multi-step setup (e.g. iCloud's two-factor step) breaks it for the user
prefix=$(grep -E '^CAMWATCH_PREFIX=' .env | tail -1 | cut -d= -f2- || true)   # production has none (pipefail!)
prefix=${prefix:-camwatch}
if [ "$force" != --force ] && docker logs --since 3m "$prefix-webui" 2>&1 | grep -q "off-site connect"; then
  echo "someone is setting up off-site storage right now - try again in a few minutes (or add --force)" >&2
  exit 3
fi

# Containers that are already broken before the update (e.g. presence without a database) must not make the update
# fail: the health check below skips them, and lists them at the end
broken_before=$(docker compose ps -a --format '{{.Name}} {{.Status}}' 2>/dev/null | grep -E 'unhealthy|Restarting|Exited' | cut -d' ' -f1 || true)

stamp=$(date +%Y%m%d-%H%M%S)
backup="$dir/.releases/$stamp"
first_install=true
mkdir -p "$backup"
for f in $CODE; do
  if [ -e "$f" ]; then cp -a "$f" "$backup/"; first_install=false; fi
done
ls -1dt "$dir"/.releases/*/ 2>/dev/null | tail -n +6 | xargs -r rm -rf
echo ">> backup of the running code: $backup"

install_from() {
  for f in $CODE; do
    [ -e "$1/$f" ] || continue
    rm -rf "${dir:?}/$f"
    cp -a "$1/$f" "$dir/"
  done
  docker compose build -q recorder && docker compose up -d --remove-orphans
}

healthy() {
  # every container up; those with a healthcheck healthy. Recorders need up to 2 min for their first video.
  for _ in $(seq 60); do
    states=$(docker compose ps -a --format '{{.Name}} {{.Status}}')
    judged=$states
    for c in $broken_before; do judged=$(echo "$judged" | grep -v "^$c " || true); done
    if ! echo "$judged" | grep -qE 'health: starting|unhealthy|Restarting|Exited|Created'; then
      echo "$states"; return 0
    fi
    sleep 5
  done
  echo "$states"
  return 1
}

echo ">> installing and starting"
if install_from "$new" && healthy; then
  docker image prune -f >/dev/null
  docker builder prune -f --filter until=72h >/dev/null   # build cache from older releases (it fills the system disk)
  echo ">> $target is running the new version"
  [ -n "$broken_before" ] && echo ">> these did not work before the update either, so they did not count: $(echo $broken_before)"
  bash "$dir/extras/install-updater.sh" "$dir" || echo "!! the update button helper did not install" >&2
  exit 0
fi

echo "!! the new version did not become healthy" >&2
docker compose ps -a >&2
for c in $(docker compose ps -a --format '{{.Name}} {{.Status}}' | grep -E 'unhealthy|Restarting|Exited' | cut -d' ' -f1); do
  echo "--- $c" >&2; docker logs --tail 25 "$c" >&2 || true
done
if $first_install; then
  echo "!! first install - nothing to roll back to" >&2; exit 1
fi
echo ">> rolling back to $backup" >&2
if install_from "$backup" && healthy >/dev/null; then
  echo ">> rolled back: $target runs the previous version again" >&2
else
  echo "!! the rollback is not healthy either - look at 'docker compose ps' in $dir" >&2
fi
exit 1
