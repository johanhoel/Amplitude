#!/usr/bin/env bash
# Build homedeck-kit.tar.gz from server/ (backend, pages and settings template), the editor (patched for
# home-network access) and kit/ (installer, services, commands).
# There is one edition now. There used to be two - the owner's pages and a stripped copy built by
# build_www.py - and the stripped one was what every fresh install actually got. What that generator
# removed is becoming configuration instead, so the same pages serve any house.
#   ./build_kit.sh [version]      -> dist/homedeck-kit.tar.gz + .sha256 + homedeck.sh
set -euo pipefail
H="$(cd "$(dirname "$0")" && pwd)"
V="${1:-$(date +%Y.%m.%d-%H%M)}"
OUT="$H/dist"; STAGE="$OUT/homedeck-kit"
rm -rf "$OUT"; mkdir -p "$STAGE/app" "$STAGE/editor" "$STAGE/bin" "$STAGE/systemd"
cp -r "$H/server/server.py" "$H/server/homedeck" "$H/server/www" "$H/server/homedeck.toml" "$STAGE/app/"
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
# No AI-authorship traces in a published kit. This used to ban the bare words
# "claude" and "llm", which stopped working the day the Local AI panel shipped:
# it loads Ollama models, routes live under /llm/, and "claude" is the setup id
# for launching Claude Code on the PC. Those are the product's own vocabulary.
# So the patterns below describe authorship instead - a byline, a session link,
# a co-author trailer - which is what the check was always for. "anthropic" and
# "chatgpt" stay banned as bare words; nothing here has a reason to say them.
if grep -rIl -i -E "anthropic\\.com|@anthropic|chatgpt|claude\\.ai|co-authored-by|generated with|written by claude|as an ai (language )?model" "$STAGE" "$H/kit/homedeck.sh"; then echo "AI authorship mention found - not publishing"; exit 1; fi
# personal words (names, street, entity ids) live in private-words.txt: one per line, kept out of git
if [ -s "$H/private-words.txt" ]; then
  if grep -rIl -i -F -f "$H/private-words.txt" "$STAGE/app" "$STAGE/editor"; then echo "personal data found"; exit 1; fi
else
  echo "warning: $H/private-words.txt is missing - the personal data check is skipped" >&2
fi
tar czf "$OUT/homedeck-kit.tar.gz" --owner=0 --group=0 -C "$OUT" homedeck-kit
( cd "$OUT" && sha256sum homedeck-kit.tar.gz > homedeck-kit.tar.gz.sha256 )
cp "$H/kit/homedeck.sh" "$OUT/"
echo "built $V: $(du -h "$OUT/homedeck-kit.tar.gz" | cut -f1)"
