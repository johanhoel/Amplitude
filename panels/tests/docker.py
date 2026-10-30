"""The container install: python3 panels/tests/docker.py

Home Deck can be installed two ways now - install.sh with systemd, or the
Dockerfile here - and both copy the same code from server/. That is the shape
that already bit once: build_kit.sh and install.sh listed the same files
separately, drifted, and a fresh install from a clone stopped on a missing
file. A third list deserves a check rather than the same trust.

Nothing here needs docker. It reads the files against each other, so it runs
wherever the suite runs.
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
BUILD_KIT = (ROOT / "build_kit.sh").read_text(encoding="utf-8")
ENTRY = ROOT / "docker" / "entrypoint.sh"
APPLY = ROOT / "docker" / "homedeck-apply"
ONBOARD = (ROOT / "onboard" / "onboard.py").read_text(encoding="utf-8")

results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


# --- the image holds what the kit holds ---------------------------------
# build_kit.sh stages the app from server/: server.py, the homedeck package,
# the pages and the settings template. The image has to carry all four, or it
# runs an install that is missing a part nobody notices until a page 404s.
for part in ("server/server.py", "server/homedeck", "server/www", "server/homedeck.toml"):
    check(f"the image copies {part}", part in DOCKERFILE,
          "build_kit.sh stages it, so a container install needs it too")
check("build_kit.sh still stages those four", all(
    p.split("/", 1)[1] in BUILD_KIT for p in
    ("server/server.py", "server/homedeck", "server/www", "server/homedeck.toml")),
      "if the kit stopped staging one, this check is comparing against nothing")
check("the image copies the setup wizard", "onboard" in DOCKERFILE)

# --- the settings and the state stay outside the image -------------------
# The point of the split: pulling a new image must never touch the house.
check("the settings are a volume, not a layer", "/data" in DOCKERFILE and "/data" in COMPOSE)
check("the state is a volume, not a layer", "/state" in DOCKERFILE and "/state" in COMPOSE)
check("the settings template is kept apart from the live file",
      "homedeck-template.toml" in DOCKERFILE and "homedeck-template.toml" in ENTRY.read_text(encoding="utf-8"),
      "seeding from the live path would overwrite a configured house")

# --- the wizard's seams, which the container drives through the env ------
# onboard.py reads these names. The Dockerfile sets them. A rename on either
# side silently gives a wizard that writes somewhere nobody reads.
for var in sorted(set(re.findall(r"environ\.get\('(ONBOARD_[A-Z_]+)'", ONBOARD))):
    check(f"the image sets {var}", re.search(rf"\b{var}=", DOCKERFILE) is not None,
          "onboard.py reads it; unset, it falls back to the systemd path")

# --- no systemd inside the container -------------------------------------
for p in (ENTRY, APPLY):
    text = p.read_text(encoding="utf-8")
    check(f"{p.name} is executable", os.access(p, os.X_OK))
    check(f"{p.name} does not reach for systemctl", "systemctl" not in text,
          "there is no init in the container; this would fail at the worst moment")

apply_text = APPLY.read_text(encoding="utf-8")
check("apply checks the settings before it restarts anything",
      apply_text.index("homedeck.check") < apply_text.index("kill -TERM 1"),
      "a restart on settings that do not load leaves the panels down with no rollback")
check("apply refuses to kill PID 1 outside a container",
      ".dockerenv" in apply_text,
      "PID 1 on a normal machine is init; this would take the host down")

entry_text = ENTRY.read_text(encoding="utf-8")
check("the settings are seeded through a temporary file",
      ".new-$$" in entry_text and "mv " in entry_text,
      "a redirect makes the file even when the command fails, and an empty "
      "homedeck.toml reads as a configured house on the next start")
check("the panels are exec'd, so docker stop reaches them",
      re.search(r"^exec python3", entry_text, re.M) is not None,
      "without exec the shell keeps PID 1 and stop becomes a kill")

# --- host networking, which presence and the scan need -------------------
check("the compose file uses host networking", "network_mode: host" in COMPOSE,
      "presence sends ARP probes and the wizard scans the network; a bridge sees neither")
check("the compose file says why", "ARP" in COMPOSE or "arp" in COMPOSE,
      "the next person will try to make it a bridge")
check("the container comes back by itself", "restart:" in COMPOSE,
      "apply restarts by stopping the container, so a restart policy is not optional")

print(f"{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
