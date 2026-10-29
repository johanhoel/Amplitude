"""Plugins: add and remove parts of the panels from the start page: python3 panels/tests/plugins.py

An addon is on when it is configured (addons.py). The person who lives here can
also switch a configured one off, from the gear on the start page. That switch
only ever hides: a plugin that is not set up cannot be switched on, because the
page would show controls that talk to nothing.

Runs the real modules against a throwaway state directory, and checks the page
and the stylesheet too: a switch that no page reads is the same bug from the
other end.
"""
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "panels" / "server"

results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


state = tempfile.mkdtemp(prefix="homedeck-plugins-")
conf = Path(state) / "homedeck.toml"
conf.write_text((SERVER / "homedeck.toml").read_text(encoding="utf-8")
                .replace("__HA_URL__", "http://127.0.0.1:8123"), encoding="utf-8")
os.environ.update(HOMEDECK_CONFIG=str(conf), STATE_DIRECTORY=state, HOMEDECK_READONLY="1")
sys.path.insert(0, str(SERVER))

from homedeck import addons, auth                  # noqa: E402
from homedeck.store import SETTINGS, load          # noqa: E402

have = addons.configured()
names = [p["name"] for p in addons.catalog()]
check("every addon is in the Plugins list", set(names) == set(have) and len(names) == len(set(names)),
      f"{sorted(set(have) ^ set(names))}")
check("the Deck counts as set up when Buttons has an address", have.get("deck") is True, str(have.get("deck")))
check("before any switch, a plugin is on exactly when it is set up", addons.state() == have)

r = addons.switch("deck", False)
check("removing the Deck hides it", "deck" not in r["enabled"].split()
      and next(p for p in r["plugins"] if p["name"] == "deck")["on"] is False)
check("the switch is saved in settings.json", load(SETTINGS, {}).get("addons_off") == ["deck"])
check("removing one plugin leaves the others", all(addons.state()[k] == v for k, v in have.items() if k != "deck"))
r = addons.switch("deck", True)
check("adding it back shows it again", "deck" in r["enabled"].split() and load(SETTINGS, {}).get("addons_off") == [])

missing = next((k for k, v in have.items() if not v), None)
if missing:
    addons.switch(missing, True)
    check(f"a plugin that is not set up stays off ({missing})", addons.state()[missing] is False)
try:
    addons.switch("nonsense", True)
    check("an unknown plugin is refused", False, "no error")
except ValueError:
    check("an unknown plugin is refused", True)

check("switching plugins needs the admin PIN", auth.needs_admin_post("/api/addons"))

page = (SERVER / "www" / "index.html").read_text(encoding="utf-8")
css = (SERVER / "www" / "wall.css").read_text(encoding="utf-8")
check("the Deck card carries its addon name", 'class="deck glass" data-addon="deck"' in page)
check("the start page has the Plugins list and saves to /api/addons", 'id="plugins"' in page and "'/api/addons', { name:" in page)
for name in names:
    rule = f'html[data-addons]:not([data-addons~="{name}"]) [data-addon~="{name}"]'
    check(f"wall.css hides {name} when it is off", rule in css)

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
