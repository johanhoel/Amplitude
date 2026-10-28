"""Screenshots of every CamWatch feature for the README, from demo data - never real footage.

    python dev/screenshots.py [--chrome PATH]      ->  docs/screenshots/*.jpg

Builds the fake recordings of tests/test_webui.py, swaps their random-noise pictures for drawn scenes (a house, a lawn,
figures, a car), serves the web UI on a free local port and photographs each page with headless Chrome: desktop pages
at 1280 px, phone pages at 390 px. Re-run it whenever a page changes and commit the pictures with the change.
"""
import argparse
import datetime as dt
import json
import os
import runpy
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PHONE_W, PHONE_H = 390, 844
OUT = REPO / "docs" / "screenshots"
CHROMES = [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
           "/usr/bin/google-chrome", "/usr/bin/chromium", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]

# (file, path, width, height, phone?) - the README's Screenshots section describes the same list
PAGES = [
    ("dashboard", "/dashboard", 1280, 1150, False),
    ("clips", "/", 1280, 960, False),
    ("clip", "/clip/{today}/garden_100040", 1280, 1250, False),
    ("live", "/live", 1280, 860, False),
    ("zones", "/zones", 1280, 980, False),
    ("report", "/report", 1280, 1150, False),
    ("strangers", "/strangers", 1280, 820, False),
    ("settings", "/settings", 1440, 1050, False),
    ("settings-cameras", "/settings#cameras", 1280, 1000, False),
    ("settings-offsite", "/settings#offsite", 1280, 900, False),
    ("settings-updates", "/settings#updates", 1280, 760, False),
    ("settings-storage", "/settings#storage", 1280, 900, False),
    ("requests", "/requests", 1280, 720, False),
    ("phone-home", "/m", PHONE_W, PHONE_H, True),
    ("phone-wall", "/view", PHONE_W, PHONE_H, True),
    ("phone-settings", "/settings#cameras", PHONE_W, PHONE_H, True),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome", default=next((c for c in CHROMES if Path(c).exists()), None))
    args = ap.parse_args()
    if not args.chrome:
        raise SystemExit("no Chrome / Edge found - pass --chrome PATH")

    sys.argv = sys.argv[:1]
    os.environ.setdefault("RTSP_URL", "rtsp://admin:example@192.0.2.10:554/stream1")
    with open(os.devnull, "w") as quiet:          # test_webui prints its checks
        stdout, sys.stdout = sys.stdout, quiet
        ns = runpy.run_path(str(REPO / "tests" / "test_webui.py"))
        sys.stdout = stdout
    root, webui = ns["root"], ns["webui"]
    import cv2
    import numpy as np
    import settings
    demo_data(root, settings, cv2, np)
    demo_update()

    def site(environ, start_response):
        """The web UI, plus /__frame: each page is shot inside a frame of the wanted size - headless Chrome won't go below
        ~500 px wide (phones) and doesn't scroll to a #section of a long page by itself (the frame's script does)."""
        if environ["PATH_INFO"] != "/__frame":
            return webui.app(environ, start_response)
        import html
        import urllib.parse
        q = {k: v[0] for k, v in urllib.parse.parse_qs(environ.get("QUERY_STRING", "")).items()}
        body = (f'<body style="margin:0;background:#101418"><iframe id="f" src="{html.escape(q["src"])}" width="{int(q["w"])}" '
                f'height="{int(q["h"])}" style="border:0;display:block"></iframe><script>'
                "const f = document.getElementById('f');"
                "f.onload = () => setTimeout(() => { const id = location.search.match(/%23([\\w-]+)/);"
                "  const el = id && f.contentDocument.getElementById(id[1]);"
                "  if (el) f.contentWindow.scrollTo(0, el.getBoundingClientRect().top + f.contentWindow.scrollY - 76); }, 1500);"
                "</script></body>").encode()
        start_response("200 OK", [("Content-Type", "text/html"), ("Content-Length", str(len(body)))])
        return [body]

    port = free_port()
    from waitress import serve
    threading.Thread(target=serve, args=(site,), kwargs={"host": "127.0.0.1", "port": port, "threads": 8, "_quiet": True},
                     daemon=True).start()
    time.sleep(1.5)
    OUT.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    profile = tempfile.mkdtemp()
    try:
        for name, path, w, h, phone in PAGES:
            png = Path(profile) / f"{name}.png"
            import urllib.parse
            url = f"http://127.0.0.1:{port}/__frame?w={w}&h={h}&src={urllib.parse.quote(path.format(today=today))}"
            cmd = [args.chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--mute-audio",
                   f"--user-data-dir={profile}", f"--window-size={max(w, 600)},{h}", "--virtual-time-budget=8000",
                   f"--force-device-scale-factor={2 if phone else 1}", f"--screenshot={png}", url]
            try:
                subprocess.run(cmd, capture_output=True, timeout=60)
            except subprocess.TimeoutExpired:
                pass
            img = cv2.imread(str(png))
            if img is None:
                print(f"FAILED  {name}")
                continue
            scale = 2 if phone else 1
            img = img[:h * scale, :w * scale]
            cv2.imwrite(str(OUT / f"{name}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 82])
            print(f"saved   docs/screenshots/{name}.jpg  {img.shape[1]}x{img.shape[0]}")
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------- demo data: drawn pictures instead of noise ----------

def scene(cv2, np, seed, people=0, car=False, garden=False, night=False, w=1280, h=720):
    """A drawn camera view: sky, hedge, lawn, path, a house wall with a door - and figures or a car."""
    rng = np.random.default_rng(seed)
    img = np.zeros((h, w, 3), np.uint8)
    top, bottom = ((70, 40, 25), (120, 80, 50)) if night else ((235, 200, 150), (250, 230, 205))
    for y in range(int(h * 0.42)):                                   # sky gradient (BGR)
        t = y / (h * 0.42)
        img[y] = [int(a + (b - a) * t) for a, b in zip(top, bottom)]
    green = (40, 95, 45) if garden else (55, 110, 70)
    img[int(h * 0.42):] = [int(c * (0.45 if night else 1)) for c in green]
    cv2.rectangle(img, (0, int(h * 0.36)), (w, int(h * 0.45)), [int(c * (0.4 if night else 0.7)) for c in (30, 70, 35)], -1)  # hedge
    for _ in range(40):                                              # lawn texture
        x, y = int(rng.integers(0, w)), int(rng.integers(int(h * 0.46), h))
        cv2.line(img, (x, y), (x + 3, y - 8), [int(c * 0.8) for c in green], 2)
    path = np.array([[int(w * 0.38), h], [int(w * 0.62), h], [int(w * 0.56), int(h * 0.45)], [int(w * 0.47), int(h * 0.45)]])
    cv2.fillPoly(img, [path], (150, 160, 170) if not night else (70, 75, 80))
    if not garden:                                                   # house wall, door, window
        cv2.rectangle(img, (int(w * 0.68), int(h * 0.12)), (w, int(h * 0.62)), (175, 195, 215) if not night else (80, 90, 100), -1)
        cv2.rectangle(img, (int(w * 0.75), int(h * 0.30)), (int(w * 0.83), int(h * 0.62)), (60, 70, 120), -1)
        cv2.circle(img, (int(w * 0.815), int(h * 0.47)), 5, (60, 190, 230), -1)
        cv2.rectangle(img, (int(w * 0.88), int(h * 0.22)), (int(w * 0.97), int(h * 0.38)), (200, 170, 120) if not night else (60, 180, 230), -1)
    else:                                                            # a tree and a bench
        cv2.rectangle(img, (int(w * 0.18), int(h * 0.30)), (int(w * 0.20), int(h * 0.55)), (40, 60, 90), -1)
        cv2.circle(img, (int(w * 0.19), int(h * 0.27)), int(h * 0.12), (40, 120, 50), -1)
        cv2.rectangle(img, (int(w * 0.70), int(h * 0.55)), (int(w * 0.86), int(h * 0.58)), (60, 90, 130), -1)
    if car:
        x, y = int(w * 0.10), int(h * 0.58)
        cv2.rectangle(img, (x, y), (x + 300, y + 80), (60, 60, 170), -1)
        cv2.rectangle(img, (x + 60, y - 50), (x + 230, y + 5), (60, 60, 170), -1)
        cv2.rectangle(img, (x + 75, y - 40), (x + 215, y), (200, 180, 150), -1)
        for cx in (x + 65, x + 235):
            cv2.circle(img, (cx, y + 82), 28, (30, 30, 30), -1)
        cv2.rectangle(img, (x + 120, y + 50), (x + 180, y + 66), (235, 235, 235), -1)
    for i in range(people):
        x = int(w * (0.50 + 0.07 * i))
        y = int(h * (0.86 - 0.04 * i))
        coat = [(150, 90, 40), (60, 60, 160), (70, 140, 70)][i % 3]
        cv2.circle(img, (x, y - 205), 26, (150, 180, 220), -1)       # head
        cv2.ellipse(img, (x, y - 222), (27, 14), 0, 180, 360, (40, 50, 70), -1)
        cv2.rectangle(img, (x - 34, y - 175), (x + 34, y - 70), coat, -1)
        cv2.line(img, (x - 15, y - 70), (x - 22, y), (50, 50, 60), 16)
        cv2.line(img, (x + 15, y - 70), (x + 22, y), (50, 50, 60), 16)
        cv2.line(img, (x - 34, y - 165), (x - 52, y - 95), coat, 14)
        cv2.line(img, (x + 34, y - 165), (x + 52, y - 95), coat, 14)
    return img


def face(cv2, np, colour, w=200, h=240):
    img = np.full((h, w, 3), (215, 225, 235), np.uint8)
    cv2.ellipse(img, (w // 2, int(h * 0.55)), (int(w * 0.32), int(h * 0.36)), 0, 0, 360, (150, 180, 220), -1)
    cv2.ellipse(img, (w // 2, int(h * 0.30)), (int(w * 0.36), int(h * 0.20)), 0, 180, 360, colour, -1)
    for ex in (int(w * 0.38), int(w * 0.62)):
        cv2.circle(img, (ex, int(h * 0.52)), 7, (40, 40, 40), -1)
    cv2.ellipse(img, (w // 2, int(h * 0.70)), (int(w * 0.12), int(h * 0.05)), 0, 0, 180, (60, 60, 140), 4)
    return img


def demo_update():
    """Settings -> Updates with a new version on a fake GitHub and the host helper installed."""
    import json
    import updates

    def github(path, token, raw=False):
        if "/commits?" in path:
            return [{"sha": "4c1d9e2" + "0" * 33, "commit": {"committer": {"date": "2026-10-29T08:00:00Z"},
                                                            "message": "CamWatch: quiet hours for pushes"}}]
        if "/contents/" in path:
            return "2026.10.29"
        return {"status": "ahead"}
    updates._get = github
    updates.DIR.mkdir(parents=True, exist_ok=True)
    updates.STATUS.write_text(json.dumps({"helper": True, "state": "done", "finished": "2026-10-28T09:12:40",
                                          "message": "updated to 2026.10.28 (3b35f6f)"}))
    (updates.DIR / "host.json").write_text(json.dumps({
        "recordings": "/mnt/hdd/camwatch/recordings", "can_mount": True, "hostname": "camwatch",
        "disks": [{"mount": "/", "fs": "ext4", "size": 64e9, "free": 41e9, "network": False},
                  {"mount": "/mnt/hdd", "fs": "ext4", "size": 2000e9, "free": 1310e9, "network": False},
                  {"mount": "/mnt/camwatch-net/nas-camwatch", "fs": "nfs4", "size": 8000e9, "free": 5200e9, "network": True}]}))
    import settings
    settings.update(update={"repo": "johanhoel/Amplitude", "folder": "CamWatch", "branch": "main", "token": "demo"})
    import feature_requests
    feature_requests._states["at"] = 9e99      # no state check against GitHub
    feature_requests._save([
        {"id": "20261021090000000000", "created": "2026-10-21T09:00:00", "title": "Quiet hours for pushes",
         "text": "No pushes between 23:00 and 06:00, except for strangers.", "number": 12, "state": "closed",
         "url": "https://github.com/johanhoel/Amplitude/issues/12", "version": "2026.10.21"},
        {"id": "20261028101500000000", "created": "2026-10-28T10:15:00", "title": "Show the battery of wireless cameras",
         "text": "A small battery icon on the camera card, and a push when it is low.", "number": 31, "state": "open",
         "url": "https://github.com/johanhoel/Amplitude/issues/31", "version": "2026.10.28"}])


def demo_data(root, settings, cv2, np):
    today = dt.date.today()
    rec = root / "recordings"
    settings.update(cameras=[{"slot": 1}, {"slot": 2, "name": "garden", "rtsp_url": "rtsp://cam:example@192.0.2.11/stream1",
                                           "detect_url": "rtsp://cam:example@192.0.2.11/stream2", "enabled": True}],
                    zones=[{"name": "door", "type": "trigger", "points": [[0.72, 0.62], [0.86, 0.62], [0.86, 0.95], [0.72, 0.95]]},
                           {"name": "street", "type": "ignore", "points": [[0, 0.36], [1, 0.36], [1, 0.45], [0, 0.45]]},
                           {"name": "doorstep", "type": "package", "points": [[0.66, 0.66], [0.80, 0.66], [0.80, 0.80], [0.66, 0.80]]},
                           {"name": "driveway", "type": "parking", "points": [[0.05, 0.55], [0.36, 0.55], [0.36, 0.90], [0.05, 0.90]]}])
    for day_folder in rec.iterdir():
        for snap in day_folder.glob("camera1_*.jpg"):
            stem = snap.stem
            hour = int(stem.split("_")[1][:2])
            meta = json.loads((day_folder / f"{stem}.json").read_text())
            labels = meta.get("labels") or {}
            cv2.imwrite(str(snap), scene(cv2, np, hash(stem) % 1000, people=1 if "person" in labels else 0, car="car" in labels))
        for crop in day_folder.glob("*_faces/*.jpg"):
            cv2.imwrite(str(crop), face(cv2, np, (40, 60, 90)))
    # a second camera, one visit seen by both cameras, a starred clip
    folder = rec / today.isoformat()
    stem = "garden_100040"
    start = dt.datetime.combine(today, dt.time(10, 0, 40))
    (folder / f"{stem}.json").write_text(json.dumps({"camera": "garden", "start": start.isoformat(),
                                                     "end": (start + dt.timedelta(seconds=25)).isoformat(),
                                                     "labels": {"person": 0.93}, "zones": [], "test": False, "video": f"{stem}.mp4"}))
    (folder / f"{stem}.mp4").write_bytes(b"\0" * 1000)
    cv2.imwrite(str(folder / f"{stem}.jpg"), scene(cv2, np, 7, people=1, garden=True))
    meta_path = folder / "camera1_130000.json"
    meta = json.loads(meta_path.read_text())
    meta["unusual"] = "no car on camera1 between 12:00 and 14:00 on weekdays in the last 26 days"
    meta_path.write_text(json.dumps(meta))
    # live pictures and heartbeats
    for cam, kw in (("camera1", {"people": 2}), ("garden", {"garden": True})):
        (root / "live" / cam).mkdir(exist_ok=True)
        cv2.imwrite(str(root / "live" / cam / "frame.jpg"), scene(cv2, np, 3, **kw))
        (root / "live" / cam / "info.json").write_text(json.dumps({"name": cam}))

    def keep_alive():
        while True:
            for cam in ("camera1", "garden"):
                (root / "live" / cam / "alive").touch()
            time.sleep(10)
    threading.Thread(target=keep_alive, daemon=True).start()
    # recurring strangers
    groups = []
    for g, colour in enumerate([(30, 40, 60), (90, 120, 160)]):
        faces = []
        for n, day_folder in enumerate(sorted(rec.iterdir())[:3]):
            crop_dir = day_folder / f"stranger{g}_faces"
            crop_dir.mkdir(exist_ok=True)
            cv2.imwrite(str(crop_dir / "1.jpg"), face(cv2, np, colour))
            faces.append({"day": day_folder.name, "stem": "camera1_100000", "crop": f"stranger{g}_faces/1.jpg",
                          "start": f"{day_folder.name}T10:00:00"})
        groups.append({"id": f"g{g}", "faces": faces, "clips": 3, "days": 3, "first": faces[0]["start"], "last": faces[-1]["start"],
                       "probably": {"name": "Alex", "score": 0.41} if g == 0 else None})
    (root / "data" / "strangers.json").write_text(json.dumps({"groups": groups, "updated": dt.datetime.now().isoformat(timespec="seconds"), "days": 30}))


if __name__ == "__main__":
    main()
