import datetime as dt, json, logging, os, subprocess, sys, tempfile
from pathlib import Path
import cv2, numpy as np

tmp = Path(tempfile.mkdtemp())
(tmp / "recordings").mkdir(); (tmp / "data").mkdir()
os.environ.update(RECORDINGS_DIR=str(tmp / "recordings"), DATA_DIR=str(tmp / "data"), TIMELAPSE_INTERVAL="1", CAMERA_NAME="camera1")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "app"))
import timelapse as tl  # noqa: E402

if os.name == "nt":   # Windows: no `nice`, and the font lives elsewhere
    tl._ffmpeg = lambda args, log: subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + args).returncode == 0
    tl.FONT = "C\\\\:/Windows/Fonts/arialbd.ttf"

log = logging.getLogger("t"); logging.basicConfig(level=logging.INFO)
day = dt.date.today().isoformat()
rng = np.random.default_rng(0)
t0 = dt.datetime.combine(dt.date.today(), dt.time(8, 0)).timestamp()
for i in range(240):                                            # 240 captures -> ~60 s video at the minimum fps
    frame = np.full((1520, 2688, 3), 40 + i % 200, np.uint8)
    tl.capture(frame, t0 + i * 2)
print("frames saved:", len(list((tl.FRAMES_DIR / 'camera1' / day).glob("*.jpg"))))

folder = tmp / "recordings" / day; folder.mkdir()
for n, (stem, who) in enumerate([("camera1_093000", "person"), ("camera1_101500", "car")]):
    vw = cv2.VideoWriter(str(folder / f"{stem}.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 15, (1280, 720))
    for i in range(150):
        vw.write(np.full((720, 1280, 3), (n * 90 + i) % 255, np.uint8))
    vw.release()
    (folder / f"{stem}.json").write_text(json.dumps({"start": f"{day}T09:30:00", "labels": {who: 0.9}, "test": False, "video": f"{stem}.mp4"}))
(folder / "camera1_093000.faces.json").write_text(json.dumps({"known": [{"name": "Alex"}], "unknown": []}))

lapse, high = tl.build_day(day, log)
def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout or 0)
print(f"{'PASS' if lapse and 15 <= dur(lapse) <= 65 else 'FAIL'}  timelapse built: {lapse and lapse.name}, {lapse and dur(lapse):.1f}s from 240 frames")
print(f"{'PASS' if high and 7 <= dur(high) <= 9 else 'FAIL'}  highlights built: {high and high.name}, {high and dur(high):.1f}s (2 x 4 s)")
print(f"{'PASS' if not (tl.FRAMES_DIR / 'camera1' / day).exists() else 'FAIL'}  frames deleted after the build")
print(f"{'PASS' if [i['day'] for i in tl.available()] == [day] else 'FAIL'}  available(): {tl.available()}")
print("caption for the person clip:", tl._who(folder, "camera1_093000", {"labels": {"person": 0.9}}))
