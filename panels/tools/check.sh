#!/bin/bash
# Everything a change must pass: Python compiles, settings + modules check, and (when staging runs) the page smoke test.
set -euo pipefail
cd "$(dirname "$0")/.."
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
python3 -m py_compile server/homedeck/*.py server/server.py services/camwatch-feed/feed.py && echo "OK   python compiles"
(cd server && sed 's#__HA_URL__#http://127.0.0.1:8123#' homedeck.toml > "$T/homedeck.toml" && \
  HOMEDECK_ROOT=$PWD HOMEDECK_CONFIG="$T/homedeck.toml" HOMEDECK_READONLY=1 STATE_DIRECTORY="$T" python3 -m homedeck.check)
if curl -s -o /dev/null -m 3 "${BASE:-http://localhost:8099}/api/health"; then
  if python3 -c 'import playwright' 2>/dev/null; then
    BASE="${BASE:-http://localhost:8099}" python3 tests/smoke.py
  elif command -v docker >/dev/null; then
    docker run --rm --network host -e BASE="${BASE:-http://localhost:8099}" -v "$PWD":/w mcr.microsoft.com/playwright/python:v1.48.0-noble \
      sh -c 'pip install -q playwright==1.48.0 2>/dev/null && python3 /w/tests/smoke.py'
  else
    echo "SKIP smoke test: no playwright and no docker (pip install playwright && playwright install chromium)"
  fi
else
  echo "SKIP smoke test: staging is not running (HOMEDECK_STUB=1 tools/staging.sh)"
fi
