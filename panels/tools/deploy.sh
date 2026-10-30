#!/bin/bash
# Deploy server/ to Home Deck (.52) from this PC. It rolls back by itself.
# The update card in Home Deck's Settings does the same from GitHub (kit/homedeck-update).
#
# The repository is public and holds no house. This house's own values stay on the server: homedeck.toml (the
# settings) and private.map (placeholder ==> real value, see tools/private.py). So a deploy:
#   1. refuses when live was changed by hand since the last install (or, the first time, prints what differs);
#   2. builds a copy of server/ from git with private.map applied - homedeck.toml is never uploaded;
#   3. uploads it and runs kit/homedeck-install-tree on the server: a trial on port 8099 with the real settings,
#      a snapshot, the copy, homedeck-apply (rolls back when the panels stop answering);
#   4. keeps the server's updater current (homedeck-update, homedeck-install-tree, homedeck-update.path), so the
#      update card can install the next version by itself.
# Usage: tools/deploy.sh [--accept-live]     --accept-live: replace live although it differs (after you checked it)
set -euo pipefail
cd "$(dirname "$0")/.."
H=root@192.168.100.52; R=/opt/panel-wrapper
PY=$(for p in python3 python py; do "$p" -c "import sys" 2>/dev/null && { echo "$p"; break; }; done)
FILES="homedeck www server.py VERSION"
TOP=$(git rev-parse --show-toplevel)
accept=${1:-}
[ -z "$(git status --porcelain server tools kit)" ] || { echo "Commit your changes first."; exit 1; }
commit=$(git rev-parse HEAD)

work=$(mktemp -d .work-XXXXXX); trap 'rm -rf "$work"' EXIT
echo "1/4  Private values from the server, and a copy built from git ..."
ssh $H "cat $R/private.map" > "$work/private.map" \
  || { echo "No $R/private.map on the server: without it the panels would get the placeholders."; exit 1; }
mkdir "$work/build"
git -C "$TOP" archive HEAD:panels/server $FILES | tar xf - -C "$work/build"      # what is committed, with Linux line endings
"$PY" tools/private.py apply "$work/private.map" "$work/build"
"$PY" -m py_compile "$work"/build/homedeck/*.py "$work/build/server.py"
find "$work/build" -name __pycache__ -type d -prune -exec rm -rf {} +

# The record of the last install lives on the server (homedeck-install-tree writes it), so a deploy from
# another machine, or an update from the card, does not look like a hand edit. Older deploys kept it here.
if ssh $H "test -f $R/.deployed.md5"; then
  ssh $H "cd $R && md5sum -c --quiet .deployed.md5" \
    || { echo "Live files changed since the last install. Run tools/pull-live.sh, commit, and try again."; exit 1; }
elif [ -f .deployed.md5 ]; then
  ssh $H "cd $R && md5sum -c --quiet" < .deployed.md5 \
    || { echo "Live files changed since the last deploy. Run tools/pull-live.sh, commit, and try again."; exit 1; }
elif [ "$accept" != --accept-live ]; then
  mkdir "$work/live"
  ssh $H "cd $R && tar czf - --exclude='*.bak-*' --exclude='__pycache__' --exclude='www/app' homedeck www server.py" | tar xzf - -C "$work/live"
  if ! diff -rq --strip-trailing-cr "$work/live" "$work/build" >/dev/null; then
    diff -rq --strip-trailing-cr "$work/live" "$work/build" | sed "s#$work/##g" | head -20
    echo "First deploy from this repo, and live differs from it (above). Check the differences, then run"
    echo "tools/deploy.sh --accept-live to replace live."
    exit 1
  fi
fi

echo "2/4  The updater on the server ..."
git -C "$TOP" archive HEAD:panels/kit homedeck-update homedeck-install-tree homedeck-update.path homedeck-update.service \
  | ssh $H "set -e; d=\$(mktemp -d); tar xf - -C \$d
            install -m 755 \$d/homedeck-update \$d/homedeck-install-tree /usr/local/sbin/
            install -m 644 \$d/homedeck-update.path \$d/homedeck-update.service /etc/systemd/system/
            rm -rf \$d; systemctl daemon-reload; systemctl enable -q --now homedeck-update.path"

echo "3/4  Uploading, trying and installing ..."
new=/tmp/homedeck-new
tar czf - -C "$work/build" $FILES | ssh $H "rm -rf $new && mkdir -p $new && chmod 700 $new && tar xzf - -C $new --no-same-owner"
ssh $H "/usr/local/sbin/homedeck-install-tree $new $commit; rc=\$?; rm -rf $new; exit \$rc"

echo "4/4  Done."
rm -f .deployed.md5                       # the server keeps the record now
stamp=$(date +%Y%m%d-%H%M%S)
git tag "deploy-$stamp" && echo "Deployed $(git rev-parse --short HEAD) and tagged deploy-$stamp"
