#!/bin/bash
# Everything a change must pass: Python compiles, settings + modules check, and (when staging runs) the page smoke test.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m py_compile server/homedeck/*.py server/server.py services/camwatch-feed/feed.py && echo "OK   python compiles"
(cd server && HOMEDECK_ROOT=$PWD HOMEDECK_CONFIG=$PWD/homedeck.toml HOMEDECK_READONLY=1 STATE_DIRECTORY=$(mktemp -d) python3 -m homedeck.check)
if curl -s -o /dev/null -m 3 "${BASE:-http://localhost:8099}/api/health"; then
  docker run --rm --network host -e BASE="${BASE:-http://localhost:8099}" -v "$PWD":/w mcr.microsoft.com/playwright/python:v1.48.0-noble \
    sh -c 'pip install -q playwright==1.48.0 2>/dev/null && python3 /w/tests/smoke.py'
else
  echo "SKIP smoke test: staging is not running (tools/staging.sh)"
fi
