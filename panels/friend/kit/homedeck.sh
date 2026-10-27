#!/usr/bin/env bash
# homedeck.sh: create Home Deck (wall, tablet, phone and desktop panels for Home Assistant) on this Proxmox node.
# Run as root on the node:
#
#   bash <(curl -fsSL https://home.example.net:8443/homedeck.sh)
#   bash <(curl -fsSL http://192.168.1.41/homedeck.sh)            # inside the home LAN
#
# Or paste the whole file into a root shell: everything is one function that runs in a
# subshell, so the paste is read completely before the first question and an error never
# closes your shell.
#
# What it does:
#   1. asks for your Home Assistant address and checks that this node can reach it
#   2. creates a small Debian 13 container (unprivileged, 1 core, 512 MB, starts at boot)
#   3. downloads Home Deck (checked with SHA-256) and installs it inside: panels on port 80, editor on 8088
# Then open the address it prints: the setup page asks for a Home Assistant token, and rooms, lights, people and
# media players are read from Home Assistant by themselves.
# Update later:  pct exec <CTID> -- homedeck-update   (keeps settings, token, layouts and your own edits).
#
# Overrides (environment): HOMEDECK_REPO (space-separated base URLs), HOMEDECK_TEMPLATE
# (a vztmpl volume to use instead of the newest Debian 13 standard template).

pve_homedeck() (
  set -euo pipefail

  # ---- settings ------------------------------------------------------------------
  local REPOS="${HOMEDECK_REPO:-https://home.example.net:8443 http://192.168.1.41}"
  # the repo only serves the kit to requests with this header (keeps browsers and casual downloads out)
  local -a REPO_HDR=(-H "X-Winrepo-Key: ${WIN_REPO_KEY:-VKcUYRQvHZAm2ZQD1c2eV7KoSqacgmsA}")
  local KIT=homedeck/homedeck-kit.tar.gz
  local TTY="${HOMEDECK_TTY:-/dev/tty}"

  # ---- helpers -------------------------------------------------------------------
  say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
  warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
  die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }
  ask() {  # ask VAR "question" "default"
    local __var=$1 __q=$2 __def=${3:-} __ans
    if [[ -n $__def ]]; then printf '%s [%s]: ' "$__q" "$__def" >"$TTY"; else printf '%s: ' "$__q" >"$TTY"; fi
    IFS= read -r __ans <"$TTY" || true
    printf -v "$__var" '%s' "${__ans:-$__def}"
  }
  ask_secret() {  # ask_secret VAR "question"
    local __var=$1 __q=$2 __a __b
    while :; do
      printf '%s: ' "$__q" >"$TTY"; IFS= read -rs __a <"$TTY" || true; printf '\n' >"$TTY"
      [[ ${#__a} -ge 5 ]] || { warn "At least 5 characters."; continue; }
      printf 'Again: ' >"$TTY"; IFS= read -rs __b <"$TTY" || true; printf '\n' >"$TTY"
      [[ $__a == "$__b" ]] && break
      warn "They don't match, try again."
    done
    printf -v "$__var" '%s' "$__a"
  }
  yesno() {  # yesno "question" y|n
    local __ans
    printf '%s [%s]: ' "$1" "$([[ $2 == y ]] && echo Y/n || echo y/N)" >"$TTY"
    IFS= read -r __ans <"$TTY" || true
    [[ ${__ans:-$2} =~ ^[Yy] ]]
  }
  pick() {  # pick VAR "title" default line... : numbered menu, returns the first word of the chosen line
    local __var=$1 __t=$2 __def=$3; shift 3
    local i=1 __n __l
    printf '\n%s\n' "$__t" >"$TTY"
    for __l in "$@"; do printf '  %d) %s\n' "$i" "$__l" >"$TTY"; i=$((i + 1)); done
    while :; do
      ask __n "Choose" "$__def"
      [[ $__n =~ ^[0-9]+$ ]] && (( __n >= 1 && __n <= $# )) && break
      warn "Pick 1-$#."
    done
    __l=${!__n}
    printf -v "$__var" '%s' "${__l%% *}"
  }

  # ---- checks --------------------------------------------------------------------
  [[ $(id -u) -eq 0 ]] || die "Run as root on the Proxmox node."
  for c in pct pveam pvesm pvesh curl sha256sum; do
    command -v "$c" >/dev/null || die "'$c' not found: run this on a Proxmox VE node."
  done
  [[ -r $TTY ]] || die "No terminal for the questions ($TTY)."

  local REPO="" r
  for r in $REPOS; do
    if curl -fsS -m 10 "${REPO_HDR[@]}" -o /dev/null "$r/$KIT.sha256" 2>/dev/null; then REPO=$r; break; fi
  done
  [[ -n $REPO ]] || die "Can't reach the Home Deck download ($REPOS)."

  printf '\n\033[1mHome Deck on Proxmox\033[0m\n'
  echo "Creates a small container with Home Deck: panels for your Home Assistant (lights by room, music, who's home,"
  echo "weather, buses, a night clock and a desktop wallpaper). Enter accepts the [default]."

  say "Home Assistant"
  echo "The address of Home Assistant as this network reaches it, e.g. http://192.168.1.20:8123"
  local HA_URL
  while :; do
    ask HA_URL "Home Assistant address" ""
    HA_URL=${HA_URL%/}
    [[ $HA_URL =~ ^https?://[^[:space:]/]+$ ]] || { warn "Format: http://ADDRESS:8123"; continue; }
    if curl -fsk -m 6 -o /dev/null "$HA_URL/manifest.json"; then echo "OK: Home Assistant answers." >"$TTY"; break; fi
    warn "No answer from $HA_URL (from this node)."
    yesno "Use it anyway" n && break
  done

  # ---- 1. container settings -----------------------------------------------------
  say "Container"
  local CTID def; def=$(pvesh get /cluster/nextid)
  while :; do
    ask CTID "Container ID" "$def"
    [[ $CTID =~ ^[0-9]+$ ]] && pvesh get /cluster/nextid --vmid "$CTID" >/dev/null 2>&1 && break
    warn "ID $CTID is taken or invalid."
  done
  local NAME; ask NAME "Hostname" "homedeck"
  local CORES; ask CORES "CPU cores" "1"
  local MEM; ask MEM "Memory in MB" "512"
  local DISK; ask DISK "Disk in GB" "4"
  [[ $CORES =~ ^[0-9]+$ && $MEM =~ ^[0-9]+$ && $DISK =~ ^[0-9]+$ ]] || die "Cores, memory and disk must be numbers."

  local -a lines=()
  mapfile -t lines < <(pvesm status --content rootdir 2>/dev/null | awk 'NR>1 && $3=="active"{printf "%s  (%s, %.0f GB free)\n", $1, $2, $6/1048576}' | sort -t'(' -k2)
  (( ${#lines[@]} )) || die "No active storage for containers (content 'rootdir')."
  local ST; pick ST "Storage for the container disk:" 1 "${lines[@]}"

  mapfile -t lines < <(ip -o link show type bridge | awk -F': ' '{print $2}' | grep -E '^vmbr' || true)
  (( ${#lines[@]} )) || lines=(vmbr0)
  local BR; pick BR "Network bridge:" 1 "${lines[@]}"

  local NET="ip=dhcp" IPCIDR GW
  if ! yesno "Use DHCP for the address (give it a reservation in the router afterwards)" y; then
    while :; do
      ask IPCIDR "Address with prefix, e.g. 192.168.1.60/24" ""
      [[ $IPCIDR =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+$ ]] && break
      warn "Format: 192.168.1.60/24"
    done
    ask GW "Gateway (the router)" "$(ip -4 route show default | awk '{print $3; exit}')"
    NET="ip=$IPCIDR,gw=$GW"
  fi
  local PW; ask_secret PW "Root password for the container console"

  # ---- 2. template ---------------------------------------------------------------
  say "Debian 13 template"
  local TST TPL
  TST=$(pvesm status --content vztmpl 2>/dev/null | awk 'NR>1 && $3=="active"{print $1}' | grep -x local || true)
  [[ -n $TST ]] || TST=$(pvesm status --content vztmpl 2>/dev/null | awk 'NR>1 && $3=="active"{print $1; exit}')
  [[ -n $TST ]] || die "No storage holds container templates (content 'vztmpl'); enable it on 'local'."
  if [[ -n ${HOMEDECK_TEMPLATE:-} ]]; then
    TPL=$HOMEDECK_TEMPLATE
  else
    pveam update >/dev/null 2>&1 || warn "pveam update failed; using the list Proxmox already has."
    local name; name=$(pveam available --section system | awk '{print $2}' | grep -E '^debian-13-standard_.*_amd64\.tar\.zst$' | sort -V | tail -1)
    [[ -n $name ]] || die "No Debian 13 template offered by pveam."
    if ! pveam list "$TST" | awk '{print $1}' | grep -qx "$TST:vztmpl/$name"; then
      say "Downloading $name"
      pveam download "$TST" "$name" >/dev/null
    fi
    TPL="$TST:vztmpl/$name"
  fi

  # ---- 3. create + start ---------------------------------------------------------
  say "Creating container $CTID ($NAME)"
  pct create "$CTID" "$TPL" --hostname "$NAME" --cores "$CORES" --memory "$MEM" --swap 512 \
    --rootfs "$ST:$DISK" --net0 "name=eth0,bridge=$BR,$NET" --ostype debian \
    --unprivileged 1 --features nesting=1 --onboot 1 \
    --description "Home Deck: panels for Home Assistant (port 80), editor (port 8088)" >/dev/null
  pct start "$CTID"
  printf 'root:%s\n' "$PW" | pct exec "$CTID" -- chpasswd
  unset PW

  say "Waiting for the network in the container"
  local ok=0
  for _ in $(seq 1 30); do
    if pct exec "$CTID" -- getent hosts deb.debian.org >/dev/null 2>&1; then ok=1; break; fi
    sleep 2
  done
  [[ $ok -eq 1 ]] || die "Container $CTID has no internet/DNS. Check the bridge and address, then run the installer by hand (see the guide)."

  # ---- 4. kit --------------------------------------------------------------------
  say "Downloading Home Deck"
  local tmp; tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  curl -fsSL "${REPO_HDR[@]}" -o "$tmp/kit.tgz" "$REPO/$KIT"
  curl -fsSL "${REPO_HDR[@]}" -o "$tmp/kit.sha256" "$REPO/$KIT.sha256"
  [[ $(sha256sum "$tmp/kit.tgz" | awk '{print $1}') == "$(awk '{print $1}' "$tmp/kit.sha256")" ]] \
    || die "The download is damaged (SHA-256 mismatch); run the command again."
  pct push "$CTID" "$tmp/kit.tgz" /root/homedeck-kit.tar.gz
  pct exec "$CTID" -- tar xzf /root/homedeck-kit.tar.gz -C /root

  # ---- 5. Home Deck installer inside the container
  say "Installing Home Deck inside container $CTID"
  pct exec "$CTID" -- env HOMEDECK_HA_URL="$HA_URL" bash /root/homedeck-kit/install-homedeck.sh <"$TTY" >"$TTY" 2>&1 \
    || die "The installer stopped. Fix the cause, then rerun it with:  pct exec $CTID -- bash /root/homedeck-kit/install-homedeck.sh"

  local ip; ip=$(pct exec "$CTID" -- hostname -I 2>/dev/null | awk '{print $1}')
  printf '\n\033[1mDone.\033[0m Container %s (%s), address %s\n' "$CTID" "$NAME" "${ip:-?}"
  echo "  1. Open  http://${ip:-<address>}/   - the setup page asks for a Home Assistant token (2 minutes)."
  echo "  2. Panels: http://${ip:-<address>}/start   Editor: http://${ip:-<address>}:8088 (choose a password first)."
  echo "  3. Give the container a fixed address in your router (DHCP reservation) so the bookmarks keep working."
  echo "  Update later:   pct exec $CTID -- homedeck-update"
)

pve_homedeck "$@"
