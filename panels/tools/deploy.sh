#!/bin/bash
# Deploy server/ to Home Deck (.52). The only way to production; it rolls back by itself.
#
# The repository is public and holds placeholders (192.168.1.x, home.example.net, sample names). This house's own
# values stay on the server: homedeck.toml (the settings) and private.map (placeholder ==> real value, see
# tools/private.py). So a deploy:
#   1. refuses when live was changed by hand since the last deploy (or, the first time, prints what differs);
#   2. builds a copy of server/ with private.map applied - homedeck.toml is never uploaded;
#   3. tries that copy on the server first: settings check, then a trial Home Deck on port 8099 with the real
#      settings, read-only, and every page must answer;
#   4. snapshots live, uploads the copy, runs homedeck-apply (checks, restarts, rolls back if the panels stop).
# Usage: tools/deploy.sh [--accept-live]     --accept-live: replace live although it differs (after you checked it)
set -euo pipefail
cd "$(dirname "$0")/.."
H=root@192.168.100.52; R=/opt/panel-wrapper
PY=$(for p in python3 python py; do "$p" -c "import sys" 2>/dev/null && { echo "$p"; break; }; done)
FILES="homedeck www server.py"
accept=${1:-}
[ -z "$(git status --porcelain server tools)" ] || { echo "Commit your changes first."; exit 1; }

work=$(mktemp -d .work-XXXXXX); trap 'rm -rf "$work"' EXIT
echo "1/4  Private values from the server ..."
ssh $H "cat $R/private.map" > "$work/private.map" \
  || { echo "No $R/private.map on the server: without it the panels would get the placeholders."; exit 1; }
mkdir "$work/build"
git -C "$(git rev-parse --show-toplevel)" archive HEAD:panels/server $FILES | tar xf - -C "$work/build"      # what is committed, with Linux line endings
"$PY" tools/private.py apply "$work/private.map" "$work/build"
"$PY" -m py_compile "$work"/build/homedeck/*.py "$work/build/server.py"
find "$work/build" -name __pycache__ -type d -prune -exec rm -rf {} +
(cd "$work/build" && find $FILES -type f -print0 | sort -z | xargs -0 md5sum) > "$work/build.md5"

if [ -f .deployed.md5 ]; then
  ssh $H "cd $R && md5sum -c --quiet" < .deployed.md5 \
    || { echo "Live files changed since the last deploy. Run tools/pull-live.sh, commit, and try again."; exit 1; }
elif [ "$accept" != --accept-live ]; then
  mkdir "$work/live"
  ssh $H "cd $R && tar czf - --exclude='*.bak-*' --exclude='__pycache__' --exclude='www/app' $FILES" | tar xzf - -C "$work/live"
  if ! diff -rq --strip-trailing-cr "$work/live" "$work/build" >/dev/null; then
    diff -rq --strip-trailing-cr "$work/live" "$work/build" | sed "s#$work/##g" | head -20
    echo "First deploy from this repo, and live differs from it (above). Check the differences, then run"
    echo "tools/deploy.sh --accept-live to replace live."
    exit 1
  fi
fi

echo "2/4  Trying the new version on the server (port 8099, real settings, read-only) ..."
try=/tmp/homedeck-try
tar czf - -C "$work/build" $FILES | ssh $H "rm -rf $try && mkdir -p $try/state && chmod 700 $try && tar xzf - -C $try --no-same-owner"
pages=$(cd "$work/build/www" && ls *.html | sed 's/\.html$//' | grep -vE '^(index|offline|setup|board)$' | tr '\n' ' ')
ssh $H "set -e; cd $try
  sed 's#^static_dir = .*#static_dir = \"$try/www\"#' $R/homedeck.toml > state/homedeck.toml
  cp /var/lib/panel-wrapper/secrets.json state/ 2>/dev/null || true
  export HOMEDECK_ROOT=$try HOMEDECK_CONFIG=$try/state/homedeck.toml STATE_DIRECTORY=$try/state HOMEDECK_READONLY=1 HOMEDECK_NO_BACKGROUND=1
  $R/venv/bin/python3 -m homedeck.check
  HOMEDECK_PORT=8099 $R/venv/bin/python3 server.py > state/try.log 2>&1 & pid=\$!
  trap 'kill \$pid 2>/dev/null; rm -rf $try' EXIT
  for i in \$(seq 1 25); do sleep 1; curl -fs -m 3 -o /dev/null http://127.0.0.1:8099/api/health && break; done
  bad=''
  for p in health $pages; do
    case \$p in health) u=/api/health;; *) u=/\$p;; esac
    code=\$(curl -s -m 10 -o /dev/null -w '%{http_code}' http://127.0.0.1:8099\$u)
    case \$code in 200|302|401) ;; *) bad=\"\$bad \$u(\$code)\";; esac
  done
  if [ -n \"\$bad\" ]; then echo \"Pages that failed:\$bad\"; tail -20 state/try.log; exit 1; fi
  echo \"Every page answers.\""

echo "3/4  Uploading ..."
stamp=$(date +%Y%m%d-%H%M%S)
tar czf - -C "$work/build" $FILES \
  | ssh $H "set -e; cd $R; tar czf .snapshots/predeploy-$stamp.tgz $FILES homedeck.toml; \
            tar xzf - --no-same-owner"
echo "4/4  homedeck-apply (checks, restarts, rolls back when the panels stop answering) ..."
ssh $H "/usr/local/sbin/homedeck-apply"
cp "$work/build.md5" .deployed.md5
git tag "deploy-$stamp" && echo "Deployed and tagged deploy-$stamp"
