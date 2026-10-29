"""Offline face identification for finished recordings.

Scans /recordings for videos without a .faces.json sidecar, samples frames, detects faces
(YuNet) and compares them (SFace embeddings) with the reference library in /photos:

    /photos/Alice/1.jpg
    /photos/Alice/holiday.png
    /photos/Bob/passport.jpg

Results: <video>.faces.json, face crops in <video>_faces/, a line per sighting in
/data/sightings.jsonl, and an optional ntfy push.
"""
import argparse
import datetime as dt
import json
import os
import shutil
import time
from pathlib import Path

import cv2
import numpy as np

from common import VIDEO_EXT, Ntfy, clip_url, env, env_bool, setup_logging
import settings
from homeassistant import HomeAssistant
import search
import strangers

log = setup_logging("facematch")

REC_DIR = Path(env("RECORDINGS_DIR", "/recordings"))
PHOTOS_DIR = Path(env("PHOTOS_DIR", "/photos"))
DATA_DIR = Path(env("DATA_DIR", "/data"))
MODELS_DIR = Path(env("MODELS_DIR", "/models"))

SAMPLE_FPS = env("FACE_SAMPLE_FPS", 2.0, float)
MAX_WIDTH = env("FACE_MAX_WIDTH", 1920, int)
DET_SCORE = env("FACE_DETECT_SCORE", 0.85, float)
MIN_FACE_PX = env("FACE_MIN_SIZE", 40, int)
THRESHOLD = env("FACE_MATCH_THRESHOLD", 0.40, float)   # SFace cosine; OpenCV suggests 0.363
MIN_HITS = env("FACE_MIN_HITS", 1, int)
UNKNOWN_MERGE = 0.45
MAX_UNKNOWN = 10
SCAN_INTERVAL = env("FACE_SCAN_INTERVAL", 60, int)
SETTLE_SECONDS = env("FACE_SETTLE_SECONDS", 30, int)
ACTIVE_HOURS = env("FACE_ACTIVE_HOURS", "")
NOTIFY_KNOWN = env_bool("FACE_NOTIFY_KNOWN", True)
NOTIFY_UNKNOWN = env_bool("FACE_NOTIFY_UNKNOWN", False)
# Re-check clips with faces when reference photos change (after this many quiet seconds)
RECHECK = env_bool("FACE_RECHECK_ON_LIBRARY_CHANGE", True)
RECHECK_DELAY = env("FACE_RECHECK_DELAY", 60, int)
# Index new clips for text search (CLIP); off = no search model loaded
SEARCH = env_bool("SEARCH_ENABLED", True)

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


class Face:
    def __init__(self, emb, crop, area, box=None):
        self.emb = emb
        self.crop = crop
        self.area = area
        self.box = box  # (x, y, w, h) in the coordinates of the image passed to FaceEngine.faces()


class FaceEngine:
    def __init__(self, part=None):
        self.part = part
        self._open()

    def _open(self):
        """The face models on the GPU through OpenCL when Settings -> Image processing allows it, else the CPU."""
        import accel
        self.providers = accel.providers()
        gpu = accel.opencl()
        target = cv2.dnn.DNN_TARGET_OPENCL if gpu else cv2.dnn.DNN_TARGET_CPU
        self.detector = cv2.FaceDetectorYN.create(
            str(MODELS_DIR / "face_detection_yunet_2023mar.onnx"), "", (320, 320), DET_SCORE, 0.3, 5000,
            cv2.dnn.DNN_BACKEND_OPENCV, target)
        self.recognizer = cv2.FaceRecognizerSF.create(
            str(MODELS_DIR / "face_recognition_sface_2021dec.onnx"), "", cv2.dnn.DNN_BACKEND_OPENCV, target)
        if self.part:
            accel.report(self.part, "OpenCL" if gpu else accel.CPU)

    def faces(self, img, min_size=MIN_FACE_PX, max_width=MAX_WIDTH):
        import accel
        if accel.providers() != self.providers:      # Settings -> Image processing changed
            self._open()
        h, w = img.shape[:2]
        scale = 1.0
        if w > max_width:
            scale = w / max_width
            img = cv2.resize(img, (max_width, int(h * max_width / w)))
            h, w = img.shape[:2]
        self.detector.setInputSize((w, h))
        _, dets = self.detector.detect(img)
        out = []
        if dets is None:
            return out
        for d in dets:
            x, y, fw, fh = (int(v) for v in d[:4])
            if min(fw, fh) < min_size:
                continue
            emb = self.recognizer.feature(self.recognizer.alignCrop(img, d)).flatten().astype(np.float32)
            emb /= np.linalg.norm(emb) + 1e-9
            pad = int(max(fw, fh) * 0.4)
            crop = img[max(0, y - pad):min(h, y + fh + pad), max(0, x - pad):min(w, x + fw + pad)].copy()
            out.append(Face(emb, crop, fw * fh, tuple(int(v * scale) for v in (x, y, fw, fh))))
        return out


class Library:
    """Reference embeddings from /photos/<Person>/*, cached by file mtime+size."""

    def __init__(self, engine):
        self.engine = engine
        self.cache_file = DATA_DIR / "library_cache.json"
        self.signature = None
        self.names = []
        self.embs = np.zeros((0, 128), dtype=np.float32)

    def _files(self):
        files = []
        if not PHOTOS_DIR.is_dir():
            return files
        for person in sorted(p for p in PHOTOS_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")):
            for img in sorted(person.rglob("*")):
                if img.suffix.lower() in IMG_EXT and img.is_file():
                    st = img.stat()
                    files.append((person.name, img, st.st_mtime, st.st_size))
        return files

    def refresh(self):
        """Reload changed reference photos. Returns True if the library changed (not on first load)."""
        files = self._files()
        signature = [(str(p), m, s) for _, p, m, s in files]
        if signature == self.signature:
            return False
        first = self.signature is None
        try:
            cache = json.loads(self.cache_file.read_text())
        except (FileNotFoundError, ValueError):
            cache = {}

        names, embs, new_cache = [], [], {}
        for person, path, mtime, size in files:
            key = str(path)
            entry = cache.get(key)
            if not entry or entry["mtime"] != mtime or entry["size"] != size:
                img = cv2.imread(key)
                faces = []
                # Portraits have huge faces, which YuNet detects best on a small image; try small first
                for width in (640, 1280, 1920):
                    faces = self.engine.faces(img, min_size=20, max_width=width) if img is not None else []
                    if faces:
                        break
                if not faces:
                    log.warning("no face found in reference photo %s", path.relative_to(PHOTOS_DIR))
                elif len(faces) > 1:
                    log.info("%d faces in %s - using the largest", len(faces), path.relative_to(PHOTOS_DIR))
                best = max(faces, key=lambda f: f.area) if faces else None
                entry = {"mtime": mtime, "size": size,
                         "emb": best.emb.tolist() if best is not None else None}
            new_cache[key] = entry
            if entry["emb"] is not None:
                names.append(person)
                embs.append(np.array(entry["emb"], dtype=np.float32))

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(json.dumps(new_cache))
        self.names = names
        self.embs = np.stack(embs) if embs else np.zeros((0, 128), dtype=np.float32)
        self.signature = signature
        log.info("reference library: %d photos of %d people", len(names), len(set(names)))
        return not first

    def match(self, emb):
        if not len(self.names):
            return None, 0.0
        sims = self.embs @ emb
        i = int(np.argmax(sims))
        return self.names[i], float(sims[i])


def sidecar(video):
    return video.with_name(video.name[: -len(video.suffix)] + ".faces.json")


def process_video(video, engine, library):
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError("cannot open video")
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps != fps or fps > 120:
        fps = 15.0
    step = max(1, round(fps / SAMPLE_FPS))

    known, unknown = {}, []
    idx = sampled = faces_seen = 0
    while cap.grab():
        if idx % step == 0:
            ok, frame = cap.retrieve()
            if ok:
                sampled += 1
                t = round(idx / fps, 1)
                for face in engine.faces(frame):
                    faces_seen += 1
                    name, score = library.match(face.emb)
                    if name and score >= THRESHOLD:
                        k = known.setdefault(name, {"score": 0.0, "count": 0, "first_seen_s": t, "crop": None})
                        k["count"] += 1
                        if score > k["score"]:
                            k["score"], k["crop"] = score, face.crop
                        continue
                    # Group unknown faces so one stranger walking past gives one entry, not twenty.
                    for u in unknown:
                        if float(u["emb"] @ face.emb) >= UNKNOWN_MERGE:
                            u["count"] += 1
                            if face.area > u["area"]:
                                u.update(area=face.area, crop=face.crop)
                            if score > u["best_guess_score"]:
                                u.update(best_guess=name, best_guess_score=score)
                            break
                    else:
                        if len(unknown) < MAX_UNKNOWN:
                            unknown.append({"emb": face.emb, "count": 1, "area": face.area, "crop": face.crop,
                                            "first_seen_s": t, "best_guess": name, "best_guess_score": score})
        idx += 1
    cap.release()

    known = {n: k for n, k in known.items() if k["count"] >= MIN_HITS}
    stem = video.name[: -len(video.suffix)]
    crops_dir = video.parent / f"{stem}_faces"
    shutil.rmtree(crops_dir, ignore_errors=True)  # drop crops from an earlier analysis

    def save_crop(img, name):
        crops_dir.mkdir(exist_ok=True)
        cv2.imwrite(str(crops_dir / name), img)
        return f"{crops_dir.name}/{name}"

    result = {
        "video": video.name,
        "processed_at": dt.datetime.now().isoformat(timespec="seconds"),
        "duration_s": round(idx / fps, 1),
        "frames_sampled": sampled,
        "faces_seen": faces_seen,
        "known": [
            {"name": n, "score": round(k["score"], 3), "count": k["count"], "first_seen_s": k["first_seen_s"],
             "crop": save_crop(k["crop"], f"known_{n}.jpg")}
            for n, k in sorted(known.items(), key=lambda kv: -kv[1]["score"])
        ],
        "unknown": [
            {"count": u["count"], "first_seen_s": u["first_seen_s"], "best_guess": u["best_guess"],
             "best_guess_score": round(u["best_guess_score"], 3),
             "crop": save_crop(u["crop"], f"unknown_{i + 1}.jpg")}
            for i, u in enumerate(unknown)
        ],
    }
    sidecar(video).write_text(json.dumps(result, indent=2))
    return result, known, unknown


def report(video, result, known, unknown, ntfy, ha):
    day, stem = video.parent.name, video.name[: -len(video.suffix)]
    web = ha.links(day, stem)
    media = settings.web_base_url() + f"/media/{day}/"
    for k in result["known"]:
        payload = ha.event("identified", name=k["name"], score=k["score"],
                           face_url=media + k["crop"] if web else None, **web)
        ha.retained("last_identified", payload)
    if result["unknown"]:
        ha.event("unknown_face", count=len(result["unknown"]),
                 face_url=media + result["unknown"][0]["crop"] if web else None, **web)

    with (DATA_DIR / "sightings.jsonl").open("a") as f:
        for k in result["known"]:
            f.write(json.dumps({"video": str(video.relative_to(REC_DIR)), "name": k["name"],
                                "score": k["score"], "at": dt.datetime.fromtimestamp(video.stat().st_mtime)
                                .isoformat(timespec="seconds")}) + "\n")

    rel = video.relative_to(REC_DIR)
    click = clip_url(video.parent.name, video.name[: -len(video.suffix)])
    if known and NOTIFY_KNOWN:
        names = ", ".join(f"{k['name']} ({k['score']:.2f})" for k in result["known"])
        top = result["known"][0]["name"]
        ok, jpg = cv2.imencode(".jpg", known[top]["crop"])
        ntfy.send(f"{names}\n{rel}", title=f"Identified: {', '.join(k['name'] for k in result['known'])}",
                  tags="bust_in_silhouette", image=jpg.tobytes() if ok else None, filename="face.jpg",
                  click=click)
    elif unknown and NOTIFY_UNKNOWN:
        ok, jpg = cv2.imencode(".jpg", max(unknown, key=lambda u: u["area"])["crop"])
        ntfy.send(f"{len(unknown)} unrecognised face(s)\n{rel}", title="Unknown person",
                  tags="question", image=jpg.tobytes() if ok else None, filename="face.jpg", click=click)


def pending_videos(force=False):
    now = time.time()
    vids = []
    for p in REC_DIR.rglob("*"):
        if p.suffix.lower() in VIDEO_EXT and p.is_file() and (force or not sidecar(p).exists()):
            mtime = p.stat().st_mtime
            if now - mtime >= SETTLE_SECONDS:
                vids.append((mtime, p))
    return [p for _, p in sorted(vids)]


def in_active_hours():
    """FACE_ACTIVE_HOURS="1-6" only processes between 01:00 and 06:59 (wraps midnight, e.g. "22-6")."""
    if not ACTIVE_HOURS:
        return True
    start, end = (int(v) for v in ACTIVE_HOURS.split("-"))
    hour = dt.datetime.now().hour
    return start <= hour <= end if start <= end else hour >= start or hour <= end


def run_once(engine, library, ntfy, ha, force=False, only=None):
    library.refresh()
    videos = [Path(only)] if only else pending_videos(force)
    for video in videos:
        if not only and not in_active_hours():
            break
        started = time.time()
        try:
            result, known, unknown = process_video(video, engine, library)
        except Exception as exc:
            log.exception("failed on %s", video)
            sidecar(video).write_text(json.dumps({"video": video.name, "error": str(exc)}))
            continue
        log.info("%s: %d faces, known=%s, unknown=%d (%.0fs)", video.relative_to(REC_DIR), result["faces_seen"],
                 [k["name"] for k in result["known"]] or "-", len(result["unknown"]), time.time() - started)
        report(video, result, known, unknown, ntfy, ha)


def recheck(engine, library):
    """Re-match clips that contain faces after the reference library changed. Quiet: no
    notifications or HA events, and sightings are only logged for newly found people."""
    clips = []
    for video in pending_videos(force=True):
        try:
            old = json.loads(sidecar(video).read_text())
        except (FileNotFoundError, ValueError):
            continue
        if old.get("faces_seen"):
            clips.append((video, {k["name"] for k in old.get("known", [])}))
    log.info("reference photos changed: re-checking %d clips with faces", len(clips))
    for video, before in clips:
        if not in_active_hours():
            break
        try:
            result, _, _ = process_video(video, engine, library)
        except Exception:
            log.exception("re-check failed on %s", video)
            continue
        new = [k for k in result["known"] if k["name"] not in before]
        if new:
            log.info("%s: now also identified %s", video.relative_to(REC_DIR), [k["name"] for k in new])
            with (DATA_DIR / "sightings.jsonl").open("a") as f:
                for k in new:
                    f.write(json.dumps({"video": str(video.relative_to(REC_DIR)), "name": k["name"],
                                        "score": k["score"], "recheck": True,
                                        "at": dt.datetime.fromtimestamp(video.stat().st_mtime)
                                        .isoformat(timespec="seconds")}) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--once", action="store_true", help="process pending videos and exit")
    parser.add_argument("--force", action="store_true", help="re-process videos that already have results")
    parser.add_argument("--file", help="process a single video and exit")
    args = parser.parse_args()

    try:
        os.nice(10)  # never starve the recorder
    except OSError:
        pass
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    engine = FaceEngine(part="faces")
    library = Library(engine)
    ntfy = Ntfy(log)
    ha = HomeAssistant(log, "facematch")

    if args.once or args.file:
        run_once(engine, library, ntfy, ha, force=args.force, only=args.file)
        return
    log.info("face matcher running (threshold %.2f, every %ss%s)", THRESHOLD, SCAN_INTERVAL,
             f", hours {ACTIVE_HOURS}" if ACTIVE_HOURS else "")
    recheck_due = None
    last_strangers = 0.0
    while True:
        if in_active_hours():
            if library.refresh() and RECHECK:
                recheck_due = time.time() + RECHECK_DELAY  # wait for more uploads to finish
            run_once(engine, library, ntfy, ha, force=args.force)
            args.force = False
            if recheck_due and time.time() >= recheck_due:
                recheck_due = None
                recheck(engine, library)
                last_strangers = 0.0  # names may have changed: regroup now
            if time.time() - last_strangers >= strangers.EVERY or (DATA_DIR / "strangers.refresh").exists():
                (DATA_DIR / "strangers.refresh").unlink(missing_ok=True)
                last_strangers = time.time()
                try:
                    strangers.update(engine, library, log)
                except Exception:
                    log.exception("grouping unknown faces failed")
            if SEARCH:
                try:
                    search.index_new(log)
                except Exception:
                    log.exception("search indexing failed")
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
