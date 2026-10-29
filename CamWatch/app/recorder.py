"""Motion + object detection, event recording, ntfy alerts and Home Assistant for one RTSP camera.

Two connections to the camera:
  * ffmpeg copies the main stream (no re-encode) into short rolling segments in /buffer
  * OpenCV decodes DETECT_URL (ideally the low-res substream) for detection
Cheap pixel motion detection runs on every frame; when something moves, YOLO checks whether
it is a person (or another DETECT_OBJECTS class). Confirmed detections start an event; the
segments covering [start - pre-roll, end + post-roll] are stitched into one file under
/recordings/YYYY-MM-DD/.
"""
import os

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import collections
import datetime as dt
import json
import queue
import subprocess
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from common import Ntfy, app_version, clip_url, env, env_bool, prune_recordings, setup_logging
import settings
from plates import PlateTally, match_known
from packages import PackageWatcher
import timelapse
from household import HouseholdCheck, PendingAlert, people_boxes, quiet_title
from homeassistant import HomeAssistant, zone_key
import alerts
import offsite
from unusual import Rarity

log = setup_logging("recorder")

CAMERA = env("CAMERA_NAME", "camera")
SLOT = env("CAMERA_SLOT", 0, int)  # set by camslot.py; 0 = started directly, no restart on camera changes
RTSP_URL = env("RTSP_URL")
DETECT_URL = env("DETECT_URL") or RTSP_URL
REC_DIR = Path(env("RECORDINGS_DIR", "/recordings"))
BUF_DIR = Path(env("BUFFER_DIR", "/buffer"))

SEGMENT_SECONDS = env("SEGMENT_SECONDS", 2, int)
PRE_ROLL = env("PRE_ROLL_SECONDS", 5, int)
POST_ROLL = env("POST_ROLL_SECONDS", 10, int)
MAX_EVENT = env("MAX_EVENT_SECONDS", 300, int)
RECORD_AUDIO = env_bool("RECORD_AUDIO", True)

DETECT_FPS = env("DETECT_FPS", 5, float)
DETECT_WIDTH = env("DETECT_WIDTH", 640, int)
PIXEL_THRESHOLD = env("MOTION_PIXEL_THRESHOLD", 25, int)
MIN_AREA = env("MOTION_MIN_AREA", 0.01, float)
MAX_AREA = env("MOTION_MAX_AREA", 0.60, float)
MIN_FRAMES = env("MOTION_MIN_FRAMES", 3, int)
MASK_SPEC = env("MOTION_MASK", "")

# "objects": motion must be confirmed by YOLO. "motion": any motion triggers (no model needed).
DETECT_MODE = env("DETECT_MODE", "objects")
DETECT_OBJECTS = [s.strip() for s in env("DETECT_OBJECTS", "person").split(",") if s.strip()]
OBJECT_MODEL = Path(env("OBJECT_MODEL", "/models/yolov8n.onnx"))
OBJECT_CONFIDENCE = env("OBJECT_CONFIDENCE", 0.5, float)
OBJECT_MIN_AREA = env("OBJECT_MIN_AREA", 0.002, float)
OBJECT_MIN_HITS = env("OBJECT_MIN_HITS", 2, int)
# Hits needed within the last OBJECT_WINDOW YOLO passes, so one missed frame doesn't restart the count
OBJECT_WINDOW = max(OBJECT_MIN_HITS, env("OBJECT_WINDOW", 3, int))
OBJECT_INTERVAL = env("OBJECT_INTERVAL", 0.2, float)
TRACK_LEAD = 6  # seconds of detections before an event starts that go into its track
# Parking zones: a vehicle with its wheels in the zone = occupied. A change that holds for PARKING_CONFIRM
# seconds is logged as the car arriving / leaving, with a clip reaching PARKING_LEAD seconds before it.
PARKING_CHECK = env("PARKING_CHECK_SECONDS", 5, float)
PARKING_CONFIRM = env("PARKING_CONFIRM_SECONDS", 20, float)
PARKING_LEAD = 20
# In objects mode, motion this small is enough to ask YOLO (a distant person is well under MOTION_MIN_AREA)
GATE_AREA = env("MOTION_GATE_AREA", min(MIN_AREA, OBJECT_MIN_AREA / 2), float)
OFFLINE_AFTER = env("OFFLINE_AFTER_SECONDS", 120, int)
# Vehicles etc. that stay put (parked car) stop triggering after this long. People never count as parked.
STATIONARY_SECONDS = env("STATIONARY_SECONDS", 30, int)
MOVING_LABELS = {"person", "dog", "cat", "bird", "horse", "sheep", "cow", "bear"}
VEHICLES = {"car", "truck", "bus", "motorcycle"}
# Read number plates of moving vehicles (needs a vehicle class in DETECT_OBJECTS)
PLATE_READING = env_bool("PLATE_READING", True)
PLATE_INTERVAL = env("PLATE_INTERVAL", 1.0, float)
PLATE_NOTIFY = env("PLATE_NOTIFY", "all")  # all | unknown | none
DATA_DIR = Path(env("DATA_DIR", "/data"))

NOTIFY_COOLDOWN = env("NOTIFY_COOLDOWN_SECONDS", 60, int)
NOTIFY_SNAPSHOT = env_bool("NOTIFY_SNAPSHOT", True)

# With several cameras only one recorder (the primary) cleans up the shared recordings folder.
# How long clips stay: Settings -> Storage (settings.storage()), read at every cleanup.
PRUNE = env_bool("PRUNE_RECORDINGS", True)

# Alert snapshots are scaled down to this width: a full 4 MP JPEG makes the push arrive noticeably later
NOTIFY_WIDTH = env("NOTIFY_WIDTH", 1280, int)

LIVE_DIR = Path(env("LIVE_DIR", "/live")) / CAMERA   # one folder per camera (several recorders share /live)
LIVE_INTERVAL = 0.2

SEG_FMT = "%Y%m%d-%H%M%S"
HEALTH_FILE = Path("/tmp/healthy")                  # frames arriving from the camera
RECORDING_HEALTH_FILE = Path("/tmp/recording")      # video being written to the buffer
RECORDING_STALL = env("RECORDING_STALL_SECONDS", 60, int)


def someone_watching():
    """The web UI touches /live/watching while a live view is open."""
    try:
        return time.time() - (LIVE_DIR / "watching").stat().st_mtime < 10
    except FileNotFoundError:
        return False


def publish_live_frame(frame):
    ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    if ok:
        tmp = LIVE_DIR / "frame.jpg.tmp"
        tmp.write_bytes(jpg.tobytes())
        os.replace(tmp, LIVE_DIR / "frame.jpg")


def take_simulate_request():
    """The web UI's "Simulate motion" button drops this file."""
    trigger = LIVE_DIR / "simulate_motion"
    if trigger.exists():
        trigger.unlink(missing_ok=True)
        return True
    return False


def segments():
    """Buffered segments as (start_ts, end_ts, path), oldest first. end_ts is the file mtime."""
    out = []
    for p in BUF_DIR.glob("*.mkv"):
        try:
            start = dt.datetime.strptime(p.stem, SEG_FMT).timestamp()
            out.append((start, p.stat().st_mtime, p))
        except (ValueError, FileNotFoundError):
            continue
    out.sort()
    return out


class Segmenter(threading.Thread):
    """Keeps ffmpeg writing the main stream into rolling segments, restarting on failure."""

    def __init__(self):
        super().__init__(daemon=True, name="segmenter")
        self.proc = None

    def restart(self):
        """Kill ffmpeg (e.g. hung on a dead connection); run() starts a new one."""
        proc = self.proc
        if proc and proc.poll() is None:
            proc.kill()

    def run(self):
        backoff = 2
        while True:
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                   "-rtsp_transport", "tcp", "-timeout", "10000000",
                   "-i", RTSP_URL, "-map", "0:v:0"]
            cmd += ["-map", "0:a:0?"] if RECORD_AUDIO else ["-an"]
            cmd += ["-c", "copy", "-f", "segment", "-segment_time", str(SEGMENT_SECONDS),
                    "-segment_format", "matroska", "-reset_timestamps", "1", "-strftime", "1",
                    str(BUF_DIR / f"{SEG_FMT}.mkv")]
            started = time.time()
            log.info("recording stream starting")
            self.proc = subprocess.Popen(cmd)
            rc = self.proc.wait()
            if time.time() - started > 60:
                backoff = 2
            log.warning("recording stream exited (code %s), restarting in %ss", rc, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)


class FrameReader(threading.Thread):
    """Drains the detection stream continuously so we always analyse the newest frame."""

    def __init__(self):
        super().__init__(daemon=True, name="frame-reader")
        self.lock = threading.Lock()
        self.frame = None
        self.frame_time = 0.0

    def run(self):
        interval = 1.0 / DETECT_FPS
        backoff = 2
        while True:
            cap = cv2.VideoCapture(DETECT_URL, cv2.CAP_FFMPEG, [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 15000,
                cv2.CAP_PROP_READ_TIMEOUT_MSEC, 15000,
            ])
            if not cap.isOpened():
                log.warning("cannot open detection stream, retrying in %ss", backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            log.info("detection stream connected")
            backoff = 2
            last = 0.0
            while cap.grab():
                now = time.time()
                if now - last < interval:
                    continue
                ok, frame = cap.retrieve()
                if ok:
                    last = now
                    with self.lock:
                        self.frame, self.frame_time = frame, now
            cap.release()
            log.warning("detection stream lost, reconnecting")
            time.sleep(2)

    def latest(self):
        with self.lock:
            return self.frame, self.frame_time


def legacy_mask_zones():
    """Convert the old MOTION_MASK env setting ("x,y x,y ...; ...") into ignore zones."""
    zones = []
    for i, poly in enumerate(filter(None, (s.strip() for s in MASK_SPEC.split(";"))), 1):
        try:
            zones.append({"name": f"ignore {i}", "type": "ignore",
                          "points": [[float(v) for v in pt.split(",")] for pt in poly.split()]})
        except ValueError:
            log.error("ignoring malformed MOTION_MASK polygon: %r", poly)
    return zones


class Zones:
    """Ignore zones mask out motion and detections; trigger zones (if any) are the only
    places where a detection counts. Points are 0..1 fractions of the frame."""

    def __init__(self, zones):
        valid = [z for z in zones if len(z.get("points", [])) >= 3]
        self.ignore = [z for z in valid if z.get("type") == "ignore"]
        self.trigger = [z for z in valid if z.get("type") == "trigger"]
        self.parking = [z for z in valid if z.get("type") == "parking"]
        self.package = [z for z in valid if z.get("type") == "package"]

    @staticmethod
    def _inside(zone, x, y):
        return cv2.pointPolygonTest(np.array(zone["points"], dtype=np.float32), (float(x), float(y)), False) >= 0

    def ignored(self, x, y):
        return any(self._inside(z, x, y) for z in self.ignore)

    def hits(self, x, y):
        """Trigger zones containing the point; None if no trigger zones are defined (= everywhere counts)."""
        if not self.trigger:
            return None
        return [z["name"] for z in self.trigger if self._inside(z, x, y)]

    def mask(self, shape):
        mask = np.full(shape, 255, dtype=np.uint8)
        h, w = shape
        for z in self.ignore:
            cv2.fillPoly(mask, [np.array([[int(x * w), int(y * h)] for x, y in z["points"]], dtype=np.int32)], 0)
        return mask


class MotionDetector:
    def __init__(self, zones, min_area=MIN_AREA):
        self.zones = zones
        self.min_area = min_area
        self.avg = None
        self.mask = None
        self.active_px = 1

    def set_zones(self, zones):
        self.zones = zones
        self.avg = None  # rebuild mask and background on the next frame

    def update(self, frame):
        """Returns (fraction of frame moving, motion boxes in full-frame coordinates)."""
        h, w = frame.shape[:2]
        scale = min(1.0, DETECT_WIDTH / w)
        small = cv2.resize(frame, (int(w * scale), int(h * scale))) if scale < 1 else frame
        gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (21, 21), 0)

        if self.avg is None or self.avg.shape != gray.shape:
            self.avg = gray.astype("float32")
            self.mask = self.zones.mask(gray.shape)
            self.active_px = max(1, cv2.countNonZero(self.mask))
            return 0.0, []

        delta = cv2.absdiff(gray, cv2.convertScaleAbs(self.avg))
        cv2.accumulateWeighted(gray, self.avg, 0.05)
        _, th = cv2.threshold(delta, PIXEL_THRESHOLD, 255, cv2.THRESH_BINARY)
        th = cv2.bitwise_and(cv2.dilate(th, None, iterations=2), self.mask)
        ratio = cv2.countNonZero(th) / self.active_px

        if ratio > MAX_AREA:
            # Whole-frame change: lights on/off, IR switch, camera auto-exposure. Re-baseline.
            self.avg = gray.astype("float32")
            return 0.0, []
        if ratio < self.min_area:
            return ratio, []

        boxes = []
        contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        min_contour = self.min_area * self.active_px / 4
        for c in contours:
            if cv2.contourArea(c) >= min_contour:
                x, y, bw, bh = cv2.boundingRect(c)
                boxes.append(tuple(int(v / scale) for v in (x, y, bw, bh)))
        return ratio, boxes


class Event:
    def __init__(self, start, taken):
        self.start = start
        self.end = None
        self.last_motion = start
        self.peak = 0.0
        self.labels = {}  # label -> best confidence
        self.zones = set()
        self.label_zones = {}  # label -> zones it has been seen in (HA event on each new zone)
        self.test = False
        self.presence_start = None  # for loitering: when an object became continuously visible
        self.last_presence = None
        self.loiter_sent = False
        self.plates = None  # PlateTally when plate reading is on
        self.known_plates = []
        # Where detected objects stood over time: (time, label, foot x, foot y, w, h, conf), 0..1 coordinates.
        # Saved as <stem>.track.json; the presence service turns it into arrived / left.
        self.track = []
        self.vehicles = []  # cars arriving at / leaving a parking zone during this event
        self.unusual = None  # why this visit is unusual for this camera at this time (unusual.py)
        self.linked = None   # {"camera", "clip"}: the same visit seen first by another camera (alerts.claim)
        # Name the clip now so the notification can link to it before the recording is finished.
        started = dt.datetime.fromtimestamp(start)
        self.day = started.strftime("%Y-%m-%d")
        self.dir = REC_DIR / self.day
        self.dir.mkdir(parents=True, exist_ok=True)
        stem = f"{CAMERA}_{started:%H%M%S}"
        n = 1
        while any(self.dir.glob(f"{stem}.*")) or (self.day, stem) in taken:
            n += 1
            stem = f"{CAMERA}_{started:%H%M%S}-{n}"
        self.stem = stem


class Finalizer(threading.Thread):
    """Stitches buffered segments into a finished recording once an event ends."""

    def __init__(self):
        super().__init__(daemon=True, name="finalizer")
        self.queue = queue.Queue()
        self.lock = threading.Lock()
        self.pending = []

    def submit(self, event):
        with self.lock:
            self.pending.append(event)
        self.queue.put(event)

    def oldest_needed(self):
        with self.lock:
            return min((e.start for e in self.pending), default=None)

    def taken(self):
        with self.lock:
            return {(e.day, e.stem) for e in self.pending}

    def run(self):
        while True:
            event = self.queue.get()
            try:
                self.finalize(event)
            except Exception:
                log.exception("failed to save recording")
            finally:
                with self.lock:
                    self.pending.remove(event)

    def finalize(self, event):
        # Wait until a segment starting after the event end exists: the one covering the end is then closed.
        deadline = time.time() + max(30, SEGMENT_SECONDS * 5)
        while time.time() < deadline:
            segs = segments()
            if segs and segs[-1][0] > event.end:
                break
            time.sleep(1)

        segs = segments()[:-1]  # newest file is still being written
        want_from = event.start - PRE_ROLL
        chosen = [p for start, end, p in segs if end >= want_from and start <= event.end]
        if not chosen:
            log.error("no buffered video for event at %s - is the recording stream up?",
                      dt.datetime.fromtimestamp(event.start))
            return

        stem = event.stem
        base = event.dir / stem

        listfile = BUF_DIR / f"concat-{stem}.txt"
        listfile.write_text("".join(f"file '{p}'\n" for p in chosen))
        concat = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                  "-f", "concat", "-safe", "0", "-i", str(listfile), "-map", "0:v:0", "-map", "0:a:0?"]
        try:
            final = Path(f"{base}.mp4")
            tmp = Path(f"{base}.mp4.part")
            rc = subprocess.call(concat + ["-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart",
                                           "-f", "mp4", str(tmp)])
            if rc != 0:
                log.warning("mp4 remux failed, saving as mkv instead")
                final = Path(f"{base}.mkv")
                tmp = Path(f"{base}.mkv.part")
                if subprocess.call(concat + ["-c", "copy", "-f", "matroska", str(tmp)]) != 0:
                    tmp.unlink(missing_ok=True)
                    raise RuntimeError("ffmpeg could not write the recording")
            tmp.rename(final)
        finally:
            listfile.unlink(missing_ok=True)

        plates = event.plates.save(event.dir, stem, event.known_plates) if event.plates else []
        Path(f"{base}.track.json").write_text(json.dumps({
            "source": "live", "start": dt.datetime.fromtimestamp(event.start).isoformat(timespec="seconds"),
            "points": [[round(t - event.start, 2), label, *(round(v, 4) for v in rest)] for t, label, *rest in event.track],
        }))
        Path(f"{base}.json").write_text(json.dumps({
            "camera": CAMERA,
            "start": dt.datetime.fromtimestamp(event.start).isoformat(timespec="seconds"),
            "end": dt.datetime.fromtimestamp(event.end).isoformat(timespec="seconds"),
            "peak_motion": round(event.peak, 4),
            "labels": {k: round(v, 2) for k, v in event.labels.items()},
            "zones": sorted(event.zones),
            "loitering": event.loiter_sent,
            "plates": plates,
            "vehicles": event.vehicles,
            "unusual": event.unusual,
            "linked": event.linked,
            "test": event.test,
            "video": final.name,
        }, indent=2))
        log.info("saved %s (%d segments, %.0fs of motion)", final.relative_to(REC_DIR),
                 len(chosen), event.last_motion - event.start)


class Housekeeper(threading.Thread):
    def __init__(self, finalizer, current_event, segmenter, ntfy):
        super().__init__(daemon=True, name="housekeeper")
        self.finalizer = finalizer
        self.current_event = current_event
        self.segmenter = segmenter
        self.ntfy = ntfy
        self.ha = None  # set by main() once Home Assistant is connected
        self.last_prune = 0.0
        self.started = time.time()
        self.stalled_since = None
        self.last_kill = 0.0

    def run(self):
        while True:
            time.sleep(10)
            try:
                self.check_recording()
            except Exception:
                log.exception("recording check failed")
            self.trim_buffer()
            # one pruner for the shared disk: the first camera that is on (it moves when camera 1 is switched off)
            if PRUNE and time.time() - self.last_prune > 600 and settings.pruning_camera() == CAMERA:
                self.last_prune = time.time()
                try:
                    keep = settings.storage()
                    prune_recordings(REC_DIR, keep["retention_days"], keep["keep_days"], keep["min_free_gb"], log)
                except Exception:
                    log.exception("retention cleanup failed")

    def check_recording(self, now=None):
        """Frames arriving doesn't mean video is being saved: watch the buffer for new segment data.
        No new data for RECORDING_STALL seconds: alert once, and kill ffmpeg so it restarts
        (it can hang on a dead connection without exiting); repeat the kill while still stalled."""
        now = now or time.time()
        segs = segments()
        newest = max((end for _, end, _ in segs), default=0.0)
        if now - newest <= RECORDING_STALL:
            RECORDING_HEALTH_FILE.touch()
            if self.stalled_since is not None:
                down = int(now - self.stalled_since)
                log.warning("recording resumed after %ss", down)
                self.ntfy.status(f"Recording works again (stopped for {down // 60} min {down % 60} s)",
                                 title=f"{CAMERA}: recording resumed", tags="white_check_mark", priority="low")
                if self.ha:
                    self.ha.event("recording_resumed", seconds=down)
                self.stalled_since = None
            return
        if now - self.started < RECORDING_STALL * 2:
            return  # still starting up
        if self.stalled_since is None:
            self.stalled_since = newest or now
            log.error("recording stalled: no video written for %.0fs, restarting ffmpeg", now - newest)
            self.ntfy.status(f"No video has been saved for {RECORDING_STALL} s. Restarting the recorder stream; "
                             "events in this time are not recorded.", title=f"{CAMERA}: recording STALLED")
            if self.ha:
                self.ha.event("recording_stalled", seconds=int(now - self.stalled_since))
        if now - self.last_kill >= RECORDING_STALL * 2:
            self.last_kill = now
            self.segmenter.restart()

    def trim_buffer(self):
        # Parking events start up to PARKING_CONFIRM + PARKING_LEAD seconds in the past
        keep_from = time.time() - PRE_ROLL - SEGMENT_SECONDS * 3 - 10 - PARKING_CONFIRM - PARKING_LEAD
        for ev in (self.current_event(), ):
            if ev is not None:
                keep_from = min(keep_from, ev.start - PRE_ROLL)
        pending = self.finalizer.oldest_needed()
        if pending is not None:
            keep_from = min(keep_from, pending - PRE_ROLL)
        for _, end, path in segments()[:-1]:
            if end < keep_from - 5:
                path.unlink(missing_ok=True)


def annotate(frame, boxes, detections=()):
    img = frame.copy()
    t = max(2, img.shape[1] // 400)
    for x, y, w, h in boxes:
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 255), t)
    for d in detections:
        x, y, w, h = d["box"]
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 200, 0), t)
        cv2.putText(img, f"{d['label']} {d['conf']:.0%}", (x, max(30, y - 10)), cv2.FONT_HERSHEY_SIMPLEX,
                    t * 0.45, (0, 200, 0), t)
    return img


def encode(img, max_width=None):
    if max_width and img.shape[1] > max_width:
        img = cv2.resize(img, (max_width, round(img.shape[0] * max_width / img.shape[1])), interpolation=cv2.INTER_AREA)
    ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return jpg.tobytes() if ok else None


def describe(event):
    if event.test:
        return "test"
    what = ", ".join(event.labels) or "motion"
    return f"{what} at {', '.join(sorted(event.zones))}" if event.zones else what


def notify(ntfy, image, event, title, message, priority=None):
    ntfy.send(message, title=f"{CAMERA}: {title}", tags="camera", priority=priority or ntfy.alert_priority,
              image=image if NOTIFY_SNAPSHOT else None, filename=f"{CAMERA}.jpg",
              click=clip_url(event.day, event.stem), actions=alerts.push_actions(CAMERA, event.day, event.stem))


def load_object_detector():
    if DETECT_MODE != "objects":
        log.info("detection mode: any motion")
        return None
    if not OBJECT_MODEL.exists():
        log.warning("object model %s not found - falling back to motion-only detection", OBJECT_MODEL)
        return None
    from objects import COCO, ObjectDetector
    unknown = [o for o in DETECT_OBJECTS if o not in COCO]
    if unknown:
        log.warning("DETECT_OBJECTS contains unknown classes %s", unknown)
    log.info("detection mode: motion confirmed by YOLO for %s", ", ".join(DETECT_OBJECTS))
    return ObjectDetector(OBJECT_MODEL, DETECT_OBJECTS, OBJECT_CONFIDENCE, part=f"objects {CAMERA}")


def iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / float(aw * ah + bw * bh - inter or 1)


class ParkingMonitor:
    """Is each parking zone occupied? Ignore zones don't apply here: the parking spot usually sits inside
    one so the parked car never raises alerts. Reports a change once it has held for PARKING_CONFIRM s."""

    def __init__(self):
        self.state = {}  # zone name -> {"occupied", "diff_since", "det", "plate"}

    def check(self, zones, detections, fw, fh, now):
        """detections: raw (label, conf, (x, y, w, h)). Returns [(zone, state dict, occupied, since, det)]."""
        changes = []
        for z in zones:
            cars = [d for d in detections if d[0] in VEHICLES and
                    Zones._inside(z, (d[2][0] + d[2][2] / 2) / fw, (d[2][1] + d[2][3]) / fh)]
            occupied, best = bool(cars), max(cars, key=lambda d: d[1], default=None)
            s = self.state.get(z["name"])
            if s is None:  # first look after startup: that's how things are, not a change
                self.state[z["name"]] = {"occupied": occupied, "diff_since": None, "det": best, "plate": None}
                continue
            if occupied == s["occupied"]:
                s["diff_since"] = None
                s["det"] = best or s["det"]
                continue
            s["diff_since"] = s["diff_since"] or now
            if now - s["diff_since"] >= PARKING_CONFIRM:
                changes.append((z, s, occupied, s["diff_since"], best or s["det"]))
                s.update(occupied=occupied, diff_since=None, det=best or s["det"])
        for name in set(self.state) - {z["name"] for z in zones}:
            del self.state[name]
        return changes


class StationaryFilter:
    """Remembers where non-moving objects (a parked car) sit so they stop triggering events.
    People and animals are never filtered."""

    def __init__(self):
        self.tracks = []
        self.seeded = False

    def apply(self, detections, now):
        keep = []
        for d in detections:
            if d["label"] in MOVING_LABELS:
                keep.append(d)
                continue
            track = max((t for t in self.tracks if t["label"] == d["label"] and iou(t["box"], d["box"]) >= 0.6),
                        key=lambda t: iou(t["box"], d["box"]), default=None)
            if track is None:
                # Objects already there at startup count as parked
                track = {"label": d["label"], "first": now - (0 if self.seeded else STATIONARY_SECONDS + 1)}
                self.tracks.append(track)
            track.update(box=d["box"], last=now)
            if now - track["first"] < STATIONARY_SECONDS:
                keep.append(d)
        self.tracks = [t for t in self.tracks if now - t["last"] < 900]
        self.seeded = True
        return keep


def main():
    if not RTSP_URL:
        raise SystemExit("RTSP_URL is not set - edit .env")
    BUF_DIR.mkdir(parents=True, exist_ok=True)
    REC_DIR.mkdir(parents=True, exist_ok=True)
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    (LIVE_DIR / "simulate_motion").unlink(missing_ok=True)
    # The web UI finds the cameras through these files
    (LIVE_DIR / "info.json").write_text(json.dumps({"name": CAMERA, "primary": CAMERA == settings.primary_camera(),
                                                    "started": dt.datetime.now().isoformat(timespec="seconds")}))
    for stale in BUF_DIR.iterdir():
        stale.unlink(missing_ok=True)

    if "zones" not in settings.raw() and MASK_SPEC:
        settings.update(zones=legacy_mask_zones())
        log.info("moved MOTION_MASK from .env into editable ignore zones")
    conf = settings.load()
    conf_mtime = settings.mtime()
    zones = Zones(settings.zones_for(conf, CAMERA))
    camera_key = settings.camera_key(settings.camera_slots(conf)[SLOT - 1]) if SLOT else None
    restart = False  # this camera's settings changed: exit once nothing is being recorded, Docker restarts camslot.py
    armed = settings.is_armed(conf)

    ntfy = Ntfy(log)
    state = {"event": None}
    finalizer = Finalizer()
    reader = FrameReader()
    segmenter = Segmenter()
    housekeeper = Housekeeper(finalizer, lambda: state["event"], segmenter, ntfy)
    if CAMERA == settings.primary_camera():
        timelapse.adopt_old_frames(CAMERA)
    for t in (segmenter, reader, finalizer, housekeeper, timelapse.NightlyBuilder(log)):
        t.start()

    objects = load_object_detector()
    rarity = Rarity(REC_DIR, CAMERA)
    threading.Thread(target=rarity.keep_fresh, daemon=True, name="unusual").start()
    stationary = StationaryFilter()
    parking = ParkingMonitor()
    ha = HomeAssistant(log, "recorder", labels=sorted(objects.wanted) if objects else [],
                       on_armed=lambda on: settings.update(mode="armed" if on else "disarmed"))
    housekeeper.ha = ha
    ha.set_zones([z["name"] for z in zones.trigger])
    ha.state("armed", armed)

    plate_reader = None
    if PLATE_READING and objects and VEHICLES & objects.wanted:
        try:
            from plates import PlateReader
            plate_reader = PlateReader(part=f"plates {CAMERA}")
            log.info("number plate reading enabled")
        except Exception:
            log.exception("number plate reading unavailable")

    # In objects mode motion only decides when YOLO looks, so a low gate costs CPU, not false alerts
    detector = MotionDetector(zones, GATE_AREA if objects else MIN_AREA)
    started = time.time()
    online = None
    hits = 0
    obj_recent = collections.deque(maxlen=OBJECT_WINDOW)  # did each recent YOLO pass find something
    recent_track = collections.deque()  # detections from the last TRACK_LEAD seconds before an event
    last_parking = 0.0
    last_frame_time = last_notify = last_live = last_obj = last_moving = last_conf_check = last_plate = 0.0
    last_alive = 0.0
    quiet_since = time.time()  # when the last event ended (package zones are only judged when it's quiet)
    simulate_until = 0.0
    motion_on = False
    seen = {}  # HA sensor key (label or zone) -> last time seen
    log.info("camwatch %s", app_version()["text"])
    log.info("watching %s (pre-roll %ss, post-roll %ss, %s)", CAMERA, PRE_ROLL, POST_ROLL,
             "armed" if armed else "disarmed")

    def close_event(event, end):
        nonlocal quiet_since, pending
        event.end = end
        finalizer.submit(event)
        state["event"] = None
        quiet_since = end
        if pending is not None and pending.event is event:
            send_alert(pending, pending.decision(time.time(), ended=True))
            pending = None
        if "person" in event.labels and not event.test:
            packages.visit_ended((event.day, event.stem), end)
        log.info("event ended")

    def on_package(kind, zone, picture, visit):
        """A package zone changed: push, HA event, picture next to the clip, entry in the clip's json."""
        day, stem = visit
        folder = REC_DIR / day
        image_name = f"{stem}.package-{kind}.jpg"
        cv2.imwrite(str(folder / image_name), picture, [cv2.IMWRITE_JPEG_QUALITY, 85])
        at = dt.datetime.now().isoformat(timespec="seconds")
        entry = {"kind": kind, "zone": zone["name"], "at": at, "image": image_name}
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with (DATA_DIR / "packages.jsonl").open("a") as f:
            f.write(json.dumps({**entry, "clip": f"{day}/{stem}"}) + "\n")
        links = ha.links(day, stem)
        ha.event(f"package_{kind}", zone=zone["name"], **links)
        what = "Package delivered?" if kind == "delivered" else "Package picked up"
        if not alerts.snoozed_until(conf, CAMERA):
            threading.Thread(target=ntfy.send, daemon=True, kwargs=dict(
                message=f"{what} ({zone['name']}, {dt.datetime.now():%H:%M})", title=f"{CAMERA}: {what.lower()}",
                tags="package", priority=ntfy.alert_priority if kind == "delivered" else "default",
                image=encode(picture, NOTIFY_WIDTH), filename="package.jpg", click=clip_url(day, stem),
                actions=alerts.push_actions(CAMERA, day, stem))).start()

        def add_to_clip():  # the clip's json may still be written by the finalizer
            meta_path = folder / f"{stem}.json"
            for _ in range(60):
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text())
                        meta.setdefault("packages", []).append(entry)
                        tmp = meta_path.with_name(meta_path.name + ".tmp")
                        tmp.write_text(json.dumps(meta, indent=2))
                        os.replace(tmp, meta_path)
                        return
                    except ValueError:
                        pass
                time.sleep(5)
            log.warning("package event not added to %s/%s: no clip json", day, stem)
        threading.Thread(target=add_to_clip, daemon=True).start()

    packages = PackageWatcher(on_package, log)
    household = HouseholdCheck(log)
    pending = None          # person alert held back while faces are checked (household.py)
    last_face_check = 0.0

    def pushes_on():
        """Pushes from this camera: armed and not snoozed (recording and Home Assistant don't depend on it)."""
        return armed and not alerts.snoozed_until(conf, CAMERA)

    def send_alert(alert, kind):
        event = alert.event
        if kind == "loud" and not event.test:
            offsite.queue_alarm(event.day, event.stem)   # off-site right away (also when the push is merged)
        if not event.test:
            linked = alerts.claim(CAMERA, alerts.kind_of(event.labels), kind == "loud", event.day, event.stem)
            if linked:
                event.linked = linked
                if not (event.unusual and kind == "loud"):
                    log.info("same visit as %s (%s) - no push", linked["clip"], linked["camera"])
                    return
        if kind == "loud" and event.unusual:
            threading.Thread(target=notify, daemon=True, args=(
                ntfy, alert.jpg, event, f"unusual: {alert.what}", f"{alert.message} - {event.unusual}", "urgent")).start()
            return
        names = ", ".join(alert.known)
        if kind == "quiet":
            if not pushes_on():     # only got here as "unusual while disarmed" - but it's the household
                log.info("household only (%s) while disarmed: no push", names)
                return
            log.info("household only (%s): quiet alert", names)
            threading.Thread(target=notify, daemon=True, args=(
                ntfy, alert.jpg, alert.event, quiet_title(alert.known),
                f"{names} at {dt.datetime.fromtimestamp(alert.event.start):%H:%M:%S}", alert.priority)).start()
        else:
            threading.Thread(target=notify, daemon=True, args=(ntfy, alert.jpg, alert.event, alert.what, alert.message)).start()
    packages.set_zones(zones.package)

    def add_detections(event, found):
        """Record labels/zones on the event; fire an HA event for each newly seen object type,
        and again when that object type shows up in a zone it was not seen in before."""
        for d in found:
            event.zones.update(d["zones"])
            seen_in = event.label_zones.setdefault(d["label"], set())
            new_zone = not set(d["zones"]) <= seen_in
            seen_in.update(d["zones"])
            if d["label"] not in event.labels or new_zone:
                ha.event(d["label"], confidence=round(d["conf"], 2), zones=d["zones"], armed=armed,
                         **ha.links(event.day, event.stem))
            event.labels[d["label"]] = max(d["conf"], event.labels.get(d["label"], 0.0))

    def announce_plate(event, plate):
        e = event.plates.reads[plate]
        k = match_known(plate, conf.get("plates", []))
        name = k.get("name") if k else None
        label = f"{plate} ({name})" if name else plate
        log.info("plate %s -> %s", label, "known" if k else "unknown")
        payload = ha.event("plate", plate=plate, name=name, known=bool(k), confidence=round(e["conf"], 2),
                           armed=armed, **ha.links(event.day, event.stem))
        ha.retained("last_plate", payload)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with (DATA_DIR / "plates.jsonl").open("a") as f:
            f.write(json.dumps({"at": dt.datetime.now().isoformat(timespec="seconds"), "plate": plate,
                                "name": name, "clip": f"{event.day}/{event.stem}"}) + "\n")
        if pushes_on() and (PLATE_NOTIFY == "all" or (PLATE_NOTIFY == "unknown" and not k)):
            threading.Thread(target=notify, daemon=True, args=(
                ntfy, encode(e["crop"]), event, f"plate {label}",
                f"{'Known' if k else 'Unknown'} vehicle: {label}", "low" if k else None)).start()

    def vehicle_change(event, frame, zone, pstate, occupied, since, det):
        """A car arrived at / left a parking zone: log it on the running event, or start one for it."""
        label, score, box = det if det else ("car", 0.0, None)
        plate = name = None
        if occupied:
            pstate["plate"] = None
            if plate_reader and box:
                x, y, w, h = box
                reads = [r for r in plate_reader.read(frame)
                         if x <= r["box"][0] + r["box"][2] / 2 <= x + w and y <= r["box"][1] + r["box"][3] / 2 <= y + h]
                if reads:
                    pstate["plate"] = max(reads, key=lambda r: r["conf"])["plate"]
            plate = pstate["plate"]
        else:
            plate, pstate["plate"] = pstate["plate"], None  # the plate read when this car arrived
        if plate:
            known = match_known(plate, conf.get("plates", []))
            name = known.get("name") if known else None
        direction = "arrived" if occupied else "left"
        move = {"direction": direction, "zone": zone["name"], "label": label, "conf": round(score, 2),
                "at": dt.datetime.fromtimestamp(since).isoformat(timespec="seconds"), "plate": plate, "name": name}
        if event is None:
            event = Event(start=since - PARKING_LEAD, taken=finalizer.taken())
            event.last_motion = frame_time
            event.track = list(recent_track)
            if plate_reader:
                event.plates = PlateTally()
                event.known_plates = conf.get("plates", [])
            state["event"] = event
            cv2.imwrite(str(event.dir / f"{event.stem}.jpg"), frame)
        event.vehicles.append(move)
        event.labels[label] = max(score, event.labels.get(label, 0.0))
        who = f"{name} ({plate})" if name else plate or label
        log.info("%s %s at %s -> %s/%s", who, direction, zone["name"], event.day, event.stem)
        links = ha.links(event.day, event.stem)
        ha.event(f"vehicle_{direction}", zone=zone["name"], plate=plate, name=name, label=label, armed=armed, **links)
        if pushes_on():
            threading.Thread(target=notify, daemon=True, args=(
                ntfy, encode(frame, NOTIFY_WIDTH), event, f"{who} {direction}",
                f"{who[0].upper() + who[1:]} {direction} ({zone['name']}) at {dt.datetime.fromtimestamp(since):%H:%M:%S}",
                "low" if name else None)).start()
        return event

    while True:
        frame, frame_time = reader.latest()
        now = time.time()
        event = state["event"]

        # Settings from the web UI / Home Assistant (arming, zones, loitering)
        if now - last_conf_check > 2:
            last_conf_check = now
            if settings.mtime() != conf_mtime:
                conf_mtime = settings.mtime()
                old_zones = settings.zones_for(conf, CAMERA)
                conf = settings.load()
                if settings.zones_for(conf, CAMERA) != old_zones:
                    zones = Zones(settings.zones_for(conf, CAMERA))
                    detector.set_zones(zones)
                    ha.set_zones([z["name"] for z in zones.trigger])
                    packages.set_zones(zones.package)
                    log.info("zones updated: %d ignore, %d trigger", len(zones.ignore), len(zones.trigger))
                if camera_key and settings.camera_key(settings.camera_slots(conf)[SLOT - 1]) != camera_key and not restart:
                    restart = True
                    log.info("camera settings changed - restarting when the current recording is saved")
            if restart and state["event"] is None and not finalizer.taken():
                log.info("restarting for the new camera settings")
                os._exit(0)
            if settings.is_armed(conf) != armed:
                armed = not armed
                ha.state("armed", armed)
                log.info("%s", "armed" if armed else "disarmed - recording continues, no push alerts")

        # Camera online/offline watchdog (alerts even when disarmed)
        is_online = frame is not None and now - frame_time < OFFLINE_AFTER
        if is_online != online and (is_online or frame is not None or now - started > OFFLINE_AFTER):
            ha.state("online", is_online)
            if online is not None or not is_online:
                text = "back online" if is_online else f"offline - no picture for {OFFLINE_AFTER}s"
                log.warning("camera %s", text)
                ntfy.status(f"Camera {text}", title=f"{CAMERA}: {'online' if is_online else 'OFFLINE'}",
                            tags="white_check_mark" if is_online else "warning",
                            priority="default" if not is_online else "low")
                ha.event("camera_online" if is_online else "camera_offline")
            online = is_online

        if frame is None or frame_time == last_frame_time:
            if event is not None and now - frame_time > POST_ROLL:
                close_event(event, now)  # detection stream died mid-event
            time.sleep(0.05)
            continue
        last_frame_time = frame_time
        HEALTH_FILE.touch()
        if now - last_alive >= 10:
            last_alive = now
            (LIVE_DIR / "alive").touch()   # dashboard: camera online
        fh, fw = frame.shape[:2]
        if event is not None:
            quiet_since = frame_time
        packages.tick(frame, frame_time, quiet_since)
        timelapse.capture(frame, frame_time)

        if now - last_live >= LIVE_INTERVAL and someone_watching():
            last_live = now
            publish_live_frame(frame)

        if take_simulate_request():
            log.info("simulated detection requested from the web UI")
            simulate_until = frame_time + 6
        simulated = frame_time < simulate_until

        # 1. Pixel motion (every frame)
        ratio, boxes = detector.update(frame)
        if zones.trigger:
            boxes = [b for b in boxes if zones.hits((b[0] + b[2] / 2) / fw, (b[1] + b[3] / 2) / fh)]
        moving = bool(boxes)
        # The HA motion sensor keeps the MOTION_MIN_AREA sensitivity, independent of the YOLO gate
        big_motion = moving and ratio >= MIN_AREA
        if big_motion:
            last_moving = frame_time
        if (big_motion and not motion_on) or (motion_on and not big_motion and frame_time - last_moving > 5):
            motion_on = big_motion
            ha.state("motion", motion_on)

        # 2. Object confirmation: while something moves or an event runs, plus once a minute
        #    so parked vehicles stay known to the stationary filter
        found = []
        raw = None  # this pass's detections before zone filtering (the parking check reuses them)
        busy = moving or event is not None or any(obj_recent)
        if objects and ((busy and now - last_obj >= OBJECT_INTERVAL) or now - last_obj >= 60):
            last_obj = now
            raw = objects.detect(frame)
            for label, score, (x, y, w, h) in raw:
                if w * h < OBJECT_MIN_AREA * fw * fh or zones.ignored((x + w / 2) / fw, (y + h / 2) / fh):
                    continue
                hit = zones.hits((x + w / 2) / fw, (y + h) / fh)  # feet / wheels
                if hit is not None and not hit:
                    continue
                found.append({"label": label, "conf": score, "box": (x, y, w, h), "zones": hit or []})
            found = stationary.apply(found, frame_time)
            obj_recent.append(bool(found))
            points = [(frame_time, d["label"], (d["box"][0] + d["box"][2] / 2) / fw, min(d["box"][1] + d["box"][3], fh) / fh,
                       d["box"][2] / fw, d["box"][3] / fh, round(d["conf"], 2)) for d in found]
            if event is not None:
                event.track.extend(points)
            else:
                # Keep the passes just before an event starts: they show where someone came from
                recent_track.extend(points)
                while recent_track and recent_track[0][0] < frame_time - TRACK_LEAD:
                    recent_track.popleft()
            for d in found:
                for key in [d["label"]] + [zone_key(z) for z in d["zones"]]:
                    if key not in seen:
                        ha.state(key, True)
                    seen[key] = frame_time
        for key, t in list(seen.items()):
            if frame_time - t > POST_ROLL:
                ha.state(key, False)
                del seen[key]

        if objects:
            triggered, active = sum(obj_recent) >= OBJECT_MIN_HITS, bool(found)
        else:
            hits = hits + 1 if moving else 0
            triggered, active = hits >= MIN_FRAMES, moving
        if simulated:
            triggered = active = True

        # 2b. Parking zones: car arrived / left (also while nothing else moves, every PARKING_CHECK s)
        if objects and zones.parking and now - last_parking >= PARKING_CHECK:
            last_parking = now
            for z, pstate, occupied, since, det in parking.check(zones.parking, raw if raw is not None else objects.detect(frame),
                                                                fw, fh, frame_time):
                event = vehicle_change(event, frame, z, pstate, occupied, since, det)

        # 3. Event lifecycle
        if event is None:
            if triggered:
                lead = len(obj_recent) * OBJECT_INTERVAL if objects else hits / DETECT_FPS
                event = Event(start=frame_time - lead, taken=finalizer.taken())
                event.peak = ratio
                event.test = simulated
                event.presence_start = event.last_presence = frame_time if found else None
                event.track = list(recent_track)
                recent_track.clear()
                if plate_reader:
                    event.plates = PlateTally()
                    event.known_plates = conf.get("plates", [])
                state["event"] = event
                cv2.imwrite(str(event.dir / f"{event.stem}.jpg"), frame)
                jpg = encode(annotate(frame, [] if objects else boxes, found), NOTIFY_WIDTH)

                links = ha.links(event.day, event.stem)
                if simulated:
                    ha.event("test", armed=armed, **links)
                elif not objects:
                    ha.event("motion", armed=armed, **links)
                add_detections(event, found)
                what = describe(event)
                log.info("%s detected -> %s/%s%s", what, event.day, event.stem, "" if armed else " (disarmed)")
                unusual_mode = conf.get("unusual_alerts", "armed")     # off | armed | always
                if not simulated and unusual_mode != "off":
                    event.unusual = rarity.check(event.labels, event.zones, dt.datetime.fromtimestamp(event.start))
                    if event.unusual:
                        log.info("unusual: %s", event.unusual)
                        ha.event("unusual", reason=event.unusual, labels=list(event.labels), armed=armed, **links)
                may_push = pushes_on() or (event.unusual and unusual_mode == "always"
                                           and not alerts.snoozed_until(conf, CAMERA))
                if jpg:
                    ha.snapshot(jpg)
                ha.retained("last_event", {"time": dt.datetime.fromtimestamp(event.start).astimezone()
                                           .isoformat(timespec="seconds"), "what": what, **links})
                if simulated or (may_push and now - last_notify >= NOTIFY_COOLDOWN):
                    last_notify = now
                    message = f"{what.capitalize()} at {dt.datetime.fromtimestamp(event.start):%H:%M:%S}"
                    alert = PendingAlert(event, jpg, what, message, now)
                    if not simulated and people_boxes(found) and household.enabled:
                        alert.add(household.faces(frame, people_boxes(found)))   # look right away
                        last_face_check = now
                        pending = alert if alert.decision(now) is None else None
                        if pending is None:
                            send_alert(alert, alert.decision(now))
                    else:
                        send_alert(alert, "loud")
        else:
            add_detections(event, found)
            if active:
                event.last_motion = frame_time
                event.peak = max(event.peak, ratio)
            if pending is not None and pending.event is event:
                if people_boxes(found) and now - last_face_check >= OBJECT_INTERVAL:
                    last_face_check = now
                    pending.add(household.faces(frame, people_boxes(found)))
                kind = pending.decision(now)
                if kind:
                    send_alert(pending, kind)
                    pending = None

            # Loitering: something continuously in view (gaps under 3 s allowed)
            loiter = int(conf.get("loiter_seconds") or 0)
            if found:
                if event.last_presence is None or frame_time - event.last_presence > 3:
                    event.presence_start = frame_time
                event.last_presence = frame_time
                if loiter and not event.loiter_sent and frame_time - event.presence_start >= loiter:
                    event.loiter_sent = True
                    what = describe(event)
                    log.info("loitering: %s for %ss", what, loiter)
                    ha.event("loitering", seconds=loiter, labels=list(event.labels), zones=sorted(event.zones),
                             armed=armed, **ha.links(event.day, event.stem))
                    if pushes_on():
                        threading.Thread(target=notify, daemon=True, args=(
                            ntfy, encode(annotate(frame, [], found), NOTIFY_WIDTH), event, f"{what} loitering",
                            f"{what.capitalize()} has been in view for {loiter}s", "urgent")).start()

            # Number plates: only plates inside a moving vehicle's box (ignores the parked car)
            vehicles = [d["box"] for d in found if d["label"] in VEHICLES]
            if plate_reader and vehicles and now - last_plate >= PLATE_INTERVAL:
                last_plate = now
                reads = [r for r in plate_reader.read(frame)
                         if any(vx <= r["box"][0] + r["box"][2] / 2 <= vx + vw and vy <= r["box"][1] + r["box"][3] / 2 <= vy + vh
                                for vx, vy, vw, vh in vehicles)]
                event.plates.add(frame, reads)
                for plate in event.plates.newly_confirmed():
                    announce_plate(event, plate)

            if frame_time - event.last_motion >= POST_ROLL or frame_time - event.start >= MAX_EVENT:
                close_event(event, frame_time)
                hits = 0
                obj_recent.clear()


if __name__ == "__main__":
    main()
