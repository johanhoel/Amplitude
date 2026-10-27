"""Shareable copies of recordings: faces (everyone, or only people not in the photo library) and number plates
pixelated, audio removed (voices), scaled to 1280 px wide. Used by the web UI's "Share a blurred copy" button.

Faces in a wide camera view are often too small (or turned away) for a face detector, so blurring is based on people:
the object model finds every person in the full-resolution frame and the head area (top third of the person box) is
pixelated. In "strangers" mode the face detector looks inside that head area (sharp there) and leaves the head visible
only when it finds a face that clearly matches the library (FACE_MATCH_THRESHOLD + SHARE_KNOWN_MARGIN); no face found
or not clearly known = blurred. Plates are found on the full-resolution frame. Detection runs on every other frame and
each box stays until it has been missed for two passes, so nothing flashes through between detections. Pixelation
(big blocks) rather than a soft blur, because a soft blur can sometimes be partly reversed.
"""
import queue
import subprocess
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from common import env

DATA_DIR = Path(env("DATA_DIR", "/data"))
OUT_DIR = DATA_DIR / "shares"
WIDTH = env("SHARE_WIDTH", 1280, int)
KEEP_DAYS = env("SHARE_KEEP_DAYS", 7, int)
MARGIN = env("SHARE_KNOWN_MARGIN", 0.05, float)
THRESHOLD = env("FACE_MATCH_THRESHOLD", 0.40, float)
PLATE_MODEL = "yolo-v9-t-640-license-plate-end2end"
OBJECT_MODEL = env("OBJECT_MODEL", "/models/yolov8s-coco.onnx")
HEAD = 0.36   # top part of a person box treated as the head area

jobs = {}           # id -> {"state": queued|running|done|error, "progress": 0..1, "file", "error", "day", "stem"}
_queue = queue.Queue()
_worker = None
_models = {}


def _load():
    """Face engine, library embeddings and plate detector, loaded once on first use."""
    if not _models:
        from facematch import FaceEngine
        from household import KnownFaces
        import open_image_models as oim
        _models["faces"] = FaceEngine()
        _models["known"] = KnownFaces()
        _models["plates"] = oim.create_detector(PLATE_MODEL)
        from objects import ObjectDetector
        _models["people"] = ObjectDetector(OBJECT_MODEL, ["person"], 0.3)
    _models["known"].refresh()
    return _models


def pixelate(img, box, grow):
    """Replace a box (x, y, w, h) with big blocks, in place; the box is enlarged by `grow` of its size."""
    h, w = img.shape[:2]
    x, y, bw, bh = box
    gx, gy = int(bw * grow), int(bh * grow)
    x0, y0, x1, y1 = max(0, x - gx), max(0, y - gy), min(w, x + bw + gx), min(h, y + bh + gy)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return
    region = img[y0:y1, x0:x1]
    blocks = max(2, min(x1 - x0, y1 - y0) // 10)
    small = cv2.resize(region, (max(1, (x1 - x0) // blocks), max(1, (y1 - y0) // blocks)), interpolation=cv2.INTER_AREA)
    img[y0:y1, x0:x1] = cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)


def known_face_in(crop, m):
    """True if the crop holds a face that clearly matches someone in the library."""
    if crop.size == 0 or min(crop.shape[:2]) < 16:
        return False
    for f in m["faces"].faces(crop, min_size=8, max_width=max(64, crop.shape[1])):
        name, score = m["known"].match(f.emb)
        if name and score >= THRESHOLD + MARGIN:
            return True
    return False


def boxes_in(frame, faces_mode, plates, m):
    """Boxes (x, y, w, h) to blur in one full-resolution frame."""
    out = []
    h, w = frame.shape[:2]
    if faces_mode != "none":
        for _, _, (x, y, bw, bh) in m["people"].detect(frame):
            hx0, hy0 = max(0, x), max(0, y - int(bh * 0.04))
            hx1, hy1 = min(w, x + bw), min(h, y + int(bh * HEAD))
            if faces_mode == "strangers" and known_face_in(frame[hy0:hy1, hx0:hx1], m):
                continue
            out.append(("head", (hx0, hy0, hx1 - hx0, hy1 - hy0)))
    if plates:
        for r in m["plates"].predict(frame):
            b = r.bounding_box
            out.append(("plate", (int(b.x1), int(b.y1), int(b.x2 - b.x1), int(b.y2 - b.y1))))
    return out


def render(src, dst, faces_mode="strangers", plates=True, progress=lambda f: None):
    m = _load()
    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        raise RuntimeError("cannot open the recording")
    fps = cap.get(cv2.CAP_PROP_FPS) or 15
    if not 1 <= fps <= 60:
        fps = 15
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    ow = min(WIDTH, w) // 2 * 2
    oh = round(h * ow / w) // 2 * 2
    tmp = dst.with_name(dst.name + ".part")
    enc = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
                            "-s", f"{ow}x{oh}", "-r", f"{fps:.3f}", "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast",
                            "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-f", "mp4", str(tmp)],
                           stdin=subprocess.PIPE)
    recent = []  # boxes from the last two detection passes
    i = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if i % 2 == 0:   # detect on the full-resolution frame, blur on the scaled one
                scale = ow / frame.shape[1]
                found = [(k, tuple(int(v * scale) for v in b)) for k, b in boxes_in(frame, faces_mode, plates, m)]
                recent = (recent + [found])[-2:]
            frame = cv2.resize(frame, (ow, oh), interpolation=cv2.INTER_AREA)
            for found in recent:
                for kind, box in found:
                    pixelate(frame, box, 0.15)
            enc.stdin.write(frame.tobytes())
            i += 1
            if i % 10 == 0:
                progress(min(0.99, i / total))
    finally:
        cap.release()
        enc.stdin.close()
        rc = enc.wait()
    if rc != 0 or i == 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("encoding failed")
    tmp.replace(dst)
    return i


def _run():
    while True:
        job_id = _queue.get()
        job = jobs[job_id]
        job["state"] = "running"
        try:
            cutoff = time.time() - KEEP_DAYS * 86400
            for old in OUT_DIR.glob("*.mp4"):
                if old.stat().st_mtime < cutoff:
                    old.unlink(missing_ok=True)
            out = OUT_DIR / job["file"]
            render(job["src"], out, job["faces"], job["plates"], progress=lambda f: job.update(progress=f))
            job.update(state="done", progress=1.0)
        except Exception as e:  # shown to the user on the clip page
            job.update(state="error", error=str(e)[:200])


def submit(src, day, stem, faces_mode, plates):
    """Queue a blurred copy; returns the job id. One job runs at a time (it uses a lot of CPU)."""
    global _worker
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    job_id = f"{stem}-{faces_mode}{'-plates' if plates else ''}-{int(time.time())}"
    jobs[job_id] = {"state": "queued", "progress": 0.0, "file": f"{job_id}.mp4", "error": None, "day": day, "stem": stem,
                    "src": src, "faces": faces_mode, "plates": plates}
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_run, daemon=True, name="share")
        _worker.start()
    _queue.put(job_id)
    return job_id
