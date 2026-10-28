"""Drive the camwatch web UI with fake recordings through Flask's test client."""
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

root = Path(tempfile.mkdtemp())
for d in ("recordings", "photos", "data", "live"):
    (root / d).mkdir()
os.environ.setdefault("OBJECT_MODEL", str(Path(__file__).resolve().parents[1] / "models" / "yolov8s-coco.onnx"))
os.environ.update(RECORDINGS_DIR=str(root / "recordings"), PHOTOS_DIR=str(root / "photos"), DATA_DIR=str(root / "data"),
                  LIVE_DIR=str(root / "live"), CAMERA_NAME="camera1", WEB_PASSWORD="", DB_SOCKET=str(root / "nosock"))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "app"))
import webui  # noqa: E402

rng = np.random.default_rng(0)
today = dt.date.today()
(root / "photos" / "Alex").mkdir()
(root / "live" / "camera1").mkdir(exist_ok=True)
cv2.imwrite(str(root / "live" / "camera1" / "frame.jpg"), rng.integers(0, 255, (1520, 2688, 3), dtype=np.uint8))
for n_day in range(3):
    day = (today - dt.timedelta(days=n_day)).isoformat()
    folder = root / "recordings" / day
    folder.mkdir()
    for i in range(4):
        stem = f"camera1_{10 + i:02d}0000"
        start = dt.datetime.fromisoformat(f"{day}T{10 + i:02d}:00:00")
        meta = {"camera": "camera1", "start": start.isoformat(), "end": (start + dt.timedelta(seconds=20)).isoformat(),
                "labels": {"person": 0.9} if i % 2 == 0 else {"car": 0.8}, "zones": [], "test": False, "video": f"{stem}.mp4",
                "plates": [{"plate": "AB12345", "reads": 3, "conf": 0.98}] if i == 1 else [],
                "packages": [{"kind": "delivered", "zone": "doorstep", "at": start.isoformat(), "image": f"{stem}.package-delivered.jpg"}] if i == 2 and n_day == 0 else []}
        (folder / f"{stem}.json").write_text(json.dumps(meta))
        (folder / f"{stem}.mp4").write_bytes(b"\0" * 1000)
        cv2.imwrite(str(folder / f"{stem}.jpg"), rng.integers(0, 255, (1520, 2688, 3), dtype=np.uint8))
        (folder / f"{stem}_faces").mkdir()
        cv2.imwrite(str(folder / f"{stem}_faces" / "unknown_1.jpg"), rng.integers(0, 255, (120, 100, 3), dtype=np.uint8))
        (folder / f"{stem}.faces.json").write_text(json.dumps({"faces_seen": 1, "known": [], "unknown": [
            {"count": 2, "best_guess": "Alex", "best_guess_score": 0.3, "crop": f"{stem}_faces/unknown_1.jpg"}]}))
        pts = [[t * 0.2, "person", 0.3 + 0.01 * t, 0.7 - 0.005 * t, 0.05, 0.2, 0.9] for t in range(40)]
        (folder / f"{stem}.track.json").write_text(json.dumps({"points": pts, "source": "live"}))
(root / "data" / "packages.jsonl").write_text(json.dumps({"kind": "delivered", "zone": "doorstep", "at": dt.datetime.now().isoformat(timespec="seconds"),
                                                          "clip": f"{today}/camera1_120000"}) + "\n")

c = webui.app.test_client()
ok = True


def check(path, method="get", expect=200, ctype=None, **kw):
    global ok
    r = getattr(c, method)(path, **kw)
    good = r.status_code == expect and (ctype is None or r.content_type.startswith(ctype))
    ok &= good
    extra = ""
    if r.content_type.startswith("application/json"):
        extra = json.dumps(r.get_json())[:150]
    print(f"{'PASS' if good else 'FAIL'} {method.upper():4} {path:<52} {r.status_code} {r.content_type.split(';')[0]:<17} {len(r.data):>7}B {extra}")
    return r


check("/dashboard", ctype="text/html")
s = check("/api/status", ctype="application/json").get_json()
check("/view", ctype="text/html")
check("/api/days", ctype="application/json")
check(f"/api/visits?day={today}", ctype="application/json")
check(f"/api/clip/{today}/camera1_100000", ctype="application/json")
check(f"/api/thumb/{today}/camera1_100000.jpg?w=480", ctype="image/jpeg")
r = check("/api/heatmap.jpg?days=7&w=800", ctype="image/jpeg")
print("     heatmap points:", r.headers.get("X-Points"))
check(f"/api/heatmap.jpg?from={today - dt.timedelta(days=6)}&to={today}&label=car", ctype="image/jpeg")
check("/live.jpg?w=960", ctype="image/jpeg")
v = check("/api/version", ctype="application/json").get_json()
want = (Path(__file__).resolve().parents[1] / "app" / "VERSION").read_text().strip()
print(f"{'PASS' if v['version'] == want and v['text'].startswith(want) else 'FAIL'} version {v['text']} (app/VERSION {want})")
print(f"{'PASS' if v['version'] == s['version']['version'] else 'FAIL'} /api/status carries the version")
check("/report", ctype="text/html")          # no database here -> renders the "not available" message
zones_html = check("/zones", ctype="text/html").get_data(as_text=True)
box = zones_html[zones_html.rfind('<div style="position:relative">', 0, zones_html.index('id="cv"')):zones_html.index('id="cv"')]
print(f"{'PASS' if 'id="bg"' in box and 'id="heat"' not in box and 'class="row"' not in box else 'FAIL'} zone drawing layer covers only the picture (same zones on phone and computer)")
check("/", ctype="text/html")
check(f"/clip/{today}/camera1_100000", ctype="text/html")
# tagging from the wall view: tag an unknown face with a new name, then the plate, then star
check(f"/clip/{today}/camera1_100000/label", "post", 302, data={"new_name": "Sam", "crop": "camera1_100000_faces/unknown_1.jpg", "add_to_library": "1"})
after = check(f"/api/clip/{today}/camera1_100000").get_json()
print("     face tag now:", after["faces"][0].get("tag"), "| library:", sorted(p.name for p in (root / "photos").iterdir()))
check("/plates", "post", 302, data={"plate": "AB12345", "name": "Family car"})
v = [x for x in check(f"/api/visits?day={today}").get_json() if x["stem"] == "camera1_110000"][0]
print("     plate name in visit:", v["plates"])
check(f"/clip/{today}/camera1_100000/star", "post", 302)
print("     starred:", check(f"/api/clip/{today}/camera1_100000").get_json()["star"])
print("status summary:", {k: s[k] for k in ("today", "week", "last", "packages_waiting")})

# the weekly report template with realistic data (no database: call the template directly)
monday = today - dt.timedelta(days=today.weekday())
fake = {"monday": monday, "sunday": monday + dt.timedelta(days=6), "total": 42, "prev_total": 35, "change": 20,
        "per_day": [(monday + dt.timedelta(days=i), i * 3) for i in range(7)], "per_hour": [h % 5 for h in range(24)], "busiest_hour": 17,
        "people": [{"name": "Alex", "n": 9, "first": dt.datetime.now(), "last": dt.datetime.now(), "arrived": 3, "lft": 2}],
        "unknown": 4, "door_visits": 2, "cars": [{"at": dt.datetime.now(), "day": str(today), "stem": "camera1_110000", "who": "Family car", "direction": "arrived"}],
        "animals": [{"kind": "dog", "n": 2}], "packages": [{"kind": "delivered", "zone": "doorstep", "at": "2026-10-25T10:00:00", "clip": f"{today}/camera1_120000"}]}
with webui.app.test_request_context("/report"):
    html = webui.render_template("report.html", r=fake, error=None, monday=monday, label="person", people=[],
                                 prev_week=monday - dt.timedelta(days=7), next_week=monday + dt.timedelta(days=7), this_monday=monday)
print(f"{'PASS' if 'Week' in html and 'Alex' in html and 'Family car' in html else 'FAIL'} report template renders ({len(html)} B)")

# Select on the Clips page: download several clips as one zip, delete several at once
import io  # noqa: E402
import zipfile  # noqa: E402
old = (today - dt.timedelta(days=2)).isoformat()
page = c.get(f"/?day={old}").get_data(as_text=True)
good = "☑ Select" in page and f'data-clip="{old}/camera1_100000"' in page and "pickbar" in page
ok &= good
print(f"{'PASS' if good else 'FAIL'} the Clips page has Select, and every clip card carries its clip")
r = c.post("/clips/download", data={"clip": [f"{old}/camera1_100000", f"{old}/camera1_110000"]})
names = sorted(zipfile.ZipFile(io.BytesIO(r.data)).namelist()) if r.status_code == 200 else []
good = names == [f"{old}_camera1_100000.jpg", f"{old}_camera1_100000.mp4", f"{old}_camera1_110000.jpg", f"{old}_camera1_110000.mp4"] \
    and "attachment" in r.headers.get("Content-Disposition", "")
ok &= good
print(f"{'PASS' if good else 'FAIL'} Download gives one zip with the videos and pictures: {names}")
r = c.post("/clips/download", data={"clip": ["../etc/camera1_100000"]})
ok &= r.status_code == 404
print(f"{'PASS' if r.status_code == 404 else 'FAIL'} Download refuses a path outside the recordings ({r.status_code})")
r = c.post("/clips/delete", data={"clip": [f"{old}/camera1_100000", f"{old}/camera1_110000"], "back": f"/?day={old}"})
left = sorted(p.name for p in (root / "recordings" / old).iterdir() if p.name.startswith(("camera1_100000", "camera1_110000")))
good = r.status_code == 302 and r.headers["Location"].endswith(f"/?day={old}") and not left \
    and (root / "recordings" / old / "camera1_120000.mp4").exists()
ok &= good
print(f"{'PASS' if good else 'FAIL'} Delete removes only the ticked clips and goes back to the same list (left: {left})")
r = c.post("/clips/delete", data={"clip": [f"{old}/camera1_120000"], "back": "//evil.example"})
good = not r.headers["Location"].startswith("//evil")
ok &= good
print(f"{'PASS' if good else 'FAIL'} Delete never sends you to another site")
print("ALL PASS" if ok else "SOME FAILED")
