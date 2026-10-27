"""Quieter alerts for the household.

When a person event starts, the faces inside the person boxes are checked for up to HOUSEHOLD_WAIT_SECONDS:
  * only known faces          -> one quiet push ("Alex at the camera", ntfy priority low, or min for HOUSEHOLD_ALERTS=silent)
  * an unknown face           -> the normal (loud) alert at once
  * no usable face by the end -> the normal alert
Known = in the photo library (the embeddings facematch keeps in /data/library_cache.json), optionally limited to the
names in HOUSEHOLD. HOUSEHOLD_ALERTS=normal turns this off (every person event alerts loudly and immediately).
"""
import json
from pathlib import Path

import numpy as np

from common import env

MODE = env("HOUSEHOLD_ALERTS", "quiet")            # quiet | silent | normal
WAIT = env("HOUSEHOLD_WAIT_SECONDS", 3.0, float)
NAMES = {n.strip() for n in (env("HOUSEHOLD", "") or "").split(",") if n.strip()}   # empty = everyone in the library
THRESHOLD = env("FACE_MATCH_THRESHOLD", 0.40, float)
CACHE = Path(env("DATA_DIR", "/data")) / "library_cache.json"
PHOTOS = Path(env("PHOTOS_DIR", "/photos"))


class KnownFaces:
    """The reference embeddings facematch computed, reloaded when the cache file changes."""

    def __init__(self):
        self.mtime, self.names, self.embs = None, [], np.zeros((0, 128), np.float32)

    def refresh(self):
        try:
            mtime = CACHE.stat().st_mtime
        except FileNotFoundError:
            return
        if mtime == self.mtime:
            return
        self.mtime = mtime
        try:
            cache = json.loads(CACHE.read_text())
        except ValueError:
            return
        names, embs = [], []
        for path, entry in cache.items():
            if entry.get("emb") is None:
                continue
            try:
                name = Path(path).relative_to(PHOTOS).parts[0]
            except ValueError:
                name = Path(path).parent.name
            names.append(name)
            embs.append(entry["emb"])
        self.names = names
        self.embs = np.array(embs, np.float32) if embs else np.zeros((0, 128), np.float32)

    def match(self, emb):
        if not len(self.names):
            return None, 0.0
        sims = self.embs @ emb
        i = int(np.argmax(sims))
        return self.names[i], float(sims[i])


class HouseholdCheck:
    def __init__(self, log):
        self.log = log
        self.known = KnownFaces()
        self.engine = None

    @property
    def enabled(self):
        if MODE == "normal" or WAIT <= 0:
            return False
        self.known.refresh()
        return bool(self.known.names)

    def faces(self, frame, person_boxes):
        """[(name or None, score)] for the faces inside the person boxes; name None = unknown face."""
        if self.engine is None:
            from facematch import FaceEngine  # the face models are only loaded when this is in use
            self.engine = FaceEngine()
        h, w = frame.shape[:2]
        out = []
        for x, y, bw, bh in person_boxes:
            pad = int(bw * 0.15)
            x0, x1 = max(0, x - pad), min(w, x + bw + pad)
            y0, y1 = max(0, y - pad), min(h, y + int(bh * 0.6))      # the head is in the upper part of the box
            crop = frame[y0:y1, x0:x1]
            if crop.size == 0 or min(crop.shape[:2]) < 24:
                continue
            for face in self.engine.faces(crop, min_size=20, max_width=max(64, crop.shape[1])):
                name, score = self.known.match(face.emb)
                household = name if name and score >= THRESHOLD and (not NAMES or name in NAMES) else None
                out.append((household, score))
        return out


class PendingAlert:
    """A person alert held back for up to WAIT seconds while faces are checked."""

    def __init__(self, event, jpg, what, message, now):
        self.event, self.jpg, self.what, self.message = event, jpg, what, message
        self.deadline = now + WAIT
        self.known = []
        self.unknown = False

    def add(self, results):
        for name, _ in results:
            if name is None:
                self.unknown = True
            elif name not in self.known:
                self.known.append(name)

    def decision(self, now, ended=False):
        """None = keep waiting, "loud" = normal alert, "quiet" = household only."""
        if self.unknown:
            return "loud"
        if now < self.deadline and not ended:
            return None
        return "quiet" if self.known else "loud"

    @property
    def priority(self):
        return "min" if MODE == "silent" else "low"


def people_boxes(found):
    return [d["box"] for d in found if d["label"] == "person"]


def quiet_title(names):
    return ", ".join(names) + (" is" if len(names) == 1 else " are") + " at the camera"

