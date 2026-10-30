"""The Studio: one inventory, the draft, applying it together, and undo.

The thing most worth protecting is that a draft is checked before it is written, not after.
Two cameras sharing a name, or an enabled slot with no stream address, is a recorder that
restarts into a broken config - and the Studio applies several changes at once, so a bad
combination can be made out of two changes that are each fine on their own.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

root = Path(tempfile.mkdtemp())
for d in ("recordings", "photos", "data", "live"):
    (root / d).mkdir()
REPO = Path(__file__).resolve().parents[1]
os.environ.setdefault("OBJECT_MODEL", str(REPO / "models" / "yolov8s-coco.onnx"))
os.environ.update(RECORDINGS_DIR=str(root / "recordings"), PHOTOS_DIR=str(root / "photos"), DATA_DIR=str(root / "data"),
                  LIVE_DIR=str(root / "live"), CAMERA_NAME="camera1", WEB_PASSWORD="secret-pw",
                  RTSP_URL="rtsp://admin:pw@192.168.1.50:554/stream1", DB_SOCKET=str(root / "nosock"))
sys.path.insert(0, str(REPO / "app"))
import homedeck  # noqa: E402
import onvif  # noqa: E402
import settings  # noqa: E402
import studio  # noqa: E402
import webui  # noqa: E402

ok = True


def report(good, text):
    global ok
    ok &= bool(good)
    print(f"{'PASS' if good else 'FAIL'} {text}")


def reset():
    settings.update(cameras=[])
    studio.clear()
    studio._write(studio.HISTORY, [])


# ---- the address out of a stream url --------------------------------
report(studio.host_of("rtsp://admin:p@ss/word@192.168.1.81:554/s") == "192.168.1.81",
       "the camera address is read past a password with / and @ in it")
report(studio.host_of("") == "", "an empty stream address has no host")

# ---- the inventory --------------------------------------------------
reset()
homedeck.save_sync({"devices": [{"ip": "192.168.1.81", "name": "reolink-garage", "vendor": "Reolink", "mac": "a"},
                                {"ip": "192.168.1.30", "name": "pihole", "vendor": "Raspberry Pi", "mac": "b"},
                                {"ip": "192.168.1.50", "name": "cam-front", "vendor": "Reolink", "mac": "c"}],
                    "people": []})
items = studio.inventory(webui.cameras())
kinds = {i["key"]: i for i in items}
report("slot1" in kinds and kinds["slot1"]["added"], "the camera in slot 1 is in the list, as added")
report("ip192.168.1.81" in kinds, "a device Home Deck knows is in the list")
report("ip192.168.1.50" not in kinds,
       "the device that IS camera 1 is not listed again as something to add")
report(kinds["ip192.168.1.81"]["camera_like"] and not kinds["ip192.168.1.30"]["camera_like"],
       "a camera maker is marked, a Pi-hole is not")
homedeck.save_sync({"devices": [{"ip": "192.168.1.84", "name": "", "vendor": "Hangzhou Hikvision Digital", "mac": "d"}],
                    "people": []})
nameless = studio.inventory(webui.cameras())[-1]
report(nameless["name"] == "Hangzhou Hikvision Digital",
       "a device with no name is headed by its maker, not by its address twice")

att = studio.attention(items)
report(any("not added yet" in a["text"] for a in att), "the attention list points at the camera not added")

# ---- the draft is checked before it is written ----------------------
reset()
report(studio.add_change({"kind": "add", "slot": 2, "name": "GARAGE", "rtsp_url": "rtsp://x/1"}) is None,
       "a camera can be added to a free slot")
report(studio.draft()["changes"][0]["name"] == "garage", "the name is stored lowercase")
report(studio.add_change({"kind": "add", "slot": 3, "name": "no-dashes", "rtsp_url": "rtsp://x/1"})
       == "the name must be lowercase letters, digits or _ (max 24)", "a bad name is refused")
report(studio.add_change({"kind": "add", "slot": 3, "name": "shed", "rtsp_url": "http://x/1"})
       == "stream addresses start with rtsp://", "a non-rtsp address is refused")
report(studio.add_change({"kind": "add", "slot": 3, "name": "shed", "rtsp_url": ""})
       == "enter the stream address", "a camera with no stream address is refused")
report(studio.add_change({"kind": "add", "slot": 9, "name": "shed", "rtsp_url": "rtsp://x/1"})
       == "unknown camera", "a slot that does not exist is refused")
report(studio.add_change({"kind": "rename", "slot": 1, "name": "other"})
       == "camera 1 keeps the name it was installed with", "camera 1 cannot be renamed")
report(len(studio.draft()["changes"]) == 1, "none of the refused changes reached the draft")

# two changes that are each fine, and wrong together
report(studio.add_change({"kind": "add", "slot": 3, "name": "garage", "rtsp_url": "rtsp://x/2"})
       == "the name garage is already used",
       "a name that collides with another change in the same draft is refused")

# pressing Add twice for one camera is a correction
studio.add_change({"kind": "add", "slot": 2, "name": "garage2", "rtsp_url": "rtsp://x/3"})
report(len(studio.draft()["changes"]) == 1 and studio.draft()["changes"][0]["name"] == "garage2",
       "adding the same camera again replaces the change instead of making a second one")

# ---- applying -------------------------------------------------------
reset()
studio.add_change({"kind": "add", "slot": 2, "name": "garage", "rtsp_url": "rtsp://u:p@192.168.1.81:554/s"})
studio.add_change({"kind": "disable", "slot": 1})
applied, error = studio.apply()
report(error is None and len(applied) == 2, f"both changes applied together ({error})")
slots = {c["slot"]: c for c in settings.camera_slots()}
report(slots[2]["name"] == "garage" and slots[2]["enabled"], "the new camera is on")
report(not slots[1]["enabled"], "camera 1 was switched off")
report(studio.draft()["changes"] == [], "the draft is empty after applying")
report(studio.apply()[1] == "nothing to apply", "applying an empty draft says so")

# ---- undo -----------------------------------------------------------
report(studio.undo() is None, "the apply can be undone")
slots = {c["slot"]: c for c in settings.camera_slots()}
report(not slots[2]["name"] and slots[1]["enabled"], "undo put the cameras back as they were")
report(studio.undo() == "there is nothing to undo", "there is only one undo")

# ---- removing -------------------------------------------------------
reset()
studio.add_change({"kind": "add", "slot": 2, "name": "garage", "rtsp_url": "rtsp://x/1"})
studio.apply()
studio.add_change({"kind": "remove", "slot": 2})
studio.apply()
report(not {c["slot"]: c for c in settings.camera_slots()}[2]["name"], "a camera can be removed")
reset()
studio.add_change({"kind": "remove", "slot": 1})
studio.apply()
slots = {c["slot"]: c for c in settings.camera_slots()}
report(slots[1]["name"] == settings.primary_camera() and not slots[1]["enabled"],
       "removing camera 1 switches it off and keeps its name, because its recordings stay")

# ---- the password never reaches the browser -------------------------
reset()
studio.add_change({"kind": "add", "slot": 2, "name": "garage", "rtsp_url": "rtsp://admin:hunter2@192.168.1.81/s"})
shown = json.dumps(studio.masked(studio.draft()["changes"], webui.mask_url))
report("hunter2" not in shown, "the camera password is masked out of the draft")
report("192.168.1.81" in shown, "the address itself is still readable")

# ---- the page and its routes ----------------------------------------
reset()
client = webui.app.test_client()
login = {"Authorization": "Basic YWRtaW46c2VjcmV0LXB3"}          # admin:secret-pw
page = client.get("/studio", headers=login)
report(page.status_code == 200, f"/studio answers ({page.status_code})")
body = page.get_data(as_text=True)
report("&lt;i class" not in body and "&lt;/i&gt;" not in body, "no icon markup is printed as text")
state = client.get("/api/studio", headers=login).get_json()
report(isinstance(state.get("items"), list) and "free" in state, "/api/studio returns the inventory")
bad = client.post("/api/studio/draft", headers=login,
                  json={"kind": "add", "slot": 2, "name": "x", "rtsp_url": "http://x"})
report(bad.status_code == 400 and "rtsp" in bad.get_json()["error"], "a refused change answers 400")

# ---- scanning more than one VLAN ------------------------------------
nets = onvif.check_subnets("192.168.1.0/24, 10.0.20.0/24 192.168.1.0/24")
report([str(n) for n in nets] == ["192.168.1.0/24", "10.0.20.0/24"],
       "networks split on commas and spaces, and a repeat is dropped")
for bad, why in [("", "enter at least one network"),
                 ("8.8.8.0/24", "only private"),
                 ("10.0.0.0/8", "at most")]:
    try:
        onvif.check_subnets(bad)
        report(False, f"{bad or 'an empty list'} is refused")
    except ValueError as exc:
        report(why in str(exc), f"{bad or 'an empty list'} is refused ({exc})")
try:
    onvif.check_subnets(" ".join(f"192.168.{n}.0/24" for n in range(onvif.MAX_NETS + 1)))
    report(False, "too many networks is refused")
except ValueError as exc:
    report("at most" in str(exc), f"too many networks is refused ({exc})")
try:
    onvif.check_subnets(" ".join(f"10.0.{n * 4}.0/22" for n in range(5)))
    report(False, "too many addresses in total is refused")
except ValueError as exc:
    report("in one scan" in str(exc), f"too many addresses in total is refused ({exc})")

calls = []
real_scan = onvif.scan
def fake_scan(subnet, timeout=0.5):
    calls.append(subnet)
    ip = "10.0.20.9" if subnet == "10.0.20.0/24" else "192.168.1.9"
    return [{"ip": ip, "rtsp_port": 554, "maker": "Axis", "model": ""}]


onvif.scan = fake_scan
rows = onvif.scan_many(nets)
report(calls == ["192.168.1.0/24", "10.0.20.0/24"], "every network is scanned")
report({r["ip"] for r in rows} == {"192.168.1.9", "10.0.20.9"}, "the results of both are merged")
report({r.get("subnet") for r in rows} == {"192.168.1.0/24", "10.0.20.0/24"},
       "each result says which network it came from")
onvif.scan = real_scan

# the networks worth scanning come from the addresses already known
reset()
homedeck.save_sync({"devices": [{"ip": "10.0.20.40", "name": "cam-shed", "vendor": "Reolink", "mac": "e"}],
                    "people": []})
settings.update(cameras=[{"slot": 2, "name": "yard", "rtsp_url": "rtsp://u:p@172.16.5.11:554/s",
                          "detect_url": "", "enabled": True}])
with webui.app.test_request_context("/", base_url="http://192.168.1.52"):
    suggested = webui.scan_networks()
report("192.168.1.0/24" in suggested, "the network camwatch is reached on is suggested")
report("172.16.5.0/24" in suggested, "the VLAN a configured camera is on is suggested")
report("10.0.20.0/24" in suggested, "the VLAN a Home Deck device is on is suggested")
report(len(suggested) <= onvif.MAX_NETS, "no more networks are suggested than can be scanned")

# ---- the dashboard you design ---------------------------------------
# The dashboard was a fixed page: the same cards in the same order for every
# house. Studio composes it now, so these are the rules that keep a saved
# choice from breaking the page it draws.
reset()
report(studio.layout() == studio.DEFAULT_LAYOUT, "a house that has chosen nothing gets the default dashboard")
report(all(c in studio.card_ids() for c in studio.DEFAULT_LAYOUT), "every card in the default is a real card")
report(studio.set_layout(["stats", "now"]) is None, "a shorter dashboard can be chosen")
report(studio.layout() == ["stats", "now"], "and it is what comes back, in that order")
report(studio.set_layout(["now", "stats"]) is None and studio.layout() == ["now", "stats"],
       "the order is the order given, not the catalogue's")
report(studio.set_layout(["stats", "nope"]) == "unknown card: nope", "a card that does not exist is refused")
report(studio.set_layout(["stats", "stats"]) == "a card can only be on the dashboard once", "a card cannot be on it twice")
report(studio.set_layout("stats") == "that is not a list of cards", "and the whole thing has to be a list")
report(studio.layout() == ["now", "stats"], "none of the refused choices were saved")

settings.update(dashboard_cards=["stats", "gone_in_a_later_version", "now"])
report(studio.layout() == ["stats", "now"],
       "a card removed from a later version leaves no hole in a saved dashboard")

report(studio.landing() == "/m", "the app opens on the phone home until told otherwise")
report(studio.set_landing("/dashboard") is None and studio.landing() == "/dashboard", "and can be told otherwise")
report(studio.set_landing("/nowhere") == "that is not a page camwatch can open on", "but not to a page that is not there")
report(studio.landing() == "/dashboard", "the refused one did not take")
settings.update(landing_page="/a-page-that-went-away")
report(studio.landing() == "/m",
       "a landing page that no longer exists falls back, instead of opening on nothing")
settings.update(landing_page="/dashboard")

homedeck.save_sync({"devices": [{"ip": "10.0.0.9", "name": "x", "vendor": "v", "mac": "f"}], "people": []})
report(studio.cards()[5]["ready"] is True, "the weather card can be chosen once Home Deck is linked")
homedeck.save_sync({"devices": [], "people": []})
homedeck.remove()
cards = {c["id"]: c for c in studio.cards()}
report(cards["weather"]["ready"] is False and cards["weather"]["needs"] == "homedeck",
       "and without the link it says what it is waiting for, rather than being missing")
report(cards["stats"]["ready"] is True, "a card that needs nothing is ready")
settings.update(dashboard_cards=["stats"])
report(cards["stats"]["on"] is not None and studio.cards()[1]["on"] is True,
       "the catalogue says which cards are on")

# ---- what the page and the manifest do with it -----------------------
settings.update(dashboard_cards=["now", "stats"], landing_page="/dashboard")
page = client.get("/dashboard", headers=login).get_data(as_text=True)
report(page.index("Now") < page.index("ui-stats"), "the dashboard draws the cards in the chosen order")
report("ui-tiles" not in page, "and leaves out the ones that are off")
man = client.get("/manifest.webmanifest").get_json()
report(man["start_url"] == "/dashboard", "the phone's home-screen icon opens the chosen page")

state = client.get("/api/studio", headers=login).get_json()
report(len(state["cards"]) == len(studio.CARDS) and state["landing"] == "/dashboard",
       "the Studio is told the whole catalogue and the chosen page")
bad = client.post("/api/studio/layout", headers=login, json={"cards": ["nope"]})
report(bad.status_code == 400 and "unknown card" in bad.get_json()["error"], "a bad layout answers 400")
good = client.post("/api/studio/layout", headers=login, json={"cards": ["stats"], "landing": "/m"})
report(good.status_code == 200 and studio.layout() == ["stats"] and studio.landing() == "/m",
       "a good one saves both at once")

print("ok" if ok else "FAILED")
sys.exit(0 if ok else 1)
