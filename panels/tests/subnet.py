"""The home network comes from the settings, not from the code: python3 panels/tests/subnet.py

Presence and the device list keep only addresses in the home network. They
used to test the text "192.168.1." in code, so a house on any other network had
no presence and no device list, and nothing said why. Now the network is
[network] home_subnet, or the first Pi-hole's /24, or Home Assistant's /24.

Each case loads the real config module against its own settings file.
"""
import importlib
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "panels" / "server"
TEMPLATE = (SERVER / "homedeck.toml").read_text(encoding="utf-8")
sys.path.insert(0, str(SERVER))
results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


def load(ha="http://127.0.0.1:8123", piholes="[]", subnet=""):
    state = tempfile.mkdtemp(prefix="homedeck-subnet-")
    text = (TEMPLATE.replace("__HA_URL__", ha)
            .replace('home_subnet = ""', f'home_subnet = "{subnet}"'))
    text = re.sub(r"(?m)^piholes = \[.*?\]", f"piholes = {piholes}", text)
    conf = Path(state) / "homedeck.toml"
    conf.write_text(text, encoding="utf-8")
    os.environ.update(HOMEDECK_CONFIG=str(conf), STATE_DIRECTORY=state, HOMEDECK_READONLY="1")
    import homedeck.config as config
    return importlib.reload(config)


c = load(subnet="10.20.30.0/24")
check("home_subnet sets the home network", str(c.C.HOME_NET) == "10.20.30.0/24", str(c.C.HOME_NET))
check("an address in it is at home", c.at_home("10.20.30.7") and not c.at_home("192.168.1.7"))
check("[network.names] numbers become full addresses", c.home_ip("30") == "10.20.30.30", c.home_ip("30"))

c = load(piholes='["192.168.100.30", "192.168.100.31"]')
check("without home_subnet, the first Pi-hole's /24 is the home network",
      str(c.C.HOME_NET) == "192.168.100.0/24", str(c.C.HOME_NET))
check("the live house's phones count as home", c.at_home("192.168.100.42") and not c.at_home("192.168.1.42"))

c = load(ha="http://172.16.5.9:8123")
check("without a Pi-hole, Home Assistant's /24 is the home network", str(c.C.HOME_NET) == "172.16.5.0/24", str(c.C.HOME_NET))

c = load(ha="https://ha.example.net")
check("with no address to go on, any private IPv4 address counts", c.C.HOME_NET is None
      and c.at_home("192.168.7.3") and not c.at_home("8.8.8.8") and c.home_ip("30") == "")


def problems(subnet):
    """The settings check alone (homedeck-apply runs it before a restart), for a value Home Deck must refuse."""
    path = Path(tempfile.mkdtemp(prefix="homedeck-subnet-")) / "homedeck.toml"
    path.write_text(TEMPLATE.replace("__HA_URL__", "http://127.0.0.1:8123")
                    .replace('home_subnet = ""', f'home_subnet = "{subnet}"'), encoding="utf-8")
    return [x for x in c.read(str(path))[1] if "home_subnet" in x]


check("a public network is refused", problems("8.8.8.0/24"))
check("only a /24 is accepted, because [network.names] counts on the last number", problems("192.168.1.0/16"))
check("a private /24 passes the check", not problems("192.168.100.0/24"))

for f in ("presence.py", "insights.py"):
    code = (SERVER / "homedeck" / f).read_text(encoding="utf-8")
    check(f"{f} has no network written into its code", not re.search(r"['\"]192\.168\.\d+\.", code))

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
