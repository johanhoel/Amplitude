"""Daily timelapse and highlights reel.

  * Each camera's recorder saves a small frame every TIMELAPSE_INTERVAL seconds (/data/timelapse/frames/<camera>/<day>/).
  * Every night at TIMELAPSE_BUILD_AT the previous day becomes, per camera,
      /data/timelapse/<day>-<camera>-timelapse.mp4   the whole day in about TIMELAPSE_SECONDS seconds
      /data/timelapse/<day>-<camera>-highlights.mp4  HIGHLIGHT_SECONDS of every recording, with time and who on screen
    (files from before multi-camera support are named <day>-timelapse.mp4 and belong to the primary camera)
    then the frames are deleted. Videos older than TIMELAPSE_KEEP_DAYS are removed.
  * The web UI's "Build today so far" calls build_day() for today (frames are kept, it is rebuilt at night).
"""
import datetime as dt
import json
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import cv2

from common import env

REC_DIR = Path(env("RECORDINGS_DIR", "/recordings"))
OUT_DIR = Path(env("DATA_DIR", "/data")) / "timelapse"
FRAMES_DIR = OUT_DIR / "frames"
CAMERA = env("CAMERA_NAME", "camera")
INTERVAL = env("TIMELAPSE_INTERVAL", 30, int)
SECONDS = env("TIMELAPSE_SECONDS", 60, int)
BUILD_AT = env("TIMELAPSE_BUILD_AT", "00:15")
KEEP_DAYS = env("TIMELAPSE_KEEP_DAYS", 14, int)
HIGHLIGHT_SECONDS = env("HIGHLIGHT_SECONDS", 4, int)
PRE_ROLL = env("PRE_ROLL_SECONDS", 5, int)
WIDTH = 960
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_build_lock = threading.Lock()
_last_capture = 0.0


def capture(frame, now):
    """Called for every analysed frame; keeps one every INTERVAL seconds."""
    global _last_capture
    if INTERVAL <= 0 or now - _last_capture < INTERVAL:
        return
    _last_capture = now
    t = dt.datetime.fromtimestamp(now)
    folder = FRAMES_DIR / CAMERA / t.strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (WIDTH, round(h * WIDTH / w) // 2 * 2), interpolation=cv2.INTER_AREA) if w > WIDTH else frame
    cv2.imwrite(str(folder / t.strftime("%H%M%S.jpg")), small, [cv2.IMWRITE_JPEG_QUALITY, 80])


def _ffmpeg(args, log):
    cmd = ["nice", "-n", "15", "ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log.warning("ffmpeg failed: %s", r.stderr.strip()[-300:])
    return r.returncode == 0


def _who(folder, stem, meta):
    """Short caption for a recording: names, else plates, else object types."""
    names = []
    for k in (json.loads((folder / f"{stem}.faces.json").read_text()).get("known", [])
              if (folder / f"{stem}.faces.json").exists() else []):
        names.append(k["name"])
    if (folder / f"{stem}.labels.json").exists():
        names += [t["name"] for t in json.loads((folder / f"{stem}.labels.json").read_text())]
    names = list(dict.fromkeys(names))
    if names:
        what = ", ".join(names)
    elif meta.get("vehicles"):
        what = ", ".join(f"{m.get('name') or m.get('plate') or m.get('label', 'car')} {m.get('direction', '')}" for m in meta["vehicles"])
    else:
        labels = meta.get("labels") or {}
        what = " + ".join(sorted(labels, key=lambda k: -labels[k])) if isinstance(labels, dict) else "motion"
    if any(p.get("kind") == "delivered" for p in meta.get("packages") or []):
        what = "package, " + what
    return re.sub(r"[^\w ,.+-]", "", what)[:60] or "motion"


def build_timelapse(day, log, camera=CAMERA):
    frames = sorted((FRAMES_DIR / camera / day).glob("*.jpg"))
    if len(frames) < 10:
        return None
    out = OUT_DIR / f"{day}-{camera}-timelapse.mp4"
    fps = max(10, min(60, round(len(frames) / SECONDS)))
    listfile = OUT_DIR / f".{day}-{camera}-frames.txt"
    listfile.write_text("".join(f"file '{f.as_posix()}'\nduration {1 / fps:.4f}\n" for f in frames))
    ok = _ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listfile), "-vf", f"fps={fps},format=yuv420p",
                  "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-movflags", "+faststart", str(out)], log)
    listfile.unlink(missing_ok=True)
    return out if ok else None


def build_highlights(day, log, camera=CAMERA):
    folder = REC_DIR / day
    if not folder.is_dir():
        return None
    parts = []
    work = OUT_DIR / f".{day}-{camera}-parts"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    for meta_path in sorted(folder.glob("*.json")):
        if re.search(r"\.(faces|labels|track)\.json$", meta_path.name):
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except ValueError:
            continue
        stem = meta_path.name[:-5]
        if not stem.startswith(f"{camera}_"):
            continue
        video = folder / (meta.get("video") or f"{stem}.mp4")
        if meta.get("test") or not video.exists():
            continue
        caption = f"{stem[-6:-4]}:{stem[-4:-2]}  {_who(folder, stem, meta)}".replace(":", r"\:").replace("'", "")
        part = work / f"{len(parts):04d}.ts"
        draw = (f"drawtext=fontfile={FONT}:text='{caption}':x=20:y=h-th-24:fontsize=30:fontcolor=white:"
                "box=1:boxcolor=black@0.55:boxborderw=10")
        if _ffmpeg(["-ss", str(max(0, PRE_ROLL - 1)), "-t", str(HIGHLIGHT_SECONDS), "-i", str(video), "-an",
                    "-vf", f"scale=1280:-2,fps=15,{draw},format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "26", "-f", "mpegts", str(part)], log):
            parts.append(part)
    out = None
    if parts:
        listfile = work / "list.txt"
        listfile.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts))
        out = OUT_DIR / f"{day}-{camera}-highlights.mp4"
        if not _ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listfile), "-c", "copy", "-movflags", "+faststart", str(out)], log):
            out = None
    shutil.rmtree(work, ignore_errors=True)
    return out


def build_day(day, log, keep_frames=False, camera=CAMERA):
    """Build both videos of one camera for a day; returns (timelapse, highlights) (None where nothing could be built)."""
    if not DAY_RE.match(day):
        raise ValueError("bad day")
    with _build_lock:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        lapse, high = build_timelapse(day, log, camera), build_highlights(day, log, camera)
        if lapse and not keep_frames:
            shutil.rmtree(FRAMES_DIR / camera / day, ignore_errors=True)
        log.info("timelapse %s %s: %s, %s (%.0fs)", camera, day, lapse.name if lapse else "no timelapse",
                 high.name if high else "no highlights", time.time() - t0)
        return lapse, high


def prune():
    cutoff = (dt.date.today() - dt.timedelta(days=KEEP_DAYS)).isoformat()
    for f in OUT_DIR.glob("*.mp4"):
        if f.name[:10] < cutoff:
            f.unlink(missing_ok=True)
    for d in FRAMES_DIR.glob("*/*"):
        if d.is_dir() and DAY_RE.match(d.name) and d.name < cutoff:
            shutil.rmtree(d, ignore_errors=True)


def adopt_old_frames(primary):
    """Frames saved before multi-camera support (frames/<day>/) belong to the primary camera."""
    for d in FRAMES_DIR.glob("*"):
        if d.is_dir() and DAY_RE.match(d.name):
            target = FRAMES_DIR / primary / d.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                for f in d.glob("*.jpg"):
                    f.replace(target / f.name)
                shutil.rmtree(d, ignore_errors=True)
            else:
                d.rename(target)


class NightlyBuilder(threading.Thread):
    """Builds every finished day that has frames but no timelapse yet, once BUILD_AT has passed."""

    def __init__(self, log):
        super().__init__(daemon=True, name="timelapse")
        self.log = log

    def run(self):
        while True:
            time.sleep(300)
            try:
                if dt.datetime.now().strftime("%H:%M") < BUILD_AT:
                    continue
                today = dt.date.today().isoformat()
                for folder in sorted((FRAMES_DIR / CAMERA).glob("*")):
                    if folder.is_dir() and DAY_RE.match(folder.name) and folder.name < today:
                        build_day(folder.name, self.log)
                        shutil.rmtree(folder, ignore_errors=True)   # one attempt per day, even if it had too few frames
                prune()
            except Exception:
                self.log.exception("timelapse build failed")


def available(primary=CAMERA):
    """[{day, camera, timelapse, highlights}] newest day first, from the files in OUT_DIR."""
    found = {}
    for f in OUT_DIR.glob("*.mp4"):
        m = re.match(r"^(\d{4}-\d{2}-\d{2})(?:-(.+?))?-(timelapse|highlights)\.mp4$", f.name)
        if m:
            key = (m.group(1), m.group(2) or primary)
            found.setdefault(key, {"day": key[0], "camera": key[1]})[m.group(3)] = f.name
    # newest day first; within a day the primary camera first, then the others by name
    return sorted(sorted(found.values(), key=lambda d: (d["camera"] != primary, d["camera"])), key=lambda d: d["day"], reverse=True)
