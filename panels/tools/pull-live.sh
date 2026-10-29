#!/bin/bash
# Copy what is live on Home Deck (.52) into server/. Then `git diff` shows anything changed outside git.
# The house's own values go back to their placeholders first (private.map on the server, tools/private.py),
# and homedeck.toml stays on the server: the repository is public.
set -euo pipefail
cd "$(dirname "$0")/.."
H=root@192.168.100.52; R=/opt/panel-wrapper
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
