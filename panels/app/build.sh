#!/bin/bash
# Build the signed Home Deck APK in Docker -> dist/homedeck.apk + dist/version.json.
# Usage: ./build.sh ["what changed"]      (versionCode = yymmddHH, versionName = yyyy.mm.dd-HHMM)
set -euo pipefail
cd "$(dirname "$0")"
VC=$(date +%y%m%d%H); VN=$(date +%Y.%m.%d-%H%M); NOTES=${1:-}
mkdir -p dist cache
docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -e HD_KEYSTORE=/signing/homedeck.jks -e HD_KS_PASS="$(cat signing/pass)" \
  -v "$PWD/android:/src" -v "$PWD/signing:/signing:ro" -v "$PWD/cache:/cache" --memory 3g \
  homedeck-android-builder gradle --no-daemon -q assembleRelease -Pvc="$VC" -Pvn="$VN"
cp android/app/build/outputs/apk/release/app-release.apk dist/homedeck.apk
python3 -c 'import json,sys; print(json.dumps({"code": int(sys.argv[1]), "name": sys.argv[2], "notes": sys.argv[3]}))' "$VC" "$VN" "$NOTES" > dist/version.json
ls -l dist; cat dist/version.json
