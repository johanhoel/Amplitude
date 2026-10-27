#!/usr/bin/env bash
# Build homedeck-kit.tar.gz (friend edition) from: src/ (backend + settings template), the owner's current pages
# (converted by build_www.py), the editor (patched for home-network access) and kit/ (installer, services, commands).
#   ./build_kit.sh [version]      -> dist/homedeck-kit.tar.gz + .sha256 + homedeck.sh
set -euo pipefail
H="$(cd "$(dirname "$0")" && pwd)"
V="${1:-friend-$(date +%Y.%m.%d-%H%M)}"
OUT="$H/dist"; STAGE="$OUT/homedeck-kit"
rm -rf "$OUT"; mkdir -p "$STAGE/app" "$STAGE/editor" "$STAGE/bin" "$STAGE/systemd"
# pages from the owner's live panels -> friend versions
rm -rf "$H/src/www"; python3 "$H/build_www.py" "$H/../homedeck-src/live/www" "$H/src/www" >/dev/null
cp -r "$H/src/server.py" "$H/src/homedeck" "$H/src/www" "$H/src/homedeck.toml" "$STAGE/app/"
find "$STAGE/app" -name __pycache__ -prune -exec rm -rf {} +
echo "$V" > "$STAGE/app/VERSION"
cp "$H/editor/editor.py" "$H/editor/editor.html" "$STAGE/editor/"
python3 "$H/kit/patch_editor.py" "$STAGE/editor/editor.py" >/dev/null
cp "$H/kit/homedeck-apply" "$H/kit/homedeck-update" "$STAGE/bin/"
cp "$H/kit/panel-wrapper.service" "$H/kit/deck-editor.service" "$STAGE/systemd/"
cp "$H/kit/install-homedeck.sh" "$STAGE/"
cat > "$STAGE/README.txt" <<TXT
Home Deck $V - panels for Home Assistant (wall, tablet, phone, desktop wallpaper).
On a Proxmox node:   bash <(curl -fsSL https://home.example.net:8443/homedeck.sh)
On any Debian/Ubuntu machine (as root, in this folder):   ./install-homedeck.sh
Then open http://<address>/ : the setup page asks for a Home Assistant long-lived token.
Editor: http://<address>:8088   Update: homedeck-update   Safe restart after edits: homedeck-apply
TXT
chmod +x "$STAGE/install-homedeck.sh" "$STAGE/bin/"*
# self-check of the packaged code: everything compiles and the settings template validates
( cd "$STAGE/app" && sed 's#__HA_URL__#http://127.0.0.1:8123#' homedeck.toml > /tmp/hd-check.toml && \
  HOMEDECK_ROOT="$STAGE/app" HOMEDECK_CONFIG=/tmp/hd-check.toml STATE_DIRECTORY="$(mktemp -d)" HOMEDECK_READONLY=1 python3 -m homedeck.check )
if grep -rIl -i -E "claude|anthropic|\bllm\b|chatgpt" "$STAGE" "$H/kit/homedeck.sh"; then echo "AI mention found - not publishing"; exit 1; fi
if grep -rIl -E "see-private-words-txt" "$STAGE/app" "$STAGE/editor"; then echo "personal data found"; exit 1; fi
tar czf "$OUT/homedeck-kit.tar.gz" --owner=0 --group=0 -C "$OUT" homedeck-kit
( cd "$OUT" && sha256sum homedeck-kit.tar.gz > homedeck-kit.tar.gz.sha256 )
cp "$H/kit/homedeck.sh" "$OUT/"
echo "built $V: $(du -h "$OUT/homedeck-kit.tar.gz" | cut -f1)"
