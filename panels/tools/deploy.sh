#!/bin/bash
# Deploy server/ to Home Deck (.52): refuse if live was changed by hand since the last deploy,
# compile-check, snapshot, upload, then homedeck-apply (checks settings, restarts, rolls back if the panels stop answering).
# The owner runs this; coding agents never do.
set -euo pipefail
cd "$(dirname "$0")/.."
H=root@192.168.1.52; R=/opt/panel-wrapper
[ -z "$(git status --porcelain server)" ] || { echo "Commit your changes first."; exit 1; }
if [ -f .deployed.md5 ]; then
  ssh $H "cd $R && md5sum -c --quiet" < .deployed.md5 \
    || { echo "Live files changed since the last deploy. Run tools/pull-live.sh, commit, and try again."; exit 1; }
else
  echo "First deploy from this repo: checking that live still matches the repo ..."
  tmp=$(mktemp -d); ssh $H "cd $R && tar czf - --exclude='*.bak-*' --exclude='__pycache__' --exclude='www/app' homedeck www server.py homedeck.toml" | tar xzf - -C "$tmp"
  if ! diff -rq "$tmp" server >/dev/null; then diff -rq "$tmp" server | head; rm -rf "$tmp"; echo "Live differs from the repo: run tools/pull-live.sh first."; exit 1; fi
  rm -rf "$tmp"
fi
python3 -m py_compile server/homedeck/*.py server/server.py
stamp=$(date +%Y%m%d-%H%M%S)
tar czf - --exclude='__pycache__' --exclude='www/app' -C server homedeck www server.py homedeck.toml \
  | ssh $H "set -e; cd $R; tar czf .snapshots/predeploy-$stamp.tgz homedeck www server.py homedeck.toml; \
            tar xzf - --no-same-owner; /usr/local/sbin/homedeck-apply"
(cd server && find homedeck www server.py homedeck.toml -type f ! -path '*/__pycache__/*' -print0 | xargs -0 md5sum) > .deployed.md5
git tag "deploy-$stamp" && echo "Deployed and tagged deploy-$stamp"
