#!/bin/bash
# Put the built app on Home Deck: www/app/homedeck.apk + version.json. Phones offer the update when opened.
# The address comes from panels/.deploy-host or HOMEDECK_HOST, the same as tools/deploy.sh.
set -euo pipefail
cd "$(dirname "$0")"
H=${HOMEDECK_HOST:-$( [ -f ../.deploy-host ] && tr -d '[:space:]' < ../.deploy-host )}
[ -n "$H" ] || { echo "No Home Deck to talk to: put the address in panels/.deploy-host"; exit 1; }
[ -f dist/homedeck.apk ] && [ -f dist/version.json ]
tar cf - -C dist homedeck.apk version.json | ssh "$H" 'set -e; mkdir -p /opt/panel-wrapper/www/app; cd /opt/panel-wrapper/www/app;
  [ -f homedeck.apk ] && cp -p homedeck.apk homedeck.apk.prev && cp -p version.json version.json.prev || true
  tar xf - --no-same-owner; chmod 644 homedeck.apk version.json; cat version.json'
