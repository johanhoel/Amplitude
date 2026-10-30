"""Services: the machines Home Deck talks to, and the guided way to connect one.

python3 panels/tests/services.py

The rule this file exists for: connecting a machine must not need root, a
restart, or an edit to homedeck.toml. Home Deck runs as panel-wrapper and
cannot write its own settings file - on purpose, so a web page can never
change what the panels restart into - so a connection is saved in
settings.json and read in preference to the file. docs/SERVICES.md is the
recipe for adding one.
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


state = tempfile.mkdtemp(prefix="homedeck-services-")
conf = Path(state) / "homedeck.toml"
conf.write_text((ROOT / "server" / "homedeck.toml").read_text(encoding="utf-8")
                .replace("__HA_URL__", "http://127.0.0.1:8123")
                .replace('prometheus = ""', 'prometheus = "http://192.0.2.9:9090"'), encoding="utf-8")
os.environ.update(HOMEDECK_CONFIG=str(conf), STATE_DIRECTORY=state, HOMEDECK_READONLY="1")
sys.path.insert(0, str(ROOT / "server"))
from homedeck import services                                     # noqa: E402
from homedeck.store import SETTINGS, load                         # noqa: E402

# ---- the catalogue ----------------------------------------------------
ids = [s.id for s in services.SERVICES]
check("there are services to connect", len(ids) >= 5, f"{ids}")
check("every id is unique", len(set(ids)) == len(ids))
for s in services.SERVICES:
    check(f"{s.id} says what it gives you", len(s.gives) > 20 and s.gives.endswith("."), s.gives)
    check(f"{s.id} says where to find its address", "ADDRESS" in s.find or "http" in s.find, s.find)
    check(f"{s.id} has steps to follow", len(s.steps) >= 1)
    check(f"{s.id} has something to ask", s.probe.startswith("/"))

# ---- what is saved, and where -----------------------------------------
check("a service with nothing saved and nothing in the file is empty",
      services.url("grafana") == "", services.url("grafana"))
check("one set in homedeck.toml is found through its setting",
      services.url("prometheus") == "http://192.0.2.9:9090", services.url("prometheus"))

check("an address without a scheme is refused",
      services.set_url("grafana", "10.0.0.9:3000") == "the address starts with http:// or https://")
check("an unknown service is refused", services.set_url("nope", "http://x") == "unknown service")
check("nothing was saved by either", services.url("grafana") == "")

check("a good one saves", services.set_url("grafana", "http://10.0.0.9:3000/") is None)
check("and comes back without its trailing slash", services.url("grafana") == "http://10.0.0.9:3000")
check("it lands in settings.json, which Home Deck may write",
      (load(SETTINGS, {}).get("services") or {}).get("grafana", {}).get("url") == "http://10.0.0.9:3000")
check("and never in homedeck.toml, which it may not",
      "10.0.0.9" not in conf.read_text(encoding="utf-8"),
      "a web page must not change what the panels restart into")

services.set_url("prometheus", "http://10.0.0.11:9090")
check("what you connect wins over what was installed",
      services.url("prometheus") == "http://10.0.0.11:9090")
services.set_url("prometheus", "")
check("and forgetting it falls back to the file, not to nothing",
      services.url("prometheus") == "http://192.0.2.9:9090")

# ---- the secret goes somewhere else -----------------------------------
services.set_url("camwatch", "http://10.0.0.20:8080", key="super-secret-key")
check("a service key is not in settings.json",
      "super-secret-key" not in json.dumps(load(SETTINGS, {})),
      "settings.json is read by pages; secrets.json is not")
check("it is in secrets.json", "super-secret-key" in (Path(state) / "secrets.json").read_text(encoding="utf-8"))

# ---- what the Studio is told ------------------------------------------
st = {s["id"]: s for s in services.state()}
check("the Studio is told every service", len(st) == len(services.SERVICES))
check("a connected one is marked on", st["grafana"]["on"] is True and st["grafana"]["url"] == "http://10.0.0.9:3000")
check("an unconnected one is still listed", st["labpanel"]["on"] is False,
      "hiding it would make the house's possibilities invisible")
check("the one that needs a key says so", st["camwatch"]["needs_key"] is True and st["ollama"]["needs_key"] is False)
check("no key is ever sent to the page", "super-secret-key" not in json.dumps(services.state()))

# ---- a connected service is probed with the rest ----------------------
links = (ROOT / "server" / "homedeck" / "links.py").read_text(encoding="utf-8")
check("the status dots include what you connected here",
      re.search(r"for s in services\.state\(\)", links) is not None
      and re.search(r'checks\[s\["id"\]\]', links) is not None,
      "otherwise connecting one would need a restart to show up")

# ---- the readers prefer it --------------------------------------------
for name, sid in (("insights.py", "prometheus"), ("insights.py", "camwatch"),
                  ("presence.py", "camwatch"), ("localai.py", "ollama")):
    body = (ROOT / "server" / "homedeck" / name).read_text(encoding="utf-8")
    check(f"{name} reads {sid} through services.url",
          f'services.url("{sid}")' in body, "it would still need a restart otherwise")

# ---- and the recipe is written down -----------------------------------
doc = (ROOT / "docs" / "SERVICES.md").read_text(encoding="utf-8")
check("docs/SERVICES.md says how to add one", "## Adding a service" in doc)
check("and says which layer a connection is saved in", "settings.json" in doc and "homedeck.toml" in doc)
studio = (ROOT / "server" / "www" / "studio.html").read_text(encoding="utf-8")
check("the Studio has a Services section", 'data-s="services"' in studio and "async services()" in studio)
check("it points at the recipe rather than listing the services twice",
      "SERVICES.md" in studio and "Grafana" not in studio,
      "the page must not know the names; services.py is the list")

print(f"{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
