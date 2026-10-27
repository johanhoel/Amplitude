#!/bin/bash
# Put the built app on Home Deck (.52): www/app/homedeck.apk + version.json. Phones offer the update when opened.
set -euo pipefail
cd "$(dirname "$0")"
[ -f dist/homedeck.apk ] && [ -f dist/version.json ]
tar cf - -C dist homedeck.apk version.json | ssh root@192.168.1.52 'set -e; mkdir -p /opt/panel-wrapper/www/app; cd /opt/panel-wrapper/www/app;
  [ -f homedeck.apk ] && cp -p homedeck.apk homedeck.apk.prev && cp -p version.json version.json.prev || true
  tar xf - --no-same-owner; chmod 644 homedeck.apk version.json; cat version.json'
