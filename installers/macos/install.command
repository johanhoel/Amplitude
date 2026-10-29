#!/bin/bash
# Mac installer for one Amplitude project; the build puts the project in place of __PROJECT__ / __NAME__.
# The app opens this in Terminal. It installs Multipass (Ubuntu's tool for small Linux machines) when needed,
# creates a Linux machine named after the project, and runs installers/linux/setup.sh from GitHub in it.
# Run it again to update, or to remove the project.
set -uo pipefail
PROJECT="__PROJECT__"
NAME="__NAME__"
VM=$(echo "$PROJECT" | tr -cd 'a-z0-9')
SETUP_URL="https://raw.githubusercontent.com/johanhoel/amplitude/main/installers/linux/setup.sh"
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
case "$PROJECT" in
  camwatch) PORT=8080; DISK=200G; MEM=4G ;;
  homedeck) PORT=8089; DISK=20G; MEM=2G ;;
  dstreamer) PORT=8480; DISK=20G; MEM=2G ;;
esac

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
stop() { printf '\n\033[1;31m%s\033[0m\n' "$*"; read -r -p "Press Enter to close. " _; exit 1; }
clear
printf '\033[1m%s for Mac\033[0m\n' "$NAME"

if [ "$PROJECT" = dstreamer ]; then
  echo
  echo "DStreamer needs direct access to the network for its clock (PTP) and audio."
  echo "On a Mac it runs in a virtual machine. Audio can drop out or stay silent."
  echo "A Linux computer or a Raspberry Pi works better."
  read -r -p "Install anyway? Type yes: " a; [ "$a" = yes ] || exit 0
fi

# ---------------------------------------------------------------- Multipass
if ! command -v multipass >/dev/null; then
  say "Installing Multipass (asks for your Mac password)"
  url=$(curl -fsSL https://api.github.com/repos/canonical/multipass/releases/latest \
        | grep -oE '"browser_download_url": *"[^"]+mac-Darwin\.pkg"' | head -1 | cut -d'"' -f4)
  [ -n "$url" ] || stop "Could not find the Multipass download. Install it from https://multipass.run and run this again."
  pkg=$(mktemp -d)/multipass.pkg
  curl -fL --progress-bar "$url" -o "$pkg" || stop "The Multipass download failed."
  sudo installer -pkg "$pkg" -target / || stop "Installing Multipass failed."
  for _ in $(seq 30); do multipass version >/dev/null 2>&1 && break; sleep 2; done
fi

# ---------------------------------------------------------------- already there?
if multipass info "$VM" >/dev/null 2>&1; then
  echo
  echo "$NAME is installed already (Linux machine '$VM')."
  echo "  1  update $NAME"
  echo "  2  remove $NAME, with all its data"
  echo "  3  cancel"
  read -r -p "Choose 1, 2 or 3: " choice
  case "$choice" in
    1) multipass start "$VM" >/dev/null 2>&1 ;;
    2) read -r -p "Remove $NAME and all its data? Type yes: " a
       [ "$a" = yes ] || exit 0
       multipass delete --purge "$VM" && echo "$NAME is removed."; read -r -p "Press Enter to close. " _; exit 0 ;;
    *) exit 0 ;;
  esac
else
  say "Creating the Linux machine '$VM' (Ubuntu 24.04)"
  # bridged: the machine gets its own address on your home network, so phones and cameras reach it
  net=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')
  if ! multipass launch 24.04 --name "$VM" --cpus 2 --memory "$MEM" --disk "$DISK" ${net:+--network "$net"}; then
    echo "A machine on the home network did not work. Trying one that only this Mac reaches."
    multipass delete --purge "$VM" >/dev/null 2>&1
    multipass launch 24.04 --name "$VM" --cpus 2 --memory "$MEM" --disk "$DISK" || stop "Creating the Linux machine failed."
  fi
fi

# ---------------------------------------------------------------- the project
say "Installing $NAME (the first time takes 5 to 20 minutes)"
tz=$(readlink /etc/localtime | sed 's#.*/zoneinfo/##')
multipass exec "$VM" -- sudo bash -c "curl -fsSL '$SETUP_URL' | HOST_TZ='$tz' bash -s $PROJECT" \
  || stop "The installation stopped with an error. Run the installer again to retry."

# the address on the home network; else the one only this Mac reaches
ips=$(multipass info "$VM" | awk '/IPv4/{print $2} /^ +[0-9]+\./{print $1}')
ip=$(echo "$ips" | grep -v '^192\.168\.64\.' | head -1); ip=${ip:-$(echo "$ips" | head -1)}

say "Done"
multipass exec "$VM" -- sudo cat "/root/$PROJECT-install.txt" 2>/dev/null
echo
echo "Open: http://$ip:$PORT"
echo "After a restart of the Mac: run this installer again and choose 1, or type: multipass start $VM"
open "http://$ip:$PORT"
read -r -p "Press Enter to close. " _
