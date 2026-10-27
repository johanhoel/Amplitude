"""Package detection: something new left in a "package" zone (e.g. the doorstep) after a visit.

There is no "package" class in the COCO object model, so this compares each package zone with how it looked before:
  * while no event has run for PACKAGE_QUIET_SECONDS, the zone is remembered as its empty reference (every minute);
  * PACKAGE_QUIET_SECONDS after a visit with a person, the zone is compared with that reference. A new, compact
    object (PACKAGE_MIN_AREA..PACKAGE_MAX_AREA of the zone) that is still there, unchanged, PACKAGE_CONFIRM_SECONDS
    later is reported as delivered;
  * after later visits, a zone that looks like the empty reference again is reported as picked up.
Brightness is normalised per patch, so slow daylight changes don't count. A large brightness jump (lights on, IR
switch at dusk) makes the comparison undecidable; it is skipped and a new reference is taken when it is quiet.
This is a heuristic: tune PACKAGE_DIFF / PACKAGE_CHROMA / PACKAGE_MIN_AREA if it reports shadows or misses small parcels.
"""
import cv2
import numpy as np

from common import env

QUIET = env("PACKAGE_QUIET_SECONDS", 20, int)
CONFIRM = env("PACKAGE_CONFIRM_SECONDS", 60, int)
MIN_AREA = env("PACKAGE_MIN_AREA", 0.04, float)
MAX_AREA = env("PACKAGE_MAX_AREA", 0.6, float)
DIFF = env("PACKAGE_DIFF", 45, int)          # local brightness change (Lab L, 0..255) that counts
CHROMA = env("PACKAGE_CHROMA", 12, int)      # colour change (Lab a/b distance) that counts
FORGET_HOURS = 48
WORK_WIDTH = 960
REF_EVERY = 60


class ZonePatch:
    """A zone's bounding box cut out of a frame (at WORK_WIDTH) with what the comparison needs:
    colour (Lab a/b, barely changed by shadows), surface texture (local energy of fine detail, which a flat box
    covers up but a shadow only dims) and smoothed brightness."""

    def __init__(self, zone, frame):
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (WORK_WIDTH, round(h * WORK_WIDTH / w))) if w > WORK_WIDTH else frame
        sh, sw = small.shape[:2]
        pts = np.array([[x * sw, y * sh] for x, y in zone["points"]], dtype=np.int32)
        x, y, bw, bh = cv2.boundingRect(pts)
        self.color = small[y:y + bh, x:x + bw].copy()
        self.mask = np.zeros((bh, bw), np.uint8)
        cv2.fillPoly(self.mask, [pts - np.array([x, y], dtype=np.int32)], 255)
        self.area = max(1, cv2.countNonZero(self.mask))
        lab = cv2.cvtColor(self.color, cv2.COLOR_BGR2LAB).astype(np.float32)
        lum, self.a, self.b = lab[..., 0], cv2.GaussianBlur(lab[..., 1], (0, 0), 3), cv2.GaussianBlur(lab[..., 2], (0, 0), 3)
        inside = lum[self.mask > 0]
        self.mean = float(inside.mean()) if inside.size else 0.0
        self.lum = cv2.GaussianBlur(lum, (0, 0), 6)
        detail = lum - cv2.GaussianBlur(lum, (0, 0), 8)
        self.texture = np.sqrt(cv2.GaussianBlur(detail * detail, (0, 0), 4))


def compare(a, b):
    """(largest changed blob, total changed area) as fractions of the zone; None when the two can't be compared."""
    if a is None or b is None or a.lum.shape != b.lum.shape or abs(a.mean - b.mean) > 45:
        return None
    chroma = np.sqrt((a.a - b.a) ** 2 + (a.b - b.b) ** 2)
    ref_texture = float(np.median(a.texture[a.mask > 0])) + 2.0
    texture = np.abs(a.texture - b.texture) / ref_texture
    lum = np.abs((b.lum - b.mean) - (a.lum - a.mean))           # local brightness change, overall change removed
    changed = (chroma > CHROMA) | (texture > 0.6) | (lum > DIFF)
    th = cv2.bitwise_and(changed.astype(np.uint8) * 255, a.mask)
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blob = max((cv2.contourArea(c) for c in contours), default=0.0) / a.area
    return blob, cv2.countNonZero(th) / a.area


def looks_new(result):
    return result is not None and MIN_AREA <= result[0] <= MAX_AREA and result[1] < 0.75


def looks_same(result):
    return result is not None and result[0] < MIN_AREA / 2


def side_by_side(before, after):
    """'before | now' picture of the zone for the notification."""
    h = 360
    imgs = []
    for patch, text in ((before, "before"), (after, "now")):
        ph, pw = patch.color.shape[:2]
        img = cv2.resize(patch.color, (max(1, round(pw * h / ph)), h))
        cv2.putText(img, text, (10, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 4)
        cv2.putText(img, text, (10, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        imgs.append(img)
    return np.hstack([imgs[0], np.full((h, 8, 3), 40, np.uint8), imgs[1]])


class PackageWatcher:
    def __init__(self, on_change, log):
        self.on_change = on_change  # (kind "delivered" | "picked_up", zone, picture, visit (day, stem)) -> None
        self.log = log
        self.zones = []
        self.empty = {}     # zone name -> ZonePatch of the empty zone
        self.present = {}   # zone name -> {"patch": ZonePatch with the package, "since": t}
        self.pending = []   # visits to look at: {"visit", "after", "candidates": {zone name: {"patch", "t"}}}
        self.last_ref = 0.0

    def set_zones(self, zones):
        if zones != self.zones:
            self.zones, self.empty, self.present, self.pending = list(zones), {}, {}, []

    def visit_ended(self, visit, now):
        """A visit with a person just ended; look at the package zones once it's quiet."""
        if self.zones:
            self.pending.append({"visit": visit, "after": now + QUIET, "candidates": {}})

    def tick(self, frame, now, quiet_since):
        """Call for every analysed frame. quiet_since = when the last event ended (or now while one runs)."""
        if not self.zones or now - quiet_since < QUIET:
            return
        for name in [n for n, p in self.present.items() if now - p["since"] > FORGET_HOURS * 3600]:
            del self.present[name]
        for p in list(self.pending):
            if now >= p["after"]:
                self._check(p, frame, now)
        if not self.pending and now - self.last_ref >= REF_EVERY:
            self.last_ref = now
            for z in self.zones:
                if z["name"] not in self.present:
                    self.empty[z["name"]] = ZonePatch(z, frame)

    def _check(self, p, frame, now):
        waiting = False
        for z in self.zones:
            name, cur = z["name"], ZonePatch(z, frame)
            empty = self.empty.get(name)
            if name in self.present:
                if looks_same(compare(empty, cur)):
                    before = self.present.pop(name)["patch"]
                    self.log.info("package zone %s: picked up (visit %s/%s)", name, *p["visit"])
                    self.on_change("picked_up", z, side_by_side(before, cur), p["visit"])
                continue
            if empty is None:
                continue
            cand = p["candidates"].get(name)
            if cand is None:
                result = compare(empty, cur)
                if looks_new(result):
                    p["candidates"][name] = {"patch": cur, "t": now}
                    waiting = True
                    self.log.info("package zone %s: new object (%.0f%% of zone), confirming in %ss",
                                  name, result[0] * 100, CONFIRM)
            elif now - cand["t"] < CONFIRM:
                waiting = True
            else:
                if looks_same(compare(cand["patch"], cur)) and looks_new(compare(empty, cur)):
                    self.present[name] = {"patch": cur, "since": now}
                    self.log.info("package zone %s: delivered (visit %s/%s)", name, *p["visit"])
                    self.on_change("delivered", z, side_by_side(empty, cur), p["visit"])
                else:
                    self.log.info("package zone %s: change did not last, ignored", name)
                del p["candidates"][name]
        if waiting:
            p["after"] = now + 5
        else:
            self.pending.remove(p)
