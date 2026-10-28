#!/usr/bin/env bash
# Build <Project>.dmg for each project on a Mac (GitHub Actions: macos-latest). Output in dist/.
# Signs and notarizes when these are set (GitHub secrets), else builds unsigned:
#   MACOS_CERT_P12        base64 of the "Developer ID Application" certificate (.p12)
#   MACOS_CERT_PASSWORD   the .p12 password
#   APPLE_ID, APPLE_TEAM_ID, APPLE_APP_PASSWORD   for notarization (an app-specific password from appleid.apple.com)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/../../dist"; mkdir -p "$OUT"
WORK=$(mktemp -d)
IDENTITY=""

if [ -n "${MACOS_CERT_P12:-}" ]; then
  KC="$WORK/build.keychain"; KCPW=$(openssl rand -hex 16)
  security create-keychain -p "$KCPW" "$KC"
  security set-keychain-settings -lut 3600 "$KC"
  security unlock-keychain -p "$KCPW" "$KC"
  echo "$MACOS_CERT_P12" | base64 --decode > "$WORK/cert.p12"
  security import "$WORK/cert.p12" -k "$KC" -P "$MACOS_CERT_PASSWORD" -T /usr/bin/codesign
  security set-key-partition-list -S apple-tool:,apple: -s -k "$KCPW" "$KC" >/dev/null
  security list-keychains -d user -s "$KC" $(security list-keychains -d user | tr -d '"')
  IDENTITY=$(security find-identity -v -p codesigning "$KC" | grep -o '"Developer ID Application[^"]*"' | head -1 | tr -d '"')
  [ -n "$IDENTITY" ] || { echo "no Developer ID Application certificate in MACOS_CERT_P12" >&2; exit 1; }
  echo "signing as: $IDENTITY"
else
  echo "no certificate: building unsigned"
fi

for entry in "camwatch:CamWatch" "homedeck:Home Deck" "dantestreamer:DanteStreamer"; do
  project=${entry%%:*}; name=${entry#*:}; file=${name// /}
  app="$WORK/$name.app"
  osacompile -o "$app" "$HERE/applet.applescript"
  sed -e "s/__PROJECT__/$project/" -e "s/__NAME__/$name/" "$HERE/install.command" > "$app/Contents/Resources/install.command"
  chmod +x "$app/Contents/Resources/install.command"
  plist="$app/Contents/Info.plist"
  /usr/libexec/PlistBuddy -c "Set :CFBundleName $name" "$plist"
  /usr/libexec/PlistBuddy -c "Delete :CFBundleIdentifier" "$plist" 2>/dev/null || true
  /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string io.github.johanhoel.amplitude.$project" "$plist"
  if [ -n "$IDENTITY" ]; then
    codesign --force --deep --options runtime --timestamp --sign "$IDENTITY" "$app"
  fi
  stage="$WORK/stage-$project"; mkdir -p "$stage"
  cp -R "$app" "$stage/"
  ln -s /Applications "$stage/Applications"
  hdiutil create -quiet -volname "$name" -srcfolder "$stage" -ov -format UDZO "$OUT/$file.dmg"
  if [ -n "$IDENTITY" ]; then
    codesign --force --timestamp --sign "$IDENTITY" "$OUT/$file.dmg"
    if [ -n "${APPLE_ID:-}" ]; then
      xcrun notarytool submit "$OUT/$file.dmg" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" \
        --password "$APPLE_APP_PASSWORD" --wait
      xcrun stapler staple "$OUT/$file.dmg"
    fi
  fi
  echo "built $file.dmg"
done
ls -la "$OUT"
