"""License plate reading (fast-alpr: YOLOv9 plate detector + CCT OCR, ONNX on the CPU or a GPU, see accel.py).

Live use: the recorder calls PlateReader.read() on frames with a moving vehicle and collects
reads per event in a PlateTally; a plate is confirmed after 2 identical reads (or 1 very
confident one) and then matched against the known plates from the web UI.

Backfill: `python plates.py [--force] [YYYY-MM-DD ...]` reads plates in existing recordings.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import cv2

from common import VIDEO_EXT, env, setup_logging

DETECTOR = "yolo-v9-t-640-license-plate-end2end"
OCR = "cct-s-v2-global-model"
MIN_DETECT = env("PLATE_MIN_DETECT", 0.5, float)
MIN_OCR = env("PLATE_MIN_OCR", 0.8, float)


def normalize(text):
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def distance(a, b):
    """Levenshtein distance; OCR often gets one character wrong."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def match_known(plate, known):
    """Known plate entry for `plate` (exact, or one character off for plates of 5+ chars)."""
    best = None
    for k in known:
        d = distance(plate, normalize(k.get("plate")))
        if d == 0 or (d == 1 and len(plate) >= 5):
            if best is None or d < best[0]:
                best = (d, k)
    return best[1] if best else None


class PlateReader:
    def __init__(self, part=None):
        self.part = part
        self._open()

    def _open(self):
        import accel
        from fast_alpr import ALPR
        self.providers = accel.providers()
        error = ""
        for providers in (self.providers, [(accel.CPU, {})]):
            try:
                # fixed thread counts: see accel.session_options
                self.alpr = ALPR(detector_model=DETECTOR, detector_providers=providers,
                                 detector_sess_options=accel.session_options(),
                                 ocr_model=OCR, ocr_device="cpu", ocr_providers=providers,
                                 ocr_sess_options=accel.session_options())
                break
            except Exception as exc:      # a GPU that the driver refuses: try again on the CPU
                if len(providers) == 1:
                    raise
                error = str(exc).splitlines()[0][:300]
        if self.part:
            accel.report(self.part, providers[0][0], error)

    def read(self, frame):
        import accel
        if accel.providers() != self.providers:      # Settings -> Image processing changed
            self._open()
        out = []
        for r in self.alpr.predict(frame):
            if not r.ocr:
                continue
            conf = r.ocr.confidence
            conf = float(sum(conf) / len(conf)) if isinstance(conf, (list, tuple)) else float(conf)
            text = normalize(r.ocr.text)
            if len(text) < 4 or r.detection.confidence < MIN_DETECT or conf < MIN_OCR:
                continue
            bb = r.detection.bounding_box
            out.append({"plate": text, "conf": conf, "box": (bb.x1, bb.y1, bb.x2 - bb.x1, bb.y2 - bb.y1)})
        return out


class PlateTally:
    """Collects reads during one event and decides when a plate is confirmed."""

    def __init__(self):
        self.reads = {}       # plate -> {"count", "conf", "crop"}
        self.announced = set()

    def add(self, frame, reads):
        h, w = frame.shape[:2]
        for r in reads:
            x, y, bw, bh = r["box"]
            pad_x, pad_y = int(bw * 0.6), int(bh * 1.5)
            crop = frame[max(0, y - pad_y):min(h, y + bh + pad_y), max(0, x - pad_x):min(w, x + bw + pad_x)].copy()
            e = self.reads.setdefault(r["plate"], {"count": 0, "conf": 0.0, "crop": None, "first": r["box"]})
            e["count"] += 1
            e["last"] = r["box"]
            if r["conf"] >= e["conf"]:
                e["conf"], e["crop"] = r["conf"], crop

    def moved(self, plate):
        """False if the plate sat in the same place for every read (a parked car)."""
        a, b = self.reads[plate]["first"], self.reads[plate]["last"]
        ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
        iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
        inter = ix * iy
        return inter / float(a[2] * a[3] + b[2] * b[3] - inter or 1) < 0.5

    def newly_confirmed(self, moving_only=False):
        new = []
        for plate, e in sorted(self.reads.items(), key=lambda kv: -kv[1]["count"]):
            if plate in self.announced or not (e["count"] >= 2 or e["conf"] >= 0.97):
                continue
            if moving_only and not self.moved(plate):
                continue
            # A one-character variant of a plate already announced is the same car misread
            if any(distance(plate, a) <= 1 for a in self.announced):
                continue
            self.announced.add(plate)
            new.append(plate)
        return new

    def save(self, folder, stem, known):
        """Write crops for announced plates; returns the list stored in the clip's .json."""
        result = []
        if not self.announced:
            return result
        crops = folder / f"{stem}_plates"
        crops.mkdir(exist_ok=True)
        for plate in sorted(self.announced, key=lambda p: -self.reads[p]["count"]):
            e = self.reads[plate]
            cv2.imwrite(str(crops / f"{plate}.jpg"), e["crop"])
            k = match_known(plate, known)
            result.append({"plate": plate, "name": k.get("name") if k else None, "reads": e["count"],
                           "conf": round(e["conf"], 2), "crop": f"{crops.name}/{plate}.jpg"})
        return result


def backfill(days, force):
    """Read plates in existing recordings (1 frame/s) and add them to each clip's .json."""
    import settings
    log = setup_logging("plates")
    rec = Path(env("RECORDINGS_DIR", "/recordings"))
    known = settings.load().get("plates", [])
    reader = PlateReader()
    for day in sorted(d for d in rec.iterdir() if d.is_dir() and (not days or d.name in days)):
        for video in sorted(p for p in day.iterdir() if p.suffix.lower() in VIDEO_EXT):
            stem = video.name[: -len(video.suffix)]
            meta_file = day / f"{stem}.json"
            try:
                meta = json.loads(meta_file.read_text())
            except (FileNotFoundError, ValueError):
                meta = {}
            if "plates" in meta and not force:
                continue
            tally = PlateTally()
            cap = cv2.VideoCapture(str(video))
            step = max(1, round(cap.get(cv2.CAP_PROP_FPS) or 15))
            idx = 0
            while cap.grab():
                if idx % step == 0:
                    ok, frame = cap.retrieve()
                    if ok:
                        tally.add(frame, reader.read(frame))
                idx += 1
            cap.release()
            tally.newly_confirmed(moving_only=True)  # no vehicle detector here: skip parked cars
            meta["plates"] = tally.save(day, stem, known)
            meta_file.write_text(json.dumps(meta, indent=2))
            log.info("%s/%s: %s", day.name, stem,
                     ", ".join(f"{p['plate']} ({p['reads']}x)" for p in meta["plates"]) or "no plates")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("days", nargs="*", help="only these YYYY-MM-DD folders")
    ap.add_argument("--force", action="store_true", help="re-read clips that already have plates")
    a = ap.parse_args()
    sys.exit(backfill(set(a.days), a.force))
