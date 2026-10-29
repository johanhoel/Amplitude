"""The link with Home Deck's Studio: the key, the sync, the camera finder's names and People's missing photos."""
import json
import os
import sys
import tempfile
import time
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
import webui  # noqa: E402

ok = True


def report(good, text):
    global ok
    ok &= bool(good)
    print(f"{'PASS' if good else 'FAIL'} {text}")


c = webui.app.test_client()
login = {"Authorization": "Basic YWRtaW46c2VjcmV0LXB3"}          # admin:secret-pw
SYNC = {"devices": [{"ip": "192.168.1.50", "name": "garage-cam", "vendor": "Shenzhen Reolink Technology", "mac": "ec:71:db:00:00:01"},
                    {"ip": "192.168.1.61", "name": "", "vendor": "Hangzhou Hikvision Digital", "mac": "44:19:b6:00:00:02"},
                    {"ip": "192.168.1.70", "name": "camille-laptop", "vendor": "Apple, Inc.", "mac": "a4:83:e7:00:00:03"},
                    {"ip": "192.168.1.80", "name": "office-ap", "vendor": "Ubiquiti Inc", "mac": "f4:92:bf:00:00:04"},
                    {"ip": "8.8.8.8", "name": "outside", "vendor": "x", "mac": ""}],
        "people": ["anna", "erik", "<script>"]}

# ---------- the key ----------
report(c.post("/api/link/sync", json=SYNC).status_code == 401, "without a key, the link is closed")
report(c.post("/api/link/sync", json=SYNC, headers=login).status_code == 401, "the web password does not open the link")
page = c.get("/settings", headers=login).get_data(as_text=True)
report('id="homedeck"' in page and "Make a link key" in page, "Settings offers a link key")
c.post("/settings/homedeck/key", headers=login)
key = homedeck.key()
report(len(key) >= 24, "Make a link key stores a random key")
report(c.post("/api/link/sync", json=SYNC, headers={"Authorization": "Bearer wrong"}).status_code == 401,
       "a wrong key is refused")

# ---------- the sync ----------
(root / "photos" / "Anna").mkdir()
(root / "photos" / "Bob").mkdir()
(root / "data" / "sightings.jsonl").write_text(
    json.dumps({"video": "2026-10-29/camera1_101500.mp4", "name": "Anna", "at": "2026-10-29T10:15:00"}) + "\n"
    + json.dumps({"video": "2026-10-29/garage_120000.mp4", "name": "Anna", "at": "2026-10-29T12:00:00"}) + "\n")
r = c.post("/api/link/sync", json=SYNC, headers={"Authorization": f"Bearer {key}"})
answer = r.get_json()
report(r.status_code == 200 and [x["name"] for x in answer["cameras"]] == ["camera1"]
       and answer["cameras"][0]["slot"] == 1, f"the answer lists the cameras: {answer['cameras']}")
people = {p["name"]: p for p in answer["people"]}
report(people["Anna"]["last_seen"] == "2026-10-29T12:00:00" and people["Anna"]["camera"] == "garage"
       and people["Bob"]["last_seen"] is None, f"the answer says when each person was last seen: {answer['people']}")
kept = homedeck.synced()
report(kept["fresh"] and [d["ip"] for d in kept["devices"]] == ["192.168.1.50", "192.168.1.61", "192.168.1.70", "192.168.1.80"]
       and kept["people"] == ["anna", "erik"], "CamWatch keeps Home Deck's devices and people, without public addresses or odd names")
report([d["ip"] for d in homedeck.camera_devices()] == ["192.168.1.50", "192.168.1.61"],
       "devices from camera makers or with cam in the name count as cameras; Camille's laptop and an access point do not")
page = c.get("/settings", headers=login).get_data(as_text=True)
report("● Linked" in page and "4 network devices, 2 people" in page, "Settings shows the last call")

# ---------- the camera finder ----------
onvif.scan = lambda subnet, timeout=0.5: [{"ip": "192.168.1.50", "rtsp_port": 554, "onvif_port": 8000, "maker": "Reolink", "model": "RLC-810A"}]
found = c.post("/settings/cameras/scan", data={"subnet": "192.168.1.0/24"}, headers=login).get_json()["found"]
by_ip = {f["ip"]: f for f in found}
report(by_ip["192.168.1.50"]["name"] == "garage-cam" and by_ip["192.168.1.50"]["used_by"] == "camera1",
       "the finder names a found camera with Home Deck's name")
report(by_ip.get("192.168.1.61", {}).get("homedeck") and by_ip["192.168.1.61"]["maker"] == "Hangzhou Hikvision Digital"
       and "192.168.1.70" not in by_ip, "the finder adds Home Deck's cameras that the scan missed, and nothing else")

# ---------- People ----------
page = c.get("/people", headers=login).get_data(as_text=True)
report("Home Deck knows these people" in page and ">Erik</button>" in page and ">Anna</button>" not in page,
       "People lists Home Deck's people who have no photos yet")

# ---------- stale and removed ----------
data = json.loads(homedeck.FILE.read_text())
data["at"] = time.time() - 3600
homedeck.FILE.write_text(json.dumps(data))
report("has not called for a while" in c.get("/settings", headers=login).get_data(as_text=True),
       "an old sync shows as a quiet link")
c.post("/settings/homedeck/remove", headers=login)
report(not homedeck.key() and not homedeck.FILE.exists()
       and c.post("/api/link/sync", json=SYNC, headers={"Authorization": f"Bearer {key}"}).status_code == 401,
       "Remove the link deletes the key and the list, and the old key no longer works")

print("ALL PASSED" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
