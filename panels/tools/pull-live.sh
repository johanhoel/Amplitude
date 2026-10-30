#!/bin/bash
# Copy what is live on Home Deck into server/. Then `git diff` shows anything changed outside git.
# The house's own values go back to their placeholders first (private.map on the server, tools/private.py),
# and homedeck.toml stays on the server: the repository is public.
set -euo pipefail
cd "$(dirname "$0")/.."
# Where Home Deck runs. Not in the repository: the repository is public, and the address of a
# machine you can SSH into as root is exactly the sort of thing it must not carry. Set it once:
#
#   echo root@homedeck.lan > panels/.deploy-host        (ignored by git)
#
# or per command:  HOMEDECK_HOST=root@homedeck.lan tools/deploy.sh
H=${HOMEDECK_HOST:-$( [ -f .deploy-host ] && tr -d '[:space:]' < .deploy-host )}
[ -n "$H" ] || { echo "No Home Deck to talk to. Put the address in panels/.deploy-host, e.g."
  echo "    echo root@homedeck.lan > panels/.deploy-host"
  echo "or set HOMEDECK_HOST for this command."; exit 1; }
R=/opt/panel-wrapper
PY=$(for p in python3 python py; do "$p" -c "import sys" 2>/dev/null && { echo "$p"; break; }; done)
work=$(mktemp -d .work-XXXXXX); trap 'rm -rf "$work"' EXIT
ssh $H "cat $R/private.map" > "$work/private.map" \
  || { echo "No $R/private.map on the server: refusing to copy private values into git."; exit 1; }
mkdir "$work/live"
ssh $H "cd $R && tar czf - --exclude='*.bak-*' --exclude='__pycache__' --exclude='www/app' homedeck www server.py" \
  | tar xzf - -C "$work/live" --no-same-owner
"$PY" tools/private.py reverse "$work/private.map" "$work/live"
cp -r "$work/live/." server/
git status --short server
