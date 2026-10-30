"""The machines Home Deck talks to, and the guided way to connect one.

A house gains machines over time. Each one used to mean editing homedeck.toml as root and knowing
which key to put where; this is the list, the tutorial and the test, in one entry per service.
docs/SERVICES.md is the recipe for adding the next one.

Two layers, and the difference is deliberate: homedeck.toml is what the installer and the setup
wizard wrote, as root, and Home Deck cannot change it - a web page must never be able to alter what
the panels restart into. What you connect afterwards is saved in settings.json, which Home Deck owns
and which needs no restart. url() reads the saved one first and falls back to the file.
"""
import threading
import time
import urllib.error
import urllib.request

from .config import C
from .store import NOCHECK, SETTINGS, load, save

_lock = threading.Lock()


class Service:
    def __init__(self, id, name, gives, find, probe="/", setting=None, secret=None, steps=()):
        self.id, self.name, self.gives, self.find = id, name, gives, find
        self.probe, self.setting, self.secret, self.steps = probe, setting, secret, list(steps)


# The order is the order the Studio shows them in: what most houses have, first.
SERVICES = [
    Service("grafana", "Grafana", "Graphs of the house, and a dot on Start when it stops answering.",
            "Usually http://ADDRESS:3000, on the machine you installed it on.", probe="/api/health",
            steps=["Open Grafana and copy the address from your browser's bar.",
                   "Paste it below and press Test."]),
    Service("proxmox", "Proxmox", "The nodes and guests on the Lab page, and a console link for each.",
            "https://ADDRESS:8006 - the same address you log in to.", probe="/",
            steps=["Open the Proxmox web UI and copy its address, port and all.",
                   "Paste it below and press Test. A certificate warning is fine: Home Deck does not check it."]),
    Service("prometheus", "Prometheus", "The readings behind the graphs on Ops.",
            "http://ADDRESS:9090, usually beside Grafana.", probe="/-/healthy", setting="PROM",
            steps=["Open Prometheus and copy its address.", "Paste it below and press Test."]),
    Service("pihole", "Pi-hole", "Who is on the network, and the DNS figures on the Network page.",
            "http://ADDRESS/admin/ - the Pi-hole's own page.", probe="/admin/",
            steps=["Open the Pi-hole admin page and copy the address.", "Paste it below and press Test."]),
    Service("camwatch", "camwatch", "Camera visits on Security and Family, and the cameras in this Studio.",
            "http://ADDRESS:8080 - camwatch's own page.", probe="/healthz", setting="CAMFEED",
            secret=("Link key", "camwatch: Settings -> Home Deck -> make a link key"),
            steps=["Open camwatch, go to Settings and then Home Deck, and make a link key.",
                   "Paste camwatch's address and that key below, then press Test."]),
    Service("labpanel", "Lab panel", "The nodes, guests and hold-to-run commands on the Lab page.",
            "http://ADDRESS:8790, the lab panel service.", probe="/health", setting="LABPANEL",
            steps=["Paste the lab panel service's address below and press Test."]),
    Service("ollama", "Ollama", "The Local AI page: the models on your PC, and chat with them.",
            "http://ADDRESS:11434 on the machine with the graphics card.", probe="/api/tags", setting="OLLAMA",
            steps=["On the machine running Ollama, make sure it listens on the network, not just localhost.",
                   "Paste http://ADDRESS:11434 below and press Test."]),
]
BY_ID = {s.id: s for s in SERVICES}


def saved(conf=None):
    return (conf or load(SETTINGS, {})).get("services") or {}


def url(id, conf=None):
    """The address for this service: what you connected, else what the settings file was installed
    with, else nothing - which every reader treats as "this house has not got one"."""
    got = saved(conf).get(id) or {}
    if got.get("url"):
        return str(got["url"]).rstrip("/")
    s = BY_ID.get(id)
    fallback = getattr(C, s.setting, "") if s and s.setting else ""
    return str(fallback or "").rstrip("/")


def set_url(id, address, key=None):
    """-> error, or None. Saves into settings.json; nothing restarts."""
    if id not in BY_ID:
        return "unknown service"
    address = (address or "").strip().rstrip("/")
    if address and not address.startswith(("http://", "https://")):
        return "the address starts with http:// or https://"
    with _lock:
        conf = load(SETTINGS, {})
        all_of = dict(conf.get("services") or {})
        if address:
            all_of[id] = {"url": address}
        else:
            all_of.pop(id, None)
        conf["services"] = all_of
        save(SETTINGS, conf)
    if key is not None and BY_ID[id].secret:
        from .store import SECRETS
        sec = load(SECRETS, {})
        if key:
            sec[id] = key
        else:
            sec.pop(id, None)
        save(SECRETS, sec)
    return None


def test(id, address=None):
    """Ask the machine whether it is there. Any HTTP answer counts, including 401 and a redirect:
    we are asking whether something is listening, not whether we may log in."""
    s = BY_ID.get(id)
    if not s:
        return {"ok": False, "why": "unknown service"}
    base = (address or url(id)).rstrip("/")
    if not base:
        return {"ok": False, "why": "no address yet"}
    t = time.time()
    try:
        req = urllib.request.Request(base + s.probe, method="GET", headers={"User-Agent": "home-deck-studio"})
        urllib.request.urlopen(req, timeout=4, context=NOCHECK).close()
    except urllib.error.HTTPError:
        pass
    except Exception as e:
        return {"ok": False, "why": str(e)[:120]}
    return {"ok": True, "ms": round((time.time() - t) * 1000)}


def state():
    """[{id, name, gives, find, steps, needs_key, url, on}] for the Studio. No network."""
    got = saved()
    return [{"id": s.id, "name": s.name, "gives": s.gives, "find": s.find, "steps": s.steps,
             "needs_key": bool(s.secret), "key_where": s.secret[1] if s.secret else "",
             "url": url(s.id), "on": bool(url(s.id)), "saved_here": s.id in got} for s in SERVICES]
