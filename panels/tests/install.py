"""The install contract: python3 panels/tests/install.py

There is one edition now, and the pages that used to be generated for a
stranger's house are the same pages this house runs. That makes the settings
template the only thing standing between a new install and somebody else's
addresses - so what it promises, and who fills it in, is worth checking.

The bug this starts from: install-homedeck.sh substitutes __HA_URL__ with the
address you type at setup, and the template had stopped containing __HA_URL__.
The sed was a no-op, nothing complained, and every fresh install came up
pointing at the author's own Home Assistant instead of the user's.
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOML = (ROOT / "server" / "homedeck.toml").read_text(encoding="utf-8")
INSTALL = (ROOT / "kit" / "install-homedeck.sh").read_text(encoding="utf-8")
STAGING = (ROOT / "tools" / "staging.sh").read_text(encoding="utf-8")
CHECK = (ROOT / "tools" / "check.sh").read_text(encoding="utf-8")

results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


# ---- the address the installer asks for actually lands somewhere ------
url = re.search(r'^url = "([^"]*)"', TOML, re.M)
check("the template has a Home Assistant url", url is not None)
check("it is a placeholder, not an address",
      url is not None and url.group(1) == "__HA_URL__",
      f'found {url.group(1) if url else "-"} - a fresh install would point at it')
check("the installer fills that placeholder in",
      "__HA_URL__" in INSTALL,
      "otherwise the address typed at setup is thrown away")

# ---- everything that reads the template handles the placeholder -------
for name, body in (("build_kit.sh", (ROOT / "build_kit.sh").read_text(encoding="utf-8")),
                   ("tools/check.sh", CHECK), ("tools/staging.sh", STAGING)):
    check(f"{name} substitutes the placeholder before using the settings",
          "__HA_URL__" in body,
          "the settings will not validate with a placeholder in them")

# ---- the suite is runnable by somebody who is not the author ----------
check("staging can run without a Home Assistant token",
      "HOMEDECK_STUB" in STAGING and (ROOT / "tools" / "stub-ha.py").exists(),
      "tests/smoke.py was unrunnable for anyone but the owner of that house")
check("staging still refuses to guess a real address",
      "HOMEDECK_HA_URL" in STAGING,
      "silently falling back to localhost would look like Home Assistant is down")
check("the smoke test does not need docker",
      "import playwright" in CHECK,
      "it was skipped on every machine without docker, which is most of them")
check("the stub is never mistaken for a credential store",
      "stub-no-real-credential" in STAGING)

# ---- the template carries nobody's house ------------------------------
# The same file used to ship the author's network: 30 addresses, the family's
# phone MACs, their rooms, their bus stop. A stranger's install probed all of
# them, and the status dots on Start were somebody else's machines.
PRIVATE_IP = re.compile(r"\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d+\.\d+\b")
MAC = re.compile(r"\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", re.I)
settings_lines = [l.split("#", 1)[0] for l in TOML.splitlines()]
settings = "\n".join(settings_lines)
check("no private address is shipped in the settings",
      not PRIVATE_IP.search(settings),
      f"found {PRIVATE_IP.findall(settings)[:4]} - a fresh install would probe them")
check("no MAC address is shipped in the settings",
      not MAC.search(settings),
      f"found {MAC.findall(settings)[:3]} - those are somebody's phones")
check("the only host it names is the one the installer fills in",
      [h for h in re.findall(r'"https?://([^/"\s:]+)', settings)
       if h not in ("127.0.0.1",) and not h.endswith((".se", ".sh"))] == [],
      "a hostname in the template is a house, not a default")
for section, why in (("presence.phones", "the people living there"),
                     ("network.names", "what each address in that house is"),
                     ("network.mac_names", "the devices in that house"),
                     ("rooms.names", "the rooms of that house")):
    body = re.search(rf"^\[{re.escape(section)}\](.*?)(?=^\[|\Z)", TOML, re.M | re.S)
    lines = [l for l in (body.group(1).splitlines() if body else []) if l.strip() and not l.strip().startswith("#")]
    check(f"[{section}] ships empty", body is not None and not lines, f"it still lists {why}")

# ---- nor does any page that ships with it -----------------------------
# The settings were not the only place: the pages hard-coded the same house in
# their link grids, and www/network.html was a 2.8 MB document of one network.
# A page may name 127.0.0.1 (itself) and the documentation ranges.
PAGES = sorted((ROOT / "server" / "www").glob("*.html")) + sorted((ROOT / "server" / "www" / "designs").glob("*.html"))
check("there are pages to check", len(PAGES) > 15, f"found {len(PAGES)}")
for page in PAGES:
    body = page.read_text(encoding="utf-8", errors="replace")
    found = sorted(set(PRIVATE_IP.findall(body)))
    check(f"www/{page.name} names no address in anyone's house", not found, f"{found[:4]}")

# ---- nor do the scripts that talk to it -------------------------------
# deploy.sh, pull-live.sh and publish.sh each held root@<the live machine>.
# An address you can SSH into as root is the last thing a public repository
# should carry, and when that machine died the scripts pointed at nothing.
TOOLS = sorted((ROOT / "tools").glob("*.sh")) + [ROOT / "app" / "publish.sh"]
check("there are scripts to check", len(TOOLS) >= 3, f"{[t.name for t in TOOLS]}")
for tool in TOOLS:
    body = tool.read_text(encoding="utf-8")
    found = sorted(set(PRIVATE_IP.findall(body)))
    check(f"{tool.name} names no machine of anyone's", not found, f"{found[:3]}")
    if "ssh " in body:
        check(f"{tool.name} is told where to go rather than assuming",
              "HOMEDECK_HOST" in body or ".deploy-host" in body,
              "a hard-coded host is wrong the day that machine is replaced")
ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
check("the address the scripts are told stays out of git", ".deploy-host" in ignored)

# ---- and still works once the installer has filled in the address -----
sys.path.insert(0, str(ROOT / "server"))
import tempfile                                                   # noqa: E402
import tomllib                                                    # noqa: E402

STATE = tempfile.mkdtemp()
FILLED = Path(STATE) / "homedeck.toml"
FILLED.write_text(TOML.replace("__HA_URL__", "http://10.1.1.5:8123"), encoding="utf-8")
os.environ.update(HOMEDECK_ROOT=str(ROOT / "server"), HOMEDECK_CONFIG=str(FILLED),
                  HOMEDECK_READONLY="1", STATE_DIRECTORY=STATE, HOMEDECK_CHECKONLY="1")
from homedeck import config as hdconfig                           # noqa: E402   (CHECKONLY: reads nothing yet)

filled = tomllib.loads(FILLED.read_text(encoding="utf-8"))
problems = hdconfig.validate(filled)
check("the shipped settings validate with nothing but the address filled in",
      not problems, "; ".join(problems[:3]))
try:
    derived = hdconfig._derive(filled)
except Exception as exc:                                          # a value that validates but cannot be used
    check("the shipped settings can be used", False, f"{type(exc).__name__}: {exc}")
    print(f"{sum(results)}/{len(results)} passed")
    raise SystemExit(1)
check("a house with no PC reads as having no PC",
      derived.PC == ("", 0), f"{derived.PC!r}")
check("the status dots are Home Deck's own pages and nothing else",
      all(u.startswith("http://127.0.0.1") for u in derived.LINK_CHECKS.values()),
      "a dot that is always red teaches people to ignore the dots")

hdconfig.C = derived          # the modules read this at import; give them the shipped settings
from homedeck import addons                                       # noqa: E402
on = [k for k, v in addons.state().items() if v]
check("a fresh install offers no panel for hardware it has not been told about",
      on == [], f"{on} would be shown")

# ---- a house that already has settings keeps running ------------------
# An update keeps the settings file the house edited, so the new code meets a
# file written before these settings existed. A missing optional line has to
# mean the same as an empty one, or the panels come up on the last good copy -
# or, the first time, not at all.
older = tomllib.loads(re.sub(r"^\[people\]\n(.*\n)*?\n", "", TOML.replace("__HA_URL__", "http://10.1.1.5:8123"), flags=re.M))
check("a settings file written before [people] existed has no new problems",
      "people" not in older and not hdconfig.validate(older),
      "; ".join(hdconfig.validate(older)[:3]) or "the section was not actually removed")
check("and nobody is hidden in it", hdconfig._derive(older).PEOPLE_HIDE == set())

# ---- the setup wizard can put every one of them back ------------------
# Emptying the template makes the wizard the only way most of this gets set,
# so it has to be able to write each kind: a value, a table, and the list of
# players. Two of those were broken: [links.extra] did not exist to write
# into, and players.hide was a setting nothing in the server ever read.
os.environ["ONBOARD_ROOT"] = str(ROOT / "server")
sys.path.insert(0, str(ROOT / "onboard"))
import onboard                                                    # noqa: E402

STATES = [{"entity_id": "lock.front", "state": "locked", "attributes": {"friendly_name": "Front door"}},
          {"entity_id": "weather.home", "state": "sunny", "attributes": {"friendly_name": "Home"}},
          {"entity_id": "media_player.kitchen", "state": "idle", "attributes": {"friendly_name": "Kitchen"}},
          {"entity_id": "media_player.attic", "state": "idle", "attributes": {"friendly_name": "Attic"}},
          {"entity_id": "person.robin", "state": "home", "attributes": {"friendly_name": "Robin"}},
          {"entity_id": "person.guest", "state": "home", "attributes": {"friendly_name": "Guest"}}]
onboard.S["ha"] = {"url": "http://10.1.1.5:8123", "token": None, "states": STATES, "error": None}
onboard.S["scan"]["result"] = {"found": {"router": [{"ip": "10.1.1.1", "label": "Router"}]}, "devices": [], "subnet": "10.1.1.0/24", "took_s": 1}

try:
    text, problems = onboard.render({"homeassistant.url": "http://10.1.1.5:8123",
                                     "entities.lock": "lock.front", "entities.weather": "weather.home",
                                     "players": ["media_player.kitchen"],
                                     "people.hide": ["person.robin"],
                                     "links.extra": ["router|http://10.1.1.1/"]})
except Exception as exc:                                          # a wizard that cannot write is a dead install
    text, problems = "", [f"{type(exc).__name__}: {exc}"]
check("what the wizard writes is a valid settings file", text and not problems, "; ".join(problems[:3]))
saved = tomllib.loads(text) if text else {"homeassistant": {}, "entities": {}, "players": [],
                                          "people": {"hide": []}, "links": {}}
check("the address you confirm is written", saved["homeassistant"]["url"] == "http://10.1.1.5:8123")
check("the front door is written", saved["entities"]["lock"] == "lock.front")
check("a ticked player becomes the players list, with its name",
      saved["players"] == [{"entity": "media_player.kitchen", "label": "Kitchen"}], f"{saved['players']}")
check("an unticked person is hidden, and only that one",
      saved["people"]["hide"] == ["person.guest"], f"{saved['people']['hide']}")
check("a device found on the network becomes a status dot",
      saved["links"]["extra"] == {"router": "http://10.1.1.1/"}, f"{saved['links'].get('extra')}")
check("the house's own machines are kept apart from Home Deck's pages",
      hdconfig._derive(saved).LINK_EXTRA == {"router"},
      "the pages list [links.extra]; mixing them in would list Home Deck's own pages as devices")
check("the dots the wizard writes are probed with the rest",
      hdconfig._derive(saved).LINK_CHECKS.get("router") == "http://10.1.1.1/",
      "they would sit in the file doing nothing")
check("the hide list is wired into the people the panels show",
      "C.PEOPLE_HIDE" in (ROOT / "server" / "homedeck" / "home.py").read_text(encoding="utf-8"),
      "the wizard would be writing a setting nothing reads")

print(f"{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
