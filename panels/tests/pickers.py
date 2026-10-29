"""The edit-mode pickers really override the config: python3 panels/tests/pickers.py

Family info reads a bus stop and a weather entity. Both start life in
homedeck.toml, and both can be changed from Page settings without touching
that file - the pick lands in the page's layout JSON and the server prefers
it. The failure mode is quiet: the picker saves, the layout file grows a
key, and the server goes on reading homedeck.toml, so the page keeps
showing the old place and nothing anywhere says why.

Runs the real modules against a throwaway state directory, so it checks the
reading code rather than a copy of it. Also checks that the picker exists in
the page, because a server that honours a key no page ever writes is the
same bug seen from the other end.
"""
import json
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


state = tempfile.mkdtemp(prefix="homedeck-pickers-")
os.environ.update(HOMEDECK_CONFIG=str(SERVER / "homedeck.toml"),
                  STATE_DIRECTORY=state, HOMEDECK_READONLY="1")
sys.path.insert(0, str(SERVER))

from homedeck import ha, transit, weather          # noqa: E402
from homedeck.config import C                      # noqa: E402

LAYOUT = Path(state) / "layouts" / "familyinfo.json"
LAYOUT.parent.mkdir(parents=True, exist_ok=True)


def layout(**keys):
    LAYOUT.write_text(json.dumps(keys))


# ---- no pick: both fall back to homedeck.toml ----
layout()
check("weather falls back to the config entity", weather.entity() == C.WEATHER, weather.entity())
check("bus stop falls back to the config stop", transit.bus_stop() == C.BUS_STOP, transit.bus_stop())

# ---- a pick wins over the config ----
layout(weather={"id": "weather.smhi_home", "name": "SMHI"})
check("a picked weather entity is used", weather.entity() == "weather.smhi_home", weather.entity())
layout(stop={"gid": "9" * 16, "name": "Somewhere"})
check("a picked bus stop is used", transit.bus_stop() == "9" * 16, transit.bus_stop())

# ---- rubbish in the layout must not reach Home Assistant ----
for bad, why in (("light.kitchen", "wrong domain"), ("weather.", "no name"),
                 ("weather.a b", "space"), ("", "empty"), ("WEATHER.HOME", "upper case")):
    layout(weather={"id": bad})
    check(f"weather rejects {why}", weather.entity() == C.WEATHER, f"{bad!r} -> {weather.entity()}")
layout(weather="weather.smhi_home")       # a bare string, not the {id, name} shape
check("weather survives a layout of the wrong shape", weather.entity() == C.WEATHER, weather.entity())

# ---- the entity list the picker fetches ----
states = [{"entity_id": "weather.b_home", "attributes": {"friendly_name": "Zebra"}},
          {"entity_id": "weather.a_home", "attributes": {"friendly_name": "apple"}},
          {"entity_id": "weather.bare", "attributes": {}},
          {"entity_id": "light.kitchen", "attributes": {"friendly_name": "Kitchen"}}]
ha._states.update(at=float("inf"), data=states)
got = ha.entities("weather")
check("the list holds only that domain", [e["id"] for e in got] == ["weather.a_home", "weather.bare", "weather.b_home"],
      str([e["id"] for e in got]))
check("the list is sorted by name, ignoring case", [e["name"] for e in got] == ["apple", "bare", "Zebra"],
      str([e["name"] for e in got]))
check("an entity with no friendly name still has one", got[1]["name"] == "bare", got[1]["name"])
ha._states.update(at=float("inf"), data=[])
check("no entities is an empty list, not an error", ha.entities("weather") == [])

# ---- the page writes what the server reads ----
page = (SERVER / "www" / "familyinfo.html").read_text()
check("Page settings has a weather field", "key: 'weather'" in page)
check("the picker fetches the entity list", "/api/ha/entities?domain=weather" in page)
check("the pick is saved as {id, name}", re.search(r"model\.weather = .*\{ id: ", page) is not None)
web = (SERVER / "homedeck" / "web.py").read_text()
check("the server serves that list", "/api/ha/entities" in web)

print(f"{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
