#!/bin/bash
# Copy what is live on Home Deck (.52) into server/. Then `git diff` shows anything changed outside git.
set -euo pipefail
cd "$(dirname "$0")/.."
ssh root@192.168.100.52 "cd /opt/panel-wrapper && tar czf - --exclude='*.bak-*' --exclude='__pycache__' \
  --exclude='www/app' homedeck www server.py homedeck.toml" | tar xzf - -C server
git status --short server
